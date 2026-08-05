# -*- coding: utf-8 -*-
"""JWT secret 强校验测试。

借鉴 JavaGuide 安全章节 + OWASP JWT 规范。
"""
import pytest


class TestJWTSecretSecure:
    """AuthConfig.is_secure 单元测试。"""

    def test_default_secret_is_insecure(self):
        """默认值 'dev-insecure-change-me' 不安全。"""
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="dev-insecure-change-me")
        assert c.is_secure is False

    def test_short_secret_is_insecure(self):
        """< 32 字符的 secret 不安全。"""
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="short_secret_123")
        assert len(c.jwt_secret) < 32
        assert c.is_secure is False

    def test_long_only_alpha_is_insecure(self):
        """只有字母 (无数字/特殊) 视为弱。"""
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="a" * 40)  # 40 个字母
        assert c.is_secure is False

    def test_long_alpha_digit_is_secure(self):
        """字母+数字 >= 32 字符 = 安全。"""
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="abcdef1234567890" * 3)  # 48 字符，字母+数字
        assert len(c.jwt_secret) >= 32
        assert c.is_secure is True

    def test_long_alpha_special_is_secure(self):
        """字母+特殊字符 = 安全。"""
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="abcdef-_-_-_-_-_-_-_-_-_-_-_-_12345")  # 字母+特殊
        assert c.is_secure is True

    def test_long_digit_special_is_secure(self):
        """数字+特殊字符 = 安全。"""
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="1234567890" * 3 + "!@#$%^&*()" * 3)
        assert c.is_secure is True

    def test_exactly_32_chars_alpha_digit_secure(self):
        """刚好 32 字符（边界值）。"""
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="a" * 16 + "1" * 16)  # 32 字符
        assert len(c.jwt_secret) == 32
        assert c.is_secure is True

    def test_31_chars_insecure(self):
        """31 字符 = 不安全。"""
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="a" * 16 + "1" * 15)  # 31 字符
        assert c.is_secure is False


class TestValidateForEnv:
    """AuthConfig.validate_for_env 启动校验测试。"""

    def test_default_raises(self):
        """默认值在任何 env 都 fail-fast。"""
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="dev-insecure-change-me")
        with pytest.raises(RuntimeError) as exc:
            c.validate_for_env("dev")
        assert "默认值" in str(exc.value) or "JWT_SECRET" in str(exc.value)

    def test_short_secret_raises(self):
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="short_weak")
        with pytest.raises(RuntimeError) as exc:
            c.validate_for_env("dev")
        assert "长度" in str(exc.value)

    def test_weak_charset_raises(self):
        """单一字符类 = 弱。"""
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="a" * 40)  # 全字母
        with pytest.raises(RuntimeError) as exc:
            c.validate_for_env("dev")
        assert "字符类" in str(exc.value) or "过弱" in str(exc.value)

    def test_strong_secret_passes_dev(self):
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="k8sH_2nA-p4qR9mZ!xT_wL7vY3cE6bN1sJ5gU8hD0fP")  # 强
        # 不抛错
        c.validate_for_env("dev")

    def test_strong_secret_passes_production(self):
        from app.core.config import AuthConfig
        c = AuthConfig(jwt_secret="k8sH_2nA-p4qR9mZ!xT_wL7vY3cE6bN1sJ5gU8hD0fP")
        c.validate_for_env("production")


class TestEnvDefaultSecret:
    """测试默认 dev secret 启动时 fail-fast。"""

    def test_env_with_default_secret_fails(self, monkeypatch):
        """JWT_SECRET 没设 env → 默认 dev 值 → 启动失败。"""
        monkeypatch.delenv("JWT_SECRET", raising=False)
        from app.core.config import AuthConfig
        # 模拟：env 没设 → 走 default
        import os
        if "JWT_SECRET" not in os.environ:
            os.environ["JWT_SECRET"] = "dev-insecure-change-me"
        c = AuthConfig(jwt_secret=os.environ.get("JWT_SECRET", ""))
        with pytest.raises(RuntimeError):
            c.validate_for_env("dev")
