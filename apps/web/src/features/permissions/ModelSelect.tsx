/**
 * 에이전트의 Claude 모델 선택 상자(권한 표·권한 팝오버 공용). 고르면 바로 저장한다.
 * 기존 에이전트 PATCH에 `{ model }`만 보낸다(권한 등 다른 필드는 건드리지 않는다).
 * 저장 중에는 이 상자만 잠그고, 실패하면 서버 사유를 알린 뒤 값이 서버 값으로 돌아간다(값을 서버 상태에서 읽기 때문).
 * 권한 확대가 아니므로 확인 창은 없다. 다음 실행부터 적용된다.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Select } from "@/components/ui/form";
import { type Agent, type Organization, api } from "@/lib/api";
import { modelLabel, modelOptions, modelPatch, modelToValue } from "@/lib/models";
import { cn } from "@/lib/utils";

export function ModelSelect({
  agent,
  className,
  disabled,
}: {
  agent: Pick<Agent, "id" | "name" | "organization_id" | "model">;
  className?: string;
  disabled?: boolean;
}) {
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: (value: string) =>
      api<Agent>(`/organizations/${agent.organization_id}/agents/${agent.id}`, { method: "PATCH", body: modelPatch(value) }),
    onSuccess: (updated) => {
      // 응답으로 캐시를 바로 갱신한다(권한 저장이 이어져도 최신 값 기준이 되게).
      queryClient.setQueryData<Agent>(["agent", updated.id], (old) => (old ? updated : old));
      queryClient.setQueriesData<Organization>({ queryKey: ["organization"] }, (org) =>
        org?.agents?.some((a) => a.id === updated.id) ? { ...org, agents: org.agents.map((a) => (a.id === updated.id ? updated : a)) } : org,
      );
      toast.success(`${agent.name}: 모델을 ${modelLabel(updated.model)}(으)로 저장했습니다. 다음 실행부터 적용됩니다.`);
    },
    onError: (e) => toast.error(`${agent.name}: 모델을 저장하지 못했습니다. ${e.message}`),
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["organization"] }),
        queryClient.invalidateQueries({ queryKey: ["agent"] }),
      ]),
  });
  return (
    <Select
      aria-label={`${agent.name} 모델`}
      aria-busy={save.isPending || undefined}
      title="다음 실행부터 적용됩니다"
      className={cn("h-7 w-32 text-xs", className)}
      value={modelToValue(agent.model)}
      disabled={disabled || save.isPending}
      onChange={(e) => {
        if (e.target.value !== modelToValue(agent.model)) save.mutate(e.target.value);
      }}
    >
      {modelOptions(agent.model).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </Select>
  );
}
