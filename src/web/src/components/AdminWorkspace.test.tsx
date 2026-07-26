import { describe, expect, it } from "vitest";

import { sha256File } from "./AdminWorkspace";

describe("sha256File", () => {
  it("在浏览器本地计算样本清单摘要", async () => {
    const bytes = new TextEncoder().encode("abc");
    const file = {
      arrayBuffer: async () => bytes.buffer,
    } as File;

    await expect(sha256File(file)).resolves.toBe(
      "ba7816bf8f01cfea414140de5dae2223" +
        "b00361a396177a9cb410ff61f20015ad"
    );
  });
});
