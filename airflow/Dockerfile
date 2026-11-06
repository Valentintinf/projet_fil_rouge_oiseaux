# Image Airflow du projet : l'image officielle + les dépendances du code de collecte.
# Voir docs/decisions/0002-orchestrateur.md
ARG AIRFLOW_VERSION=3.3.2
FROM apache/airflow:${AIRFLOW_VERSION}-python3.14

ARG AIRFLOW_VERSION
COPY requirements.txt /tmp/requirements.txt
# On reprécise la version d'Airflow pour que pip ne la change pas en installant le reste.
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements.txt
