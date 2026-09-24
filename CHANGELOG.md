# Changelog

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versions [SemVer](https://semver.org/lang/fr/).

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
