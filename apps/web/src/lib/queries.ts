/** 서버 상태 훅(react-query). 키 규칙은 live.ts의 무효화 규칙과 같다. */

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";

import {
  type Approval,
  type Capability,
  type CommandSpec,
  type ConversationDetail,
  type Conversation,
  type Design,
  type Organization,
  type OrganizationSummary,
  type Project,
  type ProjectRoot,
  type Revision,
  type SystemInfo,
  type Task,
  type Template,
  type UsagePayload,
  type Workspace,
  api,
} from "./api";

export const useWorkspace = () => useQuery({ queryKey: ["workspace"], queryFn: () => api<Workspace>("/workspace") });
export const useSystemInfo = () =>
  useQuery({ queryKey: ["system"], queryFn: () => api<SystemInfo>("/system/info"), staleTime: 60_000 });
export const useOrganizations = () =>
  useQuery({ queryKey: ["organizations"], queryFn: () => api<OrganizationSummary[]>("/organizations") });
export const useOrganization = (id: string | null | undefined) =>
  useQuery({
    queryKey: ["organization", id],
    queryFn: () => api<Organization>(`/organizations/${id}`),
    enabled: Boolean(id),
  });
export const useProjects = () => useQuery({ queryKey: ["projects"], queryFn: () => api<Project[]>("/projects") });
export const useProjectRoots = () =>
  useQuery({ queryKey: ["project-roots"], queryFn: () => api<ProjectRoot[]>("/project-roots") });
export const useCapabilities = () =>
  useQuery({ queryKey: ["capabilities"], queryFn: () => api<Capability[]>("/capabilities"), staleTime: 30_000 });
export const useTemplates = () =>
  useQuery({ queryKey: ["templates"], queryFn: () => api<Template[]>("/templates"), staleTime: Infinity });
export const useCommands = () =>
  useQuery({ queryKey: ["commands"], queryFn: () => api<CommandSpec[]>("/commands"), staleTime: Infinity });
export const useTasks = (orgId: string | null) =>
  useQuery({
    queryKey: ["tasks", orgId],
    queryFn: () => api<Task[]>(`/tasks?organization_id=${orgId}`),
    enabled: Boolean(orgId),
  });
export const useApprovals = (orgId: string | null) =>
  useQuery({
    queryKey: ["approvals", orgId],
    queryFn: () => api<Approval[]>(`/approvals?organization_id=${orgId}`),
    enabled: Boolean(orgId),
  });
export const useConversations = (orgId: string | null) =>
  useQuery({
    queryKey: ["conversations", orgId],
    queryFn: () => api<Conversation[]>(`/conversations?organization_id=${orgId}`),
    enabled: Boolean(orgId),
  });
export const useConversation = (id: string | null) =>
  useQuery({
    queryKey: ["conversation", id],
    queryFn: () => api<ConversationDetail>(`/conversations/${id}`),
    enabled: Boolean(id),
  });
export const useUsage = () =>
  useQuery({ queryKey: ["usage"], queryFn: () => api<UsagePayload>("/usage"), refetchInterval: 60_000 });
export const useDesign = (id: string | undefined) =>
  useQuery({ queryKey: ["design", id], queryFn: () => api<Design>(`/designs/${id}`), enabled: Boolean(id) });
export const useRevisions = (orgId: string | null) =>
  useQuery({
    queryKey: ["revisions", orgId],
    queryFn: () => api<Revision[]>(`/organizations/${orgId}/revisions`),
    enabled: Boolean(orgId),
  });

// ── 현재 조직(운영 모드의 범위) ───────────────────────────────────────────

export interface CurrentOrg {
  orgId: string | null;
  setOrgId: (id: string | null) => void;
}

export const CurrentOrgContext = createContext<CurrentOrg>({ orgId: null, setOrgId: () => undefined });
export const useCurrentOrg = () => useContext(CurrentOrgContext);
export const CURRENT_ORG_KEY = "ai-org.current-organization";
