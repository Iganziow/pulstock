"""
api/exception_handler.py
========================
Custom DRF exception handler — convierte excepciones no controladas
en respuestas JSON con mensaje claro en español, nunca un 500 mudo.

Principio SOLID (SRP): una sola responsabilidad — formatear errores.
Principio SOLID (OCP): extensible agregando handlers sin modificar los existentes.
"""

import logging
from decimal import InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("api.errors")


def custom_exception_handler(exc, context):
    """
    1. Deja que DRF maneje las excepciones conocidas (400, 401, 403, 404, 405, 429)
    2. Convierte excepciones comunes de Django/Python en 400 con mensaje claro
    3. Cualquier otra excepción → 500 con mensaje genérico + log completo
    """
    # DRF built-in handler
    response = drf_exception_handler(exc, context)
    if response is not None:
        # Normalizar el formato: siempre {detail: "..."} o {detail: [...]}
        if isinstance(response.data, dict) and "detail" not in response.data:
            response.data = {"detail": response.data}
        return response

    # ── Django ValidationError (from model .clean() or validators) ──
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, "message_dict"):
            return Response(
                {"detail": exc.message_dict},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"detail": exc.messages if hasattr(exc, "messages") else str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── IntegrityError (duplicate key, FK violation) ──
    if isinstance(exc, IntegrityError):
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            detail = "Este registro ya existe. Verifica que no esté duplicado."
        elif "foreign" in msg or "fk" in msg:
            detail = "No se puede completar la operación porque hay datos relacionados."
        elif "not null" in msg:
            detail = "Faltan campos obligatorios."
        else:
            detail = "Error de integridad en la base de datos."
        logger.warning("IntegrityError: %s", exc)
        return Response(
            {"detail": detail},
            status=status.HTTP_409_CONFLICT,
        )

    # ── ValueError / InvalidOperation (bad user input que llegó sin validar) ──
    if isinstance(exc, (ValueError, InvalidOperation)):
        logger.warning("ValueError: %s", exc)
        return Response(
            {"detail": "Valor inválido. Verifica los datos ingresados."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── TypeError (ej: None donde se esperaba número) ──
    if isinstance(exc, TypeError):
        logger.warning("TypeError: %s", exc, exc_info=True)
        return Response(
            {"detail": "Dato con formato incorrecto."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Cualquier otra excepción → 500 con log completo ──
    view = context.get("view")
    request = context.get("request")
    rid = getattr(request, "request_id", "-") if request else "-"
    logger.error(
        "Unhandled exception in %s (rid=%s): %s",
        view.__class__.__name__ if view else "unknown",
        rid,
        exc,
        exc_info=True,
    )
    return Response(
        {
            "detail": "Error interno del servidor. Intenta nuevamente o contacta soporte.",
            "rid": rid,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
