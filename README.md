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

## Orchestration avec Airflow

Les collectes sont planifiées par Airflow 3.3, qui tourne dans Docker avec le reste du projet ([fiche de décision 0002](docs/decisions/0002-orchestrateur.md)).

| DAG | Rythme | Rôle |
| --- | --- | --- |
| `collecte_inaturalist` | Tous les jours | Collecte incrémentale des observations iNaturalist |
| `collecte_xeno_canto` | Tous les jours | Collecte incrémentale des enregistrements xeno-canto |
| `referentiel_communes` | Tous les mois | Rechargement des communes de Gironde |

Démarrage, après avoir rempli les variables `AIRFLOW_*` du `.env` :

```bash
docker compose up -d --build
```

- L'interface est sur <http://localhost:8081>. On se connecte avec `AIRFLOW_ADMIN_USER` et `AIRFLOW_ADMIN_PASSWORD`.
- Les DAG sont en pause à leur création : il faut les activer dans l'interface.
- Pour vérifier que les DAG se chargent sans erreur : `docker compose exec airflow-scheduler airflow dags list-import-errors`.
- Pour lancer un DAG une fois, sans attendre sa planification : `docker compose exec airflow-scheduler airflow dags trigger collecte_inaturalist`.

## Sources de données

| Source | Module | Table | Fréquence |
| --- | --- | --- | --- |
| iNaturalist : observations d'oiseaux en Gironde (licences réutilisables uniquement) | `oiseaux.ingestion.inaturalist` | `brut.inaturalist_observations` | Incrémentale (`updated_since`) |
| geo.api.gouv.fr : communes de Gironde, avec leur contour et leur intercommunalité | `oiseaux.ingestion.communes` | `ref.communes` | Rechargement complet |
| xeno-canto : enregistrements de chants d'oiseaux en Gironde (API v3 avec clé, métadonnées et lien vers le son) | `oiseaux.ingestion.xeno_canto` | `brut.xeno_canto_enregistrements` | Incrémentale (`since:`) |

La clé xeno-canto (gratuite, sur la page de compte xeno-canto) va dans `.env`, sous le nom `XENO_CANTO_API_KEY`. Elle ne doit jamais apparaître dans Git.

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

On ajoute à la fin, entre parenthèses, la clé du ticket Jira concerné (projet `DE`). Elle est facultative pour les petits commits sans ticket.

**La clé s'ajoute toute seule** si on travaille sur une branche qui la porte : un hook (`scripts/ajouter_cle_jira.py`) la lit dans le nom de la branche et l'ajoute au message.

```bash
git switch -c feat/DE-30-biodiv-sports              # une branche par ticket
git commit -m "feat: collecte des zones sensibles"  # devient « ... (DE-30) »
```

Après avoir modifié `.pre-commit-config.yaml`, il faut relancer `pre-commit install` pour installer le hook.

Exemples :

- `feat: collecte des zones sensibles Biodiv'Sports (DE-30)`
- `docs: grilles d'entretien des producteurs et des exploitants (DE-23)`
- `fix: arrondi des coordonnées iNaturalist`

### Intégration et livraison continues (GitHub Actions)

Le workflow `.github/workflows/ci.yml` tourne à chaque push et à chaque pull request :

1. **Lint et contrôles** : les mêmes contrôles que pre-commit, sur tout le dépôt.
2. **Tests et dbt** : `pytest`, puis `dbt build` sur une base PostgreSQL éphémère (profil dbt dans `ci/profiles.yml`).
3. **Livraison** (branche `main` uniquement) : construit l'image Docker et la publie sur `ghcr.io`.

Les étapes dont le code n'existe pas encore (dossier `tests/`, projet dbt, `Dockerfile`) sont ignorées.
