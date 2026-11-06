# Fiches de décision

Chaque choix technique important a sa fiche : le contexte, les options comparées, la décision prise et ses conséquences. Les fiches sont numérotées dans l'ordre et ne sont jamais réécrites. Si une décision change, on écrit une nouvelle fiche qui remplace l'ancienne.

| N° | Décision | Statut | Date |
| --- | --- | --- | --- |
| [0001](0001-postgis.md) | Rattacher les observations aux communes avec PostGIS | ✅ Acceptée | 06/11/2026 |
| [0002](0002-orchestrateur.md) | Orchestrer les collectes et les transformations avec Airflow | ✅ Acceptée | 06/11/2026 |

## Modèle

```markdown
# NNNN – Titre de la décision

- **Statut :** proposée / acceptée / remplacée par NNNN
- **Date :**

## Contexte
Le problème à résoudre et les contraintes.

## Options étudiées
| Option | Avantages | Inconvénients |

## Décision
Ce qu'on retient, et pourquoi.

## Conséquences
Ce que ça change, ce que ça coûte, les limites connues.
```
