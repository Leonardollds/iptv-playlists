"""Download (com cache) dos dados da API pública do iptv-org.

A API (https://iptv-org.github.io/api) é gerada a partir do repositório
iptv-org/database, o mesmo que alimenta iptv-org/iptv e iptv-org/epg.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

API_BASE = "https://iptv-org.github.io/api"
REQUIRED = ("streams", "channels", "feeds", "logos", "guides")
OPTIONAL = ("countries",)
USER_AGENT = "iptv-playlist-builder/1.0 (+https://github.com/iptv-org/api)"


def _download(url: str, dest: Path, timeout: int = 90) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read()
    json.loads(payload)  # garante que o JSON está íntegro antes de gravar
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(payload)
    tmp.replace(dest)


def load_dataset(cache_dir: Path, max_age_hours: float, data_dir: Path | None = None) -> dict[str, list]:
    """Carrega os JSONs da API.

    - data_dir: se informado, lê direto dessa pasta (modo offline / testes).
    - caso contrário usa cache em cache_dir/api e só baixa de novo se estiver velho.
      Se o download falhar e existir cache antigo, usa o antigo (com aviso).
    """
    result: dict[str, list] = {}
    if data_dir is not None:
        for name in REQUIRED + OPTIONAL:
            f = Path(data_dir) / f"{name}.json"
            if f.exists():
                result[name] = json.loads(f.read_text(encoding="utf-8"))
            elif name in REQUIRED:
                raise FileNotFoundError(f"Arquivo ausente em --data-dir: {f}")
            else:
                result[name] = []
        return result

    api_cache = Path(cache_dir) / "api"
    api_cache.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED + OPTIONAL:
        f = api_cache / f"{name}.json"
        fresh = f.exists() and (time.time() - f.stat().st_mtime) < max_age_hours * 3600
        if not fresh:
            try:
                print(f"  baixando {name}.json ...")
                _download(f"{API_BASE}/{name}.json", f)
            except Exception as exc:  # rede fora do ar, JSON inválido etc.
                if f.exists():
                    print(f"  AVISO: falha ao baixar {name}.json ({exc}); usando cache antigo")
                elif name in OPTIONAL:
                    result[name] = []
                    continue
                else:
                    raise RuntimeError(f"Não foi possível obter {name}.json: {exc}") from exc
        result[name] = json.loads(f.read_text(encoding="utf-8"))
    return result

