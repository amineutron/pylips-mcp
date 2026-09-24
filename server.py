#!/usr/bin/env python3
"""
MCP Server wrapper pour pylips - Controle TV Philips.

Ce serveur expose les commandes pylips via le protocole MCP pour
permettre a Lyra de controler la TV Philips avec une latence minimale.

Usage:
    python server.py

Configuration:
    Les credentials TV sont lus depuis config.yaml ou variables d'env:
    - TV_HOST: IP de la TV
    - TV_USER: User genere par pairing
    - TV_PASS: Password genere par pairing
"""

import asyncio
import json
import os
import re
import ssl
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# TLS vers la TV Philips : epinglage par empreinte (certificate pinning)
#
# Les firmwares Philips embarquent une chaine PKI TP Vision de 2015 signee en
# SHA1. OpenSSL 3 (et la politique crypto de Fedora/RHEL) refuse ces
# signatures : la verification classique par autorite echoue, meme avec le
# bundle tpvision_ca.pem et SECLEVEL=0. Un certificat Let's Encrypt est
# impossible pour l'IP locale d'une TV.
#
# Ce que fait ce module :
#   - la verification par autorite est desactivee (CERT_NONE) car impossible ;
#   - a la place, l'empreinte SHA-256 du certificat presente par la TV doit
#     etre EGALE a celle du certificat feuille embarque dans tpvision_ca.pem
#     (verification faite par urllib3 via assert_fingerprint, apres la poignee
#     de main TLS : un intermediaire ne peut pas presenter ce certificat sans
#     sa cle privee) ;
#   - PYLIPS_TLS_FINGERPRINT=<sha256 hex> permet d'epingler une autre TV ;
#   - PYLIPS_TLS_PIN=0 desactive l'epinglage (un avertissement est journalise).
# ---------------------------------------------------------------------------

_TPVISION_CERT_BUNDLE = Path(__file__).parent / "tpvision_ca.pem"
_TLS_WARNED = False


def bundle_leaf_fingerprint() -> str | None:
    """Empreinte SHA-256 (hex) du premier certificat du bundle TP Vision.

    Ce premier certificat est le certificat feuille (CN restfultv.tpvision.com)
    que presentent les TV Philips JointSpace ; None si le bundle est absent.
    """
    import hashlib
    try:
        pem = _TPVISION_CERT_BUNDLE.read_text()
        end = "-----END CERTIFICATE-----"
        first = pem.split(end)[0] + end + "\n"
        der = ssl.PEM_cert_to_DER_cert(first)
        return hashlib.sha256(der).hexdigest()
    except (OSError, ValueError):
        return None


def expected_tv_fingerprint() -> str | None:
    """Empreinte a exiger : variable PYLIPS_TLS_FINGERPRINT, sinon le bundle, sinon None."""
    if os.environ.get("PYLIPS_TLS_PIN", "1") == "0":
        return None
    override = os.environ.get("PYLIPS_TLS_FINGERPRINT", "").replace(":", "").strip().lower()
    return override or bundle_leaf_fingerprint()


def _build_tv_session():
    """Retourne une requests.Session dont les connexions HTTPS vers la TV sont epinglees."""
    global _TLS_WARNED
    import requests
    from requests.adapters import HTTPAdapter

    session = requests.Session()
    fingerprint = expected_tv_fingerprint()
    if fingerprint is None and not _TLS_WARNED:
        _TLS_WARNED = True
        print("pylips-mcp: TLS pinning disabled (no fingerprint): the TV certificate is NOT verified",
              file=sys.stderr)

    try:
        from urllib3.util.ssl_ import create_urllib3_context

        class _TPVisionAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                ctx = create_urllib3_context()
                ctx.set_ciphers("DEFAULT@SECLEVEL=0")  # chaine SHA1 de 2015
                ctx.check_hostname = False              # le CN n'est pas l'IP de la TV
                ctx.verify_mode = ssl.CERT_NONE         # la verification par CA est impossible (SHA1)
                kwargs["ssl_context"] = ctx
                if fingerprint:
                    kwargs["assert_fingerprint"] = fingerprint  # verifie apres la poignee de main
                return super().init_poolmanager(*args, **kwargs)

        session.mount("https://", _TPVisionAdapter())
    except Exception as exc:  # urllib3 manquant ou incompatible : pas d'epinglage possible
        if not _TLS_WARNED:
            _TLS_WARNED = True
            print(f"pylips-mcp: TLS pinning unavailable ({exc}): the TV certificate is NOT verified",
                  file=sys.stderr)

    return session

# Bibliotheque pylips (https://github.com/eslavnov/pylips) : soit installee dans l'environnement,
# soit un clone local indique par PYLIPS_PATH. Aucun chemin par defaut.
PYLIPS_PATH = os.environ.get("PYLIPS_PATH", "")
if PYLIPS_PATH and os.path.isdir(PYLIPS_PATH):
    sys.path.insert(0, PYLIPS_PATH)

try:
    from mcp.server import Server, ServerRequestContext
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        CallToolRequestParams,
        CallToolResult,
        ListToolsResult,
        PaginatedRequestParams,
        TextContent,
        Tool,
        ToolAnnotations,
    )
except ImportError:
    print("Error: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)


def load_config() -> dict:
    """Charge la configuration TV et Denon depuis config.yaml ou variables d'env."""
    config = {
        "tv": {
            "host": os.environ.get("TV_HOST", ""),
            "user": os.environ.get("TV_USER", ""),
            "pass": os.environ.get("TV_PASS", ""),
        },
        "denon": {
            "host": os.environ.get("DENON_HOST", ""),
            "port": int(os.environ.get("DENON_PORT", "23")),
        }
    }

    # Ordre de resolution : variables d'environnement, puis YAML (PYLIPS_CONFIG, ./config.yaml,
    # config.yaml a cote du serveur, ou celui de Lyra si le serveur vit dans son arborescence).
    candidates = [Path(p) for p in (os.environ.get("PYLIPS_CONFIG", ""),) if p]
    candidates += [Path.cwd() / "config.yaml", Path(__file__).parent / "config.yaml",
                   Path(__file__).parent.parent.parent / "config.yaml"]
    config_path = next((c for c in candidates if c.exists()), None)
    if config_path is not None and not config["tv"]["host"]:
        try:
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f)

            # TV config
            tv_cfg = cfg.get("tv", {})
            config["tv"]["host"] = tv_cfg.get("host", config["tv"]["host"])
            config["tv"]["user"] = tv_cfg.get("user", config["tv"]["user"])
            config["tv"]["pass"] = tv_cfg.get("pass", config["tv"]["pass"])
            config["tv"]["mac"] = tv_cfg.get("mac", "")

            # Denon config (pour redirection volume HDMI ARC)
            denon_cfg = cfg.get("denon", {})
            config["denon"]["host"] = denon_cfg.get("host", config["denon"]["host"])
            config["denon"]["port"] = denon_cfg.get("port", config["denon"]["port"])
        except Exception as e:
            print(f"Warning: Could not load config.yaml: {e}", file=sys.stderr)

    # Surcharger avec secrets.yaml si present a cote du config.yaml retenu (les identifiants
    # ne sont pas dans config.yaml). Sans fichier de config (tout vient de l'environnement),
    # il n'y a rien a lire.
    secrets_path = config_path.parent / "secrets.yaml" if config_path is not None else None
    if secrets_path is not None and secrets_path.exists():
        try:
            import yaml
            with open(secrets_path) as f:
                sec = yaml.safe_load(f) or {}
            tv_sec = sec.get("tv", {})
            if tv_sec.get("user"):
                config["tv"]["user"] = tv_sec["user"]
            if tv_sec.get("pass"):
                config["tv"]["pass"] = tv_sec["pass"]
        except Exception as e:
            print(f"Warning: Could not load secrets.yaml: {e}", file=sys.stderr)

    return config


# Motifs d'ID YouTube, partages par les deux chemins (ADB et catt).
# Ils etaient copies-colles dans chaque methode : un correctif sur l'un
# n'atteignait pas l'autre.
_YOUTUBE_ID_PATTERNS = (
    r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
    r'^([a-zA-Z0-9_-]{11})$',
)


def extract_video_id(video: str) -> Optional[str]:
    """Extrait l'ID d'une video YouTube, ou None si l'entree n'est pas reconnue.

    La validation est obligatoire avant tout usage : l'ID finit dans une
    commande lancee sur la TV.
    """
    for pattern in _YOUTUBE_ID_PATTERNS:
        match = re.search(pattern, video)
        if match:
            return match.group(1)
    return None


def send_denon_command(host: str, port: int, command: str, timeout: int = 3) -> str:
    """Envoie une commande au Denon AVR (helper pour redirection HDMI ARC).

    Args:
        host: IP du Denon
        port: Port telnet (default: 23)
        command: Commande Denon (ex: "MV44", "MVUP")
        timeout: Timeout en secondes

    Returns:
        Reponse brute du Denon ou message d'erreur
    """
    import socket
    import time

    if not host:
        return "ERROR: Denon not configured"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)

    try:
        sock.connect((host, port))
        sock.send(f"{command}\r".encode('ascii'))
        time.sleep(0.3)
        response = sock.recv(1024).decode('ascii', errors='ignore')
        sock.close()
        return response.strip()
    except socket.timeout:
        return "ERROR: Timeout - Denon may be off"
    except Exception as e:
        return f"ERROR: {str(e)}"


class PhilipsTVController:
    """Controleur pour TV Philips via pylips."""

    def __init__(self, host: str, user: str, password: str, denon_host: str = "", denon_port: int = 23, mac: str = ""):
        self.host = host
        self.user = user
        self.password = password
        self.denon_host = denon_host
        self.denon_port = denon_port
        self.mac = mac  # MAC address pour Wake-on-LAN
        self._pylips = None
        self._initialized = False
        self._screen_muted = False  # Etat du mute ecran (toggle local)
        self._session = _build_tv_session()  # Session HTTP avec cert TP Vision

    def _init_pylips(self):
        """Initialise pylips de maniere paresseuse."""
        if self._initialized:
            return

        try:
            # Importer pylips
            from pylips import Pylips
            self._pylips = Pylips(
                host=self.host,
                user=self.user,
                password=self.password
            )
            self._initialized = True
        except ImportError:
            # Fallback: utiliser requests directement
            print("pylips not found, using direct API", file=sys.stderr)
            self._initialized = True
        except Exception as e:
            print(f"Error initializing pylips: {e}", file=sys.stderr)

    def _api_call(self, endpoint: str, method: str = "GET", body: dict = None,
                  timeout: int = 5, connect_timeout: float = None) -> dict:
        """Appel direct a l'API Philips JointSpace.

        connect_timeout: timeout de connexion TCP seul (plus court que le read timeout).
        """
        import requests
        from requests.auth import HTTPDigestAuth

        url = f"https://{self.host}:1926/6/{endpoint}"
        auth = HTTPDigestAuth(self.user, self.password)
        # Tuple (connect, read) pour separer detection hote injoignable du read lent
        t = (connect_timeout if connect_timeout else timeout, timeout)

        try:
            # verify=False desactive seulement la verification par autorite de requests
            # (impossible : chaine SHA1). L'authenticite est garantie par l'empreinte
            # epinglee dans l'adaptateur HTTPS de la session (voir _build_tv_session).
            if method == "GET":
                response = self._session.get(url, auth=auth, verify=False, timeout=t)
            else:
                response = self._session.post(url, auth=auth, json=body, verify=False, timeout=t)

            if response.status_code == 200:
                return response.json() if response.text else {"status": "ok"}
            else:
                return {"error": f"HTTP {response.status_code}"}
        except requests.exceptions.Timeout:
            return {"error": "Timeout - TV may be off"}
        except Exception as e:
            return {"error": str(e)}

    def power_on(self) -> str:
        """Allume la TV — sequence complete, auto-suffisante et verifiee.

        1. Deja allumee -> rien a faire
        2. Injoignable -> Wake-on-LAN PUIS attente que la carte reseau
           reponde (5-25s) — avant, on rendait la main ici et l'allumage
           n'aboutissait jamais depuis la veille profonde (bug 2026-08-12)
        3. Joignable en veille -> touche Standby (toggle) puis POST
           powerstate On (idempotent, corrige un eventuel toggle inverse)
        4. Verification de l'etat REEL avant de repondre "TV allumee"
        """
        import time as _time

        self._init_pylips()

        state = self._api_call("powerstate", connect_timeout=1.5, timeout=3)
        if state.get("powerstate") == "On":
            return "TV deja allumee"

        via_wol = False
        if "error" in state:
            # TV injoignable (veille profonde) -> WoL + attente de reveil reseau
            self._send_wol()
            via_wol = True
            state = self._wait_reachable(deadline_s=25.0)
            if state is None:
                raise RuntimeError(
                    "Wake-on-LAN envoye mais la TV ne repond pas apres 25s — "
                    "elle est probablement coupee du secteur (le WoL ne "
                    "fonctionne que depuis la veille, pas depuis l'arret complet)")
            if state.get("powerstate") == "On":
                return "TV allumee (reveillee par Wake-on-LAN)"

        # Joignable mais en veille (Standby/StandbyKeep) : toggle puis ordre
        # ferme. L'ordre importe — la touche d'abord, le POST On idempotent
        # ensuite pour garantir l'etat final quel que soit l'effet du toggle.
        self._api_call("input/key", "POST", {"key": "Standby"}, timeout=5)
        _time.sleep(1.0)
        self._api_call("powerstate", "POST", {"powerstate": "On"}, timeout=5)

        final = self._confirm_on(deadline_s=12.0)
        if final == "On":
            return "TV allumee (via Wake-on-LAN + API)" if via_wol else "TV allumee"
        raise RuntimeError(
            f"Sequence d'allumage envoyee mais la TV reste en etat '{final}'")

    def _send_wol(self) -> None:
        """Envoie le paquet magique Wake-on-LAN (leve si impossible)."""
        if not self.mac:
            raise RuntimeError("TV injoignable et aucune MAC configuree pour Wake-on-LAN")
        try:
            from wakeonlan import send_magic_packet
            send_magic_packet(self.mac)
        except ImportError:
            raise RuntimeError("wakeonlan non installe. Lance: pip install wakeonlan")
        except Exception as e:
            raise RuntimeError(f"Wake-on-LAN: {e}")

    def _wait_reachable(self, deadline_s: float):
        """Polle powerstate jusqu'a reponse HTTP. None si toujours injoignable."""
        import time as _time
        end = _time.time() + deadline_s
        while _time.time() < end:
            state = self._api_call("powerstate", connect_timeout=1.5, timeout=3)
            if "error" not in state:
                return state
            _time.sleep(2.0)
        return None

    def _confirm_on(self, deadline_s: float) -> str:
        """Attend que powerstate atteigne 'On'. Retourne le dernier etat vu."""
        import time as _time
        end = _time.time() + deadline_s
        last = "inconnu"
        while _time.time() < end:
            state = self._api_call("powerstate", connect_timeout=1.5, timeout=3)
            last = state.get("powerstate", "inconnu") if "error" not in state else "injoignable"
            if last == "On":
                return "On"
            _time.sleep(1.5)
        return last


    def power_off(self) -> str:
        """Eteint la TV (standby)."""
        self._init_pylips()
        result = self._api_call("powerstate", "POST", {"powerstate": "Standby"})
        if "error" not in result:
            self._screen_muted = False  # Reset: au reveil l'ecran sera actif
            return "TV eteinte (standby)"
        return f"Erreur: {result.get('error', 'unknown')}"

    def _toggle_screen_mute(self) -> bool:
        """Appelle le toggle MUTE_SCREEN via JointSpace et retourne True si OK HTTP."""
        result = self._api_call(
            "menuitems/settings/update", "POST",
            {"values": [{"value": {"Nodeid": 2130968759}}]},
            timeout=8
        )
        return "error" not in result

    def _adb_screensaver(self) -> bool:
        """Lance le screensaver Philips via ADB (DreamerService).

        Retourne True si l'envoi a reussi (sans garantie d'effet visible).
        """
        import os

        from adb_shell.adb_device import AdbDeviceTcp
        from adb_shell.auth.sign_pythonrsa import PythonRSASigner

        key_path = os.path.expanduser("~/.android/adbkey")
        if not os.path.exists(key_path):
            return False

        try:
            with open(key_path) as f:
                priv = f.read()
            with open(key_path + ".pub") as f:
                pub = f.read()
            signer = PythonRSASigner(pub, priv)
            device = AdbDeviceTcp(self.host, 5555)
            device.connect(rsa_keys=[signer], auth_timeout_s=5)
            # Broadcast START_SCREENSAVER vers DreamerService Philips
            device.shell(
                "am broadcast -a org.droidtv.intent.action.START_SCREENSAVER",
                timeout_s=8
            )
            # Demarrer le DreamerService directement
            device.shell(
                "am startservice -n org.droidtv.tvsystemui/.logodreams.DreamerService"
                " -a org.droidtv.intent.action.START_SCREENSAVER",
                timeout_s=8
            )
            return True
        except Exception:
            return False

    def screen_off(self) -> str:
        """Eteint l'ecran tout en gardant le son (mode musique).

        Strategie:
        1. JointSpace MAIN_MUTE_SCREEN (fonctionne sur source HDMI/TV)
        2. Screensaver Philips via ADB (DreamerService) en fallback Android
        """
        self._init_pylips()
        if self._screen_muted:
            return "Ecran deja eteint (son actif)"

        # Tentative 1: JointSpace MUTE_SCREEN
        self._toggle_screen_mute()
        self._screen_muted = True

        # Tentative 2: Screensaver Philips via ADB
        self._adb_screensaver()

        return ("Commande ecran eteint envoyee. "
                "Si l ecran est toujours allume, ce mode ne fonctionne "
                "qu en source HDMI/TV (pas sur le launcher Android).")

    def screen_on(self) -> str:
        """Rallume l'ecran (apres screen_off)."""
        self._init_pylips()
        # Toujours tenter le toggle (si l'ecran etait mute via JointSpace)
        self._toggle_screen_mute()
        # Touche Info pour sortir du screensaver
        self._api_call("input/key", "POST", {"key": "Info"}, timeout=5)
        self._screen_muted = False
        return "Ecran rallume"

    def get_state(self) -> dict:
        """Etat de la TV : alimentation, volume, mute, mode ambilight.

        Ne renvoyait que powerstate ; un client (neutroncore, roadmap #73) qui
        veut afficher l'etat sans reimplementer JointSpace a besoin du reste.
        Les cles powerstate/error sont conservees telles quelles.
        """
        self._init_pylips()
        state = self._api_call("powerstate", connect_timeout=1.5, timeout=3)
        if "error" in state:
            return state
        audio = self._api_call("audio/volume", timeout=3)
        ambi = self._api_call("ambilight/currentconfiguration", timeout=3)
        power = self._api_call("ambilight/power", timeout=3)
        state["volume"] = audio.get("current") if "error" not in audio else None
        state["muted"] = bool(audio.get("muted")) if "error" not in audio else None
        state["ambilight_on"] = (power.get("power") == "On") if "error" not in power else None
        state["ambilight_mode"] = ambi.get("styleName") if "error" not in ambi else None
        return state

    def volume_up(self, step: int = 5) -> str:
        """Augmente le volume de X (default 5).

        IMPORTANT: Si HDMI ARC est actif (Denon configure), redirige vers le Denon.
        """
        # Redirection HDMI ARC -> Denon
        if self.denon_host:
            for _ in range(step):
                send_denon_command(self.denon_host, self.denon_port, "MVUP")
            import time
            time.sleep(0.3)
            # Lire le volume Denon
            response = send_denon_command(self.denon_host, self.denon_port, "MV?")
            if "MV" in response and "ERROR" not in response:
                for line in response.split('\r'):
                    if line.startswith('MV') and not line.startswith('MVMAX'):
                        vol_str = line[2:]
                        if len(vol_str) == 3:  # Ex: "245" -> 24.5
                            volume = float(vol_str) / 10
                        elif len(vol_str) == 2:  # Ex: "44" -> 44
                            volume = int(vol_str)
                        else:
                            volume = vol_str
                        return f"Volume Denon: {volume}"
            return "Volume augmente (Denon)"

        # Fallback: API TV (ne marche pas si HDMI ARC actif)
        self._init_pylips()
        current = self._api_call("audio/volume")
        if "error" in current:
            return f"Erreur: {current.get('error', 'unknown')}"
        new_level = min(60, current.get("current", 20) + step)
        result = self._api_call("audio/volume", "POST", {"current": new_level, "muted": False})
        if "error" not in result:
            return f"Volume: {new_level}"
        return f"Erreur: {result.get('error', 'unknown')}"

    def volume_down(self, step: int = 5) -> str:
        """Baisse le volume de X (default 5).

        IMPORTANT: Si HDMI ARC est actif (Denon configure), redirige vers le Denon.
        """
        # Redirection HDMI ARC -> Denon
        if self.denon_host:
            for _ in range(step):
                send_denon_command(self.denon_host, self.denon_port, "MVDOWN")
            import time
            time.sleep(0.3)
            # Lire le volume Denon
            response = send_denon_command(self.denon_host, self.denon_port, "MV?")
            if "MV" in response and "ERROR" not in response:
                for line in response.split('\r'):
                    if line.startswith('MV') and not line.startswith('MVMAX'):
                        vol_str = line[2:]
                        if len(vol_str) == 3:
                            volume = float(vol_str) / 10
                        elif len(vol_str) == 2:
                            volume = int(vol_str)
                        else:
                            volume = vol_str
                        return f"Volume Denon: {volume}"
            return "Volume baisse (Denon)"

        # Fallback: API TV
        self._init_pylips()
        current = self._api_call("audio/volume")
        if "error" in current:
            return f"Erreur: {current.get('error', 'unknown')}"
        new_level = max(0, current.get("current", 20) - step)
        result = self._api_call("audio/volume", "POST", {"current": new_level, "muted": False})
        if "error" not in result:
            return f"Volume: {new_level}"
        return f"Erreur: {result.get('error', 'unknown')}"

    def volume_set(self, level: int) -> str:
        """Regle le volume a un niveau specifique (0-60 pour TV, 0-98 pour Denon).

        IMPORTANT: Si HDMI ARC est actif (Denon configure), redirige vers le Denon.
        """
        # Redirection HDMI ARC -> Denon
        if self.denon_host:
            level = max(0, min(98, level))  # Denon range: 0-98
            response = send_denon_command(self.denon_host, self.denon_port, f"MV{level:02d}")

            if "ERROR" in response:
                return f"Erreur Denon: {response}"

            # Verifier que ca a marche
            import time
            time.sleep(0.3)
            check = send_denon_command(self.denon_host, self.denon_port, "MV?")
            if "MV" in check and "ERROR" not in check:
                for line in check.split('\r'):
                    if line.startswith('MV') and not line.startswith('MVMAX'):
                        vol_str = line[2:]
                        if len(vol_str) == 3:
                            actual = float(vol_str) / 10
                        elif len(vol_str) == 2:
                            actual = int(vol_str)
                        else:
                            actual = -1

                        if abs(actual - level) < 0.6:  # Tolerance
                            return f"Volume Denon regle a {level}"
                        else:
                            return f"Volume Denon: {actual} (demande: {level})"

            return f"Volume Denon regle a {level}"

        # Fallback: API TV (ne marche pas si HDMI ARC actif)
        self._init_pylips()
        level = max(0, min(60, level))

        # Lire le volume actuel d'abord
        current = self._api_call("audio/volume")
        if "error" in current:
            return f"Erreur lecture volume: {current.get('error', 'unknown')}"

        # Regler le nouveau volume
        result = self._api_call("audio/volume", "POST", {"current": level, "muted": False})
        if "error" not in result:
            # Verifier que ca a bien marche
            check = self._api_call("audio/volume")
            if "error" not in check:
                actual_level = check.get("current", -1)
                if actual_level == level:
                    return f"Volume regle a {level}"
                else:
                    return f"Volume partiellement regle (demande: {level}, actuel: {actual_level})"
            return f"Volume regle a {level}"
        return f"Erreur: {result.get('error', 'unknown')}"

    def mute(self) -> str:
        """Coupe ou remet le son.

        IMPORTANT: Si HDMI ARC est actif (Denon configure), redirige vers le Denon.
        """
        # Redirection HDMI ARC -> Denon
        if self.denon_host:
            response = send_denon_command(self.denon_host, self.denon_port, "MUON")
            if "ERROR" not in response:
                return "Mute Denon toggle"
            return f"Erreur Denon: {response}"

        # Fallback: API TV
        self._init_pylips()
        result = self._api_call("input/key", "POST", {"key": "Mute"})
        if "error" not in result:
            return "Mute toggle"
        return f"Erreur: {result.get('error', 'unknown')}"

    def ambilight_on(self) -> str:
        """Active l'Ambilight."""
        self._init_pylips()
        result = self._api_call("ambilight/power", "POST", {"power": "On"})
        if "error" not in result:
            return "Ambilight active"
        return f"Erreur: {result.get('error', 'unknown')}"

    def ambilight_off(self) -> str:
        """Desactive l'Ambilight."""
        self._init_pylips()
        result = self._api_call("ambilight/power", "POST", {"power": "Off"})
        if "error" not in result:
            return "Ambilight desactive"
        return f"Erreur: {result.get('error', 'unknown')}"

    def ambilight_mode(self, mode: str) -> str:
        """Change le mode Ambilight."""
        self._init_pylips()

        # Mapping des modes - menuSetting requis pour que ca marche
        mode_configs = {
            "follow_video": {"styleName": "FOLLOW_VIDEO", "isExpert": False, "menuSetting": "GAME"},
            "follow_audio": {"styleName": "FOLLOW_AUDIO", "isExpert": False, "menuSetting": "ENERGY_ADAPTIVE_BRIGHTNESS"},
            "lounge_light": {"styleName": "Lounge light", "isExpert": False, "menuSetting": "ISF"},
            "manual": {"styleName": "FOLLOW_COLOR", "isExpert": False, "menuSetting": "GAME"},
            # Aliases
            "video_immersive": {"styleName": "FOLLOW_VIDEO", "isExpert": False, "menuSetting": "GAME"},
            "audio_spectrum": {"styleName": "FOLLOW_AUDIO", "isExpert": False, "menuSetting": "ENERGY_ADAPTIVE_BRIGHTNESS"},
        }

        config = mode_configs.get(mode, mode_configs["follow_video"])
        result = self._api_call("ambilight/currentconfiguration", "POST", config)

        if "error" not in result:
            return f"Ambilight mode: {mode}"
        return f"Erreur: {result.get('error', 'unknown')}"

    def list_apps(self) -> str:
        """Liste les applications disponibles."""
        apps = ["netflix", "youtube", "plex", "disney", "prime"]
        return f"Applications disponibles: {', '.join(apps)}"

    def launch_app(self, app: str) -> str:
        """Lance une application."""
        import subprocess

        # Mapping package + activite principale (Android TV / Leanback)
        app_map = {
            "netflix": ("com.netflix.ninja",                    "com.netflix.ninja.MainActivity"),
            "youtube": ("com.google.android.youtube.tv",        "com.google.android.apps.youtube.tv.activity.ShellActivity"),
            "plex":    ("com.plexapp.android",                  "com.plexapp.plex.activities.SplashActivity"),
            "disney":  ("com.disney.disneyplus",                "com.bamtechmedia.domern.main.MainActivity"),
            "prime":   ("com.amazon.amazonvideo.livingroom",    "com.amazon.ignition.IgnitionActivity"),
        }

        app_lower = app.lower()
        if app_lower not in app_map:
            return f"App inconnue: {app}. Apps disponibles: {', '.join(app_map.keys())}"

        package, activity = app_map[app_lower]
        adb_path = "/tmp/platform-tools/adb"
        if not os.path.exists(adb_path):
            adb_path = "adb"

        # JointSpace activities/launch retourne 200 mais n'ouvre pas les apps Android TV.
        # On utilise ADB am start directement.
        try:
            subprocess.run(
                [adb_path, "connect", f"{self.host}:5555"],
                capture_output=True, timeout=5,
            )
            result = subprocess.run(
                [adb_path, "-s", f"{self.host}:5555", "shell",
                 "am", "start", "-n", f"{package}/{activity}"],
                capture_output=True, text=True, timeout=8,
            )
            if result.returncode == 0:
                return f"App {app} lancee"
            return f"Erreur ADB: {(result.stdout + result.stderr).strip()}"
        except subprocess.TimeoutExpired:
            return "Erreur: ADB timeout"
        except Exception as e:
            return f"Erreur: {e}"

    def youtube_video(self, video: str) -> str:
        """Lance YouTube sur une video specifique via ADB (utilise le compte connecte)."""
        import subprocess

        # Chemin ADB (telecharge depuis Google)
        adb_path = "/tmp/platform-tools/adb"
        if not os.path.exists(adb_path):
            # Fallback: essayer catt si ADB non disponible
            return self._youtube_video_catt(video)

        # Validation obligatoire : l'ID part dans une commande ADB distante
        video_id = extract_video_id(video)
        if not video_id:
            return f"URL YouTube invalide: {video[:80]!r}"

        url = f"https://www.youtube.com/watch?v={video_id}"

        # S'assurer que ADB est connecte
        try:
            # Connecter a la TV
            subprocess.run(
                [adb_path, "connect", f"{self.host}:5555"],
                capture_output=True, timeout=10
            )

            # Lancer YouTube avec l'intent VIEW (utilise le compte connecte!)
            result = subprocess.run(
                [adb_path, "-s", f"{self.host}:5555", "shell", "am", "start",
                 "-a", "android.intent.action.VIEW",
                 "-d", url,
                 "com.google.android.youtube.tv"],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0:
                return f"YouTube Premium: video {video_id} lancee"
            else:
                error = result.stderr or result.stdout
                # Si ADB echoue, fallback sur catt
                if "error" in error.lower() or "unauthorized" in error.lower():
                    return self._youtube_video_catt(video)
                return f"Erreur ADB: {error[:100]}"

        except subprocess.TimeoutExpired:
            return "Erreur: timeout ADB"
        except Exception:
            # Fallback sur catt en cas d'erreur
            return self._youtube_video_catt(video)

    def _youtube_video_catt(self, video: str) -> str:
        """Fallback: Lance YouTube via Cast (catt) - sans compte Premium."""
        import re
        import shutil
        import subprocess

        catt_path = shutil.which("catt") or os.path.expanduser("~/.local/bin/catt")
        if not os.path.exists(catt_path):
            return "Erreur: ni ADB ni catt disponibles"

        # Auparavant, une entree non reconnue etait castee telle quelle.
        video_id = extract_video_id(video)
        if not video_id:
            return f"URL YouTube invalide: {video[:80]!r}"

        url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            result = subprocess.run(
                [catt_path, "-d", "55OLED705/12", "cast", url],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                output = result.stdout + result.stderr
                if "Playing" in output:
                    title_match = re.search(r'Playing "([^"]+)"', output)
                    if title_match:
                        return f"Lecture (Cast): {title_match.group(1)}"
                return f"Video {video_id} (Cast, sans Premium)"
            else:
                return f"Erreur catt: {result.stderr}"

        except Exception as e:
            return f"Erreur: {e}"

    _VALID_KEYS: frozenset = frozenset({
        "Home", "Back", "Play", "Pause", "Stop", "FastForward", "Rewind",
        "VolumeUp", "VolumeDown", "Mute", "Standby",
        "CursorUp", "CursorDown", "CursorLeft", "CursorRight",
        "Confirm", "Exit", "Info", "Options", "Record",
        "ChannelStepUp", "ChannelStepDown", "Source", "AmbilightOnOff",
    })

    def send_key(self, key: str) -> str:
        """Envoie une touche de telecommande."""
        if key not in self._VALID_KEYS:
            valid = ", ".join(sorted(self._VALID_KEYS))
            return f"Touche invalide: {key!r}. Touches valides: {valid}"
        self._init_pylips()
        result = self._api_call("input/key", "POST", {"key": key})
        if "error" not in result:
            return f"Touche {key} envoyee"
        return f"Erreur: {result.get('error', 'unknown')}"


# Instance globale du serveur
tv: PhilipsTVController = None


# Profils d'annotations MCP (ToolAnnotations) : ils disent au client ce que fait
# un outil avant de l'appeler. Aucun outil de ce serveur n'ecrase de donnee,
# donc destructiveHint reste False ; la distinction utile est la lecture seule
# et l'idempotence (rejouable sans effet cumulatif).
_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
_SET = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
_ACTION = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)


def list_tools() -> list[Tool]:
    """Liste les outils disponibles."""
    return [
        Tool(
            name="power_on",
            annotations=_SET,
            description="Allume la TV Philips",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="power_off",
            annotations=_SET,
            description="Eteint la TV Philips (standby)",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="screen_off",
            annotations=_SET,
            description="Eteint l'ecran de la TV tout en gardant le son actif (mode musique). Note: fonctionne principalement en source HDMI/TV, limite en mode Android.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="screen_on",
            annotations=_SET,
            description="Rallume l'ecran de la TV apres un screen_off",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="volume_up",
            annotations=_ACTION,
            description="Augmente le volume de la TV (default +5)",
            inputSchema={
                "type": "object",
                "properties": {
                    "step": {"type": "integer", "default": 5, "description": "Increment (default 5)"}
                },
                "required": []
            }
        ),
        Tool(
            name="volume_down",
            annotations=_ACTION,
            description="Baisse le volume de la TV (default -5)",
            inputSchema={
                "type": "object",
                "properties": {
                    "step": {"type": "integer", "default": 5, "description": "Decrement (default 5)"}
                },
                "required": []
            }
        ),
        Tool(
            name="volume_set",
            annotations=_SET,
            description="Regle le volume a un niveau specifique",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 60,
                        "description": "Niveau de volume (0-60)"
                    }
                },
                "required": ["level"]
            }
        ),
        Tool(
            name="mute",
            annotations=_SET,
            description="Coupe ou remet le son de la TV",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="ambilight_on",
            annotations=_SET,
            description="Active l'Ambilight de la TV",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="ambilight_off",
            annotations=_SET,
            description="Desactive l'Ambilight de la TV",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="ambilight_mode",
            annotations=_SET,
            description="Change le mode Ambilight",
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["follow_video", "follow_audio", "lounge_light", "manual", "video_immersive", "audio_spectrum"],
                        "description": "Mode Ambilight"
                    }
                },
                "required": ["mode"]
            }
        ),
        Tool(
            name="list_apps",
            annotations=_READ,
            description="Liste les applications disponibles sur la TV",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="launch_app",
            annotations=_ACTION,
            description="Lance une application sur la TV",
            inputSchema={
                "type": "object",
                "properties": {
                    "app": {
                        "type": "string",
                        "enum": ["netflix", "youtube", "plex", "disney", "prime"],
                        "description": "Nom de l'application"
                    }
                },
                "required": ["app"]
            }
        ),
        Tool(
            name="youtube_video",
            annotations=_ACTION,
            description="Lance YouTube sur une video specifique (URL youtube ou ID de video)",
            inputSchema={
                "type": "object",
                "properties": {
                    "video": {
                        "type": "string",
                        "description": "URL YouTube (youtube.com/watch?v=xxx, youtu.be/xxx) ou ID de video (11 caracteres)"
                    }
                },
                "required": ["video"]
            }
        ),
        Tool(
            name="get_state",
            annotations=_READ,
            description="Retourne l'etat actuel de la TV : powerstate (On/Standby), volume, muted, ambilight_on, ambilight_mode",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="send_key",
            annotations=_ACTION,
            description="Envoie une touche de telecommande",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Touche a envoyer (ex: Home, Back, Play, Pause, Stop)"
                    }
                },
                "required": ["key"]
            }
        ),
    ]


async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute un outil."""
    global tv

    if tv is None:
        return [TextContent(type="text", text="Erreur: TV non configuree")]

    try:
        if name == "power_on":
            result = tv.power_on()
        elif name == "power_off":
            result = tv.power_off()
        elif name == "screen_off":
            result = tv.screen_off()
        elif name == "screen_on":
            result = tv.screen_on()
        elif name == "volume_up":
            step = arguments.get("step", 5)
            result = tv.volume_up(step)
        elif name == "volume_down":
            step = arguments.get("step", 5)
            result = tv.volume_down(step)
        elif name == "volume_set":
            level = arguments.get("level", 20)
            result = tv.volume_set(level)
        elif name == "mute":
            result = tv.mute()
        elif name == "ambilight_on":
            result = tv.ambilight_on()
        elif name == "ambilight_off":
            result = tv.ambilight_off()
        elif name == "ambilight_mode":
            mode = arguments.get("mode", "follow_video")
            result = tv.ambilight_mode(mode)
        elif name == "list_apps":
            result = tv.list_apps()
        elif name == "launch_app":
            app_name = arguments.get("app", "")
            result = tv.launch_app(app_name)
        elif name == "youtube_video":
            video = arguments.get("video", "")
            result = tv.youtube_video(video)
        elif name == "get_state":
            state = tv.get_state()
            result = json.dumps(state, indent=2)
        elif name == "send_key":
            key = arguments.get("key", "")
            result = tv.send_key(key)
        else:
            result = f"Outil inconnu: {name}"

        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Erreur: {e}")]


async def handle_list_tools(ctx: ServerRequestContext, params: PaginatedRequestParams | None) -> ListToolsResult:
    return ListToolsResult(tools=list_tools())


async def handle_call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    return CallToolResult(content=await call_tool(params.name, params.arguments or {}))


app = Server("pylips-mcp", on_list_tools=handle_list_tools, on_call_tool=handle_call_tool)


async def main():
    """Point d'entree principal."""
    global tv

    # Charger la configuration
    config = load_config()

    if not config["tv"]["host"]:
        print("Warning: TV_HOST not configured. Set TV_HOST env var or tv.host in config.yaml", file=sys.stderr)
    else:
        tv = PhilipsTVController(
            host=config["tv"]["host"],
            user=config["tv"]["user"],
            password=config["tv"]["pass"],
            mac=config["tv"].get("mac", ""),
            denon_host=config["denon"]["host"],
            denon_port=config["denon"]["port"]
        )
        print(f"pylips-mcp: TV configured at {config['tv']['host']}", file=sys.stderr)
        if config["denon"]["host"]:
            print(f"pylips-mcp: Denon HDMI ARC redirect enabled ({config['denon']['host']})", file=sys.stderr)

    # Demarrer le serveur MCP
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    # Desactiver les warnings SSL (auto-signed cert de la TV)
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    asyncio.run(main())


def cli() -> None:
    """Point d'entree console (pip/uvx) : lance le serveur MCP sur stdio."""
    import asyncio as _asyncio
    _asyncio.run(main())
