"""Tokens from a company login server (OIDC: Keycloak, Azure AD, Okta, Google, Auth0…).

The data API trusts a login server named in its spec (jwt.provider: oidc). Tokens are checked
against the server's public signing keys (JWKS), found through its discovery document, with
asymmetric algorithms only: a shared-secret (HS*) or unsigned token can never pass.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any

import jwt

from contractapi.core.errors import AppError
from contractapi.core.logging import get_logger

logger = get_logger("contractapi.idp")

ASYMMETRIC_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512")
KEYS_TTL = 600  # signing keys are re-read every 10 minutes
REFETCH_GAP = 30  # an unknown key id triggers at most one re-read per 30 s (rotation, not DoS)

_lock = threading.Lock()
_discovery: dict[str, tuple[float, dict[str, Any]]] = {}
_keys: dict[str, tuple[float, dict[str, Any]]] = {}
_last_fetch: dict[str, float] = {}


def require_login_crypto() -> None:
    """Company-login signatures (RSA/EC) need the optional `cryptography` package."""
    import importlib.util

    if importlib.util.find_spec("cryptography") is None:
        raise AppError(
            type_="https://contractapi.dev/problems/dependency-missing",
            title="Package not installed",
            status=400,
            detail="Company login needs extra support on the server: pip install 'contractapi[oidc]'.",
        )


class LoginServerUnreachable(Exception):
    """The login server (or its key list) could not be read."""


def fetch_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "contractapi"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise LoginServerUnreachable(f"{url}: {getattr(exc, 'reason', exc)}") from exc
    if not isinstance(data, dict):
        raise LoginServerUnreachable(f"{url}: not a JSON object")
    return data


def discover(issuer: str) -> dict[str, Any]:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    now = time.time()
    with _lock:
        cached = _discovery.get(url)
        if cached and cached[0] > now:
            return cached[1]
    data = fetch_json(url)
    with _lock:
        _discovery[url] = (now + 3600, data)
    return data


def keys_url(issuer: str, jwks_url: str | None) -> str:
    if jwks_url:
        return jwks_url
    url = discover(issuer).get("jwks_uri")
    if not isinstance(url, str) or not url:
        raise LoginServerUnreachable(f"{issuer}: the discovery document has no jwks_uri")
    return url


def _key_set(url: str, *, refresh: bool = False) -> dict[str, Any]:
    now = time.time()
    with _lock:
        cached = _keys.get(url)
        if cached and cached[0] > now and not refresh:
            return cached[1]
        if refresh and cached and now - _last_fetch.get(url, 0) < REFETCH_GAP:
            return cached[1]
        _last_fetch[url] = now
    data = fetch_json(url)
    with _lock:
        _keys[url] = (now + KEYS_TTL, data)
    return data


def _signing_key(url: str, kid: str | None) -> Any:
    for refresh in (False, True):  # an unknown kid may mean the server rotated its keys
        keys = [k for k in _key_set(url, refresh=refresh).get("keys", []) if isinstance(k, dict)]
        usable = [k for k in keys if k.get("use", "sig") == "sig" and (kid is None or k.get("kid") == kid)]
        if usable:
            return jwt.PyJWK.from_dict(usable[0]).key
    raise jwt.InvalidTokenError("no signing key with this kid")


def _invalid(detail: str) -> AppError:
    return AppError(type_="https://contractapi.dev/problems/invalid-token", title="Invalid token",
                    status=401, detail=detail)


def verify_login_token(token: str, *, issuer: str, audience: str, jwks_url: str | None) -> dict[str, Any]:
    """Claims of a valid token from the login server, or a Problem Details error."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise _invalid("This is not a login token (JWT).") from exc
    alg = header.get("alg")
    if alg not in ASYMMETRIC_ALGORITHMS:
        raise _invalid("This token is not signed by your company login.")
    try:
        key = _signing_key(keys_url(issuer, jwks_url), header.get("kid"))
        return jwt.decode(
            token, key, algorithms=[alg], audience=audience, issuer=issuer, leeway=30,
            options={"require": ["exp", "iss", "aud"]},
        )
    except LoginServerUnreachable as exc:
        logger.warning("login server unreachable: %s", exc)
        raise AppError(
            type_="https://contractapi.dev/problems/auth-unavailable",
            title="Login server unavailable",
            status=503,
            detail="The company login server could not be reached to check this token. Try again shortly.",
        ) from exc
    except jwt.ExpiredSignatureError as exc:
        raise AppError(type_="https://contractapi.dev/problems/token-expired", title="Token expired",
                       status=401, detail="The login token has expired. Sign in again.") from exc
    except jwt.InvalidAudienceError as exc:
        raise _invalid("This token was issued for another application (audience).") from exc
    except jwt.InvalidIssuerError as exc:
        raise _invalid("This token comes from another login server (issuer).") from exc
    except jwt.PyJWTError as exc:
        raise _invalid("The login token is not valid.") from exc


def claim_values(claims: dict[str, Any], path: str) -> list[str]:
    """Values at a claim path ("roles", "groups", "realm_access.roles"); text is split on spaces
    and commas (like the "scope" claim)."""
    node: Any = claims
    for part in path.split("."):
        if not isinstance(node, dict):
            return []
        node = node.get(part)
    if isinstance(node, str):
        return [v for v in node.replace(",", " ").split() if v]
    if isinstance(node, list):
        return [str(v) for v in node]
    return []


def describe_login_server(issuer: str, jwks_url: str | None) -> dict[str, Any]:
    """What Studio's "Test connection" shows: where the keys are and how many."""
    url = keys_url(issuer, jwks_url)
    keys = [k for k in _key_set(url, refresh=True).get("keys", []) if isinstance(k, dict)]
    signing = [k for k in keys if k.get("use", "sig") == "sig"]
    return {
        "issuer": issuer,
        "jwks_uri": url,
        "signing_keys": len(signing),
        "algorithms": sorted({str(k.get("alg")) for k in signing if k.get("alg")}),
    }
