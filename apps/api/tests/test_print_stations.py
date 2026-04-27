"""
Tests para el feature de Print Stations (estaciones de impresión).

Cubre:
  - Modelo PrintStation: creación, unique_together por tenant, defaults
  - Endpoints CRUD: list, create, update, delete
  - Permisos: solo manager/owner pueden tocar; cashier no
  - Tenant isolation: no se ven estaciones de otro tenant
  - Asignación de impresoras (AgentPrinterStationView)
  - Routing por station_id en AutoPrintView
  - SET_NULL semantics: borrar estación NO borra categorías/productos
  - Estación efectiva en serializers (override > category > null)
  - OpenOrder lines incluyen print_station_id
  - Validación: nombre seguro, station_id pertenece al tenant, etc.
"""
import base64
import pytest
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import User, Tenant
from catalog.models import Category, Product
from printing.models import PrintAgent, PrintJob, AgentPrinter, PrintStation


# ─── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def active_subscription(db, tenant):
    """Suscripción activa requerida por SubscriptionAccessMiddleware."""
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
    """Client autenticado como owner del tenant."""
    c = APIClient()
    token = RefreshToken.for_user(user)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return c


@pytest.fixture
def cashier_client(db, tenant, store, active_subscription):
    """Client autenticado como CASHIER (no debería poder editar stations)."""
    cashier, _ = User.objects.get_or_create(
        username="cashier_test",
        defaults={
            "tenant": tenant,
            "active_store": store,
            "role": User.Role.CASHIER,
        },
    )
    cashier.tenant = tenant
    cashier.role = User.Role.CASHIER
    cashier.set_password("testpass123")
    cashier.save()

    c = APIClient()
    token = RefreshToken.for_user(cashier)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return c


@pytest.fixture
def online_agent(tenant):
    a = PrintAgent.objects.create(tenant=tenant, name="PC Test")
    a.generate_pairing_code()
    a.mark_paired()
    a.last_seen_at = timezone.now()
    a.save(update_fields=["last_seen_at"])
    return a


@pytest.fixture
def offline_agent(tenant):
    a = PrintAgent.objects.create(tenant=tenant, name="PC Offline")
    a.generate_pairing_code()
    a.mark_paired()
    a.last_seen_at = timezone.now() - timedelta(minutes=10)
    a.save(update_fields=["last_seen_at"])
    return a


# ═══════════════════════════════════════════════════════════════════
# 1. MODEL TESTS
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPrintStationModel:
    """Tests del modelo PrintStation directamente (sin HTTP)."""

    def test_create_station(self, tenant):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        assert s.id is not None
        assert s.is_active is True
        assert s.is_default_for_receipts is False
        assert s.sort_order == 0

    def test_unique_name_per_tenant(self, tenant):
        PrintStation.objects.create(tenant=tenant, name="Cocina")
        with pytest.raises(Exception):  # IntegrityError
            PrintStation.objects.create(tenant=tenant, name="Cocina")

    def test_same_name_different_tenants_ok(self, tenant):
        """Tenant A y Tenant B pueden tener cada uno su propia 'Cocina'."""
        t2 = Tenant(name="Tenant 2", slug="t2")
        t2._skip_subscription = True
        t2.save()
        PrintStation.objects.create(tenant=tenant, name="Cocina")
        s2 = PrintStation.objects.create(tenant=t2, name="Cocina")
        assert s2.tenant_id == t2.id

    def test_str(self, tenant):
        s = PrintStation.objects.create(tenant=tenant, name="Bar")
        assert "Bar" in str(s)


# ═══════════════════════════════════════════════════════════════════
# 2. CRUD ENDPOINTS
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestStationListCreate:
    URL = "/api/printing/stations/"

    def test_list_empty(self, jwt_client):
        r = jwt_client.get(self.URL)
        assert r.status_code == 200
        assert r.json() == []

    def test_list_returns_only_own_tenant(self, jwt_client, tenant):
        # Estación nuestra
        PrintStation.objects.create(tenant=tenant, name="Cocina")
        # Estación de otro tenant
        t2 = Tenant(name="Otro", slug="otro")
        t2._skip_subscription = True
        t2.save()
        PrintStation.objects.create(tenant=t2, name="Bar Otro Tenant")

        r = jwt_client.get(self.URL)
        assert r.status_code == 200
        data = r.json()
        names = [s["name"] for s in data]
        assert "Cocina" in names
        assert "Bar Otro Tenant" not in names

    def test_create_basic(self, jwt_client, tenant):
        r = jwt_client.post(self.URL, {"name": "Cocina"}, format="json")
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "Cocina"
        assert body["is_default_for_receipts"] is False
        assert PrintStation.objects.filter(tenant=tenant, name="Cocina").exists()

    def test_create_default_for_receipts(self, jwt_client, tenant):
        r = jwt_client.post(
            self.URL,
            {"name": "Caja", "is_default_for_receipts": True},
            format="json",
        )
        assert r.status_code == 201
        s = PrintStation.objects.get(tenant=tenant, name="Caja")
        assert s.is_default_for_receipts is True

    def test_create_only_one_default(self, jwt_client, tenant):
        """Crear una nueva estación con is_default_for_receipts=True desactiva
        el flag en cualquier estación previa."""
        PrintStation.objects.create(
            tenant=tenant, name="Caja Vieja", is_default_for_receipts=True,
        )
        r = jwt_client.post(
            self.URL,
            {"name": "Caja Nueva", "is_default_for_receipts": True},
            format="json",
        )
        assert r.status_code == 201
        # Vieja ya no es default
        old = PrintStation.objects.get(tenant=tenant, name="Caja Vieja")
        assert old.is_default_for_receipts is False
        # Nueva sí
        new = PrintStation.objects.get(tenant=tenant, name="Caja Nueva")
        assert new.is_default_for_receipts is True

    def test_create_duplicate_name_returns_409(self, jwt_client, tenant):
        PrintStation.objects.create(tenant=tenant, name="Cocina")
        r = jwt_client.post(self.URL, {"name": "Cocina"}, format="json")
        assert r.status_code == 409
        assert "Cocina" in r.json()["detail"]

    def test_create_revives_soft_deleted_station(self, jwt_client, tenant):
        """
        Bug del piloto Marbrava: el user creó "caja", la borró, y al intentar
        crear "caja" de nuevo recibía 409 — la unique_together (tenant, name)
        bloqueaba el INSERT porque la fila soft-deleted seguía ahí.
        Ahora reactivamos la inactiva en vez de fallar.
        """
        # Crear y soft-delete
        original = PrintStation.objects.create(
            tenant=tenant, name="Caja", is_active=True,
            sort_order=5, is_default_for_receipts=True,
        )
        original_id = original.id
        original.is_active = False
        original.is_default_for_receipts = False
        original.save()

        # Re-crear con mismo nombre + nuevos atributos
        r = jwt_client.post(
            self.URL,
            {"name": "Caja", "is_default_for_receipts": True, "sort_order": 0},
            format="json",
        )
        assert r.status_code == 201, r.json()
        body = r.json()
        # Mismo id (revivida, no nueva)
        assert body["id"] == original_id
        # Atributos actualizados
        assert body["is_default_for_receipts"] is True
        assert body["sort_order"] == 0
        # Verificar en DB
        revived = PrintStation.objects.get(id=original_id)
        assert revived.is_active is True
        assert revived.is_default_for_receipts is True
        # Sigue siendo una sola estación con ese nombre
        assert PrintStation.objects.filter(tenant=tenant, name="Caja").count() == 1

    def test_create_revives_only_when_inactive(self, jwt_client, tenant):
        """Si ya hay una ACTIVA con el mismo nombre, sí devuelve 409 (es
        duplicado real). El revive solo aplica a soft-deleted."""
        PrintStation.objects.create(tenant=tenant, name="Bar", is_active=True)
        r = jwt_client.post(self.URL, {"name": "Bar"}, format="json")
        assert r.status_code == 409

    def test_create_revives_does_not_cross_tenants(self, jwt_client, tenant):
        """Una estación soft-deleted en otro tenant NO se revive cuando este
        tenant pide el mismo nombre — son tenants distintos."""
        from core.models import Tenant
        t2 = Tenant(name="Otro", slug="otro-revive")
        t2._skip_subscription = True
        t2.save()
        PrintStation.objects.create(tenant=t2, name="Caja", is_active=False)

        r = jwt_client.post(self.URL, {"name": "Caja"}, format="json")
        assert r.status_code == 201
        # Se creó nueva estación en NUESTRO tenant — la del otro tenant queda
        # intacta (sigue inactiva).
        assert PrintStation.objects.filter(tenant=tenant, name="Caja", is_active=True).count() == 1
        assert PrintStation.objects.filter(tenant=t2, name="Caja", is_active=False).count() == 1

    def test_create_blank_name_400(self, jwt_client):
        r = jwt_client.post(self.URL, {"name": ""}, format="json")
        assert r.status_code == 400

    def test_create_unsafe_name_400(self, jwt_client):
        # Caracteres de control / HTML deben rechazarse
        for bad in ["<script>", '"; DROP TABLE', "\x00null", "  "]:
            r = jwt_client.post(self.URL, {"name": bad}, format="json")
            assert r.status_code == 400, f"name={bad!r} debería rechazarse"

    def test_create_accents_ok(self, jwt_client):
        for ok in ["Cocina caliente", "Café", "Recepción", "Bar 2"]:
            r = jwt_client.post(self.URL, {"name": ok}, format="json")
            assert r.status_code == 201, f"name={ok!r} debería aceptarse: {r.json()}"

    def test_cap_30_stations(self, jwt_client, tenant):
        for i in range(30):
            PrintStation.objects.create(tenant=tenant, name=f"Estación {i}")
        r = jwt_client.post(self.URL, {"name": "Una más"}, format="json")
        assert r.status_code == 400
        assert "30" in r.json()["detail"]

    def test_cashier_cannot_create(self, cashier_client):
        r = cashier_client.post(self.URL, {"name": "Cocina"}, format="json")
        assert r.status_code in (403, 401)  # IsManager rechaza CASHIER


@pytest.mark.django_db
class TestStationDetail:
    def url(self, pk):
        return f"/api/printing/stations/{pk}/"

    def test_rename(self, jwt_client, tenant):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        r = jwt_client.patch(self.url(s.id), {"name": "Cocina caliente"}, format="json")
        assert r.status_code == 200
        s.refresh_from_db()
        assert s.name == "Cocina caliente"

    def test_rename_to_existing_returns_409(self, jwt_client, tenant):
        PrintStation.objects.create(tenant=tenant, name="Cocina")
        s2 = PrintStation.objects.create(tenant=tenant, name="Bar")
        r = jwt_client.patch(self.url(s2.id), {"name": "Cocina"}, format="json")
        assert r.status_code == 409

    def test_rename_to_invalid_returns_400(self, jwt_client, tenant):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        r = jwt_client.patch(self.url(s.id), {"name": "<bad>"}, format="json")
        assert r.status_code == 400

    def test_set_default_unsets_others(self, jwt_client, tenant):
        s1 = PrintStation.objects.create(
            tenant=tenant, name="Caja 1", is_default_for_receipts=True,
        )
        s2 = PrintStation.objects.create(tenant=tenant, name="Caja 2")
        r = jwt_client.patch(
            self.url(s2.id), {"is_default_for_receipts": True}, format="json",
        )
        assert r.status_code == 200
        s1.refresh_from_db(); s2.refresh_from_db()
        assert s1.is_default_for_receipts is False
        assert s2.is_default_for_receipts is True

    def test_delete_soft_deletes(self, jwt_client, tenant):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        r = jwt_client.delete(self.url(s.id))
        assert r.status_code == 204
        s.refresh_from_db()
        assert s.is_active is False

    def test_delete_unsets_default_flag(self, jwt_client, tenant):
        s = PrintStation.objects.create(
            tenant=tenant, name="Caja", is_default_for_receipts=True,
        )
        jwt_client.delete(self.url(s.id))
        s.refresh_from_db()
        assert s.is_default_for_receipts is False

    def test_delete_deassociates_printers(self, jwt_client, tenant, online_agent):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        p = AgentPrinter.objects.create(
            agent=online_agent, name="Epson Cocina", station=s,
        )
        jwt_client.delete(self.url(s.id))
        p.refresh_from_db()
        assert p.station_id is None  # SET_NULL
        # La impresora sigue activa — solo se desasoció
        assert p.is_active is True

    def test_delete_other_tenant_404(self, jwt_client):
        t2 = Tenant(name="Otro", slug="otro")
        t2._skip_subscription = True
        t2.save()
        s = PrintStation.objects.create(tenant=t2, name="Cocina Ajena")
        r = jwt_client.delete(self.url(s.id))
        assert r.status_code == 404

    def test_inactive_returns_404(self, jwt_client, tenant):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina", is_active=False)
        r = jwt_client.patch(self.url(s.id), {"name": "x"}, format="json")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# 3. PRINTER ↔ STATION ASSIGNMENT
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPrinterStationAssignment:
    def url(self, printer_id):
        return f"/api/printing/printers/{printer_id}/station/"

    def test_assign_printer(self, jwt_client, tenant, online_agent):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        p = AgentPrinter.objects.create(agent=online_agent, name="Epson")
        r = jwt_client.patch(self.url(p.id), {"station_id": s.id}, format="json")
        assert r.status_code == 200
        p.refresh_from_db()
        assert p.station_id == s.id

    def test_unassign_printer(self, jwt_client, tenant, online_agent):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        p = AgentPrinter.objects.create(agent=online_agent, name="Epson", station=s)
        r = jwt_client.patch(self.url(p.id), {"station_id": None}, format="json")
        assert r.status_code == 200
        p.refresh_from_db()
        assert p.station_id is None

    def test_assign_other_tenant_station_404(self, jwt_client, online_agent):
        t2 = Tenant(name="Otro", slug="otro2")
        t2._skip_subscription = True
        t2.save()
        s_other = PrintStation.objects.create(tenant=t2, name="Cocina otra")
        p = AgentPrinter.objects.create(agent=online_agent, name="Epson")
        r = jwt_client.patch(self.url(p.id), {"station_id": s_other.id}, format="json")
        assert r.status_code == 404

    def test_assign_other_tenant_printer_404(self, jwt_client, tenant):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        # Crear printer en agente de otro tenant
        t2 = Tenant(name="Otro", slug="otro3")
        t2._skip_subscription = True
        t2.save()
        a2 = PrintAgent.objects.create(tenant=t2, name="PC otro")
        a2.mark_paired()
        p_other = AgentPrinter.objects.create(agent=a2, name="EpsonOtro")
        r = jwt_client.patch(self.url(p_other.id), {"station_id": s.id}, format="json")
        assert r.status_code == 404

    def test_invalid_station_id_400(self, jwt_client, online_agent):
        p = AgentPrinter.objects.create(agent=online_agent, name="Epson")
        r = jwt_client.patch(self.url(p.id), {"station_id": "abc"}, format="json")
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════
# 4. AUTO-PRINT ROUTING BY STATION
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAutoPrintWithStation:
    URL = "/api/printing/print/"
    PAYLOAD_B64 = base64.b64encode(b"hello").decode()

    def test_print_with_station_routes_to_assigned_printer(
        self, jwt_client, tenant, online_agent,
    ):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        p = AgentPrinter.objects.create(
            agent=online_agent, name="Epson Cocina", station=s, is_default=True,
        )
        # Otra impresora SIN estación — no debería elegirse
        AgentPrinter.objects.create(
            agent=online_agent, name="Otra impresora", is_default=True,
        )
        r = jwt_client.post(
            self.URL,
            {"data_b64": self.PAYLOAD_B64, "station_id": s.id, "source": "comanda"},
            format="json",
        )
        assert r.status_code == 201
        body = r.json()
        # El nombre que vuelve es el display_name o name
        assert "Epson Cocina" in body["printer_name"]
        # Verificar que el job se creó con la printer correcta
        job = PrintJob.objects.get(pk=body["job_id"])
        assert job.printer_name == p.name
        assert job.source == "comanda"

    def test_print_with_station_no_assigned_printer_returns_404(
        self, jwt_client, tenant,
    ):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        r = jwt_client.post(
            self.URL,
            {"data_b64": self.PAYLOAD_B64, "station_id": s.id},
            format="json",
        )
        assert r.status_code == 404
        assert "no tiene impresoras" in r.json()["detail"].lower()

    def test_print_with_station_offline_agent_returns_404(
        self, jwt_client, tenant, offline_agent,
    ):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        AgentPrinter.objects.create(
            agent=offline_agent, name="Epson Cocina", station=s,
        )
        r = jwt_client.post(
            self.URL,
            {"data_b64": self.PAYLOAD_B64, "station_id": s.id},
            format="json",
        )
        assert r.status_code == 404
        assert "online" in r.json()["detail"].lower()

    def test_print_with_invalid_station_id_400(self, jwt_client):
        r = jwt_client.post(
            self.URL,
            {"data_b64": self.PAYLOAD_B64, "station_id": "abc"},
            format="json",
        )
        assert r.status_code == 400

    def test_print_with_other_tenant_station_400(self, jwt_client, online_agent):
        t2 = Tenant(name="Otro", slug="otro4")
        t2._skip_subscription = True
        t2.save()
        s_other = PrintStation.objects.create(tenant=t2, name="Cocina ajena")
        r = jwt_client.post(
            self.URL,
            {"data_b64": self.PAYLOAD_B64, "station_id": s_other.id},
            format="json",
        )
        assert r.status_code == 400

    def test_print_without_station_uses_default_flow(
        self, jwt_client, tenant, online_agent,
    ):
        """Backward compatibility: sin station_id, sigue funcionando como antes."""
        AgentPrinter.objects.create(
            agent=online_agent, name="Default", is_default=True,
        )
        r = jwt_client.post(
            self.URL, {"data_b64": self.PAYLOAD_B64}, format="json",
        )
        assert r.status_code == 201

    def test_comanda_source_accepted(self, jwt_client, tenant, online_agent):
        AgentPrinter.objects.create(
            agent=online_agent, name="Default", is_default=True,
        )
        r = jwt_client.post(
            self.URL,
            {"data_b64": self.PAYLOAD_B64, "source": "comanda"},
            format="json",
        )
        assert r.status_code == 201
        job = PrintJob.objects.get(pk=r.json()["job_id"])
        assert job.source == "comanda"


# ═══════════════════════════════════════════════════════════════════
# 5. CATALOG INTEGRATION
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCategoryWithStation:
    def test_category_serializer_returns_station(self, jwt_client, tenant):
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        c = Category.objects.create(
            tenant=tenant, name="Comida caliente", default_print_station=s,
        )
        r = jwt_client.get(f"/api/catalog/categories/{c.id}/")
        assert r.status_code == 200
        body = r.json()
        assert body["default_print_station_id"] == s.id
        assert body["default_print_station_name"] == "Cocina"

    def test_category_assign_station(self, jwt_client, tenant):
        s = PrintStation.objects.create(tenant=tenant, name="Bar")
        c = Category.objects.create(tenant=tenant, name="Bebidas")
        r = jwt_client.patch(
            f"/api/catalog/categories/{c.id}/",
            {"default_print_station_id": s.id},
            format="json",
        )
        assert r.status_code == 200
        c.refresh_from_db()
        assert c.default_print_station_id == s.id

    def test_category_clear_station(self, jwt_client, tenant):
        s = PrintStation.objects.create(tenant=tenant, name="Bar")
        c = Category.objects.create(
            tenant=tenant, name="Bebidas", default_print_station=s,
        )
        r = jwt_client.patch(
            f"/api/catalog/categories/{c.id}/",
            {"default_print_station_id": None},
            format="json",
        )
        assert r.status_code == 200
        c.refresh_from_db()
        assert c.default_print_station_id is None

    def test_category_other_tenant_station_rejected(self, jwt_client, tenant):
        t2 = Tenant(name="Otro", slug="otro5")
        t2._skip_subscription = True
        t2.save()
        s_other = PrintStation.objects.create(tenant=t2, name="Otra")
        c = Category.objects.create(tenant=tenant, name="Bebidas")
        r = jwt_client.patch(
            f"/api/catalog/categories/{c.id}/",
            {"default_print_station_id": s_other.id},
            format="json",
        )
        # Como la queryset del PrimaryKeyRelatedField filtra por
        # is_active=True (no por tenant), DRF no encuentra y devuelve 400
        # con "Invalid pk". Si la encontrara, validate_default_print_station_id
        # rechazaría con 400 también. En cualquier caso: rechazo.
        assert r.status_code == 400

    def test_delete_station_set_null_on_category(self, tenant):
        """Eliminar una estación NO borra la categoría — solo deja el FK null."""
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        c = Category.objects.create(
            tenant=tenant, name="Comida", default_print_station=s,
        )
        s.delete()  # hard delete — comprobamos SET_NULL del modelo
        c.refresh_from_db()
        assert c.id is not None
        assert c.default_print_station_id is None


@pytest.mark.django_db
class TestProductEffectiveStation:
    """La 'estación efectiva' resuelve override > category default > null."""

    def test_no_override_no_category_station(self, tenant):
        from catalog.serializers import ProductReadSerializer
        cat = Category.objects.create(tenant=tenant, name="X")
        p = Product.objects.create(tenant=tenant, name="P", price=Decimal("100"), category=cat)
        data = ProductReadSerializer(p).data
        assert data["effective_print_station_id"] is None

    def test_inherits_from_category(self, tenant):
        from catalog.serializers import ProductReadSerializer
        s = PrintStation.objects.create(tenant=tenant, name="Cocina")
        cat = Category.objects.create(
            tenant=tenant, name="X", default_print_station=s,
        )
        p = Product.objects.create(tenant=tenant, name="P", price=Decimal("100"), category=cat)
        data = ProductReadSerializer(p).data
        assert data["effective_print_station_id"] == s.id

    def test_override_wins_over_category(self, tenant):
        from catalog.serializers import ProductReadSerializer
        s_cat = PrintStation.objects.create(tenant=tenant, name="Cocina")
        s_override = PrintStation.objects.create(tenant=tenant, name="Bar")
        cat = Category.objects.create(
            tenant=tenant, name="X", default_print_station=s_cat,
        )
        p = Product.objects.create(
            tenant=tenant, name="P", price=Decimal("100"),
            category=cat, print_station_override=s_override,
        )
        data = ProductReadSerializer(p).data
        assert data["effective_print_station_id"] == s_override.id

    def test_no_category_no_override(self, tenant):
        from catalog.serializers import ProductReadSerializer
        p = Product.objects.create(tenant=tenant, name="P", price=Decimal("100"))
        data = ProductReadSerializer(p).data
        assert data["effective_print_station_id"] is None


# ═══════════════════════════════════════════════════════════════════
# 6. OPENORDER LINES INCLUDE PRINT_STATION_ID
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestOpenOrderLinesPrintStation:
    def test_line_includes_station_from_category(
        self, jwt_client, tenant, warehouse, store, owner,
    ):
        from tables.models import Table, OpenOrder, OpenOrderLine

        s = PrintStation.objects.create(tenant=tenant, name="Bar")
        cat = Category.objects.create(
            tenant=tenant, name="Bebidas", default_print_station=s,
        )
        p = Product.objects.create(
            tenant=tenant, name="Coca", price=Decimal("1500"), category=cat,
        )
        table = Table.objects.create(tenant=tenant, store=store, name="Mesa 1")
        order = OpenOrder.objects.create(
            tenant=tenant, store=store, table=table,
            warehouse=warehouse, opened_by=owner,
        )
        OpenOrderLine.objects.create(
            tenant=tenant, order=order, product=p,
            qty=Decimal("1"), unit_price=Decimal("1500"), added_by=owner,
        )

        r = jwt_client.get(f"/api/tables/orders/{order.id}/")
        assert r.status_code == 200
        body = r.json()
        assert len(body["lines"]) == 1
        assert body["lines"][0]["print_station_id"] == s.id

    def test_line_includes_override_station(
        self, jwt_client, tenant, warehouse, store, owner,
    ):
        from tables.models import Table, OpenOrder, OpenOrderLine

        s_cat = PrintStation.objects.create(tenant=tenant, name="Cocina")
        s_ovr = PrintStation.objects.create(tenant=tenant, name="Bar especial")
        cat = Category.objects.create(
            tenant=tenant, name="X", default_print_station=s_cat,
        )
        p = Product.objects.create(
            tenant=tenant, name="Café irlandés", price=Decimal("3500"),
            category=cat, print_station_override=s_ovr,
        )
        table = Table.objects.create(tenant=tenant, store=store, name="Mesa 1")
        order = OpenOrder.objects.create(
            tenant=tenant, store=store, table=table,
            warehouse=warehouse, opened_by=owner,
        )
        OpenOrderLine.objects.create(
            tenant=tenant, order=order, product=p,
            qty=Decimal("1"), unit_price=Decimal("3500"), added_by=owner,
        )

        r = jwt_client.get(f"/api/tables/orders/{order.id}/")
        body = r.json()
        assert body["lines"][0]["print_station_id"] == s_ovr.id

    def test_line_no_station_returns_null(
        self, jwt_client, tenant, warehouse, store, owner,
    ):
        from tables.models import Table, OpenOrder, OpenOrderLine
        p = Product.objects.create(tenant=tenant, name="Sin Cat", price=Decimal("1000"))
        table = Table.objects.create(tenant=tenant, store=store, name="Mesa 1")
        order = OpenOrder.objects.create(
            tenant=tenant, store=store, table=table,
            warehouse=warehouse, opened_by=owner,
        )
        OpenOrderLine.objects.create(
            tenant=tenant, order=order, product=p,
            qty=Decimal("1"), unit_price=Decimal("1000"), added_by=owner,
        )
        r = jwt_client.get(f"/api/tables/orders/{order.id}/")
        body = r.json()
        assert body["lines"][0]["print_station_id"] is None


# ═══════════════════════════════════════════════════════════════════
# 7. PRINTER LIST INCLUDES STATION_ID
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_agents_list_includes_printer_station_id(
    jwt_client, tenant, online_agent,
):
    s = PrintStation.objects.create(tenant=tenant, name="Cocina")
    AgentPrinter.objects.create(agent=online_agent, name="Epson", station=s)
    r = jwt_client.get("/api/printing/agents/")
    assert r.status_code == 200
    agents = r.json()
    assert len(agents) >= 1
    printers = agents[0]["printers"]
    assert len(printers) >= 1
    assert printers[0]["station_id"] == s.id


# ═══════════════════════════════════════════════════════════════════
# 8. STATIONS LIST INCLUDES PRINTERS
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_stations_list_includes_assigned_printers(
    jwt_client, tenant, online_agent,
):
    s = PrintStation.objects.create(tenant=tenant, name="Cocina")
    AgentPrinter.objects.create(agent=online_agent, name="P1", station=s)
    AgentPrinter.objects.create(agent=online_agent, name="P2", station=s)
    # Una sin estación, no debe aparecer
    AgentPrinter.objects.create(agent=online_agent, name="Otra", station=None)

    r = jwt_client.get("/api/printing/stations/")
    body = r.json()
    cocina = next(x for x in body if x["name"] == "Cocina")
    assert len(cocina["printers"]) == 2
    names = sorted([p["name"] for p in cocina["printers"]])
    assert names == ["P1", "P2"]
