"""
superadmin/views.py
===================
Panel de superadministración de la plataforma Pulstock.
Todos los endpoints requieren is_superuser=True.
"""

from api.utils import safe_int
from django.db import models, transaction
from django.db.models import Count, Sum, Q, F, Avg, FloatField
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import TruncDate, TruncMonth, Cast
from django.utils import timezone
from django.shortcuts import get_object_or_404
from datetime import timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from core.models import Tenant, User
from core.permissions import IsSuperAdmin
from billing.models import Plan, Subscription, Invoice
from stores.models import Store

import logging
logger = logging.getLogger(__name__)

PERMS = [IsAuthenticated, IsSuperAdmin]


# ─────────────────────────────────────────────────────────────
# DASHBOARD KPIs
# ─────────────────────────────────────────────────────────────
class PlatformStatsView(APIView):
    """KPIs globales de la plataforma."""
    permission_classes = PERMS

    def get(self, request):
        now = timezone.now()
        month_ago = now - timedelta(days=30)

        total_tenants = Tenant.objects.count()
        active_tenants = Tenant.objects.filter(is_active=True).count()
        total_users = User.objects.filter(is_active=True, is_superuser=False).count()
        total_stores = Store.objects.filter(is_active=True).count()

        # Suscripciones por estado
        sub_stats = dict(
            Subscription.objects.values_list("status")
            .annotate(c=Count("id"))
            .values_list("status", "c")
        )

        # Ingresos últimos 30 días
        revenue_30d = Invoice.objects.filter(
            status=Invoice.Status.PAID,
            paid_at__gte=month_ago,
        ).aggregate(total=Sum("amount_clp"))["total"] or 0

        # Ingresos totales
        revenue_total = Invoice.objects.filter(
            status=Invoice.Status.PAID,
        ).aggregate(total=Sum("amount_clp"))["total"] or 0

        # Tenants nuevos últimos 30 días
        new_tenants_30d = Tenant.objects.filter(created_at__gte=month_ago).count()

        # MRR (Monthly Recurring Revenue)
        mrr = Subscription.objects.filter(
            status__in=["active", "trialing", "past_due"],
        ).aggregate(
            mrr=Sum("plan__price_clp")
        )["mrr"] or 0

        # Tenants con pagos pendientes
        past_due = Subscription.objects.filter(status="past_due").count()
        suspended = Subscription.objects.filter(status="suspended").count()

        # Distribución por plan
        plan_dist = list(
            Subscription.objects.filter(
                status__in=["active", "trialing", "past_due"],
            ).values(
                plan_name=F("plan__name"),
                plan_key=F("plan__key"),
            ).annotate(count=Count("id")).order_by("-count")
        )

        return Response({
            "total_tenants": total_tenants,
            "active_tenants": active_tenants,
            "new_tenants_30d": new_tenants_30d,
            "total_users": total_users,
            "total_stores": total_stores,
            "subscription_stats": sub_stats,
            "revenue_30d": revenue_30d,
            "revenue_total": revenue_total,
            "mrr": mrr,
            "past_due": past_due,
            "suspended": suspended,
            "plan_distribution": plan_dist,
        })


# ─────────────────────────────────────────────────────────────
# REVENUE CHART (últimos 12 meses)
# ─────────────────────────────────────────────────────────────
class RevenueChartView(APIView):
    permission_classes = PERMS

    def get(self, request):
        months = safe_int(request.query_params.get("months"), 12)
        since = timezone.now() - timedelta(days=months * 30)

        data = list(
            Invoice.objects.filter(
                status=Invoice.Status.PAID,
                paid_at__gte=since,
            ).annotate(
                month=TruncMonth("paid_at")
            ).values("month").annotate(
                total=Sum("amount_clp"),
                count=Count("id"),
            ).order_by("month")
        )

        for d in data:
            d["month"] = d["month"].strftime("%Y-%m")

        return Response(data)


# ─────────────────────────────────────────────────────────────
# TENANT LIST + DETAIL
# ─────────────────────────────────────────────────────────────
class TenantListView(APIView):
    permission_classes = PERMS

    def get(self, request):
        qs = Tenant.objects.all().order_by("-created_at")

        # Filtros
        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q) | Q(email__icontains=q))

        status_filter = request.query_params.get("status")
        if status_filter == "active":
            qs = qs.filter(is_active=True)
        elif status_filter == "inactive":
            qs = qs.filter(is_active=False)

        plan_filter = request.query_params.get("plan")
        if plan_filter:
            qs = qs.filter(subscription__plan__key=plan_filter)

        sub_status = request.query_params.get("sub_status")
        if sub_status:
            qs = qs.filter(subscription__status=sub_status)

        # Annotate
        qs = qs.annotate(
            user_count=Count("users", filter=Q(users__is_active=True, users__is_superuser=False)),
            store_count=Count("stores", filter=Q(stores__is_active=True), distinct=True),
        )

        # Paginación simple
        page = safe_int(request.query_params.get("page"), 1)
        page_size = safe_int(request.query_params.get("page_size"), 25)
        total = qs.count()
        offset = (page - 1) * page_size
        tenants = qs[offset:offset + page_size]

        results = []
        # Prefetch subscriptions
        tenant_ids = [t.id for t in tenants]
        subs = {
            s.tenant_id: s
            for s in Subscription.objects.filter(tenant_id__in=tenant_ids).select_related("plan")
        }

        for t in tenants:
            sub = subs.get(t.id)
            results.append({
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "email": t.email,
                "business_type": getattr(t, "business_type", "other") or "other",
                "is_active": t.is_active,
                "created_at": t.created_at.isoformat(),
                "user_count": t.user_count,
                "store_count": t.store_count,
                "subscription": {
                    "status": sub.status if sub else None,
                    "plan_name": sub.plan.name if sub else None,
                    "plan_key": sub.plan.key if sub else None,
                    "price_clp": sub.plan.price_clp if sub else 0,
                    "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
                    "has_card": bool(sub.card_last4) if sub else False,
                } if sub else None,
            })

        return Response({
            "results": results,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        })


class TenantDetailView(APIView):
    permission_classes = PERMS

    def get(self, request, tenant_id):
        t = get_object_or_404(Tenant, pk=tenant_id)

        users = list(
            User.objects.filter(tenant=t, is_superuser=False).values(
                "id", "username", "email", "first_name", "last_name",
                "role", "is_active", "last_login", "date_joined",
            ).order_by("-date_joined")
        )

        stores = list(
            Store.objects.filter(tenant=t).values(
                "id", "name", "is_active",
            )
        )

        sub = None
        try:
            s = Subscription.objects.select_related("plan").get(tenant=t)
            sub = {
                "id": s.id,
                "status": s.status,
                "plan_key": s.plan.key,
                "plan_name": s.plan.name,
                "price_clp": s.plan.price_clp,
                "trial_ends_at": s.trial_ends_at.isoformat() if s.trial_ends_at else None,
                "current_period_start": s.current_period_start.isoformat() if s.current_period_start else None,
                "current_period_end": s.current_period_end.isoformat() if s.current_period_end else None,
                "has_card": bool(s.card_last4),
                "card_brand": s.card_brand,
                "card_last4": s.card_last4,
                "payment_retry_count": s.payment_retry_count,
            }
        except Subscription.DoesNotExist:
            pass

        invoices = list(
            Invoice.objects.filter(subscription__tenant=t).values(
                "id", "status", "amount_clp", "period_start", "period_end",
                "paid_at", "created_at",
            ).order_by("-created_at")[:20]
        )

        # Conteos rápidos
        from catalog.models import Product
        from sales.models import Sale
        product_count = Product.objects.filter(tenant=t).count()
        sale_count = Sale.objects.filter(tenant=t).count()

        return Response({
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "email": t.email,
            "phone": t.phone,
            "rut": t.rut,
            "legal_name": t.legal_name,
            "business_type": getattr(t, "business_type", "other") or "other",
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat(),
            "users": users,
            "stores": stores,
            "subscription": sub,
            "invoices": invoices,
            "stats": {
                "products": product_count,
                "sales": sale_count,
            },
        })

    def patch(self, request, tenant_id):
        """Modificar tenant (activar/desactivar, etc.)."""
        t = get_object_or_404(Tenant, pk=tenant_id)
        changed = []

        if "is_active" in request.data:
            t.is_active = bool(request.data["is_active"])
            changed.append("is_active")

        if "name" in request.data:
            t.name = request.data["name"]
            changed.append("name")

        if "business_type" in request.data:
            valid_types = [c[0] for c in Tenant.BUSINESS_TYPE_CHOICES]
            bt = request.data["business_type"]
            if bt in valid_types:
                t.business_type = bt
                changed.append("business_type")

        if changed:
            t.save(update_fields=changed)
            logger.info("Superadmin %s updated tenant %d: %s", request.user.email, t.id, changed)

        return Response({"ok": True, "id": t.id, "is_active": t.is_active, "name": t.name})

    def delete(self, request, tenant_id):
        """Eliminar tenant y todos sus datos asociados (orden respeta PROTECT FKs)."""
        from sales.models import Sale, SaleLine, SalePayment
        from purchases.models import Purchase, PurchaseLine, PurchaseInvoiceLine, Supplier
        from inventory.models import StockItem, StockMove, StockTransfer, StockTransferLine
        from catalog.models import Barcode, RecipeLine, Recipe, Product, Category, Unit
        from forecast.models import (
            SuggestionOutcome, ForecastAccuracy, SuggestionLine,
            PurchaseSuggestion, Forecast, ForecastModel, CategoryDemandProfile,
            DailySales, Holiday,
        )
        from tables.models import OpenOrderLine, OpenOrder, Table
        from caja.models import CashMovement, CashSession, CashRegister
        from billing.models import CheckoutSession, Invoice, PaymentAttempt, Subscription
        from stores.models import Store
        from core.models import Warehouse

        t = get_object_or_404(Tenant, pk=tenant_id)
        tenant_name = t.name
        user_count = User.objects.filter(tenant=t).count()

        with transaction.atomic():
            # Null out PROTECT FKs that would block deletion
            Tenant.objects.filter(pk=t.pk).update(default_warehouse=None)

            # Delete in dependency order (leaves before branches)
            SalePayment.objects.filter(tenant=t).delete()
            SaleLine.objects.filter(tenant=t).delete()
            Sale.objects.filter(tenant=t).delete()
            OpenOrderLine.objects.filter(tenant=t).delete()
            OpenOrder.objects.filter(tenant=t).delete()
            Table.objects.filter(tenant=t).delete()
            CashMovement.objects.filter(tenant=t).delete()
            CashSession.objects.filter(tenant=t).delete()
            CashRegister.objects.filter(tenant=t).delete()
            PurchaseInvoiceLine.objects.filter(tenant=t).delete()
            PurchaseLine.objects.filter(tenant=t).delete()
            Purchase.objects.filter(tenant=t).delete()
            Supplier.objects.filter(tenant=t).delete()
            SuggestionOutcome.objects.filter(tenant=t).delete()
            ForecastAccuracy.objects.filter(tenant=t).delete()
            SuggestionLine.objects.filter(suggestion__tenant=t).delete()
            PurchaseSuggestion.objects.filter(tenant=t).delete()
            Forecast.objects.filter(tenant=t).delete()
            ForecastModel.objects.filter(tenant=t).delete()
            CategoryDemandProfile.objects.filter(tenant=t).delete()
            Holiday.objects.filter(tenant=t).delete()
            DailySales.objects.filter(tenant=t).delete()
            StockTransferLine.objects.filter(tenant=t).delete()
            StockTransfer.objects.filter(tenant=t).delete()
            StockMove.objects.filter(tenant=t).delete()
            StockItem.objects.filter(tenant=t).delete()
            Barcode.objects.filter(tenant=t).delete()
            RecipeLine.objects.filter(tenant=t).delete()
            Recipe.objects.filter(tenant=t).delete()
            Product.objects.filter(tenant=t).delete()
            Category.objects.filter(tenant=t).update(parent=None)
            Category.objects.filter(tenant=t).delete()
            Unit.objects.filter(tenant=t).delete()
            PaymentAttempt.objects.filter(invoice__subscription__tenant=t).delete()
            CheckoutSession.objects.filter(tenant=t).delete()
            Invoice.objects.filter(subscription__tenant=t).delete()
            Subscription.objects.filter(tenant=t).delete()
            # Null active_store for any user referencing this tenant's stores
            User.objects.filter(active_store__tenant=t).update(active_store=None)
            Warehouse.objects.filter(tenant=t).delete()
            Store.objects.filter(tenant=t).delete()
            User.objects.filter(tenant=t).delete()
            t.refresh_from_db()
            t.delete()

        logger.info(
            "Superadmin %s deleted tenant %d (%s) with %d users",
            request.user.email, tenant_id, tenant_name, user_count,
        )
        return Response({"ok": True, "deleted": tenant_name, "users_deleted": user_count})


# ─────────────────────────────────────────────────────────────
# SUBSCRIPTION MANAGEMENT
# ─────────────────────────────────────────────────────────────
class AdminSubscriptionView(APIView):
    """Cambiar plan o estado de suscripción de un tenant."""
    permission_classes = PERMS

    def patch(self, request, tenant_id):
        sub = get_object_or_404(Subscription.objects.select_related("plan"), tenant_id=tenant_id)
        changed = []

        # Cambiar plan
        new_plan_key = request.data.get("plan_key")
        if new_plan_key and new_plan_key != sub.plan.key:
            try:
                new_plan = Plan.objects.get(key=new_plan_key, is_active=True)
                sub.plan = new_plan
                changed.append("plan")
                logger.info(
                    "Superadmin %s changed tenant %d plan to %s",
                    request.user.email, tenant_id, new_plan_key,
                )
            except Plan.DoesNotExist:
                return Response({"detail": f"Plan '{new_plan_key}' no encontrado."}, status=400)

        # Cambiar estado
        new_status = request.data.get("status")
        if new_status and new_status != sub.status:
            valid = [c[0] for c in Subscription.Status.choices]
            if new_status not in valid:
                return Response({"detail": f"Estado inválido: {new_status}"}, status=400)
            sub.status = new_status
            changed.append("status")
            if new_status == "suspended":
                sub.suspended_at = timezone.now()
                changed.append("suspended_at")
            elif new_status == "active":
                sub.suspended_at = None
                sub.payment_retry_count = 0
                changed.extend(["suspended_at", "payment_retry_count"])
            logger.info(
                "Superadmin %s changed tenant %d status to %s",
                request.user.email, tenant_id, new_status,
            )

        # Extender período
        extend_days = request.data.get("extend_days")
        if extend_days:
            days = safe_int(extend_days, 0)
            if sub.current_period_end:
                sub.current_period_end += timedelta(days=days)
            else:
                sub.current_period_end = timezone.now() + timedelta(days=days)
            changed.append("current_period_end")
            logger.info(
                "Superadmin %s extended tenant %d period by %d days",
                request.user.email, tenant_id, days,
            )

        if changed:
            sub.save(update_fields=list(set(changed)))

        return Response({
            "ok": True,
            "status": sub.status,
            "plan": sub.plan.key,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        })


# ─────────────────────────────────────────────────────────────
# USER MANAGEMENT
# ─────────────────────────────────────────────────────────────
class AdminUserListView(APIView):
    """Lista todos los usuarios de la plataforma."""
    permission_classes = PERMS

    def get(self, request):
        qs = User.objects.filter(is_superuser=False).select_related("tenant").order_by("-date_joined")

        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(email__icontains=q) | Q(username__icontains=q) |
                Q(first_name__icontains=q) | Q(last_name__icontains=q)
            )

        role = request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)

        active = request.query_params.get("active")
        if active == "true":
            qs = qs.filter(is_active=True)
        elif active == "false":
            qs = qs.filter(is_active=False)

        tenant_id = request.query_params.get("tenant_id")
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)

        page = safe_int(request.query_params.get("page"), 1)
        page_size = safe_int(request.query_params.get("page_size"), 25)
        total = qs.count()
        offset = (page - 1) * page_size

        users = []
        for u in qs[offset:offset + page_size]:
            users.append({
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "role": u.role,
                "is_active": u.is_active,
                "tenant_id": u.tenant_id,
                "tenant_name": u.tenant.name if u.tenant else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "date_joined": u.date_joined.isoformat(),
            })

        return Response({
            "results": users,
            "total": total,
            "page": page,
            "page_size": page_size,
        })


class AdminUserCreateView(APIView):
    """Crear usuario desde superadmin."""
    permission_classes = PERMS

    def post(self, request):
        email = request.data.get("email", "").strip()
        password = request.data.get("password", "").strip()
        first_name = request.data.get("first_name", "").strip()
        last_name = request.data.get("last_name", "").strip()
        role = request.data.get("role", "owner")
        tenant_id = request.data.get("tenant_id")

        if not email or not password:
            return Response({"detail": "Email y contraseña son requeridos."}, status=400)

        if not tenant_id:
            return Response({"detail": "Debes asignar un negocio (tenant) al usuario."}, status=400)

        if User.objects.filter(email=email).exists():
            return Response({"detail": "Ya existe un usuario con ese email."}, status=400)

        if User.objects.filter(username=email).exists():
            return Response({"detail": "Ya existe un usuario con ese nombre de usuario."}, status=400)

        tenant = get_object_or_404(Tenant, pk=tenant_id)

        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=role,
                tenant=tenant,
            )
        except Exception:
            return Response({"detail": "Error al crear el usuario. Verifica que los datos no estén duplicados."}, status=400)

        logger.info("Superadmin %s created user %s (tenant=%s)", request.user.email, email, tenant_id)

        return Response({
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "tenant_id": user.tenant_id,
        }, status=201)


class AdminUserToggleView(APIView):
    """Activar/desactivar usuario."""
    permission_classes = PERMS

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id, is_superuser=False)
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        action = "activated" if user.is_active else "deactivated"
        logger.info("Superadmin %s %s user %d", request.user.email, action, user_id)
        return Response({"ok": True, "is_active": user.is_active})


class AdminUserDeleteView(APIView):
    """Eliminar usuario permanentemente, o desactivarlo si tiene datos asociados."""
    permission_classes = PERMS

    def delete(self, request, user_id):
        user = get_object_or_404(User, pk=user_id, is_superuser=False)
        username = user.username
        try:
            user.delete()
            logger.info("Superadmin %s deleted user %d (%s)", request.user.email, user_id, username)
            return Response({"ok": True, "deleted": username})
        except models.ProtectedError:
            user.is_active = False
            user.save(update_fields=["is_active"])
            logger.info("Superadmin %s deactivated user %d (%s) (has protected references)", request.user.email, user_id, username)
            return Response({"ok": True, "deactivated": username})


# ─────────────────────────────────────────────────────────────
# INVOICES (global view)
# ─────────────────────────────────────────────────────────────
class AdminInvoiceListView(APIView):
    permission_classes = PERMS

    def get(self, request):
        qs = Invoice.objects.select_related(
            "subscription__tenant", "subscription__plan"
        ).order_by("-created_at")

        inv_status = request.query_params.get("status")
        if inv_status:
            qs = qs.filter(status=inv_status)

        page = safe_int(request.query_params.get("page"), 1)
        page_size = safe_int(request.query_params.get("page_size"), 25)
        total = qs.count()
        offset = (page - 1) * page_size

        results = []
        for inv in qs[offset:offset + page_size]:
            results.append({
                "id": inv.id,
                "tenant_id": inv.subscription.tenant_id,
                "tenant_name": inv.subscription.tenant.name,
                "plan_name": inv.subscription.plan.name,
                "status": inv.status,
                "amount_clp": inv.amount_clp,
                "period_start": inv.period_start.isoformat(),
                "period_end": inv.period_end.isoformat(),
                "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
                "created_at": inv.created_at.isoformat(),
            })

        return Response({
            "results": results,
            "total": total,
            "page": page,
            "page_size": page_size,
        })


# ─────────────────────────────────────────────────────────────
# FORECAST METRICS (overview por tenant)
# ─────────────────────────────────────────────────────────────
class AdminForecastMetricsView(APIView):
    permission_classes = PERMS

    def get(self, request):
        try:
            from forecast.models import ForecastModel, ForecastAccuracy
        except ImportError:
            return Response({"detail": "Módulo forecast no disponible."}, status=404)

        mape_float = Cast(KeyTextTransform("mape", "metrics"), FloatField())

        active_models = ForecastModel.objects.filter(is_active=True)

        # Resumen global
        total_models = active_models.count()
        avg_mape = active_models.annotate(
            mape_val=mape_float,
        ).aggregate(avg=Avg("mape_val"))["avg"]

        # Por tenant (con avg MAPE)
        by_tenant = list(
            active_models.annotate(mape_val=mape_float).values(
                "tenant_id",
                tenant_name=F("tenant__name"),
            ).annotate(
                model_count=Count("id"),
                avg_mape=Avg("mape_val"),
            ).order_by("-model_count")[:50]
        )
        for t in by_tenant:
            t["avg_mape"] = round(float(t["avg_mape"] or 0), 2)

        # Distribución por algoritmo
        by_algorithm = list(
            active_models.values("algorithm").annotate(
                count=Count("id"),
            ).order_by("-count")
        )

        # Distribución por confianza
        by_confidence = list(
            active_models.values(confidence=F("confidence_label")).annotate(
                count=Count("id"),
            ).order_by("-count")
        )

        # Distribución por patrón de demanda
        by_pattern = list(
            active_models.values("demand_pattern").annotate(
                count=Count("id"),
            ).order_by("-count")
        )

        # Accuracy reciente (últimos 7 días)
        week_ago = timezone.now() - timedelta(days=7)
        recent_accuracy = ForecastAccuracy.objects.filter(
            date__gte=week_ago.date(),
        ).aggregate(
            avg_error=Avg("abs_pct_error"),
            total_predictions=Count("id"),
        )

        # Tendencia de accuracy diaria (últimos 30 días)
        month_ago = timezone.now() - timedelta(days=30)
        accuracy_trend = list(
            ForecastAccuracy.objects.filter(
                date__gte=month_ago.date(),
            ).values("date").annotate(
                avg_error=Avg("abs_pct_error"),
                predictions=Count("id"),
            ).order_by("date")
        )
        for row in accuracy_trend:
            row["date"] = str(row["date"])
            row["avg_error"] = round(float(row["avg_error"] or 0), 2)

        # Modelos mejorados vs empeorados (con mape_delta)
        improved = active_models.filter(mape_delta__lt=0).count()
        worsened = active_models.filter(mape_delta__gt=0).count()
        unchanged = active_models.filter(mape_delta=0).count()

        return Response({
            "total_active_models": total_models,
            "global_avg_mape": round(float(avg_mape or 0), 2),
            "by_tenant": by_tenant,
            "by_algorithm": by_algorithm,
            "by_confidence": by_confidence,
            "by_pattern": by_pattern,
            "model_health": {
                "improved": improved,
                "worsened": worsened,
                "unchanged": unchanged,
            },
            "accuracy_trend": accuracy_trend,
            "recent_7d": {
                "avg_pct_error": round(float(recent_accuracy["avg_error"] or 0), 2),
                "total_predictions": recent_accuracy["total_predictions"],
            },
            "training_logs": self._get_training_logs(),
        })

    def _get_training_logs(self):
        """Últimas 10 ejecuciones del pipeline de forecast."""
        from forecast.models import ForecastTrainingLog
        logs = ForecastTrainingLog.objects.order_by("-started_at")[:10]
        return [
            {
                "command": log.command,
                "status": log.status,
                "started_at": log.started_at.isoformat(),
                "duration_seconds": log.duration_seconds,
                "models_trained": log.models_trained,
                "models_improved": log.models_improved,
                "models_failed": log.models_failed,
                "avg_mape": log.avg_mape,
                "error_message": log.error_message[:200] if log.error_message else "",
                "algorithm_distribution": log.algorithm_distribution,
            }
            for log in logs
        ]
