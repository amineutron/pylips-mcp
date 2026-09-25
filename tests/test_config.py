"""load_config() : l'environnement seul doit suffire (aucun fichier YAML requis)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pylips_mcp import server  # noqa: E402


def test_env_only_without_any_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # pas de ./config.yaml
    monkeypatch.setattr(server, "__file__", str(tmp_path / "deep" / "er" / "server.py"))
    monkeypatch.delenv("PYLIPS_CONFIG", raising=False)
    monkeypatch.setenv("TV_HOST", "192.0.2.10")
    monkeypatch.setenv("TV_USER", "u")
    monkeypatch.setenv("TV_PASS", "p")
    cfg = server.load_config()
    assert cfg["tv"] == {"host": "192.0.2.10", "user": "u", "pass": "p"}


def test_yaml_then_secrets_next_to_it(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("tv:\n  host: 192.0.2.11\n")
    (tmp_path / "secrets.yaml").write_text("tv:\n  user: su\n  pass: sp\n")
    for k in ("TV_HOST", "TV_USER", "TV_PASS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PYLIPS_CONFIG", str(tmp_path / "config.yaml"))
    cfg = server.load_config()
    assert (cfg["tv"]["host"], cfg["tv"]["user"], cfg["tv"]["pass"]) == ("192.0.2.11", "su", "sp")
