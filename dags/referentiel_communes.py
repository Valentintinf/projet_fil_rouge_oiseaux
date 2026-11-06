"""Rechargement mensuel du référentiel des communes de Gironde (geo.api.gouv.fr).

Les communes changent rarement (fusions de communes, changement d'intercommunalité) :
un rechargement par mois suffit.
"""

from datetime import datetime, timedelta

from airflow.sdk import dag, task


@dag(
    dag_id="referentiel_communes",
    description="Rechargement des communes de Gironde avec leur contour et leur intercommunalité",
    schedule="@monthly",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["oiseaux", "ingestion", "referentiel"],
)
def referentiel_communes() -> None:
    @task
    def charger() -> int:
        """Télécharge et charge les communes, puis renvoie leur nombre."""
        from oiseaux.ingestion import communes

        return communes.executer()

    charger()


referentiel_communes()
