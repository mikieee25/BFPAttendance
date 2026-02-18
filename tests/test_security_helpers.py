from flask import Flask

from routes.auth import _is_safe_redirect_url
from routes.profile import _database_config_from_url
from utils import validate_password


def test_validate_password_rejects_weak_passwords():
    ok, msg = validate_password("weak")
    assert ok is False
    assert "at least 8" in msg.lower()


def test_validate_password_accepts_strong_password():
    ok, _ = validate_password("StrongPass123")
    assert ok is True


def test_safe_redirect_url_blocks_external_hosts():
    app = Flask(__name__)
    with app.test_request_context("/auth/login", base_url="http://localhost:5000"):
        assert _is_safe_redirect_url("/dashboard") is True
        assert _is_safe_redirect_url("http://evil.example.com/phish") is False


def test_database_url_parser_mysql():
    cfg = _database_config_from_url("mysql+pymysql://user:pass@127.0.0.1:3306/mydb")
    assert cfg["host"] == "127.0.0.1"
    assert cfg["port"] == 3306
    assert cfg["user"] == "user"
    assert cfg["password"] == "pass"
    assert cfg["database"] == "mydb"
