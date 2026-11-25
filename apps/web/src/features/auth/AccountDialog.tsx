import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { DialogContent, DialogFooter } from "@/components/ui/overlay";
import { api } from "@/lib/api";

import { useAuth } from "./AuthGate";

/** 계정 설정: 표시 이름, 비밀번호 변경(다른 브라우저 세션은 끊긴다). */
export function AccountDialog({ onClose }: { onClose: () => void }) {
  const { user, refresh } = useAuth();
  const [name, setName] = useState(user?.display_name ?? "");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const rename = useMutation({
    mutationFn: () => api("/auth/me", { method: "PATCH", body: { display_name: name } }),
    onSuccess: () => {
      toast.success("표시 이름을 바꿨습니다.");
      refresh();
    },
    onError: (e) => toast.error(e.message),
  });
  const change = useMutation({
    mutationFn: () => api("/auth/password", { method: "POST", body: { current_password: current, new_password: next } }),
    onSuccess: () => {
      toast.success("비밀번호를 바꿨습니다. 다른 브라우저의 로그인은 끊겼습니다.");
      setCurrent("");
      setNext("");
      onClose();
    },
  });
  const submitPassword = (e: FormEvent) => {
    e.preventDefault();
    change.mutate();
  };
  return (
    <DialogContent title="계정" description={`아이디: ${user?.username ?? ""}`}>
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          rename.mutate();
        }}
      >
        <Field label="표시 이름" className="flex-1">
          {(id) => <Input id={id} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Button type="submit" disabled={rename.isPending || !name.trim()}>
          저장
        </Button>
      </form>
      <form onSubmit={submitPassword} className="mt-6 flex flex-col gap-3 border-t border-border pt-5">
        <h3 className="text-sm font-semibold">비밀번호 변경</h3>
        <Field label="현재 비밀번호">
          {(id) => <Input id={id} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />}
        </Field>
        <Field label="새 비밀번호" hint="8자 이상" error={change.error?.message}>
          {(id) => <Input id={id} type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required minLength={8} />}
        </Field>
        <DialogFooter>
          <Button type="submit" variant="primary" disabled={change.isPending}>
            비밀번호 변경
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
