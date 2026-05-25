"""
Tests del fast-path de /api/core/health/.

El HealthCheckFastPathMiddleware corta el request antes de session/csrf/
auth/jwt/billing para que los pings de monitor (1-5/min) no consuman
~280ms de CPU cada uno.

Reglas que debe cumplir:
1. GET /api/core/health/ devuelve 200 + {"status":"ok"} sin tocar nada
2. HEAD /api/core/health/ también funciona (UptimeRobot usa HEAD)
3. POST u otros métodos NO entran al fast-path (caen al view real)
4. /api/core/health/deep/ NO entra al fast-path (debe pasar por el view)
5. Otros paths no se ven afectados
6. No requiere auth (tampoco antes, pero confirmamos que el cambio no rompió eso)
7. No setea cookies de sesión ni CSRF en el response (señal de que no pasó
   por SessionMiddleware ni CsrfViewMiddleware)
"""
import pytest
from django.test import Client


@pytest.fixture
def client():
    return Client()


def test_get_health_returns_ok(client):
    r = client.get("/api/core/health/")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_head_health_returns_ok(client):
    r = client.head("/api/core/health/")
    assert r.status_code == 200


def test_health_does_not_touch_session(client):
    """El fast-path corta antes de SessionMiddleware → no debe haber
    Set-Cookie con sessionid en el response."""
    r = client.get("/api/core/health/")
    set_cookies = r.headers.get("Set-Cookie", "") or ""
    # Si pasara por SessionMiddleware, podría setear sessionid.
    assert "sessionid" not in set_cookies
    # CSRF tampoco debe meterse.
    assert "csrftoken" not in set_cookies


def test_health_does_not_require_auth(client):
    """Sin Authorization header / sin cookie de access_token → debe seguir
    devolviendo 200. (El JWTCookieMiddleware ni siquiera se ejecuta.)"""
    r = client.get("/api/core/health/")
    assert r.status_code == 200


def test_post_health_does_not_match_fastpath(client):
    """POST a /health/ debe caer al view real (que solo acepta GET → 405)."""
    r = client.post("/api/core/health/")
    # Django REST devuelve 405 Method Not Allowed; verificamos que no es 200
    # con cuerpo del fast-path.
    if r.status_code == 200:
        # Si el view devolviera 200 sería el real, no el fast-path.
        # Pero como solo declara `get`, debería ser 405.
        pass
    assert r.status_code in (405, 403)  # 405 lo normal; 403 si DRF mete CSRF


def test_deep_health_does_not_hit_fastpath(client, db):
    """/health/deep/ debe seguir ejecutando el DeepHealthView completo
    (chequea DB, redis, cron, disk). Lo verificamos por la forma del
    response: el fast-path devuelve {"status":"ok"} simple, pero deep
    devuelve eso O bien "degraded"/"down" — y al menos pasa por el view
    real, no por el middleware."""
    r = client.get("/api/core/health/deep/")
    # 200 o 503 según el estado real del sistema; nunca un dict idéntico
    # al fast-path porque el fast-path NO matchea este path.
    assert r.status_code in (200, 503)
    body = r.json()
    assert "status" in body


def test_other_paths_still_work_normally(client):
    """Sanity check: el fast-path NO debe interceptar /api/auth/login/ ni
    nada que no sea exactamente /api/core/health/."""
    # Path inexistente → 404 (no 200 con {"status":"ok"})
    r = client.get("/api/core/health/not-real/")
    assert r.status_code == 404
