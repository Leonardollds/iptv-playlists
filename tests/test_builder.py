"""Testes offline (sem rede) usando os JSONs de tests/fixtures. Rode com: python -m unittest"""

import tempfile
import unittest
from collections import Counter
from pathlib import Path

from iptv_builder import cli, epg, m3u
from iptv_builder.config import ConfigError, load_config
from iptv_builder.curate import Catalog, collect, finalize
from iptv_builder.data import load_dataset

FIXTURES = Path(__file__).parent / "fixtures"

CONFIG = """
[settings]
output_dir = "out"
group_order = ["news"]

[epg]
url = "https://exemplo.test/guide.xml"
preferred_sites = ["guia-a.test"]

[group_names]
news = "Notícias"
general = "Geral"

[defaults]
languages = []

[[playlist]]
name = "brasil"
file = "brasil.m3u"
countries = ["BR"]
priority_channels = ["GloboNews.br"]
priority_group = "Favoritos"

[[playlist]]
name = "so_noticias"
file = "so_noticias.m3u8"
categories = ["news"]
include_channels = ["RTP1.pt"]

[[playlist]]
name = "portugues"
file = "portugues.m3u"
languages = ["por"]
exclude_channels = ["RTP1.pt"]
"""


class BuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cfg_dir = Path(cls.tmp.name) / "config"
        cfg_dir.mkdir()
        (cfg_dir / "playlists.toml").write_text(CONFIG, encoding="utf-8")
        cls.cfg = load_config(cfg_dir / "playlists.toml")
        cls.catalog = Catalog(load_dataset(Path("x"), 1, FIXTURES))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def build(self, name):
        rules = next(p for p in self.cfg.playlists if p.name == name)
        stats = Counter()
        entries = finalize(collect(self.catalog, rules, self.cfg, stats), rules, self.cfg, stats)
        return entries, stats

    def ids(self, name):
        return [e.channel_id for e in self.build(name)[0]]

    def test_filtro_por_pais_e_descartes(self):
        entries, stats = self.build("brasil")
        ids = [e.channel_id for e in entries]
        self.assertNotIn("RTP1.pt", ids)          # outro país
        self.assertNotIn("Adulto.br", ids)        # nsfw
        self.assertNotIn("Antigo.br", ids)        # encerrado
        self.assertNotIn("GeoTV.br", ids)         # geoblock
        self.assertNotIn("TVBrasil.br", ids)      # exige referrer
        self.assertNotIn("Esporte.br", ids)       # URL rtmp inválida
        self.assertEqual(stats["nsfw"], 1)
        self.assertEqual(stats["exige_headers"], 1)

    def test_melhor_qualidade_e_prioridade(self):
        entries, _ = self.build("brasil")
        self.assertEqual(entries[0].channel_id, "GloboNews.br")   # prioritário vem primeiro
        self.assertTrue(entries[0].url.endswith("globonews_1080.m3u8"))
        self.assertEqual(entries[0].group, "Favoritos")
        self.assertEqual(sum(e.channel_id == "GloboNews.br" for e in entries), 1)

    def test_duplicatas_por_url(self):
        ids = self.ids("brasil")
        self.assertEqual(sum(i in ("DupA.br", "DupB.br") for i in ids), 1)

    def test_feed_vira_tvg_id_e_nome(self):
        e = next(x for x in self.build("brasil")[0] if x.channel_id == "Regional.br")
        self.assertEqual(e.tvg_id, "Regional.br@SP")
        self.assertEqual(e.name, "Regional (São Paulo)")
        self.assertEqual(e.group, "Outros")

    def test_logo_prefere_png_a_svg(self):
        e = next(x for x in self.build("brasil")[0] if x.channel_id == "GloboNews.br")
        self.assertTrue(e.logo.endswith(".png"))

    def test_categoria_e_include(self):
        ids = self.ids("so_noticias")
        self.assertIn("GloboNews.br", ids)
        self.assertIn("CNN.us", ids)
        self.assertIn("RTP1.pt", ids)             # forçado por include_channels
        self.assertNotIn("TVBrasil.br", ids)

    def test_idioma_e_exclude(self):
        ids = self.ids("portugues")
        self.assertIn("GloboNews.br", ids)
        self.assertNotIn("CNN.us", ids)           # inglês
        self.assertNotIn("RTP1.pt", ids)          # excluído na config

    def test_playlist_gerada_e_valida(self):
        entries, _ = self.build("brasil")
        text = m3u.render(entries, self.cfg.epg["url"])
        self.assertTrue(text.startswith('#EXTM3U x-tvg-url="https://exemplo.test/guide.xml"\n'))
        self.assertEqual(m3u.validate(text), [])
        self.assertIn('tvg-id="GloboNews.br"', text)
        self.assertIn('group-title="Favoritos"', text)

    def test_atributos_sao_sanitizados(self):
        # o nome do CNN tem aspas e vírgula, que quebrariam o #EXTINF se fossem copiadas cruas
        entries, _ = self.build("so_noticias")
        text = m3u.render(entries)
        self.assertEqual(m3u.validate(text), [])
        cnn = next(line for line in text.splitlines() if "CNN.us" in line)
        self.assertIn("tvg-name=\"CNN The 'News' Channel\"", cnn)

    def test_validador_pega_erros(self):
        self.assertTrue(m3u.validate("http://a.test/x.m3u8\n"))                        # sem #EXTM3U
        self.assertTrue(m3u.validate("#EXTM3U\n#EXTINF:-1,Canal\n"))                   # sem URL
        self.assertTrue(m3u.validate("#EXTM3U\n#EXTINF:-1,Canal\nrtmp://a/b\n"))       # URL inválida
        self.assertTrue(m3u.validate("#EXTM3U\n#EXTINF:abc,Canal\nhttp://a.test/x\n")) # EXTINF ruim
        dup = "#EXTM3U\n#EXTINF:-1,A\nhttp://a.test/x\n#EXTINF:-1,B\nhttp://a.test/x\n"
        self.assertTrue(any("duplicada" in e for e in m3u.validate(dup)))
        self.assertTrue(m3u.validate("#EXTM3U\n"))                                      # vazia
        self.assertEqual(m3u.validate("#EXTM3U\n#EXTINF:-1,A\nhttp://a.test/x\n"), [])

    def test_epg_cobertura_e_channels_xml(self):
        entries, _ = self.build("brasil")
        with_guide, total = epg.coverage(entries, self.catalog.guides)
        self.assertEqual(with_guide, 1)
        self.assertEqual(total, len(entries))
        out = Path(self.tmp.name) / "c.xml"
        n = epg.write_channels_xml(entries, self.catalog.guides, out, ["guia-a.test"])
        self.assertEqual(n, 1)
        xml = out.read_text(encoding="utf-8")
        self.assertIn('site="guia-a.test" site_id="20"', xml)   # site preferido venceu
        self.assertIn('xmltv_id="GloboNews.br"', xml)

    def test_config_invalida(self):
        bad = Path(self.tmp.name) / "bad.toml"
        bad.write_text('[[playlist]]\nname="a"\nfile="../x.m3u"\n', encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_config(bad)
        bad.write_text('[[playlist]]\nname="a"\nfile="a.m3u"\npaises=["BR"]\n', encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_config(bad)

    def test_build_completo_via_cli(self):
        cfg_path = Path(self.tmp.name) / "config" / "playlists.toml"
        code = cli.main(["build", "-c", str(cfg_path), "--data-dir", str(FIXTURES), "--no-check"])
        self.assertEqual(code, 0)
        out = Path(self.tmp.name) / "out"
        for f in ("brasil.m3u", "so_noticias.m3u8", "portugues.m3u", "report.json", "index.html", "brasil.channels.xml"):
            self.assertTrue((out / f).exists(), f)
        self.assertEqual(cli.main(["validate", str(out / "brasil.m3u")]), 0)


if __name__ == "__main__":
    unittest.main()
