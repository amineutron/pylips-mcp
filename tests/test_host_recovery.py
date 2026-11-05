"""IP de la TV changee (DHCP) apres le demarrage du serveur.

Regression 2026-10-30 : le serveur lisait l'hote une seule fois ; apres un
changement d'IP toutes les touches de telecommande echouaient (« No route to
host ») jusqu'au redemarrage du demon.
"""

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pylips_mcp import server  # noqa: E402
from pylips_mcp.server import PhilipsTVController  # noqa: E402


class FauxReponse:
    status_code = 200
    text = '{"powerstate": "On"}'

    def json(self):
        return {"powerstate": "On"}


class FausseSession:
    """Echoue sur l'ancienne IP, repond sur la nouvelle."""

    def __init__(self, bonne_ip):
        self.bonne_ip = bonne_ip
        self.urls = []

    def get(self, url, **kw):
        self.urls.append(url)
        if self.bonne_ip not in url:
            raise requests.exceptions.ConnectionError("No route to host")
        return FauxReponse()

    post = get


@pytest.fixture()
def tv(monkeypatch):
    controleur = PhilipsTVController(host="192.0.2.1", user="u", password="p")
    controleur._session = FausseSession("192.0.2.9")
    monkeypatch.setattr(server, "HOST_LOCATOR", Path("/inexistant"))
    return controleur


def config_avec(host):
    return lambda: {"tv": {"host": host}}


def test_adopte_la_nouvelle_ip_de_la_config_et_rejoue(tv, monkeypatch):
    monkeypatch.setattr(server, "load_config", config_avec("192.0.2.9"))
    assert tv._api_call("powerstate") == {"powerstate": "On"}
    assert tv.host == "192.0.2.9"


def test_config_inchangee_rend_l_erreur_sans_boucler(tv, monkeypatch):
    monkeypatch.setattr(server, "load_config", config_avec("192.0.2.1"))
    res = tv._api_call("powerstate")
    assert "No route to host" in res["error"]
    assert len(tv._session.urls) == 1


def test_une_tv_eteinte_ne_relance_pas_la_recherche_a_chaque_appel(tv, monkeypatch):
    appels = []
    monkeypatch.setattr(server, "load_config",
                        lambda: appels.append(1) or {"tv": {"host": "192.0.2.1"}})
    tv._api_call("powerstate")
    tv._api_call("powerstate")
    assert len(appels) == 1


def test_denon_retrouve_apres_changement_d_ip(monkeypatch):
    """Meme panne que la TV : l'ampli (redirection du volume ARC) gardait l'ancienne IP."""
    ctrl = PhilipsTVController(host="192.0.2.1", user="u", password="p", denon_host="192.0.2.50")
    monkeypatch.setattr(server, "HOST_LOCATOR", Path("/inexistant"))
    monkeypatch.setattr(server, "load_config", lambda: {"denon": {"host": "192.0.2.51"}})
    vus = []

    def faux(host, port, command, timeout=3):
        vus.append(host)
        return "MV44" if host == "192.0.2.51" else "ERROR: No route to host"
    monkeypatch.setattr(server, "send_denon_command", faux)
    assert ctrl._denon("MV?") == "MV44"
    assert vus == ["192.0.2.50", "192.0.2.51"] and ctrl.denon_host == "192.0.2.51"
