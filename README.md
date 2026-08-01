# CS2 Skin Arbitrage

Détecte des écarts de prix (arbitrage) sur les skins CS2 entre plusieurs
marketplaces, nets de frais, pour repérer des opportunités d'achat/revente.

Voir [CLAUDE.md](CLAUDE.md) pour le contexte détaillé du projet (objectif,
décisions, architecture, roadmap).

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

## Structure

```
src/cs2_arbitrage/
    sources/    # un module par marketplace (Steam, Skinport, ...)
    normalize.py
    compare.py
    report.py
tests/
```

## Lancer les tests

```bash
pytest
```
