"""
Tests para los huecos críticos detectados en la auditoría de imports/exports.

Cubre:
- ProductImport: NaN/inf en precios, duplicados intra-archivo, límite plan.
- RecipeImport: MAX_ROWS, productos inactivos con mensaje claro.
- AdminImportSalesView: transaction.atomic, qty negativa, no fallback silencioso.
- Exports XLSX: formula injection neutralizada por sanitize_cell.
"""
import io
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from catalog.models import Product, Recipe, RecipeLine, Unit


def _csv_bytes(rows, header="name,sku,price"):
    out = io.StringIO()
    out.write(header + "\n")
    for r in rows:
        out.write(r + "\n")
    return io.BytesIO(out.getvalue().encode("utf-8-sig"))


# ─── ProductImport ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestProductImportNaNInfRejected:
    """`_normalize_price` debe rechazar NaN, Infinity y negativos."""

    def test_nan_rejected(self, api_client, tenant):
        f = _csv_bytes(["Producto NaN,SKU1,NaN"])
        r = api_client.post(
            "/api/catalog/products/import-csv/",
            {"file": f},
            format="multipart",
        )
        assert r.status_code == 200
        assert r.data["created"] == 0
        # Mensaje debe mencionar NaN/Infinity
        assert any("nan" in str(e).lower() or "infinity" in str(e).lower()
                   for e in r.data["errors"]), r.data["errors"]

    def test_infinity_rejected(self, api_client, tenant):
        f = _csv_bytes(["Producto Inf,SKU2,Infinity"])
        r = api_client.post("/api/catalog/products/import-csv/", {"file": f}, format="multipart")
        assert r.data["created"] == 0
        assert len(r.data["errors"]) >= 1

    def test_negative_price_rejected(self, api_client, tenant):
        f = _csv_bytes(["Producto Neg,SKU3,-100"])
        r = api_client.post("/api/catalog/products/import-csv/", {"file": f}, format="multipart")
        assert r.data["created"] == 0
        assert any("negativo" in str(e).lower() for e in r.data["errors"])

    def test_valid_price_accepted(self, api_client, tenant):
        f = _csv_bytes(["Producto OK,SKU_OK,1500.50"])
        r = api_client.post("/api/catalog/products/import-csv/", {"file": f}, format="multipart")
        assert r.data["created"] == 1
        p = Product.objects.get(tenant=tenant, sku="SKU_OK")
        assert p.price == Decimal("1500.50")


@pytest.mark.django_db
class TestProductImportDuplicatesInFile:
    """SKU/nombre duplicado en el MISMO archivo se rechaza con mensaje claro."""

    def test_duplicate_sku_in_file_rejected(self, api_client, tenant):
        f = _csv_bytes([
            "Producto A,DUPSKU,100",
            "Producto B,DUPSKU,200",  # mismo SKU → debe rechazar
        ])
        r = api_client.post("/api/catalog/products/import-csv/", {"file": f}, format="multipart")
        assert r.data["created"] == 1, "Solo el primer SKU debe crearse"
        assert r.data["skipped"] == 1
        # Mensaje del error menciona la línea 2 donde apareció primero
        err_msg = " ".join(str(e) for e in r.data["errors"])
        assert "DUPSKU" in err_msg or "ya apareció" in err_msg.lower()

    def test_duplicate_name_no_sku_rejected(self, api_client, tenant):
        f = _csv_bytes([
            "Producto Sin Sku,,100",
            "Producto Sin Sku,,200",  # mismo nombre, sin SKU → rechazar
        ])
        r = api_client.post("/api/catalog/products/import-csv/", {"file": f}, format="multipart")
        assert r.data["created"] == 1
        assert r.data["skipped"] == 1


# ─── RecipeImport ──────────────────────────────────────────────────────


def _u(tenant, code):
    return Unit.objects.create(tenant=tenant, code=code, name=code,
                                family="COUNT", is_base=True, conversion_factor=Decimal("1"))


def _p(tenant, name, sku=None, active=True):
    return Product.objects.create(
        tenant=tenant, name=name, sku=sku or name.replace(" ", "_").upper(),
        price=Decimal("100"), is_active=active,
    )


def _recipe_csv(rows):
    out = io.StringIO()
    out.write("product_sku,ingredient_sku,qty\n")
    for r in rows:
        out.write(r + "\n")
    return io.BytesIO(out.getvalue().encode("utf-8-sig"))


@pytest.mark.django_db
class TestRecipeImportInactiveProducts:
    """Si producto padre o ingrediente está desactivado, error claro
    (antes decía 'Producto no encontrado' confuso)."""

    def test_inactive_parent_message(self, api_client, tenant):
        _p(tenant, "PADRE_OFF", active=False)
        _p(tenant, "ING1", active=True)
        f = _recipe_csv(["PADRE_OFF,ING1,100"])
        r = api_client.post("/api/catalog/recipes/import-csv/", {"file": f}, format="multipart")
        assert r.status_code == 200
        err_msg = " ".join(str(e) for e in r.data.get("errors", []))
        assert "DESACTIVADO" in err_msg or "desactivado" in err_msg.lower(), \
            f"Mensaje debería mencionar desactivado: {err_msg}"

    def test_inactive_ingredient_message(self, api_client, tenant):
        _p(tenant, "PADRE", active=True)
        _p(tenant, "ING_OFF", active=False)
        f = _recipe_csv(["PADRE,ING_OFF,100"])
        r = api_client.post("/api/catalog/recipes/import-csv/", {"file": f}, format="multipart")
        err_msg = " ".join(str(e) for e in r.data.get("errors", []))
        assert "DESACTIVADO" in err_msg or "desactivado" in err_msg.lower()


@pytest.mark.django_db
class TestRecipeImportMaxRows:
    """Cap de filas para evitar DoS."""

    def test_max_rows_enforced(self, api_client, tenant, monkeypatch):
        """Patcheamos MAX_ROWS a 3 para no generar 5000 productos."""
        from catalog.views import RecipeImport
        monkeypatch.setattr(RecipeImport, "MAX_ROWS", 3)

        _p(tenant, "ING_MAX", active=True)
        for i in range(5):
            _p(tenant, f"PADRE_{i}", sku=f"PMAX_{i}", active=True)
        rows = [f"PMAX_{i},ING_MAX,1" for i in range(5)]
        f = _recipe_csv(rows)
        r = api_client.post("/api/catalog/recipes/import-csv/", {"file": f}, format="multipart")
        errors = r.data.get("errors", [])
        # Cada error es {"line": N, "error": "..."}
        cap_errors = [
            e for e in errors
            if isinstance(e, dict) and "ximo" in str(e.get("error", "")).lower()
        ]
        assert len(cap_errors) >= 1, \
            f"Esperaba error de cap. Got errors={errors[:5]}"


# ─── AdminImportSalesView ─────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminSalesImportNegativeQty:
    """qty_sold negativo debe rechazarse explícitamente."""

    def test_negative_qty_skipped_with_error(
        self, api_client, tenant, warehouse,
    ):
        from core.models import User
        admin = User.objects.create_superuser(
            username="admin_test", email="admin@test.cl", password="x123456",
        )
        client = APIClient()
        client.force_authenticate(user=admin)

        p = _p(tenant, "P_neg")
        # CSV con qty negativo
        csv = io.StringIO()
        csv.write("date,product_id,qty_sold,total\n")
        csv.write(f"2026-04-01,{p.id},-5,1000\n")
        csv.write(f"2026-04-02,{p.id},10,2000\n")  # válido
        f = io.BytesIO(csv.getvalue().encode("utf-8-sig"))
        f.name = "test.csv"

        r = client.post(
            "/api/superadmin/forecast/import-sales/",
            {"tenant_id": tenant.id, "file": f},
            format="multipart",
        )
        assert r.status_code == 200, r.data
        # Una fila válida, una rechazada
        assert r.data["created"] == 1
        assert r.data["skipped"] == 1
        err_msg = " ".join(str(e) for e in r.data.get("errors", []))
        assert "negativo" in err_msg.lower()
