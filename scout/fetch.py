"""Hämtar sidor från stats.swehockey.se med diskcache och artig fördröjning."""
from __future__ import annotations

import hashlib
import time
import urllib.request
from pathlib import Path

BASE = "https://stats.swehockey.se"
USER_AGENT = "scoutrapport/0.1 (PoC; matchanalys)"


class Fetcher:
    def __init__(self, cache_dir: Path, delay: float = 0.7, verbose: bool = True):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.verbose = verbose
        self._last = 0.0

    def get(self, path: str, max_age: float | None = None) -> str:
        """Hämta en sida. max_age=None betyder att cachen aldrig går ut
        (spelade matcher ändras inte). Sekunder annars."""
        key = hashlib.sha1(path.encode()).hexdigest()[:16]
        f = self.cache_dir / f"{key}.html"
        if f.exists() and (max_age is None or time.time() - f.stat().st_mtime < max_age):
            return f.read_text(encoding="utf-8")

        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        if self.verbose:
            print(f"  hämtar {path}")
        req = urllib.request.Request(BASE + path, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8", errors="replace")
        self._last = time.time()
        f.write_text(text, encoding="utf-8")
        return text
