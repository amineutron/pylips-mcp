"""Entrees de la TV et lecture de ce qu'elle affiche : la source part vers une commande ADB."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pylips_mcp import server  # noqa: E402
from pylips_mcp.server import HDMI_INPUTS, SOURCES, describe_activity  # noqa: E402


def test_les_quatre_entrees_hdmi_et_l_accueil():
    assert SOURCES == ("home", "hdmi1", "hdmi2", "hdmi3", "hdmi4")
    assert HDMI_INPUTS["hdmi1"].endswith("/HW5") and HDMI_INPUTS["hdmi4"].endswith("/HW8")


@pytest.mark.parametrize("paquet, attendu", [
    ("com.google.android.youtube.tv", {"kind": "app", "app": "youtube"}),
    ("com.plexapp.android", {"kind": "app", "app": "plex"}),
    ("org.droidtv.playtv", {"kind": "input", "app": None}),
    ("com.google.android.tvlauncher", {"kind": "home", "app": None}),
    ("com.example.autre", {"kind": "other", "app": None}),
])
def test_describe_activity(paquet, attendu):
    assert describe_activity({"component": {"packageName": paquet, "className": "x"}}) == {**attendu, "package": paquet}


@pytest.mark.parametrize("brut", [{}, {"component": None}, {"component": {}}, None, "texte"])
def test_describe_activity_reponse_vide(brut):
    assert describe_activity(brut)["kind"] == "unknown"


def _tv(monkeypatch, sorties):
    classe = next(c for c in vars(server).values() if isinstance(c, type) and hasattr(c, "set_source"))
    tv = classe.__new__(classe)
    appels = []

    def adb(*args, timeout=8):
        appels.append(args)
        return sorties.get(args[1] if len(args) > 1 else "", (True, "ok"))
    monkeypatch.setattr(tv, "_adb_run", adb, raising=False)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    return tv, appels


@pytest.mark.parametrize("source", ["hdmi5", "", "; reboot", "hdmi1 --es x y", "HDMI"])
def test_source_inconnue_refusee_sans_toucher_la_tv(monkeypatch, source):
    tv, appels = _tv(monkeypatch, {})
    assert tv.set_source(source).startswith("Erreur")
    assert appels == []


def test_hdmi_arrete_le_lecteur_puis_ouvre_l_entree(monkeypatch):
    tv, appels = _tv(monkeypatch, {})
    assert tv.set_source("HDMI1") == "Entree HDMI1 affichee"
    assert appels[0] == ("shell", "am", "force-stop", "org.droidtv.playtv")
    assert appels[1][-1] == HDMI_INPUTS["hdmi1"] and appels[1][:3] == ("shell", "am", "start")


def test_home_envoie_la_touche_accueil(monkeypatch):
    tv, appels = _tv(monkeypatch, {})
    assert tv.set_source("home") == "Menu d'accueil affiche"
    assert appels == [("shell", "input", "keyevent", "KEYCODE_HOME")]
