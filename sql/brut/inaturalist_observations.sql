-- Zone « brut » : observations d'oiseaux iNaturalist, telles que collectées.
-- Aucune donnée sur l'observateur n'est conservée (RGPD) et les coordonnées
-- sont arrondies à 3 décimales, soit environ 100 m.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS brut;

CREATE TABLE IF NOT EXISTS brut.inaturalist_observations (
    id BIGINT PRIMARY KEY,
    observe_le DATE,
    observe_a TIMESTAMPTZ,
    cree_le TIMESTAMPTZ NOT NULL,
    mis_a_jour_le TIMESTAMPTZ NOT NULL,
    taxon_id BIGINT,
    nom_scientifique TEXT,
    nom_francais TEXT,
    rang TEXT,
    latitude NUMERIC(6, 3),
    longitude NUMERIC(6, 3),
    precision_m INTEGER,
    coordonnees_floutees BOOLEAN NOT NULL,
    captif BOOLEAN NOT NULL,
    qualite TEXT NOT NULL,
    licence TEXT NOT NULL,
    url TEXT NOT NULL,
    ingere_le TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inaturalist_mis_a_jour_le
ON brut.inaturalist_observations (mis_a_jour_le);

-- Point géographique calculé automatiquement à partir des coordonnées (PostGIS).
-- Ajouté avec ALTER TABLE pour mettre à jour une table déjà créée.
ALTER TABLE brut.inaturalist_observations
ADD COLUMN IF NOT EXISTS geom GEOMETRY (POINT, 4326)
GENERATED ALWAYS AS (st_setsrid(st_makepoint(longitude, latitude), 4326)) STORED;

CREATE INDEX IF NOT EXISTS idx_inaturalist_geom
ON brut.inaturalist_observations USING gist (geom);
