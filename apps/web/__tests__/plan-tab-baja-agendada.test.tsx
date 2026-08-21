/**
 * PlanTab — la baja agendada (B21) en la interfaz.
 *
 * Con B21 la suscripción queda en `active` después de la baja, así que sin
 * estos tests la UI mostraba "Activa / Próximo cobro" como si nada hubiera
 * pasado y seguía ofreciendo "Cancelar suscripción" a alguien que ya canceló.
 * El endpoint resume/ quedaba muerto: el que se arrepiente llama a soporte.
 *
 * Este archivo existe porque PlanTab.tsx no tenía NINGÚN test y es el cambio
 * de frontend más grande del lote que se va a producción.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn(), apiUpload: vi.fn() }));

const { apiFetch } = await import("@/lib/api");
const { default: PlanTab } = await import("@/components/settings/PlanTab");

const PLAN = {
  key: "pro", name: "Plan Pro", price_clp: 35000, trial_days: 14,
  max_products: 1000, max_stores: 3, max_users: 10,
  has_forecast: true, has_abc: true, has_reports: true, has_transfers: true,
};

function suscripcion(extra: Record<string, unknown> = {}) {
  return {
    status: "active", status_label: "Activa", is_access_allowed: true,
    plan: PLAN, trial_ends_at: null,
    current_period_end: "2026-09-15T00:00:00Z",
    days_remaining: 26, payment_retry_count: 0, next_retry_at: null,
    recent_invoices: [], has_card: true, card_brand: "visa", card_last4: "4242",
    cancel_at_period_end: false,
    ...extra,
  };
}

/** Resuelve la carga inicial: GET suscripción + GET planes. */
function montar(sub: Record<string, unknown>) {
  const flash = vi.fn();
  (apiFetch as any).mockImplementation((url: string) => {
    if (url === "/billing/subscription/") return Promise.resolve(sub);
    if (url === "/billing/plans/") return Promise.resolve([PLAN]);
    return Promise.resolve({});
  });
  render(<PlanTab mob={false} flash={flash} />);
  return flash;
}

beforeEach(() => vi.clearAllMocks());

describe("PlanTab — baja agendada (B21)", () => {
  it("con la baja agendada avisa hasta cuándo sigue el acceso", async () => {
    montar(suscripcion({ cancel_at_period_end: true }));

    expect(await screen.findByText(/suscripción dada de baja/i)).toBeTruthy();
    expect(screen.getByText(/no se hará un nuevo cobro/i)).toBeTruthy();
  });

  it("ofrece reanudar en vez de volver a cancelar", async () => {
    montar(suscripcion({ cancel_at_period_end: true }));

    expect(await screen.findByRole("button", { name: /reanudar suscripción/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^cancelar suscripción$/i })).toBeNull();
  });

  it("una suscripción normal SÍ deja cancelar y no muestra el aviso", async () => {
    montar(suscripcion());

    expect(await screen.findByRole("button", { name: /cancelar suscripción/i })).toBeTruthy();
    expect(screen.queryByText(/suscripción dada de baja/i)).toBeNull();
  });

  it("'Próximo cobro' pasa a 'Acceso hasta' cuando ya no habrá cobro", async () => {
    montar(suscripcion({ cancel_at_period_end: true }));

    expect(await screen.findByText(/acceso hasta/i)).toBeTruthy();
    expect(screen.queryByText(/próximo cobro/i)).toBeNull();
  });

  it("reanudar llama al endpoint y recarga el estado", async () => {
    const user = userEvent.setup();
    montar(suscripcion({ cancel_at_period_end: true }));

    await user.click(await screen.findByRole("button", { name: /reanudar suscripción/i }));

    await waitFor(() => {
      const llamadas = (apiFetch as any).mock.calls.map((c: any[]) => c[0]);
      expect(llamadas).toContain("/billing/subscription/resume/");
    });
  });

  it("el mensaje al cancelar sale del backend, no está escrito en el front", async () => {
    // Si no queda período pagado por delante el acceso termina AHORA, y
    // prometer lo contrario sería la misma mentira que arreglamos.
    const user = userEvent.setup();
    const flash = vi.fn();
    (apiFetch as any).mockImplementation((url: string) => {
      if (url === "/billing/subscription/") return Promise.resolve(suscripcion());
      if (url === "/billing/plans/") return Promise.resolve([PLAN]);
      if (url === "/billing/subscription/cancel/")
        return Promise.resolve({ ok: true, message: "El acceso finaliza ahora.", cancel_at_period_end: false });
      return Promise.resolve({});
    });
    render(<PlanTab mob={false} flash={flash} />);

    await user.click(await screen.findByRole("button", { name: /cancelar suscripción/i }));
    await user.click(await screen.findByRole("button", { name: /sí, cancelar/i }));

    await waitFor(() => {
      expect(flash).toHaveBeenCalledWith("ok", "El acceso finaliza ahora.");
    });
  });
});
