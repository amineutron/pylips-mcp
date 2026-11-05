"""Allumage depuis la veille profonde : le WoL reveille Android mais pas JointSpace.

Regression 2026-10-30 : apres le paquet magique, ADB repondait (ecran
« Asleep ») alors que JointSpace (1926) restait muet ; power_on n'attendait
que JointSpace et concluait « coupee du secteur ».
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pylips_mcp.server import PhilipsTVController  # noqa: E402


@pytest.fixture()
def tv(monkeypatch):
    c = PhilipsTVController(host="192.0.2.1", user="u", password="p", mac="aa:bb:cc:dd:ee:ff")
    monkeypatch.setattr(c, "_send_wol", lambda: None)
    monkeypatch.setattr(c, "_api_call", lambda *a, **k: {"error": "refused"})
    return c


def test_adb_repond_mais_jointspace_muet_reveille_l_ecran_et_le_dit(tv, monkeypatch):
    commandes = []
    monkeypatch.setattr(tv, "_wait_reachable", lambda deadline_s: None)
    monkeypatch.setattr(tv, "_adb_run", lambda *a, **k: commandes.append(a) or (True, "ok"))
    with pytest.raises(RuntimeError) as e:
        tv.power_on()
    assert ("shell", "input", "keyevent", "KEYCODE_WAKEUP") in commandes
    assert "JointSpace" in str(e.value)
    assert "secteur" not in str(e.value)


def test_screen_off_coupe_le_panneau_par_screenstate(tv, monkeypatch):
    """Regression 2026-10-31 : « son seul » repondait ok sans rien eteindre."""
    appels = []
    monkeypatch.setattr(
        tv, "_api_call",
        lambda ep, method="GET", body=None, **k: appels.append((ep, body)) or {},
    )
    tv.screen_off()
    assert ("screenstate", {"screenstate": "Off"}) in appels
    tv.screen_on()
    assert ("screenstate", {"screenstate": "On"}) in appels


def test_ni_jointspace_ni_adb_garde_le_message_secteur(tv, monkeypatch):
    monkeypatch.setattr(tv, "_wait_reachable", lambda deadline_s: None)
    monkeypatch.setattr(tv, "_adb_run", lambda *a, **k: (False, "ADB timeout"))
    with pytest.raises(RuntimeError, match="secteur"):
        tv.power_on()
