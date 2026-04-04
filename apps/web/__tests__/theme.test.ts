import { describe, it, expect } from "vitest";
import { C } from "@/lib/theme";

describe("Theme constants (C)", () => {
  it("has accent color defined", () => {
    expect(C.accent).toBe("#4F46E5");
  });

  it("has font families", () => {
    expect(C.font).toContain("DM Sans");
    expect(C.mono).toContain("JetBrains Mono");
  });

  it("has border radius values", () => {
    expect(C.r).toBeDefined();
    expect(C.rMd).toBeDefined();
    expect(C.rLg).toBeDefined();
  });

  it("has all color families", () => {
    // Each semantic color should have bg + bd variants
    for (const key of ["green", "red", "amber"]) {
      expect(C[key as keyof typeof C]).toBeDefined();
      expect(C[`${key}Bg` as keyof typeof C]).toBeDefined();
      expect(C[`${key}Bd` as keyof typeof C]).toBeDefined();
    }
  });

  it("has shadow values", () => {
    expect(C.sh).toBeDefined();
    expect(C.shMd).toBeDefined();
    expect(C.shLg).toBeDefined();
  });
});
