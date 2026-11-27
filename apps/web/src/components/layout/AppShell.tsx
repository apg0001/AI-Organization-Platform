import { useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  BellOff,
  Blocks,
  Building2,
  Check,
  CircleHelp,
  Palette,
  ChevronsUpDown,
  FolderGit2,
  Gauge,
  LayoutDashboard,
  LogOut,
  MessagesSquare,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Settings,
  Sparkles,
  UserRound,
} from "lucide-react";
import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { toast } from "sonner";

import { Dialog, Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@/components/ui/overlay";
import { AccountDialog } from "@/features/auth/AccountDialog";
import { useAuth } from "@/features/auth/AuthGate";
import { markVisited, setGuideHidden } from "@/features/guide/guide";
import { api } from "@/lib/api";
import {
  disableBrowserNotifications,
  enableBrowserNotifications,
  isDesktopShell,
  notificationsSupported,
  useBrowserNotifications,
} from "@/lib/notify";
import { THEMES, type ThemeChoice, setTheme, useTheme } from "@/lib/theme";
import { useLiveConnected } from "@/lib/live";
import { UsageMeter } from "@/features/usage/UsagePage";
import { useApprovals, useCurrentOrg, useOrganizations, useProjects, useSystemInfo, useUsage } from "@/lib/queries";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "대시보드", icon: LayoutDashboard, end: true },
  { to: "/command", label: "커맨드 센터", icon: MessagesSquare },
  { to: "/organization", label: "조직", icon: Network },
  { to: "/office", label: "사무실", icon: Building2 },
  { to: "/projects", label: "프로젝트", icon: FolderGit2 },
  { to: "/capabilities", label: "기능 관리", icon: Blocks },
  { to: "/usage", label: "사용량", icon: Gauge },
];

const RAIL_KEY = "ai-org.sidebar.rail";

/**
 * 주 사이드바 안에 화면별 내용을 넣는 자리(#79). 커맨드 센터는 대화 목록을 여기에 그린다.
 * rail이면 사이드바가 아이콘 막대로 접힌 상태다.
 */
export const SidebarSlotContext = createContext<{ slot: HTMLElement | null; rail: boolean; setRail: (v: boolean) => void }>({
  slot: null,
  rail: false,
  setRail: () => undefined,
});
export const useSidebarSlot = () => useContext(SidebarSlotContext);

export function AppShell() {
  const { pathname } = useLocation();
  useEffect(() => markVisited(pathname), [pathname]);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const [rail, setRailState] = useState(() => localStorage.getItem(RAIL_KEY) === "1");
  const setRail = (v: boolean) => {
    localStorage.setItem(RAIL_KEY, v ? "1" : "0");
    setRailState(v);
  };
  // Ctrl+B(맥은 ⌘B)로 사이드바 접기·펴기. 입력 중이어도 동작한다(편집기 단축키와 겹치지 않음).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setRailState((v) => {
          localStorage.setItem(RAIL_KEY, v ? "0" : "1");
          return !v;
        });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <SidebarSlotContext.Provider value={{ slot, rail, setRail }}>
    <div className="flex h-full min-h-0">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-surface-2 px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        본문으로 건너뛰기
      </a>
      <AppSidebar rail={rail} setRail={setRail} onSlot={setSlot} />
      <main id="main" className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
    </SidebarSlotContext.Provider>
  );
}

function AppSidebar({
  rail,
  setRail,
  onSlot,
}: {
  rail: boolean;
  setRail: (v: boolean) => void;
  onSlot: (el: HTMLElement | null) => void;
}) {
  const { orgId } = useCurrentOrg();
  const approvals = useApprovals(orgId);
  const pending = approvals.data?.length ?? 0;
  return (
    <nav
      aria-label="주 메뉴"
      data-rail={rail}
      className="group/side flex w-60 shrink-0 flex-col border-r border-border bg-surface-1 transition-[width] duration-150 max-md:w-14 data-[rail=true]:w-14"
    >
      {/* 상단 줄: 조직 전환 + 사이드바 접기·펴기(#95). 접힌 막대에서는 접기 버튼이 맨 위, 조직 표시가 그 아래로 쌓인다. */}
      <div className="flex items-center gap-1 px-2 pt-2 group-data-[rail=true]/side:flex-col-reverse group-data-[rail=true]/side:items-stretch">
        <OrgSwitcher />
        <button
          type="button"
          onClick={() => setRail(!rail)}
          aria-label={rail ? "사이드바 펴기" : "사이드바 접기"}
          aria-expanded={!rail}
          title={`${rail ? "사이드바 펴기" : "사이드바 접기"} (Ctrl+B)`}
          className="grid size-8 shrink-0 cursor-pointer place-items-center rounded-md text-muted transition-colors duration-[120ms] hover:bg-surface-2 hover:text-fg max-md:hidden group-data-[rail=true]/side:w-full"
        >
          {rail ? <PanelLeftOpen className="size-4" aria-hidden /> : <PanelLeftClose className="size-4" aria-hidden />}
        </button>
      </div>
      <ul className="flex flex-col gap-0.5 px-2 pt-2">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              title={label}
              className={({ isActive }) =>
                cn(
                  "flex h-8 items-center gap-2.5 rounded-md px-2 text-sm transition-colors duration-[120ms]",
                  isActive ? "bg-surface-3 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg",
                )
              }
            >
              <Icon className="size-4 shrink-0" aria-hidden />
              <span className="truncate max-md:sr-only group-data-[rail=true]/side:sr-only">{label}</span>
              {to === "/command" && pending > 0 ? (
                <span
                  className="ml-auto rounded-sm bg-warning px-1.5 text-2xs font-semibold text-on-warning tabular max-md:hidden group-data-[rail=true]/side:hidden"
                  title={`승인 대기 ${pending}건`}
                >
                  {pending}
                </span>
              ) : null}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="px-2 pt-1">
        <NavLink
          to="/builder"
          title="조직 설계"
          className={({ isActive }) =>
            cn(
              "flex h-8 items-center gap-2.5 rounded-md px-2 text-sm transition-colors",
              isActive ? "bg-surface-3 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg",
            )
          }
        >
          <Sparkles className="size-4 shrink-0 text-primary-text" aria-hidden />
          <span className="max-md:sr-only group-data-[rail=true]/side:sr-only">조직 설계</span>
        </NavLink>
      </div>
      {/* 화면별 내용(커맨드 센터의 대화 목록). 접힌 막대·좁은 화면에서는 숨긴다. */}
      <div ref={onSlot} className="flex min-h-0 flex-1 flex-col max-md:hidden group-data-[rail=true]/side:hidden" />
      <PreferencesMenu />
      <UserMenu />
      <SystemStatus />
    </nav>
  );
}

function OrgSwitcher() {
  const { orgId, setOrgId } = useCurrentOrg();
  const orgs = useOrganizations();
  const projects = useProjects();
  const navigate = useNavigate();
  const current = orgs.data?.find((o) => o.id === orgId);
  // 조직마다 연결된 프로젝트를 함께 보여 준다(조직 전환 = 팀 전환이고 폴더는 대화마다 정해진다, #79).
  const projectsOf = (id: string) => (projects.data ?? []).filter((p) => p.organization_id === id).map((p) => p.name);
  const projectLine = (id: string) => {
    const names = projectsOf(id);
    return names.length === 0 ? "연결된 프로젝트 없음" : names.length === 1 ? names[0]! : `${names[0]} 외 ${names.length - 1}`;
  };
  return (
    <Menu>
      <MenuTrigger
        className="flex h-11 min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-md px-2 text-left transition-colors hover:bg-surface-2 data-[state=open]:bg-surface-2"
        aria-label="조직 선택"
      >
        <span className="grid size-7 shrink-0 place-items-center rounded-md bg-primary-soft font-pixel text-xs text-primary-text">
          {(current?.name ?? "AI").slice(0, 1)}
        </span>
        <span className="flex min-w-0 flex-1 flex-col max-md:hidden group-data-[rail=true]/side:hidden">
          <span className="truncate text-sm font-medium">{current?.name ?? "조직 없음"}</span>
          <span className="truncate text-2xs text-faint">
            {current ? (
              <>
                <FolderGit2 className="mr-0.5 inline size-3 align-[-2px]" aria-hidden />
                {projectLine(current.id)} · {current.agent_count}명
              </>
            ) : (
              "조직을 만들어 시작하세요"
            )}
          </span>
        </span>
        <ChevronsUpDown className="size-3.5 text-faint max-md:hidden group-data-[rail=true]/side:hidden" aria-hidden />
      </MenuTrigger>
      <MenuContent align="start" className="w-64">
        <MenuLabel>조직(팀) — 작업 폴더는 대화마다 고릅니다</MenuLabel>
        {(orgs.data ?? []).map((org) => (
          <MenuItem key={org.id} onSelect={() => setOrgId(org.id)}>
            <span className="flex min-w-0 flex-col">
              <span className={cn("truncate", org.id === orgId && "font-medium text-primary-text")}>{org.name}</span>
              <span className="truncate text-2xs text-faint">
                <FolderGit2 className="mr-0.5 inline size-3 align-[-2px]" aria-hidden />
                {projectLine(org.id)}
              </span>
            </span>
          </MenuItem>
        ))}
        {orgs.data?.length === 0 ? <p className="px-2 py-1.5 text-xs text-faint">아직 조직이 없습니다.</p> : null}
        <MenuSeparator />
        <MenuItem onSelect={() => navigate("/builder")}>
          <Plus /> 새 조직 만들기
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}

/** 테마 선택과 시작 가이드 다시 열기. 로그인한 경우 테마를 계정 설정에도 저장한다. */
function PreferencesMenu() {
  const theme = useTheme();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const choose = (t: ThemeChoice) => {
    setTheme(t);
    if (user) {
      void api("/auth/me", { method: "PATCH", body: { settings: { ...user.settings, theme: t } } }).then(
        () => queryClient.invalidateQueries({ queryKey: ["auth"] }),
        () => undefined,
      );
    }
  };
  return (
    <Menu>
      <MenuTrigger
        className="mx-2 mb-1 flex h-9 cursor-pointer items-center gap-2 rounded-md px-2 text-left text-sm text-muted transition-colors hover:bg-surface-2 hover:text-fg"
        aria-label="화면 설정"
      >
        <Palette className="size-4 shrink-0" aria-hidden />
        <span className="truncate max-md:sr-only group-data-[rail=true]/side:sr-only">화면 설정</span>
      </MenuTrigger>
      <MenuContent align="start" side="top" className="w-52">
        <MenuLabel>테마</MenuLabel>
        {THEMES.map((t) => (
          <MenuItem key={t.id} onSelect={() => choose(t.id)} aria-checked={theme === t.id} role="menuitemradio">
            <Check className={cn(theme === t.id ? "opacity-100" : "opacity-0")} /> {t.label}
          </MenuItem>
        ))}
        <MenuSeparator />
        <NotificationItem />
        <MenuItem
          onSelect={() => {
            setGuideHidden(false);
            navigate("/");
          }}
        >
          <CircleHelp /> 시작 가이드 보기
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}

/** 브라우저 알림 켜기·끄기. 데스크톱 앱 창에서는 앱이 알림을 보내므로 안내만 한다. */
function NotificationItem() {
  const on = useBrowserNotifications();
  if (isDesktopShell()) return <MenuLabel>알림: 데스크톱 앱이 보냅니다</MenuLabel>;
  if (!notificationsSupported()) return <MenuLabel>이 브라우저는 알림을 지원하지 않습니다</MenuLabel>;
  return (
    <MenuItem
      onSelect={() => {
        if (on) {
          disableBrowserNotifications();
          return;
        }
        void enableBrowserNotifications().then((p) => {
          if (p === "granted") toast.success("브라우저 알림을 켰습니다. 이 탭이 안 보일 때 승인 요청·작업 완료·사용량 경고를 알립니다.");
          else toast.error("알림 권한이 거부되어 있습니다. 브라우저 사이트 설정에서 허용해 주세요.");
        });
      }}
    >
      {on ? <BellOff /> : <Bell />} {on ? "브라우저 알림 끄기" : "브라우저 알림 켜기"}
    </MenuItem>
  );
}

function UserMenu() {
  const { user, authEnabled, logout } = useAuth();
  const [open, setOpen] = useState(false);
  if (!authEnabled || !user) return null;
  return (
    <>
      <Menu>
        <MenuTrigger
          className="mx-2 mb-1 flex h-9 cursor-pointer items-center gap-2 rounded-md px-2 text-left text-sm text-muted transition-colors hover:bg-surface-2 hover:text-fg"
          aria-label="계정 메뉴"
        >
          <UserRound className="size-4 shrink-0" aria-hidden />
          <span className="truncate max-md:sr-only group-data-[rail=true]/side:sr-only">{user.display_name}</span>
        </MenuTrigger>
        <MenuContent align="start" side="top" className="w-52">
          <MenuLabel>{user.username}</MenuLabel>
          <MenuItem onSelect={() => setOpen(true)}>
            <Settings /> 계정 설정
          </MenuItem>
          <MenuItem onSelect={() => void logout()}>
            <LogOut /> 로그아웃
          </MenuItem>
        </MenuContent>
      </Menu>
      <Dialog open={open} onOpenChange={setOpen}>
        {open ? <AccountDialog onClose={() => setOpen(false)} /> : null}
      </Dialog>
    </>
  );
}

/** 사이드바 아래 Claude 사용률(켜져 있고 값이 있을 때만). */
function UsageMini() {
  const usage = useUsage();
  const claude = usage.data?.providers.find((p) => p.id === "claude" && p.state === "ok");
  const w = claude?.windows[0];
  if (!w) return null;
  return (
    <NavLink to="/usage" className="flex flex-col gap-1 rounded-md px-1 py-1 hover:bg-surface-2" title={`Claude ${w.label} ${w.percent.toFixed(0)}%`}>
      <span className="flex justify-between">
        <span>Claude {w.label}</span>
        <span className="tabular">{w.percent.toFixed(0)}%</span>
      </span>
      <UsageMeter window={w} compact />
    </NavLink>
  );
}

function SystemStatus() {
  const info = useSystemInfo();
  const live = useLiveConnected();
  const claude = info.data?.runtimes.find((r) => r.id === "claude-code");
  return (
    <div className="flex flex-col gap-1.5 border-t border-border px-3 py-3 text-2xs text-faint max-md:hidden group-data-[rail=true]/side:hidden">
      <UsageMini />
      <span className="flex items-center gap-1.5" title={claude?.detail ?? claude?.path ?? undefined}>
        <span
          className="size-1.5 rounded-full"
          style={{ background: claude?.available ? "var(--success)" : "var(--danger)" }}
          aria-hidden
        />
        {info.isLoading
          ? "Claude Code 확인 중…"
          : claude?.available
            ? claude.version === "fake"
              ? claude.name
              : `Claude Code ${claude.version ?? ""}`
            : "Claude Code를 찾지 못함"}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="size-1.5 rounded-full" style={{ background: live ? "var(--success)" : "var(--warning)" }} aria-hidden />
        {live ? "실시간 연결됨" : "실시간 연결 재시도 중…"}
      </span>
    </div>
  );
}
