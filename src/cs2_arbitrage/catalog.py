import hashlib
import io
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps

from cs2_arbitrage.sources.skinport import fetch_items
from cs2_arbitrage.sources.steam import CS2_APP_ID
from cs2_arbitrage.sources.waxpeer import WaxpeerError
from cs2_arbitrage.sources.waxpeer import fetch_items as fetch_waxpeer_items

# La navigation Type/Arme/Skin/Variante est sourcée depuis Skinport (déjà
# une source du projet) : elle renvoie tout son catalogue en UN SEUL appel
# non paginé, jamais rate-limité jusqu'ici, contrairement au market Steam.
# Vérifié en réel le 2026-08-02 : le champ "market_page" de chaque item
# encode déjà Type + Arme dans son URL, ex:
# "https://skinport.com/market/rifle/ak-47?item=Aphrodite".
# Skinport n'a en revanche aucune image. Les icônes sont désormais
# sourcées en priorité depuis le dump Waxpeer (sources/waxpeer.py) : chaque
# item y porte une URL d'image directe, dans le même appel unique que les
# prix, sans throttle. Steam ne sert plus que de repli pour les items
# absents du catalogue Waxpeer (moins couvert : seulement les items
# actuellement en vente là-bas), à la demande et avec un cache disque
# (cf. fetch_icon) — c'est ce chemin de repli qui reste throttlé.
ICON_SEARCH_URL = "https://steamcommunity.com/market/search/render/"
ICON_BASE_URL = "https://community.akamai.steamstatic.com/economy/image"
# Les images brutes Waxpeer sont en 512x384 (vérifié le 2026-08-03) : 192
# reste largement en dessous, pas de perte de netteté à l'affichage.
ICON_SIZE = 192
ICON_CACHE_DIR = Path(".cache/icons")

THROTTLE_SECONDS = 1.5
MAX_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 10

# Catégories Skinport correspondant à des "skins d'armes" (le besoin
# exprimé pour ce projet), gardées pour le V1. Ce sont des emplacements
# d'équipement du jeu, très stables : contrairement aux skins, pas besoin
# de les déduire dynamiquement. Les autres catégories Skinport (sticker,
# graffiti, container, patch, agent, music-kit, collectible, pass, key,
# gift, tag, tool, equipment) restent hors-scope.
TYPE_LABELS = {
    "rifle": "Rifle",
    "pistol": "Pistol",
    "smg": "SMG",
    "heavy": "Heavy",
    "knife": "Knife",
    "gloves": "Gloves",
}

# Regroupe les items sans skin (couteaux "vanilla" comme "★ StatTrak™
# Karambit") sous une entrée dédiée plutôt que de les exclure.
VANILLA_LABEL = "(Vanilla)"

_QUALITY_PREFIXES = ("StatTrak™ ", "Souvenir ", "★ ")
_WEAR_PATTERN = re.compile(r"^(?P<base>.*) \((?P<wear>[^()]+)\)$")


class CatalogError(Exception):
    """Erreur lors de la navigation dans le catalogue ou de la résolution
    d'une image."""


@dataclass(frozen=True)
class CatalogEntry:
    label: str
    representative_hash_name: str


def icon_image_url(icon_url: str, size: int = ICON_SIZE) -> str:
    return f"{ICON_BASE_URL}/{icon_url}/{size}fx{size}f"


def fetch_icon_bytes(icon_url: str, size: int = ICON_SIZE) -> bytes:
    try:
        response = requests.get(icon_image_url(icon_url, size), timeout=10)
        response.raise_for_status()
    except requests.RequestException as error:
        raise CatalogError(f"Impossible de charger l'image '{icon_url}'") from error
    return response.content


def fetch_icon(hash_name: str, size: int = ICON_SIZE, cache_dir: Path = ICON_CACHE_DIR) -> bytes:
    """Renvoie l'image (PNG) d'un skin, identifié par son market_hash_name.
    Mise en cache sur disque : une fois résolue, une image n'est plus
    jamais redemandée (ni dans cette session, ni dans une future)."""
    cache_path = cache_dir / f"{hashlib.sha1(hash_name.encode()).hexdigest()}.png"
    if cache_path.exists():
        return cache_path.read_bytes()

    image_bytes = _fetch_icon_from_waxpeer(hash_name, size)
    if image_bytes is None:
        icon_url = _resolve_icon_url(hash_name)
        image_bytes = fetch_icon_bytes(icon_url, size)

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(image_bytes)
    return image_bytes


@lru_cache(maxsize=1)
def _waxpeer_image_index() -> dict:
    """market_hash_name -> URL d'image, à partir du dump Waxpeer (un seul
    appel, mis en cache pour la durée du process : pas question de
    retélécharger ~5 Mo de catalogue à chaque icône résolue)."""
    try:
        items = fetch_waxpeer_items()
    except (requests.RequestException, WaxpeerError):
        return {}
    return {item["name"]: item["img"] for item in items if item.get("img")}


def _fetch_icon_from_waxpeer(hash_name: str, size: int) -> bytes | None:
    image_url = _waxpeer_image_index().get(hash_name)
    if image_url is None:
        return None
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return None

    # Les images Waxpeer ne sont pas carrées (512x384) : un simple resize
    # vers (size, size) écraserait l'aspect ratio. On les fait plutôt tenir
    # dans le carré (contain) puis on centre sur un canevas transparent,
    # comme le fait déjà Steam côté serveur pour ses propres icônes.
    image = Image.open(io.BytesIO(response.content)).convert("RGBA")
    fitted = ImageOps.contain(image, (size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - fitted.width) // 2, (size - fitted.height) // 2)
    canvas.paste(fitted, offset, fitted)
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def _resolve_icon_url(hash_name: str) -> str:
    data = _fetch_with_retry(
        ICON_SEARCH_URL,
        params={"query": hash_name, "appid": CS2_APP_ID, "norender": 1, "count": 1},
    )
    if not data.get("success"):
        raise CatalogError(f"Échec de la recherche Steam pour '{hash_name}'")

    match = next((r for r in data.get("results", []) if r.get("hash_name") == hash_name), None)
    if match is None:
        raise CatalogError(f"Steam n'a pas trouvé d'image pour '{hash_name}'")
    return match["asset_description"]["icon_url"]


def _fetch_with_retry(url: str, params: dict) -> dict:
    for attempt in range(MAX_ATTEMPTS):
        time.sleep(THROTTLE_SECONDS)
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 429 and attempt < MAX_ATTEMPTS - 1:
            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
            continue
        if response.status_code == 429:
            raise CatalogError(
                f"Steam limite les requêtes (429) lors de la résolution d'une image, "
                f"même après {MAX_ATTEMPTS} tentatives"
            )
        response.raise_for_status()
        return response.json()


def _parse_hash_name(hash_name: str) -> tuple[str, str | None, str | None]:
    """Extrait (arme, skin, wear) d'un market_hash_name, ex:
    "StatTrak™ AK-47 | Redline (Field-Tested)" -> ("AK-47", "Redline", "Field-Tested")
    "★ StatTrak™ Karambit" -> ("Karambit", None, None)
    Ne reconstruit rien : le hash_name d'origine reste la valeur à utiliser
    pour get_price(), ce parsing ne sert qu'à regrouper/naviguer.
    """
    working = hash_name
    for prefix in _QUALITY_PREFIXES:
        working = working.replace(prefix, "")

    wear = None
    match = _WEAR_PATTERN.match(working)
    if match:
        working = match.group("base")
        wear = match.group("wear")

    if " | " in working:
        weapon, skin = working.split(" | ", 1)
        skin = skin.strip()
    else:
        weapon, skin = working, None

    return weapon.strip(), skin, wear


def _category_slug(market_page: str) -> str | None:
    parts = [p for p in urlparse(market_page).path.split("/") if p]
    # ex: ["market", "rifle", "ak-47"] -> "rifle"
    return parts[1] if len(parts) > 1 else None


class ItemCatalog:
    """Navigue Type -> Arme -> Skin -> Variante sans base de données codée
    en dur (à part la petite liste de catégories TYPE_LABELS, stable côté
    jeu) : tout est déduit du catalogue Skinport, récupéré une fois par
    session."""

    def __init__(self):
        self._catalog = None
        self._weapon_cache = {}
        self._skin_cache = {}
        self._variant_cache = {}

    def fetch_types(self) -> list[str]:
        self._ensure_catalog()
        present = {_category_slug(item["market_page"]) for item in self._catalog}
        return sorted(label for slug, label in TYPE_LABELS.items() if slug in present)

    def fetch_weapons(self, item_type: str) -> list[str]:
        if item_type not in self._weapon_cache:
            slug = self._type_slug(item_type)
            weapons = {
                _parse_hash_name(item["market_hash_name"])[0]
                for item in self._catalog
                if _category_slug(item["market_page"]) == slug
            }
            self._weapon_cache[item_type] = sorted(weapons)
        return self._weapon_cache[item_type]

    def fetch_skins(self, item_type: str, weapon: str) -> list[CatalogEntry]:
        key = (item_type, weapon)
        if key not in self._skin_cache:
            slug = self._type_slug(item_type)
            matches = [
                item
                for item in self._catalog
                if _category_slug(item["market_page"]) == slug
                and _parse_hash_name(item["market_hash_name"])[0] == weapon
            ]
            # Réutilisé tel quel par fetch_variants : pas de calcul
            # supplémentaire pour descendre au niveau Variante.
            self._variant_cache[key] = matches

            skin_examples = {}
            for item in matches:
                skin = _parse_hash_name(item["market_hash_name"])[1] or VANILLA_LABEL
                skin_examples.setdefault(skin, item["market_hash_name"])
            self._skin_cache[key] = [
                CatalogEntry(label=skin, representative_hash_name=hash_name)
                for skin, hash_name in sorted(skin_examples.items())
            ]
        return self._skin_cache[key]

    def fetch_variants(self, item_type: str, weapon: str, skin: str) -> list[str]:
        key = (item_type, weapon)
        if key not in self._variant_cache:
            self.fetch_skins(item_type, weapon)
        target_skin = None if skin == VANILLA_LABEL else skin
        variants = [
            item["market_hash_name"]
            for item in self._variant_cache[key]
            if _parse_hash_name(item["market_hash_name"])[1] == target_skin
        ]
        return sorted(variants)

    def _ensure_catalog(self) -> None:
        if self._catalog is not None:
            return
        try:
            self._catalog = fetch_items()
        except requests.RequestException as error:
            raise CatalogError("Impossible de charger le catalogue Skinport") from error

    def _type_slug(self, item_type: str) -> str:
        self._ensure_catalog()
        for slug, label in TYPE_LABELS.items():
            if label == item_type:
                return slug
        raise CatalogError(f"Type d'item inconnu : '{item_type}'")
