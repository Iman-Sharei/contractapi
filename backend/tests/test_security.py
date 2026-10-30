from dataapi.domain.sensitive import find_sensitive_columns, is_sensitive_column
from dataapi.infrastructure.security.rate_limit import SlidingWindowRateLimiter
from dataapi.core.errors import AppError
import pytest


def test_sensitive_detection():
    assert is_sensitive_column("password_hash")
    assert is_sensitive_column("api_key")
    assert is_sensitive_column("secret_token")
    assert not is_sensitive_column("email")
    assert find_sensitive_columns(["id", "password", "name"]) == ["password"]


def test_rate_limiter_trips():
    lim = SlidingWindowRateLimiter()
    for _ in range(3):
        lim.check("k", limit=3, window_seconds=60)
    with pytest.raises(AppError) as exc:
        lim.check("k", limit=3, window_seconds=60)
    assert exc.value.status == 429
