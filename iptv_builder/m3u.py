"""Geração e validação de arquivos M3U/M3U8."""

from __future__ import annotations

import re

from .curate import Entry

_EXTINF = re.compile(r'^#EXTINF:(-?\d+(?:\.\d+)?)((?:\s+[\w\-]+="[^"]*")*)\s*,(.+)$')
_URL = re.compile(r"^https?://\S+$")


def _attr(value: str) -> str:
    """Limpa um valor de atributo: sem aspas, vírgulas ou quebras de linha (quebram parsers simples)."""
    return re.sub(r"\s+", " ", str(value).replace('"', "'").replace(",", " ")).strip()


def _title(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def render(entries: list[Entry], epg_url: str = "") -> str:
    header = "#EXTM3U"
    if epg_url:
        header += f' x-tvg-url="{_attr(epg_url)}"'
    lines = [header]
    for e in entries:
        attrs = f'tvg-id="{_attr(e.tvg_id)}" tvg-name="{_attr(e.name)}"'
        if e.logo:
            attrs += f' tvg-logo="{_attr(e.logo)}"'
        attrs += f' group-title="{_attr(e.group)}"'
        lines.append(f"#EXTINF:-1 {attrs},{_title(e.name)}")
        if e.referrer:
            lines.append(f"#EXTVLCOPT:http-referrer={_title(e.referrer)}")
        if e.user_agent:
            lines.append(f"#EXTVLCOPT:http-user-agent={_title(e.user_agent)}")
        lines.append(e.url)
    return "\n".join(lines) + "\n"


def validate(text: str) -> list[str]:
    """Verifica a sintaxe da playlist. Devolve a lista de problemas (vazia = válida)."""
    errors: list[str] = []
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or not lines[0].startswith("#EXTM3U"):
        return ["A primeira linha deve começar com #EXTM3U"]

    pending: int | None = None  # nº da linha do #EXTINF que ainda espera uma URL
    seen_urls: set[str] = set()
    channels = 0
    for n, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            if pending is not None:
                errors.append(f"linha {pending}: #EXTINF sem URL logo após")
            if not _EXTINF.match(line):
                errors.append(f"linha {n}: #EXTINF malformado")
            pending = n
        elif line.startswith("#"):
            continue  # #EXTVLCOPT, #EXTGRP etc.
        else:
            if pending is None:
                errors.append(f"linha {n}: URL sem #EXTINF antes")
            if not _URL.match(line):
                errors.append(f"linha {n}: URL inválida: {line[:80]}")
            key = line.rstrip("/").lower()
            if key in seen_urls:
                errors.append(f"linha {n}: URL duplicada")
            seen_urls.add(key)
            pending = None
            channels += 1
    if pending is not None:
        errors.append(f"linha {pending}: #EXTINF sem URL logo após")
    if channels == 0:
        errors.append("A playlist não tem nenhum canal")
    return errors

