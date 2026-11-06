"""Collecte quotidienne des observations d'oiseaux iNaturalist (Gironde).

Le DAG appelle le code de collecte de src/oiseaux : il ne contient aucune logique métier.
La collecte est incrémentale : chaque jour, seules les observations créées ou modifiées
depuis la veille sont relues.
"""

from datetime import datetime, timedelta

from airflow.sdk import dag, task


@dag(
    dag_id="collecte_inaturalist",
    description="Collecte incrémentale des observations d'oiseaux iNaturalist en Gironde",
    schedule="@daily",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["oiseaux", "ingestion", "api"],
)
def collecte_inaturalist() -> None:
    @task
    def collecter() -> int:
        """Collecte et charge les nouvelles observations, puis renvoie leur nombre."""
        # Import dans la tâche : le DAG reste rapide à analyser par Airflow.
        from oiseaux.ingestion import inaturalist

        return inaturalist.executer()

    collecter()


collecte_inaturalist()
