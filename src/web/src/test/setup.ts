import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

vi.mock("echarts/core", () => ({
  use: vi.fn(),
  init: vi.fn(() => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  })),
}));

vi.mock("echarts/charts", () => ({ RadarChart: {} }));
vi.mock("echarts/components", () => ({ GridComponent: {}, TooltipComponent: {} }));
vi.mock("echarts/renderers", () => ({ SVGRenderer: {} }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllEnvs();
});

beforeEach(() => {
  window.history.pushState({}, "", "/");
  vi.stubGlobal(
    "ResizeObserver",
    class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => ({ items: [] }),
      text: async () => "",
    }))
  );
});
