import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn(), apiUpload: vi.fn() }));

const { apiFetch } = await import("@/lib/api");
const { default: PermissionsTab } = await import("@/components/settings/PermissionsTab");

const PERM_META = [
  { key: "pos", label: "Punto de venta", group: "Ventas" },
  { key: "caja", label: "Caja / arqueos", group: "Ventas" },
];

function payload(usersByRole: Record<string, { id: number; name: string }[]>) {
  return {
    permission_meta: PERM_META,
    editable_roles: ["manager", "cashier", "inventory"],
    roles: [
      { role: "manager", role_label: "Administrador", permissions: { pos: true, caja: true } },
      { role: "cashier", role_label: "Caja/Garzón", permissions: { pos: true, caja: true } },
      { role: "inventory", role_label: "Inventario", permissions: { pos: false, caja: true } },
    ],
    users_by_role: usersByRole,
  };
}

const BASE = {
  owner: [{ id: 1, name: "Mario Muñoz" }, { id: 9, name: "Socio Dos" }],
  manager: [{ id: 2, name: "Nadia" }],
  cashier: [{ id: 3, name: "Anais" }],
  inventory: [],
};

function setup(props: any = {}) {
  const flash = vi.fn();
  const onUsersChanged = vi.fn();
  render(<PermissionsTab flash={flash} meId={1} onUsersChanged={onUsersChanged} {...props} />);
  return { flash, onUsersChanged };
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
  vi.mocked(apiFetch).mockResolvedValue(payload(structuredClone(BASE)) as any);
});

describe("PermissionsTab — personas en cada rol", () => {
  it("muestra a cada persona en la tarjeta de su rol", async () => {
    setup();
    await waitFor(() => expect(screen.getByText("Personas en cada rol")).toBeTruthy());
    expect(screen.getByText(/Mario Muñoz/)).toBeTruthy();
    expect(screen.getByText("Nadia")).toBeTruthy();
    expect(screen.getByText("Anais")).toBeTruthy();
    // El rol sin gente lo dice explícitamente, no queda en blanco
    expect(screen.getByText("— Nadie en este rol —")).toBeTruthy();
  });

  it("cambiar el rol de una persona llama al PATCH correcto y refresca", async () => {
    const user = userEvent.setup();
    const { flash, onUsersChanged } = setup();
    await waitFor(() => expect(screen.getByTestId("role-select-2")).toBeTruthy());

    await user.selectOptions(screen.getByTestId("role-select-2"), "inventory");

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith("/core/users/2/", {
        method: "PATCH", body: JSON.stringify({ role: "inventory" }),
      });
    });
    // Vuelve a leer la lista para reflejar el cambio
    await waitFor(() => expect(onUsersChanged).toHaveBeenCalled());
    expect(flash).toHaveBeenCalledWith("ok", "Nadia ahora es Inventario");
  });

  it("el dueño que está mirando NO puede cambiarse el rol a sí mismo", async () => {
    setup({ meId: 1 });
    await waitFor(() => expect(screen.getByText(/Mario Muñoz/)).toBeTruthy());
    // Candado en vez de selector, y se marca como "(tú)"
    expect(screen.getByTestId("lock-1")).toBeTruthy();
    expect(screen.queryByTestId("role-select-1")).toBeNull();
    expect(screen.getByText("Mario Muñoz (tú)")).toBeTruthy();
    // El otro dueño sí se puede mover
    expect(screen.getByTestId("role-select-9")).toBeTruthy();
  });

  it("no deja mover al ÚNICO dueño (dejaría el negocio sin dueño)", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      payload({ ...structuredClone(BASE), owner: [{ id: 7, name: "Dueño Solo" }] }) as any,
    );
    setup({ meId: null });
    await waitFor(() => expect(screen.getByText("Dueño Solo")).toBeTruthy());
    expect(screen.getByTestId("lock-7")).toBeTruthy();
    expect(screen.queryByTestId("role-select-7")).toBeNull();
  });

  it("'Agregar persona' ofrece SOLO a gente de otros roles, con su rol actual", async () => {
    const user = userEvent.setup();
    setup();
    await waitFor(() => expect(screen.getByTestId("add-to-inventory")).toBeTruthy());

    await user.click(screen.getByTestId("add-to-inventory"));
    const picker = screen.getByTestId("add-picker-inventory") as HTMLSelectElement;
    const opciones = [...picker.options].map(o => o.text);

    expect(opciones).toContain("Nadia · Administrador");
    expect(opciones).toContain("Anais · Caja/Garzón");
    expect(opciones).toContain("Socio Dos · Dueño/Gerente");
    // Yo mismo nunca soy candidato (el backend lo rechazaría)
    expect(opciones.some(o => o.includes("Mario Muñoz"))).toBe(false);
  });

  it("elegir a alguien en 'Agregar persona' lo mueve a ese rol", async () => {
    const user = userEvent.setup();
    const { flash } = setup();
    await waitFor(() => expect(screen.getByTestId("add-to-inventory")).toBeTruthy());

    await user.click(screen.getByTestId("add-to-inventory"));
    await user.selectOptions(screen.getByTestId("add-picker-inventory"), "3");

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith("/core/users/3/", {
        method: "PATCH", body: JSON.stringify({ role: "inventory" }),
      });
    });
    expect(flash).toHaveBeenCalledWith("ok", "Anais ahora es Inventario");
  });

  it("un error del backend se muestra tal cual (no un mensaje genérico)", async () => {
    const user = userEvent.setup();
    const { flash } = setup();
    await waitFor(() => expect(screen.getByTestId("role-select-9")).toBeTruthy());

    vi.mocked(apiFetch).mockRejectedValueOnce(
      Object.assign(new Error("400"), { data: { detail: "No se puede quitar el último dueño." } }),
    );
    await user.selectOptions(screen.getByTestId("role-select-9"), "manager");

    await waitFor(() =>
      expect(flash).toHaveBeenCalledWith("err", "No se puede quitar el último dueño."));
  });

  it("mover a alguien NO borra los permisos que todavía no se guardaron", async () => {
    const user = userEvent.setup();
    setup();
    await waitFor(() => expect(screen.getByTestId("role-select-2")).toBeTruthy());

    // Apago "Punto de venta" para Administrador (sin guardar todavía)
    const fila = screen.getByText("Punto de venta").closest("tr")!;
    const celdaManager = fila.querySelectorAll("td")[1].firstElementChild as HTMLElement;
    expect(celdaManager.getAttribute("title")).toBe("Activado");
    await user.click(celdaManager);
    expect(
      (screen.getByText("Punto de venta").closest("tr")!.querySelectorAll("td")[1]
        .firstElementChild as HTMLElement).getAttribute("title"),
    ).toBe("Desactivado");

    // Muevo a alguien de rol: recarga la lista de gente, NO la matriz
    await user.selectOptions(screen.getByTestId("role-select-2"), "inventory");
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith("/core/users/2/", expect.anything()));

    // El toggle sin guardar sigue apagado
    await waitFor(() => {
      const celda = screen.getByText("Punto de venta").closest("tr")!
        .querySelectorAll("td")[1].firstElementChild as HTMLElement;
      expect(celda.getAttribute("title")).toBe("Desactivado");
    });
  });
});
