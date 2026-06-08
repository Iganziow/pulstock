import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { default: AccountTab } = await import("@/components/settings/AccountTab");

function renderTab(onSave = vi.fn().mockResolvedValue(undefined)) {
  const me = {
    id: 1, username: "mario@marbrava.cl", first_name: "Mario",
    last_name: "Muñoz", email: "m@m.cl", role: "owner",
  } as any;
  render(<AccountTab me={me} onSave={onSave} saving={false} mob={false} />);
  return onSave;
}

describe("AccountTab — Mi cuenta (cambiar contraseña)", () => {
  it("el ojo muestra/oculta la nueva contraseña", async () => {
    const user = userEvent.setup();
    renderTab();
    const pw = screen.getByTestId("acc-pw-new") as HTMLInputElement;
    expect(pw.type).toBe("password");
    await user.click(screen.getByTestId("acc-pw-new-toggle"));
    expect(pw.type).toBe("text");
  });

  it("bloquea guardar y avisa si las contraseñas NO coinciden", async () => {
    const user = userEvent.setup();
    const onSave = renderTab();
    await user.type(screen.getByTestId("acc-pw-new"), "marbrava745");
    await user.type(screen.getByTestId("acc-pw-conf"), "marbrava999");
    await user.click(screen.getByRole("button", { name: /guardar cambios/i }));
    expect(screen.getByText(/no coinciden/i)).toBeTruthy();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("guarda con la contraseña cuando coinciden", async () => {
    const user = userEvent.setup();
    const onSave = renderTab();
    await user.type(screen.getByTestId("acc-pw-new"), "marbrava745");
    await user.type(screen.getByTestId("acc-pw-conf"), "marbrava745");
    await user.click(screen.getByRole("button", { name: /guardar cambios/i }));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0]).toMatchObject({ password: "marbrava745" });
  });

  it("guarda sin tocar la contraseña si los campos quedan vacíos", async () => {
    const user = userEvent.setup();
    const onSave = renderTab();
    await user.click(screen.getByRole("button", { name: /guardar cambios/i }));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0]).not.toHaveProperty("password");
  });
});
