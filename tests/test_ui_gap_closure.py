from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def test_no_emoji_or_unicode_glyph_icons_remain():
    forbidden = set("⛔⚠✓✔✕✖→←↑↓•×Δ")
    found = sorted(forbidden.intersection(HTML))
    assert not found, f"Emoji/unicode glyph icons still present: {found}"


def test_status_icons_are_inline_svg_with_current_color():
    assert "const ICONS = {" in HTML
    assert HTML.count('stroke="currentColor"') >= 8
    assert "arrowLeft:" in HTML and "arrowRight:" in HTML and "linkBroken:" in HTML


def test_required_ui_behaviors_are_wired():
    assert "alert(" not in HTML
    assert "function toast(" in HTML
    assert "skeleton-card" in HTML and "skeleton-bar" in HTML
    assert "empty-state" in HTML and "errorState()" in HTML
    assert "navigator.clipboard.writeText" in HTML
    assert 'aria-live="polite"' in HTML and "verdictAnnouncer" in HTML
    assert ":focus-visible" in HTML
    assert "body.presenter-mode" in HTML
    assert "Toggle Presenter Mode" in HTML


def test_tamper_ui_consumes_server_invalidation_payload():
    assert "downstream_seqs" in HTML
    assert "invalidated_seqs" in HTML
