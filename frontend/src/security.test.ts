import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      return sourceFiles(path);
    }
    return /\.(ts|tsx)$/.test(entry) ? [path] : [];
  });
}

const FILES = sourceFiles(join(process.cwd(), "src"));

describe("前端安全邊界", () => {
  it("沒有任何地方使用 dangerouslySetInnerHTML 或 innerHTML", () => {
    const offenders = FILES.filter((path) => {
      if (path.endsWith("security.test.ts")) {
        return false;
      }
      const source = readFileSync(path, "utf8");
      return source.includes("dangerouslySetInnerHTML") || source.includes(".innerHTML =");
    });
    expect(offenders).toEqual([]);
  });

  it("沒有把資料寫進 localStorage、sessionStorage 或 cookie", () => {
    const offenders = FILES.filter((path) => {
      if (path.endsWith(".test.ts") || path.endsWith(".test.tsx")) {
        return false;
      }
      const source = readFileSync(path, "utf8");
      return (
        source.includes("localStorage.setItem") ||
        source.includes("sessionStorage.setItem") ||
        source.includes("document.cookie =")
      );
    });
    expect(offenders).toEqual([]);
  });
});
