"""get_state expose l'etat du panneau (screenstate) : « On » ou « Off » (mode sound only)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pylips_mcp import server  # noqa: E402


def _tv(monkeypatch, screenstate):
    tv = server.PhilipsTVController("192.0.2.10", "u", "p")
    reponses = {
        "powerstate": {"powerstate": "On"},
        "audio/volume": {"current": 12, "muted": False},
        "ambilight/currentconfiguration": {"styleName": "FOLLOW_VIDEO"},
        "ambilight/power": {"power": "On"},
        "screenstate": screenstate,
    }
    monkeypatch.setattr(tv, "_api_call", lambda endpoint, method="GET", body=None, **kw: reponses[endpoint])
    return tv


@pytest.mark.parametrize("brut,attendu", [({"screenstate": "On"}, "On"), ({"screenstate": "Off"}, "Off")])
def test_get_state_expose_l_etat_du_panneau(monkeypatch, brut, attendu):
    assert _tv(monkeypatch, brut).get_state()["screen"] == attendu


def test_get_state_panneau_illisible_ne_casse_pas_le_reste(monkeypatch):
    state = _tv(monkeypatch, {"error": "timeout"}).get_state()
    assert state["screen"] is None
    assert state["powerstate"] == "On" and state["volume"] == 12
