-- Référentiel : communes de la Gironde, avec leur contour (source : geo.api.gouv.fr).
-- Sert à rattacher chaque observation à sa commune (voir docs/decisions/0001-postgis.md).
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS ref;

CREATE TABLE IF NOT EXISTS ref.communes (
    code_insee TEXT PRIMARY KEY,
    nom TEXT NOT NULL,
    code_epci TEXT,
    population INTEGER,
    geom GEOMETRY (MULTIPOLYGON, 4326) NOT NULL,
    mis_a_jour_le TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_communes_geom
ON ref.communes USING gist (geom);
