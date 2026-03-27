from django.contrib import admin
from .models import Plan, Subscription, Invoice, PaymentAttempt, CheckoutSession


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display  = ["key", "name", "price_clp", "max_products", "max_stores", "max_users", "is_active"]
    list_editable = ["is_active"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display  = ["tenant", "plan", "status", "current_period_end", "payment_retry_count", "created_at"]
    list_filter   = ["status", "plan"]
    search_fields = ["tenant__name"]
    readonly_fields = ["created_at", "updated_at"]
    actions = ["reactivate_selected"]

    @admin.action(description="Reactivar suscripciones seleccionadas")
    def reactivate_selected(self, request, queryset):
        from .services import reactivate_subscription
        for sub in queryset:
            reactivate_subscription(sub)
        self.message_user(request, f"{queryset.count()} suscripción(es) reactivadas.")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display  = ["id", "subscription", "status", "amount_clp", "period_start", "period_end", "paid_at"]
    list_filter   = ["status", "gateway"]
    search_fields = ["subscription__tenant__name"]
    readonly_fields = ["created_at"]


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = ["id", "invoice", "result", "gateway", "attempted_at"]
    list_filter  = ["result", "gateway"]
    readonly_fields = ["attempted_at"]


@admin.register(CheckoutSession)
class CheckoutSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "email", "plan", "status", "amount_clp", "created_at", "completed_at"]
    list_filter  = ["status", "plan"]
    search_fields = ["email", "token"]
    readonly_fields = ["token", "created_at"]