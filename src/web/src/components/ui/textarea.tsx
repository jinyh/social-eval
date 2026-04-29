import { TextareaHTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/utils";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-24 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 outline-none transition-colors placeholder:text-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-500/10 disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
);
Textarea.displayName = "Textarea";
