import hashlib
import io
from unittest.mock import MagicMock, Mock, patch

import pytest

from cs2_arbitrage.catalog import (
    CatalogEntry,
    CatalogError,
    ItemCatalog,
    fetch_icon,
    fetch_icon_bytes,
    icon_image_url,
)

SKINPORT_CATALOG = [
    {
        "market_hash_name": "AK-47 | Redline (Field-Tested)",
        "market_page": "https://skinport.com/market/rifle/ak-47?item=Redline",
    },
    {
        "market_hash_name": "StatTrak™ AK-47 | Redline (Minimal Wear)",
        "market_page": "https://skinport.com/market/rifle/ak-47?item=Redline",
    },
    {
        "market_hash_name": "AK-47 | Vulcan (Factory New)",
        "market_page": "https://skinport.com/market/rifle/ak-47?item=Vulcan",
    },
    {
        "market_hash_name": "★ Karambit | Doppler (Factory New)",
        "market_page": "https://skinport.com/market/knife/karambit?item=Doppler",
    },
    {
        "market_hash_name": "★ StatTrak™ Karambit",
        "market_page": "https://skinport.com/market/knife/karambit?item=Vanilla",
    },
    {
        "market_hash_name": "Sticker | Basilisk",
        "market_page": "https://skinport.com/market/sticker?item=Basilisk",
    },
]


@pytest.fixture(autouse=True)
def mock_sleep(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("cs2_arbitrage.catalog.time.sleep", mock)
    return mock


@pytest.fixture(autouse=True)
def no_waxpeer_images_by_default(monkeypatch):
    # fetch_icon essaie Waxpeer avant Steam : par défaut dans les tests, on
    # simule un catalogue Waxpeer vide pour forcer le repli Steam (chemin
    # historiquement testé ci-dessous) sans dépendre du réseau. Les tests
    # du chemin Waxpeer remplacent explicitement ce mock.
    from cs2_arbitrage import catalog

    catalog._waxpeer_image_index.cache_clear()
    monkeypatch.setattr(catalog, "fetch_waxpeer_items", list)
    yield
    catalog._waxpeer_image_index.cache_clear()


def _mock_response(json_data=None, content=b"", status_code=200):
    response = Mock()
    response.status_code = status_code
    response.raise_for_status = Mock()
    if json_data is not None:
        response.json.return_value = json_data
    response.content = content
    return response


def _search_response(results):
    return {
        "success": True,
        "results": [
            {"hash_name": hash_name, "asset_description": {"icon_url": icon_url}}
            for hash_name, icon_url in results
        ],
    }


def test_icon_image_url_builds_expected_url():
    assert icon_image_url("abc123", size=64) == (
        "https://community.akamai.steamstatic.com/economy/image/abc123/64fx64f"
    )


@patch("cs2_arbitrage.catalog.requests.get")
def test_fetch_icon_bytes_returns_content(mock_get):
    mock_get.return_value = _mock_response(content=b"\x89PNG...")

    assert fetch_icon_bytes("abc123") == b"\x89PNG..."


@patch("cs2_arbitrage.catalog.requests.get")
def test_fetch_icon_bytes_raises_on_network_error(mock_get):
    import requests

    mock_get.side_effect = requests.ConnectionError("boom")

    with pytest.raises(CatalogError):
        fetch_icon_bytes("abc123")


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_fetch_types_returns_only_known_weapon_categories_present(mock_get):
    mock_get.return_value = _mock_response(SKINPORT_CATALOG)

    catalog = ItemCatalog()

    # "Sticker" n'est pas dans TYPE_LABELS (hors-scope) : absent du résultat.
    assert catalog.fetch_types() == ["Knife", "Rifle"]


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_fetch_weapons_filters_by_type_and_dedupes_names(mock_get):
    mock_get.return_value = _mock_response(SKINPORT_CATALOG)

    catalog = ItemCatalog()

    assert catalog.fetch_weapons("Rifle") == ["AK-47"]
    assert mock_get.call_count == 1  # catalogue Skinport chargé une seule fois


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_fetch_skins_extracts_skin_names_and_representative_hash_name(mock_get):
    mock_get.return_value = _mock_response(SKINPORT_CATALOG)

    catalog = ItemCatalog()
    skins = catalog.fetch_skins("Rifle", "AK-47")

    assert skins == [
        CatalogEntry(label="Redline", representative_hash_name="AK-47 | Redline (Field-Tested)"),
        CatalogEntry(label="Vulcan", representative_hash_name="AK-47 | Vulcan (Factory New)"),
    ]


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_fetch_skins_groups_vanilla_items_without_pipe(mock_get):
    mock_get.return_value = _mock_response(SKINPORT_CATALOG)

    catalog = ItemCatalog()
    skins = catalog.fetch_skins("Knife", "Karambit")

    labels = [entry.label for entry in skins]
    assert "(Vanilla)" in labels
    assert "Doppler" in labels


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_fetch_variants_reuses_fetch_skins_cache_without_extra_request(mock_get):
    mock_get.return_value = _mock_response(SKINPORT_CATALOG)

    catalog = ItemCatalog()
    catalog.fetch_skins("Rifle", "AK-47")
    call_count_after_skins = mock_get.call_count

    variants = catalog.fetch_variants("Rifle", "AK-47", "Redline")

    assert variants == [
        "AK-47 | Redline (Field-Tested)",
        "StatTrak™ AK-47 | Redline (Minimal Wear)",
    ]
    assert mock_get.call_count == call_count_after_skins


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_fetch_weapons_raises_on_unknown_type(mock_get):
    mock_get.return_value = _mock_response(SKINPORT_CATALOG)

    catalog = ItemCatalog()

    with pytest.raises(CatalogError, match="Type d'item inconnu"):
        catalog.fetch_weapons("Sticker")


@patch("cs2_arbitrage.sources.skinport.requests.get")
def test_ensure_catalog_raises_on_network_error(mock_get):
    import requests

    mock_get.side_effect = requests.ConnectionError("boom")

    catalog = ItemCatalog()

    with pytest.raises(CatalogError, match="Impossible de charger le catalogue Skinport"):
        catalog.fetch_types()


# -- fetch_icon (résolution Steam + cache disque) --------------------------


@patch("cs2_arbitrage.catalog.requests.get")
def test_fetch_icon_uses_disk_cache_without_network_call(mock_get, tmp_path):
    cache_dir = tmp_path / "icons"
    cache_dir.mkdir()
    hash_name = "AK-47 | Redline (Field-Tested)"
    cache_path = cache_dir / f"{hashlib.sha1(hash_name.encode()).hexdigest()}.png"
    cache_path.write_bytes(b"cached-bytes")

    result = fetch_icon(hash_name, cache_dir=cache_dir)

    assert result == b"cached-bytes"
    mock_get.assert_not_called()


@patch("cs2_arbitrage.catalog.requests.get")
def test_fetch_icon_resolves_via_steam_and_writes_disk_cache_on_miss(mock_get, tmp_path):
    cache_dir = tmp_path / "icons"
    hash_name = "AK-47 | Redline (Field-Tested)"
    mock_get.side_effect = [
        _mock_response(_search_response([(hash_name, "icon123")])),
        _mock_response(content=b"\x89PNG-bytes"),
    ]

    result = fetch_icon(hash_name, cache_dir=cache_dir)

    assert result == b"\x89PNG-bytes"
    cached_files = list(cache_dir.glob("*.png"))
    assert len(cached_files) == 1
    assert cached_files[0].read_bytes() == b"\x89PNG-bytes"


@patch("cs2_arbitrage.catalog.requests.get")
def test_fetch_icon_raises_when_steam_result_does_not_match_exactly(mock_get, tmp_path):
    mock_get.return_value = _mock_response(_search_response([("Un autre item", "icon123")]))

    with pytest.raises(CatalogError, match="n'a pas trouvé d'image"):
        fetch_icon("AK-47 | Redline (Field-Tested)", cache_dir=tmp_path / "icons")


@patch("cs2_arbitrage.catalog.requests.get")
def test_fetch_icon_retries_on_429_then_succeeds(mock_get, tmp_path, mock_sleep):
    hash_name = "AK-47 | Redline (Field-Tested)"
    mock_get.side_effect = [
        _mock_response(status_code=429),
        _mock_response(_search_response([(hash_name, "icon123")])),
        _mock_response(content=b"bytes"),
    ]

    result = fetch_icon(hash_name, cache_dir=tmp_path / "icons")

    assert result == b"bytes"


@patch("cs2_arbitrage.catalog.requests.get")
def test_fetch_icon_raises_after_exhausting_retries_on_429(mock_get, tmp_path):
    mock_get.return_value = _mock_response(status_code=429)

    with pytest.raises(CatalogError):
        fetch_icon("AK-47 | Redline (Field-Tested)", cache_dir=tmp_path / "icons")

    assert mock_get.call_count == 4


# -- fetch_icon (résolution Waxpeer, sans throttle) -------------------------


def _png_bytes(size=8, color=(255, 0, 0, 255)):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGBA", (size, size), color).save(buffer, format="PNG")
    return buffer.getvalue()


@patch("cs2_arbitrage.catalog.requests.get")
def test_fetch_icon_prefers_waxpeer_over_steam(mock_get, tmp_path, monkeypatch):
    from cs2_arbitrage import catalog

    hash_name = "AK-47 | Redline (Field-Tested)"
    monkeypatch.setattr(
        catalog,
        "fetch_waxpeer_items",
        lambda: [{"name": hash_name, "img": "https://images.waxpeer.com/a.webp"}],
    )
    catalog._waxpeer_image_index.cache_clear()
    mock_get.return_value = _mock_response(content=_png_bytes())

    result = fetch_icon(hash_name, size=32, cache_dir=tmp_path / "icons")

    assert result != b""
    # Un seul appel réseau (l'image), pas de résolution Steam (search + image).
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == "https://images.waxpeer.com/a.webp"


@patch("cs2_arbitrage.catalog.requests.get")
def test_fetch_icon_falls_back_to_steam_when_item_absent_from_waxpeer(
    mock_get, tmp_path, monkeypatch
):
    from cs2_arbitrage import catalog

    hash_name = "AK-47 | Redline (Field-Tested)"
    monkeypatch.setattr(catalog, "fetch_waxpeer_items", list)
    catalog._waxpeer_image_index.cache_clear()
    mock_get.side_effect = [
        _mock_response(_search_response([(hash_name, "icon123")])),
        _mock_response(content=b"steam-bytes"),
    ]

    result = fetch_icon(hash_name, cache_dir=tmp_path / "icons")

    assert result == b"steam-bytes"


@patch("cs2_arbitrage.catalog.requests.get")
def test_fetch_icon_falls_back_to_steam_when_waxpeer_index_unavailable(
    mock_get, tmp_path, monkeypatch
):
    from cs2_arbitrage import catalog
    from cs2_arbitrage.sources.waxpeer import WaxpeerError

    hash_name = "AK-47 | Redline (Field-Tested)"

    def _raise():
        raise WaxpeerError("boom")

    monkeypatch.setattr(catalog, "fetch_waxpeer_items", _raise)
    catalog._waxpeer_image_index.cache_clear()
    mock_get.side_effect = [
        _mock_response(_search_response([(hash_name, "icon123")])),
        _mock_response(content=b"steam-bytes"),
    ]

    result = fetch_icon(hash_name, cache_dir=tmp_path / "icons")

    assert result == b"steam-bytes"


@patch("cs2_arbitrage.catalog.requests.get")
def test_waxpeer_image_index_is_built_only_once_across_calls(mock_get, tmp_path, monkeypatch):
    from cs2_arbitrage import catalog

    call_count = {"n": 0}

    def _fetch():
        call_count["n"] += 1
        return [
            {"name": "AK-47 | Redline (Field-Tested)", "img": "https://images.waxpeer.com/a.webp"},
            {"name": "AWP | Asiimov (Field-Tested)", "img": "https://images.waxpeer.com/b.webp"},
        ]

    monkeypatch.setattr(catalog, "fetch_waxpeer_items", _fetch)
    catalog._waxpeer_image_index.cache_clear()
    mock_get.return_value = _mock_response(content=_png_bytes())

    fetch_icon("AK-47 | Redline (Field-Tested)", cache_dir=tmp_path / "icons")
    fetch_icon("AWP | Asiimov (Field-Tested)", cache_dir=tmp_path / "icons")

    assert call_count["n"] == 1
