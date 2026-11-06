# 0001 – Rattacher les observations aux communes avec PostGIS

- **Statut :** ✅ acceptée
- **Date :** 06/11/2026

## Contexte

La question de décision du projet porte sur les **communes** : « Dans quelles communes de Bordeaux Métropole les populations d'oiseaux évoluent-elles le plus ? » (voir [le cadrage](../cadrage.md)).

Or une observation n'est qu'un point GPS. Il faut donc savoir :
- dans quelle commune se trouve chaque observation ;
- si cette commune fait partie de Bordeaux Métropole (intercommunalité n° 243300316, 28 communes).

**Contraintes :**
- toutes les sources doivent pouvoir utiliser le même rattachement : iNaturalist aujourd'hui, puis GBIF, Faune-France, BirdWeather…
- le volume va grandir : environ 23 000 observations iNaturalist aujourd'hui, beaucoup plus avec GBIF ;
- l'entrepôt sera construit en SQL avec dbt (E5) ;
- tout doit tourner en local, gratuitement.

## Options étudiées

| Option | Avantages | Inconvénients |
| --- | --- | --- |
| **PostGIS**, l'extension géographique de PostgreSQL | Jointure spatiale en SQL, dans la base qu'on utilise déjà. Index spatial (GiST), donc rapide même sur de gros volumes. Utilisable directement dans dbt. Standard du métier. Image Docker officielle. | Une extension à installer. Il faut apprendre les fonctions `ST_*`. |
| GeoPandas / Shapely en Python, avant le chargement | Simple pour de petits volumes. | Calcul en dehors de la base, à refaire dans chaque script de collecte. Inutilisable depuis dbt. Tout se fait en mémoire. |
| API de géocodage inverse (`geo.api.gouv.fr/communes?lat=…&lon=…`) | Aucun calcul de notre côté. | Un appel par observation, soit des centaines de milliers d'appels. Lent, dépendant du réseau, soumis à des quotas. |
| DuckDB avec son extension spatiale | Très rapide en analyse. | Ajoute un second moteur de base de données, alors que l'entrepôt est prévu en PostgreSQL. |

## Décision

On utilise **PostGIS** :
- l'image Docker `postgis/postgis:16-3.7` remplace `postgres:16`, en local comme dans la CI. Cette version repose sur la même Debian (trixie) que `postgres:16`. Avec la version 3.5, basée sur une Debian plus ancienne, PostgreSQL signalait un écart de « collation » (les règles de tri du texte), qui peut fausser les index sur du texte ;
- le **référentiel des communes de Gironde** est chargé dans `ref.communes` depuis l'API officielle [geo.api.gouv.fr](https://geo.api.gouv.fr), avec pour chaque commune son code INSEE, son nom, son intercommunalité, sa population et son contour ;
- chaque observation reçoit une colonne géographique `geom`, calculée automatiquement à partir de la latitude et de la longitude ;
- le rattachement se fait par une jointure spatiale (`ST_Intersects`), accélérée par des index spatiaux. Il est exposé dans la vue `brut.inaturalist_observations_communes`.

## Conséquences

- ✅ Le rattachement se fait en SQL : il est réutilisable par toutes les sources et par dbt.
- ✅ D'autres analyses spatiales deviennent possibles. Par exemple, les **zones sensibles de Biodiv'Sports** sont aussi des polygones : on pourra repérer les observations qui y tombent, pour les flouter (RGPD, protection des espèces).
- ⚠️ **Limite connue :** les coordonnées sont arrondies à environ 100 m pour protéger la vie privée. Une observation faite à moins de 100 m d'une limite communale peut donc être attribuée à la commune voisine. C'est acceptable pour des indicateurs par commune.
- ⚠️ Les observations situées hors des communes de Gironde (en mer, sur l'estuaire, ou mal géolocalisées) n'ont pas de commune. Elles restent visibles dans la vue, avec une commune vide.
- 🔜 La vue de rattachement est provisoire. Elle deviendra un modèle dbt quand l'entrepôt sera construit (E5).
- 📄 Les données des communes viennent de l'IGN et de l'INSEE, diffusées par geo.api.gouv.fr sous Licence Ouverte (Etalab).
