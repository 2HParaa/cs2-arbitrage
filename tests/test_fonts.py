from unittest.mock import MagicMock

from cs2_arbitrage import fonts


def _reset():
    fonts._registered = False


def test_register_fonts_calls_add_font_resource_for_each_ttf(monkeypatch):
    _reset()
    monkeypatch.setattr(fonts.sys, "platform", "win32")
    fake_gdi32 = MagicMock()
    monkeypatch.setattr(fonts.ctypes, "windll", MagicMock(gdi32=fake_gdi32), raising=False)

    fonts.register_fonts()

    # Les deux .ttf embarqués (Regular + Bold) sont bien enregistrés.
    assert fake_gdi32.AddFontResourceExW.call_count == 2
    _reset()


def test_register_fonts_is_idempotent(monkeypatch):
    _reset()
    monkeypatch.setattr(fonts.sys, "platform", "win32")
    fake_gdi32 = MagicMock()
    monkeypatch.setattr(fonts.ctypes, "windll", MagicMock(gdi32=fake_gdi32), raising=False)

    fonts.register_fonts()
    fonts.register_fonts()

    assert fake_gdi32.AddFontResourceExW.call_count == 2  # pas ré-enregistré au 2e appel
    _reset()


def test_register_fonts_is_a_noop_outside_windows(monkeypatch):
    _reset()
    monkeypatch.setattr(fonts.sys, "platform", "linux")
    fake_gdi32 = MagicMock()
    monkeypatch.setattr(fonts.ctypes, "windll", MagicMock(gdi32=fake_gdi32), raising=False)

    fonts.register_fonts()

    fake_gdi32.AddFontResourceExW.assert_not_called()
    _reset()


def test_fonts_dir_contains_the_embedded_ttf_files():
    names = {path.name for path in fonts._fonts_dir().glob("*.ttf")}

    assert names == {"NotoSans-Regular.ttf", "NotoSans-Bold.ttf"}
