"""Static accessibility guards (no browser needed). They protect the fixes from the accessibility pass;
they do not replace axe / Lighthouse / a screen-reader check (see docs/ACCESSIBILITY.md)."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as main_mod

ROOT = Path(__file__).resolve().parent.parent.parent
PAGES = ["app/index.html", "portal/index.html", "portal/dashboard.html"]


def _lum(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(fg, bg):
    a, b = _lum(fg), _lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# (foreground, background, minimum ratio): the colour pairs the shared stylesheet relies on
PAIRS = [
    ("#ffffff", "#0f766e", 4.5),   # white on primary
    ("#ffffff", "#115e59", 4.5),   # white on primary-dark
    ("#ffffff", "#0369a1", 4.5),   # white on secondary
    ("#b91c1c", "#ffffff", 4.5),   # danger text on white
    ("#475569", "#ffffff", 4.5),   # muted text on white
    ("#475569", "#f8fafc", 4.5),   # muted text on page background
    ("#047857", "#ffffff", 4.5),   # success text on white
    ("#b45309", "#ffffff", 4.5),   # warning text on white
    ("#ffffff", "#047857", 4.5), ("#ffffff", "#c2410c", 4.5), ("#ffffff", "#b91c1c", 4.5),
    ("#ffffff", "#7e22ce", 4.5), ("#ffffff", "#475569", 4.5),  # icon-array dots
    ("#1d4ed8", "#ffffff", 3.0),   # focus ring against white (non-text 3:1)
]


@pytest.mark.parametrize("fg,bg,minimum", PAIRS)
def test_colour_pairs_meet_wcag_aa(fg, bg, minimum):
    assert ratio(fg, bg) >= minimum, f"{fg} on {bg} = {ratio(fg, bg):.2f}"


def test_stylesheet_tokens_match_the_tested_pairs():
    css = (ROOT / "app" / "assets" / "a11y.css").read_text(encoding="utf-8")
    for token, value in {"--primary": "#0f766e", "--danger": "#b91c1c", "--text-muted": "#475569", "--success": "#047857"}.items():
        assert re.search(rf"{re.escape(token)}:\s*{value}", css), token
    assert ":focus-visible" in css and "prefers-reduced-motion" in css and ".skip-link" in css


@pytest.mark.parametrize("page", PAGES)
def test_pages_load_shared_layer_and_basics(page):
    html = (ROOT / page).read_text(encoding="utf-8")
    assert "/assets/a11y.css" in html and "/assets/a11y.js" in html
    assert re.search(r"<html[^>]*\blang=", html)
    viewport = re.search(r'<meta name="viewport"[^>]*>', html).group(0)
    assert "user-scalable=no" not in viewport and "maximum-scale" not in viewport  # zoom must stay possible
    assert not re.search(r'tabindex="[1-9]', html)                                   # no positive tabindex


def test_shared_assets_are_served():
    c = TestClient(main_mod.app)
    assert c.get("/assets/a11y.css").status_code == 200
    assert c.get("/assets/a11y.js").status_code == 200


def test_every_modal_gets_dialog_semantics_from_the_script():
    js = (ROOT / "app" / "assets" / "a11y.js").read_text(encoding="utf-8")
    for needle in ("role', 'dialog'", "aria-modal", "Escape", "aria-labelledby"):
        assert needle in js
    html = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
    assert html.count('class="modal-overlay') >= 4


def test_audit_script_is_shipped_for_manual_runs():
    assert (ROOT / "eval" / "a11y_audit.js").exists()
