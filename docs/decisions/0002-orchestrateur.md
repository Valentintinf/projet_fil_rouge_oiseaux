# 0002 – Orchestrer les collectes et les transformations avec Airflow

- **Statut :** ✅ acceptée
- **Date :** 06/11/2026

## Contexte

Le projet a déjà deux scripts de collecte (iNaturalist et le référentiel des communes). D'autres vont suivre : GBIF, BirdWeather, Movebank, le scraping, puis les transformations dbt de l'entrepôt. Il faut :
- les **lancer automatiquement**, chacun à son rythme (tous les jours, tous les mois…) ;
- les **relancer en cas d'échec** et **savoir quand quelque chose a échoué** ;
- gérer les **dépendances** (charger avant de transformer) ;
- garder une **trace** de chaque exécution, à montrer au jury (C8 : « automatiser l'extraction »).

**Contraintes :**
- Python 3.14 (voir le cadrage) ;
- dbt pour l'entrepôt (E5) ;
- tout en local et gratuit, avec Docker ;
- 32 Go de RAM disponibles ;
- un outil que le jury et le marché connaissent.

## Options étudiées

Versions vérifiées sur PyPI et Docker Hub le 06/11/2026.

| Option | Python 3.14 | Intégration dbt | Avantages | Inconvénients |
| --- | --- | --- | --- | --- |
| **Airflow 3.3** | ✅ Image officielle `apache/airflow:3.3.2-python3.14` | ✅ Cosmos : un modèle dbt = une tâche | Standard du marché, interface de suivi complète, nouvelles tentatives, rattrapage de l'historique (backfill), planification fine | Lourd : plusieurs conteneurs, environ 4 Go de RAM. Configuration assez verbeuse. |
| Prefect 3.9 | ✅ (et 3.15) | Possible, moins intégrée | Léger, du Python pur avec des décorateurs | Moins répandu en France, modèle serveur et cloud moins standard |
| Dagster 1.13 | ⚠️ le cœur oui, mais `dagster-dbt` exige Python < 3.14 | ✅ excellente, en Python 3.13 | Pensé « données » (assets), très bon lignage | Obligerait à redescendre en Python 3.13. Moins répandu. |
| Cron + scripts | ✅ | ❌ | Très simple | Ni reprise sur erreur, ni suivi, ni dépendances entre tâches |
| Airflow managé par AWS (MWAA) | — | — | Rien à installer | Environ 350 $/mois, bien au-delà du budget (0 €) |

## Décision

On utilise **Airflow 3.3**, **en local avec Docker Compose** :
- une **image du projet** (`airflow/Dockerfile`) : l'image officielle `apache/airflow:3.3.2-python3.14`, à laquelle on ajoute les dépendances du code de collecte ;
- l'**exécuteur LocalExecutor**, qui lance les tâches dans le conteneur du scheduler. Il suffit pour un seul poste et évite Redis et les workers Celery du fichier officiel ;
- une **base de métadonnées Airflow séparée** (conteneur `airflow-db`), distincte de la base des données du projet ;
- une **connexion obligatoire** à l'interface (gestionnaire d'authentification FAB), avec des identifiants lus dans `.env` ;
- le code de collecte reste dans `src/oiseaux`. Les DAG (`dags/`) ne font que l'appeler, donc on peut toujours lancer un script à la main.

Premiers DAG :

| DAG | Rythme | Rôle |
| --- | --- | --- |
| `collecte_inaturalist` | Tous les jours | Collecte incrémentale des observations |
| `referentiel_communes` | Tous les mois | Rechargement des communes de Gironde |

## Conséquences

- ✅ Chaque collecte est planifiée, relancée en cas d'échec (2 nouvelles tentatives, 5 minutes d'écart) et visible dans l'interface. C'est une preuve directe pour C8.
- ✅ Les modèles dbt pourront être ajoutés comme tâches (Cosmos) quand l'entrepôt existera (E5).
- ✅ Les traitements batch du data lake (E7) passeront par le même outil.
- ⚠️ Environ 4 Go de RAM et 4 conteneurs de plus : `airflow-db`, `airflow-apiserver`, `airflow-scheduler`, `airflow-dag-processor`.
- ⚠️ Les tâches tournent dans le conteneur Airflow. Elles joignent PostgreSQL par le réseau Docker (`postgres:5432`), pas par `localhost:5433` comme les scripts lancés depuis WSL.
- 🔜 Si une source a besoin d'attente asynchrone (par exemple le temps réel), on ajoutera le service `triggerer`.
