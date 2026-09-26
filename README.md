# pylips-mcp
<!-- mcp-name: io.github.amineutron/pylips-mcp -->

[![tests](https://github.com/amineutron/pylips-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/amineutron/pylips-mcp/actions/workflows/tests.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

MCP server for controlling Philips Android TV via the JointSpace API and ADB.

Exposes 14 tools covering power, volume, ambilight, app launching, and YouTube playback.
Handles the TP Vision SHA1 certificate chain transparently.

## Demo

![MCP client: the 16 tools, then get_state on the real TV](docs/assets/demo.gif)

Recorded against the real TV with [`docs/demo/record.sh`](docs/demo/record.sh): a minimal MCP client ([`docs/demo/mcp_demo.py`](docs/demo/mcp_demo.py)) starts the server over stdio with `TV_HOST`/`TV_USER`/`TV_PASS` in the environment, lists the tools and calls `get_state` (read-only). Credentials never appear on screen.

## Tools

<!-- tools:start -->
| Outil | Rôle |
|---|---|
| `power_on` | Allume la TV Philips |
| `power_off` | Eteint la TV Philips (standby) |
| `screen_off` | Eteint l'ecran de la TV tout en gardant le son actif (mode musique). Note: fonctionne principalement en source HDMI/TV, limite en mode Android. |
| `screen_on` | Rallume l'ecran de la TV apres un screen_off |
| `volume_up` | Augmente le volume de la TV (default +5) |
| `volume_down` | Baisse le volume de la TV (default -5) |
| `volume_set` | Regle le volume a un niveau specifique |
| `mute` | Coupe ou remet le son de la TV |
| `ambilight_on` | Active l'Ambilight de la TV |
| `ambilight_off` | Desactive l'Ambilight de la TV |
| `ambilight_mode` | Change le mode Ambilight |
| `ambilight_color` | Met l'Ambilight sur une couleur fixe (RVB 0-255), luminosite optionnelle |
| `list_apps` | Liste les applications disponibles sur la TV |
| `launch_app` | Lance une application sur la TV |
| `youtube_video` | Lance YouTube sur une video specifique (URL youtube ou ID de video) |
| `get_state` | Retourne l'etat actuel de la TV : powerstate (On/Standby), volume, muted, ambilight_on, ambilight_mode |
| `send_key` | Envoie une touche de telecommande |
<!-- tools:end -->

### YouTube ID extraction

`extract_video_id` is deliberately duplicated in [catt-mcp](https://github.com/amineutron/catt-mcp) (`cast_youtube`, Chromecast with start position and dual-screen sync). Both servers stay installable on their own; each one tests its copy with the same table of cases (`tests/test_youtube_id.py`). Decision recorded on 2026-09-20.

## Requirements

- Python 3.10+
- JointSpace credentials (user + password) from a one-time pairing with the TV (see Setup); the server itself talks to the TV API directly and does not need pylips at runtime
- Philips Android TV with JointSpace API enabled (2016+ models)
- ADB enabled on the TV (for YouTube deep linking)
- `wakeonlan` Python package (optional, for Wake-on-LAN)

## Installation en une ligne

```bash
uvx pylips-mcp                 # depuis PyPI ; avant publication : uvx --from git+https://github.com/amineutron/pylips-mcp pylips-mcp
```

Configuration Claude Desktop / Claude Code (`mcpServers`) :

```json
{ "pylips": { "command": "uvx", "args": ["pylips-mcp"], "env": { "TV_HOST": "192.0.2.10", "TV_USER": "...", "TV_PASS": "..." } } }
```

## Setup

### 1. Pair with your TV

Pairing is done once, to get a JointSpace user and password. Use the pairing tool of
[eslavnov/pylips](https://github.com/eslavnov/pylips) from a clone of that repository
(the `pylips` package on PyPI is an unrelated project: do not `pip install pylips`),
and follow its README with your TV's IP. pylips-mcp does not need pylips afterwards.

Keep the user and password the pairing gives you: they go into `config.yaml` (step 3) or `TV_USER` / `TV_PASS`.

### 2. Install dependencies

```bash
pip install pylips-mcp        # or: uvx pylips-mcp
```

### 3. Configure

Copy `config.example.yaml` to `config.yaml` and fill in your TV credentials:

```yaml
tv:
  host: "192.168.0.XX"
  user: "your_user"
  pass: "your_password"

```

### 4. Run

```bash
pylips-mcp                    # installed (pip, uvx) ; `pylips-mcp --help` lists the settings
python -m pylips_mcp          # same thing, from any environment where the package is installed
python server.py              # from a clone, without installing (thin launcher, code in pylips_mcp/)
```

Or set via environment variables:

```bash
TV_HOST=192.168.0.XX TV_USER=xxx TV_PASS=xxx pylips-mcp
```

The code lives in the `pylips_mcp` package (with the TP Vision certificate), so it can be
installed next to other MCP servers without module name clashes.

## Claude Desktop Configuration

```json
{
  "mcpServers": {
    "philips-tv": {
      "command": "python3",
      "args": ["/path/to/pylips-mcp/server.py"],
      "env": {
        "TV_HOST": "192.168.0.XX",
        "TV_USER": "your_user",
        "TV_PASS": "your_password"
      }
    }
  }
}
```

## SSL Note

Philips TVs present a TP Vision certificate chain from 2015 signed with SHA1.
Modern OpenSSL and the Fedora/RHEL crypto policy reject SHA1 signatures, so a
classic CA verification is impossible, even with the bundled chain and
`SECLEVEL=0`.

What this server does instead, honestly:

- CA verification is disabled (it cannot succeed);
- the SHA-256 fingerprint of the certificate presented by the TV must match the
  leaf certificate shipped in `tpvision_ca.pem` (checked by urllib3 after the
  TLS handshake, so a man-in-the-middle cannot impersonate the TV without the
  private key). Verified against a real 55OLED705 (JointSpace 6, port 1926);
- `PYLIPS_TLS_FINGERPRINT=<sha256 hex>` pins another TV, `PYLIPS_TLS_PIN=0`
  disables pinning and logs a warning.

`tpvision_ca.pem` is the public TP Vision chain (leaf `restfultv.tpvision.com`,
intermediate `ca.tpvision.com`, root `www.tpvision.com`, valid until 2042),
extracted from a TV with `openssl s_client -showcerts`. It contains no secret.

## License

MIT

## Volume en HDMI ARC

Quand la TV est reliee a un ampli en HDMI ARC, le son ne sort pas de la TV :
agir sur son volume n'a aucun effet audible. Si `denon.host` est renseigne
dans la configuration, `volume_up`, `volume_down`, `volume_set` et `mute`
sont donc rediriges vers l'ampli Denon ; sinon ils passent par l'API de la TV.

Pour piloter l'ampli directement (entrees, extinction, statut), utiliser
[denon-mcp](https://github.com/amineutron/denon-mcp).

## Part of the Lyra ecosystem

| Dépôt | Rôle |
|---|---|
| [lyra](https://github.com/amineutron/lyra) | assistant DevOps vocal, local par défaut (AGPL-3.0) |
| [fedora-agents](https://github.com/amineutron/fedora-agents) | MCP : machines virtuelles KVM et sauvegardes |
| [mcp-tracking](https://github.com/amineutron/mcp-tracking) | MCP + API + tableau de bord des tâches longues |
| [neutroncore](https://github.com/amineutron/neutroncore) | hub PWA du homelab |
| [hue-mcp](https://github.com/amineutron/hue-mcp) | MCP Philips Hue (fork de ThomasRohde/hue-mcp) |
| [pylips-mcp](https://github.com/amineutron/pylips-mcp) | MCP TV Philips |
| [denon-mcp](https://github.com/amineutron/denon-mcp) | MCP ampli Denon |
| [catt-mcp](https://github.com/amineutron/catt-mcp) | MCP Chromecast et DLNA |
