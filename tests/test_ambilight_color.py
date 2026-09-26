"""Outil ambilight_color (#7) : couleur fixe RVB -> configuration JointSpace.

Lyra envoyait deja `tv.ambilight_color` avec r/g/b pour « ambilight en rouge »,
mais l'outil n'existait pas : chaque demande de couleur echouait.
Corps de requete repris de pylips (available_commands.json, ambilight_color).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pylips_mcp import server  # noqa: E402


@pytest.mark.parametrize("rgb,expected", [
    ((255, 0, 0), {"hue": 0, "saturation": 255, "brightness": 255}),      # rouge
    ((0, 255, 0), {"hue": 85, "saturation": 255, "brightness": 255}),     # vert : 120 deg
    ((0, 0, 255), {"hue": 170, "saturation": 255, "brightness": 255}),    # bleu : 240 deg
    ((255, 255, 255), {"hue": 0, "saturation": 0, "brightness": 255}),   # blanc
    ((128, 0, 0), {"hue": 0, "saturation": 255, "brightness": 128}),      # rouge sombre
])
def test_rgb_vers_teinte_saturation_luminosite(rgb, expected):
    assert server.rgb_to_ambilight_color(*rgb) == expected


def test_luminosite_imposee():
    assert server.rgb_to_ambilight_color(255, 0, 0, brightness=40)["brightness"] == 40


@pytest.mark.parametrize("args", [(256, 0, 0), (0, -1, 0), (0, 0, 300), (10, 10, 10, 256)])
def test_valeurs_hors_bornes_refusees(args):
    with pytest.raises(ValueError):
        server.rgb_to_ambilight_color(*args)


# Reponses reelles de la 55OLED705/12 (2026-09-26) : pas de FOLLOW_COLOR, la couleur
# fixe passe par « Lounge light » + MANUAL_HUE (pixels emis mesures : 255/0/0 pour du rouge).
SUPPORTED_OLED705 = {"supportedStyles": [{}, {}, {"styleName": "FOLLOW_AUDIO", "algorithms": ["VU_METER", "PARTY"]},
                                          {"styleName": "Lounge light", "algorithms": ["MANUAL_HUE", "AUTOMATIC_HUE"]}, {}]}
APPLIED_OLED705 = {"styleName": "Lounge light", "isExpert": True, "colorSettings": {
    "color": {"hue": 0, "saturation": 255, "brightness": 255}, "colorDelta": {"hue": 0, "saturation": 0, "brightness": 0},
    "speed": 255, "algorithm": "MANUAL_HUE"}}
IGNORED = {"styleName": "FOLLOW_VIDEO", "isExpert": False, "menuSetting": "STANDARD"}


@pytest.mark.parametrize("supported,expected", [
    (SUPPORTED_OLED705, "Lounge light"),
    ({"supportedStyles": [{"styleName": "Lounge light", "algorithms": ["MANUAL_HUE"]},
                          {"styleName": "FOLLOW_COLOR", "algorithms": ["MANUAL_HUE"]}]}, "FOLLOW_COLOR"),
    ({"supportedStyles": [{"styleName": "FOLLOW_AUDIO", "algorithms": ["VU_METER"]}]}, None),
    ({"error": "Timeout - TV may be off"}, None),
    ("pas un dict", None),
])
def test_style_couleur_detecte(supported, expected):
    assert server.color_style_from_supported(supported) == expected


def test_corps_de_requete_manual_hue():
    body = server.ambilight_color_body(255, 0, 0, style="Lounge light")
    assert body["styleName"] == "Lounge light" and body["algorithm"] == "MANUAL_HUE" and body["isExpert"] is True
    assert body["colorSettings"]["color"] == {"hue": 0, "saturation": 255, "brightness": 255}
    assert body["colorSettings"]["colorDelta"] == {"hue": 0, "saturation": 0, "brightness": 0}


@pytest.mark.parametrize("config,ok", [
    (APPLIED_OLED705, True),
    ({**APPLIED_OLED705, "colorSettings": {"algorithm": "AUTOMATIC_HUE"}}, False),
    (IGNORED, False),
    ({"error": "HTTP 500"}, False),
])
def test_couleur_appliquee_ou_ignoree(config, ok):
    assert server.color_applied(config, "Lounge light") is ok


def test_outil_declare_et_annote():
    tools = {t.name: t for t in server.list_tools()}
    tool = tools["ambilight_color"]
    assert tool.model_dump(by_alias=True)["inputSchema"]["required"] == ["r", "g", "b"]
    hints = tool.annotations.model_dump(by_alias=True)
    assert hints["readOnlyHint"] is False and hints["idempotentHint"] is True and hints["destructiveHint"] is False


class FakeTV:
    """Rejoue les reponses de la TV ; `ignore=True` imite le bug d'origine (200 mais rien ne change)."""

    def __init__(self, supported=SUPPORTED_OLED705, ignore=False):
        self.supported, self.ignore, self.calls, self.config = supported, ignore, [], IGNORED

    def __call__(self, endpoint, method="GET", body=None, **kw):
        self.calls.append((endpoint, method, body))
        if endpoint == "ambilight/supportedstyles":
            return self.supported
        if method == "POST":
            if not self.ignore:
                self.config = {**APPLIED_OLED705, "styleName": body["styleName"]}
            return {"status": "ok"}
        return self.config


def _tv(monkeypatch, fake):
    tv = server.PhilipsTVController("192.0.2.10", "u", "p")
    monkeypatch.setattr(tv, "_api_call", fake)
    return tv


def test_controleur_applique_et_verifie(monkeypatch):
    fake = FakeTV()
    tv = _tv(monkeypatch, fake)
    assert tv.ambilight_color(0, 0, 255) == "Ambilight couleur fixe : RVB(0, 0, 255)"
    posts = [c for c in fake.calls if c[1] == "POST"]
    assert posts[0][2]["styleName"] == "Lounge light" and posts[0][2]["colorSettings"]["color"]["hue"] == 170


def test_regression_tv_qui_ignore_la_couleur(monkeypatch):
    # 2026-09-25 : FOLLOW_COLOR renvoyait 200 et la TV restait en FOLLOW_VIDEO -> faux succes
    tv = _tv(monkeypatch, FakeTV(ignore=True))
    out = tv.ambilight_color(255, 0, 0)
    assert out.startswith("Erreur") and "FOLLOW_VIDEO" in out


def test_style_lu_une_seule_fois(monkeypatch):
    fake = FakeTV()
    tv = _tv(monkeypatch, fake)
    tv.ambilight_color(255, 0, 0)
    tv.ambilight_color(0, 255, 0)
    assert sum(1 for c in fake.calls if c[0] == "ambilight/supportedstyles") == 1


def test_styles_illisibles_repli_sans_memoriser(monkeypatch):
    fake = FakeTV(supported={"error": "Timeout - TV may be off"})
    tv = _tv(monkeypatch, fake)
    assert tv.ambilight_color(255, 0, 0).startswith("Ambilight")
    assert [c for c in fake.calls if c[1] == "POST"][0][2]["styleName"] == server.DEFAULT_COLOR_STYLE
    tv.ambilight_color(255, 0, 0)
    assert sum(1 for c in fake.calls if c[0] == "ambilight/supportedstyles") == 2


def test_controleur_refuse_une_couleur_invalide(monkeypatch):
    tv = _tv(monkeypatch, lambda *a, **k: pytest.fail("aucun appel attendu"))
    assert tv.ambilight_color(300, 0, 0).startswith("Erreur")
