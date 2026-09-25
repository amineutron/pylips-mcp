"""Regression : l'epinglage TLS doit reellement s'appliquer (le pinning etait neutralise par verify=False)."""
import hashlib
import ssl
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pylips_mcp import server  # noqa: E402

BUNDLE = Path(server.__file__).parent / "tpvision_ca.pem"


def _leaf_sha256() -> str:
    pem = BUNDLE.read_text()
    end = "-----END CERTIFICATE-----"
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem.split(end)[0] + end + "\n")).hexdigest()


def test_bundle_leaf_fingerprint_matches_first_certificate():
    assert server.bundle_leaf_fingerprint() == _leaf_sha256()


def test_session_pins_the_bundle_fingerprint(monkeypatch):
    pytest.importorskip("requests")
    monkeypatch.delenv("PYLIPS_TLS_PIN", raising=False)
    monkeypatch.delenv("PYLIPS_TLS_FINGERPRINT", raising=False)
    session = server._build_tv_session()
    kw = session.get_adapter("https://192.0.2.10/").poolmanager.connection_pool_kw
    assert kw.get("assert_fingerprint") == _leaf_sha256()
    assert kw["ssl_context"].verify_mode == ssl.CERT_NONE


def test_override_and_disable(monkeypatch):
    pytest.importorskip("requests")
    monkeypatch.setenv("PYLIPS_TLS_FINGERPRINT", "AA:BB:cc")
    assert server.expected_tv_fingerprint() == "aabbcc"
    monkeypatch.setenv("PYLIPS_TLS_PIN", "0")
    assert server.expected_tv_fingerprint() is None
