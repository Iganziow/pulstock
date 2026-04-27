/**
 * Tests para el splitter de líneas por estación de impresión.
 *
 * `splitLinesByStation` agrupa las líneas de una comanda en sub-grupos
 * por `print_station_id`. Cada sub-grupo se imprime después como un
 * ticket independiente en su impresora correspondiente (cocina, bar,
 * despacho, etc.).
 *
 * Casos cubiertos:
 *   - Lista vacía → array vacío
 *   - Todas las líneas misma estación → 1 grupo
 *   - Múltiples estaciones → múltiples grupos
 *   - Líneas sin estación (null) → grupo "stationId: null"
 *   - Mezcla null + estaciones → 2+ grupos
 *   - Orden estable: stationIds numéricos ASC, null al final
 *   - Mantiene orden original DENTRO de cada grupo
 */
import { describe, it, expect } from "vitest";
import { splitLinesByStation, type CommandLine } from "@/lib/printer";

function L(name: string, qty = 1, station: number | null = null): CommandLine {
  return { product_name: name, qty, line_total: qty * 1000, print_station_id: station };
}

describe("splitLinesByStation", () => {
  it("returns empty array for empty input", () => {
    expect(splitLinesByStation([])).toEqual([]);
  });

  it("groups lines with same station into one group", () => {
    const lines = [L("Café", 1, 5), L("Té", 2, 5), L("Galleta", 3, 5)];
    const result = splitLinesByStation(lines);
    expect(result.length).toBe(1);
    expect(result[0].stationId).toBe(5);
    expect(result[0].lines.map(l => l.product_name)).toEqual(["Café", "Té", "Galleta"]);
  });

  it("splits multiple stations into multiple groups", () => {
    const lines = [
      L("Hamburguesa", 1, 1),    // cocina
      L("Cerveza", 1, 2),        // bar
      L("Papas", 1, 1),          // cocina
      L("Cola", 1, 2),           // bar
    ];
    const result = splitLinesByStation(lines);
    expect(result.length).toBe(2);
    const cocina = result.find(g => g.stationId === 1);
    const bar = result.find(g => g.stationId === 2);
    expect(cocina?.lines.map(l => l.product_name)).toEqual(["Hamburguesa", "Papas"]);
    expect(bar?.lines.map(l => l.product_name)).toEqual(["Cerveza", "Cola"]);
  });

  it("groups lines without station into a null-keyed group", () => {
    const lines = [L("X"), L("Y")];
    const result = splitLinesByStation(lines);
    expect(result.length).toBe(1);
    expect(result[0].stationId).toBe(null);
    expect(result[0].lines.length).toBe(2);
  });

  it("handles mix of null and station ids", () => {
    const lines = [
      L("Sin estación", 1, null),
      L("Cocina", 1, 1),
      L("Bar", 1, 2),
    ];
    const result = splitLinesByStation(lines);
    expect(result.length).toBe(3);
    // Orden estable: numéricos ASC, null al final
    expect(result[0].stationId).toBe(1);
    expect(result[1].stationId).toBe(2);
    expect(result[2].stationId).toBe(null);
  });

  it("orders groups: numeric station IDs ascending, null at end", () => {
    const lines = [
      L("A", 1, 10),
      L("B", 1, 1),
      L("C", 1, null),
      L("D", 1, 5),
    ];
    const result = splitLinesByStation(lines);
    expect(result.map(g => g.stationId)).toEqual([1, 5, 10, null]);
  });

  it("preserves original line order within each group", () => {
    const lines = [
      L("Primero cocina", 1, 1),
      L("Segundo bar", 1, 2),
      L("Tercero cocina", 1, 1),
      L("Cuarto bar", 1, 2),
      L("Quinto cocina", 1, 1),
    ];
    const result = splitLinesByStation(lines);
    const cocina = result.find(g => g.stationId === 1);
    expect(cocina?.lines.map(l => l.product_name)).toEqual([
      "Primero cocina",
      "Tercero cocina",
      "Quinto cocina",
    ]);
  });

  it("treats undefined station_id as null", () => {
    const lines: CommandLine[] = [
      { product_name: "Sin definir", qty: 1, line_total: 100 }, // sin print_station_id
      { product_name: "Con null", qty: 1, line_total: 100, print_station_id: null },
    ];
    const result = splitLinesByStation(lines);
    expect(result.length).toBe(1); // ambos al null group
    expect(result[0].stationId).toBe(null);
    expect(result[0].lines.length).toBe(2);
  });

  it("handles single line correctly", () => {
    const result = splitLinesByStation([L("Solo", 1, 7)]);
    expect(result).toEqual([
      { stationId: 7, lines: [expect.objectContaining({ product_name: "Solo" })] },
    ]);
  });

  it("does not mutate input array", () => {
    const lines = [L("A", 1, 1), L("B", 1, 2)];
    const original = lines.map(l => ({ ...l }));
    splitLinesByStation(lines);
    expect(lines).toEqual(original);
  });
});
