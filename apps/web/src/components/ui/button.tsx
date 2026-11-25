import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/**
 * 버튼 규칙(docs/COMPONENT_GUIDELINES.md):
 * - primary는 화면의 주 행동 하나에만. 나머지는 secondary/ghost.
 * - 누르면 살짝 눌린다(scale 0.98, 100ms). hover 색 전환은 120ms.
 * - 아이콘만 있는 버튼은 aria-label 필수(IconButton).
 */
export const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium select-none " +
    "transition-[background-color,color,border-color,transform] duration-[120ms] active:scale-[0.98] " +
    "disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-4 [&_svg]:shrink-0 cursor-pointer",
  {
    variants: {
      variant: {
        primary: "bg-primary text-white hover:bg-primary-hover",
        secondary: "border border-border-strong bg-surface-2 text-fg hover:bg-surface-3",
        ghost: "text-muted hover:bg-surface-3 hover:text-fg",
        danger: "bg-danger-solid text-white hover:brightness-110",
        warning: "bg-warning text-[#1a1306] hover:brightness-105",
      },
      size: {
        sm: "h-7 px-2.5 text-xs",
        md: "h-8 px-3 text-sm",
        lg: "h-9 px-4 text-base",
        icon: "size-8",
        "icon-sm": "size-7 [&_svg]:size-3.5",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps extends ComponentProps<"button">, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild, type, ...props }: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      type={asChild ? undefined : (type ?? "button")}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export function IconButton({
  label,
  size = "icon",
  variant = "ghost",
  ...props
}: Omit<ButtonProps, "aria-label"> & { label: string }) {
  return <Button aria-label={label} title={label} size={size} variant={variant} {...props} />;
}
