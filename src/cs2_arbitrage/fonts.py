import ctypes
import sys
from pathlib import Path

# "Noto Sans" (Google, SIL Open Font License 1.1 — texte complet dans
# assets/fonts/OFL.txt) sert de police pour tous les noms d'items dans la
# GUI. Choisie comme alternative à Motiva Sans (police interne développée
# pour Valve, utilisée par Steam) : visuellement proche (sans-serif
# géométrique, lisible, terminaisons arrondies similaires) mais sous une
# licence qui autorise sans ambiguïté l'usage personnel ET commercial ainsi
# que la redistribution — contrairement à Motiva Sans, dont le statut de
# licence en dehors de Valve reste flou (seulement trouvable sur des sites
# de téléchargement tiers à la fiabilité variable), un problème qui
# deviendrait concret une fois le projet packagé en exécutable
# redistribuable.
ITEM_NAME_FONT_FAMILY = "Noto Sans"

# Windows GDI : police visible pour ce process seulement, pas installée sur la machine.
_FR_PRIVATE = 0x10

_registered = False


def _fonts_dir() -> Path:
    # PyInstaller extrait les fichiers de données embarqués vers un dossier
    # temporaire exposé via sys._MEIPASS ; en exécution depuis les sources,
    # on part du dossier du package pour remonter à la racine du repo.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
    return base / "assets" / "fonts"


def register_fonts() -> None:
    """Enregistre les .ttf embarqués (assets/fonts/) pour ce process, sans
    installation système — nécessaire pour que tkinter résolve
    ITEM_NAME_FONT_FAMILY même sur une machine où Noto Sans n'est pas
    installée. Windows uniquement (AddFontResourceExW, API GDI) : sans
    effet ailleurs, tkinter retombe alors sur la police par défaut plutôt
    que de planter. Idempotent (pas de ré-enregistrement à chaque fenêtre
    ouverte)."""
    global _registered
    if _registered or sys.platform != "win32":
        return
    _registered = True
    for ttf_path in _fonts_dir().glob("*.ttf"):
        ctypes.windll.gdi32.AddFontResourceExW(str(ttf_path), _FR_PRIVATE, 0)
