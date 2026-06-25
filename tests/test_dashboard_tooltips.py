from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tip_system_uses_delegation_for_dynamic_verdict_triggers():
    js = (ROOT / "static/js/dashboard.js").read_text(encoding="utf-8")

    assert 'closest(".tip-trigger")' in js
    assert 'addEventListener("focusin"' in js
    assert 'addEventListener("mouseover"' in js
    assert 'querySelectorAll(".tip-trigger").forEach' not in js
    assert 'event.stopPropagation();\n    }, true)' not in js
    assert 'if (event.target.closest(".tip-trigger")) return;' in js
    assert "data-tip-title" in js
    assert "Claude's take" in js


def test_existing_column_header_tooltips_still_use_shared_markup():
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")

    assert 'class="tip-trigger target-tip-trigger"' in html
    assert 'data-tip-title="Trend Sense"' in html
    assert 'data-tip-title="Rating"' in html
    assert 'id="tip-popover"' in html
