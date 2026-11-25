"""Filtragem e curadoria: transforma os dados brutos da API em entradas de playlist."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .config import Config, Playlist

OTHER_GROUP = "Outros"
# Formatos de imagem que a maioria das TVs/players consegue desenhar (SVG costuma falhar).
_RASTER = {"png": 0, "jpeg": 0, "jpg": 0, "webp": 1}


@dataclass
class Entry:
    tvg_id: str
    channel_id: str
    feed_id: str | None
    name: str
    url: str
    group: str
    logo: str = ""
    quality: str = ""
    referrer: str = ""
    user_agent: str = ""
    category: str = ""  # categoria original (para ordenar grupos)


def quality_height(quality: str | None) -> int:
    m = re.match(r"(\d+)", quality or "")
    return int(m.group(1)) if m else 0


def _build_logo_index(logos: list[dict]) -> dict[tuple[str, str | None], str]:
    """Escolhe o melhor logo por (canal, feed): em uso > formato raster > maior largura."""
    best: dict[tuple[str, str | None], tuple] = {}
    for lg in logos:
        url = lg.get("url")
        if not url or not lg.get("channel"):
            continue
        fmt = (lg.get("format") or "").lower()
        score = (
            0 if lg.get("in_use", True) else 1,
            _RASTER.get(fmt, 2),
            -(lg.get("width") or 0),
        )
        key = (lg["channel"], lg.get("feed"))
        if key not in best or score < best[key][0]:
            best[key] = (score, url)
    return {k: v[1] for k, v in best.items()}


class Catalog:
    """Índices pré-calculados sobre o dataset (criado uma vez, usado por todas as playlists)."""

    def __init__(self, dataset: dict[str, list]):
        self.streams = dataset["streams"]
        self.channels = {c["id"]: c for c in dataset["channels"]}
        self.feeds = {(f["channel"], f["id"]): f for f in dataset["feeds"]}
        self.main_feed = {f["channel"]: f["id"] for f in dataset["feeds"] if f.get("is_main")}
        self.logos = _build_logo_index(dataset["logos"])
        self.countries = {c["code"].upper(): c.get("name", c["code"]) for c in dataset.get("countries", [])}
        self.guides = dataset["guides"]


def _group_name(cat_or_country: str, cfg: Config) -> str:
    if not cat_or_country or cat_or_country == "undefined":
        return OTHER_GROUP
    return cfg.group_names.get(cat_or_country.lower(), cat_or_country.replace("_", " ").title())


def collect(catalog: Catalog, rules: Playlist, cfg: Config, stats: Counter) -> list[Entry]:
    """Aplica os filtros e devolve TODOS os streams candidatos (ainda sem escolher o melhor)."""
    s = cfg.settings
    forced = set(rules.include_channels) | set(rules.priority_channels)
    excluded = set(rules.exclude_channels)
    priority_group = rules.priority_group
    out: list[Entry] = []

    for st in catalog.streams:
        ch_id = st.get("channel")
        url = (st.get("url") or "").strip()
        if not ch_id or ch_id not in catalog.channels:
            stats["sem_canal"] += 1
            continue
        if ch_id in excluded:
            stats["excluido_na_config"] += 1
            continue
        if not re.match(r"^https?://\S+$", url):
            stats["url_invalida"] += 1
            continue
        ch = catalog.channels[ch_id]

        if s["exclude_nsfw"] and ch.get("is_nsfw"):
            stats["nsfw"] += 1
            continue
        if s["exclude_closed"] and ch.get("closed"):
            stats["canal_encerrado"] += 1
            continue
        if s["exclude_geoblocked"] and "geo" in (st.get("label") or "").lower():
            stats["geoblock"] += 1
            continue
        if s["https_only"] and not url.startswith("https://"):
            stats["sem_https"] += 1
            continue
        referrer = (st.get("referrer") or "").strip()
        user_agent = (st.get("user_agent") or "").strip()
        if (referrer or user_agent) and not s["allow_header_streams"]:
            stats["exige_headers"] += 1
            continue

        feed_key = st.get("feed")
        feed = catalog.feeds.get((ch_id, feed_key or catalog.main_feed.get(ch_id)))
        languages = {x.lower() for x in (feed or {}).get("languages", [])}
        categories = [c.lower() for c in ch.get("categories", [])]
        country = (ch.get("country") or "").upper()

        if ch_id not in forced:
            if rules.countries and country not in rules.countries:
                continue
            if rules.languages and not (languages & set(rules.languages)):
                continue
            if rules.categories and not (set(categories) & set(rules.categories)):
                continue
            if rules.exclude_categories and (set(categories) & set(rules.exclude_categories)):
                continue

        # Nome exibido: canal + feed quando não é o feed principal (ex.: "Globo (São Paulo)")
        name = ch["name"]
        if feed_key and feed and not feed.get("is_main") and feed.get("name"):
            name = f"{name} ({feed['name']})"
        if s["quality_in_name"] and st.get("quality"):
            name = f"{name} [{st['quality']}]"

        if ch_id in rules.priority_channels and priority_group:
            group = priority_group
        elif rules.group_by == "country":
            group = catalog.countries.get(country, country) or OTHER_GROUP
        else:
            group = _group_name(categories[0] if categories else "", cfg)

        logo = (
            catalog.logos.get((ch_id, feed_key))
            or catalog.logos.get((ch_id, None))
            or ""
        )
        out.append(
            Entry(
                tvg_id=ch_id + (f"@{feed_key}" if feed_key else ""),
                channel_id=ch_id,
                feed_id=feed_key,
                name=name,
                url=url,
                group=group,
                logo=logo,
                quality=st.get("quality") or "",
                referrer=referrer,
                user_agent=user_agent,
                category=categories[0] if categories else "",
            )
        )
    # melhor qualidade primeiro; desempate pela URL para a saída ser determinística
    out.sort(key=lambda e: (e.tvg_id, -quality_height(e.quality), e.url))
    return out


def limit_per_channel(entries: list[Entry], n: int) -> list[Entry]:
    """Mantém os n melhores streams de cada tvg_id (assume lista já ordenada por qualidade)."""
    count: Counter = Counter()
    kept = []
    for e in entries:
        if count[e.tvg_id] < n:
            count[e.tvg_id] += 1
            kept.append(e)
    return kept


def finalize(entries: list[Entry], rules: Playlist, cfg: Config, stats: Counter) -> list[Entry]:
    """Escolhe os streams finais, remove URLs duplicadas e ordena a lista."""
    chosen = limit_per_channel(entries, rules.max_streams_per_channel)

    seen_urls: set[str] = set()
    unique: list[Entry] = []
    for e in chosen:
        key = e.url.rstrip("/").lower()
        if key in seen_urls:
            stats["url_duplicada"] += 1
            continue
        seen_urls.add(key)
        unique.append(e)

    # 2º+ stream do mesmo canal ganha sufixo para não aparecer nome repetido no player
    seen: Counter = Counter()
    for e in unique:
        seen[e.tvg_id] += 1
        if seen[e.tvg_id] > 1:
            e.name = f"{e.name} #{seen[e.tvg_id]}"

    prio = {cid: i for i, cid in enumerate(rules.priority_channels)}
    order = {g: i for i, g in enumerate(_group_name(c, cfg) for c in cfg.settings["group_order"])}

    def sort_key(e: Entry):
        # ordem: prioritários -> grupos listados em group_order -> demais grupos (A-Z) -> "Outros"
        if e.group == OTHER_GROUP:
            group_rank = len(order) + 1
        else:
            group_rank = order.get(e.group, len(order))
        return (
            prio.get(e.channel_id, len(prio)),
            group_rank,
            e.group.casefold(),
            e.name.casefold(),
            e.tvg_id,
        )

    unique.sort(key=sort_key)
    return unique
