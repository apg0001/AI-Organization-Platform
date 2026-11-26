import { describe, expect, it } from "vitest";

import type { AgentPermissions, ApprovalGroup } from "./api";
import {
  BUSY_MESSAGE,
  type CellState,
  GROUPS,
  admitChange,
  applyPreset,
  badgesOf,
  cellState,
  effectiveState,
  escalations,
  isEscalation,
  nextState,
  rebasePermissions,
  ruleInputProblem,
  samePermissions,
  setCell,
  statesOf,
} from "./permissions";

/** 백엔드 기본값(schemas.py AgentPermissions)과 같다. */
const base: AgentPermissions = {
  permission_mode: "default",
  file_scope: [],
  allow_shell: false,
  allow_network: true,
  allow_file_write: true,
  allow_file_delete: false,
  require_approval: ["shell", "file_write", "file_delete", "mcp"],
  can_delegate: false,
  allow_rules: [],
};
const with_ = (patch: Partial<AgentPermissions>): AgentPermissions => ({ ...base, ...patch });

describe("칸 3상태 ↔ allow_*·require_approval", () => {
  it("백엔드 기본값을 읽는다", () => {
    expect(GROUPS.map((g) => cellState(base, g))).toEqual(["deny", "ask", "deny", "allow", "deny", "ask"]);
  });

  it("상태별로 쓰는 필드 값", () => {
    const allow = setCell(base, "shell", "allow");
    expect([allow.allow_shell, allow.require_approval.includes("shell")]).toEqual([true, false]);
    const ask = setCell(base, "shell", "ask");
    expect([ask.allow_shell, ask.require_approval.includes("shell")]).toEqual([true, true]);
    const deny = setCell(allow, "shell", "deny");
    expect([deny.allow_shell, deny.require_approval.includes("shell")]).toEqual([false, true]);
    // 위임은 can_delegate에 대응한다.
    expect(setCell(base, "delegate", "ask").can_delegate).toBe(true);
    expect(setCell(base, "delegate", "ask").require_approval).toContain("delegate");
  });

  it("모든 묶음·모든 상태가 왕복한다(쓴 상태를 그대로 읽는다)", () => {
    for (const group of GROUPS) {
      for (const state of statesOf(group)) {
        for (const start of [base, with_({ allow_shell: true, require_approval: [] })]) {
          expect(cellState(setCell(start, group, state), group)).toBe(state);
        }
      }
    }
  });

  it("다른 묶음과 허용 리스트는 건드리지 않고 입력을 바꾸지 않는다", () => {
    const start = with_({ allow_rules: ["Bash(npm test:*)"] });
    const frozen = JSON.stringify(start);
    const next = setCell(start, "shell", "allow");
    expect(JSON.stringify(start)).toBe(frozen);
    for (const group of GROUPS.filter((g) => g !== "shell")) expect(cellState(next, group)).toBe(cellState(start, group));
    expect(next.allow_rules).toEqual(["Bash(npm test:*)"]);
    expect(next.require_approval).toEqual(["file_write", "file_delete", "mcp"]);
  });

  it("허용 → 승인 필요 → 금지 → 허용으로 순환한다", () => {
    const seen: CellState[] = [];
    let perms = setCell(base, "shell", "allow");
    for (let i = 0; i < 3; i += 1) {
      perms = setCell(perms, "shell", nextState("shell", cellState(perms, "shell")));
      seen.push(cellState(perms, "shell"));
    }
    expect(seen).toEqual(["ask", "deny", "allow"]);
  });

  it("MCP는 allow_* 필드가 없어 허용 ↔ 승인 필요만 있다", () => {
    expect(statesOf("mcp")).toEqual(["allow", "ask"]);
    expect(nextState("mcp", "allow")).toBe("ask");
    expect(nextState("mcp", "ask")).toBe("allow");
    expect(setCell(base, "mcp", "deny")).toBe(base);
    expect(cellState(setCell(base, "mcp", "allow"), "mcp")).toBe("allow");
  });
});

describe("프리셋", () => {
  const open = with_({
    permission_mode: "acceptEdits",
    allow_shell: true,
    allow_file_delete: true,
    can_delegate: true,
    require_approval: ["delegate"],
    allow_rules: ["Bash(git status:*)", "Read(src/**)"],
    file_scope: ["apps/web"],
  });
  const cells = (p: AgentPermissions) => Object.fromEntries(GROUPS.map((g) => [g, cellState(p, g)])) as Record<ApprovalGroup, CellState>;

  it("안전: 셸·수정·삭제·네트워크 금지, MCP 승인", () => {
    const next = applyPreset(open, "safe");
    expect(next.permission_mode).toBe("default");
    expect(cells(next)).toEqual({ shell: "deny", file_write: "deny", file_delete: "deny", network: "deny", delegate: "ask", mcp: "ask" });
    expect(next).toMatchObject({ allow_shell: false, allow_file_write: false, allow_file_delete: false, allow_network: false, can_delegate: true });
    expect([...next.require_approval].sort()).toEqual(["delegate", "file_delete", "file_write", "mcp", "network", "shell"]);
  });

  it("표준: 셸·수정 승인, 삭제 금지, 네트워크 허용", () => {
    const next = applyPreset(open, "standard");
    expect(next.permission_mode).toBe("default");
    expect(cells(next)).toEqual({ shell: "ask", file_write: "ask", file_delete: "deny", network: "allow", delegate: "ask", mcp: "ask" });
    expect(next).toMatchObject({ allow_shell: true, allow_file_write: true, allow_file_delete: false, allow_network: true });
    expect([...next.require_approval].sort()).toEqual(["delegate", "file_delete", "file_write", "mcp", "shell"]);
  });

  it("자율: auto 모드, 삭제 칸은 그대로", () => {
    const next = applyPreset(base, "autonomous");
    expect(next.permission_mode).toBe("auto");
    expect(cells(next)).toEqual({ shell: "ask", file_write: "ask", file_delete: "deny", network: "allow", delegate: "deny", mcp: "ask" });
    expect(next).toMatchObject({ allow_shell: true, allow_file_write: true, allow_file_delete: false, allow_network: true });
    expect(applyPreset(open, "autonomous").allow_file_delete).toBe(true);
  });

  it("어느 프리셋도 허용 리스트·위임·작업 범위를 바꾸지 않는다", () => {
    for (const preset of ["safe", "standard", "autonomous"] as const) {
      const next = applyPreset(open, preset);
      expect(next.allow_rules).toEqual(["Bash(git status:*)", "Read(src/**)"]);
      expect(next.can_delegate).toBe(true);
      expect(cellState(next, "delegate")).toBe("ask");
      expect(next.file_scope).toEqual(["apps/web"]);
      expect(applyPreset(base, preset).can_delegate).toBe(false);
    }
  });

  it("같은 프리셋을 다시 적용해도 결과가 같다", () => {
    for (const preset of ["safe", "standard", "autonomous"] as const) {
      const once = applyPreset(open, preset);
      expect(samePermissions(once, applyPreset(once, preset))).toBe(true);
    }
  });
});

describe("확대 판정", () => {
  it("금지→승인 필요, 금지→허용, 승인 필요→허용은 확대다", () => {
    expect(isEscalation(base, setCell(base, "shell", "ask"))).toBe(true);
    expect(isEscalation(base, setCell(base, "shell", "allow"))).toBe(true);
    expect(isEscalation(base, setCell(base, "file_write", "allow"))).toBe(true);
    expect(escalations(base, setCell(base, "shell", "ask"))).toEqual(["셸: 금지 → 승인 필요"]);
  });

  it("좁히는 변경은 확대가 아니다", () => {
    expect(isEscalation(base, setCell(base, "file_write", "deny"))).toBe(false);
    expect(isEscalation(base, setCell(base, "network", "ask"))).toBe(false);
    expect(isEscalation(base, base)).toBe(false);
    expect(isEscalation(with_({ permission_mode: "auto" }), base)).toBe(false);
    expect(isEscalation(with_({ allow_rules: ["WebSearch"] }), base)).toBe(false);
  });

  it("모드 상향과 auto 켜기는 확대다", () => {
    expect(isEscalation(base, with_({ permission_mode: "acceptEdits" }))).toBe(true);
    expect(isEscalation(base, with_({ permission_mode: "auto" }))).toBe(true);
    expect(isEscalation(with_({ permission_mode: "plan" }), base)).toBe(true);
    expect(isEscalation(base, with_({ permission_mode: "plan" }))).toBe(false);
    expect(isEscalation(with_({ permission_mode: "acceptEdits" }), base)).toBe(false);
    expect(escalations(base, with_({ permission_mode: "auto" }))[0]).toContain("auto");
  });

  it("허용 규칙 추가는 확대, 삭제는 아니다", () => {
    expect(escalations(base, with_({ allow_rules: ["Bash(npm test:*)"] }))).toEqual(["허용 규칙 추가: Bash(npm test:*)"]);
    expect(isEscalation(with_({ allow_rules: ["A", "B"] }), with_({ allow_rules: ["B"] }))).toBe(false);
  });

  it("프리셋: 기본값에서 안전은 확대가 아니고 표준·자율은 확대다", () => {
    expect(escalations(base, applyPreset(base, "safe"))).toEqual([]);
    expect(escalations(base, applyPreset(base, "standard"))).toEqual(["셸: 금지 → 승인 필요"]);
    expect(isEscalation(base, applyPreset(base, "autonomous"))).toBe(true);
  });

  it("좁히는 점이 섞여 있어도 넓어지는 점이 있으면 확대다", () => {
    const mixed = setCell(setCell(base, "file_write", "deny"), "shell", "ask");
    expect(escalations(base, mixed)).toEqual(["셸: 금지 → 승인 필요"]);
  });

  it("셸을 켜면 '셸 금지로 막힘'이던 삭제가 함께 풀리는 것도 사유에 나온다", () => {
    const blocked = with_({ allow_file_delete: true }); // 셸 금지 + 삭제 칸은 승인 필요
    expect(effectiveState(blocked, "file_delete")).toBe("deny");
    expect(escalations(blocked, setCell(blocked, "shell", "ask"))).toEqual(["셸: 금지 → 승인 필요", "삭제: 금지 → 승인 필요"]);
    const free = with_({ allow_file_delete: true, require_approval: ["shell"] });
    expect(escalations(free, setCell(free, "shell", "ask"))).toEqual(["셸: 금지 → 승인 필요", "삭제: 금지 → 허용"]);
    // 자율 프리셋도 삭제가 풀리는 것을 알린다.
    expect(escalations(blocked, applyPreset(blocked, "autonomous")).some((r) => r.startsWith("삭제: 금지 → Claude 판단"))).toBe(true);
    // 삭제 칸이 금지면 셸을 켜도 삭제는 그대로다.
    expect(escalations(base, setCell(base, "shell", "ask"))).toEqual(["셸: 금지 → 승인 필요"]);
    // 반대로 셸을 끄는 것은 확대가 아니다.
    expect(isEscalation(setCell(blocked, "shell", "ask"), blocked)).toBe(false);
  });

  it("default → auto: 승인 필요였던 묶음이 Claude 판단이 되는 것을 사유에 넣는다", () => {
    const reasons = escalations(base, with_({ permission_mode: "auto" }));
    expect(reasons[0]).toContain("삭제·위임을 포함해 묶음별 승인이 적용되지 않고");
    expect(reasons).toContain("파일 수정: 승인 필요 → Claude 판단(승인 없이 실행될 수 있음)");
    expect(reasons).toContain("MCP: 승인 필요 → Claude 판단(승인 없이 실행될 수 있음)");
    // 금지·허용 칸은 auto에서도 그대로라 사유에 없다.
    expect(reasons.some((r) => r.startsWith("셸:") || r.startsWith("네트워크:"))).toBe(false);
    // auto → default는 Claude 판단 → 승인 필요로 좁아진다.
    expect(isEscalation(with_({ permission_mode: "auto" }), base)).toBe(false);
    // auto 안에서 승인 필요 → 허용은 여전히 확대다.
    const auto = with_({ permission_mode: "auto" });
    expect(escalations(auto, setCell(auto, "file_write", "allow"))).toEqual(["파일 수정: Claude 판단(승인 없이 실행될 수 있음) → 허용"]);
  });
});

describe("오래된 화면 값으로 만든 변경을 최신 값에 다시 얹기", () => {
  it("방금 금지로 바꾼 칸을 옛 값으로 되살리지 않는다(연속 클릭)", () => {
    const stale = setCell(base, "shell", "ask"); // 화면이 아직 들고 있는 값
    const latest = setCell(stale, "shell", "deny"); // 방금 저장된 서버 값
    const clicked = setCell(stale, "network", "ask"); // 옛 값에서 네트워크 칸만 누름
    const rebased = rebasePermissions(stale, clicked, latest);
    expect(cellState(rebased, "shell")).toBe("deny");
    expect(cellState(rebased, "network")).toBe("ask");
    expect(escalations(latest, rebased)).toEqual([]);
    // 다시 얹지 않으면 확인 창 없이 셸이 켜지는 변경이었다.
    expect(escalations(latest, clicked)).toContain("셸: 금지 → 승인 필요");
  });

  it("그 사이 '항상 허용'으로 늘어난 규칙을 지우지 않는다", () => {
    const stale = with_({ allow_rules: ["WebSearch"] });
    const latest = with_({ allow_rules: ["WebSearch", "Bash(npm test:*)"] });
    expect(rebasePermissions(stale, { ...stale, allow_network: false }, latest).allow_rules).toEqual(["WebSearch", "Bash(npm test:*)"]);
    // 사용자가 지운 규칙만 빠지고, 더한 규칙은 뒤에 붙는다(중복 없이).
    expect(rebasePermissions(stale, with_({ allow_rules: [] }), latest).allow_rules).toEqual(["Bash(npm test:*)"]);
    expect(rebasePermissions(stale, with_({ allow_rules: ["WebSearch", "WebFetch"] }), latest).allow_rules).toEqual(["WebSearch", "Bash(npm test:*)", "WebFetch"]);
    expect(rebasePermissions(stale, with_({ allow_rules: ["WebSearch", "Bash(npm test:*)"] }), latest).allow_rules).toEqual(["WebSearch", "Bash(npm test:*)"]);
  });

  it("모드도 바꾼 경우에만 옮긴다. 최신 값이 화면 값과 같으면 next 그대로다", () => {
    const latest = with_({ permission_mode: "plan" });
    expect(rebasePermissions(base, setCell(base, "network", "ask"), latest).permission_mode).toBe("plan");
    expect(rebasePermissions(base, with_({ permission_mode: "auto" }), latest).permission_mode).toBe("auto");
    for (const next of [setCell(base, "shell", "allow"), applyPreset(base, "safe"), applyPreset(base, "autonomous")]) {
      expect(samePermissions(rebasePermissions(base, next, base), next)).toBe(true);
    }
    // 금지 칸의 승인 체크만 바꾼 변경(편집기)도 옮긴다.
    const unchecked = { ...base, require_approval: base.require_approval.filter((g) => g !== "shell") };
    expect(rebasePermissions(base, unchecked, latest).require_approval).toEqual(["file_write", "file_delete", "mcp"]);
    const frozen = JSON.stringify(latest);
    rebasePermissions(base, applyPreset(base, "standard"), latest);
    expect(JSON.stringify(latest)).toBe(frozen);
  });
});

describe("저장 중 잠금", () => {
  it("잠금 중 요청은 거부하고 알린다(조용히 버리지 않는다)", () => {
    const notified: string[] = [];
    expect(admitChange(true, (m) => notified.push(m))).toBe(false);
    expect(notified).toEqual([BUSY_MESSAGE]);
    expect(BUSY_MESSAGE).toContain("반영되지 않았습니다");
  });
  it("잠금이 아니면 받고 알리지 않는다", () => {
    const notified: string[] = [];
    expect(admitChange(false, (m) => notified.push(m))).toBe(true);
    expect(notified).toEqual([]);
  });
});

describe("조직도 배지", () => {
  it("기본값: 승인 필요 + 셸 금지", () => {
    expect(badgesOf(base)).toEqual(["approval", "no-shell"]);
  });
  it("auto 모드에서는 승인 필요 대신 auto", () => {
    expect(badgesOf(applyPreset(base, "autonomous"))).toEqual(["auto"]);
    expect(badgesOf(with_({ permission_mode: "auto" }))).toEqual(["auto", "no-shell"]);
  });
  it("plan 모드에서는 승인 필요 대신 계획만", () => {
    expect(badgesOf(with_({ permission_mode: "plan" }))).toEqual(["plan", "no-shell"]);
    expect(badgesOf(with_({ permission_mode: "plan", allow_shell: true }))).toEqual(["plan"]);
  });
  it("셸 금지로 막힌 삭제만 승인 대상이면 승인 필요 배지가 없다", () => {
    expect(badgesOf(with_({ allow_file_delete: true, require_approval: ["file_delete"] }))).toEqual(["no-shell"]);
  });
  it("승인을 거치는 묶음이 없으면 승인 필요 배지가 없다", () => {
    expect(badgesOf(with_({ allow_shell: true, require_approval: [] }))).toEqual([]);
    // 금지된 묶음만 승인 목록에 있으면 실제로 승인받을 일이 없다.
    expect(badgesOf(with_({ allow_file_write: false, require_approval: ["shell", "file_write", "file_delete"] }))).toEqual(["no-shell"]);
  });
});

describe("허용 리스트 입력", () => {
  it("빈 값·중복·길이·개수만 미리 거른다", () => {
    expect(ruleInputProblem([], "  ")).toBe("규칙을 입력하세요.");
    expect(ruleInputProblem(["WebSearch"], " WebSearch ")).toBe("이미 있는 규칙입니다.");
    expect(ruleInputProblem([], `Read(${"a".repeat(200)})`)).toContain("200자");
    expect(ruleInputProblem(Array.from({ length: 50 }, (_, i) => `Read(f${i})`), "WebSearch")).toContain("50개");
    expect(ruleInputProblem(["WebSearch"], "Bash(npm test:*)")).toBeNull();
  });
});
