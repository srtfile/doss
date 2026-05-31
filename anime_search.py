#!/usr/bin/env python3
"""
anime_search.py
===============
Search any anime by name and get Megaplay / Vidwish stream links.

Flow:
  1. Search anikototv.to  → pick anime
  2. Load watch page       → get anikoto anime_id + episode list (MAL ID, timestamp)
  3. mapper.nekostream.site → encrypted stream tokens
  4. anikototv.to/ajax/server → decrypt token → mewcdn player URL
  5. base64 decode fragment  → direct .m3u8
  6. Load vidwish/megaplay page → parse data-realid → build final URLs

Usage:
    python anime_search.py
    python anime_search.py --query "naruto shippuden" --ep 1
    python anime_search.py --query "one piece" --ep 100 --json
"""

import argparse
import base64
import json
import re
import sys
import time
import traceback

import requests
from bs4 import BeautifulSoup

# ── Constants ─────────────────────────────────────────────────────────────────
BASE        = "https://anikototv.to"
MAPPER_BASE = "https://mapper.nekostream.site/api/mal"
MEGAPLAY    = "https://megaplay.buzz"
VIDWISH     = "https://vidwish.live"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

CDN_HOST_MAP = {
    "vault-10.owocdn.top": "10.bigdreamsmalldih.site",
    "vault-11.owocdn.top": "11.bigdreamsmalldih.site",
    "vault-12.owocdn.top": "12.bigdreamsmalldih.site",
    "vault-13.owocdn.top": "13.bigdreamsmalldih.site",
    "vault-14.owocdn.top": "14.bigdreamsmalldih.site",
    "vault-15.owocdn.top": "15.bigdreamsmalldih.site",
    "vault-16.owocdn.top": "16.bigdreamsmalldih.site",
    "vault-99.owocdn.top": "99.bigdreamsmalldih.site",
    "vault-01.uwucdn.top": "uwu1.bigdreamsmalldih.site",
    "vault-02.uwucdn.top": "uwu2.bigdreamsmalldih.site",
    "vault-03.uwucdn.top": "uwu3.bigdreamsmalldih.site",
    "vault-04.uwucdn.top": "uwu4.bigdreamsmalldih.site",
    "vault-05.uwucdn.top": "uwu5.bigdreamsmalldih.site",
    "vibeplayer.site":     "nanobyte.bigdreamsmalldih.site",
    "vault-06.uwucdn.top": "uwu6.bigdreamsmalldih.site",
    "vault-07.uwucdn.top": "uwu7.bigdreamsmalldih.site",
    "vault-08.uwucdn.top": "uwu8.bigdreamsmalldih.site",
    "vault-09.uwucdn.top": "uwu9.bigdreamsmalldih.site",
    "vault-10.uwucdn.top": "uwu10.bigdreamsmalldih.site",
    "vault-11.uwucdn.top": "uwu11.bigdreamsmalldih.site",
    "vault-12.uwucdn.top": "uwu12.bigdreamsmalldih.site",
    "vault-13.uwucdn.top": "uwu13.bigdreamsmalldih.site",
    "vault-14.uwucdn.top": "uwu14.bigdreamsmalldih.site",
    "vault-15.uwucdn.top": "uwu15.bigdreamsmalldih.site",
    "vault-16.uwucdn.top": "uwu16.bigdreamsmalldih.site",
    "vault-99.uwucdn.top": "uwu17.bigdreamsmalldih.site",
}

# ── Session ───────────────────────────────────────────────────────────────────
sess = requests.Session()
sess.headers.update({
    "user-agent":      UA,
    "accept-language": "en-US,en;q=0.9",
})

# ── Helpers ───────────────────────────────────────────────────────────────────

def b64dec(s: str) -> str:
    s = s.strip()
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.b64decode(s).decode("utf-8", errors="replace")


def parse_json_response(r: requests.Response) -> dict:
    """Try plain JSON first, then base64-wrapped JSON."""
    try:
        return r.json()
    except Exception:
        pass
    try:
        return json.loads(b64dec(r.text.strip()))
    except Exception:
        return {}


def remap_cdn(url: str) -> str:
    for orig, mapped in CDN_HOST_MAP.items():
        if orig in url:
            url = url.replace(orig, mapped)
    return url


def _get(url, **kwargs) -> requests.Response:
    r = sess.get(url, timeout=20, **kwargs)
    r.raise_for_status()
    return r


# ── Step 1: Search ────────────────────────────────────────────────────────────

def search_anime(query: str) -> list[dict]:
    """
    Search using the filter page (GET /filter?keyword=...) which returns
    full results in div.ani.items, plus the ajax endpoint as a fallback.
    """
    results = _search_filter_page(query)
    if not results:
        results = _search_ajax(query)
    return results


def _search_filter_page(query: str) -> list[dict]:
    """
    GET https://anikototv.to/filter?keyword=<query>
    Results are in div.ani.items — up to 24+ items per page.
    """
    r = sess.get(
        f"{BASE}/filter",
        params={"keyword": query},
        headers={"accept": "text/html", "referer": f"{BASE}/"},
        timeout=20,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    seen = set()

    # Main results container: div.ani.items
    container = soup.select_one("div.ani.items")
    if not container:
        return []

    for item in container.select("div.item"):
        # Each item has an inner <a> with the watch link
        a = item.select_one("a[href*='/watch/']")
        if not a:
            continue
        href = a.get("href", "")
        if href in seen:
            continue
        seen.add(href)

        # Title: .name or .d-title inside the item
        name_el = item.select_one(".name, .d-title")
        # Meta: type, year, episodes
        type_el  = item.select_one(".right, .fd-infor .fdi-type")
        sub_el   = item.select_one(".ep-status.sub span")
        dub_el   = item.select_one(".ep-status.dub span")
        eps_el   = item.select_one(".ep-status.total span")
        thumb    = item.select_one("img")

        name = name_el.get_text(strip=True) if name_el else a.get("title", "?")
        if not name or name.isdigit():
            # fallback: use alt text from img
            name = thumb.get("alt", "?") if thumb else "?"

        meta_parts = []
        if type_el:
            meta_parts.append(type_el.get_text(strip=True))
        if eps_el:
            meta_parts.append(f"{eps_el.get_text(strip=True)} eps")
        if sub_el:
            meta_parts.append("SUB")
        if dub_el:
            meta_parts.append("DUB")

        slug = href.rstrip("/").split("/watch/")[-1].split("/")[0]

        results.append({
            "title":     name,
            "url":       href if href.startswith("http") else BASE + href,
            "slug":      slug,
            "thumbnail": thumb["src"] if thumb and thumb.get("src") else "",
            "meta":      " | ".join(meta_parts),
        })

    return results


def _search_ajax(query: str) -> list[dict]:
    """
    Fallback: GET https://anikototv.to/ajax/anime/search?keyword=<query>
    Returns up to 5 results.
    """
    r = sess.get(
        f"{BASE}/ajax/anime/search",
        params={"keyword": query},
        headers={
            "accept":           "application/json, text/javascript, */*; q=0.01",
            "x-requested-with": "XMLHttpRequest",
            "referer":          f"{BASE}/",
        },
        timeout=20,
    )
    r.raise_for_status()
    data = parse_json_response(r)
    html = data.get("result", {}).get("html", "") or data.get("result", "")
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.select("a.item"):
        href     = item.get("href", "")
        name_el  = item.select_one(".name, .d-title")
        meta_el  = item.select_one(".meta")
        thumb    = item.select_one("img")
        name     = name_el.get_text(strip=True) if name_el else "?"
        slug     = href.rstrip("/").split("/watch/")[-1].split("/")[0] if href else ""
        results.append({
            "title":     name,
            "url":       href if href.startswith("http") else BASE + href,
            "slug":      slug,
            "thumbnail": thumb["src"] if thumb and thumb.get("src") else "",
            "meta":      meta_el.get_text(" ", strip=True) if meta_el else "",
        })
    return results


def pick_anime(results: list[dict], query: str) -> dict:
    """Interactive picker — show numbered list, user picks one."""
    if not results:
        raise ValueError(f"No results found for '{query}'")

    print(f"\n  Found {len(results)} result(s) for '{query}':\n")
    for i, r in enumerate(results, 1):
        print(f"  [{i:2}] {r['title']}")
        print(f"       {r['meta']}  →  {r['url']}")
    print()

    while True:
        try:
            choice = input("  Pick a number (or 0 to cancel): ").strip()
            n = int(choice)
            if n == 0:
                sys.exit(0)
            if 1 <= n <= len(results):
                return results[n - 1]
        except (ValueError, KeyboardInterrupt):
            pass
        print("  Invalid choice, try again.")

def pick_episode(episodes: list[dict], anime_title: str) -> int:
    """
    Show episode range info and prompt the user to enter an episode number.
    """
    if not episodes:
        # No episode list — just ask for a number
        while True:
            try:
                val = input("  Enter episode number: ").strip()
                n = int(val)
                if n >= 1:
                    return n
            except (ValueError, KeyboardInterrupt):
                pass
            print("  Invalid, enter a positive integer.")

    # Build a compact range display
    nums = sorted(e["num"] for e in episodes if e["num"] is not None)
    total = len(nums)
    ep_min = nums[0] if nums else 1
    ep_max = nums[-1] if nums else total

    # Show sub/dub availability summary
    has_dub = any(e.get("has_dub") for e in episodes)
    dub_str = " | DUB available" if has_dub else " | SUB only"

    print(f"\n  {anime_title}")
    print(f"  Episodes: {total}  (ep {ep_min} – {ep_max}){dub_str}")

    # Show first few and last few episode numbers as reference
    if total <= 20:
        print(f"  Available: {', '.join(str(n) for n in nums)}")
    else:
        first5 = ', '.join(str(n) for n in nums[:5])
        last5  = ', '.join(str(n) for n in nums[-5:])
        print(f"  Available: {first5} ... {last5}")

    while True:
        try:
            val = input(f"\n  Enter episode number (1–{ep_max}): ").strip()
            n = int(val)
            if n in nums:
                return n
            # Allow out-of-list numbers with a warning
            if 1 <= n <= ep_max + 50:
                print(f"  [warn] ep {n} not in list, will try anyway.")
                return n
        except (ValueError, KeyboardInterrupt):
            pass
        print(f"  Invalid. Enter a number between 1 and {ep_max}.")




def get_watch_page_info(anime_url: str) -> dict:
    """
    Scrape the watch page to get:
      - anikoto_id  (data-id on #watch-main)
      - mal_id      (data-mal on episode <a> tags)
      - timestamp   (data-timestamp on episode <a> tags)
      - episodes    [{num, slug, mal, timestamp, ep_id}]
      - title
    """
    # Ensure we land on ep-1 so the episode list is populated
    base_url = anime_url.rstrip("/")
    if "/ep-" not in base_url:
        watch_url = base_url + "/ep-1"
    else:
        watch_url = base_url

    print(f"\n[2] watch   GET {watch_url}")
    r = _get(watch_url, headers={"referer": f"{BASE}/"})
    soup = BeautifulSoup(r.text, "html.parser")

    # anikoto internal anime ID
    watch_main = soup.select_one("#watch-main")
    anikoto_id = watch_main["data-id"] if watch_main else None

    # Title
    title_tag = soup.select_one("h1.title")
    title = title_tag.get_text(strip=True) if title_tag else "Unknown"

    # Episode list is loaded via AJAX — fetch it
    episodes = []
    mal_id    = None
    timestamp = None

    if anikoto_id:
        ep_list = _get_episode_list(anikoto_id)
        episodes  = ep_list["episodes"]
        mal_id    = ep_list["mal_id"]
        timestamp = ep_list["timestamp"]

    return {
        "title":      title,
        "anikoto_id": anikoto_id,
        "mal_id":     mal_id,
        "timestamp":  timestamp,
        "episodes":   episodes,
        "watch_url":  watch_url,
    }


def _get_episode_list(anikoto_id: str) -> dict:
    """
    GET /ajax/episode/list/<id>
    Parse episode <a> tags.
    Actual attributes: data-id, data-num, data-slug, data-mal,
                       data-timestamp, data-sub, data-dub, data-ids (VRF)
    """
    url = f"{BASE}/ajax/episode/list/{anikoto_id}"
    print(f"    ep-list GET {url}")
    r = _get(url, headers={
        "accept":           "application/json, text/javascript, */*; q=0.01",
        "x-requested-with": "XMLHttpRequest",
        "referer":          f"{BASE}/",
    })
    data = parse_json_response(r)
    html = data.get("result", "") or data.get("html", "")
    soup = BeautifulSoup(html, "html.parser")

    episodes  = []
    mal_id    = None
    timestamp = None

    for a in soup.select("ul.ep-range li > a, a[data-slug]"):
        slug      = a.get("data-slug") or a.get("href", "").rstrip("/").split("/")[-1]
        mal       = a.get("data-mal")
        ts        = a.get("data-timestamp")
        ep_num_s  = a.get("data-num") or a.get("data-ep-name") or a.get_text(strip=True)
        ep_id     = a.get("data-id")
        vrf       = a.get("data-ids", "")   # encrypted server VRF token

        try:
            ep_num = int(float(ep_num_s))
        except (TypeError, ValueError):
            ep_num = None

        if mal and not mal_id:
            mal_id = int(mal)
        if ts and not timestamp:
            timestamp = int(ts)

        episodes.append({
            "num":       ep_num,
            "slug":      f"ep-{ep_num}" if slug and slug.isdigit() else slug,
            "mal":       int(mal) if mal else None,
            "timestamp": int(ts) if ts else None,
            "ep_id":     ep_id,
            "vrf":       vrf,
            "has_sub":   a.get("data-sub") == "1",
            "has_dub":   a.get("data-dub") == "1",
        })

    return {"episodes": episodes, "mal_id": mal_id, "timestamp": timestamp}


# ── Step 3: mapper.nekostream.site → encrypted tokens ─────────────────────────

def get_mapper_tokens(mal_id: int, ep_num: int, timestamp: int = None) -> dict:
    """
    GET https://mapper.nekostream.site/api/mal/<mal_id>/<ep>/<timestamp>

    Returns {
      "sub": "<encrypted_token>",
      "dub": "<encrypted_token>",   # may be absent
      "download": {...}
    }
    """
    ts  = timestamp or int(time.time())
    url = f"{MAPPER_BASE}/{mal_id}/{ep_num}/{ts}"
    print(f"[3] mapper  GET {url}")

    r = _get(url, headers={
        "accept":         "application/json",
        "origin":         BASE,
        "referer":        f"{BASE}/",
        "sec-fetch-site": "cross-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    })
    data = r.json()

    cache = data.get("status", {}).get("serves_from", "?")
    print(f"    cache={cache!r}")

    tokens    = {}
    downloads = {}

    for key, val in data.items():
        if key == "status" or not isinstance(val, dict):
            continue
        for stype in ("sub", "dub"):
            if stype not in val or not isinstance(val[stype], dict):
                continue
            token = val[stype].get("url", "")
            if token and len(token) > 10 and stype not in tokens:
                tokens[stype] = token
                print(f"    [{stype}] token found  (server={key!r})")
            dl = val[stype].get("download", {})
            if dl:
                downloads.update(dl)

    if not tokens:
        raise ValueError(
            f"No stream tokens for MAL {mal_id} ep {ep_num}. "
            "The episode may not be available on this server yet."
        )

    return {"tokens": tokens, "downloads": downloads}


# ── Step 4: Decrypt token → mewcdn player URL ─────────────────────────────────

def decrypt_token(token: str, stype: str) -> tuple[str, dict]:
    """
    GET https://anikototv.to/ajax/server?get=<token>
    Returns (player_url, skip_data)
    """
    url = f"{BASE}/ajax/server?get={token}"
    print(f"[4] decrypt GET [{stype.upper()}] {url[:90]}...")

    r = _get(url, headers={
        "accept":           "application/json, text/javascript, */*; q=0.01",
        "x-requested-with": "XMLHttpRequest",
        "referer":          f"{BASE}/",
        "sec-fetch-site":   "same-origin",
        "sec-fetch-mode":   "cors",
        "sec-fetch-dest":   "empty",
    })
    data = parse_json_response(r)

    if not isinstance(data, dict) or data.get("status") != 200:
        raise ValueError(f"Decrypt failed [{stype}]: {r.text[:200]}")

    result     = data["result"]
    player_url = result.get("url", "")
    skip_data  = result.get("skip_data", {})
    print(f"    player_url: {player_url[:100]}")
    return player_url, skip_data


# ── Step 5: Decode mewcdn fragment → m3u8 ────────────────────────────────────

def decode_mewcdn_url(player_url: str, stype: str) -> dict:
    """
    mewcdn format: https://mewcdn.online/player/plyr.php#<b64_m3u8>#
    Decode the base64 fragment → real .m3u8 → apply CDN remap.
    """
    if "mewcdn.online" not in player_url or "#" not in player_url:
        return {
            "mewcdn_url":   player_url,
            "m3u8_original": player_url,
            "m3u8_direct":  player_url,
        }

    b64_frag    = player_url.split("#")[1].strip()
    m3u8_raw    = b64dec(b64_frag)
    m3u8_direct = remap_cdn(m3u8_raw)
    mewcdn_url  = f"https://mewcdn.online/player/plyr.php#{b64_frag}#"

    print(f"[5] m3u8    [{stype.upper()}] {m3u8_raw}")
    if m3u8_direct != m3u8_raw:
        print(f"            remapped → {m3u8_direct}")

    return {
        "mewcdn_url":    mewcdn_url,
        "m3u8_original": m3u8_raw,
        "m3u8_direct":   m3u8_direct,
    }


# ── Step 6: Get Megaplay / Vidwish realid and build final URLs ────────────────

def get_megaplay_vidwish_urls(
    anikoto_id: str,
    ep_slug: str,
    ep_num: int,
    anime_slug: str,
    ep_vrf: str = "",
    ep_id: str = "",
) -> dict:
    """
    Use the episode's data-ids VRF token to call /ajax/server/list,
    get the Vidstream/VidCloud link-id, decrypt it, load the embed page,
    and parse data-realid.
    """
    link_ids = {}

    # Strategy A: use data-ids VRF from episode list (fastest, no extra page load)
    if ep_vrf:
        link_ids = _get_server_link_ids(f"{BASE}/ajax/server/list", ep_vrf, anikoto_id)

    # Strategy B: load the watch page and extract VRF from HTML/JS
    if not link_ids:
        watch_ep_url = f"{BASE}/watch/{anime_slug}/{ep_slug}"
        print(f"[6] watch-ep GET {watch_ep_url}")
        r = _get(watch_ep_url, headers={"referer": f"{BASE}/"})
        vrf = _extract_vrf(r.text, anikoto_id)
        if vrf:
            link_ids = _get_server_link_ids(f"{BASE}/ajax/server/list", vrf, anikoto_id)

    # Strategy C: use /ajax/episode/servers/<ep_id>
    if not link_ids and ep_id:
        link_ids = _get_server_link_ids_by_ep_id(ep_id)

    realid = None
    for stype in ("sub", "dub"):
        if stype in link_ids and realid is None:
            try:
                player_url, _ = decrypt_token(link_ids[stype], stype)
                realid = _extract_realid_from_embed(player_url, stype)
                if realid:
                    print(f"    realid={realid!r} (from {stype} embed)")
                    break
            except Exception as e:
                print(f"    [warn] decrypt {stype}: {e}")

    if not realid:
        raise ValueError(
            "Could not find data-realid. "
            "The episode may not have a Vidstream/VidCloud server."
        )

    return _build_stream_urls(realid)


def _get_server_link_ids_by_ep_id(ep_id: str) -> dict:
    """
    GET /ajax/episode/servers/<ep_id>
    Alternative to server/list — uses the episode's own ID.
    """
    url = f"{BASE}/ajax/episode/servers/{ep_id}"
    print(f"    ep-srv  GET {url}")
    try:
        r = _get(url, headers={
            "accept":           "application/json, text/javascript, */*; q=0.01",
            "x-requested-with": "XMLHttpRequest",
            "referer":          f"{BASE}/",
        })
        data = parse_json_response(r)
        html = data.get("result", "") or ""
        soup = BeautifulSoup(html, "html.parser")

        link_ids = {}
        priority = ["e54", "a41", "e28", "e30"]

        for stype in ("sub", "dub"):
            container = soup.select_one(f'div[data-type="{stype}"]')
            if not container:
                continue
            for sv_id in priority:
                li = container.select_one(f'li[data-sv-id="{sv_id}"]')
                if li and li.get("data-link-id"):
                    link_ids[stype] = li["data-link-id"]
                    print(f"    [{stype}] sv-id={sv_id!r} link-id found (ep-srv)")
                    break

        return link_ids
    except Exception as e:
        print(f"    [warn] ep-srv: {e}")
        return {}
    """Extract the servers VRF token from the page source."""
    # Look for the ajax/server/list call with servers= param in inline JS
    m = re.search(r'ajax/server/list\?servers=([A-Za-z0-9+/=]+)', page_html)
    if m:
        return m.group(1)
    # Also check for data-vrf attribute
    m = re.search(r'data-vrf=["\']([^"\']+)["\']', page_html)
    if m:
        return m.group(1)
    return ""


def _get_server_link_ids(url: str, vrf: str, anikoto_id: str) -> dict:
    """
    GET /ajax/server/list?servers=<vrf>
    Parse the HTML for data-link-id values keyed by sub/dub type.
    Prefer Vidstream-2 (sv-id=e54) or VidCloud-1 (sv-id=a41).
    """
    full_url = f"{url}?servers={vrf}"
    print(f"    srvlist GET {full_url[:90]}...")
    try:
        r = _get(full_url, headers={
            "accept":           "application/json, text/javascript, */*; q=0.01",
            "x-requested-with": "XMLHttpRequest",
            "referer":          f"{BASE}/",
        })
        data = parse_json_response(r)
        html = data.get("result", "") or ""
        soup = BeautifulSoup(html, "html.parser")

        link_ids = {}
        # Priority: e54 (Vidstream-2) > a41 (VidCloud-1)
        priority = ["e54", "a41", "e28", "e30"]

        for stype in ("sub", "dub"):
            container = soup.select_one(f'div[data-type="{stype}"]')
            if not container:
                continue
            for sv_id in priority:
                li = container.select_one(f'li[data-sv-id="{sv_id}"]')
                if li and li.get("data-link-id"):
                    link_ids[stype] = li["data-link-id"]
                    print(f"    [{stype}] sv-id={sv_id!r} link-id found")
                    break

        return link_ids
    except Exception as e:
        print(f"    [warn] server list: {e}")
        return {}


def _extract_realid_from_embed(player_url: str, stype: str):
    """
    The player_url from ajax/server is either:
      A) https://mewcdn.online/player/plyr.php#...  (mewcdn, no realid here)
      B) https://vidwish.live/stream/s-2/12352/sub  (direct embed URL)
      C) https://megaplay.buzz/stream/s-2/12352/dub

    For B/C we can parse the realid straight from the URL.
    For A we need to load the embed page and read data-realid from the HTML.
    """
    # Direct vidwish/megaplay URL in the player_url itself
    m = re.search(r'/stream/s-\d+/(\d+)/', player_url)
    if m:
        return m.group(1)

    # mewcdn wraps the real URL — load the page and look for an iframe or redirect
    if "mewcdn.online" in player_url:
        try:
            r = _get(player_url, headers={"referer": f"{BASE}/"})
            # Check for iframe pointing to vidwish/megaplay
            soup = BeautifulSoup(r.text, "html.parser")
            for iframe in soup.select("iframe"):
                src = iframe.get("src", "")
                m = re.search(r'/stream/s-\d+/(\d+)/', src)
                if m:
                    return m.group(1)
            # Check for JS redirect or window.location
            m = re.search(r'/stream/s-\d+/(\d+)/', r.text)
            if m:
                return m.group(1)
        except Exception:
            pass

    # If the player_url is a vidwish/megaplay embed page, load it
    if "vidwish.live" in player_url or "megaplay.buzz" in player_url:
        try:
            r = _get(player_url, headers={"referer": f"{BASE}/"})
            soup = BeautifulSoup(r.text, "html.parser")
            el = soup.select_one("[data-realid]")
            if el:
                return el["data-realid"]
        except Exception:
            pass

    return None


def _try_realid_from_ep_list(anikoto_id: str, ep_num: int):
    """
    Fallback: call /ajax/episode/servers/<ep_id> to get server list,
    then decrypt the Vidstream link-id and load the embed page.
    """
    # We need the ep_id for this episode — re-fetch the episode list
    try:
        ep_list = _get_episode_list(anikoto_id)
        ep = next(
            (e for e in ep_list["episodes"] if e["num"] == ep_num),
            None
        )
        if not ep or not ep.get("ep_id"):
            return None

        ep_id = ep["ep_id"]
        url   = f"{BASE}/ajax/episode/servers/{ep_id}"
        print(f"    ep-srv  GET {url}")
        r = _get(url, headers={
            "accept":           "application/json, text/javascript, */*; q=0.01",
            "x-requested-with": "XMLHttpRequest",
            "referer":          f"{BASE}/",
        })
        data = parse_json_response(r)
        html = data.get("result", "") or ""
        soup = BeautifulSoup(html, "html.parser")

        priority = ["e54", "a41", "e28", "e30"]
        for sv_id in priority:
            li = soup.select_one(f'li[data-sv-id="{sv_id}"]')
            if li and li.get("data-link-id"):
                link_id   = li["data-link-id"]
                # Walk up to find the parent div[data-type]
                parent    = li.parent
                while parent and not parent.get("data-type"):
                    parent = parent.parent
                ep_stype  = parent["data-type"] if parent and parent.get("data-type") else "sub"
                try:
                    player_url, _ = decrypt_token(link_id, ep_stype)
                    realid = _extract_realid_from_embed(player_url, ep_stype)
                    if realid:
                        return realid
                except Exception:
                    pass
    except Exception as e:
        print(f"    [warn] ep-list fallback: {e}")

    return None


def _build_stream_urls(realid: str) -> dict:
    """Build all megaplay + vidwish URLs from a realid."""
    return {
        "realid":      realid,
        "megaplay_sub": f"{MEGAPLAY}/stream/s-2/{realid}/sub?autostart=true",
        "megaplay_dub": f"{MEGAPLAY}/stream/s-2/{realid}/dub?autostart=true",
        "vidwish_sub":  f"{VIDWISH}/stream/s-2/{realid}/sub?autostart=true",
        "vidwish_dub":  f"{VIDWISH}/stream/s-2/{realid}/dub?autostart=true",
    }


# ── MAL ID direct mode ───────────────────────────────────────────────────────

def run_by_mal(mal_id: int, ep_num: int = None, json_out: bool = False):
    """
    Direct mode: MAL ID + episode → realid + all stream URLs.
    Skips search entirely. Uses mapper → decrypt → realid chain.
    Falls back to anikoto watch page if mapper doesn't give realid directly.
    """
    W = 68

    # ── Prompt for episode if not given
    if ep_num is None:
        while True:
            try:
                val = input(f"  Episode number for MAL {mal_id}: ").strip()
                ep_num = int(val)
                if ep_num >= 1:
                    break
            except (ValueError, KeyboardInterrupt):
                pass
            print("  Invalid, enter a positive integer.")
    else:
        print(f"  MAL ID={mal_id}  EP={ep_num}")

    print(f"\n  MAL ID  : {mal_id}")
    print(f"  Episode : {ep_num}")

    # ── Step 1: mapper → encrypted tokens
    mapper_data = get_mapper_tokens(mal_id, ep_num)

    realid      = None
    stream_urls = {}
    mewcdn_streams = {}

    # ── Step 2: decrypt each token → player URL → try to get realid
    for stype, token in mapper_data["tokens"].items():
        try:
            player_url, skip_data = decrypt_token(token, stype)

            # Try realid from player URL directly (megaplay/vidwish direct URL)
            if realid is None:
                realid = _extract_realid_from_embed(player_url, stype)
                if realid:
                    print(f"    realid={realid!r} (from {stype} player URL)")
                    stream_urls = _build_stream_urls(realid)

            # Decode mewcdn m3u8
            decoded = decode_mewcdn_url(player_url, stype)
            decoded["skip_data"] = skip_data
            mewcdn_streams[stype] = decoded

        except Exception as e:
            print(f"  [warn] {stype}: {e}")

    # ── Step 3: if still no realid, look up the anime on anikoto via MAL ID
    if not realid:
        print(f"\n  [i] mapper gave mewcdn URL — looking up realid via anikoto...")
        try:
            realid, stream_urls = _get_realid_via_anikoto_mal(mal_id, ep_num)
        except Exception as e:
            print(f"  [warn] anikoto fallback: {e}")

    if not realid:
        print("  [!] Could not get realid — Vidstream/VidCloud not available for this episode.")

    # ── Build result
    result = {
        "anime":          f"MAL:{mal_id}",
        "mal_id":         mal_id,
        "episode":        ep_num,
        "anikoto_id":     None,
        "mewcdn_streams": mewcdn_streams,
        "stream_urls":    stream_urls,
        "downloads":      mapper_data.get("downloads", {}),
    }

    if json_out:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_result(result, W)

    return result


def _get_realid_via_anikoto_mal(mal_id: int, ep_num: int):
    """
    Find the anime on anikoto by MAL ID, get the episode VRF,
    call server/list, decrypt the Vidstream link-id → realid.
    Returns (realid, stream_urls_dict) or raises.
    """
    print(f"    Searching anikoto for MAL {mal_id}...")

    # Use Jikan (MAL public API) to get the anime title for searching
    mal_r = sess.get(f"https://api.jikan.moe/v4/anime/{mal_id}", timeout=10)
    if mal_r.status_code != 200:
        raise ValueError(f"Jikan API {mal_r.status_code} for MAL {mal_id}")

    mal_data   = mal_r.json().get("data", {})
    title_en   = mal_data.get("title_english") or ""
    title_main = mal_data.get("title", "")
    search_q   = title_en or title_main
    print(f"    Title: {search_q!r}")

    # Search anikoto and find the entry whose episode list has data-mal == mal_id
    results = _search_filter_page(search_q) or _search_ajax(search_q)

    for anime in results[:6]:
        try:
            info = get_watch_page_info(anime["url"])
            if info["mal_id"] != mal_id:
                continue
            print(f"    Matched: {anime['title']!r}  anikoto_id={info['anikoto_id']}")
            ep = next((e for e in info["episodes"] if e["num"] == ep_num), None)
            if ep is None:
                ep = {"num": ep_num, "slug": f"ep-{ep_num}",
                      "mal": mal_id, "timestamp": info["timestamp"],
                      "ep_id": None, "vrf": ""}
            anime_slug = anime["url"].rstrip("/").split("/watch/")[-1].split("/")[0]
            su = get_megaplay_vidwish_urls(
                anikoto_id=info["anikoto_id"],
                ep_slug=ep["slug"],
                ep_num=ep_num,
                anime_slug=anime_slug,
                ep_vrf=ep.get("vrf", ""),
                ep_id=ep.get("ep_id", ""),
            )
            return su["realid"], su
        except Exception as e:
            print(f"    [skip] {anime.get('title','?')}: {e}")

    raise ValueError(f"Could not match MAL {mal_id} on anikoto")



def run(query: str, ep_num: int = None, json_out: bool = False):
    W = 68

    # ── 1. Search
    print(f"\n[1] search  '{query}'")
    results = search_anime(query)
    anime   = pick_anime(results, query)
    print(f"\n  Selected: {anime['title']}")
    print(f"  URL:      {anime['url']}")

    # Extract anime slug (last path segment before any /ep-N)
    anime_slug = anime["url"].rstrip("/").split("/watch/")[-1].split("/")[0]

    # ── 2. Watch page → IDs + episode list
    info = get_watch_page_info(anime["url"])
    print(f"\n  Anikoto ID : {info['anikoto_id']}")
    print(f"  MAL ID     : {info['mal_id']}")
    print(f"  Timestamp  : {info['timestamp']}")

    total_eps = len(info["episodes"])
    print(f"  Episodes   : {total_eps} found")

    # ── Episode selection (prompt if not given via CLI)
    if ep_num is None:
        ep_num = pick_episode(info["episodes"], anime["title"])
    else:
        print(f"  Episode    : {ep_num} (from --ep flag)")

    # Find the episode in the list
    ep = None
    for e in info["episodes"]:
        if e["num"] == ep_num:
            ep = e
            break

    if ep is None:
        print(f"  [warn] ep {ep_num} not in list, constructing slug")
        ep = {
            "num":       ep_num,
            "slug":      f"ep-{ep_num}",
            "mal":       info["mal_id"],
            "timestamp": info["timestamp"],
            "ep_id":     None,
            "vrf":       "",
        }
    else:
        print(f"  Episode {ep_num}: slug={ep['slug']!r}  ep_id={ep['ep_id']!r}")

    mal_id    = ep.get("mal") or info["mal_id"]
    timestamp = ep.get("timestamp") or info["timestamp"]

    if not mal_id:
        raise ValueError("Could not determine MAL ID for this anime.")

    # ── 3-5. mapper → decrypt → m3u8
    mapper_data = get_mapper_tokens(mal_id, ep_num, timestamp)
    mewcdn_streams = {}
    for stype, token in mapper_data["tokens"].items():
        try:
            player_url, skip_data = decrypt_token(token, stype)
            decoded = decode_mewcdn_url(player_url, stype)
            decoded["skip_data"] = skip_data
            mewcdn_streams[stype] = decoded
        except Exception as e:
            print(f"  [warn] mewcdn {stype}: {e}")

    # ── 6. Megaplay / Vidwish realid
    stream_urls = {}
    try:
        stream_urls = get_megaplay_vidwish_urls(
            anikoto_id=info["anikoto_id"],
            ep_slug=ep["slug"],
            ep_num=ep_num,
            anime_slug=anime_slug,
            ep_vrf=ep.get("vrf", ""),
            ep_id=ep.get("ep_id", ""),
        )
    except Exception as e:
        print(f"\n  [warn] megaplay/vidwish: {e}")

    # ── Build result
    result = {
        "anime":          anime["title"],
        "mal_id":         mal_id,
        "episode":        ep_num,
        "anikoto_id":     info["anikoto_id"],
        "mewcdn_streams": mewcdn_streams,
        "stream_urls":    stream_urls,
        "downloads":      mapper_data.get("downloads", {}),
    }

    if json_out:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_result(result, W)

    return result


def _print_result(r: dict, W: int = 68):
    sep = "=" * W
    print(f"\n{sep}")
    print("  RESULTS")
    print(sep)
    print(f"  Anime   : {r['anime']}")
    print(f"  MAL ID  : {r['mal_id']}")
    print(f"  Episode : {r['episode']}")

    # ── Megaplay / Vidwish
    su = r.get("stream_urls", {})
    if su.get("realid"):
        print(f"\n  ── Megaplay / Vidwish  (realid={su['realid']}) {'─'*(W-42)}")
        print(f"  Megaplay SUB : {su.get('megaplay_sub', 'N/A')}")
        print(f"  Megaplay DUB : {su.get('megaplay_dub', 'N/A')}")
        print(f"  Vidwish  SUB : {su.get('vidwish_sub',  'N/A')}")
        print(f"  Vidwish  DUB : {su.get('vidwish_dub',  'N/A')}")
    else:
        print(f"\n  [!] Megaplay/Vidwish URLs not available for this episode.")

    # ── mewcdn / m3u8
    for stype, s in r.get("mewcdn_streams", {}).items():
        bar = "─" * max(1, W - 12 - len(stype))
        print(f"\n  ── mewcdn {stype.upper()} {bar}")
        print(f"  Player  : {s.get('mewcdn_url', 'N/A')}")
        print(f"  m3u8    : {s.get('m3u8_direct', 'N/A')}")
        skip  = s.get("skip_data", {})
        intro = skip.get("intro", [0, 0])
        outro = skip.get("outro", [0, 0])
        if any(intro) or any(outro):
            print(f"  Skip intro : {intro[0]}s → {intro[1]}s")
            print(f"  Skip outro : {outro[0]}s → {outro[1]}s")

    # ── Downloads
    dl = r.get("downloads", {})
    if dl:
        print(f"\n  ── Downloads {'─'*(W-14)}")
        for quality, url in dl.items():
            print(f"  [{quality}] {url}")

    print(sep)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--query", "-q", type=str, default=None,
        help="Anime name to search (prompted if omitted)",
    )
    parser.add_argument(
        "--mal", "-m", type=int, default=None,
        help="MyAnimeList ID — skip search, go direct (e.g. --mal 1735 --ep 1)",
    )
    parser.add_argument(
        "--ep", "-e", type=int, default=None,
        help="Episode number (prompted interactively if omitted)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON instead of formatted text",
    )
    args = parser.parse_args()

    try:
        # ── MAL direct mode (via flag)
        if args.mal:
            run_by_mal(mal_id=args.mal, ep_num=args.ep, json_out=args.json)
            return

        # ── Search mode (via flag)
        if args.query:
            run(query=args.query, ep_num=args.ep, json_out=args.json)
            return

        # ── Interactive mode — no flags given, ask the user
        print("\n  ┌─────────────────────────────────────┐")
        print("  │   Anime Stream Finder               │")
        print("  └─────────────────────────────────────┘")
        print("\n  How do you want to search?")
        print("  [1] Search by anime name")
        print("  [2] Enter MAL ID directly")
        print()

        while True:
            try:
                mode = input("  Choose (1 or 2): ").strip()
            except KeyboardInterrupt:
                print("\nAborted.")
                sys.exit(0)
            if mode in ("1", "2"):
                break
            print("  Enter 1 or 2.")

        if mode == "2":
            # MAL ID + episode prompt
            while True:
                try:
                    mal_raw = input("\n  MAL ID: ").strip()
                    mal_id  = int(mal_raw)
                    if mal_id > 0:
                        break
                except (ValueError, KeyboardInterrupt):
                    pass
                print("  Invalid, enter a positive integer.")

            run_by_mal(mal_id=mal_id, ep_num=args.ep, json_out=args.json)

        else:
            # Search by name
            try:
                query = input("\n  Search anime: ").strip()
            except KeyboardInterrupt:
                print("\nAborted.")
                sys.exit(0)
            if not query:
                print("No query provided.")
                sys.exit(1)
            run(query=query, ep_num=args.ep, json_out=args.json)

    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
