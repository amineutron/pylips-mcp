# pylips-mcp

[![tests](https://github.com/amineutron/pylips-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/amineutron/pylips-mcp/actions/workflows/tests.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

MCP server for controlling Philips Android TV via the JointSpace API and ADB.

Exposes 14 tools covering power, volume, ambilight, app launching, and YouTube playback.
Handles the TP Vision SHA1 certificate chain transparently.

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
| `list_apps` | Liste les applications disponibles sur la TV |
| `launch_app` | Lance une application sur la TV |
| `youtube_video` | Lance YouTube sur une video specifique (URL youtube ou ID de video) |
| `get_state` | Retourne l'etat actuel de la TV (allumee/standby) |
| `send_key` | Envoie une touche de telecommande |
<!-- tools:end -->

## Requirements

- Python 3.10+
- [pylips](https://github.com/eslavnov/pylips) installed and accessible
- Philips Android TV with JointSpace API enabled (2016+ models)
- ADB enabled on the TV (for YouTube deep linking)
- `wakeonlan` Python package (optional, for Wake-on-LAN)

## Setup

### 1. Pair with your TV

```bash
pip install pylips
python -m pylips --host 192.168.0.XX --init
```

This generates credentials saved in `~/.config/pylips/pylips.conf`.

### 2. Install dependencies

```bash
pip install mcp requests wakeonlan
```

### 3. Configure

Copy `config.example.yaml` to `config.yaml` and fill in your TV credentials:

```yaml
tv:
  host: "192.168.0.XX"
  user: "your_user"
  pass: "your_password"

pylips_path: "/path/to/pylips"  # or set PYLIPS_PATH env var
```

### 4. Run

```bash
python server.py
```

Or set via environment variables:

```bash
TV_HOST=192.168.0.XX TV_USER=xxx TV_PASS=xxx python server.py
```

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
        "TV_PASS": "your_password",
        "PYLIPS_PATH": "/path/to/pylips"
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
