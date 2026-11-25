import { Switch as SwitchPrimitive } from "radix-ui";
import { type ComponentProps, type ReactNode, useId } from "react";

import { cn } from "@/lib/utils";

const field =
  "w-full min-w-0 rounded-md border border-border-strong bg-surface-2 px-2.5 text-sm text-fg placeholder:text-faint " +
  "transition-[border-color] duration-[120ms] hover:border-input-hover focus-visible:border-ring focus-visible:outline-none " +
  "disabled:opacity-50 aria-[invalid=true]:border-danger";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(field, "h-8", className)} autoComplete="off" {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(field, "min-h-20 py-2 leading-relaxed", className)} {...props} />;
}

/** 네이티브 select(키보드·접근성 기본 제공). 어두운 테마에서도 배경을 명시한다. */
export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <select className={cn(field, "h-8 cursor-pointer bg-surface-2 pr-7", className)} {...props}>
      {children}
    </select>
  );
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("text-xs font-medium text-muted", className)} {...props} />;
}

/** 라벨 + 컨트롤 + 도움말/오류. 컨트롤에 id를 넘겨 라벨과 연결한다. */
export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  children: (id: string) => ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children(id)}
      {error ? (
        <p className="text-xs text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-faint">{hint}</p>
      ) : null}
    </div>
  );
}

export function Switch({
  className,
  label,
  description,
  ...props
}: ComponentProps<typeof SwitchPrimitive.Root> & { label: string; description?: string }) {
  const id = useId();
  return (
    <div className={cn("flex items-start justify-between gap-4", className)}>
      <label htmlFor={id} className="flex cursor-pointer flex-col gap-0.5">
        <span className="text-sm text-fg">{label}</span>
        {description ? <span className="text-xs text-faint">{description}</span> : null}
      </label>
      <SwitchPrimitive.Root
        id={id}
        className="relative mt-0.5 inline-flex h-[18px] w-8 shrink-0 cursor-pointer items-center rounded-full border border-border-strong bg-surface-3 transition-colors duration-150 data-[state=checked]:border-primary data-[state=checked]:bg-primary disabled:opacity-50"
        {...props}
      >
        <SwitchPrimitive.Thumb className="block size-3 translate-x-[2px] rounded-full bg-fg transition-transform duration-150 ease-[var(--ease-out)] data-[state=checked]:translate-x-[15px]" />
      </SwitchPrimitive.Root>
    </div>
  );
}
