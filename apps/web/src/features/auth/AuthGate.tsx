/**
 * 인증 게이트: 첫 계정 만들기 → 로그인 → 앱. 앱 로그인은 Claude Code 인증과 별개다(Claude Code는 CLI 로그인을 쓴다).
 * 로그인을 끈 설치(AI_ORG_AUTH=off)에서는 바로 앱을 보여 준다.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, createContext, useContext, useEffect, useState } from "react";

import { AgentAvatar } from "@/components/agent/AgentAvatar";
import { ErrorState, LoadingState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { type AuthStatus, type AuthUser, UNAUTHORIZED_EVENT, api } from "@/lib/api";
import { getTheme, isTheme, setTheme } from "@/lib/theme";

interface AuthContextValue {
  user: AuthUser | null;
  authEnabled: boolean;
  logout: () => Promise<void>;
  refresh: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  authEnabled: false,
  logout: async () => undefined,
  refresh: () => undefined,
});
export const useAuth = () => useContext(AuthContext);

export function AuthGate({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["auth"], queryFn: () => api<AuthStatus>("/auth/status"), staleTime: 60_000 });
  useEffect(() => {
    const onUnauthorized = () => void queryClient.invalidateQueries({ queryKey: ["auth"] });
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [queryClient]);

  // 로그인한 계정에 저장된 테마가 있으면 이 브라우저에도 적용한다(다른 기기에서 고른 테마를 따라감).
  const savedTheme = status.data?.user?.settings.theme;
  useEffect(() => {
    if (isTheme(savedTheme) && savedTheme !== getTheme()) setTheme(savedTheme);
  }, [savedTheme]);

  if (status.isLoading) return <LoadingState className="p-6" />;
  if (status.error || !status.data) return <ErrorState className="m-6" error={status.error} retry={() => void status.refetch()} />;
  const s = status.data;
  const refresh = () => {
    queryClient.clear();
    void status.refetch();
  };
  if (s.auth_enabled && s.setup_required) return <AuthScreen mode="setup" onDone={refresh} />;
  if (s.auth_enabled && !s.authenticated) return <AuthScreen mode="login" onDone={refresh} />;
  const value: AuthContextValue = {
    user: s.user,
    authEnabled: s.auth_enabled,
    refresh,
    logout: async () => {
      await api("/auth/logout", { method: "POST" });
      refresh();
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function AuthScreen({ mode, onDone }: { mode: "setup" | "login"; onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const submit = useMutation({
    mutationFn: () =>
      mode === "setup"
        ? api("/auth/setup", { method: "POST", body: { username, password, display_name: displayName } })
        : api("/auth/login", { method: "POST", body: { username, password } }),
    onSuccess: onDone,
  });
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (mode === "setup" && password !== confirm) {
      setLocalError("비밀번호 확인이 일치하지 않습니다.");
      return;
    }
    submit.mutate();
  };
  const error = localError ?? submit.error?.message ?? null;
  return (
    <main className="grid min-h-full place-items-center px-4 py-10">
      <form onSubmit={onSubmit} className="flex w-full max-w-sm flex-col gap-5" aria-labelledby="auth-title">
        <div className="flex items-center gap-3">
          <AgentAvatar id="ai-org-ceo" lead size={44} />
          <div>
            <h1 id="auth-title" className="text-lg font-semibold">
              {mode === "setup" ? "AI 조직을 시작합니다" : "다시 오신 걸 환영합니다"}
            </h1>
            <p className="text-sm text-muted">
              {mode === "setup" ? "이 컴퓨터에서 쓸 관리자 계정을 만드세요." : "계정으로 로그인하세요."}
            </p>
          </div>
        </div>
        <Field label="아이디" hint={mode === "setup" ? "영문·숫자·._- 3~40자" : undefined}>
          {(id) => (
            <Input id={id} name="username" autoComplete="username" spellCheck={false} value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
          )}
        </Field>
        {mode === "setup" ? (
          <Field label="표시 이름(선택)">
            {(id) => <Input id={id} name="display_name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />}
          </Field>
        ) : null}
        <Field label="비밀번호" hint={mode === "setup" ? "8자 이상" : undefined}>
          {(id) => (
            <Input
              id={id}
              name="password"
              type="password"
              autoComplete={mode === "setup" ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          )}
        </Field>
        {mode === "setup" ? (
          <Field label="비밀번호 확인">
            {(id) => (
              <Input id={id} name="confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            )}
          </Field>
        ) : null}
        {error ? (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        ) : null}
        <Button type="submit" variant="primary" size="lg" disabled={submit.isPending}>
          {submit.isPending ? "확인하는 중…" : mode === "setup" ? "계정 만들기" : "로그인"}
        </Button>
        <p className="text-xs text-faint">
          {mode === "setup"
            ? "이 계정은 이 앱을 보호합니다. Claude Code 로그인과는 별개이며, 에이전트는 CLI에 로그인된 Claude Code를 씁니다."
            : "비밀번호를 잊었으면 터미널에서 `ai-org-admin reset-auth`로 계정을 초기화할 수 있습니다(조직·대화는 유지)."}
        </p>
      </form>
    </main>
  );
}
