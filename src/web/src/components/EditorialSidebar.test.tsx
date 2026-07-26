import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EditorialSidebar } from "./EditorialSidebar";

describe("EditorialSidebar", () => {
  it("在常见笔记本宽度显示双栏导航，并只在窄屏显示移动入口", () => {
    const { container } = render(
      <EditorialSidebar
        units={[
          {
            id: "unit-1",
            journal_id: "journal-1",
            journal_name: "交大法学",
            code: "editorial",
            name: "交大法学编辑部",
            policy_key: "jiaodafaxue",
            policy_version: "1.0",
            rollout_state: "shadow",
          },
        ]}
        unitId="unit-1"
        onUnitChange={vi.fn()}
        activeView="dashboard"
        onViewChange={vi.fn()}
        collapsed={false}
        onCollapsedChange={vi.fn()}
        mobileOpen={false}
        onMobileOpenChange={vi.fn()}
        pendingCount={0}
        unreadCount={0}
      />
    );

    const desktopSidebar = container.querySelector("aside");
    expect(desktopSidebar).toHaveClass("md:block");
    expect(desktopSidebar).not.toHaveClass("lg:block");
    expect(screen.getByRole("button", { name: "打开编辑导航" })).toHaveClass(
      "md:hidden"
    );
  });
});
