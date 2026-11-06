# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions [SemVer](https://semver.org/lang/fr/).

## [0.4.0] - 2026-09-26

### Ajouté

- `ambilight_color` tool: fixed RGB colour (0-255) with optional brightness (#7). The colour style is read from `ambilight/supportedstyles`: the one offering the `MANUAL_HUE` algorithm (`FOLLOW_COLOR` on older sets, `Lounge light` on the 55OLED705). The tool reads the configuration back and reports an error when the TV ignored the request: it answers HTTP 200 either way.

### Connu

- `ambilight_mode(mode="manual")` still targets `FOLLOW_COLOR`, which the 55OLED705 does not have (no effect there). Use `ambilight_color` for a fixed colour.

## [0.3.0] - 2026-09-25

### Modifié

- The code now lives in a `pylips_mcp` package (`pylips_mcp.server`, with `tpvision_ca.pem` inside it). The wheel used to install a top-level `server` module and the certificate at the root of site-packages, clashing with denon-mcp and catt-mcp. `python server.py` from a clone still works (thin launcher), and `python -m pylips_mcp` is new.

### Supprimé

- The optional import of the pylips library (`PYLIPS_PATH`, `pylips_path`): it was never used, every call already goes to the JointSpace API directly. Only the one-time pairing needs pylips; the README no longer suggests `pip install pylips`, an unrelated PyPI package.

### Corrigé

- `pylips-mcp --help` and `--version` answer without any configuration (they used to start the server).

## [0.2.1] - 2026-09-24

### Ajouté

- **registry** : MCP registry manifest and package ownership marker

## [0.2.0] - 2026-09-24

### Ajouté
- `get_state` renvoie aussi `volume`, `muted`, `ambilight_on` et `ambilight_mode` (les clients n'ont plus à réimplémenter JointSpace).
- Annotations MCP (`readOnlyHint`, `idempotentHint`, `destructiveHint`) sur chaque outil.
- Workflow de release sur tag `v*` : build du wheel, publication PyPI par Trusted Publishing, release GitHub.
- Démo enregistrée (GIF) et script de régénération.

### Modifié
- Migration vers `mcp` 2.
- Un seul extracteur d'identifiant YouTube, chemin catt validé aussi.
- Configuration par variables d'environnement seules, sans `config.yaml`.

### Corrigé
- `power_on` : séquence de réveil complète et vérifiée (Wake-on-LAN, attente réseau, état réel).
- Import `Optional` manquant qui cassait Python < 3.14.
- TV en veille profonde : `get_state` répond en ~1,5 s au lieu de bloquer.

## [0.1.0] - 2026-09-09

Première version publiée : configuration autonome, wheel installable avec point d'entrée, table des outils générée, tests et CI.
