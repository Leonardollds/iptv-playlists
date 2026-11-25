"""Leitura e validação do arquivo de configuração (TOML)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Valores padrão de cada playlist. Podem ser sobrescritos em [defaults] e em cada [[playlist]].
PLAYLIST_DEFAULTS = {
    "countries": [],             # códigos ISO 3166-1 alpha-2, ex.: ["BR", "PT"]. Vazio = todos
    "languages": [],             # códigos ISO 639-3, ex.: ["por"]. Vazio = todos
    "categories": [],            # ex.: ["news", "sports"]. Vazio = todas
    "exclude_categories": [],    # ex.: ["shop"]
    "include_channels": [],      # IDs que entram mesmo sem passar pelos filtros
    "exclude_channels": [],      # IDs que nunca entram
    "priority_channels": [],     # IDs que vêm primeiro (nessa ordem); entram automaticamente
    "priority_group": "",        # se preenchido, vira o group-title dos canais prioritários
    "group_by": "category",      # "category" ou "country"
    "max_streams_per_channel": 1,
}
PLAYLIST_ONLY_KEYS = {"name", "file"}

SETTINGS_DEFAULTS = {
    "output_dir": "public",
    "cache_dir": ".cache",
    "cache_max_age_hours": 6,
    "exclude_nsfw": True,
    "exclude_closed": True,
    "exclude_geoblocked": True,
    "allow_header_streams": False,  # streams que exigem referrer/user-agent específicos
    "https_only": False,
    "quality_in_name": False,
    "group_order": [],
}

CHECK_DEFAULTS = {
    "enabled": False,
    "timeout": 8,
    "workers": 32,
    "ttl_hours": 12,             # quanto tempo um "funciona" fica em cache
    "retry_failed_hours": 6,     # quanto tempo um "falhou" fica em cache
    "candidates_per_channel": 3, # quantos streams por canal testar (os de melhor qualidade)
}

EPG_DEFAULTS = {
    "url": "",                   # URL pública do XMLTV (vai em x-tvg-url)
    "generate_channels_xml": True,
    "preferred_sites": [],       # ex.: ["mi.tv", "tvguia.es"]
}


class ConfigError(ValueError):
    pass


@dataclass
class Playlist:
    name: str
    file: str
    countries: list[str]
    languages: list[str]
    categories: list[str]
    exclude_categories: list[str]
    include_channels: list[str]
    exclude_channels: list[str]
    priority_channels: list[str]
    priority_group: str
    group_by: str
    max_streams_per_channel: int


@dataclass
class Config:
    settings: dict
    check: dict
    epg: dict
    group_names: dict[str, str]
    playlists: list[Playlist] = field(default_factory=list)
    base_dir: Path = Path(".")


def _merge(defaults: dict, given: dict, section: str) -> dict:
    unknown = set(given) - set(defaults)
    if unknown:
        raise ConfigError(f"[{section}] chaves desconhecidas: {', '.join(sorted(unknown))}")
    return {**defaults, **given}


def load_config(path: str | Path) -> Config:
    path = Path(path)
    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    settings = _merge(SETTINGS_DEFAULTS, raw.get("settings", {}), "settings")
    check = _merge(CHECK_DEFAULTS, raw.get("check", {}), "check")
    epg = _merge(EPG_DEFAULTS, raw.get("epg", {}), "epg")
    defaults = _merge(PLAYLIST_DEFAULTS, raw.get("defaults", {}), "defaults")

    playlists: list[Playlist] = []
    for i, pl in enumerate(raw.get("playlist", []), start=1):
        unknown = set(pl) - set(PLAYLIST_DEFAULTS) - PLAYLIST_ONLY_KEYS
        if unknown:
            raise ConfigError(f"[[playlist]] #{i}: chaves desconhecidas: {', '.join(sorted(unknown))}")
        if "name" not in pl or "file" not in pl:
            raise ConfigError(f"[[playlist]] #{i}: 'name' e 'file' são obrigatórios")
        if Path(pl["file"]).name != pl["file"]:
            raise ConfigError(f"[[playlist]] {pl['name']}: 'file' deve ser só o nome do arquivo")
        if not pl["file"].lower().endswith((".m3u", ".m3u8")):
            raise ConfigError(f"[[playlist]] {pl['name']}: 'file' deve terminar em .m3u ou .m3u8")

        merged = {**defaults, **pl}
        if merged["group_by"] not in ("category", "country"):
            raise ConfigError(f"[[playlist]] {pl['name']}: group_by deve ser 'category' ou 'country'")
        if int(merged["max_streams_per_channel"]) < 1:
            raise ConfigError(f"[[playlist]] {pl['name']}: max_streams_per_channel deve ser >= 1")

        playlists.append(
            Playlist(
                name=merged["name"],
                file=merged["file"],
                countries=[c.upper() for c in merged["countries"]],
                languages=[c.lower() for c in merged["languages"]],
                categories=[c.lower() for c in merged["categories"]],
                exclude_categories=[c.lower() for c in merged["exclude_categories"]],
                include_channels=list(merged["include_channels"]),
                exclude_channels=list(merged["exclude_channels"]),
                priority_channels=list(merged["priority_channels"]),
                priority_group=merged["priority_group"],
                group_by=merged["group_by"],
                max_streams_per_channel=int(merged["max_streams_per_channel"]),
            )
        )

    if not playlists:
        raise ConfigError("Nenhuma [[playlist]] definida no arquivo de configuração")
    names = [p.name for p in playlists]
    files = [p.file for p in playlists]
    if len(set(names)) != len(names) or len(set(files)) != len(files):
        raise ConfigError("Os campos 'name' e 'file' das playlists devem ser únicos")

    return Config(
        settings=settings,
        check=check,
        epg=epg,
        group_names={k.lower(): v for k, v in raw.get("group_names", {}).items()},
        playlists=playlists,
        base_dir=path.resolve().parent.parent if path.resolve().parent.name == "config" else path.resolve().parent,
    )

