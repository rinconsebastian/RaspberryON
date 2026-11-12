import json
import re

from tests.conftest import ORIGIN

WORDS = ("pc", "encend", "apag", "relé", "rele", "power", "raspberry", "control")


def neutral(text: str) -> bool:
    low = text.lower()
    return not any(re.search(rf"\b{w}", low) for w in WORDS)


async def test_manifest_is_public_valid_and_neutral(env):
    async with env.client() as c:
        r = await c.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    assert m["name"] == "Panel" and m["short_name"] == "Panel"
    assert m["display"] == "standalone" and m["start_url"] == "./" and m["scope"] == "./"
    assert "description" not in m
    assert neutral(r.text)  # sin mención al PC ni al control de encendido
    sizes = {i["sizes"] for i in m["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(i.get("purpose") == "maskable" for i in m["icons"])


async def test_manifest_uses_configured_app_name_escaped(make_env):
    e = make_env(extra_env={"APP_NAME": "Casa <b>"})
    async with e.client() as c:
        m = (await c.get("/manifest.webmanifest")).json()
        assert m["name"] == "Casa <b>"  # JSON: el navegador no lo interpreta como HTML
        page = (await c.get("/")).text
    assert "Casa &lt;b&gt;" in page and "Casa <b>" not in page


async def test_icons_are_public_pngs_and_unknown_is_404(env):
    async with env.client() as c:
        m = (await c.get("/manifest.webmanifest")).json()
        for icon in m["icons"]:
            r = await c.get("/" + icon["src"])
            assert r.status_code == 200 and r.headers["content-type"] == "image/png"
            assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
        assert (await c.get("/static/icons/apple-touch-icon.png")).status_code == 200
        for bad in ("nope.png", "..%2Fapp.css", "icon-192.png.bak"):
            r = await c.get(f"/static/icons/{bad}")
            assert r.status_code == 404 and r.content == b""


async def test_service_worker_is_network_only_and_never_caches(env):
    async with env.client() as c:
        r = await c.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert r.headers["cache-control"] == "no-store"
    js = r.text
    assert "addEventListener(\"fetch\"" in js
    for forbidden in ("caches.", "cache.put", "cache.add", "localStorage", "indexedDB"):
        assert forbidden not in js
    assert "Sin conexión" in js  # mensaje propio al no haber red
    offline = re.search(r"const OFFLINE_HTML = `(.*?)`", js, re.S).group(1)
    assert neutral(re.sub(r"<[^>]+>", " ", offline))  # lo único que ve el usuario sin red


async def test_pages_link_manifest_icons_and_register_the_worker(env):
    async with env.logged_in() as c:
        panel = (await c.get("/")).text
    async with env.client() as c:
        login = (await c.get("/")).text
        reg = await c.get("/static/sw-register.js")
    for page in (login, panel):
        assert '<link rel="manifest" href="manifest.webmanifest">' in page
        assert 'rel="apple-touch-icon"' in page and 'name="apple-mobile-web-app-capable"' in page
        assert "static/sw-register.js" in page
        assert "<script>" not in page  # la CSP no admite scripts en línea
    assert reg.status_code == 200 and 'register("sw.js")' in reg.text


async def test_install_metadata_without_session_does_not_reveal_purpose(env):
    async with env.client() as c:
        login = (await c.get("/")).text
        assert "apple-mobile-web-app-title\" content=\"Panel\"" in login
    assert neutral(re.sub(r"<[^>]+>", " ", login))


async def test_panel_js_and_api_remain_protected(env):
    async with env.client() as c:
        for path in ("/static/panel.js", "/api/status", "/api/events"):
            r = await c.get(path)
            assert r.status_code == 404 and r.content == b"", path


async def test_manifest_and_icons_carry_security_headers(env):
    async with env.client() as c:
        for path in ("/manifest.webmanifest", "/sw.js", "/static/icons/icon-192.png"):
            r = await c.get(path)
            assert "default-src 'self'" in r.headers["content-security-policy"]
            assert "server" not in r.headers
