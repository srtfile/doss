"""
app.py — Flask backend for Anime Stream Finder
Serves: Kiwi SUB/DUB m3u8 streams + realid
Deploy on Render: render.com
"""
from flask import Flask, request, jsonify, send_from_directory
import base64, json, re, time, os
import requests
from bs4 import BeautifulSoup

app = Flask(__name__, static_folder="static")

# ── Constants ─────────────────────────────────────────────────────────────────
BASE        = "https://anikototv.to"
MAPPER_BASE = "https://mapper.nekostream.site/api/mal"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

CDN_HOST_MAP = {
    "vault-10.owocdn.top":"10.bigdreamsmalldih.site",
    "vault-11.owocdn.top":"11.bigdreamsmalldih.site",
    "vault-12.owocdn.top":"12.bigdreamsmalldih.site",
    "vault-13.owocdn.top":"13.bigdreamsmalldih.site",
    "vault-14.owocdn.top":"14.bigdreamsmalldih.site",
    "vault-15.owocdn.top":"15.bigdreamsmalldih.site",
    "vault-16.owocdn.top":"16.bigdreamsmalldih.site",
    "vault-99.owocdn.top":"99.bigdreamsmalldih.site",
    "vault-01.uwucdn.top":"uwu1.bigdreamsmalldih.site",
    "vault-02.uwucdn.top":"uwu2.bigdreamsmalldih.site",
    "vault-03.uwucdn.top":"uwu3.bigdreamsmalldih.site",
    "vault-04.uwucdn.top":"uwu4.bigdreamsmalldih.site",
    "vault-05.uwucdn.top":"uwu5.bigdreamsmalldih.site",
    "vibeplayer.site":    "nanobyte.bigdreamsmalldih.site",
    "vault-06.uwucdn.top":"uwu6.bigdreamsmalldih.site",
    "vault-07.uwucdn.top":"uwu7.bigdreamsmalldih.site",
    "vault-08.uwucdn.top":"uwu8.bigdreamsmalldih.site",
    "vault-09.uwucdn.top":"uwu9.bigdreamsmalldih.site",
    "vault-10.uwucdn.top":"uwu10.bigdreamsmalldih.site",
    "vault-11.uwucdn.top":"uwu11.bigdreamsmalldih.site",
    "vault-12.uwucdn.top":"uwu12.bigdreamsmalldih.site",
    "vault-13.uwucdn.top":"uwu13.bigdreamsmalldih.site",
    "vault-14.uwucdn.top":"uwu14.bigdreamsmalldih.site",
    "vault-15.uwucdn.top":"uwu15.bigdreamsmalldih.site",
    "vault-16.uwucdn.top":"uwu16.bigdreamsmalldih.site",
    "vault-99.uwucdn.top":"uwu17.bigdreamsmalldih.site",
}

MAL_TITLES = {
    20:"Naruto", 1735:"Naruto Shippuden", 21:"One Piece",
    269:"Bleach", 813:"Dragon Ball Z", 16498:"Attack on Titan",
    38000:"Demon Slayer", 40748:"Jujutsu Kaisen", 11061:"Hunter x Hunter",
    5114:"Fullmetal Alchemist Brotherhood", 31964:"My Hero Academia",
    34572:"Black Clover", 1:"Cowboy Bebop", 22319:"Tokyo Ghoul",
    9253:"Steins Gate", 199:"Bleach", 6:"Trigun",
}

sess = requests.Session()
sess.headers.update({"user-agent": UA, "accept-language": "en-US,en;q=0.9"})

# ── Helpers ───────────────────────────────────────────────────────────────────
def b64dec(s):
    s = s.strip()
    pad = 4 - len(s) % 4
    if pad != 4: s += "=" * pad
    return base64.b64decode(s).decode("utf-8", errors="replace")

def parse_json_resp(r):
    try: return r.json()
    except Exception: pass
    try: return json.loads(b64dec(r.text.strip()))
    except Exception: return {}

def remap_cdn(url):
    for orig, mapped in CDN_HOST_MAP.items():
        if orig in url: url = url.replace(orig, mapped)
    return url

def _get(url, **kw):
    r = sess.get(url, timeout=15, **kw)
    r.raise_for_status()
    return r

# ── Core logic ────────────────────────────────────────────────────────────────
def get_mapper_tokens(mal_id, ep_num):
    ts  = int(time.time())
    url = f"{MAPPER_BASE}/{mal_id}/{ep_num}/{ts}"
    r   = _get(url, headers={"accept":"application/json","origin":BASE,
                              "referer":f"{BASE}/","sec-fetch-site":"cross-site",
                              "sec-fetch-mode":"cors","sec-fetch-dest":"empty"})
    data = r.json()
    tokens, downloads = {}, {}
    for key, val in data.items():
        if key == "status" or not isinstance(val, dict): continue
        for stype in ("sub","dub"):
            if stype not in val or not isinstance(val[stype], dict): continue
            token = val[stype].get("url","")
            if token and len(token) > 10 and stype not in tokens:
                tokens[stype] = token
            dl = val[stype].get("download",{})
            if dl: downloads.update(dl)
    if not tokens:
        raise ValueError(f"No tokens for MAL {mal_id} ep {ep_num}")
    return tokens, downloads

def decrypt_token(token):
    url  = f"{BASE}/ajax/server?get={token}"
    r    = _get(url, headers={"accept":"application/json, text/javascript, */*; q=0.01",
                               "x-requested-with":"XMLHttpRequest","referer":f"{BASE}/",
                               "sec-fetch-site":"same-origin","sec-fetch-mode":"cors",
                               "sec-fetch-dest":"empty"})
    data = parse_json_resp(r)
    if not isinstance(data, dict) or data.get("status") != 200:
        raise ValueError(f"Decrypt failed: {r.text[:100]}")
    result = data["result"]
    return result.get("url",""), result.get("skip_data",{})

def decode_mewcdn(player_url):
    if "mewcdn.online" not in player_url or "#" not in player_url:
        return player_url, player_url
    b64_frag    = player_url.split("#")[1].strip()
    m3u8_raw    = b64dec(b64_frag)
    m3u8_direct = remap_cdn(m3u8_raw)
    mewcdn_url  = f"https://mewcdn.online/player/plyr.php#{b64_frag}#"
    return m3u8_direct, mewcdn_url

def get_realid(mal_id, ep_num):
    """Get realid via anikoto server list."""
    # Search anikoto for this anime
    search_q = MAL_TITLES.get(mal_id)
    if not search_q:
        # Try Jikan
        try:
            jr = sess.get(f"https://api.jikan.moe/v4/anime/{mal_id}", timeout=5)
            if jr.status_code == 200:
                d = jr.json().get("data",{})
                search_q = d.get("title_english") or d.get("title","")
        except Exception:
            pass
    if not search_q:
        raise ValueError(f"Cannot determine title for MAL {mal_id}")

    # Search anikoto filter page
    r = sess.get(f"{BASE}/filter", params={"keyword": search_q},
                 headers={"accept":"text/html","referer":f"{BASE}/"}, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    container = soup.select_one("div.ani.items")
    if not container:
        raise ValueError("No search results on anikoto")

    for item in container.select("div.item"):
        a = item.select_one("a[href*='/watch/']")
        if not a: continue
        href = a.get("href","")
        if not href: continue
        watch_url = href if href.startswith("http") else BASE + href
        watch_url = watch_url.rstrip("/")
        if "/ep-" not in watch_url:
            watch_url += "/ep-1"

        try:
            wr   = _get(watch_url, headers={"referer":f"{BASE}/"})
            wsoup = BeautifulSoup(wr.text, "html.parser")
            wm   = wsoup.select_one("#watch-main")
            if not wm: continue
            anikoto_id = wm["data-id"]

            # Get episode list
            er   = _get(f"{BASE}/ajax/episode/list/{anikoto_id}",
                        headers={"accept":"application/json","x-requested-with":"XMLHttpRequest",
                                 "referer":f"{BASE}/"})
            edata = parse_json_resp(er)
            ehtml = edata.get("result","") or ""
            esoup = BeautifulSoup(ehtml, "html.parser")

            # Check MAL ID match
            ep1 = esoup.select_one("a[data-num='1']") or esoup.select_one("a[data-slug]")
            if not ep1: continue
            ep_mal = ep1.get("data-mal")
            if ep_mal and int(ep_mal) != mal_id: continue

            # Find the requested episode
            ep_a = esoup.select_one(f"a[data-num='{ep_num}']")
            if not ep_a:
                ep_a = esoup.select_one("a[data-num='1']")
            if not ep_a: continue

            vrf = ep_a.get("data-ids","")
            if not vrf: continue

            # Get server list
            sr   = _get(f"{BASE}/ajax/server/list?servers={vrf}",
                        headers={"accept":"application/json","x-requested-with":"XMLHttpRequest",
                                 "referer":f"{BASE}/"})
            sdata = parse_json_resp(sr)
            shtml = sdata.get("result","") or ""
            ssoup = BeautifulSoup(shtml, "html.parser")

            # Get Vidstream link-id
            priority = ["e54","a41","e28","e30"]
            for sv_id in priority:
                li = ssoup.select_one(f'div[data-type="sub"] li[data-sv-id="{sv_id}"]')
                if li and li.get("data-link-id"):
                    player_url, _ = decrypt_token(li["data-link-id"])
                    m = re.search(r'/stream/s-\d+/(\d+)/', player_url)
                    if m:
                        return m.group(1)
        except Exception:
            continue

    raise ValueError(f"Could not find realid for MAL {mal_id} ep {ep_num}")

# ── API endpoint ──────────────────────────────────────────────────────────────
@app.route("/api/stream")
def api_stream():
    try:
        mal_id  = int(request.args.get("mal","0"))
        ep_num  = int(request.args.get("ep","0"))
        if mal_id <= 0 or ep_num <= 0:
            return jsonify({"error":"mal and ep are required"}), 400

        # 1. Get Kiwi streams from mapper
        tokens, downloads = get_mapper_tokens(mal_id, ep_num)

        kiwi = {}
        for stype, token in tokens.items():
            try:
                player_url, skip_data = decrypt_token(token)
                m3u8_direct, mewcdn_url = decode_mewcdn(player_url)
                kiwi[stype] = {
                    "m3u8":       m3u8_direct,
                    "player_url": mewcdn_url,
                    "skip_data":  skip_data,
                }
            except Exception as e:
                kiwi[stype] = {"error": str(e)}

        # 2. Get realid
        realid = None
        try:
            realid = get_realid(mal_id, ep_num)
        except Exception as e:
            pass  # realid optional

        return jsonify({
            "mal_id":    mal_id,
            "episode":   ep_num,
            "realid":    realid,
            "kiwi":      kiwi,
            "downloads": downloads,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Serve frontend ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
