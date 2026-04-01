import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
    pathname: "/",
  }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

// Mock next/link
vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: any) => {
    return children;
  },
}));

// Mock localStorage
const store: Record<string, string> = {};
vi.stubGlobal("localStorage", {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => { store[key] = value; },
  removeItem: (key: string) => { delete store[key]; },
  clear: () => { Object.keys(store).forEach((k) => delete store[k]); },
  get length() { return Object.keys(store).length; },
  key: (i: number) => Object.keys(store)[i] ?? null,
});

// Mock window.location
const locationMock = {
  href: "http://localhost:3000",
  replace: vi.fn(),
  assign: vi.fn(),
  reload: vi.fn(),
  pathname: "/",
  search: "",
  hash: "",
  origin: "http://localhost:3000",
  host: "localhost:3000",
  hostname: "localhost",
  port: "3000",
  protocol: "http:",
};
vi.stubGlobal("location", locationMock);
