/**
 * PaymentModal, "Por items": parte sin nada seleccionado.
 *
 * Mario (05/09/26): al cobrar por items aparecia todo marcado. Una mesa de
 * 20 productos obligaba a desmarcar 19 para cobrarle al primero, que solo
 * consumio uno. Ahora el cajero agrega de a uno lo que paga cada cliente.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn(), apiUpload: vi.fn() }));

const { PaymentModal } = await import("@/components/mesas/PaymentModal");

const LINEAS = [
  { id: 1, product_id: 11, product_name: "Chocolate Caliente", qty: "1", unit_price: "4000", line_total: "4000", is_paid: false },
  { id: 2, product_id: 12, product_name: "Espresso doble", qty: "1", unit_price: "2800", line_total: "2800", is_paid: false },
  { id: 3, product_id: 13, product_name: "Torta de murta", qty: "1", unit_price: "4980", line_total: "4980", is_paid: false },
] as any[];

function abrirPorItems() {
  const onConfirm = vi.fn();
  render(
    <PaymentModal total={11780} tableName="1" unpaidLines={LINEAS} loading={false}
      onConfirm={onConfirm} onClose={() => {}} />,
  );
  fireEvent.click(screen.getByText("Por items"));
  return onConfirm;
}

describe("PaymentModal, Por items", () => {
  it("parte con todos los items SIN marcar y el boton de cobrar deshabilitado", () => {
    abrirPorItems();
    const casillas = screen.getAllByRole("checkbox").filter(c => (c as HTMLInputElement).checked);
    expect(casillas).toHaveLength(0);
    const boton = screen.getByText(/Cobrar \$0/).closest("button")!;
    expect(boton.disabled).toBe(true);
  });

  it("al marcar un item, el total es solo ese item y se puede cobrar", () => {
    const onConfirm = abrirPorItems();
    const fila = screen.getByText("Espresso doble").closest("div")!;
    fireEvent.click(fila.querySelector("input[type=checkbox]")!);
    const boton = screen.getByText(/Cobrar \$2\.800/).closest("button")!;
    expect(boton.disabled).toBe(false);
    fireEvent.click(boton);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    const [, , modo, lineIds] = onConfirm.mock.calls[0];
    expect(modo).toBe("partial");
    expect(lineIds).toEqual([2]);
  });

  it("Cobrar todo sigue cobrando la mesa completa sin tocar la seleccion", () => {
    const onConfirm = vi.fn();
    render(
      <PaymentModal total={11780} tableName="1" unpaidLines={LINEAS} loading={false}
        onConfirm={onConfirm} onClose={() => {}} />,
    );
    const boton = screen.getByText(/Cobrar \$11\.780/).closest("button")!;
    expect(boton.disabled).toBe(false);
  });
});
