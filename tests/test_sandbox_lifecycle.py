"""沙盒生命周期机制测试（纯逻辑，不依赖 Docker）。

- configure() 运行时设置 TTL 硬上限
- _ttl_expired() 生命周期判定
- 默认配置包含 sandbox_ttl
"""

import server.agent.sandbox as sb_mod
from server.core.user_settings import _DEFAULT_SETTINGS


def test_configure_sets_ttl(monkeypatch):
    monkeypatch.setattr(sb_mod, "_SANDBOX_TTL", 86400)
    sb_mod.configure(ttl=3600)
    assert sb_mod._SANDBOX_TTL == 3600


def test_configure_ignores_invalid_values(monkeypatch):
    monkeypatch.setattr(sb_mod, "_SANDBOX_TTL", 86400)
    sb_mod.configure(ttl=0)       # 非正值忽略
    sb_mod.configure(ttl=None)    # 缺省忽略
    sb_mod.configure(ttl=-5)
    assert sb_mod._SANDBOX_TTL == 86400


def test_ttl_expired(monkeypatch):
    monkeypatch.setattr(sb_mod, "_SANDBOX_TTL", 3600)
    entry = {"created_at": 1000.0}

    assert sb_mod._ttl_expired(entry, 1000.0 + 3601) is True
    assert sb_mod._ttl_expired(entry, 1000.0 + 3600) is False   # 恰好到点不算过期
    assert sb_mod._ttl_expired(entry, 1000.0 + 100) is False


def test_ttl_expired_missing_created_at(monkeypatch):
    """旧版池条目没有 created_at 字段时按 0 处理（时钟正常时必然过期，触发重建）。"""
    monkeypatch.setattr(sb_mod, "_SANDBOX_TTL", 3600)
    assert sb_mod._ttl_expired({"last_active": 1.0}, 5000.0) is True


def test_default_settings_contains_sandbox_ttl():
    ex = _DEFAULT_SETTINGS["executor"]
    assert ex["sandbox_ttl"] == 86400
