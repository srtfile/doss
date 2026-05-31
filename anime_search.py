#!/usr/bin/env python3
"""
anime_search.py — Get Megaplay/Vidwish stream URLs.
Usage:
    python anime_search.py                          # interactive
    python anime_search.py --mal 1735 --ep 1        # MAL direct
    python anime_search.py --query "naruto" --ep 1  # search
    python anime_search.py --mal 1735 --ep 1 --json # JSON output
"""
import argparse, base64, json, re, sys, time, traceback
import requests
from bs4 import BeautifulSoup

BASE        = "https://anikototv.to"
MAPPER_BASE = "https://mapper.nekostream.site/api/mal"
MEGAPLAY    = "https://megaplay.buzz"
VIDWISH     = "https://vidwish.live"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Always log to stderr so stdout stays clean for --json mode
def log(*args, **kwargs):
    kwargs.pop('file', None)
    print(*args, file=sys.stderr, **kwargs)

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

sess = requests.Session()
sess.headers.update({"user-agent": UA, "accept-language": "en-US,en;q=0.9"})

# ── helpers ───────────────────────────────────────────────────────────────────
def b64dec(s):
    s = s.strip()
    pad = 4 - len(s) % 4
    if pad != 4: s += "=" * pad
    return base64.b64decode(s).decode("utf-8", errors="replace")

def parse_json_response(r):
    try: return r.json()
    except Exception: pass
    try: return json.loads(b64dec(r.text.strip()))
    except Exception: return {}

def remap_cdn(url):
    for orig, mapped in CDN_HOST_MAP.items():
        if orig in url: url = url.replace(orig, mapped)
    return url

def _get(url, **kw):
    r = sess.get(url, timeout=20, **kw)
    r.raise_for_status()
    return r

# ── search ────────────────────────────────────────────────────────────────────
def search_anime(query):
    results = _search_filter_page(query)
    if not results:
        results = _search_ajax(query)
    return results

def _search_filter_page(query):
    r = sess.get(f"{BASE}/filter", params={"keyword": query},
                 headers={"accept": "text/html", "referer": f"{BASE}/"}, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    container = soup.select_one("div.ani.items")
    if not container: return []
    results, seen = [], set()
    for item in container.select("div.item"):
        a = item.select_one("a[href*='/watch/']")
        if not a: continue
        href = a.get("href", "")
        if href in seen: continue
        seen.add(href)
        name_el = item.select_one(".name, .d-title")
        thumb   = item.select_one("img")
        type_el = item.select_one(".right, .fd-infor .fdi-type")
        sub_el  = item.select_one(".ep-status.sub span")
        dub_el  = item.select_one(".ep-status.dub span")
        eps_el  = item.select_one(".ep-status.total span")
        name = name_el.get_text(strip=True) if name_el else (thumb.get("alt","?") if thumb else "?")
        meta_parts = []
        if type_el: meta_parts.append(type_el.get_text(strip=True))
        if eps_el:  meta_parts.append(f"{eps_el.get_text(strip=True)} eps")
        if sub_el:  meta_parts.append("SUB")
        if dub_el:  meta_parts.append("DUB")
        slug = href.rstrip("/").split("/watch/")[-1].split("/")[0]
        results.append({"title": name,
                        "url": href if href.startswith("http") else BASE+href,
                        "slug": slug,
                        "thumbnail": thumb["src"] if thumb and thumb.get("src") else "",
                        "meta": " | ".join(meta_parts)})
    return results

def _search_ajax(query):
    r = sess.get(f"{BASE}/ajax/anime/search", params={"keyword": query},
                 headers={"accept":"application/json","x-requested-with":"XMLHttpRequest",
                          "referer":f"{BASE}/"}, timeout=20)
    r.raise_for_status()
    data = parse_json_response(r)
    html = data.get("result",{}).get("html","") or data.get("result","")
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.select("a.item"):
        href    = item.get("href","")
        name_el = item.select_one(".name,.d-title")
        meta_el = item.select_one(".meta")
        thumb   = item.select_one("img")
        slug    = href.rstrip("/").split("/watch/")[-1].split("/")[0] if href else ""
        results.append({"title": name_el.get_text(strip=True) if name_el else "?",
                        "url": href if href.startswith("http") else BASE+href,
                        "slug": slug,
                        "thumbnail": thumb["src"] if thumb and thumb.get("src") else "",
                        "meta": meta_el.get_text(" ",strip=True) if meta_el else ""})
    return results

def pick_anime(results, query):
    if not results: raise ValueError(f"No results for '{query}'")
    print(f"\n  Found {len(results)} result(s) for '{query}':\n")
    for i, r in enumerate(results, 1):
        print(f"  [{i:2}] {r['title']}")
        log(f"       {r['meta']}  →  {r['url']}")
    print()
    while True:
        try:
            n = int(input("  Pick a number (or 0 to cancel): ").strip())
            if n == 0: sys.exit(0)
            if 1 <= n <= len(results): return results[n-1]
        except (ValueError, KeyboardInterrupt): pass
        print("  Invalid choice.")

def pick_episode(episodes, title):
    if not episodes:
        while True:
            try:
                n = int(input("  Enter episode number: ").strip())
                if n >= 1: return n
            except (ValueError, KeyboardInterrupt): pass
    nums  = sorted(e["num"] for e in episodes if e["num"] is not None)
    total = len(nums)
    ep_min, ep_max = nums[0], nums[-1]
    has_dub = any(e.get("has_dub") for e in episodes)
    print(f"\n  {title}")
    log(f"  Episodes: {total}  (ep {ep_min}–{ep_max}){' | DUB available' if has_dub else ' | SUB only'}")
    if total <= 20:
        print(f"  Available: {', '.join(str(n) for n in nums)}")
    else:
        print(f"  Available: {', '.join(str(n) for n in nums[:5])} ... {', '.join(str(n) for n in nums[-5:])}")
    while True:
        try:
            n = int(input(f"\n  Enter episode number (1–{ep_max}): ").strip())
            if n in nums: return n
            if 1 <= n <= ep_max + 50:
                print(f"  [warn] ep {n} not in list, will try anyway.")
                return n
        except (ValueError, KeyboardInterrupt): pass
        print(f"  Invalid. Enter 1–{ep_max}.")

# ── watch page ────────────────────────────────────────────────────────────────
def get_watch_page_info(anime_url):
    base_url  = anime_url.rstrip("/")
    watch_url = base_url if "/ep-" in base_url else base_url + "/ep-1"
    log(f"\n[2] watch   GET {watch_url}")
    r    = _get(watch_url, headers={"referer": f"{BASE}/"})
    soup = BeautifulSoup(r.text, "html.parser")
    wm   = soup.select_one("#watch-main")
    anikoto_id = wm["data-id"] if wm else None
    title_tag  = soup.select_one("h1.title")
    title      = title_tag.get_text(strip=True) if title_tag else "Unknown"
    episodes, mal_id, timestamp = [], None, None
    if anikoto_id:
        ep_list   = _get_episode_list(anikoto_id)
        episodes  = ep_list["episodes"]
        mal_id    = ep_list["mal_id"]
        timestamp = ep_list["timestamp"]
    return {"title": title, "anikoto_id": anikoto_id, "mal_id": mal_id,
            "timestamp": timestamp, "episodes": episodes, "watch_url": watch_url}

def _get_episode_list(anikoto_id):
    url = f"{BASE}/ajax/episode/list/{anikoto_id}"
    log(f"    ep-list GET {url}")
    r    = _get(url, headers={"accept":"application/json","x-requested-with":"XMLHttpRequest","referer":f"{BASE}/"})
    data = parse_json_response(r)
    html = data.get("result","") or data.get("html","")
    soup = BeautifulSoup(html, "html.parser")
    episodes, mal_id, timestamp = [], None, None
    for a in soup.select("ul.ep-range li > a, a[data-slug]"):
        slug  = a.get("data-slug") or a.get("href","").rstrip("/").split("/")[-1]
        mal   = a.get("data-mal")
        ts    = a.get("data-timestamp")
        ep_ns = a.get("data-num") or a.get("data-ep-name") or a.get_text(strip=True)
        ep_id = a.get("data-id")
        vrf   = a.get("data-ids","")
        try:    ep_num = int(float(ep_ns))
        except: ep_num = None
        if mal and not mal_id:    mal_id    = int(mal)
        if ts  and not timestamp: timestamp = int(ts)
        episodes.append({"num": ep_num,
                         "slug": f"ep-{ep_num}" if slug and slug.isdigit() else slug,
                         "mal": int(mal) if mal else None,
                         "timestamp": int(ts) if ts else None,
                         "ep_id": ep_id, "vrf": vrf,
                         "has_sub": a.get("data-sub")=="1",
                         "has_dub": a.get("data-dub")=="1"})
    return {"episodes": episodes, "mal_id": mal_id, "timestamp": timestamp}

# ── mapper + decrypt + m3u8 ───────────────────────────────────────────────────
def get_mapper_tokens(mal_id, ep_num, timestamp=None):
    ts  = timestamp or int(time.time())
    url = f"{MAPPER_BASE}/{mal_id}/{ep_num}/{ts}"
    log(f"[3] mapper  GET {url}")
    r    = _get(url, headers={"accept":"application/json","origin":BASE,"referer":f"{BASE}/",
                               "sec-fetch-site":"cross-site","sec-fetch-mode":"cors","sec-fetch-dest":"empty"})
    data = r.json()
    log(f"    cache={data.get('status',{}).get('serves_from','?')!r}")
    tokens, downloads = {}, {}
    for key, val in data.items():
        if key == "status" or not isinstance(val, dict): continue
        for stype in ("sub","dub"):
            if stype not in val or not isinstance(val[stype], dict): continue
            token = val[stype].get("url","")
            if token and len(token) > 10 and stype not in tokens:
                tokens[stype] = token
                log(f"    [{stype}] token found  (server={key!r})")
            dl = val[stype].get("download",{})
            if dl: downloads.update(dl)
    if not tokens:
        raise ValueError(f"No stream tokens for MAL {mal_id} ep {ep_num}.")
    return {"tokens": tokens, "downloads": downloads}

def decrypt_token(token, stype):
    url = f"{BASE}/ajax/server?get={token}"
    log(f"[4] decrypt GET [{stype.upper()}] {url[:90]}...")
    r    = _get(url, headers={"accept":"application/json, text/javascript, */*; q=0.01",
                               "x-requested-with":"XMLHttpRequest","referer":f"{BASE}/",
                               "sec-fetch-site":"same-origin","sec-fetch-mode":"cors","sec-fetch-dest":"empty"})
    data = parse_json_response(r)
    if not isinstance(data, dict) or data.get("status") != 200:
        raise ValueError(f"Decrypt failed [{stype}]: {r.text[:200]}")
    result     = data["result"]
    player_url = result.get("url","")
    skip_data  = result.get("skip_data",{})
    log(f"    player_url: {player_url[:100]}")
    return player_url, skip_data

def decode_mewcdn_url(player_url, stype):
    if "mewcdn.online" not in player_url or "#" not in player_url:
        return {"mewcdn_url": player_url, "m3u8_original": player_url, "m3u8_direct": player_url}
    b64_frag    = player_url.split("#")[1].strip()
    m3u8_raw    = b64dec(b64_frag)
    m3u8_direct = remap_cdn(m3u8_raw)
    mewcdn_url  = f"https://mewcdn.online/player/plyr.php#{b64_frag}#"
    log(f"[5] m3u8    [{stype.upper()}] {m3u8_raw}")
    if m3u8_direct != m3u8_raw: log(f"            remapped → {m3u8_direct}")
    return {"mewcdn_url": mewcdn_url, "m3u8_original": m3u8_raw, "m3u8_direct": m3u8_direct}

# ── server list + realid ──────────────────────────────────────────────────────
def get_megaplay_vidwish_urls(anikoto_id, ep_slug, ep_num, anime_slug, ep_vrf="", ep_id=""):
    link_ids = {}
    if ep_vrf:
        link_ids = _get_server_link_ids(f"{BASE}/ajax/server/list", ep_vrf, anikoto_id)
    if not link_ids:
        watch_ep_url = f"{BASE}/watch/{anime_slug}/{ep_slug}"
        log(f"[6] watch-ep GET {watch_ep_url}")
        r   = _get(watch_ep_url, headers={"referer": f"{BASE}/"})
        vrf = _extract_vrf(r.text, anikoto_id)
        if vrf: link_ids = _get_server_link_ids(f"{BASE}/ajax/server/list", vrf, anikoto_id)
    realid = None
    for stype in ("sub","dub"):
        if stype in link_ids and realid is None:
            try:
                player_url, _ = decrypt_token(link_ids[stype], stype)
                realid = _extract_realid_from_embed(player_url, stype)
                if realid:
                    log(f"    realid={realid!r} (from {stype} embed)")
                    break
            except Exception as e:
                log(f"    [warn] decrypt {stype}: {e}")
    if not realid:
        raise ValueError("Could not find data-realid.")
    return _build_stream_urls(realid)

def _extract_vrf(page_html, anikoto_id):
    m = re.search(r'ajax/server/list\?servers=([A-Za-z0-9+/=]+)', page_html)
    if m: return m.group(1)
    m = re.search(r'data-vrf=["\']([^"\']+)["\']', page_html)
    if m: return m.group(1)
    return ""

def _get_server_link_ids(url, vrf, anikoto_id):
    full_url = f"{url}?servers={vrf}"
    log(f"    srvlist GET {full_url[:90]}...")
    try:
        r    = _get(full_url, headers={"accept":"application/json","x-requested-with":"XMLHttpRequest","referer":f"{BASE}/"})
        data = parse_json_response(r)
        html = data.get("result","") or ""
        soup = BeautifulSoup(html, "html.parser")
        link_ids, priority = {}, ["e54","a41","e28","e30"]
        for stype in ("sub","dub"):
            container = soup.select_one(f'div[data-type="{stype}"]')
            if not container: continue
            for sv_id in priority:
                li = container.select_one(f'li[data-sv-id="{sv_id}"]')
                if li and li.get("data-link-id"):
                    link_ids[stype] = li["data-link-id"]
                    log(f"    [{stype}] sv-id={sv_id!r} link-id found")
                    break
        return link_ids
    except Exception as e:
        log(f"    [warn] server list: {e}")
        return {}

def _extract_realid_from_embed(player_url, stype):
    m = re.search(r'/stream/s-\d+/(\d+)/', player_url)
    if m: return m.group(1)
    if "mewcdn.online" in player_url:
        try:
            r    = _get(player_url, headers={"referer": f"{BASE}/"})
            soup = BeautifulSoup(r.text, "html.parser")
            for iframe in soup.select("iframe"):
                m = re.search(r'/stream/s-\d+/(\d+)/', iframe.get("src",""))
                if m: return m.group(1)
            m = re.search(r'/stream/s-\d+/(\d+)/', r.text)
            if m: return m.group(1)
        except Exception: pass
    if "vidwish.live" in player_url or "megaplay.buzz" in player_url:
        try:
            r    = _get(player_url, headers={"referer": f"{BASE}/"})
            soup = BeautifulSoup(r.text, "html.parser")
            el   = soup.select_one("[data-realid]")
            if el: return el["data-realid"]
        except Exception: pass
    return None

def _build_stream_urls(realid):
    return {"realid": realid,
            "megaplay_sub": f"{MEGAPLAY}/stream/s-2/{realid}/sub?autostart=true",
            "megaplay_dub": f"{MEGAPLAY}/stream/s-2/{realid}/dub?autostart=true",
            "vidwish_sub":  f"{VIDWISH}/stream/s-2/{realid}/sub?autostart=true",
            "vidwish_dub":  f"{VIDWISH}/stream/s-2/{realid}/dub?autostart=true"}

# ── MAL direct mode ───────────────────────────────────────────────────────────
def run_by_mal(mal_id, ep_num=None, json_out=False):
    W = 68
    if ep_num is None:
        while True:
            try:
                ep_num = int(input(f"  Episode number for MAL {mal_id}: ").strip())
                if ep_num >= 1: break
            except (ValueError, KeyboardInterrupt): pass
            log("  Invalid.")
    else:
        log(f"  MAL ID={mal_id}  EP={ep_num}")

    log(f"\n  MAL ID  : {mal_id}\n  Episode : {ep_num}")
    mapper_data    = get_mapper_tokens(mal_id, ep_num)
    realid         = None
    stream_urls    = {}
    mewcdn_streams = {}

    for stype, token in mapper_data["tokens"].items():
        try:
            player_url, skip_data = decrypt_token(token, stype)
            if realid is None:
                realid = _extract_realid_from_embed(player_url, stype)
                if realid:
                    log(f"    realid={realid!r} (from {stype} player URL)")
                    stream_urls = _build_stream_urls(realid)
            decoded = decode_mewcdn_url(player_url, stype)
            decoded["skip_data"] = skip_data
            mewcdn_streams[stype] = decoded
        except Exception as e:
            log(f"  [warn] {stype}: {e}")

    if not realid:
        log(f"\n  [i] mapper gave mewcdn URL — looking up realid via anikoto...")
        try:
            realid, stream_urls = _get_realid_via_anikoto_mal(mal_id, ep_num)
        except Exception as e:
            log(f"  [warn] anikoto fallback: {e}")

    if not realid:
        log("  [!] Could not get realid — Vidstream/VidCloud not available.")

    result = {"anime": f"MAL:{mal_id}", "mal_id": mal_id, "episode": ep_num,
              "anikoto_id": None, "mewcdn_streams": mewcdn_streams,
              "stream_urls": stream_urls, "downloads": mapper_data.get("downloads",{})}
    if json_out: log(json.dumps(result, indent=2, ensure_ascii=False))
    else:        _print_result(result, W)
    return result

def _get_realid_via_anikoto_mal(mal_id, ep_num):
    log(f"    Searching anikoto for MAL {mal_id}...")
    mal_r = sess.get(f"https://api.jikan.moe/v4/anime/{mal_id}", timeout=10)
    if mal_r.status_code != 200:
        raise ValueError(f"Jikan API {mal_r.status_code}")
    mal_data   = mal_r.json().get("data",{})
    search_q   = mal_data.get("title_english") or mal_data.get("title","")
    log(f"    Title: {search_q!r}")
    results = _search_filter_page(search_q) or _search_ajax(search_q)
    for anime in results[:6]:
        try:
            info = get_watch_page_info(anime["url"])
            if info["mal_id"] != mal_id: continue
            log(f"    Matched: {anime['title']!r}  anikoto_id={info['anikoto_id']}")
            ep = next((e for e in info["episodes"] if e["num"] == ep_num), None)
            if ep is None:
                ep = {"num": ep_num, "slug": f"ep-{ep_num}", "mal": mal_id,
                      "timestamp": info["timestamp"], "ep_id": None, "vrf": ""}
            anime_slug = anime["url"].rstrip("/").split("/watch/")[-1].split("/")[0]
            su = get_megaplay_vidwish_urls(
                anikoto_id=info["anikoto_id"], ep_slug=ep["slug"],
                ep_num=ep_num, anime_slug=anime_slug,
                ep_vrf=ep.get("vrf",""), ep_id=ep.get("ep_id",""))
            return su["realid"], su
        except Exception as e:
            log(f"    [skip] {anime.get('title','?')}: {e}")
    raise ValueError(f"Could not match MAL {mal_id} on anikoto")

# ── search mode orchestrator ──────────────────────────────────────────────────
def run(query, ep_num=None, json_out=False):
    W = 68
    log(f"\n[1] search  '{query}'")
    results    = search_anime(query)
    anime      = pick_anime(results, query)
    log(f"\n  Selected: {anime['title']}\n  URL:      {anime['url']}")
    anime_slug = anime["url"].rstrip("/").split("/watch/")[-1].split("/")[0]
    info       = get_watch_page_info(anime["url"])
    log(f"\n  Anikoto ID : {info['anikoto_id']}")
    log(f"  MAL ID     : {info['mal_id']}")
    log(f"  Episodes   : {len(info['episodes'])} found")

    if ep_num is None:
        ep_num = pick_episode(info["episodes"], anime["title"])
    else:
        log(f"  Episode    : {ep_num} (from --ep flag)")

    ep = next((e for e in info["episodes"] if e["num"] == ep_num), None)
    if ep is None:
        ep = {"num": ep_num, "slug": f"ep-{ep_num}", "mal": info["mal_id"],
              "timestamp": info["timestamp"], "ep_id": None, "vrf": ""}
    else:
        log(f"  Episode {ep_num}: slug={ep['slug']!r}  ep_id={ep['ep_id']!r}")

    mal_id    = ep.get("mal") or info["mal_id"]
    timestamp = ep.get("timestamp") or info["timestamp"]
    if not mal_id: raise ValueError("Could not determine MAL ID.")

    mapper_data    = get_mapper_tokens(mal_id, ep_num, timestamp)
    mewcdn_streams = {}
    for stype, token in mapper_data["tokens"].items():
        try:
            player_url, skip_data = decrypt_token(token, stype)
            decoded = decode_mewcdn_url(player_url, stype)
            decoded["skip_data"] = skip_data
            mewcdn_streams[stype] = decoded
        except Exception as e:
            log(f"  [warn] mewcdn {stype}: {e}")

    stream_urls = {}
    try:
        stream_urls = get_megaplay_vidwish_urls(
            anikoto_id=info["anikoto_id"], ep_slug=ep["slug"],
            ep_num=ep_num, anime_slug=anime_slug,
            ep_vrf=ep.get("vrf",""), ep_id=ep.get("ep_id",""))
    except Exception as e:
        log(f"\n  [warn] megaplay/vidwish: {e}")

    result = {"anime": anime["title"], "mal_id": mal_id, "episode": ep_num,
              "anikoto_id": info["anikoto_id"], "mewcdn_streams": mewcdn_streams,
              "stream_urls": stream_urls, "downloads": mapper_data.get("downloads",{})}
    if json_out: log(json.dumps(result, indent=2, ensure_ascii=False))
    else:        _print_result(result, W)
    return result

# ── print result ──────────────────────────────────────────────────────────────
def _print_result(r, W=68):
    sep = "=" * W
    print(f"\n{sep}\n  RESULTS\n{sep}")
    print(f"  Anime   : {r['anime']}")
    print(f"  MAL ID  : {r['mal_id']}")
    print(f"  Episode : {r['episode']}")
    su = r.get("stream_urls",{})
    if su.get("realid"):
        print(f"\n  ── Megaplay / Vidwish  (realid={su['realid']}) {'─'*(W-42)}")
        print(f"  Megaplay SUB : {su.get('megaplay_sub','N/A')}")
        print(f"  Megaplay DUB : {su.get('megaplay_dub','N/A')}")
        print(f"  Vidwish  SUB : {su.get('vidwish_sub','N/A')}")
        print(f"  Vidwish  DUB : {su.get('vidwish_dub','N/A')}")
    else:
        print(f"\n  [!] Megaplay/Vidwish URLs not available for this episode.")
    for stype, s in r.get("mewcdn_streams",{}).items():
        print(f"\n  ── mewcdn {stype.upper()} {'─'*max(1,W-12-len(stype))}")
        print(f"  Player  : {s.get('mewcdn_url','N/A')}")
        print(f"  m3u8    : {s.get('m3u8_direct','N/A')}")
        skip  = s.get("skip_data",{})
        intro = skip.get("intro",[0,0])
        outro = skip.get("outro",[0,0])
        if any(intro): print(f"  Skip intro : {intro[0]}s → {intro[1]}s")
        if any(outro): print(f"  Skip outro : {outro[0]}s → {outro[1]}s")
    dl = r.get("downloads",{})
    if dl:
        print(f"\n  ── Downloads {'─'*(W-14)}")
        for quality, url in dl.items():
            print(f"  [{quality}] {url}")
    print(sep)

# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--query","-q", type=str, default=None)
    parser.add_argument("--mal",  "-m", type=int, default=None,
                        help="MyAnimeList ID — skip search (e.g. --mal 1735)")
    parser.add_argument("--ep",   "-e", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        if args.mal:
            run_by_mal(mal_id=args.mal, ep_num=args.ep, json_out=args.json)
            return
        if args.query:
            run(query=args.query, ep_num=args.ep, json_out=args.json)
            return

        # interactive menu
        print("\n  ┌─────────────────────────────────────┐")
        print("  │   Anime Stream Finder               │")
        print("  └─────────────────────────────────────┘")
        print("\n  [1] Search by anime name")
        print("  [2] Enter MAL ID directly\n")
        while True:
            try:
                mode = input("  Choose (1 or 2): ").strip()
            except KeyboardInterrupt:
                print("\nAborted."); sys.exit(0)
            if mode in ("1","2"): break
            print("  Enter 1 or 2.")

        if mode == "2":
            while True:
                try:
                    mal_id = int(input("\n  MAL ID: ").strip())
                    if mal_id > 0: break
                except (ValueError, KeyboardInterrupt): pass
                print("  Invalid.")
            run_by_mal(mal_id=mal_id, ep_num=args.ep, json_out=args.json)
        else:
            try:
                query = input("\n  Search anime: ").strip()
            except KeyboardInterrupt:
                print("\nAborted."); sys.exit(0)
            if not query:
                print("No query."); sys.exit(1)
            run(query=query, ep_num=args.ep, json_out=args.json)

    except KeyboardInterrupt:
        print("\nAborted."); sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        traceback.print_exc(); sys.exit(1)

if __name__ == "__main__":
    main()
