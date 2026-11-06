-- Rattachement de chaque observation iNaturalist à sa commune (jointure spatiale).
-- Vue provisoire : elle deviendra un modèle dbt avec l'entrepôt (E5).
-- Une observation hors des communes de Gironde garde une commune vide.
CREATE OR REPLACE VIEW brut.inaturalist_observations_communes AS
SELECT
    o.id AS observation_id,
    c.code_insee,
    c.nom AS commune,
    coalesce(c.code_epci = '243300316', FALSE) AS bordeaux_metropole
FROM brut.inaturalist_observations AS o
LEFT JOIN ref.communes AS c
    ON st_intersects(c.geom, o.geom);
