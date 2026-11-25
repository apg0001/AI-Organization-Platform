import {
  Blocks,
  Building2,
  ChevronsUpDown,
  FolderGit2,
  LayoutDashboard,
  LogOut,
  MessagesSquare,
  Network,
  Plus,
  Settings,
  Sparkles,
  UserRound,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";

import { Dialog, Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@/components/ui/overlay";
import { AccountDialog } from "@/features/auth/AccountDialog";
import { useAuth } from "@/features/auth/AuthGate";
import { useLiveConnected } from "@/lib/live";
import { useApprovals, useCurrentOrg, useOrganizations, useSystemInfo } from "@/lib/queries";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "대시보드", icon: LayoutDashboard, end: true },
  { to: "/command", label: "커맨드 센터", icon: MessagesSquare },
  { to: "/organization", label: "조직", icon: Network },
  { to: "/office", label: "사무실", icon: Building2 },
  { to: "/projects", label: "프로젝트", icon: FolderGit2 },
  { to: "/capabilities", label: "기능 관리", icon: Blocks },
];

export function AppShell() {
  return (
    <div className="flex h-full min-h-0">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-surface-2 px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        본문으로 건너뛰기
      </a>
      <AppSidebar />
      <main id="main" className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}

function AppSidebar() {
  const { orgId } = useCurrentOrg();
  const approvals = useApprovals(orgId);
  const pending = approvals.data?.length ?? 0;
  return (
    <nav
      aria-label="주 메뉴"
      className="flex w-56 shrink-0 flex-col border-r border-border bg-surface-1 max-md:w-14"
    >
      <OrgSwitcher />
      <ul className="flex flex-col gap-0.5 px-2 pt-2">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex h-8 items-center gap-2.5 rounded-md px-2 text-sm transition-colors duration-[120ms]",
                  isActive ? "bg-surface-3 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg",
                )
              }
            >
              <Icon className="size-4 shrink-0" aria-hidden />
              <span className="truncate max-md:sr-only">{label}</span>
              {to === "/command" && pending > 0 ? (
                <span
                  className="ml-auto rounded-sm bg-warning px-1.5 text-2xs font-semibold text-[#1a1306] tabular max-md:hidden"
                  title={`승인 대기 ${pending}건`}
                >
                  {pending}
                </span>
              ) : null}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="px-2 pt-4">
        <NavLink
          to="/builder"
          className={({ isActive }) =>
            cn(
              "flex h-8 items-center gap-2.5 rounded-md px-2 text-sm transition-colors",
              isActive ? "bg-surface-3 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg",
            )
          }
        >
          <Sparkles className="size-4 shrink-0 text-primary-text" aria-hidden />
          <span className="max-md:sr-only">조직 설계</span>
        </NavLink>
      </div>
      <div className="mt-auto" />
      <UserMenu />
      <SystemStatus />
    </nav>
  );
}

function OrgSwitcher() {
  const { orgId, setOrgId } = useCurrentOrg();
  const orgs = useOrganizations();
  const navigate = useNavigate();
  const current = orgs.data?.find((o) => o.id === orgId);
  return (
    <Menu>
      <MenuTrigger
        className="mx-2 mt-2 flex h-11 cursor-pointer items-center gap-2 rounded-md px-2 text-left transition-colors hover:bg-surface-2 data-[state=open]:bg-surface-2"
        aria-label="조직 선택"
      >
        <span className="grid size-7 shrink-0 place-items-center rounded-md bg-primary-soft font-pixel text-xs text-primary-text">
          {(current?.name ?? "AI").slice(0, 1)}
        </span>
        <span className="flex min-w-0 flex-1 flex-col max-md:hidden">
          <span className="truncate text-sm font-medium">{current?.name ?? "조직 없음"}</span>
          <span className="truncate text-2xs text-faint">
            {current ? `에이전트 ${current.agent_count}명` : "조직을 만들어 시작하세요"}
          </span>
        </span>
        <ChevronsUpDown className="size-3.5 text-faint max-md:hidden" aria-hidden />
      </MenuTrigger>
      <MenuContent align="start" className="w-60">
        <MenuLabel>조직</MenuLabel>
        {(orgs.data ?? []).map((org) => (
          <MenuItem key={org.id} onSelect={() => setOrgId(org.id)}>
            <span className={cn("truncate", org.id === orgId && "font-medium text-primary-text")}>{org.name}</span>
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
          <span className="truncate max-md:sr-only">{user.display_name}</span>
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

function SystemStatus() {
  const info = useSystemInfo();
  const live = useLiveConnected();
  const claude = info.data?.runtimes.find((r) => r.id === "claude-code");
  return (
    <div className="flex flex-col gap-1.5 border-t border-border px-3 py-3 text-2xs text-faint max-md:hidden">
      <span className="flex items-center gap-1.5" title={claude?.detail ?? claude?.path ?? undefined}>
        <span
          className="size-1.5 rounded-full"
          style={{ background: claude?.available ? "var(--success)" : "var(--danger)" }}
          aria-hidden
        />
        {info.isLoading
          ? "Claude Code 확인 중…"
          : claude?.available
            ? `Claude Code ${claude.version ?? ""}`
            : "Claude Code를 찾지 못함"}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="size-1.5 rounded-full" style={{ background: live ? "var(--success)" : "var(--warning)" }} aria-hidden />
        {live ? "실시간 연결됨" : "실시간 연결 재시도 중…"}
      </span>
    </div>
  );
}
