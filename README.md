# IPTV Playlist Builder

Gera playlists **M3U/M3U8** filtradas e validadas a partir dos dados públicos do [iptv-org](https://github.com/iptv-org), e publica em uma URL pública (GitHub Pages) que painéis como o **IBO Player** conseguem carregar.

- Só Python 3.11+ (biblioteca padrão, **sem dependências**).
- Usa a [API do iptv-org](https://iptv-org.github.io/api), que é gerada pelo repositório [iptv-org/database](https://github.com/iptv-org/database), a mesma base de [iptv-org/iptv](https://github.com/iptv-org/iptv) e [iptv-org/epg](https://github.com/iptv-org/epg). Não precisa clonar nenhum deles.
- Só entram streams públicos que tocam sem credencial. Por padrão ficam de fora: canais adultos, encerrados, com geoblock declarado e streams que exigem `referrer`/`user-agent` específicos.

> [!NOTE]
> O projeto não hospeda vídeo. Ele só organiza links que o iptv-org cataloga. Links públicos caem ou mudam com frequência, por isso a lista é regenerada a cada 6 horas e os streams podem ser testados antes de entrar.

## Estrutura

```
.
├── config/playlists.toml        # <- você edita aqui (filtros, favoritos, EPG)
├── iptv_builder/
│   ├── cli.py                   # comandos build / validate
│   ├── config.py                # lê e valida o TOML
│   ├── data.py                  # baixa a API do iptv-org (com cache)
│   ├── curate.py                # filtros, escolha do melhor stream, ordenação
│   ├── check.py                 # testa se cada stream responde (opcional)
│   ├── m3u.py                   # gera e valida o arquivo M3U
│   └── epg.py                   # cobertura de guia + channels.xml
├── tests/                       # testes offline (python -m unittest)
├── docs/
│   ├── PUBLICACAO.md            # GitHub Pages + cadastro no IBO Player
│   └── EPG.md                   # como ter programação (XMLTV)
├── .github/workflows/update.yml # atualiza e publica a cada 6h
└── public/                      # SAÍDA gerada (não vai para o git)
```

## Uso rápido

```bash
python -m iptv_builder build              # gera tudo em public/
python -m iptv_builder build --check      # idem, testando se os streams respondem
python -m iptv_builder build --only brasil
python -m iptv_builder validate public/brasil.m3u
python -m unittest discover -s tests      # roda os testes
```

## Como configurar (`config/playlists.toml`)

Cada `[[playlist]]` vira um arquivo. Exemplo:

```toml
[[playlist]]
name = "brasil"
file = "brasil.m3u"
countries = ["BR"]                 # país do canal (ISO alpha-2)
languages = []                     # idioma do feed (ISO 639-3), vazio = todos
categories = []                    # vazio = todas
exclude_categories = ["shop"]
include_channels = ["CNN.us"]      # entra mesmo sem passar nos filtros
exclude_channels = ["Fulano.br"]   # nunca entra
priority_channels = ["GloboNews.br", "TVBrasil.br"]   # vêm primeiro, nesta ordem
priority_group = "Favoritos"       # group-title deles
group_by = "category"              # ou "country"
max_streams_per_channel = 1        # >1 = mantém alternativas de backup
```

Os filtros se combinam com **E** entre tipos (país **e** idioma **e** categoria) e **OU** dentro de cada lista. IDs de canais e códigos estão listados em [iptv-org.github.io](https://iptv-org.github.io/). O cabeçalho do arquivo de configuração traz as categorias disponíveis.

### O que cada entrada leva

```
#EXTINF:-1 tvg-id="GloboNews.br@SD" tvg-name="GloboNews" tvg-logo="https://..." group-title="Favoritos",GloboNews
http://.../stream.m3u8
```

- `tvg-id`: ID do canal no iptv-org (+ `@feed`, igual às listas oficiais), usado para casar com o EPG.
- `tvg-logo`: melhor logo disponível (prefere PNG/JPEG, que as TVs desenham melhor que SVG).
- `group-title`: categoria traduzida (editável em `[group_names]`) ou país.

### Garantias da saída

- Começa com `#EXTM3U`; cada `#EXTINF` é seguido de uma URL `http(s)`.
- Sem URLs duplicadas, sem aspas/vírgulas/quebras de linha que quebrem o `#EXTINF`.
- Se a playlist gerada for inválida, o build falha (código ≠ 0) e o arquivo não é gravado.
- Para cada canal fica o stream de **maior qualidade**; com `--check`, o melhor entre os que **responderam**.

## EPG, publicação e IBO Player

- Programação (guia): [docs/EPG.md](docs/EPG.md)
- Publicar a URL e cadastrar no IBO Player: [docs/PUBLICACAO.md](docs/PUBLICACAO.md)

## Limitações

- Streams públicos são instáveis; a taxa de canais que funcionam varia. `--check` reduz, mas não elimina, links ruins (um link pode responder para o servidor do GitHub e falhar na sua casa por geoblock).
- O guia (EPG) cobre só parte dos canais (o relatório mostra, ex.: `73/266`).
- Os dados da API são do iptv-org; correções de nome, logo ou link devem ser sugeridas lá.

