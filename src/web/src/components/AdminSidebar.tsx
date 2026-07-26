import {
  BookOpenCheck,
  ChevronLeft,
  ChevronRight,
  FlaskConical,
  Gauge,
  Menu,
  NotebookTabs,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";

import { Button } from "./ui/button";

export type AdminWorkspaceView =
  | "overview"
  | "users"
  | "units"
  | "policies"
  | "activation"
  | "models";

const items = [
  { id: "overview", label: "系统总览", icon: Gauge },
  { id: "users", label: "用户与权限", icon: Users },
  { id: "units", label: "期刊与编辑单元", icon: NotebookTabs },
  { id: "policies", label: "期刊策略", icon: BookOpenCheck },
  { id: "activation", label: "启用验证", icon: ShieldCheck },
  { id: "models", label: "模型升级验证", icon: FlaskConical },
] as const;

type Props = {
  activeView: AdminWorkspaceView;
  onViewChange: (view: AdminWorkspaceView) => void;
  collapsed: boolean;
  onCollapsedChange: (value: boolean) => void;
  mobileOpen: boolean;
  onMobileOpenChange: (value: boolean) => void;
};

function Content({
  activeView,
  onViewChange,
  collapsed,
  onCollapsedChange,
}: Omit<Props, "mobileOpen" | "onMobileOpenChange">) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-200 p-3">
        <div
          className={cn(
            "flex h-10 items-center rounded-xl bg-blue-600 font-semibold text-white",
            collapsed ? "w-10 justify-center" : "gap-2 px-3"
          )}
        >
          <ShieldCheck className="h-5 w-5 shrink-0" />
          {!collapsed ? <span>系统管理</span> : null}
        </div>
      </div>
      <nav className="flex-1 space-y-1 p-3" aria-label="管理员工作台导航">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              aria-current={activeView === item.id ? "page" : undefined}
              aria-label={item.label}
              title={collapsed ? item.label : undefined}
              className={cn(
                "flex w-full items-center rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                collapsed ? "justify-center" : "gap-3",
                activeView === item.id
                  ? "bg-blue-600 text-white"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"
              )}
              onClick={() => onViewChange(item.id)}
            >
              <Icon className="h-5 w-5 shrink-0" />
              {!collapsed ? <span>{item.label}</span> : null}
            </button>
          );
        })}
      </nav>
      <div className="border-t border-slate-200 p-3">
        <Button
          type="button"
          variant="outline"
          className={cn("w-full", collapsed ? "px-0" : "justify-start")}
          aria-label={collapsed ? "展开导航栏" : "收起导航栏"}
          onClick={() => onCollapsedChange(!collapsed)}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <>
              <ChevronLeft className="h-4 w-4" />
              收起导航栏
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

export function AdminSidebar(props: Props) {
  return (
    <>
      <aside
        className={cn(
          "sticky top-24 hidden h-[calc(100vh-7rem)] shrink-0 self-start overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm md:block",
          props.collapsed ? "w-[72px]" : "w-60"
        )}
      >
        <Content {...props} />
      </aside>
      <Button
        type="button"
        variant="outline"
        className="fixed bottom-5 right-5 z-30 rounded-full shadow-lg md:hidden"
        onClick={() => props.onMobileOpenChange(true)}
        aria-label="打开管理员导航"
      >
        <Menu className="h-5 w-5" />
      </Button>
      {props.mobileOpen ? (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-slate-950/30"
            aria-label="关闭管理员导航"
            onClick={() => props.onMobileOpenChange(false)}
          />
          <aside className="relative h-full w-[min(86vw,320px)] bg-white shadow-2xl">
            <button
              type="button"
              className="absolute right-3 top-3 z-10 rounded-lg p-2 text-slate-500 hover:bg-slate-100"
              onClick={() => props.onMobileOpenChange(false)}
              aria-label="关闭管理员导航"
            >
              <X className="h-5 w-5" />
            </button>
            <Content
              {...props}
              collapsed={false}
              onViewChange={(view) => {
                props.onViewChange(view);
                props.onMobileOpenChange(false);
              }}
            />
          </aside>
        </div>
      ) : null}
    </>
  );
}
