"""
Printing Agent system — allows Pulstock to print via a desktop agent
installed on a client PC that has access to local/LAN printers.

Flow:
1. Tenant user clicks "Install Agent" → server creates a PrintAgent with
   a short pairing_code (e.g. "ABCD-1234") displayed to the user.
2. User installs the agent software on their PC and enters the pairing
   code. Agent exchanges the code for a long-lived api_key.
3. Agent polls GET /api/printing/agents/poll/?key=X every 2-5s.
4. Frontend (web) queues a PrintJob → backend stores it pending.
5. Agent picks up pending jobs, prints them locally, reports result.
6. Agent reports its available printers via POST /agents/printers/.
"""

import secrets
import string
from datetime import timedelta

from django.db import models
from django.utils import timezone


def _gen_api_key() -> str:
    """64-char URL-safe random key for agent authentication."""
    return secrets.token_urlsafe(48)


def _gen_pairing_code() -> str:
    """Short pairing code like 'ABCD-1234' that the user types into agent."""
    alpha = "ABCDEFGHJKMNPQRSTUVWXYZ"  # no I, L, O — easier to type
    digit = "23456789"  # no 0, 1 — easier to distinguish
    letters = "".join(secrets.choice(alpha) for _ in range(4))
    digits = "".join(secrets.choice(digit) for _ in range(4))
    return f"{letters}-{digits}"


class PrintAgent(models.Model):
    """An agent program installed on a client's PC."""

    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.CASCADE,
        related_name="print_agents",
    )
    store = models.ForeignKey(
        "stores.Store", on_delete=models.CASCADE,
        related_name="print_agents",
        null=True, blank=True,
        help_text="Local al que pertenece este agente (opcional)",
    )
    name = models.CharField(
        max_length=100,
        help_text="Nombre descriptivo, ej: 'PC de Caja Principal'",
    )

    # Authentication
    api_key = models.CharField(
        max_length=128, unique=True, db_index=True,
        default=_gen_api_key,
        help_text="API key que usa el agente para autenticarse",
    )
    # Pairing (set at registration, cleared once agent claims it)
    pairing_code = models.CharField(
        max_length=16, blank=True, default="",
        db_index=True,
        help_text="Código temporal que el usuario escribe en el agente",
    )
    pairing_code_expires_at = models.DateTimeField(null=True, blank=True)
    paired_at = models.DateTimeField(null=True, blank=True)

    # State
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Última vez que el agente hizo un poll",
    )
    version = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Versión del software del agente",
    )
    os_info = models.CharField(
        max_length=100, blank=True, default="",
        help_text="OS reportado por el agente (Windows 10, etc.)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "printing_printagent"
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["tenant", "store"]),
            models.Index(fields=["pairing_code"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.tenant.name})"

    # ─── Helpers ────────────────────────────────────────────────

    @property
    def is_online(self) -> bool:
        """True if agent polled in the last 2 minutes."""
        if not self.last_seen_at:
            return False
        return (timezone.now() - self.last_seen_at).total_seconds() < 120

    @property
    def is_pairing_pending(self) -> bool:
        """True if waiting for the agent to claim its pairing code."""
        return (
            bool(self.pairing_code)
            and self.paired_at is None
            and self.pairing_code_expires_at is not None
            and self.pairing_code_expires_at > timezone.now()
        )

    def generate_pairing_code(self, ttl_minutes: int = 30) -> str:
        """(Re)generate a pairing code. Returns the code string."""
        self.pairing_code = _gen_pairing_code()
        self.pairing_code_expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
        self.paired_at = None
        self.save(update_fields=[
            "pairing_code", "pairing_code_expires_at", "paired_at",
        ])
        return self.pairing_code

    def mark_paired(self) -> None:
        """Consume the pairing code — called when agent successfully authenticates."""
        self.paired_at = timezone.now()
        self.pairing_code = ""  # one-shot
        self.pairing_code_expires_at = None
        self.save(update_fields=[
            "paired_at", "pairing_code", "pairing_code_expires_at",
        ])

    def touch(self) -> None:
        """Update last_seen_at. Called on every poll.

        Debounced: como `is_online` considera online <2min, no necesitamos
        precisión al segundo. Solo actualizamos si la última vez fue hace
        >=20s — reduce escrituras de DB de 1200/hora/agente a 180/hora/agente.
        """
        now = timezone.now()
        if self.last_seen_at is not None:
            delta = (now - self.last_seen_at).total_seconds()
            if delta < 20:
                return
        self.last_seen_at = now
        self.save(update_fields=["last_seen_at"])


class AgentPrinter(models.Model):
    """A printer that the agent has detected and reported back to the server."""

    CONNECTION_CHOICES = [
        ("system", "Sistema (impresora del OS)"),
        ("usb", "USB directa"),
        ("network", "Red (LAN por IP)"),
    ]

    agent = models.ForeignKey(
        PrintAgent, on_delete=models.CASCADE,
        related_name="printers",
    )
    name = models.CharField(
        max_length=150,
        help_text="Nombre de la impresora (como la reporta el OS)",
    )
    display_name = models.CharField(
        max_length=150, blank=True, default="",
        help_text="Nombre descriptivo para el usuario",
    )
    paper_width = models.IntegerField(
        default=80,
        choices=[(58, "58mm"), (80, "80mm")],
    )
    connection_type = models.CharField(
        max_length=20, choices=CONNECTION_CHOICES,
        default="system",
    )
    network_address = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Solo para connection_type=network: '192.168.1.11:9100'",
    )

    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "printing_agentprinter"
        unique_together = [("agent", "name")]
        indexes = [
            models.Index(fields=["agent", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.display_name or self.name} @ {self.agent.name}"


class PrintJob(models.Model):
    """A print job queued for an agent to execute."""

    STATUS_PENDING = "pending"
    STATUS_PRINTING = "printing"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_PRINTING, "Imprimiendo"),
        (STATUS_DONE, "Completado"),
        (STATUS_FAILED, "Fallido"),
        (STATUS_CANCELLED, "Cancelado"),
    ]

    tenant = models.ForeignKey(
        "core.Tenant", on_delete=models.CASCADE,
        related_name="print_jobs",
    )
    agent = models.ForeignKey(
        PrintAgent, on_delete=models.CASCADE,
        related_name="jobs",
    )
    printer_name = models.CharField(
        max_length=150, blank=True, default="",
        help_text="Vacío = usar la impresora por defecto del agente",
    )

    # Payload — use one of these
    data_b64 = models.TextField(
        blank=True, default="",
        help_text="Base64 de bytes ESC/POS",
    )
    html = models.TextField(
        blank=True, default="",
        help_text="HTML para imprimir via diálogo del OS",
    )

    # State
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES,
        default=STATUS_PENDING, db_index=True,
    )
    error_msg = models.CharField(max_length=500, blank=True, default="")
    retry_count = models.IntegerField(default=0)

    # Audit
    created_by = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="+",
    )
    source = models.CharField(
        max_length=30, blank=True, default="",
        help_text="Origen del trabajo: pos, mesa, manual, test",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    picked_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "printing_printjob"
        indexes = [
            models.Index(fields=["agent", "status", "created_at"]),
            models.Index(fields=["tenant", "status"]),
        ]
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Job #{self.pk} → {self.printer_name or '[default]'} [{self.status}]"

    # ─── Helpers ────────────────────────────────────────────────

    def mark_printing(self) -> None:
        self.status = self.STATUS_PRINTING
        self.picked_at = timezone.now()
        self.save(update_fields=["status", "picked_at"])

    def mark_done(self) -> None:
        self.status = self.STATUS_DONE
        self.completed_at = timezone.now()
        self.error_msg = ""
        self.save(update_fields=["status", "completed_at", "error_msg"])

    def mark_failed(self, error: str) -> None:
        self.status = self.STATUS_FAILED
        self.completed_at = timezone.now()
        self.error_msg = (error or "")[:500]
        self.save(update_fields=["status", "completed_at", "error_msg"])
