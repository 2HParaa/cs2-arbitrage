# CS2 Skin Arbitrage

Détecte des écarts de prix (arbitrage) sur les skins CS2 entre plusieurs
marketplaces, nets de frais, pour repérer des opportunités d'achat/revente.

Compare les prix sur 7 plateformes (Steam Community Market, Skinport,
CS.Money, Waxpeer, CS.Deals, White.market, market.csgo.com), calcule le
spread net de frais entre chaque paire, et affiche un rapport (console et
fenêtre graphique) des meilleures opportunités trouvées.

## ⚠️ Avertissement

Ceci est un **projet personnel**, développé pour apprendre et pour un usage
propre — pas un produit maintenu, audité, ni destiné à un usage en
production. Fourni tel quel, sans garantie d'aucune sorte.

- **Aucun trade n'est jamais exécuté automatiquement.** Le projet est
  strictement en lecture seule : il interroge des endpoints publics pour
  comparer des prix, et affiche des liens pour accélérer l'exécution
  *manuelle* d'un trade. Il ne se connecte à aucun compte, ne stocke et ne
  requiert aucun identifiant ou clé API.
- **Vérifiez les conditions d'utilisation (ToS) de chaque plateforme avant
  toute utilisation.** Ce projet interroge des endpoints publics de
  plusieurs marketplaces tierces ; certaines interdisent explicitement le
  scraping, l'automatisation ou l'usage non-officiel de leurs données dans
  leurs CGU. C'est à vous de vérifier que votre usage respecte les
  conditions en vigueur de chaque plateforme au moment où vous l'utilisez
  — elles peuvent changer sans préavis.
- Ce projet n'est affilié à Valve, Steam, ni à aucune des marketplaces
  listées ci-dessus.
- Les prix crypto/skins sont volatils et les données peuvent contenir des
  anomalies (offre isolée à un prix aberrant, catalogue temporairement
  restreint pendant une migration, etc.) : ne prenez aucune décision
  financière sur la seule base de ce rapport sans vérifier vous-même
  l'opportunité affichée directement sur la plateforme concernée.

Aucune licence open-source n'est attachée à ce dépôt pour l'instant — tous
droits réservés par défaut.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

## Utilisation

```bash
python main.py
```

Ouvre un navigateur graphique pour sélectionner des items (ou lancer un
scan de tout le catalogue entre deux prix), puis affiche le rapport des
meilleures opportunités trouvées.

## Structure

```
src/cs2_arbitrage/
    sources/    # un module par marketplace (Steam, Skinport, ...)
    normalize.py
    compare.py
    scanner.py
    report.py
    gui.py
tests/
```

## Lancer les tests

```bash
pytest
```
