"""Suporte a EPG: cobertura de guia e geração de channels.xml para o grabber do iptv-org/epg."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from .curate import Entry


def _best_guides(entries: list[Entry], guides: list[dict], preferred_sites: list[str]) -> dict[str, dict]:
    """Escolhe 1 guia (site) por tvg_id. Preferência: mesmo feed > guia sem feed > sites preferidos."""
    by_channel: dict[str, list[dict]] = defaultdict(list)
    for g in guides:
        if g.get("channel") and g.get("site") and g.get("site_id") is not None:
            by_channel[g["channel"]].append(g)

    site_rank = {s: i for i, s in enumerate(preferred_sites)}
    chosen: dict[str, dict] = {}
    for e in entries:
        if e.tvg_id in chosen:
            continue
        cands = by_channel.get(e.channel_id, [])
        if not cands:
            continue
        cands = sorted(
            cands,
            key=lambda g: (
                0 if (g.get("feed") and g.get("feed") == e.feed_id) else (1 if not g.get("feed") else 2),
                site_rank.get(g["site"], len(site_rank)),
                g["site"],
                str(g["site_id"]),
            ),
        )
        # guia de outro feed não serve para este feed
        for g in cands:
            if not g.get("feed") or g.get("feed") == e.feed_id:
                chosen[e.tvg_id] = g
                break
    return chosen


def coverage(entries: list[Entry], guides: list[dict]) -> tuple[int, int]:
    """(canais com guia disponível, total de canais únicos)."""
    chosen = _best_guides(entries, guides, [])
    total = len({e.tvg_id for e in entries})
    return len(chosen), total


def write_channels_xml(entries: list[Entry], guides: list[dict], path: Path, preferred_sites: list[str]) -> int:
    """Gera channels.xml no formato do grabber iptv-org/epg. Devolve quantos canais têm guia."""
    chosen = _best_guides(entries, guides, preferred_sites)
    names = {e.tvg_id: e.name for e in entries}
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<channels>"]
    for tvg_id in sorted(chosen):
        g = chosen[tvg_id]
        lang = g.get("lang") or "en"
        lines.append(
            f"  <channel site={quoteattr(g['site'])} site_id={quoteattr(str(g['site_id']))} "
            f"lang={quoteattr(lang)} xmltv_id={quoteattr(tvg_id)}>{escape(names[tvg_id])}</channel>"
        )
    lines.append("</channels>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(chosen)

