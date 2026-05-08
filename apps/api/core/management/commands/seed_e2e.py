"""
Seeder E2E aislado — crea/limpia un tenant dedicado para Playwright tests.

USO LOCAL (dev):
    python manage.py seed_e2e          # crea tenant + user + productos + caja
    python manage.py seed_e2e --cleanup # borra TODO lo que el seeder creó

GARANTÍAS DE SEGURIDAD:
  - Tenant aislado con slug='e2e-test' — NUNCA toca tenant de Mario.
  - Idempotente: corrérlo dos veces no duplica datos.
  - Cleanup borra solo lo que tiene tenant.slug='e2e-test'.
  - NO correr en producción salvo que el operador entienda lo que hace.
    Si DEBUG=False, requiere --i-know-this-is-prod para ejecutar.

¿Por qué un management command y no fixtures?
  Los modelos de Pulstock tienen muchas FKs y signals (ej: el signal que
  crea MovementCategory al crear Tenant). Un script imperativo es más
  legible y mantenible que fixtures.json estáticos.
"""
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Tenant, User, Warehouse
from stores.models import Store
from catalog.models import Product
from caja.models import CashRegister


E2E_SLUG = "e2e-test"
E2E_USER = "e2e_test"
E2E_PASS = "E2eTest2026!"


class Command(BaseCommand):
    help = "Sembrar/limpiar tenant aislado para Playwright E2E tests."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cleanup", action="store_true",
            help="Borrar todo lo que el seeder creó (tenant entero).",
        )
        parser.add_argument(
            "--i-know-this-is-prod", action="store_true",
            help="Confirmación explícita para correr con DEBUG=False.",
        )

    def handle(self, *args, **opts):
        # Guardrail anti-accidente: si DEBUG=False, requerimos flag explícita
        if not settings.DEBUG and not opts["i_know_this_is_prod"]:
            raise CommandError(
                "DEBUG=False (probablemente producción). Si REALMENTE querés correr "
                "el seeder E2E, agregá --i-know-this-is-prod. Igual va a crear un "
                "tenant aislado (slug=e2e-test), pero confirma que sabés lo que hacés."
            )

        if opts["cleanup"]:
            self._cleanup()
        else:
            self._seed()

    @transaction.atomic
    def _seed(self):
        # 1. Tenant aislado
        tenant, created = Tenant.objects.get_or_create(
            slug=E2E_SLUG,
            defaults={"name": "E2E Test Tenant"},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"[OK] Tenant creado: {tenant.name} (id={tenant.id})"))
        else:
            self.stdout.write(f"  Tenant ya existía: {tenant.name} (id={tenant.id})")

        # 2. Store + warehouse
        store, _ = Store.objects.get_or_create(
            tenant=tenant, name="E2E Local",
            defaults={"is_active": True},
        )
        warehouse, _ = Warehouse.objects.get_or_create(
            tenant=tenant, store=store, name="E2E Bodega",
        )

        # 3. Usuario E2E
        user, user_created = User.objects.get_or_create(
            username=E2E_USER,
            defaults={
                "email": "e2e@test.local",
                "tenant": tenant,
                "active_store": store,
                "role": User.Role.OWNER,
                "first_name": "E2E",
                "last_name": "Tester",
            },
        )
        # Asegurar password siempre — útil si el user existe pero no se sabe la pass
        user.set_password(E2E_PASS)
        user.tenant = tenant
        user.active_store = store
        user.role = User.Role.OWNER
        user.is_active = True
        user.save()
        if user_created:
            self.stdout.write(self.style.SUCCESS(f"[OK] Usuario creado: {user.username}"))

        # 4. Productos de prueba
        products_data = [
            ("E2E-LATTE", "Latte E2E", Decimal("3000")),
            ("E2E-BROWNIE", "Brownie E2E", Decimal("1500")),
            ("E2E-CAPPUCCINO", "Cappuccino E2E", Decimal("3500")),
        ]
        for sku, name, price in products_data:
            Product.objects.update_or_create(
                tenant=tenant, sku=sku,
                defaults={"name": name, "price": price, "is_active": True},
            )
        self.stdout.write(f"[OK] {len(products_data)} productos sembrados")

        # 5. CashRegister
        register, _ = CashRegister.objects.get_or_create(
            tenant=tenant, store=store, name="E2E Caja",
            defaults={"is_active": True},
        )

        # 6. Subscription activa para que SubscriptionAccessMiddleware no bloquee.
        try:
            from billing.models import Plan, Subscription
            plan, _ = Plan.objects.get_or_create(
                key="pro",
                defaults={
                    "name": "Plan Pro", "price_clp": 59990,
                    "max_products": -1, "max_stores": -1, "max_users": -1,
                    "has_forecast": True, "has_abc": True,
                    "has_reports": True, "has_transfers": True,
                },
            )
            now = timezone.now()
            Subscription.objects.update_or_create(
                tenant=tenant,
                defaults={
                    "plan": plan,
                    "status": "active",
                    "current_period_start": now,
                    "current_period_end": now + timezone.timedelta(days=365),
                },
            )
            self.stdout.write("[OK] Suscripción activa configurada")
        except ImportError:
            self.stdout.write(self.style.WARNING("billing module no disponible — skip"))

        self.stdout.write(self.style.SUCCESS(
            f"\n[OK] Seed E2E completo. Login con: {E2E_USER} / {E2E_PASS}"
        ))

    @transaction.atomic
    def _cleanup(self):
        try:
            tenant = Tenant.objects.get(slug=E2E_SLUG)
        except Tenant.DoesNotExist:
            self.stdout.write("  Nada que limpiar — tenant E2E no existe.")
            return

        # Cleanup ordenado: primero las cosas que apuntan al tenant,
        # después el tenant. Algunos modelos usan PROTECT así que hay
        # que borrarlos a mano antes.
        from caja.models import CashSession, CashMovement, MovementCategory, CashRegister
        from sales.models import Sale, SaleLine, SalePayment, SaleTip
        from inventory.models import StockItem, StockMove
        from promotions.models import Promotion, PromotionProduct
        from tables.models import Table, OpenOrder, OpenOrderLine

        deleted_count = 0

        # Sales y sus dependientes
        sales = Sale.objects.filter(tenant=tenant)
        for s in sales:
            SaleLine.objects.filter(sale=s).delete()
            SalePayment.objects.filter(sale=s).delete()
            SaleTip.objects.filter(sale=s).delete()
        deleted_count += sales.count(); sales.delete()

        # Caja
        for s in CashSession.objects.filter(tenant=tenant):
            CashMovement.objects.filter(session=s).delete()
        deleted_count += CashSession.objects.filter(tenant=tenant).count()
        CashSession.objects.filter(tenant=tenant).delete()
        CashRegister.objects.filter(tenant=tenant).delete()
        MovementCategory.objects.filter(tenant=tenant).delete()

        # Mesas
        for o in OpenOrder.objects.filter(tenant=tenant):
            OpenOrderLine.objects.filter(order=o).delete()
        OpenOrder.objects.filter(tenant=tenant).delete()
        Table.objects.filter(tenant=tenant).delete()

        # Promociones
        for p in Promotion.objects.filter(tenant=tenant):
            PromotionProduct.objects.filter(promotion=p).delete()
        Promotion.objects.filter(tenant=tenant).delete()

        # Inventario
        for si in StockItem.objects.filter(tenant=tenant):
            StockMove.objects.filter(stock_item=si).delete()
        StockItem.objects.filter(tenant=tenant).delete()

        # Catálogo (use all_objects para incluir soft-deleted)
        Product.all_objects.filter(tenant=tenant).delete()

        # Subscription
        try:
            from billing.models import Subscription
            Subscription.objects.filter(tenant=tenant).delete()
        except ImportError:
            pass

        # Users del tenant — primero null'eamos active_store y default_warehouse
        # del user para evitar PROTECT al borrar Store/Warehouse después.
        User.objects.filter(tenant=tenant).update(active_store=None)
        User.objects.filter(tenant=tenant).delete()

        # Antes de borrar Warehouse, hay que romper el FK Tenant.default_warehouse
        # (PROTECT). Mismo patrón con default_store si existe.
        if hasattr(tenant, "default_warehouse_id"):
            Tenant.objects.filter(pk=tenant.pk).update(default_warehouse=None)
        if hasattr(tenant, "default_store_id"):
            Tenant.objects.filter(pk=tenant.pk).update(default_store=None)
        Warehouse.objects.filter(tenant=tenant).delete()
        Store.objects.filter(tenant=tenant).delete()

        tenant_name = tenant.name
        tenant.delete()

        self.stdout.write(self.style.SUCCESS(
            f"[OK] Cleanup completo: tenant '{tenant_name}' y todo su contenido borrado."
        ))
