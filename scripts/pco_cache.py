"""Lazy on-disk cache for PCO API responses.

Drop-in replacement for the per-script `get(path, **params)` pattern.
Every successful fetch is mirrored to ``cache/`` as JSON. Repeat calls
hit disk, not the network. Cache never expires automatically — pass
``_refresh=True`` (or delete the cache/ dir) when you need fresh data.

Usage:
    from pco_cache import get

    data = get("/service_types", per_page=100)
    plans = get(f"/service_types/{sid}/plans", filter="future")

    # force a network fetch (e.g. refreshing upcoming plans before a matrix build):
    plans = get(f"/service_types/{sid}/plans", filter="future", _refresh=True)
"""
import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

BASE = "https://api.planningcenteronline.com/services/v2"
CACHE_DIR = Path(__file__).parent / "cache"

_SECRETS = Path.home() / "Secrets" / "pco.env"
if not _SECRETS.exists():
    sys.exit("No secrets file at ~/Secrets/pco.env")
load_dotenv(dotenv_path=_SECRETS)
_CID, _SEC = os.getenv("PCO_CLIENT_ID"), os.getenv("PCO_SECRET")
if not _CID or not _SEC:
    sys.exit("Missing PCO_CLIENT_ID / PCO_SECRET in ~/Secrets/pco.env")

session = requests.Session()
session.auth = (_CID, _SEC)


def _cache_path(url: str, params: dict) -> Path:
    """Stable filename: human-readable slug + short hash of url+params."""
    canonical = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    h = hashlib.sha1(canonical.encode()).hexdigest()[:16]
    slug = url.replace(BASE, "").strip("/").replace("/", "_")[:60] or "root"
    return CACHE_DIR / f"{slug}__{h}.json"


def get(path: str, *, _refresh: bool = False, **params):
    """Drop-in for the per-script `get()`. Reads cache; fetches on miss.

    Pass ``_refresh=True`` to bypass cache and force a network fetch
    (the new response overwrites the cache entry).
    """
    url = path if path.startswith("http") else BASE + path
    cache_file = _cache_path(url, params)

    if cache_file.exists() and not _refresh:
        return json.loads(cache_file.read_text())["body"]

    r = session.get(url, params=params)
    r.raise_for_status()
    body = r.json()

    CACHE_DIR.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps({
        "_meta": {
            "url": url,
            "params": params,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "body": body,
    }, indent=2))
    return body
