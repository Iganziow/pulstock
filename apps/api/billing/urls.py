from django.urls import path
from .views import (
    PlanListView,
    SubscriptionView,
    ChangePlanView,
    CancelSubscriptionView,
    ReactivateSubscriptionView,
    PaymentLinkView,
    ConfirmPaymentView,
    RegisterCardView,
    UnregisterCardView,
    InvoiceListView,
    FlowWebhookView,
    FlowCardRegisterWebhookView,
    CheckoutCreateView,
    CheckoutStatusView,
    CheckoutCompleteView,
    FlowCheckoutWebhookView,
)

urlpatterns = [
    # Público
    path("plans/",                  PlanListView.as_view()),

    # Suscripción del tenant autenticado
    path("subscription/",           SubscriptionView.as_view()),
    path("subscription/upgrade/",   ChangePlanView.as_view()),
    path("subscription/cancel/",    CancelSubscriptionView.as_view()),
    path("subscription/reactivate/",ReactivateSubscriptionView.as_view()),
    path("subscription/pay/",       PaymentLinkView.as_view()),
    path("subscription/confirm-payment/", ConfirmPaymentView.as_view()),

    # Tarjeta de crédito (cobro automático)
    path("subscription/card/",          RegisterCardView.as_view()),
    path("subscription/card/remove/",   UnregisterCardView.as_view()),

    # Facturas
    path("invoices/",               InvoiceListView.as_view()),

    # Checkout directo (público, sin auth)
    path("checkout/create/",    CheckoutCreateView.as_view()),
    path("checkout/status/",    CheckoutStatusView.as_view()),
    path("checkout/complete/",  CheckoutCompleteView.as_view()),

    # Webhooks pasarela
    path("webhook/flow/",               FlowWebhookView.as_view()),
    path("webhook/flow-card-register/", FlowCardRegisterWebhookView.as_view()),
    path("webhook/flow-checkout/",      FlowCheckoutWebhookView.as_view()),
]
