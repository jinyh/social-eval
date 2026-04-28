import { HTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium", {
  variants: {
    variant: {
      default: "border-blue-200 bg-blue-50 text-blue-700",
      neutral: "border-slate-200 bg-slate-50 text-slate-600",
      success: "border-emerald-200 bg-emerald-50 text-emerald-700",
      warning: "border-amber-200 bg-amber-50 text-amber-700",
      danger: "border-red-200 bg-red-50 text-red-700",
      violet: "border-violet-200 bg-violet-50 text-violet-700",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>;

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
