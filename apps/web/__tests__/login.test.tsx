import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock fetch
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Import component after mocks
const { default: LoginPage } = await import("@/app/(auth)/login/page");

beforeEach(() => {
  mockFetch.mockReset();
  localStorage.clear();
  (window.location.replace as any).mockReset?.();
  (window.location.href as any) = "http://localhost:3000/login";
});

describe("LoginPage", () => {
  it("renders login form with usuario and contraseña fields", () => {
    render(<LoginPage />);
    expect(screen.getByPlaceholderText("Tu nombre de usuario")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("••••••••")).toBeInTheDocument();
    expect(screen.getByText("Ingresar")).toBeInTheDocument();
    expect(screen.getByText("Pulstock")).toBeInTheDocument();
  });

  it("disables submit button when fields are empty", () => {
    render(<LoginPage />);
    const btn = screen.getByText("Ingresar");
    expect(btn).toBeDisabled();
  });

  it("enables submit button when both fields have values", async () => {
    render(<LoginPage />);
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Tu nombre de usuario"), "test@test.cl");
    await user.type(screen.getByPlaceholderText("••••••••"), "password123");
    expect(screen.getByText("Ingresar")).toBeEnabled();
  });

  it("shows error on failed login", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Usuario o contraseña incorrectos" }),
    });

    render(<LoginPage />);
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Tu nombre de usuario"), "bad@user.cl");
    await user.type(screen.getByPlaceholderText("••••••••"), "wrongpass");
    await user.click(screen.getByText("Ingresar"));

    await waitFor(() => {
      expect(screen.getByText("Usuario o contraseña incorrectos")).toBeInTheDocument();
    });
  });

  it("does NOT auto-redirect when token exists in localStorage", () => {
    localStorage.setItem("access", "some-old-token");
    render(<LoginPage />);
    // Should still show the login form, not redirect
    expect(screen.getByPlaceholderText("Tu nombre de usuario")).toBeInTheDocument();
    expect(window.location.replace).not.toHaveBeenCalled();
  });

  it("toggles password visibility", async () => {
    render(<LoginPage />);
    const user = userEvent.setup();
    const pwInput = screen.getByPlaceholderText("••••••••");
    expect(pwInput).toHaveAttribute("type", "password");

    // Find and click the eye toggle button
    const toggleBtn = screen.getByLabelText("Mostrar contraseña");
    await user.click(toggleBtn);
    expect(pwInput).toHaveAttribute("type", "text");
  });
});
