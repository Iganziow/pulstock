/**
 * printer.ts — la impresión automática nunca abre el selector de
 * dispositivos del navegador.
 *
 * Nadia (06/09/26): al cobrar una mesa saltaba "pulstock.cl quiere
 * conectarse / No se han podido encontrar dispositivos compatibles". Era el
 * picker de Web Bluetooth/USB abierto por la boleta automática, porque la
 * impresora guardada en ese PC no estaba disponible. El picker solo se abre
 * cuando la persona tocó "Imprimir".
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn(), apiUpload: vi.fn() }));

const printer = await import("@/lib/printer");

function impresoraPorDefecto(type: "bluetooth" | "usb") {
  const p = { id: "p1", name: "Térmica caja", type, paperWidth: 80 as const };
  printer.savePrinter(p as any);
  printer.setDefaultPrinter(p.id);
  return p;
}

function conBluetooth(requestDevice: any) {
  Object.defineProperty(navigator, "bluetooth", {
    configurable: true,
    value: { getDevices: vi.fn().mockResolvedValue([]), requestDevice },
  });
}

function conUSB(requestDevice: any) {
  Object.defineProperty(navigator, "usb", {
    configurable: true,
    value: { getDevices: vi.fn().mockResolvedValue([]), requestDevice },
  });
}

const bytes = new Uint8Array([27, 64]);

describe("impresión automática (silent)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(console, "log").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
    delete (navigator as any).bluetooth;
    delete (navigator as any).usb;
  });

  it("Bluetooth sin dispositivo autorizado: no abre el picker y explica qué hacer", async () => {
    impresoraPorDefecto("bluetooth");
    const requestDevice = vi.fn();
    conBluetooth(requestDevice);
    const r = await printer.printUniversal({ bytes, html: "<p/>", source: "pos", silent: true });
    expect(requestDevice).not.toHaveBeenCalled();
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/"Térmica caja" no está conectada por Bluetooth/);
    expect(r.error).toMatch(/toca Imprimir/);
  });

  it("USB sin dispositivo autorizado: tampoco abre el picker", async () => {
    impresoraPorDefecto("usb");
    const requestDevice = vi.fn();
    conUSB(requestDevice);
    const r = await printer.printUniversal({ bytes, html: "<p/>", source: "pos", silent: true });
    expect(requestDevice).not.toHaveBeenCalled();
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/no está conectada por USB/);
  });

  it("con gesto del usuario (sin silent) el picker sí se abre, como antes", async () => {
    impresoraPorDefecto("bluetooth");
    const cancel = Object.assign(new Error("User cancelled the requestDevice() chooser."), { name: "NotAllowedError" });
    const requestDevice = vi.fn().mockRejectedValue(cancel);
    conBluetooth(requestDevice);
    const r = await printer.printUniversal({ bytes, html: "<p/>", source: "pos" });
    expect(requestDevice).toHaveBeenCalledTimes(1);
    expect(r.ok).toBe(false);
    expect((r as any).cancelled).toBe(true);
  });
});
