"""
Regression tests for bug fixes applied during the Agent PC audit.
Covers: soft-delete cascade, input validation, stuck-job watchdog, race safety.
"""
import base64
import pytest
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from printing.models import PrintAgent, PrintJob, AgentPrinter


@pytest.fixture
def active_subscription(db, tenant):
    """Active subscription for the test tenant (required by SubscriptionAccessMiddleware)."""
    from billing.models import Plan, Subscription
    plan, _ = Plan.objects.get_or_create(
        key="pro",
        defaults={"name": "Plan Pro", "price_clp": 29990, "max_products": -1,
                  "max_stores": -1, "max_users": -1},
    )
    sub, _ = Subscription.objects.get_or_create(
        tenant=tenant,
        defaults={
            "plan": plan, "status": "active",
            "current_period_start": timezone.now(),
            "current_period_end": timezone.now() + timedelta(days=30),
        },
    )
    return sub


@pytest.fixture
def jwt_client(user, active_subscription):
    c = APIClient()
    token = RefreshToken.for_user(user)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return c


@pytest.fixture
def agent(tenant):
    a = PrintAgent.objects.create(tenant=tenant, name="Test PC")
    a.generate_pairing_code()
    a.mark_paired()
    return a


# ─── 1. Soft-delete cancels pending/printing jobs ───────────────────

@pytest.mark.django_db
def test_soft_delete_cancels_pending_jobs(jwt_client, agent, tenant):
    pending = PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==", status="pending",
    )
    printing = PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==", status="printing",
        picked_at=timezone.now(),
    )
    done = PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==", status="done",
        completed_at=timezone.now(),
    )

    r = jwt_client.delete(f"/api/printing/agents/{agent.pk}/")
    assert r.status_code == 204

    pending.refresh_from_db()
    printing.refresh_from_db()
    done.refresh_from_db()

    assert pending.status == "cancelled"
    assert printing.status == "cancelled"
    assert done.status == "done"  # completed jobs untouched
    assert "eliminado" in pending.error_msg.lower()


# ─── 2. Queue endpoint validates printer_name + html size ────────────

@pytest.mark.django_db
def test_queue_rejects_malicious_printer_name(jwt_client, agent):
    r = jwt_client.post(
        "/api/printing/jobs/queue/",
        {"agent_id": agent.pk, "data_b64": "dGVzdA==", "printer_name": "-oraw malicious"},
        format="json",
    )
    assert r.status_code == 400
    assert "inválid" in r.json()["detail"].lower() or "invalid" in r.json()["detail"].lower()


@pytest.mark.django_db
def test_queue_rejects_printer_name_with_newline(jwt_client, agent):
    r = jwt_client.post(
        "/api/printing/jobs/queue/",
        {"agent_id": agent.pk, "data_b64": "dGVzdA==", "printer_name": "foo\nbar"},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_queue_accepts_normal_printer_name(jwt_client, agent):
    r = jwt_client.post(
        "/api/printing/jobs/queue/",
        {"agent_id": agent.pk, "data_b64": "dGVzdA==", "printer_name": "EPSON TM-T20III (Red)"},
        format="json",
    )
    assert r.status_code == 201


@pytest.mark.django_db
def test_queue_rejects_huge_html(jwt_client, agent):
    r = jwt_client.post(
        "/api/printing/jobs/queue/",
        {"agent_id": agent.pk, "html": "x" * 200_001},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_queue_accepts_normal_html(jwt_client, agent):
    r = jwt_client.post(
        "/api/printing/jobs/queue/",
        {"agent_id": agent.pk, "html": "<b>hola</b>"},
        format="json",
    )
    assert r.status_code == 201


# ─── 3. Poll watchdog — stuck printing jobs are reclaimed ────────────

@pytest.mark.django_db
def test_poll_watchdog_reclaims_stuck_printing_job(agent, tenant):
    stuck = PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==", status="printing",
        picked_at=timezone.now() - timedelta(seconds=120),  # >60s ago
        retry_count=0,
    )
    c = APIClient()
    r = c.get(f"/api/printing/agents/poll/?key={agent.api_key}")
    assert r.status_code == 200

    stuck.refresh_from_db()
    # watchdog lo pasó a pending con retry_count=1, y luego este mismo poll
    # lo reclamó → status=printing nuevamente, retry_count=1
    assert stuck.retry_count == 1
    assert stuck.status == "printing"


@pytest.mark.django_db
def test_poll_watchdog_fails_job_after_3_retries(agent, tenant):
    exhausted = PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==", status="printing",
        picked_at=timezone.now() - timedelta(seconds=120),
        retry_count=3,
    )
    c = APIClient()
    r = c.get(f"/api/printing/agents/poll/?key={agent.api_key}")
    assert r.status_code == 200

    exhausted.refresh_from_db()
    assert exhausted.status == "failed"
    assert "reintentos" in exhausted.error_msg.lower()


# ─── 4. Tenant isolation on delete/queue ─────────────────────────────

@pytest.mark.django_db
def test_cannot_delete_other_tenant_agent(jwt_client, tenant):
    from core.models import Tenant
    other = Tenant(name="Other Co", slug="other-co")
    other._skip_subscription = True
    other.save()
    other_agent = PrintAgent.objects.create(tenant=other, name="Other PC")

    r = jwt_client.delete(f"/api/printing/agents/{other_agent.pk}/")
    assert r.status_code == 404

    other_agent.refresh_from_db()
    assert other_agent.is_active is True  # still alive


@pytest.mark.django_db
def test_cannot_queue_to_other_tenant_agent(jwt_client, tenant):
    from core.models import Tenant
    other = Tenant(name="Other Co 2", slug="other-co-2")
    other._skip_subscription = True
    other.save()
    other_agent = PrintAgent.objects.create(tenant=other, name="Other PC 2")

    r = jwt_client.post(
        "/api/printing/jobs/queue/",
        {"agent_id": other_agent.pk, "data_b64": "dGVzdA=="},
        format="json",
    )
    assert r.status_code == 404


# ─── 5. Agent list excludes soft-deleted ─────────────────────────────

@pytest.mark.django_db
def test_agent_list_excludes_soft_deleted(jwt_client, agent):
    # pre-check
    r = jwt_client.get("/api/printing/agents/")
    assert r.status_code == 200
    assert any(a["id"] == agent.pk for a in r.json())

    # soft-delete
    agent.is_active = False
    agent.save()

    r = jwt_client.get("/api/printing/agents/")
    assert not any(a["id"] == agent.pk for a in r.json())


# ─── 6. New hardening: source whitelist, max agents, debounce, cleanup ───

@pytest.mark.django_db
def test_source_whitelist_normalizes_unknown_source(jwt_client, agent):
    r = jwt_client.post(
        "/api/printing/jobs/queue/",
        {"agent_id": agent.pk, "data_b64": "dGVzdA==", "source": "hacker_payload"},
        format="json",
    )
    assert r.status_code == 201
    job = PrintJob.objects.get(pk=r.json()["id"])
    assert job.source == "api"  # normalized


@pytest.mark.django_db
def test_source_whitelist_preserves_valid(jwt_client, agent):
    r = jwt_client.post(
        "/api/printing/jobs/queue/",
        {"agent_id": agent.pk, "data_b64": "dGVzdA==", "source": "pos"},
        format="json",
    )
    job = PrintJob.objects.get(pk=r.json()["id"])
    assert job.source == "pos"


@pytest.mark.django_db
def test_max_agents_per_tenant_cap(jwt_client, tenant):
    from printing.views import MAX_AGENTS_PER_TENANT
    # Pre-create up to the cap
    for i in range(MAX_AGENTS_PER_TENANT):
        PrintAgent.objects.create(tenant=tenant, name=f"Agent {i}")

    r = jwt_client.post(
        "/api/printing/agents/",
        {"name": "One too many"}, format="json",
    )
    assert r.status_code == 400
    assert "máximo" in r.json()["detail"].lower()


@pytest.mark.django_db
def test_touch_is_debounced(agent):
    """Llamadas a touch() dentro de 20s no escriben en DB."""
    import time as _time
    from django.utils import timezone as _tz
    # Fija last_seen_at hace 5s (dentro del debounce)
    agent.last_seen_at = _tz.now() - timedelta(seconds=5)
    agent.save()
    original = agent.last_seen_at
    agent.touch()
    agent.refresh_from_db()
    assert agent.last_seen_at == original  # no cambió


@pytest.mark.django_db
def test_touch_updates_after_debounce(agent):
    agent.last_seen_at = timezone.now() - timedelta(seconds=30)
    agent.save()
    original = agent.last_seen_at
    agent.touch()
    agent.refresh_from_db()
    assert agent.last_seen_at > original


@pytest.mark.django_db
def test_soft_delete_deactivates_printers(jwt_client, agent):
    p = AgentPrinter.objects.create(agent=agent, name="TestPrinter", is_active=True)
    r = jwt_client.delete(f"/api/printing/agents/{agent.pk}/")
    assert r.status_code == 204
    p.refresh_from_db()
    assert p.is_active is False


# ─── 7. Celery cleanup task ──────────────────────────────────────────

@pytest.mark.django_db
def test_cleanup_old_jobs_task_deletes_terminal_jobs(agent, tenant):
    from printing.tasks import cleanup_old_jobs, PRINT_JOB_RETENTION_DAYS
    old_cutoff = timezone.now() - timedelta(days=PRINT_JOB_RETENTION_DAYS + 1)
    recent_cutoff = timezone.now() - timedelta(days=1)

    old_done = PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==",
        status="done", completed_at=old_cutoff,
    )
    old_failed = PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==",
        status="failed", completed_at=old_cutoff,
    )
    old_cancelled = PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==",
        status="cancelled", completed_at=old_cutoff,
    )
    recent_done = PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==",
        status="done", completed_at=recent_cutoff,
    )
    pending = PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==",
        status="pending",  # no completed_at
    )

    deleted = cleanup_old_jobs()
    assert deleted == 3

    # Viejos terminales borrados
    assert not PrintJob.objects.filter(pk=old_done.pk).exists()
    assert not PrintJob.objects.filter(pk=old_failed.pk).exists()
    assert not PrintJob.objects.filter(pk=old_cancelled.pk).exists()
    # Recientes y pending preservados
    assert PrintJob.objects.filter(pk=recent_done.pk).exists()
    assert PrintJob.objects.filter(pk=pending.pk).exists()


@pytest.mark.django_db
def test_cleanup_task_returns_zero_when_nothing_to_delete(agent, tenant):
    from printing.tasks import cleanup_old_jobs
    PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==",
        status="done", completed_at=timezone.now(),
    )
    assert cleanup_old_jobs() == 0


# ─── 8. Idempotent complete ──────────────────────────────────────────

@pytest.mark.django_db
def test_complete_is_idempotent(agent, tenant):
    job = PrintJob.objects.create(
        tenant=tenant, agent=agent, data_b64="dGVzdA==", status="done",
        completed_at=timezone.now(),
    )
    c = APIClient()
    r = c.post(
        f"/api/printing/jobs/{job.pk}/complete/?key={agent.api_key}",
        {"success": True}, format="json",
    )
    assert r.status_code == 200
    assert "already" in r.json().get("detail", "").lower()
