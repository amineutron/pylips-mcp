"""Outils ambilight_stream_* : flux Ambilight rapide, sans relecture, avec minuteur de securite."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pylips_mcp import server  # noqa: E402

SUPPORTED = {"supportedStyles": [{"styleName": "Lounge light", "algorithms": ["MANUAL_HUE"]}]}
OLD_CONFIG = {"styleName": "FOLLOW_VIDEO", "isExpert": False, "menuSetting": "STANDARD"}


class FakeTimer:
    instances = []

    def __init__(self, interval, function, args=None, kwargs=None):
        self.interval, self.function = interval, function
        self.daemon, self.started, self.cancelled = False, False, False
        FakeTimer.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.function()


class FakeAPI:
    def __init__(self, power="On", mode="internal", config=OLD_CONFIG, ignore_mode_posts=0):
        self.ignore_mode_posts = ignore_mode_posts
        self.sleeps = []
        self.state = {"ambilight/power": {"power": power}, "ambilight/mode": {"current": mode},
                      "ambilight/currentconfiguration": config, "ambilight/supportedstyles": SUPPORTED}
        self.calls = []

    def __call__(self, endpoint, method="GET", body=None, **kw):
        self.calls.append((endpoint, method, body, kw.get("timeout")))
        if method == "POST" and endpoint == "ambilight/mode":
            if self.ignore_mode_posts > 0:
                self.ignore_mode_posts -= 1
            else:
                self.state["ambilight/mode"] = {"current": body["current"]}
        return self.state.get(endpoint, {}) if method == "GET" else {"status": "ok"}

    def posts(self):
        return [(e, b) for e, m, b, _ in self.calls if m == "POST"]


@pytest.fixture
def make_tv(monkeypatch):
    FakeTimer.instances = []

    def build(**kw):
        api = FakeAPI(**kw)
        tv = server.PhilipsTVController("192.0.2.10", "u", "p")
        monkeypatch.setattr(tv, "_api_call", api)
        monkeypatch.setattr(tv, "_timer_factory", FakeTimer)
        monkeypatch.setattr(tv, "_sleep", lambda s: api.sleeps.append(s))
        return tv, api
    return build


def test_constante_watchdog():
    assert server.STREAM_WATCHDOG_S == 15


def test_start_cached_passe_en_manual(make_tv):
    tv, api = make_tv()
    assert tv.ambilight_stream_start("cached").startswith("OK")
    assert api.posts() == [("ambilight/mode", {"current": "manual"})]


def test_start_lounge_ne_change_pas_le_mode(make_tv):
    tv, api = make_tv()
    assert tv.ambilight_stream_start("lounge").startswith("OK")
    assert api.posts() == []


def test_start_allume_un_ambilight_eteint(make_tv):
    tv, api = make_tv(power="Off")
    assert tv.ambilight_stream_start("cached").startswith("OK")
    assert api.posts() == [("ambilight/power", {"power": "On"}), ("ambilight/mode", {"current": "manual"})]
    assert tv.ambilight_stream_level(1, 2, 3) == "OK"


def test_stop_eteint_de_nouveau_ce_qui_etait_eteint(make_tv):
    tv, api = make_tv(power="Off")
    tv.ambilight_stream_start("cached")
    api.calls.clear()
    assert tv.ambilight_stream_stop().startswith("OK")
    posts = api.posts()
    assert posts[0] == ("ambilight/mode", {"current": "internal"})
    assert posts[-1] == ("ambilight/power", {"power": "Off"})
    assert ("ambilight/currentconfiguration", OLD_CONFIG) not in posts


def test_watchdog_eteint_aussi_ce_qui_etait_eteint(make_tv):
    tv, api = make_tv(power="Off")
    tv.ambilight_stream_start("lounge")
    api.calls.clear()
    FakeTimer.instances[-1].fire()
    assert api.posts()[-1] == ("ambilight/power", {"power": "Off"})


def test_stop_ne_coupe_pas_un_ambilight_qui_etait_allume(make_tv):
    tv, api = make_tv(power="On")
    tv.ambilight_stream_start("cached")
    api.calls.clear()
    tv.ambilight_stream_stop()
    assert ("ambilight/power", {"power": "Off"}) not in api.posts()


def test_start_echec_allumage_ne_demarre_rien(make_tv, monkeypatch):
    tv, api = make_tv(power="Off")
    reel = api.__call__
    monkeypatch.setattr(tv, "_api_call", lambda e, m="GET", b=None, **kw:
                        {"error": "refuse"} if (e, m) == ("ambilight/power", "POST") else reel(e, m, b, **kw))
    assert tv.ambilight_stream_start("cached").startswith("Erreur")
    assert tv.ambilight_stream_level(1, 2, 3) == "Erreur: flux Ambilight non demarre"


def test_start_voie_invalide(make_tv):
    tv, api = make_tv()
    assert tv.ambilight_stream_start("x").startswith("Erreur")
    assert api.calls == []


def test_start_lounge_sans_style(make_tv, monkeypatch):
    tv, api = make_tv()
    monkeypatch.setattr(tv, "_color_style", lambda: None)
    assert tv.ambilight_stream_start("lounge").startswith("Erreur")


@pytest.mark.parametrize("rgb", [(256, 0, 0), (0, -1, 0), (0, 0, 300), ("a", 0, 0), (1.5, 0, 0), (True, 0, 0)])
def test_level_valide_les_entiers(make_tv, rgb):
    tv, api = make_tv()
    tv.ambilight_stream_start("cached")
    n = len(api.calls)
    assert tv.ambilight_stream_level(*rgb).startswith("Erreur")
    assert len(api.calls) == n


def test_level_sans_start(make_tv):
    tv, api = make_tv()
    assert tv.ambilight_stream_level(1, 2, 3) == "Erreur: flux Ambilight non demarre"
    assert api.calls == []


def test_level_cached(make_tv):
    tv, api = make_tv()
    tv.ambilight_stream_start("cached")
    api.calls.clear()
    assert tv.ambilight_stream_level(10, 20, 30) == "OK"
    assert api.calls == [("ambilight/cached", "POST", {"r": 10, "g": 20, "b": 30}, 2)]


def test_level_lounge_sans_relecture(make_tv):
    tv, api = make_tv()
    tv.ambilight_stream_start("lounge")
    api.calls.clear()
    assert tv.ambilight_stream_level(255, 0, 0) == "OK"
    assert len(api.calls) == 1
    endpoint, method, body, _ = api.calls[0]
    assert (endpoint, method) == ("ambilight/currentconfiguration", "POST")
    assert body == server.ambilight_color_body(255, 0, 0, None, "Lounge light")


def test_stop_restaure_mode_puis_config(make_tv):
    tv, api = make_tv()
    tv.ambilight_stream_start("cached")
    api.calls.clear()
    assert tv.ambilight_stream_stop().startswith("OK")
    assert api.posts() == [("ambilight/mode", {"current": "internal"}),
                           ("ambilight/currentconfiguration", OLD_CONFIG)]


def test_stop_idempotent(make_tv):
    tv, api = make_tv()
    assert tv.ambilight_stream_stop().startswith("OK")
    assert api.calls == []
    tv.ambilight_stream_start("cached")
    tv.ambilight_stream_stop()
    api.calls.clear()
    assert tv.ambilight_stream_stop().startswith("OK")
    assert api.calls == []


def test_second_start_garde_l_instantane(make_tv):
    tv, api = make_tv(mode="internal")
    tv.ambilight_stream_start("cached")
    api.state["ambilight/mode"] = {"current": "manual"}
    tv.ambilight_stream_start("lounge")
    api.calls.clear()
    tv.ambilight_stream_stop()
    assert api.posts()[0] == ("ambilight/mode", {"current": "internal"})


def test_watchdog_arme_daemon_et_rearme(make_tv):
    tv, api = make_tv()
    tv.ambilight_stream_start("cached")
    tv.ambilight_stream_level(1, 1, 1)
    first = FakeTimer.instances[-1]
    assert first.interval == 15 and first.daemon and first.started
    tv.ambilight_stream_level(2, 2, 2)
    assert first.cancelled and FakeTimer.instances[-1] is not first


def test_watchdog_restaure_comme_stop(make_tv):
    tv, api = make_tv()
    tv.ambilight_stream_start("cached")
    tv.ambilight_stream_level(1, 1, 1)
    api.calls.clear()
    FakeTimer.instances[-1].fire()
    assert api.posts() == [("ambilight/mode", {"current": "internal"}),
                           ("ambilight/currentconfiguration", OLD_CONFIG)]
    assert tv.ambilight_stream_level(1, 1, 1) == "Erreur: flux Ambilight non demarre"


def test_stop_annule_le_minuteur(make_tv):
    tv, api = make_tv()
    tv.ambilight_stream_start("cached")
    tv.ambilight_stream_level(1, 1, 1)
    tv.ambilight_stream_stop()
    assert FakeTimer.instances[-1].cancelled


def test_outils_declares():
    tools = {t.name: t for t in server.list_tools()}
    assert tools["ambilight_stream_start"].model_dump(by_alias=True)["inputSchema"]["required"] == ["voie"]
    assert tools["ambilight_stream_level"].model_dump(by_alias=True)["inputSchema"]["required"] == ["r", "g", "b"]
    assert tools["ambilight_stream_stop"].model_dump(by_alias=True)["inputSchema"]["required"] == []


def test_start_cached_reessaie_quand_la_tv_ignore_le_mode_manuel(make_tv):
    tv, api = make_tv(ignore_mode_posts=2)
    assert tv.ambilight_stream_start("cached").startswith("OK")
    assert [b for e, b in api.posts() if e == "ambilight/mode"] == [{"current": "manual"}] * 3
    assert api.state["ambilight/mode"] == {"current": "manual"}
    assert api.sleeps


def test_start_cached_echoue_si_la_tv_reste_hors_mode_manuel(make_tv):
    tv, api = make_tv(ignore_mode_posts=99)
    assert tv.ambilight_stream_start("cached").startswith("Erreur")
    assert tv.ambilight_stream_level(1, 2, 3) == "Erreur: flux Ambilight non demarre"


def test_start_ambilight_eteint_attend_avant_le_mode_manuel(make_tv):
    tv, api = make_tv(power="Off")
    tv.ambilight_stream_start("cached")
    assert api.sleeps and api.sleeps[0] >= 0.5
