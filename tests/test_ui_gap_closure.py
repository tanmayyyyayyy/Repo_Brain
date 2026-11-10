from pathlib import Path
from repobrain.server import find_index_html


ROOT = Path(__file__).resolve().parent.parent
HTML = Path(find_index_html()).read_text(encoding="utf-8")


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


def test_highlight_code_uses_single_pass_tokenizer():
    assert "const KW = new Set([" in HTML
    assert "while ((m = re.exec(raw)))" in HTML
    # Must not chain sequential .replace() passes over inserted <span class="..."> attributes
    assert 's.replace(/(#[^\\n]*)/g' not in HTML


def test_demo_uses_fictional_agent_identities():
    demo_src = (ROOT / "repobrain" / "demo.py").read_text(encoding="utf-8")
    assert "copilot-swe-agent" not in demo_src
    assert "noreply@anthropic.com" not in demo_src
    assert "demo-agent[bot]" in demo_src
    assert "refactor-bot[bot]" in demo_src

