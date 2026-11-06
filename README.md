# projet_fil_rouge_oiseaux
des oiseaux

Le besoin, le périmètre et l'architecture sont décrits dans [docs/cadrage.md](docs/cadrage.md).

## Démarrage rapide (sous WSL)

1. Créer le venv et installer les dépendances :

   ```bash
   uv venv --python 3.14 .venv && source .venv/bin/activate
   uv pip install -r requirements.txt -r requirements-dev.txt
   ```

2. Créer le fichier `.env` à partir du modèle, changer le mot de passe, puis charger les variables :

   ```bash
   cp .env.example .env
   set -a && source .env && set +a
   ```

3. Démarrer PostgreSQL :

   ```bash
   docker compose up -d
   ```

4. Charger le référentiel des communes, puis lancer une collecte :

   ```bash
   python -m oiseaux.ingestion.communes                    # 534 communes de Gironde
   python -m oiseaux.ingestion.inaturalist --pages-max 2   # essai rapide : 400 observations
   python -m oiseaux.ingestion.inaturalist                 # collecte incrémentale complète
   ```

5. Lancer les tests :

   ```bash
   pytest
   ```

## Sources de données

| Source | Module | Table | Fréquence |
| --- | --- | --- | --- |
| iNaturalist : observations d'oiseaux en Gironde (licences réutilisables uniquement) | `oiseaux.ingestion.inaturalist` | `brut.inaturalist_observations` | Incrémentale (`updated_since`) |
| geo.api.gouv.fr : communes de Gironde, avec leur contour et leur intercommunalité | `oiseaux.ingestion.communes` | `ref.communes` | Rechargement complet |

Chaque observation est rattachée à sa commune par une jointure spatiale PostGIS, dans la vue `brut.inaturalist_observations_communes`.

Les choix techniques sont justifiés dans [docs/decisions](docs/decisions/README.md).

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
