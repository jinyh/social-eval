import {
  Bell,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  FilePlus2,
  LayoutDashboard,
  ListFilter,
  Menu,
  X,
} from "lucide-react";

import type { EditorialUnit } from "@/lib/types";
import { cn } from "@/lib/utils";

import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Select } from "./ui/select";

export type EditorWorkspaceView =
  | "dashboard"
  | "submissions"
  | "new"
  | "pending"
  | "notifications";

const navigationItems = [
  { id: "dashboard", label: "工作台", icon: LayoutDashboard },
  { id: "submissions", label: "投稿管理", icon: ListFilter },
  { id: "new", label: "新建投稿", icon: FilePlus2 },
  { id: "pending", label: "待处理", icon: ClipboardCheck },
  { id: "notifications", label: "通知", icon: Bell },
] as const;

type EditorialSidebarProps = {
  units: EditorialUnit[];
  unitId: string;
  onUnitChange: (unitId: string) => void;
  activeView: EditorWorkspaceView;
  onViewChange: (view: EditorWorkspaceView) => void;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
  pendingCount: number;
  unreadCount: number;
};

function SidebarContent({
  units,
  unitId,
  onUnitChange,
  activeView,
  onViewChange,
  collapsed,
  onCollapsedChange,
  pendingCount,
  unreadCount,
}: Omit<EditorialSidebarProps, "mobileOpen" | "onMobileOpenChange">) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-200 p-3">
        {collapsed ? (
          <div
            className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 font-semibold text-white"
            title="编辑工作台"
          >
            编
          </div>
        ) : (
          <>
            <p className="text-xs font-medium tracking-wide text-slate-500">
              当前编辑单元
            </p>
            <Select
              className="mt-2"
              value={unitId}
              onChange={(event) => onUnitChange(event.target.value)}
              aria-label="当前编辑单元"
            >
              {units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </Select>
          </>
        )}
      </div>

      <nav className="flex-1 space-y-1 p-3" aria-label="编辑工作台导航">
        {navigationItems.map((item) => {
          const Icon = item.icon;
          const count =
            item.id === "pending"
              ? pendingCount
              : item.id === "notifications"
                ? unreadCount
                : 0;
          return (
            <button
              type="button"
              key={item.id}
              title={collapsed ? item.label : undefined}
              aria-label={item.label}
              aria-current={activeView === item.id ? "page" : undefined}
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
              {!collapsed ? (
                <>
                  <span className="flex-1 text-left">{item.label}</span>
                  {count > 0 ? (
                    <Badge
                      variant={activeView === item.id ? "neutral" : "warning"}
                    >
                      {count}
                    </Badge>
                  ) : null}
                </>
              ) : count > 0 ? (
                <span className="sr-only">{count} 项</span>
              ) : null}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-slate-200 p-3">
        <Button
          type="button"
          variant="outline"
          className={cn("w-full", collapsed ? "px-0" : "justify-start")}
          onClick={() => onCollapsedChange(!collapsed)}
          aria-label={collapsed ? "展开导航栏" : "收起导航栏"}
          title={collapsed ? "展开导航栏" : undefined}
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

export function EditorialSidebar(props: EditorialSidebarProps) {
  const { mobileOpen, onMobileOpenChange } = props;
  return (
    <>
      <aside
        className={cn(
          "sticky top-24 hidden h-[calc(100vh-7rem)] shrink-0 self-start overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm md:block",
          props.collapsed ? "w-[72px]" : "w-60"
        )}
      >
        <SidebarContent {...props} />
      </aside>

      <Button
        type="button"
        variant="outline"
        className="fixed bottom-5 right-5 z-30 rounded-full shadow-lg md:hidden"
        onClick={() => onMobileOpenChange(true)}
        aria-label="打开编辑导航"
      >
        <Menu className="h-5 w-5" />
      </Button>

      {mobileOpen ? (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-slate-950/30"
            aria-label="关闭编辑导航"
            onClick={() => onMobileOpenChange(false)}
          />
          <aside className="relative h-full w-[min(86vw,320px)] bg-white shadow-2xl">
            <button
              type="button"
              className="absolute right-3 top-3 z-10 rounded-lg p-2 text-slate-500 hover:bg-slate-100"
              onClick={() => onMobileOpenChange(false)}
              aria-label="关闭编辑导航"
            >
              <X className="h-5 w-5" />
            </button>
            <SidebarContent
              {...props}
              collapsed={false}
              onViewChange={(view) => {
                props.onViewChange(view);
                onMobileOpenChange(false);
              }}
            />
          </aside>
        </div>
      ) : null}
    </>
  );
}
