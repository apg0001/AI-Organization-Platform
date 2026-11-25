/**
 * 서버 컴퓨터의 폴더를 앱 안에서 둘러보고 고르는 탐색 창(#65).
 * 브라우저 파일 창은 실제 경로를 주지 않고, 원격으로 쓰면 접속한 컴퓨터의 디스크를 보여 주므로
 * 에이전트가 실제로 일할 컴퓨터(로컬 백엔드)의 홈 폴더 안을 보여 준다. 하위 폴더만 보이고 파일은 보이지 않는다.
 */

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, CornerLeftUp, Folder, FolderGit2, Home } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { ErrorState, LoadingState } from "@/components/common/states";
import { Button, IconButton } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/overlay";
import { type FolderListing, api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** 홈 기준 경로 조각(이동 버튼용). */
export function crumbs(path: string, home: string): { label: string; path: string }[] {
  const out = [{ label: "홈", path: home }];
  if (!path.startsWith(home) || path === home) return out;
  let current = home;
  for (const part of path.slice(home.length).split("/").filter(Boolean)) {
    current = `${current}/${part}`;
    out.push({ label: part, path: current });
  }
  return out;
}

export function FolderPicker({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  onPick,
  pending,
  extra,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  confirmLabel: string;
  onPick: (path: string) => void;
  pending?: boolean;
  /** 확인 버튼 위에 둘 추가 입력(예: 연결할 조직). */
  extra?: ReactNode;
}) {
  const [path, setPath] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    if (!open) setPath(null);
  }, [open]);
  const listing = useQuery({
    queryKey: ["fs-browse", path, hidden],
    queryFn: () =>
      api<FolderListing>(`/fs/browse?${new URLSearchParams({ ...(path ? { path } : {}), hidden: String(hidden) })}`),
    enabled: open,
    placeholderData: (previous) => previous,
  });
  const data = listing.data;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} description={description} wide>
        <div className="flex flex-col gap-3">
          <nav aria-label="현재 위치" className="flex min-w-0 flex-wrap items-center gap-0.5 text-sm">
            {data
              ? crumbs(data.path, data.home).map((c, i, all) => (
                  <span key={c.path} className="flex items-center gap-0.5">
                    {i > 0 ? <ChevronRight className="size-3.5 text-faint" aria-hidden /> : null}
                    <button
                      type="button"
                      onClick={() => setPath(c.path)}
                      aria-current={i === all.length - 1 ? "location" : undefined}
                      className={cn(
                        "flex items-center gap-1 rounded-sm px-1.5 py-0.5 hover:bg-surface-3",
                        i === all.length - 1 ? "font-medium text-fg" : "text-muted",
                      )}
                    >
                      {i === 0 ? <Home className="size-3.5" aria-hidden /> : null}
                      {c.label}
                    </button>
                  </span>
                ))
              : null}
          </nav>
          <div className="flex items-center gap-2">
            <IconButton
              label="상위 폴더"
              size="icon-sm"
              disabled={!data?.parent}
              onClick={() => data?.parent && setPath(data.parent)}
            >
              <CornerLeftUp />
            </IconButton>
            <code className="min-w-0 flex-1 truncate font-mono text-xs text-muted" title={data?.path}>
              {data?.path ?? "…"}
            </code>
            <label className="flex items-center gap-1.5 text-xs text-muted">
              <input type="checkbox" checked={hidden} onChange={(e) => setHidden(e.target.checked)} />
              숨김 폴더
            </label>
          </div>
          <div className="h-80 overflow-y-auto rounded-md border border-border bg-surface-1">
            {listing.isLoading ? <LoadingState className="p-4" label="폴더를 읽는 중…" /> : null}
            {listing.error ? <ErrorState className="m-3" error={listing.error} retry={() => void listing.refetch()} /> : null}
            {data && data.entries.length === 0 ? <p className="p-4 text-sm text-muted">하위 폴더가 없습니다.</p> : null}
            <ul aria-label="하위 폴더">
              {data?.entries.map((e) => (
                <li key={e.path}>
                  <button
                    type="button"
                    onClick={() => setPath(e.path)}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-surface-2"
                  >
                    {e.is_git ? (
                      <FolderGit2 className="size-4 shrink-0 text-primary-text" aria-label="Git 저장소" />
                    ) : (
                      <Folder className="size-4 shrink-0 text-faint" aria-hidden />
                    )}
                    <span className="min-w-0 flex-1 truncate">{e.name}</span>
                    {e.kind !== "unknown" ? <span className="text-2xs text-faint">{e.kind}</span> : null}
                    <ChevronRight className="size-3.5 shrink-0 text-faint" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
            {data?.truncated ? <p className="p-3 text-xs text-faint">폴더가 많아 500개까지만 보입니다.</p> : null}
          </div>
          {extra}
          <DialogFooter>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              취소
            </Button>
            <Button variant="primary" disabled={!data || pending} onClick={() => data && onPick(data.path)}>
              {confirmLabel}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
