"""
import_historical_sales
=======================
Importa ventas históricas desde Excel del POS (formato Ventas + Adiciones)
directamente a DailySales con forecast_only=True — sin tocar stock.

El modelo de forecast usa estos datos igual que los reales.

Uso:
    # Un archivo:
    python manage.py import_historical_sales \
        --file ventas.xls --tenant 1 --warehouse 1

    # Múltiples archivos de una vez:
    python manage.py import_historical_sales \
        --file febrero.xls marzo.xls --tenant 1 --warehouse 1

    # Vista previa sin guardar:
    python manage.py import_historical_sales \
        --file ventas.xls --tenant 1 --warehouse 1 --dry-run

    # Crear productos que no existen en el catálogo:
    python manage.py import_historical_sales \
        --file ventas.xls --tenant 1 --warehouse 1 --create-products
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
        parser.add_argument(
            "--file", required=True, nargs="+",
            help="Ruta(s) al archivo Excel (.xls o .xlsx). Acepta varios archivos.",
        )
        parser.add_argument("--tenant",    required=True, type=int, help="ID del tenant")
        parser.add_argument("--warehouse", required=True, type=int, help="ID de la bodega")
        parser.add_argument("--dry-run",   action="store_true", help="Vista previa sin guardar")
        parser.add_argument(
            "--create-products", action="store_true",
            help="Crear productos que no existen en el catálogo",
        )
        parser.add_argument("--sheet-sales", default="Ventas",    help="Nombre hoja de ventas")
        parser.add_argument("--sheet-lines", default="Adiciones", help="Nombre hoja de líneas")

    def handle(self, *args, **options):
        tenant_id    = options["tenant"]
        warehouse_id = options["warehouse"]

        from core.models import Tenant, Warehouse

        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            raise CommandError(f"Tenant {tenant_id} no existe")

        try:
            warehouse = Warehouse.objects.get(pk=warehouse_id, tenant=tenant)
        except Warehouse.DoesNotExist:
            raise CommandError(f"Bodega {warehouse_id} no existe o no pertenece al tenant")

        filepaths   = options["file"]
        dry_run     = options["dry_run"]
        create_prods = options["create_products"]

        total_created = total_updated = total_skipped = 0

        for filepath in filepaths:
            self.stdout.write(f"\n{'='*60}")
            created, updated, skipped = self._process_file(
                filepath, tenant, warehouse, dry_run, create_prods, options,
            )
            total_created += created
            total_updated += updated
            total_skipped += skipped

        self.stdout.write(f"\n{'='*60}")
        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] Nada fue guardado."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"TOTAL: {total_created} creados, "
                f"{total_updated} actualizados, {total_skipped} omitidos"
            ))
            self.stdout.write(
                f"\nPróximos pasos:\n"
                f"  1. python manage.py compute_category_profiles --tenant {tenant_id}\n"
                f"  2. python manage.py train_forecast_models --tenant {tenant_id}\n"
                f"  3. python manage.py generate_purchase_suggestions --tenant {tenant_id}"
            )

    # ------------------------------------------------------------------

    def _process_file(self, filepath, tenant, warehouse, dry_run, create_products, options):
        """Procesa un archivo Excel. Retorna (created, updated, skipped)."""
        try:
            import pandas as pd
        except ImportError:
            raise CommandError("Instala pandas: pip install pandas openpyxl xlrd")

        from catalog.models import Product
        from forecast.models import DailySales

        self.stdout.write(f"Leyendo {filepath}...")
        try:
            xl = pd.ExcelFile(filepath)
        except Exception as e:
            raise CommandError(f"No se pudo abrir el archivo: {e}")

        sheet_sales = options["sheet_sales"]
        sheet_lines = options["sheet_lines"]

        if sheet_sales not in xl.sheet_names:
            raise CommandError(f"Hoja '{sheet_sales}' no encontrada. Hojas disponibles: {xl.sheet_names}")
        if sheet_lines not in xl.sheet_names:
            raise CommandError(f"Hoja '{sheet_lines}' no encontrada. Hojas disponibles: {xl.sheet_names}")

        # La hoja "Ventas" tiene 3 filas de metadatos al inicio
        df_sales = xl.parse(sheet_sales, skiprows=3, header=0)
        df_lines = xl.parse(sheet_lines)

        df_sales.columns = [str(c).strip() for c in df_sales.columns]
        df_lines.columns = [str(c).strip() for c in df_lines.columns]

        self.stdout.write(f"  Ventas: {len(df_sales)} filas | Adiciones: {len(df_lines)} filas")

        # Validar columnas requeridas
        required = ["Id. Venta", "Producto", "Cantidad", "Precio", "Costo total", "Cancelada"]
        missing  = [c for c in required if c not in df_lines.columns]
        if missing:
            raise CommandError(
                f"Columnas faltantes en '{sheet_lines}': {missing}\n"
                f"Columnas encontradas: {list(df_lines.columns)}"
            )

        # Construir mapa sale_id → fecha
        date_map: dict[int, date_cls] = {}
        for _, row in df_sales.iterrows():
            sid   = row.get("Id")
            fecha = row.get("Fecha")
            if pd.isna(sid) or pd.isna(fecha):
                continue
            try:
                d = fecha.date() if hasattr(fecha, "date") else pd.to_datetime(fecha).date()
                date_map[int(sid)] = d
            except Exception:
                continue

        if not date_map:
            raise CommandError("No se encontraron ventas con fechas válidas")

        self.stdout.write(
            f"  Rango de fechas: {min(date_map.values())} → {max(date_map.values())} "
            f"({len(date_map)} ventas)"
        )

        # Filtrar canceladas
        cancelada_col = df_lines["Cancelada"].astype(str).str.strip().str.lower()
        df_lines = df_lines[~cancelada_col.isin(["sí", "si", "yes", "true", "1"])]
        self.stdout.write(f"  Líneas válidas (sin canceladas): {len(df_lines)}")

        # Índice de productos existentes
        product_map = {p.name.strip().lower(): p for p in Product.objects.filter(tenant=tenant)}

        # Agregar por (date, product_name)
        agg: dict[date_cls, dict[str, dict]] = defaultdict(
            lambda: defaultdict(lambda: {
                "qty": Decimal("0.000"),
                "revenue": Decimal("0.00"),
                "cost": Decimal("0.00"),
                "category": "",
            })
        )

        skipped_no_date = 0
        for _, row in df_lines.iterrows():
            raw_id = row.get("Id. Venta")
            if pd.isna(raw_id):
                skipped_no_date += 1
                continue
            try:
                sale_id = int(raw_id)
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
                qty    = Decimal(str(row.get("Cantidad", 0)))
                precio = Decimal(str(row.get("Precio", 0)))
                costo  = Decimal(str(row.get("Costo total", 0)))
            except InvalidOperation:
                continue

            categoria = str(row.get("Categoría", "")).strip()
            entry = agg[d][product_name]
            entry["qty"]      += qty
            entry["revenue"]  += qty * precio
            entry["cost"]     += costo
            entry["category"]  = entry["category"] or categoria

        if skipped_no_date:
            self.stdout.write(self.style.WARNING(
                f"  {skipped_no_date} líneas sin venta origen omitidas"
            ))

        # Detectar productos no encontrados
        all_names = {name for day in agg.values() for name in day}
        not_found = sorted(n for n in all_names if n.lower() not in product_map)

        if not_found:
            self.stdout.write(self.style.WARNING(
                f"\n  {len(not_found)} productos NO encontrados en el catálogo:"
            ))
            for n in not_found:
                self.stdout.write(f"    ✗ {n}")

            if create_products and not dry_run:
                self._create_missing_products(not_found, agg, tenant, product_map)
            else:
                self.stdout.write(self.style.WARNING(
                    "  → Usa --create-products para crearlos automáticamente."
                ))

        total_combos = sum(len(day) for day in agg.values())
        self.stdout.write(
            f"\n  {total_combos} combinaciones fecha+producto en {len(agg)} días"
        )

        if dry_run:
            self._print_preview(agg, product_map)
            return 0, 0, 0

        # Guardar
        created = updated = skipped = 0

        with transaction.atomic():
            for d, day_data in sorted(agg.items()):
                for product_name, entry in day_data.items():
                    p = product_map.get(product_name.lower())
                    if not p:
                        skipped += 1
                        continue

                    revenue = entry["revenue"]
                    cost    = entry["cost"]
                    qty     = entry["qty"]

                    _, was_created = DailySales.objects.update_or_create(
                        tenant=tenant,
                        product=p,
                        warehouse=warehouse,
                        date=d,
                        defaults={
                            "qty_sold":      qty,
                            "revenue":       revenue,
                            "total_cost":    cost,
                            "gross_profit":  revenue - cost,
                            "qty_lost":      Decimal("0.000"),
                            "qty_received":  Decimal("0.000"),
                            "promo_qty":     Decimal("0.000"),
                            "promo_revenue": Decimal("0.00"),
                            "forecast_only": True,
                        },
                    )
                    if was_created:
                        created += 1
                    else:
                        updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"  ✓ {created} creados, {updated} actualizados, {skipped} omitidos"
        ))
        return created, updated, skipped

    # ------------------------------------------------------------------

    def _create_missing_products(self, names, agg, tenant, product_map):
        """Crea productos faltantes con categoría inferida del Excel."""
        from catalog.models import Product, Category

        name_to_cat = {}
        for day_data in agg.values():
            for name, entry in day_data.items():
                if name in names and entry.get("category"):
                    name_to_cat[name] = entry["category"]

        for name in names:
            cat_name = name_to_cat.get(name, "Sin categoría")
            cat, _ = Category.objects.get_or_create(
                tenant=tenant, name=cat_name,
                defaults={"is_active": True},
            )
            p = Product.objects.create(
                tenant=tenant, name=name, category=cat,
                price=Decimal("0.00"), cost=Decimal("0.00"),
                is_active=True,
            )
            product_map[name.lower()] = p
            self.stdout.write(self.style.SUCCESS(f"  ✓ Producto creado: {name} [{cat_name}]"))

    def _print_preview(self, agg, product_map):
        self.stdout.write("\n--- PREVIEW ---")
        for d in sorted(agg.keys()):
            self.stdout.write(f"\n{d}:")
            for name, entry in sorted(agg[d].items()):
                estado = "✓" if name.lower() in product_map else "✗ NO ENCONTRADO"
                self.stdout.write(
                    f"  {estado:20} {name}: qty={entry['qty']} "
                    f"revenue={entry['revenue']} cost={entry['cost']}"
                )
