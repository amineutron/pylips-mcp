# pylips-mcp

MCP server for controlling Philips Android TV via the JointSpace API and ADB.

Exposes 14 tools covering power, volume, ambilight, app launching, and YouTube playback.
Handles the TP Vision SHA1 certificate chain transparently.

## Tools

| Tool | Description |
|------|-------------|
| `set_wake` | Power on the TV |
| `set_standby` | Put TV in standby |
| `set_screen_off` | Turn off screen while keeping audio (HDMI source only) |
| `set_screen_on` | Turn screen back on after screen_off |
| `set_volume` | Set volume to a specific level |
| `get_volume` | Get current volume |
| `set_ambilight` | Enable/configure Ambilight |
| `get_ambilight_status` | Get Ambilight state |
| `launch_app` | Launch an app by name |
| `get_current_app` | Get currently running app |
| `launch_app` (YouTube) | Launch YouTube with a specific video (ADB deep link) |
| `get_tv_status` | Get TV power state |
| `send_key` | Send a remote control keypress |
| `dismiss_screensaver` | Dismiss active screensaver |

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

Philips TVs use a TP Vision PKI chain from 2015 (SHA1). The included `tpvision_ca.pem`
pins this certificate so connections use the actual CA rather than disabling all validation.
Modern OpenSSL rejects SHA1 by default, so `SECLEVEL=0` is set in the adapter.

## License

MIT
