from django.db import models
from django.contrib.auth.models import AbstractUser


class Tenant(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ── Datos empresa (Chile) ──
    legal_name = models.CharField(max_length=200, blank=True, default="",
        help_text="Razón social")
    rut = models.CharField(max_length=15, blank=True, default="",
        help_text="RUT empresa (ej: 76.123.456-7)")
    giro = models.CharField(max_length=200, blank=True, default="",
        help_text="Giro comercial")
    address = models.CharField(max_length=300, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    comuna = models.CharField(max_length=100, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    website = models.URLField(blank=True, default="")

    # ── Branding ──
    logo_url = models.URLField(blank=True, default="",
        help_text="URL del logo de la empresa")
    primary_color = models.CharField(max_length=7, blank=True, default="#4F46E5",
        help_text="Color principal (hex)")

    # ── Configuración de boleta/recibo ──
    receipt_header = models.TextField(blank=True, default="",
        help_text="Texto adicional en el encabezado de boletas")
    receipt_footer = models.TextField(blank=True, default="",
        help_text="Texto al pie de boletas (ej: políticas de devolución)")
    receipt_show_logo = models.BooleanField(default=True)
    receipt_show_rut = models.BooleanField(default=True)

    # ── Tipo de negocio ──
    BUSINESS_TYPE_CHOICES = [
        ("retail",      "Minimarket / Retail"),
        ("restaurant",  "Restaurant / Cafetería"),
        ("hardware",    "Ferretería / Materiales"),
        ("wholesale",   "Distribuidora / Mayorista"),
        ("pharmacy",    "Farmacia / Droguería"),
        ("other",       "Otro"),
    ]
    business_type = models.CharField(
        max_length=20,
        choices=BUSINESS_TYPE_CHOICES,
        default="retail",
        help_text="Tipo de negocio — ajusta parámetros del modelo de forecast automáticamente",
    )

    # ── Configuración general ──
    currency = models.CharField(max_length=3, default="CLP")
    timezone = models.CharField(max_length=50, default="America/Santiago")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=19,
        help_text="IVA por defecto (%)")

    # Compatibilidad
    default_warehouse = models.ForeignKey(
        "core.Warehouse",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER     = "owner",     "Dueño/Gerente"
        MANAGER   = "manager",   "Administrador"
        CASHIER   = "cashier",   "Caja y/o Garzón"
        INVENTORY = "inventory", "Inventario"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
        help_text="Empresa/negocio del usuario",
    )

    active_store = models.ForeignKey(
        "stores.Store",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Local activo del usuario dentro del tenant",
    )

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.OWNER,
        help_text="Rol del usuario en el tenant",
    )

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_manager(self):
        return self.role in (self.Role.OWNER, self.Role.MANAGER)

    @property
    def is_cashier(self):
        return self.role == self.Role.CASHIER

    @property
    def is_inventory(self):
        return self.role == self.Role.INVENTORY


class Warehouse(models.Model):
    WAREHOUSE_TYPE_CHOICES = [
        ("sales_floor", "Sala de venta"),
        ("storage", "Bodega"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="warehouses")

    # ✅ AHORA OBLIGATORIO
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.PROTECT,
        related_name="warehouses",
    )

    name = models.CharField(max_length=120, default="Bodega Principal")
    warehouse_type = models.CharField(
        max_length=16,
        choices=WAREHOUSE_TYPE_CHOICES,
        default="storage",
        help_text="Tipo: sala de venta o bodega de almacenamiento",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("tenant", "store", "name")]
        indexes = [
            models.Index(fields=["tenant", "store", "name"]),
            models.Index(fields=["tenant", "store", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} (tenant={self.tenant_id}, store={self.store_id})"


class AlertPreference(models.Model):
    """Preferencias de notificación por usuario."""
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="alert_preferences",
        null=True,  # null for backfill of existing rows
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="alert_prefs",
    )
    stock_bajo = models.BooleanField(default=True)
    forecast_urgente = models.BooleanField(default=True)
    sugerencia_compra = models.BooleanField(default=True)
    merma_alta = models.BooleanField(default=False)
    sin_rotacion = models.BooleanField(default=False)
    resumen_diario = models.BooleanField(default=False)

    class Meta:
        db_table = "core_alertpreference"

    def __str__(self) -> str:
        return f"AlertPrefs(user={self.user_id})"


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════

class AuditEntry(models.Model):
    """Registro de auditoría para cambios de negocio relevantes."""
    ACTION_CHOICES = [
        ("price_change",    "Cambio de precio"),
        ("sale_void",       "Anulación de venta"),
        ("stock_adjust",    "Ajuste de stock"),
        ("product_create",  "Producto creado"),
        ("product_update",  "Producto actualizado"),
        ("product_delete",  "Producto desactivado"),
        ("purchase_post",   "Compra contabilizada"),
        ("purchase_void",   "Compra anulada"),
        ("transfer",        "Transferencia"),
        ("user_change",     "Cambio de usuario"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="audit_entries")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    entity_type = models.CharField(max_length=30)  # "product", "sale", "stockitem", etc.
    entity_id = models.IntegerField()
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "core_auditentry"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["tenant", "action"]),
            models.Index(fields=["tenant", "entity_type", "entity_id"]),
        ]

    def __str__(self):
        return f"[{self.action}] {self.entity_type}#{self.entity_id} by {self.user_id}"


def log_audit(request, action, entity_type, entity_id, detail=None):
    """Convenience helper to create an AuditEntry from a DRF request."""
    AuditEntry.objects.create(
        tenant_id=request.user.tenant_id,
        user=request.user,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail or {},
        ip_address=request.META.get("REMOTE_ADDR"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# STORE ACCESS CONTROL
# ═══════════════════════════════════════════════════════════════════════════

class UserStoreAccess(models.Model):
    """Controls which stores a user can access. Owners bypass this."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="store_access_entries")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="store_access")
    store = models.ForeignKey("stores.Store", on_delete=models.CASCADE, related_name="user_access")

    class Meta:
        db_table = "core_userstoreaccess"
        unique_together = [("user", "store")]
        indexes = [
            models.Index(fields=["user", "store"]),
            models.Index(fields=["tenant", "user"]),
        ]

    def __str__(self) -> str:
        return f"User {self.user_id} → Store {self.store_id}"


class CronHeartbeat(models.Model):
    """
    Tracker de última ejecución de cada cron / task periódica.
    Cada comando actualiza su heartbeat cuando termina OK.
    El endpoint /api/core/health/deep revisa si los heartbeats están fresh.
    """
    task_name = models.CharField(max_length=100, primary_key=True)
    last_run_at = models.DateTimeField(auto_now=True)
    last_duration_s = models.FloatField(default=0)
    last_result = models.CharField(max_length=20, default="ok",
        help_text="ok / failed / running")
    last_error = models.CharField(max_length=500, blank=True, default="")
    # Cuán "viejo" puede estar antes de considerarse stale
    expected_max_age_minutes = models.IntegerField(default=90,
        help_text="Minutos máximos entre ejecuciones esperadas")

    class Meta:
        db_table = "core_cron_heartbeat"

    def __str__(self) -> str:
        return f"{self.task_name} @ {self.last_run_at}"

    @property
    def is_stale(self) -> bool:
        """True si hace más de expected_max_age_minutes que no corre."""
        from django.utils import timezone as _tz
        from datetime import timedelta as _td
        if not self.last_run_at:
            return True
        cutoff = _tz.now() - _td(minutes=self.expected_max_age_minutes)
        return self.last_run_at < cutoff


def record_cron_heartbeat(task_name: str, duration_s: float = 0,
                          result: str = "ok", error: str = "",
                          expected_max_age_minutes: int = 90):
    """Helper que registra heartbeat desde cualquier management command/task."""
    CronHeartbeat.objects.update_or_create(
        task_name=task_name,
        defaults={
            "last_duration_s": round(duration_s, 2),
            "last_result": result,
            "last_error": error[:500],
            "expected_max_age_minutes": expected_max_age_minutes,
        },
    )