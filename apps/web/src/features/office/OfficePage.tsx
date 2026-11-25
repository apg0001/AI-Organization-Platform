import { Crosshair, Network } from "lucide-react";
import Phaser from "phaser";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import { EmptyState, LoadingState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { onLive } from "@/lib/live";
import { useCurrentOrg, useOrganization } from "@/lib/queries";

import { deskRowsFor } from "./behavior";
import { createDefaultOffice, ZONE_GUIDE, ZONE_LABELS } from "./grid";
import { OfficeScene } from "./OfficeScene";
import { toOfficeState } from "./orgOffice";

/**
 * 아이소메트릭 사무실. Agent Office 렌더러(OfficeScene)를 그대로 쓰고, 조직의 실제 에이전트 상태를 입력한다.
 * 캐릭터 위치는 연출이고 사실은 에이전트 상태(서버)다. 활동 구역은 실행 이벤트의 최근 도구 분류를 따른다.
 */
interface Handoff {
  id: string;
  from: string;
  to: string;
  kind: "delegated" | "review";
}

export default function OfficePage() {
  const { orgId } = useCurrentOrg();
  const org = useOrganization(orgId);
  const navigate = useNavigate();
  const hostRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<OfficeScene | null>(null);
  const gameRef = useRef<Phaser.Game | null>(null);
  const [autoFocus, setAutoFocus] = useState(true);
  const [recent, setRecent] = useState<Record<string, string>>({});
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const names = useMemo(() => new Map((org.data?.agents ?? []).map((a) => [a.id, a.name])), [org.data]);

  useEffect(
    () =>
      onLive((event) => {
        if (event.type === "agent.status" && typeof event.agent_id === "string") {
          const detail = typeof event.detail === "string" ? event.detail : "";
          setRecent((r) => ({ ...r, [event.agent_id as string]: detail }));
        }
        if (event.type === "task.delegated" && event.organization_id === orgId) {
          const from = String(event.from_agent_id);
          const to = String(event.to_agent_id);
          const kind = event.kind === "review" ? "review" : "delegated";
          sceneRef.current?.handoff(from, to, kind);
          const id = `${String(event.task_id)}-${Date.now()}`;
          setHandoffs((h) => [...h.slice(-3), { id, from, to, kind }]);
          window.setTimeout(() => setHandoffs((h) => h.filter((x) => x.id !== id)), 6000);
        }
      }),
    [orgId],
  );

  const state = useMemo(() => toOfficeState(org.data?.agents ?? [], recent), [org.data, recent]);

  useEffect(() => {
    if (!hostRef.current || !org.data) return;
    {
      const scene = new OfficeScene(createDefaultOffice(deskRowsFor(state)), state);
      scene.onSelect = (agentId) => navigate(`/agents/${agentId}`);
      scene.onCameraChange = (camera) => setAutoFocus(camera.autoFocus);
      sceneRef.current = scene;
      gameRef.current = new Phaser.Game({
        type: Phaser.AUTO,
        parent: hostRef.current,
        backgroundColor: "#0e1015",
        pixelArt: true,
        scale: { mode: Phaser.Scale.RESIZE, width: hostRef.current.clientWidth, height: hostRef.current.clientHeight },
        scene,
        banner: false,
      });
    }
    return () => {
      gameRef.current?.destroy(true);
      gameRef.current = null;
      sceneRef.current = null;
    };
    // 조직이 바뀔 때만 장면을 새로 만든다. 상태 변화는 applyState로 전달한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [org.data?.id]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    const rows = deskRowsFor(state);
    if (rows !== scene.rows) scene.setMap(createDefaultOffice(rows));
    scene.applyState(state);
  }, [state]);

  if (!orgId) {
    return (
      <div className="p-6">
        <EmptyState icon={<Network />} title="조직이 없습니다" action={<Button asChild><Link to="/builder">조직 설계</Link></Button>} />
      </div>
    );
  }
  if (org.isLoading) return <LoadingState className="p-6" />;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-6 py-3">
        <h1 className="text-md font-semibold">{org.data?.name} 사무실</h1>
        <span className="text-xs text-faint">캐릭터를 누르면 에이전트 상세로 이동합니다. 끌어서 이동, 휠로 확대·축소.</span>
        <Button
          size="sm"
          className="ml-auto"
          variant={autoFocus ? "ghost" : "secondary"}
          onClick={() => sceneRef.current?.resumeFocus()}
          disabled={autoFocus}
        >
          <Crosshair /> {autoFocus ? "자동 초점 중" : "자동 초점 다시 켜기"}
        </Button>
      </header>
      <div className="relative min-h-0 flex-1">
        <div ref={hostRef} className="absolute inset-0" />
        {/* 업무 전달 기록: 연출과 같은 사실을 글로도 알린다(스크린 리더·동작 줄이기 사용자). */}
        <ol aria-live="polite" aria-label="최근 업무 전달" className="pointer-events-none absolute top-3 right-3 flex w-72 flex-col gap-1.5">
          {handoffs.map((h) => (
            <li key={h.id} className="feed-in rounded-md border border-border bg-surface-1/95 px-3 py-2 text-xs shadow-overlay">
              <span className="font-medium">{names.get(h.from) ?? "에이전트"}</span>
              <span className="text-faint"> → </span>
              <span className="font-medium">{names.get(h.to) ?? "에이전트"}</span>
              <span className="ml-1.5 text-muted">{h.kind === "review" ? "검토 요청" : "업무 전달"}</span>
            </li>
          ))}
        </ol>
        <details className="absolute bottom-3 left-3 max-w-xs rounded-md border border-border bg-surface-1/95 px-3 py-2 text-xs">
          <summary className="cursor-pointer text-muted">구역 안내</summary>
          <ul className="mt-2 flex flex-col gap-1">
            {ZONE_GUIDE.map((z) => (
              <li key={z.zone}>
                <span className="font-medium">{ZONE_LABELS[z.zone]}</span> — <span className="text-muted">{z.meaning}</span>
              </li>
            ))}
          </ul>
        </details>
      </div>
    </div>
  );
}
