"""Verificação de streams: descarta links que estão offline ou não são reproduzíveis."""

from __future__ import annotations

import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .curate import Entry

_DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def check_stream(entry: Entry, timeout: float) -> bool:
    """True se o stream responde 200 e parece conteúdo de vídeo válido.

    - HLS (.m3u8): o corpo precisa começar com #EXTM3U.
    - Outros formatos: basta responder 200 com algum dado.
    Lê só os primeiros bytes, então é rápido e não baixa o vídeo.
    """
    headers = {"User-Agent": entry.user_agent or _DEFAULT_UA}
    if entry.referrer:
        headers["Referer"] = entry.referrer
    try:
        req = urllib.request.Request(entry.url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            ctype = (resp.headers.get("Content-Type") or "").lower()
            head = resp.read(2048)
    except Exception:
        return False  # timeout, DNS, TLS, HTTP 4xx/5xx...
    if not head:
        return False
    is_hls = ".m3u8" in entry.url.lower() or "mpegurl" in ctype
    if is_hls:
        return head.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"#EXTM3U")
    if "text/html" in ctype:  # página de erro/login disfarçada de 200
        return False
    return True


def check_entries(
    entries: list[Entry],
    cache_file: Path,
    timeout: float,
    workers: int,
    ttl_hours: float,
    retry_failed_hours: float,
) -> dict[str, bool]:
    """Testa as URLs (em paralelo) reaproveitando resultados recentes do cache."""
    cache: dict[str, list] = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}

    now = time.time()
    result: dict[str, bool] = {}
    todo: dict[str, Entry] = {}
    for e in entries:
        hit = cache.get(e.url)
        if hit:
            ok, ts = hit
            ttl = ttl_hours if ok else retry_failed_hours
            if now - ts < ttl * 3600:
                result[e.url] = bool(ok)
                continue
        todo.setdefault(e.url, e)

    if todo:
        print(f"  testando {len(todo)} streams ({len(result)} vieram do cache)...")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for e, ok in zip(todo.values(), pool.map(lambda x: check_stream(x, timeout), todo.values())):
                result[e.url] = ok
                cache[e.url] = [ok, now]

    # remove entradas muito antigas para o cache não crescer para sempre
    cache = {u: v for u, v in cache.items() if now - v[1] < 7 * 24 * 3600}
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache), encoding="utf-8")
    return result

