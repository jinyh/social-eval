import { SelectHTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/utils";

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-500/10 disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
);
Select.displayName = "Select";
