# Add these to your main api/urls.py or create a separate auth/urls.py
# 
# In api/urls.py, add:
#   path("auth/", include("onboarding.urls")),
#
# Or if you already have auth urls, add these paths:

from django.urls import path
from onboarding.views import RegisterView, OnboardingStatusView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("onboarding-status/", OnboardingStatusView.as_view(), name="auth-onboarding-status"),
]

# ─────────────────────────────────────────────────────
# INTEGRATION INSTRUCTIONS:
# ─────────────────────────────────────────────────────
#
# OPTION A: Create as a Django app
#   1. Create folder: apps/api/onboarding/
#   2. Add __init__.py, views.py (from onboarding_views.py), urls.py (this file)
#   3. In api/urls.py: path("auth/", include("onboarding.urls")),
#
# OPTION B: Add to existing core app
#   1. Add RegisterView and OnboardingStatusView to core/views.py
#   2. Add the two paths to core/urls.py
#   3. Make sure they're accessible at /api/auth/register/ and /api/auth/onboarding-status/
#
# Both options work. The views only import from core.models, stores.models,
# catalog.models, and sales.models — all already exist.