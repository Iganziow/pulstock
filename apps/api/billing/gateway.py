"""
billing/gateway.py
==================
Capa de abstracción de pasarela de pago.

Soporta:
  - Mock (desarrollo/testing)
  - Flow.cl (producción / sandbox Chile)

Protocolo Flow (payment/create → webhook):
  1. Servidor crea orden con POST /payment/create (params firmados con HMAC-SHA256)
  2. Flow responde con {url, token}. Redirigir al usuario a url?token=token
  3. El usuario paga en Flow
  4. Flow envía POST a urlConfirmation con {token} (form-urlencoded)
  5. Servidor recibe token, llama GET /payment/getStatus para verificar resultado
  6. Procesa según status: 1=pendiente, 2=pagado, 3=rechazado, 4=anulado

Retorno estándar de charge_subscription() / create_payment_link():
{
    "success": bool,
    "gateway_order_id": str,
    "gateway_tx_id": str,
    "payment_url": str | None,
    "error": str,
    "raw": dict,
}
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid

import requests
from django.conf import settings
from django.utils import timezone

from .models import Invoice, PaymentAttempt, Subscription

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# CONFIG — leído una vez al importar el módulo
# ─────────────────────────────────────────────────────────────
GATEWAY = getattr(settings, "PAYMENT_GATEWAY", "mock")


def _get_gateway():
    """Read gateway at call time so @override_settings works in tests."""
    return getattr(settings, "PAYMENT_GATEWAY", GATEWAY)

if not settings.DEBUG and GATEWAY == "mock":
    logger.warning(
        "⚠️  PAYMENT_GATEWAY=mock en producción — los cobros NO son reales. "
        "Configura PAYMENT_GATEWAY=flow y las credenciales de Flow.cl."
    )


def _flow_cfg():
    """Lee credenciales Flow desde settings (definidas en settings.py desde env)."""
    return {
        "api_key":  getattr(settings, "FLOW_API_KEY", ""),
        "secret":   getattr(settings, "FLOW_SECRET_KEY", ""),
        "base_url": getattr(settings, "FLOW_BASE_URL", "https://sandbox.flow.cl/api"),
        "api_base": getattr(settings, "API_BASE_URL", "http://localhost:8000"),
        "app_base": getattr(settings, "APP_BASE_URL", "http://localhost:3000"),
    }


# ─────────────────────────────────────────────────────────────
# INTERFAZ PÚBLICA
# ─────────────────────────────────────────────────────────────
def charge_subscription(subscription: Subscription, invoice: Invoice) -> dict:
    """Punto de entrada principal. Delega al gateway configurado."""
    if _get_gateway() == "flow":
        return _charge_via_flow(subscription, invoice)
    return _charge_mock(subscription, invoice)


def create_payment_link(subscription: Subscription, invoice: Invoice) -> dict:
    """Genera link de pago manual (el usuario paga y el webhook confirma)."""
    if _get_gateway() == "flow":
        return _create_flow_payment_link(subscription, invoice)
    return _create_mock_payment_link(subscription, invoice)


def get_payment_status(token: str) -> dict:
    """
    Consulta el estado de un pago en Flow usando el token del webhook.
    Retorna el objeto PaymentStatus de Flow (o mock equivalente).
    """
    if _get_gateway() == "flow":
        return _flow_get_payment_status(token)
    # Mock: retorna pagado siempre
    return {"status": 2, "commerceOrder": "0", "flowOrder": 0, "mock": True}


# ─────────────────────────────────────────────────────────────
# FIRMA HMAC-SHA256 (según documentación Flow)
# ─────────────────────────────────────────────────────────────
def _flow_sign(params: dict, secret: str) -> str:
    """
    Firma los parámetros según protocolo Flow:
    1. Ordenar params alfabéticamente por key
    2. Concatenar key+value sin separadores
    3. HMAC-SHA256 con secretKey
    """
    keys = sorted(params.keys())
    to_sign = "".join(f"{k}{params[k]}" for k in keys if k != "s")
    return hmac.new(secret.encode(), to_sign.encode(), hashlib.sha256).hexdigest()


def _verify_flow_token_signature(data: dict) -> bool:
    """Verifica la firma 's' en una respuesta de Flow (cuando aplica)."""
    cfg = _flow_cfg()
    signature = data.get("s", "")
    if not signature:
        return False
    expected = _flow_sign(data, cfg["secret"])
    return hmac.compare_digest(expected, signature)


# ─────────────────────────────────────────────────────────────
# FLOW API CALL (con firma automática)
# ─────────────────────────────────────────────────────────────
def _flow_api_call(method: str, endpoint: str, params: dict) -> dict:
    """
    Llama a la API de Flow con firma automática.
    - Agrega apiKey si no está presente
    - Calcula y agrega firma 's'
    - Envía la petición (POST form-urlencoded o GET query params)
    - Retorna el JSON de respuesta
    """
    cfg = _flow_cfg()

    if not cfg["api_key"] or not cfg["secret"]:
        raise ValueError(
            "FLOW_API_KEY y FLOW_SECRET_KEY son requeridas. "
            "Configúralas en el .env del backend."
        )

    # Asegurar apiKey en params
    if "apiKey" not in params:
        params["apiKey"] = cfg["api_key"]

    # Firmar (excluye 's' si ya existe)
    params["s"] = _flow_sign(params, cfg["secret"])

    url = f"{cfg['base_url']}{endpoint}"

    if method == "POST":
        resp = requests.post(url, data=params, timeout=30)
    else:
        resp = requests.get(url, params=params, timeout=30)

    if resp.status_code not in (200, 400, 401):
        logger.error("Flow API error HTTP %d: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()

    result = resp.json()

    # Flow retorna errores con code+message en status 400/401
    if resp.status_code in (400, 401):
        error_msg = result.get("message", result.get("error", "Error Flow API"))
        logger.warning("Flow API error %d: %s", resp.status_code, error_msg)
        raise FlowAPIError(resp.status_code, error_msg, result)

    return result


class FlowAPIError(Exception):
    """Error retornado por la API de Flow."""
    def __init__(self, status_code: int, message: str, raw: dict):
        self.status_code = status_code
        self.message = message
        self.raw = raw
        super().__init__(f"Flow API {status_code}: {message}")


# ─────────────────────────────────────────────────────────────
# MOCK (desarrollo / CI)
# ─────────────────────────────────────────────────────────────
def _charge_mock(subscription: Subscription, invoice: Invoice) -> dict:
    """Simula cobro. Para simular fallo: PAYMENT_GATEWAY_MOCK_FAIL=1."""
    import os
    should_fail = os.getenv("PAYMENT_GATEWAY_MOCK_FAIL", "0") == "1"

    order_id = f"MOCK-{invoice.pk}-{uuid.uuid4().hex[:8].upper()}"

    attempt = PaymentAttempt.objects.create(
        invoice=invoice,
        gateway="mock",
        result=PaymentAttempt.Result.PENDING,
        raw={"order_id": order_id, "mock": True},
    )

    if should_fail:
        attempt.result = PaymentAttempt.Result.FAILED
        attempt.error_msg = "Tarjeta rechazada (mock)"
        attempt.save(update_fields=["result", "error_msg"])
        invoice.status = Invoice.Status.FAILED
        invoice.save(update_fields=["status"])
        return {
            "success": False,
            "gateway_order_id": order_id,
            "gateway_tx_id": "",
            "payment_url": None,
            "error": "Tarjeta rechazada (mock)",
            "raw": {"mock": True},
        }

    tx_id = f"TXMOCK-{uuid.uuid4().hex[:12].upper()}"
    attempt.result = PaymentAttempt.Result.SUCCESS
    attempt.raw["tx_id"] = tx_id
    attempt.save(update_fields=["result", "raw"])

    invoice.gateway_order_id = order_id
    invoice.gateway_tx_id = tx_id
    invoice.save(update_fields=["gateway_order_id", "gateway_tx_id"])

    return {
        "success": True,
        "gateway_order_id": order_id,
        "gateway_tx_id": tx_id,
        "payment_url": None,
        "error": "",
        "raw": {"mock": True, "tx_id": tx_id},
    }


def _create_mock_payment_link(subscription: Subscription, invoice: Invoice) -> dict:
    order_id = f"MOCK-LINK-{invoice.pk}"
    cfg = _flow_cfg()
    url = f"{cfg['app_base']}/dashboard/settings?tab=suscripcion&mock_pay={invoice.pk}"
    invoice.payment_url = url
    invoice.gateway_order_id = order_id
    invoice.save(update_fields=["payment_url", "gateway_order_id"])
    return {"success": True, "payment_url": url, "order_id": order_id}


# ─────────────────────────────────────────────────────────────
# FLOW.CL — Crear link de pago (payment/create)
# ─────────────────────────────────────────────────────────────
def _create_flow_payment_link(subscription: Subscription, invoice: Invoice) -> dict:
    """
    Crea una orden de pago en Flow.
    Retorna URL de pago para redirigir al usuario.
    """
    cfg = _flow_cfg()

    try:
        params = {
            "commerceOrder": str(invoice.pk),
            "subject":       f"Pulstock - {subscription.plan.name}",
            "amount":        int(invoice.amount_clp),
            "email":         _get_owner_email(subscription),
            "currency":      "CLP",
            "paymentMethod": 9,   # Todos los medios de pago
            # Flow enviará POST con token a esta URL cuando el pago se confirme
            "urlConfirmation": f"{cfg['api_base']}/api/billing/webhook/flow/",
            # Flow redirigirá al usuario a esta URL después de pagar
            # Flow agrega ?token=XXX automáticamente al redirigir
            "urlReturn":       f"{cfg['app_base']}/dashboard/settings?tab=plan",
        }

        result = _flow_api_call("POST", "/payment/create", params)

        if "url" in result and "token" in result:
            payment_url = f"{result['url']}?token={result['token']}"
            invoice.payment_url = payment_url
            invoice.gateway_order_id = str(invoice.pk)
            invoice.save(update_fields=["payment_url", "gateway_order_id"])

            logger.info(
                "Flow payment link creado: invoice=%d url=%s",
                invoice.pk, payment_url[:80]
            )
            return {
                "success": True,
                "payment_url": payment_url,
                "gateway_order_id": str(invoice.pk),
                "gateway_tx_id": "",
                "error": "",
                "raw": result,
            }
        else:
            error = result.get("message", "Respuesta inesperada de Flow")
            logger.error("Flow payment/create sin url/token: %s", result)
            return {
                "success": False,
                "error": error,
                "payment_url": None,
                "gateway_order_id": "",
                "gateway_tx_id": "",
                "raw": result,
            }

    except FlowAPIError as e:
        logger.error("Flow API error creando pago: %s", e)
        return {
            "success": False,
            "error": e.message,
            "payment_url": None,
            "gateway_order_id": "",
            "gateway_tx_id": "",
            "raw": e.raw,
        }
    except Exception as e:
        logger.error("Error inesperado creando link Flow: %s", e, exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "payment_url": None,
            "gateway_order_id": "",
            "gateway_tx_id": "",
            "raw": {},
        }


# ─────────────────────────────────────────────────────────────
# FLOW.CL — Cobro automático (si hay método guardado)
# ─────────────────────────────────────────────────────────────
def _charge_via_flow(subscription: Subscription, invoice: Invoice) -> dict:
    """
    Intenta cobro automático si hay tarjeta registrada.
    Si no hay tarjeta, genera link de pago manual.
    """
    if subscription.flow_customer_id and subscription.card_last4:
        return _flow_charge_customer(subscription, invoice)
    return _create_flow_payment_link(subscription, invoice)


def _flow_charge_customer(subscription: Subscription, invoice: Invoice) -> dict:
    """
    Cobra automáticamente en la tarjeta registrada del cliente.
    POST /customer/charge
    """
    try:
        params = {
            "customerId":    subscription.flow_customer_id,
            "amount":        int(invoice.amount_clp),
            "subject":       f"Pulstock - {subscription.plan.name}",
            "commerceOrder": str(invoice.pk),
            "currency":      "CLP",
        }
        result = _flow_api_call("POST", "/customer/charge", params)

        flow_status = result.get("status")
        flow_order = result.get("flowOrder", "")

        if flow_status == 2:
            attempt_result = PaymentAttempt.Result.SUCCESS
        elif flow_status == 1:
            attempt_result = PaymentAttempt.Result.PENDING
        else:
            attempt_result = PaymentAttempt.Result.FAILED

        attempt = PaymentAttempt.objects.create(
            invoice=invoice,
            gateway="flow",
            result=attempt_result,
            raw=result,
        )

        if flow_status == 2:
            invoice.gateway_order_id = str(invoice.pk)
            invoice.gateway_tx_id = str(flow_order)
            invoice.save(update_fields=["gateway_order_id", "gateway_tx_id"])
            logger.info("Flow auto-charge OK: invoice=%d flowOrder=%s", invoice.pk, flow_order)
            return {
                "success": True,
                "gateway_order_id": str(invoice.pk),
                "gateway_tx_id": str(flow_order),
                "payment_url": None,
                "error": "",
                "raw": result,
            }
        else:
            error = f"Cargo automático rechazado (status={flow_status})"
            attempt.error_msg = error
            attempt.save(update_fields=["error_msg"])
            logger.warning("Flow auto-charge failed: invoice=%d status=%s", invoice.pk, flow_status)
            # Fallback: generar link de pago manual
            return _create_flow_payment_link(subscription, invoice)

    except FlowAPIError as e:
        logger.error("Flow customer/charge error: %s", e)
        # Fallback: generar link manual
        return _create_flow_payment_link(subscription, invoice)
    except Exception as e:
        logger.error("Error auto-charge Flow: %s", e, exc_info=True)
        return _create_flow_payment_link(subscription, invoice)


# ─────────────────────────────────────────────────────────────
# FLOW.CL — Consultar estado de pago (payment/getStatus)
# ─────────────────────────────────────────────────────────────
def _flow_get_payment_status(token: str) -> dict:
    """
    Consulta el estado extendido de un pago usando el token recibido en el webhook.

    Usamos /payment/getStatusExtended (NO /payment/getStatus) porque el extended
    retorna los datos del pago que necesitamos para el cliente y los emails:
      - paymentData.media             (ej. 'webpay', 'Mach', 'Servipag')
      - paymentData.mediaType         ('Crédito' / 'Débito')
      - paymentData.cardLast4Numbers  ('9876')
      - paymentData.cardNumber        ('457630 **** **** 9876' — contiene marca)
      - paymentData.installments      (cuotas)
      - paymentData.autorizationCode  (código autorización)
      - lastError.code / .message     (cuando hubo rechazo)

    Flow retorna en `status`:
      1=pendiente, 2=pagado, 3=rechazado, 4=anulado
    """
    # Validar que el token no esté vacío ni sea excesivamente largo
    if not token or len(token) > 512:
        logger.warning("Flow getStatus: token inválido (len=%d)", len(token) if token else 0)
        return {"status": -1, "error": "Token inválido"}

    try:
        result = _flow_api_call("GET", "/payment/getStatusExtended", {"token": token})
        logger.info(
            "Flow getStatusExtended: commerceOrder=%s status=%s flowOrder=%s media=%s last4=%s",
            result.get("commerceOrder"),
            result.get("status"),
            result.get("flowOrder"),
            (result.get("paymentData") or {}).get("media"),
            (result.get("paymentData") or {}).get("cardLast4Numbers"),
        )
        return result
    except FlowAPIError as e:
        logger.error("Flow getStatusExtended error: %s", e)
        return {"status": -1, "error": e.message, "raw": e.raw}
    except Exception as e:
        logger.error("Error consultando estado Flow: %s", e, exc_info=True)
        return {"status": -1, "error": str(e)}


def extract_payment_details(flow_status: dict) -> dict:
    """Extrae los campos relevantes del response /payment/getStatusExtended.

    Uso:
        details = extract_payment_details(flow_status_response)
        invoice.card_last4 = details["card_last4"]
        invoice.card_brand = details["card_brand"]
        ... etc

    Devuelve un dict con todos los campos listos para asignar directamente al
    modelo Invoice. Campos ausentes vuelven "" (string vacío) o None para ints.

    Marca de tarjeta: Flow no la devuelve explícitamente en un campo separado,
    pero se puede inferir del BIN (primeros 6 dígitos en `paymentData.cardNumber`).
    Los BINs más comunes:
      - 4xxxxx → Visa
      - 5xxxxx → Mastercard
      - 34/37xx → American Express
    """
    payment_data = flow_status.get("paymentData") or {}
    last_error = flow_status.get("lastError") or {}

    # Extraer card_number "457630 **** **** 9876" → BIN "457630" → marca
    card_number = payment_data.get("cardNumber") or ""
    card_bin = card_number.split(" ")[0] if card_number else ""

    card_brand = ""
    if card_bin:
        first = card_bin[0] if card_bin else ""
        if first == "4":
            card_brand = "Visa"
        elif first == "5":
            card_brand = "Mastercard"
        elif card_bin[:2] in ("34", "37"):
            card_brand = "American Express"
        elif card_bin[:2] == "62":
            card_brand = "UnionPay"
        elif card_bin[:4] == "6011" or card_bin[:2] == "65":
            card_brand = "Discover"
        else:
            card_brand = "Tarjeta"  # fallback genérico

    return {
        "card_last4": (payment_data.get("cardLast4Numbers") or "")[:4],
        "card_brand": card_brand,
        "payment_media": (payment_data.get("media") or "")[:40],
        "payment_media_type": (payment_data.get("mediaType") or "")[:20],
        "installments": payment_data.get("installments") or None,
        "authorization_code": (payment_data.get("autorizationCode") or "")[:40],
        "failure_code": (last_error.get("code") or "")[:20],
        "failure_message": last_error.get("message") or "",
    }


# ─────────────────────────────────────────────────────────────
# FLOW.CL — Customer (registro de tarjeta para cobro automático)
# ─────────────────────────────────────────────────────────────
def create_flow_customer(subscription: Subscription) -> dict:
    """
    Crea un cliente en Flow. Retorna el customerId.
    Si ya tiene uno, lo retorna directamente.
    """
    if subscription.flow_customer_id:
        return {"customerId": subscription.flow_customer_id, "already_exists": True}

    if _get_gateway() != "flow":
        cid = f"mock_cus_{subscription.tenant_id}"
        subscription.flow_customer_id = cid
        subscription.save(update_fields=["flow_customer_id"])
        return {"customerId": cid, "mock": True}

    email = _get_owner_email(subscription)
    if not email:
        return {"error": "El owner no tiene email configurado."}

    try:
        result = _flow_api_call("POST", "/customer/create", {
            "name": subscription.tenant.name or email,
            "email": email,
            "externalId": str(subscription.tenant_id),
        })
        cid = result.get("customerId", "")
        if cid:
            subscription.flow_customer_id = cid
            subscription.save(update_fields=["flow_customer_id"])
            logger.info("Flow customer creado: %s tenant=%s", cid, subscription.tenant_id)
        return result
    except FlowAPIError as e:
        logger.error("Flow customer/create error: %s", e)
        return {"error": e.message}
    except Exception as e:
        logger.error("Error creando customer Flow: %s", e, exc_info=True)
        return {"error": str(e)}


def register_flow_card(subscription: Subscription) -> dict:
    """
    Inicia el proceso de registro de tarjeta.
    Retorna URL para redirigir al usuario.
    """
    if _get_gateway() != "flow":
        return {"error": "Registro de tarjeta solo disponible con Flow."}

    # Crear customer si no existe
    if not subscription.flow_customer_id:
        result = create_flow_customer(subscription)
        if "error" in result:
            return result

    cfg = _flow_cfg()
    try:
        result = _flow_api_call("POST", "/customer/register", {
            "customerId": subscription.flow_customer_id,
            "url_return": f"{cfg['api_base']}/api/billing/webhook/flow-card-register/",
        })
        if "url" in result and "token" in result:
            register_url = f"{result['url']}?token={result['token']}"
            logger.info("Flow card register URL: tenant=%s", subscription.tenant_id)
            return {"url": register_url, "token": result["token"]}
        return {"error": "Respuesta inesperada de Flow"}
    except FlowAPIError as e:
        logger.error("Flow customer/register error: %s", e)
        return {"error": e.message}
    except Exception as e:
        logger.error("Error registrando tarjeta Flow: %s", e, exc_info=True)
        return {"error": str(e)}


def get_card_register_status(token: str) -> dict:
    """Consulta el resultado del registro de tarjeta."""
    if _get_gateway() != "flow":
        return {"status": "1", "customerId": "", "creditCardType": "Visa", "last4CardDigits": "4242", "mock": True}

    try:
        return _flow_api_call("GET", "/customer/getRegisterStatus", {"token": token})
    except FlowAPIError as e:
        logger.error("Flow getRegisterStatus error: %s", e)
        return {"status": "0", "error": e.message}
    except Exception as e:
        logger.error("Error getRegisterStatus: %s", e, exc_info=True)
        return {"status": "0", "error": str(e)}


def unregister_flow_card(subscription: Subscription) -> dict:
    """Elimina la tarjeta registrada del cliente."""
    if _get_gateway() != "flow" or not subscription.flow_customer_id:
        subscription.card_brand = ""
        subscription.card_last4 = ""
        subscription.save(update_fields=["card_brand", "card_last4"])
        return {"ok": True}

    try:
        result = _flow_api_call("POST", "/customer/unRegister", {
            "customerId": subscription.flow_customer_id,
        })
        subscription.card_brand = ""
        subscription.card_last4 = ""
        subscription.save(update_fields=["card_brand", "card_last4"])
        logger.info("Flow card unregistered: tenant=%s", subscription.tenant_id)
        return {"ok": True, "raw": result}
    except FlowAPIError as e:
        logger.error("Flow unRegister error: %s", e)
        return {"error": e.message}
    except Exception as e:
        logger.error("Error unregistering card: %s", e, exc_info=True)
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────
# CHECKOUT (pago pre-registro, sin suscripción)
# ─────────────────────────────────────────────────────────────
def create_checkout_payment_link(checkout_session) -> dict:
    """
    Crea un link de pago en Flow para un CheckoutSession (pre-registro).
    Similar a create_payment_link pero no requiere Subscription.
    """
    if _get_gateway() == "flow":
        return _create_flow_checkout_link(checkout_session)
    return _create_mock_checkout_link(checkout_session)


def _create_mock_checkout_link(checkout_session) -> dict:
    """Mock: auto-marca como pagado y retorna URL de completion."""
    order_id = f"CS-MOCK-{checkout_session.pk}-{uuid.uuid4().hex[:8].upper()}"
    cfg = _flow_cfg()

    checkout_session.gateway_order_id = order_id
    checkout_session.gateway_tx_id = f"TXMOCK-{uuid.uuid4().hex[:12].upper()}"
    checkout_session.status = "paid"
    checkout_session.payment_url = f"{cfg['app_base']}/checkout/complete?token={checkout_session.token}"
    checkout_session.save(update_fields=[
        "gateway_order_id", "gateway_tx_id", "status", "payment_url",
    ])

    return {
        "success": True,
        "payment_url": checkout_session.payment_url,
        "gateway_order_id": order_id,
        "mock": True,
    }


def _create_flow_checkout_link(checkout_session) -> dict:
    """Crea orden de pago en Flow para checkout pre-registro."""
    cfg = _flow_cfg()
    commerce_order = f"CS-{checkout_session.pk}"

    try:
        params = {
            "commerceOrder": commerce_order,
            "subject":       f"Pulstock - {checkout_session.plan.name}",
            "amount":        int(checkout_session.amount_clp),
            "email":         checkout_session.email,
            "currency":      "CLP",
            "paymentMethod": 9,
            "urlConfirmation": f"{cfg['api_base']}/api/billing/webhook/flow-checkout/",
            "urlReturn":       f"{cfg['app_base']}/checkout/complete?token={checkout_session.token}",
        }

        result = _flow_api_call("POST", "/payment/create", params)

        if "url" in result and "token" in result:
            payment_url = f"{result['url']}?token={result['token']}"
            checkout_session.payment_url = payment_url
            checkout_session.gateway_order_id = commerce_order
            checkout_session.flow_token = result["token"]
            checkout_session.save(update_fields=["payment_url", "gateway_order_id", "flow_token"])

            logger.info("Checkout payment link creado: session=%d url=%s",
                        checkout_session.pk, payment_url[:80])
            return {
                "success": True,
                "payment_url": payment_url,
                "gateway_order_id": commerce_order,
            }
        else:
            error = result.get("message", "Respuesta inesperada de Flow")
            logger.error("Flow checkout sin url/token: %s", result)
            return {"success": False, "error": error, "payment_url": None}

    except FlowAPIError as e:
        logger.error("Flow checkout error: %s", e)
        return {"success": False, "error": e.message, "payment_url": None}
    except Exception as e:
        logger.error("Error checkout Flow: %s", e, exc_info=True)
        return {"success": False, "error": str(e), "payment_url": None}


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _get_owner_email(subscription: Subscription) -> str:
    """Obtiene el email del owner del tenant."""
    from core.models import User
    owner = User.objects.filter(
        tenant=subscription.tenant, role="owner", is_active=True
    ).values("email").first()
    return owner["email"] if owner else ""
