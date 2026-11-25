import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderGit2, FolderOpen, FolderPlus, GitBranch, RefreshCw, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, LoadingState, PageHeader, Section } from "@/components/common/states";
import { Button, IconButton } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/overlay";
import { type GitInfo, type Project, type ProjectCandidate, api } from "@/lib/api";
import { useOrganizations, useProjectRoots, useProjects } from "@/lib/queries";
import { cn } from "@/lib/utils";

import { FolderPicker } from "./FolderPicker";

/** 로컬 프로젝트 관리. 브라우저는 경로 문자열만 보내고, 탐색·검증은 로컬 백엔드가 등록된 경로 안에서만 한다. */
export function ProjectsPage() {
  const projects = useProjects();
  const roots = useProjectRoots();
  const orgs = useOrganizations();
  const queryClient = useQueryClient();
  const [rootOpen, setRootOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const scan = useQuery({
    queryKey: ["project-scan"],
    queryFn: () => api<ProjectCandidate[]>("/project-roots/scan"),
    enabled: (roots.data?.length ?? 0) > 0,
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["projects"] });
    void queryClient.invalidateQueries({ queryKey: ["project-scan"] });
    void queryClient.invalidateQueries({ queryKey: ["project-roots"] });
  };
  const register = useMutation({
    mutationFn: (path: string) => api<Project>("/projects", { method: "POST", body: { path } }),
    onSuccess: (p) => {
      refresh();
      toast.success(`'${p.name}' 프로젝트를 등록했습니다.`);
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/projects/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  const removeRoot = useMutation({ mutationFn: (id: string) => api(`/project-roots/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const link = useMutation({
    mutationFn: ({ id, organization_id }: { id: string; organization_id: string | null }) =>
      api(`/projects/${id}`, { method: "PATCH", body: { organization_id } }),
    onSuccess: refresh,
  });
  // 폴더 탐색 창에서 고른 폴더를 탐색 경로(깊이 0, 이미 포함되면 생략)와 프로젝트로 한 번에 등록한다(#65).
  const [pickOpen, setPickOpen] = useState(false);
  const [pickOrg, setPickOrg] = useState("");
  const addFromFolder = useMutation({
    mutationFn: async (path: string) => {
      const covered = (roots.data ?? []).some((r) => path === r.path || path.startsWith(`${r.path.replace(/\/$/, "")}/`));
      if (!covered) await api("/project-roots", { method: "POST", body: { path, max_depth: 0 } });
      return api<Project>("/projects", { method: "POST", body: { path, organization_id: pickOrg || null } });
    },
    onSuccess: (p) => {
      refresh();
      setPickOpen(false);
      toast.success(`'${p.name}' 프로젝트를 등록했습니다.`);
    },
    onError: (e) => toast.error(e.message),
  });
  const candidates = (scan.data ?? []).filter((c) => !c.registered);
  const orgName = new Map((orgs.data ?? []).map((o) => [o.id, o.name]));

  return (
    <div className="flex-1 overflow-y-auto">
      <PageHeader
        title="프로젝트"
        description="에이전트가 작업할 로컬 폴더입니다. 탐색 경로로 등록한 폴더 안의 프로젝트만 등록할 수 있습니다."
        actions={
          <>
            <Button variant="primary" onClick={() => setPickOpen(true)}>
              <FolderOpen /> 폴더에서 추가
            </Button>
            <Button onClick={() => setRootOpen(true)}>
              <FolderPlus /> 탐색 경로 추가
            </Button>
          </>
        }
      />
      <div className="grid gap-8 px-6 pb-10 xl:grid-cols-[1.5fr_1fr]">
        <div className="flex flex-col gap-8">
          <Section title={`등록된 프로젝트 ${projects.data?.length ?? ""}`}>
            {projects.isLoading ? <LoadingState /> : null}
            {projects.error ? <ErrorState error={projects.error} /> : null}
            {projects.data?.length === 0 ? (
              <EmptyState icon={<FolderGit2 />} title="등록된 프로젝트가 없습니다">
                탐색 경로를 추가하면 그 아래의 Git 저장소·프로젝트를 찾아 보여 줍니다.
              </EmptyState>
            ) : null}
            <ul className="flex flex-col divide-y divide-border">
              {(projects.data ?? []).map((p) => (
                <li key={p.id} className="flex flex-col gap-2 py-3">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      className="min-w-0 flex-1 cursor-pointer text-left"
                      onClick={() => setSelected(selected === p.id ? null : p.id)}
                      aria-expanded={selected === p.id}
                    >
                      <span className="block truncate text-sm font-medium hover:text-primary-text">{p.name}</span>
                      <span className="block truncate font-mono text-xs text-faint">{p.path}</span>
                    </button>
                    <span className="rounded-sm bg-surface-3 px-1.5 py-0.5 text-2xs text-muted">{p.kind}</span>
                    {!p.exists ? <span className="text-xs text-danger">경로 없음</span> : null}
                    <Select
                      aria-label={`${p.name} 연결 조직`}
                      className="w-40"
                      value={p.organization_id ?? ""}
                      onChange={(e) => link.mutate({ id: p.id, organization_id: e.target.value || null })}
                    >
                      <option value="">연결된 조직 없음</option>
                      {(orgs.data ?? []).map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.name}
                        </option>
                      ))}
                    </Select>
                    <IconButton label={`${p.name} 등록 해제(파일은 지우지 않음)`} size="icon-sm" onClick={() => remove.mutate(p.id)}>
                      <Trash2 />
                    </IconButton>
                  </div>
                  {selected === p.id ? <GitPanel projectId={p.id} /> : null}
                  {p.organization_id && selected !== p.id ? (
                    <span className="text-2xs text-faint">조직: {orgName.get(p.organization_id)}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </Section>
        </div>
        <div className="flex flex-col gap-8">
          <Section
            title="찾은 프로젝트"
            actions={
              <IconButton label="다시 탐색" size="icon-sm" onClick={() => void scan.refetch()}>
                <RefreshCw className={cn(scan.isFetching && "animate-spin")} />
              </IconButton>
            }
          >
            {roots.data?.length === 0 ? <p className="text-sm text-muted">탐색 경로를 먼저 추가하세요.</p> : null}
            {scan.isLoading ? <LoadingState label="탐색하는 중…" /> : null}
            {scan.data && candidates.length === 0 ? <p className="text-sm text-muted">새로 등록할 프로젝트가 없습니다.</p> : null}
            <ul className="flex flex-col gap-1">
              {candidates.map((c) => (
                <li key={c.path} className="flex items-center gap-2 py-1">
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 text-sm">
                      {c.is_git ? <GitBranch className="size-3.5 text-faint" aria-label="Git 저장소" /> : null}
                      {c.name}
                    </span>
                    <span className="block truncate font-mono text-2xs text-faint">{c.path}</span>
                  </span>
                  <Button size="sm" onClick={() => register.mutate(c.path)} disabled={register.isPending}>
                    등록
                  </Button>
                </li>
              ))}
            </ul>
          </Section>
          <Section title="탐색 경로">
            <ul className="flex flex-col gap-1">
              {(roots.data ?? []).map((r) => (
                <li key={r.id} className="flex items-center gap-2 text-sm">
                  <span className="min-w-0 flex-1 truncate font-mono text-xs">{r.path}</span>
                  <span className="text-2xs text-faint">깊이 {r.max_depth}</span>
                  {!r.exists ? <span className="text-xs text-danger">없음</span> : null}
                  <IconButton label={`${r.path} 탐색 경로 제거`} size="icon-sm" onClick={() => removeRoot.mutate(r.id)}>
                    <Trash2 />
                  </IconButton>
                </li>
              ))}
            </ul>
            <p className="text-xs text-faint">전체 디스크 탐색은 지원하지 않습니다. 필요한 폴더만 등록하세요.</p>
          </Section>
        </div>
      </div>
      <AddRootDialog open={rootOpen} onOpenChange={setRootOpen} onDone={refresh} />
      <FolderPicker
        open={pickOpen}
        onOpenChange={setPickOpen}
        title="폴더에서 프로젝트 추가"
        description="에이전트가 일할 컴퓨터의 폴더입니다(홈 폴더 안). 폴더로 들어간 뒤 '이 폴더 추가'를 누르세요."
        confirmLabel="이 폴더 추가"
        pending={addFromFolder.isPending}
        onPick={(path) => addFromFolder.mutate(path)}
        extra={
          <Field label="연결할 조직" hint="이 조직의 새 대화가 이 프로젝트에서 시작합니다.">
            {(id) => (
              <Select id={id} value={pickOrg} onChange={(e) => setPickOrg(e.target.value)}>
                <option value="">연결 안 함</option>
                {(orgs.data ?? []).map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        }
      />
    </div>
  );
}

function GitPanel({ projectId }: { projectId: string }) {
  const detail = useQuery({ queryKey: ["project", projectId], queryFn: () => api<Project & { git: GitInfo }>(`/projects/${projectId}`) });
  if (detail.isLoading) return <LoadingState label="Git 상태 확인 중…" />;
  const git = detail.data?.git;
  if (!git) return null;
  if (!git.is_repo) return <p className="text-xs text-faint">Git 저장소가 아닙니다.</p>;
  return (
    <dl className="grid grid-cols-[6rem_1fr] gap-y-1 rounded-md bg-surface-2 px-3 py-2 text-xs">
      <dt className="text-faint">브랜치</dt>
      <dd className="font-mono">{git.branch ?? "(detached)"}</dd>
      <dt className="text-faint">최근 커밋</dt>
      <dd className="truncate">
        <span className="font-mono text-muted">{git.head}</span> {git.head_subject}
      </dd>
      <dt className="text-faint">작업 트리</dt>
      <dd>{git.dirty_files ? `변경된 파일 ${git.dirty_files}개` : "깨끗함"}</dd>
      {git.ahead !== null ? (
        <>
          <dt className="text-faint">원격 대비</dt>
          <dd className="tabular">
            앞섬 {git.ahead} · 뒤처짐 {git.behind}
          </dd>
        </>
      ) : null}
      {git.remote ? (
        <>
          <dt className="text-faint">원격</dt>
          <dd className="truncate font-mono">{git.remote}</dd>
        </>
      ) : null}
    </dl>
  );
}

function AddRootDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (v: boolean) => void; onDone: () => void }) {
  const [path, setPath] = useState("");
  const [browsing, setBrowsing] = useState(false);
  const [depth, setDepth] = useState(2);
  const add = useMutation({
    mutationFn: () => api("/project-roots", { method: "POST", body: { path, max_depth: depth } }),
    onSuccess: () => {
      onDone();
      setPath("");
      onOpenChange(false);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate();
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="탐색 경로 추가" description="이 폴더 아래에서 Git 저장소와 프로젝트(package.json, pyproject.toml 등)를 찾습니다.">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <Field label="절대 경로" error={add.error?.message} hint="예: /home/사용자/code">
            {(id) => (
              <div className="flex gap-2">
                <Input
                  id={id}
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  placeholder="/home/you/code…"
                  spellCheck={false}
                  className="font-mono"
                  aria-invalid={Boolean(add.error)}
                />
                <Button onClick={() => setBrowsing(true)}>
                  <FolderOpen /> 찾아보기
                </Button>
              </div>
            )}
          </Field>
          <Field label="탐색 깊이" hint="0이면 이 폴더 자체만, 2면 두 단계 아래까지 찾습니다.">
            {(id) => (
              <Select id={id} value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
                {[0, 1, 2, 3, 4].map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <DialogFooter>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              취소
            </Button>
            <Button type="submit" variant="primary" disabled={!path.trim() || add.isPending}>
              추가
            </Button>
          </DialogFooter>
        </form>
        <FolderPicker
          open={browsing}
          onOpenChange={setBrowsing}
          title="탐색 경로 고르기"
          confirmLabel="이 폴더 사용"
          onPick={(picked) => {
            setPath(picked);
            setBrowsing(false);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
