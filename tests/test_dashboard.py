"""api/dashboard.py is a plain string, no dependency — sanity checks
only (the actual rendering/JS behavior was verified in a real browser
against both a 404 API and a mocked one returning realistic trade data;
see docs/PROGRESS.md for what that covered)."""
from api.dashboard import DASHBOARD_HTML


def test_is_well_formed_html_document():
    assert DASHBOARD_HTML.strip().startswith("<!doctype html>")
    assert "<html" in DASHBOARD_HTML and "</html>" in DASHBOARD_HTML
    assert "<script>" in DASHBOARD_HTML and "</script>" in DASHBOARD_HTML


def test_fetches_only_read_only_endpoints():
    assert 'fetchJSON("/trades' in DASHBOARD_HTML
    assert 'fetchJSON("/trades/pnl/today' in DASHBOARD_HTML
    # must never reference an endpoint that could place/approve/reject a trade
    for forbidden in ("/buy", "/sell", "/approve", "/proposal\"", "POST"):
        assert forbidden not in DASHBOARD_HTML


def test_declares_itself_read_only_in_the_page_text():
    assert "Read-only" in DASHBOARD_HTML


def test_required_element_ids_present():
    for element_id in (
        "env", "pnlToday", "closedCount", "winRate", "openCount",
        "equityChart", "tradesBody",
    ):
        assert f'id="{element_id}"' in DASHBOARD_HTML
