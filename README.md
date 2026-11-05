# projet_fil_rouge_oiseaux
des oiseaux

## Qualité du code et CI/CD

### Avant chaque commit (pre-commit)

À installer une fois, dans le venv du projet sous WSL :

```bash
pip install pre-commit
pre-commit install
```

Ensuite, chaque `git commit` lance automatiquement :

| Contrôle | Outil | Configuration |
| --- | --- | --- |
| Lint et formatage Python | ruff | `ruff.toml` |
| Lint SQL et modèles dbt | sqlfluff | `.sqlfluff` |
| Détection de secrets (clés d'API, mots de passe) | detect-secrets | `.pre-commit-config.yaml` |
| Hygiène des fichiers (YAML, JSON, fins de ligne, fichiers trop gros) | pre-commit-hooks | `.pre-commit-config.yaml` |
| Format du message de commit | conventional-pre-commit | `.pre-commit-config.yaml` |

Lancer tous les contrôles à la main : `pre-commit run --all-files`.

### Convention des messages de commit

Chaque message commence par un préfixe, suivi d'une courte description :

- `feat:` nouvelle fonctionnalité (script d'ingestion, modèle dbt, API...)
- `fix:` correction de bug
- `chore:` configuration, outillage, dépendances
- `docs:` documentation

Exemple : `feat: ingestion des détections BirdWeather`

### Intégration et livraison continues (GitHub Actions)

Le workflow `.github/workflows/ci.yml` tourne à chaque push et à chaque pull request :

1. **Lint et contrôles** : les mêmes contrôles que pre-commit, sur tout le dépôt.
2. **Tests et dbt** : `pytest`, puis `dbt build` sur une base PostgreSQL éphémère (profil dbt dans `ci/profiles.yml`).
3. **Livraison** (branche `main` uniquement) : construit l'image Docker et la publie sur `ghcr.io`.

Les étapes dont le code n'existe pas encore (dossier `tests/`, projet dbt, `Dockerfile`) sont ignorées.
