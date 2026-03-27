"""
import_historical_sales
=======================
Importa ventas históricas desde un Excel exportado del POS
(formato: hojas "Ventas" + "Adiciones") directamente a DailySales
con forecast_only=True — sin tocar stock, sin crear transacciones.

El modelo de forecast usa estos datos igual que los reales.

Uso:
    python manage.py import_historical_sales \
        --file ventas.xls \
        --tenant 1 \
        --warehouse 1

    # Vista previa sin guardar:
    python manage.py import_historical_sales \
        --file ventas.xls --tenant 1 --warehouse 1 --dry-run

    # Crear productos que no existen:
    python manage.py import_historical_sales \
        --file ventas.xls --tenant 1 --warehouse 1 --create-products

Columnas requeridas en hoja "Adiciones":
    Id. Venta, Creación, Producto, Categoría, Cantidad, Precio,
    Costo base, Costo total, Cancelada

Columnas requeridas en hoja "Ventas":
    Id, Fecha
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date as date_cls
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Importa ventas históricas desde Excel del POS a DailySales (forecast_only=True)"

    def add_arguments(self, parser):
        parser.add_argument("--file",       required=True, help="Ruta al archivo Excel (.xls o .xlsx)")
        parser.add_argument("--tenant",     required=True, type=int, help="ID del tenant")
        parser.add_argument("--warehouse",  required=True, type=int, help="ID de la bodega")
        parser.add_argument("--dry-run",    action="store_true", help="Vista previa sin guardar")
        parser.add_argument("--create-products", action="store_true",
                            help="Crear productos que no existen en el catálogo")
        parser.add_argument("--sheet-sales",      default="Ventas",    help="Nombre hoja de ventas")
        parser.add_argument("--sheet-lines",      default="Adiciones", help="Nombre hoja de líneas")

    def handle(self, *args, **options):
        try:
            import pandas as pd
        except ImportError:
            raise CommandError("Instala pandas: pip install pandas openpyxl xlrd")

        filepath   = options["file"]
        tenant_id  = options["tenant"]
        warehouse_id = options["warehouse"]
        dry_run    = options["dry_run"]
        create_products = options["create_products"]

        # ── Cargar modelos ──
        from core.models import Tenant, Warehouse
        from catalog.models import Product, Category
        from forecast.models import DailySales

        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            raise CommandError(f"Tenant {tenant_id} no existe")

        try:
            warehouse = Warehouse.objects.get(pk=warehouse_id, tenant=tenant)
        except Warehouse.DoesNotExist:
            raise CommandError(f"Bodega {warehouse_id} no existe o no pertenece al tenant")

        # ── Leer Excel ──
        self.stdout.write(f"Leyendo {filepath}...")
        try:
            xl = pd.ExcelFile(filepath)
        except Exception as e:
            raise CommandError(f"No se pudo abrir el archivo: {e}")

        sheet_sales = options["sheet_sales"]
        sheet_lines = options["sheet_lines"]

        if sheet_sales not in xl.sheet_names:
            raise CommandError(f"Hoja '{sheet_sales}' no encontrada. Hojas: {xl.sheet_names}")
        if sheet_lines not in xl.sheet_names:
            raise CommandError(f"Hoja '{sheet_lines}' no encontrada. Hojas: {xl.sheet_names}")

        # La hoja "Ventas" tiene 3 filas de metadatos antes de los datos reales
        df_sales = xl.parse(sheet_sales, skiprows=3, header=0)
        df_lines = xl.parse(sheet_lines)

        # Limpiar columnas (quitar espacios)
        df_sales.columns = [str(c).strip() for c in df_sales.columns]
        df_lines.columns = [str(c).strip() for c in df_lines.columns]

        self.stdout.write(f"  Ventas: {len(df_sales)} filas")
        self.stdout.write(f"  Adiciones: {len(df_lines)} filas")

        # ── Validar columnas requeridas ──
        required_lines_cols = ["Id. Venta", "Producto", "Cantidad", "Precio", "Costo total", "Cancelada"]
        missing = [c for c in required_lines_cols if c not in df_lines.columns]
        if missing:
            raise CommandError(f"Columnas faltantes en '{sheet_lines}': {missing}\nColumnas encontradas: {list(df_lines.columns)}")

        # ── Construir mapa sale_id → fecha ──
        date_map = {}  # sale_id (int) → date_cls
        for _, row in df_sales.iterrows():
            sid = row.get("Id")
            fecha = row.get("Fecha")
            if pd.isna(sid) or pd.isna(fecha):
                continue
            try:
                if hasattr(fecha, "date"):
                    d = fecha.date()
                else:
                    d = pd.to_datetime(fecha).date()
                date_map[int(sid)] = d
            except Exception:
                continue

        if not date_map:
            raise CommandError("No se encontraron ventas con fechas válidas en la hoja de Ventas")

        self.stdout.write(f"  Rango de fechas: {min(date_map.values())} → {max(date_map.values())}")

        # ── Filtrar líneas canceladas ──
        df_lines = df_lines[df_lines["Cancelada"].astype(str).str.strip().str.lower() != "sí"]
        df_lines = df_lines[df_lines["Cancelada"].astype(str).str.strip().str.lower() != "si"]
        self.stdout.write(f"  Líneas válidas (sin canceladas): {len(df_lines)}")

        # ── Construir índice de productos por nombre ──
        products_qs = Product.objects.filter(tenant=tenant)
        product_map = {p.name.strip().lower(): p for p in products_qs}

        # ── Agregar por (date, product_name) ──
        # agg[date][product_name] = {qty, revenue, cost}
        agg: dict[date_cls, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {
            "qty": Decimal("0.000"),
            "revenue": Decimal("0.00"),
            "cost": Decimal("0.00"),
            "category": "",
        }))

        skipped_no_date = 0
        for _, row in df_lines.iterrows():
            sale_id_raw = row.get("Id. Venta")
            if pd.isna(sale_id_raw):
                skipped_no_date += 1
                continue
            try:
                sale_id = int(sale_id_raw)
            except (ValueError, TypeError):
                skipped_no_date += 1
                continue

            d = date_map.get(sale_id)
            if not d:
                skipped_no_date += 1
                continue

            product_name = str(row.get("Producto", "")).strip()
            if not product_name:
                continue

            try:
                qty = Decimal(str(row.get("Cantidad", 0)))
            except InvalidOperation:
                qty = Decimal("0")

            try:
                precio = Decimal(str(row.get("Precio", 0)))
            except InvalidOperation:
                precio = Decimal("0")

            try:
                costo = Decimal(str(row.get("Costo total", 0)))
            except InvalidOperation:
                costo = Decimal("0")

            categoria = str(row.get("Categoría", "")).strip()

            entry = agg[d][product_name]
            entry["qty"] += qty
            entry["revenue"] += qty * precio
            entry["cost"] += costo
            entry["category"] = categoria

        if skipped_no_date:
            self.stdout.write(self.style.WARNING(f"  {skipped_no_date} líneas sin fecha válida omitidas"))

        # ── Resolver productos / crear si se pide ──
        all_product_names = set(
            name for day_data in agg.values() for name in day_data.keys()
        )

        not_found = []
        to_create = []
        for name in sorted(all_product_names):
            if name.lower() not in product_map:
                not_found.append(name)

        if not_found:
            self.stdout.write(self.style.WARNING(
                f"\n  {len(not_found)} productos NO encontrados en el catálogo:"
            ))
            for n in not_found:
                self.stdout.write(f"    - {n}")

            if create_products and not dry_run:
                self._create_missing_products(
                    not_found, agg, tenant, product_map
                )
            elif not create_products:
                self.stdout.write(
                    self.style.WARNING(
                        "\n  Usa --create-products para crearlos automáticamente, "
                        "o créalos manualmente en el catálogo primero."
                    )
                )

        # ── Resumen previo ──
        total_rows = sum(len(day) for day in agg.values())
        self.stdout.write(f"\n  Total combinaciones fecha+producto: {total_rows}")
        self.stdout.write(f"  Días a importar: {len(agg)}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] No se guardó nada."))
            self._print_preview(agg, product_map)
            return

        # ── Guardar ──
        created = 0
        updated = 0
        skipped = 0

        with transaction.atomic():
            for d, day_data in sorted(agg.items()):
                for product_name, entry in day_data.items():
                    p = product_map.get(product_name.lower())
                    if not p:
                        skipped += 1
                        continue

                    revenue = entry["revenue"]
                    cost = entry["cost"]
                    qty = entry["qty"]

                    obj, was_created = DailySales.objects.update_or_create(
                        tenant=tenant,
                        product=p,
                        warehouse=warehouse,
                        date=d,
                        defaults={
                            "qty_sold":    qty,
                            "revenue":     revenue,
                            "total_cost":  cost,
                            "gross_profit": revenue - cost,
                            "qty_lost":    Decimal("0.000"),
                            "qty_received": Decimal("0.000"),
                            "promo_qty":   Decimal("0.000"),
                            "promo_revenue": Decimal("0.00"),
                            "forecast_only": True,
                        },
                    )
                    if was_created:
                        created += 1
                    else:
                        updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Importación completa: {created} creados, {updated} actualizados, {skipped} omitidos (producto no encontrado)"
        ))
        self.stdout.write(
            "\nPróximos pasos:\n"
            "  1. python manage.py compute_category_profiles --tenant {}\n"
            "  2. python manage.py train_forecast_models --tenant {}\n"
            "  3. python manage.py generate_purchase_suggestions --tenant {}".format(
                tenant_id, tenant_id, tenant_id
            )
        )

    def _create_missing_products(self, names, agg, tenant, product_map):
        """Crea productos faltantes con categoría inferida del Excel."""
        from catalog.models import Product, Category

        # Intentar inferir categoría de cada producto
        name_to_category = {}
        for day_data in agg.values():
            for name, entry in day_data.items():
                if name in names and entry.get("category"):
                    name_to_category[name] = entry["category"]

        for name in names:
            cat_name = name_to_category.get(name, "Sin categoría")
            cat, _ = Category.objects.get_or_create(
                tenant=tenant,
                name=cat_name,
                defaults={"is_active": True},
            )
            p = Product.objects.create(
                tenant=tenant,
                name=name,
                category=cat,
                price=Decimal("0.00"),
                cost=Decimal("0.00"),
                is_active=True,
            )
            product_map[name.lower()] = p
            self.stdout.write(self.style.SUCCESS(f"  ✓ Producto creado: {name} (cat: {cat_name})"))

    def _print_preview(self, agg, product_map):
        """Muestra resumen de lo que se importaría."""
        self.stdout.write("\n--- PREVIEW ---")
        for d in sorted(agg.keys()):
            self.stdout.write(f"\n{d}:")
            for name, entry in sorted(agg[d].items()):
                found = "✓" if name.lower() in product_map else "✗ NO ENCONTRADO"
                self.stdout.write(
                    f"  {found} {name}: qty={entry['qty']} revenue={entry['revenue']} cost={entry['cost']}"
                )
