"""The web app shell: the page and its self-hosted typeface."""
from fastapi.testclient import TestClient

from feedforward.api.main import app

client = TestClient(app)        # no lifespan: these routes do not need the engine


def test_app_page_revalidates_on_every_load():
    res = client.get("/app")
    assert res.status_code == 200 and "text/html" in res.headers["content-type"]
    assert res.headers["cache-control"] == "no-cache"
    assert "/app/fonts/inter-latin-wght-normal.woff2" in res.text


def test_font_is_served_from_the_app_itself():
    res = client.get("/app/fonts/inter-latin-wght-normal.woff2")
    assert res.status_code == 200 and res.headers["content-type"] == "font/woff2"
    assert res.content[:4] == b"wOF2"
    assert "immutable" in res.headers["cache-control"]


def test_font_route_serves_only_font_files():
    for bad in ("nope.woff2", "OFL.txt", "..%2Findex.html", "%2E%2E", "..\\index.html"):
        assert client.get(f"/app/fonts/{bad}").status_code == 404, bad
