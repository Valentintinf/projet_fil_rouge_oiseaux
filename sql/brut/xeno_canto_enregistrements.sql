-- Zone « brut » : enregistrements de chants d'oiseaux xeno-canto (Gironde).
-- On ne garde que les métadonnées et le lien vers le son (aucun fichier audio).
-- Aucune donnée sur l'enregistreur n'est conservée (RGPD), ni le lieu-dit ni les
-- remarques libres. Les coordonnées sont arrondies à 3 décimales, soit environ 100 m.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS brut;

CREATE TABLE IF NOT EXISTS brut.xeno_canto_enregistrements (
    id BIGINT PRIMARY KEY,
    nom_scientifique TEXT NOT NULL,
    nom_anglais TEXT,
    statut_identification TEXT,
    type_son TEXT,
    qualite TEXT,
    enregistre_le DATE,
    heure TEXT,
    duree_s INTEGER,
    latitude NUMERIC(6, 3),
    longitude NUMERIC(6, 3),
    especes_en_fond TEXT[] NOT NULL DEFAULT '{}',
    licence TEXT NOT NULL,
    url TEXT NOT NULL,
    url_son TEXT,
    url_sonagramme TEXT,
    mis_en_ligne_le DATE,
    ingere_le TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_xeno_canto_mis_en_ligne_le
ON brut.xeno_canto_enregistrements (mis_en_ligne_le);

-- Point géographique calculé à partir des coordonnées (PostGIS)
ALTER TABLE brut.xeno_canto_enregistrements
ADD COLUMN IF NOT EXISTS geom GEOMETRY (POINT, 4326)
GENERATED ALWAYS AS (st_setsrid(st_makepoint(longitude, latitude), 4326)) STORED;

CREATE INDEX IF NOT EXISTS idx_xeno_canto_geom
ON brut.xeno_canto_enregistrements USING gist (geom);
