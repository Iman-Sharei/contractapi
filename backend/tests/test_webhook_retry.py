from dataapi.domain.models.spec import WebhookConfig
from dataapi.infrastructure import webhooks as wh


def test_webhook_exhausted_goes_to_dlq(tmp_path, monkeypatch):
    monkeypatch.setenv("SPECS_DIR", str(tmp_path))
    from dataapi.core.config import get_settings

    get_settings.cache_clear()

    calls = {"n": 0}

    def boom(hook, body):
        calls["n"] += 1
        raise RuntimeError("down")

    monkeypatch.setattr(wh, "_send_once", boom)
    monkeypatch.setattr(wh, "_BACKOFF_SECONDS", (0, 0, 0, 0, 0))
    monkeypatch.setattr(wh, "_MAX_ATTEMPTS", 3)

    hook = WebhookConfig(url="http://127.0.0.1:9/hook", events=["create"], secret="s")
    wh._send_with_retries(hook, b'{"event":"create"}', "create", "customers")
    assert calls["n"] == 3
    dlq = tmp_path / ".runtime" / "webhook-dlq.jsonl"
    assert dlq.exists()
    assert "down" in dlq.read_text()
