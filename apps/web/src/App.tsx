import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, lazy, Suspense, useEffect, useMemo, useState } from "react";
import { createBrowserRouter, Outlet, RouterProvider } from "react-router";
import { Toaster } from "sonner";

import { LoadingState } from "@/components/common/states";
import { AppShell } from "@/components/layout/AppShell";
import { TooltipProvider } from "@/components/ui/overlay";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { useLiveConnection } from "@/lib/live";
import { CURRENT_ORG_KEY, CurrentOrgContext, useOrganizations } from "@/lib/queries";

// Phaser(약 1.2MB)는 사무실 화면에 들어갈 때만 받는다.
const OfficePage = lazy(() => import("@/features/office/OfficePage"));
const ProjectsPage = lazy(() => import("@/features/projects/ProjectsPage").then((m) => ({ default: m.ProjectsPage })));
const OrganizationPage = lazy(() => import("@/features/organization/OrganizationPage").then((m) => ({ default: m.OrganizationPage })));
const CommandCenter = lazy(() => import("@/features/command/CommandCenter").then((m) => ({ default: m.CommandCenter })));
const CapabilitiesPage = lazy(() => import("@/features/capabilities/CapabilitiesPage").then((m) => ({ default: m.CapabilitiesPage })));
const BuilderWorkspace = lazy(() => import("@/features/builder/BuilderWorkspace").then((m) => ({ default: m.BuilderWorkspace })));
const BuilderHome = lazy(() => import("@/features/builder/BuilderHome").then((m) => ({ default: m.BuilderHome })));
const AgentDetailPage = lazy(() => import("@/features/agents/AgentDetailPage").then((m) => ({ default: m.AgentDetailPage })));

function page(node: ReactNode, label?: string) {
  return <Suspense fallback={<LoadingState label={label} className="p-6" />}>{node}</Suspense>;
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, retry: 1, refetchOnWindowFocus: false } },
});

const router = createBrowserRouter([
  {
    element: <Root />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "command", element: page(<CommandCenter />) },
          { path: "command/:conversationId", element: page(<CommandCenter />) },
          { path: "organization", element: page(<OrganizationPage />) },
          { path: "agents/:agentId", element: page(<AgentDetailPage />) },
          { path: "office", element: page(<OfficePage />, "사무실을 불러오는 중…") },
          { path: "projects", element: page(<ProjectsPage />) },
          { path: "capabilities", element: page(<CapabilitiesPage />) },
          { path: "builder", element: page(<BuilderHome />) },
          { path: "builder/:designId", element: page(<BuilderWorkspace />) },
        ],
      },
    ],
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

function Root() {
  useLiveConnection();
  return (
    <CurrentOrgProvider>
      <Outlet />
      <Toaster theme="dark" position="bottom-right" toastOptions={{ className: "!bg-surface-2 !border-border-strong !text-fg" }} />
    </CurrentOrgProvider>
  );
}

/** 현재 조직: localStorage에 기억하고, 없거나 지워졌으면 첫 조직을 고른다. */
function CurrentOrgProvider({ children }: { children: ReactNode }) {
  const orgs = useOrganizations();
  const [orgId, setOrgIdState] = useState<string | null>(() => localStorage.getItem(CURRENT_ORG_KEY));
  useEffect(() => {
    if (!orgs.data) return;
    if (!orgId || !orgs.data.some((o) => o.id === orgId)) {
      setOrgIdState(orgs.data[0]?.id ?? null);
    }
  }, [orgs.data, orgId]);
  const value = useMemo(
    () => ({
      orgId,
      setOrgId: (id: string | null) => {
        setOrgIdState(id);
        if (id) localStorage.setItem(CURRENT_ORG_KEY, id);
        else localStorage.removeItem(CURRENT_ORG_KEY);
      },
    }),
    [orgId],
  );
  return <CurrentOrgContext.Provider value={value}>{children}</CurrentOrgContext.Provider>;
}
