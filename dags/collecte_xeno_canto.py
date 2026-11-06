"""Collecte quotidienne des enregistrements de chants d'oiseaux xeno-canto (Gironde).

La clé d'API est transmise au conteneur Airflow par la variable XENO_CANTO_API_KEY
(fichier .env). Le DAG appelle le code de src/oiseaux, sans logique métier.
"""

from datetime import datetime, timedelta

from airflow.sdk import dag, task


@dag(
    dag_id="collecte_xeno_canto",
    description="Collecte incrémentale des enregistrements de chants d'oiseaux xeno-canto",
    schedule="@daily",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["oiseaux", "ingestion", "api"],
)
def collecte_xeno_canto() -> None:
    @task
    def collecter() -> int:
        """Collecte et charge les nouveaux enregistrements, puis renvoie leur nombre."""
        from oiseaux.ingestion import xeno_canto

        return xeno_canto.executer()

    collecter()


collecte_xeno_canto()
