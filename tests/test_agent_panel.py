"""
Regression tests for the Fire Intelligence Agent panel's message rendering.

Root cause of the "agent is not working" crash: `_render_message` built a
re.sub replacement *template* containing NUL-byte sentinels written as an
x-hex escape, and Python's replacement-template parser rejects that escape
("bad escape" re.error). It raised on every bot reply, so any agent answer
crashed the whole page.
"""
from __future__ import annotations

from dashboard.agent import panel


def test_richtext_does_not_raise_on_bold():
    # this exact transformation used to raise re.error: bad escape \x
    out = panel._richtext("**Persistent Source** near Surat\nrisk 73/100")
    assert out == "<strong>Persistent Source</strong> near Surat<br>risk 73/100"


def test_richtext_escapes_html():
    out = panel._richtext("<script>alert(1)</script> **bold**")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "<strong>bold</strong>" in out


def test_richtext_plain_text_untouched():
    assert panel._richtext("no markup here") == "no markup here"


def test_richtext_handles_multiple_and_unbalanced_markers():
    assert panel._richtext("**a** and **b**") == "<strong>a</strong> and <strong>b</strong>"
    # a lone ** must not blow up or emit a tag
    assert "strong" not in panel._richtext("2 ** 3 = compute")


def test_render_message_bot_reply_does_not_raise(monkeypatch):
    calls = []
    monkeypatch.setattr(panel.st, "markdown", lambda *a, **k: calls.append(a))
    panel._render_message(
        {"role": "bot", "text": "**Found 3** alerts", "ts": "10:00",
         "cards": [], "mode": "deterministic"},
        scope="test", idx=0,
    )
    assert calls and "<strong>Found 3</strong>" in calls[-1][0]
