"""Linha de comando: python -m iptv_builder build | validate"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import epg, m3u
from .check import check_entries
from .config import ConfigError, load_config
from .curate import Catalog, collect, finalize, limit_per_channel
from .data import load_dataset


def _index_html(items: list[dict], generated: str) -> str:
    rows = "\n".join(
        f'<li><b>{html.escape(i["name"])}</b> — {i["channels"]} canais<br>'
        f'<a href="{html.escape(i["file"])}">{html.escape(i["file"])}</a> '
        f'<code class="abs" data-href="{html.escape(i["file"])}"></code></li>'
        for i in items
    )
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<title>Playlists IPTV</title>
<body style="font-family:sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem">
<h1>Playlists IPTV</h1><p>Atualizado em {generated} (UTC). Copie o link completo para o seu player.</p>
<ul>{rows}</ul>
<script>document.querySelectorAll('.abs').forEach(e=>e.textContent=new URL(e.dataset.href,location.href).href)</script>
</body></html>
"""


def cmd_build(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    base = cfg.base_dir
    out_dir = base / cfg.settings["output_dir"]
    cache_dir = base / cfg.settings["cache_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Carregando dados do iptv-org...")
    dataset = load_dataset(
        cache_dir, cfg.settings["cache_max_age_hours"], Path(args.data_dir) if args.data_dir else None
    )
    catalog = Catalog(dataset)

    check_on = cfg.check["enabled"] if args.check is None else args.check
    report = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "playlists": []}
    index_items: list[dict] = []
    exit_code = 0

    for rules in cfg.playlists:
        if args.only and rules.name not in args.only:
            continue
        print(f"\n[{rules.name}]")
        stats: Counter = Counter()
        candidates = collect(catalog, rules, cfg, stats)
        print(f"  {len(candidates)} streams candidatos")

        if check_on:
            keep = max(cfg.check["candidates_per_channel"], rules.max_streams_per_channel)
            to_test = limit_per_channel(candidates, keep)
            alive = check_entries(
                to_test,
                cache_dir / "stream_status.json",
                cfg.check["timeout"],
                cfg.check["workers"],
                cfg.check["ttl_hours"],
                cfg.check["retry_failed_hours"],
            )
            stats["offline"] = sum(1 for e in to_test if not alive.get(e.url))
            candidates = [e for e in to_test if alive.get(e.url)]

        entries = finalize(candidates, rules, cfg, stats)

        # Prioritários pedidos que não apareceram (ID errado, offline, geoblock...)
        present = {e.channel_id for e in entries}
        missing = [c for c in rules.priority_channels if c not in present]
        for c in missing:
            print(f"  AVISO: canal prioritário sem stream utilizável: {c}")

        text = m3u.render(entries, cfg.epg["url"])
        problems = m3u.validate(text)
        if problems:
            print("  ERRO: playlist gerada é inválida:")
            for p in problems[:10]:
                print("   -", p)
            exit_code = 1
            continue
        (out_dir / rules.file).write_text(text, encoding="utf-8", newline="\n")

        with_guide, total = epg.coverage(entries, catalog.guides)
        print(f"  OK: {len(entries)} entradas -> {rules.file} (guia disponível para {with_guide}/{total} canais)")
        if cfg.epg["generate_channels_xml"]:
            xml_name = f"{Path(rules.file).stem}.channels.xml"
            epg.write_channels_xml(entries, catalog.guides, out_dir / xml_name, cfg.epg["preferred_sites"])

        report["playlists"].append(
            {
                "name": rules.name,
                "file": rules.file,
                "channels": len(entries),
                "epg_coverage": f"{with_guide}/{total}",
                "descartados": dict(stats),
                "prioritarios_ausentes": missing,
            }
        )
        index_items.append({"name": rules.name, "file": rules.file, "channels": len(entries)})

    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "index.html").write_text(_index_html(index_items, report["generated_at"]), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    print(f"\nArquivos gerados em: {out_dir}")
    return exit_code


def cmd_validate(args: argparse.Namespace) -> int:
    code = 0
    expanded_files: list[Path] = []
    for pattern in args.files:
        p = Path(pattern)
        if "*" in pattern or "?" in pattern:
            parent = p.parent if str(p.parent) != "" else Path(".")
            expanded_files.extend(parent.glob(p.name))
        elif p.exists():
            expanded_files.append(p)
        else:
            print(f"AVISO: arquivo não encontrado para validação: {pattern}")
    if not expanded_files:
        print("Nenhum arquivo para validar.")
        return 0
    for f in expanded_files:
        problems = m3u.validate(f.read_text(encoding="utf-8"))
        if problems:
            code = 1
            print(f"{f}: INVÁLIDO")
            for p in problems[:20]:
                print("  -", p)
        else:
            print(f"{f}: ok")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iptv_builder", description="Gera playlists IPTV M3U a partir do iptv-org.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="gera as playlists definidas no arquivo de configuração")
    b.add_argument("-c", "--config", default="config/playlists.toml")
    b.add_argument("--check", dest="check", action="store_true", default=None, help="testa se os streams respondem")
    b.add_argument("--no-check", dest="check", action="store_false", help="não testa os streams")
    b.add_argument("--only", nargs="+", help="gera só as playlists com esses nomes")
    b.add_argument("--data-dir", help="usa JSONs locais em vez de baixar (testes/offline)")
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("validate", help="valida a sintaxe de arquivos .m3u/.m3u8")
    v.add_argument("files", nargs="+")
    v.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, FileNotFoundError, RuntimeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

