from datetime import timedelta
from pathlib import Path
import os
from django.core.exceptions import ImproperlyConfigured

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

# ======================================================
# CORE
# ======================================================
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "La variable de entorno DJANGO_SECRET_KEY es requerida. "
        "Genera una con: python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
    )

DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"

_allowed_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "")
if not _allowed_hosts:
    if DEBUG:
        ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
    else:
        raise ImproperlyConfigured(
            "La variable de entorno DJANGO_ALLOWED_HOSTS es requerida en producción. "
            "Ejemplo: DJANGO_ALLOWED_HOSTS=midominio.com,www.midominio.com"
        )
else:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(",")]

# Validar variables críticas de producción
if not DEBUG:
    _required = {
        "WEB_ORIGIN": os.getenv("WEB_ORIGIN"),
    }
    _missing = [k for k, v in _required.items() if not v]
    if _missing:
        raise ImproperlyConfigured(
            f"Variables de entorno requeridas en producción faltantes: {', '.join(_missing)}"
        )
    # Email: requerido si no se sobreescribe el backend
    _email_backend = os.getenv("EMAIL_BACKEND", "")
    if not _email_backend:  # usa SMTP por defecto en producción
        _email_required = {
            "EMAIL_HOST_USER": os.getenv("EMAIL_HOST_USER"),
            "EMAIL_HOST_PASSWORD": os.getenv("EMAIL_HOST_PASSWORD"),
        }
        _email_missing = [k for k, v in _email_required.items() if not v]
        if _email_missing:
            raise ImproperlyConfigured(
                f"Variables de email requeridas en producción: {', '.join(_email_missing)}. "
                "Configura EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend para omitir."
            )

    # Flow.cl: opcionales hasta activar cobros reales
    # Cuando configures PAYMENT_GATEWAY=flow, estas pasan a ser requeridas
    if os.getenv("PAYMENT_GATEWAY") == "flow":
        _flow_required = {
            "FLOW_API_KEY": os.getenv("FLOW_API_KEY"),
            "FLOW_SECRET_KEY": os.getenv("FLOW_SECRET_KEY"),
        }
        _flow_missing = [k for k, v in _flow_required.items() if not v]
        if _flow_missing:
            raise ImproperlyConfigured(
                f"PAYMENT_GATEWAY=flow requiere: {', '.join(_flow_missing)}"
            )

# ======================================================
# PAYMENT GATEWAY (Flow.cl)
# ======================================================
DJANGO_ADMIN_URL = os.getenv("DJANGO_ADMIN_URL", "admin/")

PAYMENT_GATEWAY  = os.getenv("PAYMENT_GATEWAY", "mock")
FLOW_API_KEY     = os.getenv("FLOW_API_KEY", "")
FLOW_SECRET_KEY  = os.getenv("FLOW_SECRET_KEY", "")
# Default a sandbox por seguridad: si alguien olvida setear FLOW_BASE_URL en prod,
# no cobra plata real. Para activar producción hay que setearlo explícitamente a
# https://www.flow.cl/api en el .env.
FLOW_BASE_URL    = os.getenv("FLOW_BASE_URL", "https://sandbox.flow.cl/api")

# ======================================================
# DEEP HEALTH — token para endpoint /api/core/health/deep/?token=X
# ======================================================
# Si está configurado, /health/deep/?token=<value> devuelve detalles completos.
# Sin token, el endpoint solo devuelve status (ok/degraded/down).
DEEP_HEALTH_TOKEN = os.getenv("DEEP_HEALTH_TOKEN", "")
# URL pública del backend Django (para callbacks de Flow)
API_BASE_URL     = os.getenv("API_BASE_URL", "http://localhost:8000")
# URL pública del frontend Next.js (para redirigir al usuario tras pago)
APP_BASE_URL     = os.getenv("APP_BASE_URL", "http://localhost:3000")

# Tenants con acceso de por vida (dueño de la app, cuentas internas).
# Estos NUNCA pagan ni se bloquean por el middleware de suscripción.
# Lista separada por comas via env: BILLING_LIFETIME_SLUGS=marbrava,otro-slug
_lifetime_raw = os.getenv("BILLING_LIFETIME_SLUGS", "marbrava")
BILLING_LIFETIME_SLUGS = [s.strip() for s in _lifetime_raw.split(",") if s.strip()]

# ======================================================
# APPS
# ======================================================
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_celery_beat",
]

LOCAL_APPS = [
    "core.apps.CoreConfig",
    "catalog.apps.CatalogConfig",
    "inventory",
    "sales",
    "reports",
    "stores.apps.StoresConfig",
    "purchases",
    "forecast.apps.ForecastConfig",
    "billing.apps.BillingConfig",
    "caja",
    "tables",
    "onboarding",
    "superadmin.apps.SuperadminConfig",
    "promotions.apps.PromotionsConfig",
    "printing.apps.PrintingConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ======================================================
# MIDDLEWARE
# ======================================================
MIDDLEWARE = [
    "api.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",

    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "api.middleware.JWTCookieMiddleware",
    "billing.middleware.SubscriptionAccessMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "api.urls"

# ======================================================
# TEMPLATES
# ======================================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "api.wsgi.application"
ASGI_APPLICATION = "api.asgi.application"

# ======================================================
# DATABASE
# ======================================================
_database_url = os.getenv("DATABASE_URL")
if _database_url:
    import dj_database_url
    DATABASES = {
        "default": dj_database_url.parse(
            _database_url,
            conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "60")),
            conn_health_checks=True,
        )
    }
elif not DEBUG:
    raise ImproperlyConfigured(
        "La variable de entorno DATABASE_URL es requerida en producción. "
        "Ejemplo: DATABASE_URL=postgres://user:password@host:5432/dbname"
    )
else:
    # Solo permitido en desarrollo
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ======================================================
# AUTH
# ======================================================
AUTH_USER_MODEL = "core.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# ======================================================
# I18N
# ======================================================
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

# ======================================================
# STATIC
# ======================================================
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ======================================================
# DRF / AUTH API
# ======================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "api.throttles.TenantRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "200/hour",
        "user": "2000/hour",
        "tenant": "5000/hour",
        "login": "10/minute",
        "register": "10/hour",
        "sensitive_action": "20/hour",
        "webhook": "60/minute",
        "agent_pair": "20/hour",  # anti-brute-force on pairing code exchange
        "agent_poll": "60/minute",  # 3s poll = 20/min normal, 60 tolera hipo
    },
    "EXCEPTION_HANDLER": "api.exception_handler.custom_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
}

# ======================================================
# CORS
# ======================================================
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("WEB_ORIGIN", "http://localhost:3000").split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True

# ======================================================
# SECURITY HEADERS (solo producción)
# ======================================================
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # HSTS preload solo activar después de registrar el dominio en https://hstspreload.org
    SECURE_HSTS_PRELOAD = os.getenv("DJANGO_HSTS_PRELOAD", "0") == "1"
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "1") == "1"
    SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
    CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT

# ======================================================
# LOGGING
# ======================================================
_LOG_FILE = os.getenv("DJANGO_LOG_FILE", "")
_log_handlers = ["console"]
_logging_handlers: dict = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "verbose",
    },
}
if _LOG_FILE:
    _log_handlers.append("file")
    _logging_handlers["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": _LOG_FILE,
        "maxBytes": 10 * 1024 * 1024,  # 10 MB
        "backupCount": 5,
        "formatter": "verbose",
    }

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} rid={request_id} {message}",
            "style": "{",
            "defaults": {"request_id": "-"},
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
        "json": {
            "()": "django.utils.log.ServerFormatter",
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": _logging_handlers,
    "root": {
        "handlers": _log_handlers,
        "level": "WARNING",
    },
    "loggers": {
        "django.security": {
            "handlers": _log_handlers,
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": _log_handlers,
            "level": "ERROR",
            "propagate": False,
        },
        # Loggers de negocio — registran operaciones críticas
        "sales": {
            "handlers": _log_handlers,
            "level": "INFO",
            "propagate": False,
        },
        "inventory": {
            "handlers": _log_handlers,
            "level": "INFO",
            "propagate": False,
        },
        "purchases": {
            "handlers": _log_handlers,
            "level": "INFO",
            "propagate": False,
        },
        "billing": {
            "handlers": _log_handlers,
            "level": "INFO",
            "propagate": False,
        },
        "api.errors": {
            "handlers": _log_handlers,
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# ======================================================
# CELERY
# ======================================================
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "billing-process-renewals": {
        "task": "billing.tasks.process_renewals",
        "schedule": crontab(minute=0),
    },
    "billing-send-reminders": {
        "task": "billing.tasks.send_payment_reminders",
        "schedule": crontab(hour=9, minute=0),
    },
    "billing-suspend-overdue": {
        "task": "billing.tasks.suspend_overdue_subscriptions",
        "schedule": crontab(minute=30),
    },
    "billing-retry-payments": {
        "task": "billing.tasks.retry_failed_payments",
        "schedule": crontab(minute=15),
    },
    "billing-expire-trials": {
        "task": "billing.tasks.expire_trials",
        "schedule": crontab(hour=2, minute=0),
    },
    # ── Printing: cleanup de jobs terminales viejos ──────────────
    "printing-cleanup-old-jobs": {
        "task": "printing.tasks.cleanup_old_jobs",
        "schedule": crontab(hour=3, minute=30),
    },
    # ── Forecast pipeline (nightly, sequential) ──────────────
    "forecast-aggregate-daily-sales": {
        "task": "forecast.tasks.aggregate_daily_sales",
        "schedule": crontab(hour=2, minute=0),
    },
    "forecast-compute-category-profiles": {
        "task": "forecast.tasks.compute_category_profiles",
        "schedule": crontab(hour=2, minute=30),
    },
    "forecast-track-accuracy": {
        "task": "forecast.tasks.track_forecast_accuracy",
        "schedule": crontab(hour=2, minute=45),
    },
    "forecast-train-models": {
        "task": "forecast.tasks.train_forecast_models",
        "schedule": crontab(hour=3, minute=0),
    },
    "forecast-generate-suggestions": {
        "task": "forecast.tasks.generate_purchase_suggestions",
        "schedule": crontab(hour=4, minute=0),
    },
    "forecast-evaluate-outcomes": {
        "task": "forecast.tasks.evaluate_suggestion_outcomes",
        "schedule": crontab(hour=5, minute=0),
    },
    # ── Weekly ABC report email ──────────────────────────
    "reports-weekly-abc": {
        "task": "reports.tasks.send_weekly_abc_report",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),  # Monday 8am
    },
    # ── Daily low stock alerts ───────────────────────────
    "inventory-low-stock-alerts": {
        "task": "inventory.tasks.send_low_stock_alerts",
        "schedule": crontab(hour=7, minute=30),  # Daily 7:30am
    },
}

# ======================================================
# EMAIL
# ======================================================
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Pulstock <noreply@pulstock.cl>")


# ─── Sentry (monitoreo de errores en producción) ───────────────────
# Activación: agregar SENTRY_DSN al .env de producción.
# Sin DSN, el SDK NO se inicializa — cero overhead, cero spam en dev.
#
# Setup paso a paso:
#   1. Crear cuenta en sentry.io (free: 5k errors/mes, 1 user, ilimitado retention)
#   2. Crear proyecto tipo "Django"
#   3. Copiar el DSN (https://xxx@o123.ingest.sentry.io/456)
#   4. En el server: echo "SENTRY_DSN=https://..." >> apps/api/.env
#   5. pdeploy-api → reload gunicorn → Sentry empieza a reportar
SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[
                DjangoIntegration(
                    transaction_style="url",  # /api/sales/123/ → /api/sales/{id}/
                ),
                CeleryIntegration(),
                LoggingIntegration(level=None, event_level=None),  # Solo unhandled
            ],
            # Sample 10% de transacciones para performance monitoring.
            # Subir a 1.0 en debugging si hace falta. Bajar si saturás cuota.
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_RATE", "0.1")),
            # Capturar 100% de errores (cuota free aguanta 5k/mes — sobra).
            sample_rate=1.0,
            # Tag útil para filtrar en el dashboard.
            environment=os.getenv("SENTRY_ENV", "production" if not DEBUG else "development"),
            # Release tracking — corremos `git rev-parse HEAD` en deploy y lo
            # exportamos como SENTRY_RELEASE para que Sentry agrupe errores
            # por commit (ayuda a saber "esto rompió en el último deploy").
            release=os.getenv("SENTRY_RELEASE", None),
            # Mandar PII (request body, headers, etc) — útil para debug.
            # Si tenés clientes con datos sensibles, poner False.
            send_default_pii=False,
            # Ignora 404s y errores comunes que no queremos en el dashboard.
            ignore_errors=[
                "django.http.Http404",
                "rest_framework.exceptions.NotFound",
                "rest_framework.exceptions.NotAuthenticated",
                "rest_framework.exceptions.AuthenticationFailed",
                "rest_framework.exceptions.PermissionDenied",
                "rest_framework.exceptions.Throttled",
            ],
        )
    except ImportError:
        # sentry_sdk no instalado — pasa silenciosamente. Útil en dev/CI sin
        # las deps de monitoring. En prod debería estar siempre instalado.
        pass
