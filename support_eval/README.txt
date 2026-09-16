Support Evaluator V2 — Smishie's Lab

Ce dossier contient le moteur de travail de l'évaluation des supports.

Fichiers :
- support_evaluator_v2.py
- support_effect_overrides.json

Le moteur lit directement invokers.db en lecture seule et charge automatiquement
tous les héros dont le rôle est Support.

Principes :
- Combat Output = DPS × min(TTD, durée combat)
- Impact brut = Output avec support / Output sans support - 1
- Score général /100 = percentile des impacts généraux
- Score boss /100 = percentile des impacts sur ce boss
- Heal utile = min(heal brut, PV manquants)
- Shield utile = min(shield, dégâts réellement absorbables)
- Revive ne vaut quelque chose que si une mort se produit
- Les effets complexes absents de coefficients_raw passent par le fichier overrides
- Profil Ulgorim 16 inclus
- Formule DEF retenue :
  1 / (1 + 0.0001696×DEF + 0.0000001245×DEF²)

Nirvelle :
- les effets DB sont chargés automatiquement ;
- heal/rez sont encore marqués provisional ;
- ils ne doivent pas être traités comme confirmés depuis les fichiers du jeu tant
  que son SkillConfig/Graph n'est pas décodé.

Étape suivante :
brancher le moteur aux résultats réels du simulateur Combat de server.py pour produire :
- Impact combat %
- Score général /100
- Score boss /100
- contribution par effet via contre-factuels

IMPORTANT :
Ces fichiers ne sont pas encore ajoutés au manifest d'auto-update. Ils servent de
base de développement GitHub avant intégration finale dans server.py.
