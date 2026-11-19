from app.config import Settings, load_settings


def test_load_settings_defaults_when_env_empty():
    settings = load_settings({})

    assert isinstance(settings, Settings)
    assert settings.sqlite_path == "./data/orders.db"
    assert settings.feishu_mode == "fake"


def test_load_settings_reads_env_overrides():
    env = {
        "SHOPIFY_WEBHOOK_SECRET": "whsec_test",
        "SQLITE_PATH": "/var/lib/demo/orders.db",
        "FEISHU_MODE": "real",
    }

    settings = load_settings(env)

    assert settings.shopify_webhook_secret == "whsec_test"
    assert settings.sqlite_path == "/var/lib/demo/orders.db"
    assert settings.feishu_mode == "real"


def test_load_settings_partial_env_keeps_other_defaults():
    settings = load_settings({"FEISHU_MODE": "real"})

    assert settings.feishu_mode == "real"
    assert settings.sqlite_path == "./data/orders.db"


def test_load_settings_defaults_to_os_environ(monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", ":memory:")
    monkeypatch.delenv("FEISHU_MODE", raising=False)

    settings = load_settings()

    assert settings.sqlite_path == ":memory:"
    assert settings.feishu_mode == "fake"
