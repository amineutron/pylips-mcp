"""Sequence d'allumage de la TV : elle doit aboutir, et etre verifiee.

Regression 2026-08-12 : depuis la veille profonde, power_on envoyait le
Wake-on-LAN puis rendait la main ("attends 15-20s") sans jamais terminer
l'allumage ; et le chemin veille reseau repondait "TV allumee" sans verifier
l'etat reel.

Ce correctif n'avait jamais ete remonte dans ce depot : il ne vivait que dans
une copie locale, ou aucune CI ne le jouait.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pylips_mcp.server import PhilipsTVController  # noqa: E402


@pytest.fixture()
def controller():
    tv = PhilipsTVController(host="192.0.2.1", user="u", password="p",
                             mac="00:11:22:33:44:55")
    return tv


def scripted_api(responses):
    """_api_call simule : rejoue une liste de reponses puis repete la derniere."""
    calls = []

    def fake(path, method="GET", body=None, **kwargs):
        calls.append((path, method, body))
        index = min(len(calls) - 1, len(responses) - 1)
        return responses[index]

    fake.calls = calls
    return fake


class TestPowerOn:
    def test_deja_allumee(self, controller):
        controller._api_call = scripted_api([{"powerstate": "On"}])
        assert controller.power_on() == "TV deja allumee"

    def test_veille_reseau_sequence_complete_et_verifiee(self, controller):
        controller._api_call = scripted_api([
            {"powerstate": "Standby"},   # check initial
            {},                          # input/key Standby
            {},                          # POST powerstate On
            {"powerstate": "On"},        # confirmation
        ])
        assert controller.power_on() == "TV allumee"
        paths = [c[0] for c in controller._api_call.calls]
        assert paths == ["powerstate", "input/key", "powerstate", "powerstate"]
        assert controller._api_call.calls[2] == ("powerstate", "POST",
                                                 {"powerstate": "On"})

    def test_veille_profonde_wol_puis_api(self, controller):
        wol_sent = []
        controller._send_wol = lambda: wol_sent.append(True)
        controller._api_call = scripted_api([
            {"error": "timeout"},        # injoignable
            {"powerstate": "Standby"},   # reveil reseau apres WoL
            {},                          # input/key
            {},                          # POST On
            {"powerstate": "On"},        # confirmation
        ])
        result = controller.power_on()
        assert wol_sent, "le WoL doit etre envoye"
        assert result == "TV allumee (via Wake-on-LAN + API)"

    def test_veille_profonde_wol_reveil_deja_on(self, controller):
        controller._send_wol = lambda: None
        controller._api_call = scripted_api([
            {"error": "timeout"},
            {"powerstate": "On"},
        ])
        assert controller.power_on() == "TV allumee (reveillee par Wake-on-LAN)"

    def test_wol_sans_reponse_erreur_claire(self, controller):
        controller._send_wol = lambda: None
        controller._wait_reachable = lambda deadline_s: None
        controller._api_call = scripted_api([{"error": "timeout"}])
        with pytest.raises(RuntimeError, match="coupee du secteur"):
            controller.power_on()

    def test_sequence_sans_effet_erreur_honnete(self, controller):
        controller._confirm_on = lambda deadline_s: "Standby"
        controller._api_call = scripted_api([
            {"powerstate": "Standby"}, {}, {},
        ])
        with pytest.raises(RuntimeError, match="reste en etat 'Standby'"):
            controller.power_on()

    def test_pas_de_mac_erreur_claire(self):
        tv = PhilipsTVController(host="192.0.2.1", user="u", password="p", mac="")
        tv._api_call = scripted_api([{"error": "timeout"}])
        with pytest.raises(RuntimeError, match="aucune MAC"):
            tv.power_on()


class TestHelpers:
    def test_wait_reachable_retourne_l_etat(self, controller):
        controller._api_call = scripted_api([{"powerstate": "Standby"}])
        assert controller._wait_reachable(deadline_s=1.0) == {"powerstate": "Standby"}

    def test_wait_reachable_timeout(self, controller):
        controller._api_call = scripted_api([{"error": "x"}])
        assert controller._wait_reachable(deadline_s=0.1) is None

    def test_confirm_on_immediat(self, controller):
        controller._api_call = scripted_api([{"powerstate": "On"}])
        assert controller._confirm_on(deadline_s=1.0) == "On"

    def test_confirm_on_rapporte_le_dernier_etat(self, controller):
        controller._api_call = scripted_api([{"powerstate": "StandbyKeep"}])
        assert controller._confirm_on(deadline_s=0.1) == "StandbyKeep"
