"""Génère la vue technique de l'architecture : docs/architecture/vue_technique.png.

Prérequis, une seule fois (sous WSL, venv activé) :
    sudo apt install graphviz
    uv pip install -r requirements-dev.txt

Lancement, depuis la racine du dépôt :
    python docs/architecture/generer_vue_technique.py
"""

from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.generic.storage import Storage
from diagrams.onprem.analytics import Dbt, Metabase, Spark
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import Users
from diagrams.onprem.container import Docker
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.onprem.network import Internet
from diagrams.onprem.queue import Kafka
from diagrams.onprem.workflow import Airflow
from diagrams.programming.flowchart import Database, Document, MultipleDocuments
from diagrams.programming.framework import FastAPI, GraphQL
from diagrams.programming.language import Python

SORTIE = Path(__file__).with_name("vue_technique")

ATTRIBUTS_GRAPHE = {
    "fontsize": "22",
    "pad": "0.5",
    "nodesep": "0.7",
    "ranksep": "1.2",
}


def generer() -> None:
    with Diagram(
        "Oiseaux de Gironde – vue technique",
        filename=str(SORTIE),
        outformat="png",
        show=False,
        direction="LR",
        graph_attr=ATTRIBUTS_GRAPHE,
    ):
        with Cluster("Sources"):
            apis = Internet("API REST\niNaturalist · Biodiv'Sports\nMovebank")
            birdweather = GraphQL("BirdWeather\nGraphQL temps réel")
            scraping = Python("Scraping\npage sous licence ouverte")
            fichiers = MultipleDocuments("Fichiers CSV\nFaune-France · TAXREF\nliste rouge")
            gbif = Database("Snapshot GBIF\nParquet")

        with Cluster("Collecte et traitement"):
            airflow = Airflow("Orchestration\nbatch")
            kafka = Kafka("Flux\ntemps réel")
            spark = Spark("Traitement\nbig data")

        with Cluster("Stockage"):
            lake = Storage("Data lake\nbronze · silver · gold")
            catalogue = Document("Catalogue de données\n(outil à comparer)")
            base = PostgreSQL("Base\nopérationnelle")
            with Cluster("Entrepôt de données"):
                dbt = Dbt("Transformations\ndbt")
                entrepot = PostgreSQL("Schéma\nen étoile")

        with Cluster("Mise à disposition"):
            api = FastAPI("API REST")
            tableau_de_bord = Metabase("Tableau\nde bord")

        utilisateurs = Users("Métropole · LPO\ngrand public")

        with Cluster("Exploitation"):
            metriques = Prometheus("Métriques")
            supervision = Grafana("Supervision")
            docker = Docker("Docker Compose")
            ci_cd = GithubActions("CI/CD")
            # Lien invisible : place Docker et la CI côte à côte (grille 2 x 2)
            docker >> Edge(style="invis") >> ci_cd

        # Collecte batch
        [apis, scraping, fichiers] >> airflow >> [lake, base]

        # Temps réel
        birdweather >> kafka
        apis >> Edge(label="Movebank", style="dashed") >> kafka
        kafka >> lake

        # Big data
        gbif >> spark >> lake

        # Catalogue
        lake >> Edge(label="métadonnées", style="dotted") >> catalogue

        # Entrepôt et mise à disposition
        [lake, base] >> dbt >> entrepot >> [api, tableau_de_bord]
        [api, tableau_de_bord] >> utilisateurs

        # Supervision du stockage
        lake >> Edge(label="supervision", style="dotted") >> metriques >> supervision


if __name__ == "__main__":
    generer()
