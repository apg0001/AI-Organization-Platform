import { X } from "lucide-react";
import { Dialog as D, DropdownMenu as M, Popover as P, Tabs as T, Tooltip as TT } from "radix-ui";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

// ── Dialog ────────────────────────────────────────────────────────────────

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({
  title,
  description,
  children,
  className,
  wide,
  onCloseAutoFocus,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
  wide?: boolean;
  /** 닫힐 때 포커스를 돌려줄 곳을 직접 정할 때(연 요소가 사라진 경우 등). */
  onCloseAutoFocus?: (event: Event) => void;
}) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-[1px]" />
      <D.Content
        onCloseAutoFocus={onCloseAutoFocus}
        className={cn(
          "overlay-in fixed top-1/2 left-1/2 z-50 flex max-h-[88vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border border-border-strong bg-surface-1 shadow-overlay",
          wide ? "max-w-4xl" : "max-w-lg",
          className,
        )}
        style={{ overscrollBehavior: "contain" }}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="flex flex-col gap-1">
            <D.Title className="text-md font-semibold">{title}</D.Title>
            {description ? <D.Description className="text-sm text-muted">{description}</D.Description> : null}
          </div>
          <D.Close
            aria-label="닫기"
            className="-mr-1 rounded-md p-1 text-muted transition-colors hover:bg-surface-3 hover:text-fg"
          >
            <X className="size-4" />
          </D.Close>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </D.Content>
    </D.Portal>
  );
}

export function DialogFooter({ children }: { children: ReactNode }) {
  return <div className="mt-5 flex justify-end gap-2">{children}</div>;
}

// ── Dropdown ──────────────────────────────────────────────────────────────

export const Menu = M.Root;
export const MenuTrigger = M.Trigger;

export function MenuContent({ className, ...props }: ComponentProps<typeof M.Content>) {
  return (
    <M.Portal>
      <M.Content
        sideOffset={4}
        className={cn(
          "overlay-in z-50 min-w-44 rounded-md border border-border-strong bg-surface-2 p-1 shadow-overlay",
          className,
        )}
        {...props}
      />
    </M.Portal>
  );
}

export function MenuItem({ className, ...props }: ComponentProps<typeof M.Item>) {
  return (
    <M.Item
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-fg outline-none select-none data-[disabled]:opacity-45 data-[highlighted]:bg-surface-3 [&_svg]:size-4 [&_svg]:text-muted",
        className,
      )}
      {...props}
    />
  );
}

export function MenuLabel({ className, ...props }: ComponentProps<typeof M.Label>) {
  return <M.Label className={cn("px-2 py-1 text-2xs font-medium text-faint", className)} {...props} />;
}

export const MenuSeparator = () => <M.Separator className="my-1 h-px bg-border" />;

// ── Popover ───────────────────────────────────────────────────────────────

export const Popover = P.Root;
export const PopoverTrigger = P.Trigger;
export const PopoverClose = P.Close;

/** 이름 있는 대화형 팝오버. Esc·바깥 클릭으로 닫히고 포커스는 연 버튼으로 돌아간다(Radix 기본 동작). */
export function PopoverContent({ className, ...props }: ComponentProps<typeof P.Content>) {
  return (
    <P.Portal>
      <P.Content
        sideOffset={6}
        collisionPadding={8}
        className={cn(
          "overlay-in z-50 w-80 rounded-lg border border-border-strong bg-surface-2 p-3 shadow-overlay outline-none",
          className,
        )}
        {...props}
      />
    </P.Portal>
  );
}

// ── Tabs ──────────────────────────────────────────────────────────────────

export const Tabs = T.Root;
export const TabsContent = T.Content;

export function TabsList({ className, ...props }: ComponentProps<typeof T.List>) {
  return <T.List className={cn("flex gap-1 border-b border-border", className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof T.Trigger>) {
  return (
    <T.Trigger
      className={cn(
        "-mb-px cursor-pointer border-b-2 border-transparent px-2.5 py-2 text-sm text-muted transition-colors hover:text-fg data-[state=active]:border-primary-text data-[state=active]:text-fg",
        className,
      )}
      {...props}
    />
  );
}

// ── Tooltip ───────────────────────────────────────────────────────────────

export const TooltipProvider = ({ children }: { children: ReactNode }) => (
  // 첫 툴팁만 지연하고 이어지는 툴팁은 바로 보인다.
  <TT.Provider delayDuration={400} skipDelayDuration={300}>
    {children}
  </TT.Provider>
);

export function Tooltip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <TT.Root>
      <TT.Trigger asChild>{children}</TT.Trigger>
      <TT.Portal>
        <TT.Content
          sideOffset={6}
          className="overlay-in z-50 max-w-72 rounded-md border border-border-strong bg-surface-2 px-2 py-1 text-xs text-fg shadow-overlay"
        >
          {content}
        </TT.Content>
      </TT.Portal>
    </TT.Root>
  );
}
