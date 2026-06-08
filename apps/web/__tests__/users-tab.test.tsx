import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn(), apiUpload: vi.fn() }));

const { default: UsersTab } = await import("@/components/settings/UsersTab");

function setup() {
  const props = {
    users: [],
    me: { id: 1, username: "owner", role: "owner" },
    stores: [{ id: 1, name: "Local Único" }],
    onRefresh: vi.fn(),
    flash: vi.fn(),
  } as any;
  render(<UsersTab {...props} />);
}

const openForm = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole("button", { name: "+ Nuevo usuario" }));

describe("UsersTab — crear usuario (mejoras)", () => {
  it("muestra el hint '(usuario para entrar al sistema)'", async () => {
    const user = userEvent.setup();
    setup();
    await openForm(user);
    expect(screen.getByText("(usuario para entrar al sistema)")).toBeTruthy();
  });

  it("botón deshabilitado y aviso si las contraseñas NO coinciden", async () => {
    const user = userEvent.setup();
    setup();
    await openForm(user);
    await user.type(screen.getByTestId("nu-user"), "jperez");
    await user.type(screen.getByTestId("nu-pass"), "marbrava745");
    await user.type(screen.getByTestId("nu-pass2"), "marbrava999");
    expect(screen.getByTestId("pass-mismatch")).toBeTruthy();
    const crear = screen.getByRole("button", { name: /crear usuario/i }) as HTMLButtonElement;
    expect(crear.disabled).toBe(true);
  });

  it("habilita Crear cuando las contraseñas coinciden (y oculta el aviso)", async () => {
    const user = userEvent.setup();
    setup();
    await openForm(user);
    await user.type(screen.getByTestId("nu-user"), "jperez");
    await user.type(screen.getByTestId("nu-pass"), "marbrava745");
    await user.type(screen.getByTestId("nu-pass2"), "marbrava745");
    expect(screen.queryByTestId("pass-mismatch")).toBeNull();
    const crear = screen.getByRole("button", { name: /crear usuario/i }) as HTMLButtonElement;
    expect(crear.disabled).toBe(false);
  });

  it("el botón Ver/Ocultar alterna la visibilidad de ambas contraseñas", async () => {
    const user = userEvent.setup();
    setup();
    await openForm(user);
    const pass = screen.getByTestId("nu-pass") as HTMLInputElement;
    const conf = screen.getByTestId("nu-pass2") as HTMLInputElement;
    expect(pass.type).toBe("password");
    expect(conf.type).toBe("password");
    await user.click(screen.getByTestId("toggle-pass"));
    expect(pass.type).toBe("text");
    expect(conf.type).toBe("text");
    expect(screen.getByTestId("toggle-pass").textContent).toContain("Ocultar");
    await user.click(screen.getByTestId("toggle-pass"));
    expect(pass.type).toBe("password");
    expect(conf.type).toBe("password");
  });
});
