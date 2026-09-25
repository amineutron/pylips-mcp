"""Paquet pylips_mcp : ligne de commande, certificat embarque, aucune dependance a pylips.

Avant la 0.3.0, le wheel installait un module `server` et un fichier
`tpvision_ca.pem` a la racine de site-packages (conflit avec denon-mcp et
catt-mcp, eux aussi `server`), et le serveur tentait d'importer pylips, un
depot non package, sans jamais s'en servir.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pylips_mcp import server  # noqa: E402


def test_cli_help_sans_configuration(capsys):
    with pytest.raises(SystemExit) as exc:
        server.cli(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "TV_HOST" in out and "PYLIPS_TLS_FINGERPRINT" in out


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        server.cli(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("pylips-mcp ")


def test_certificat_dans_le_paquet():
    assert server._TPVISION_CERT_BUNDLE.parent == Path(server.__file__).parent
    assert server._TPVISION_CERT_BUNDLE.is_file()


def test_aucune_reference_a_la_bibliotheque_pylips():
    source = Path(server.__file__).read_text(encoding="utf-8")
    assert "from pylips import" not in source and "PYLIPS_PATH" not in source


def test_python_m_pylips_mcp_version():
    out = subprocess.run([sys.executable, "-m", "pylips_mcp", "--version"], cwd=ROOT,
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0 and out.stdout.startswith("pylips-mcp ")
