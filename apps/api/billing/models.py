"""
billing/models.py
=================
Sistema completo de suscripciones para Pulstock.

Modelos:
  Plan              → Define los planes disponibles (Inicio, Crecimiento, Pro)
  Subscription      → La suscripción activa de cada Tenant
  Invoice           → Registro de cada cobro (exitoso o fallido)
  PaymentAttempt    → Intentos individuales de cobro (para reintentos)
"""

import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta


# ─────────────────────────────────────────────
# PLAN
# ─────────────────────────────────────────────
class Plan(models.Model):
    class PlanKey(models.TextChoices):
        INICIO      = "inicio",      "Plan Inicio"
        CRECIMIENTO = "crecimiento", "Plan Crecimiento"
        PRO         = "pro",         "Plan Pro"

    key         = models.CharField(max_length=20, choices=PlanKey.choices, unique=True)
    name        = models.CharField(max_length=80)
    price_clp   = models.IntegerField(default=0, help_text="Precio mensual en CLP")
    trial_days  = models.IntegerField(default=14, help_text="Días de prueba gratis")
    is_active   = models.BooleanField(default=True)

    # Límites
    max_products  = models.IntegerField(default=100,  help_text="-1 = ilimitado")
    max_stores    = models.IntegerField(default=1,    help_text="-1 = ilimitado")
    max_users     = models.IntegerField(default=1,    help_text="-1 = ilimitado")
    max_registers = models.IntegerField(default=1,    help_text="Max cajas. -1 = ilimitado")

    # Features (flags)
    has_forecast  = models.BooleanField(default=False)
    has_abc       = models.BooleanField(default=False)
    has_reports   = models.BooleanField(default=False, help_text="Reportes avanzados (>3)")
    has_transfers = models.BooleanField(default=False, help_text="Transferencias entre locales")

    class Meta:
        ordering = ["price_clp"]

    def __str__(self):
        return f"{self.name} (${self.price_clp:,} CLP/mes)"


# ─────────────────────────────────────────────
# SUBSCRIPTION
# ─────────────────────────────────────────────
class Subscription(models.Model):
    class Status(models.TextChoices):
        TRIALING   = "trialing",   "En período de prueba"
        ACTIVE     = "active",     "Activa"
        PAST_DUE   = "past_due",   "Pago pendiente"
        SUSPENDED  = "suspended",  "Suspendida"
        CANCELLED  = "cancelled",  "Cancelada"

    tenant      = models.OneToOneField(
        "core.Tenant", on_delete=models.PROTECT, related_name="subscription"
    )
    plan        = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status      = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIALING)

    # Fechas clave
    trial_ends_at    = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end   = models.DateTimeField(null=True, blank=True)
    cancelled_at     = models.DateTimeField(null=True, blank=True)
    suspended_at     = models.DateTimeField(null=True, blank=True)

    # Flow customer (para cobro automático con tarjeta)
    flow_customer_id    = models.CharField(max_length=60, blank=True, default="",
                                           help_text="ID del cliente en Flow (cus_xxx)")
    card_brand          = models.CharField(max_length=20, blank=True, default="",
                                           help_text="Marca tarjeta registrada (Visa, Mastercard)")
    card_last4          = models.CharField(max_length=4, blank=True, default="",
                                           help_text="Últimos 4 dígitos tarjeta")

    # Reintentos de cobro
    payment_retry_count = models.IntegerField(default=0)
    next_retry_at       = models.DateTimeField(null=True, blank=True)

    # Notificaciones enviadas (para no duplicar)
    notified_7_days  = models.BooleanField(default=False)
    notified_3_days  = models.BooleanField(default=False)
    notified_1_day   = models.BooleanField(default=False)
    notified_past_due = models.BooleanField(default=False)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["current_period_end"]),
            models.Index(fields=["next_retry_at"]),
            models.Index(fields=["status", "current_period_end"]),
            models.Index(fields=["status", "next_retry_at"]),
        ]

    def __str__(self):
        return f"{self.tenant.name} → {self.plan.name} [{self.status}]"

    # ── Helpers ──────────────────────────────
    @property
    def is_access_allowed(self):
        """¿Puede el tenant usar el sistema ahora mismo?

        Bloquea trials vencidos aunque Celery no haya corrido expire_trials.
        Guarda la app de dar acceso infinito si el cron no corre.

        Lifetime/owner tenants (configurados en settings.BILLING_LIFETIME_SLUGS)
        siempre tienen acceso, sin importar el status.
        """
        # Lifetime tenants (dueño de la app, cuentas internas, etc.)
        if self.tenant_id:
            from django.conf import settings as dj_settings
            lifetime_slugs = getattr(dj_settings, "BILLING_LIFETIME_SLUGS", [])
            if lifetime_slugs and self.tenant.slug in lifetime_slugs:
                return True

        if self.status == self.Status.TRIALING:
            # Trial: verificar que no haya vencido
            if self.trial_ends_at and timezone.now() > self.trial_ends_at:
                return False
            return True
        return self.status in (
            self.Status.ACTIVE,
            self.Status.PAST_DUE,   # gracia de 3 días antes de suspender
        )

    @property
    def days_until_renewal(self):
        if not self.current_period_end:
            return None
        delta = self.current_period_end - timezone.now()
        return max(0, delta.days)

    @property
    def days_until_trial_end(self):
        if not self.trial_ends_at:
            return None
        delta = self.trial_ends_at - timezone.now()
        return max(0, delta.days)

    @property
    def is_trial(self):
        return self.status == self.Status.TRIALING

    @property
    def is_free_plan(self):
        return self.plan.price_clp == 0

    def reset_notification_flags(self):
        """Resetea flags al iniciar nuevo período."""
        self.notified_7_days = False
        self.notified_3_days = False
        self.notified_1_day  = False
        self.notified_past_due = False


# ─────────────────────────────────────────────
# INVOICE
# ─────────────────────────────────────────────
class Invoice(models.Model):
    class Status(models.TextChoices):
        PENDING  = "pending",  "Pendiente"
        PAID     = "paid",     "Pagada"
        FAILED   = "failed",   "Fallida"
        VOIDED   = "voided",   "Anulada"

    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="invoices")
    status       = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    amount_clp   = models.IntegerField()
    period_start = models.DateField()
    period_end   = models.DateField()

    # Pasarela de pago
    gateway          = models.CharField(max_length=40, default="flow", help_text="flow | transbank | manual")
    gateway_order_id = models.CharField(max_length=120, blank=True, default="")
    gateway_tx_id    = models.CharField(max_length=120, blank=True, default="")
    payment_url      = models.URLField(blank=True, default="", help_text="URL de pago Flow/Transbank")

    paid_at    = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes  = [models.Index(fields=["subscription", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["gateway_order_id"],
                condition=~Q(gateway_order_id=""),
                name="unique_invoice_gateway_order_id_non_empty",
            )
        ]

    def __str__(self):
        return f"Invoice #{self.pk} — {self.subscription.tenant.name} — {self.status}"

    def mark_paid(self, tx_id=""):
        self.status   = self.Status.PAID
        self.paid_at  = timezone.now()
        if tx_id:
            self.gateway_tx_id = tx_id
        self.save(update_fields=["status", "paid_at", "gateway_tx_id"])


# ─────────────────────────────────────────────
# PAYMENT ATTEMPT  (log de intentos)
# ─────────────────────────────────────────────
class PaymentAttempt(models.Model):
    class Result(models.TextChoices):
        SUCCESS = "success", "Exitoso"
        FAILED  = "failed",  "Fallido"
        PENDING = "pending", "Pendiente"

    invoice    = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="attempts")
    result     = models.CharField(max_length=10, choices=Result.choices, default=Result.PENDING)
    gateway    = models.CharField(max_length=40, default="flow")
    error_msg  = models.TextField(blank=True, default="")
    raw        = models.JSONField(default=dict, help_text="Respuesta raw de la pasarela")
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-attempted_at"]

    def __str__(self):
        return f"Attempt #{self.pk} → {self.result} ({self.attempted_at:%Y-%m-%d %H:%M})"


# ─────────────────────────────────────────────
# CHECKOUT SESSION (pago pre-registro)
# ─────────────────────────────────────────────
class CheckoutSession(models.Model):
    STATUS_PENDING   = "pending"
    STATUS_PAID      = "paid"
    STATUS_COMPLETED = "completed"
    STATUS_EXPIRED   = "expired"
    STATUS_CHOICES = [
        (STATUS_PENDING,   "Esperando pago"),
        (STATUS_PAID,      "Pagado"),
        (STATUS_COMPLETED, "Cuenta creada"),
        (STATUS_EXPIRED,   "Expirado"),
    ]

    token            = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    email            = models.EmailField()
    plan             = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="checkout_sessions")
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    amount_clp       = models.IntegerField(help_text="Monto cobrado")

    # Flow data
    payment_url      = models.URLField(blank=True, default="")
    flow_token       = models.CharField(max_length=200, blank=True, default="",
                                         help_text="Token de Flow para consultar estado")
    gateway_order_id = models.CharField(max_length=120, blank=True, default="")
    gateway_tx_id    = models.CharField(max_length=120, blank=True, default="")

    # Business/owner data collected upfront (so webhook can auto-create account)
    business_name        = models.CharField(max_length=200, blank=True, default="")
    business_type        = models.CharField(max_length=50, blank=True, default="")
    owner_name           = models.CharField(max_length=150, blank=True, default="")
    owner_username       = models.CharField(max_length=150, blank=True, default="")
    owner_password_hash  = models.CharField(max_length=200, blank=True, default="")

    # After completion, link to created tenant
    tenant           = models.ForeignKey(
        "core.Tenant", on_delete=models.SET_NULL, null=True, blank=True
    )

    expires_at       = models.DateTimeField()
    created_at       = models.DateTimeField(auto_now_add=True)
    completed_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["email", "status"]),
        ]

    def __str__(self):
        return f"Checkout {self.token} — {self.email} — {self.status}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at and self.status == self.STATUS_PENDING