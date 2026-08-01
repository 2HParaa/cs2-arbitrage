# Contexte projet — CS2 Skin Arbitrage

## Objectif
Détecter des écarts de prix (arbitrage) sur les skins CS2 entre plusieurs
marketplaces, nets de frais, pour repérer des opportunités d'achat/revente.

## Décisions prises
- Cible finale : le plus de plateformes possible (large scraping), mais on
  démarre volontairement simple et on complexifie progressivement.
- Phase 1 : seulement les plateformes avec API publique/documentée pour
  éviter le scraping/anti-bot dès le départ :
  - Steam Community Market (endpoint public, pas de clé, mais rate-limité)
  - Skinport (API publique documentée, prix + frais)
- Phase 2+ (plus tard) : ajouter CS.Money, Buff163, DMarket, Bitskins...
  (scraping / API non-officielle, plus de robustesse nécessaire : headers,
  anti-bot, retries).
- Mode de fonctionnement : démarrer avec un script lancé à la demande
  (pas de temps réel ni d'alertes dès le début) ; le monitoring continu et
  les alertes viendront après un MVP qui marche.

## Architecture
Pipeline en 4 étapes :
1. **Collecteurs** (`src/cs2_arbitrage/sources/`) : un module par plateforme,
   qui implémente une interface commune `PriceSource` (pattern adapter) avec
   une méthode `get_price(item_name) -> Price`. Permet d'ajouter une
   plateforme sans toucher au reste du pipeline.
2. **Normalisation** (`normalize.py`) : mêmes noms d'items, même devise,
   frais réseau/marketplace déduits pour avoir un prix "net" comparable.
3. **Comparateur** (`compare.py`) : calcule le spread net entre chaque paire
   de plateformes pour une liste d'items donnée.
4. **Sortie** (`report.py`) : rapport texte en phase 1 ; alertes (mail,
   webhook...) en phase 2+.

## Stack technique
- Python (langage principal de l'utilisateur).
- `requests` pour les appels API en phase 1.
- Tests avec `pytest`.
- CI GitHub Actions prévue une fois le repo poussé (lint + tests sur chaque
  push).

## Préférences de l'utilisateur (contexte général, pas spécifique à ce projet)
- Debutant sur la gestion de codebase avec Git/GitHub — veut apprendre les
  bonnes pratiques en pratiquant (branches, commits clairs, PR, CI).
- Apprécie les explications détaillées et les approches qui le font monter
  en compétences, pas juste la solution la plus rapide.
- À l'aise en Python, notions de C.

## Prochaines étapes
- [ ] Initialiser le repo Git avec la structure ci-dessus.
- [ ] Implémenter `sources/base.py` (interface abstraite).
- [ ] Implémenter `sources/steam.py` et `sources/skinport.py`.
- [ ] Implémenter `normalize.py` et `compare.py`.
- [ ] Premier script bout-en-bout sur une petite liste d'items de test.
- [ ] Une fois que ça marche : ajouter une 3e plateforme, puis CI GitHub.
