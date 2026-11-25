# Guia de EPG (programação dos canais)

O EPG é um arquivo XMLTV (`guide.xml`) que traz a programação. Para funcionar, o `id` de cada canal no XML precisa ser igual ao `tvg-id` da playlist. Aqui os dois vêm do iptv-org (ex.: `GloboNews.br`), então combinam.

## O que o projeto faz e o que não faz

| Faz | Não faz |
|---|---|
| Mantém o `tvg-id` compatível com o iptv-org/epg | Não baixa/gera a programação em si |
| Coloca sua URL de EPG no cabeçalho `x-tvg-url` | Não hospeda o `guide.xml` |
| Informa quantos canais da lista têm guia disponível | |
| Gera `<playlist>.channels.xml` pronto para o grabber | |

O repositório [iptv-org/epg](https://github.com/iptv-org/epg) é um **grabber**: ele coleta a programação de sites de TV e gera o XML. Ele não entrega um arquivo pronto, então você precisa gerar e hospedar o seu (ou usar um guia público de terceiros).

## Opção A: usar um XMLTV já hospedado por alguém

Cole a URL em `config/playlists.toml`:

```toml
[epg]
url = "https://exemplo.com/guide.xml"
```

Confira se o guia usa os mesmos IDs (iptv-org). Guias com outros IDs não vão casar.

## Opção B: gerar o seu próprio guia com o iptv-org/epg

Requer Node.js 18+. O processo é lento (minutos a horas, dependendo do nº de canais), por isso gere só os canais das suas playlists.

1. Gere as playlists: `python -m iptv_builder build`. Saem `public/brasil.channels.xml` etc.
2. Clone o grabber e instale:
   ```bash
   git clone --depth 1 https://github.com/iptv-org/epg.git
   cd epg
   npm install
   ```
3. Rode com o seu `channels.xml`:
   ```bash
   npm run grab -- --channels=../public/brasil.channels.xml --output=../public/guide.xml --maxConnections=10
   ```
4. Publique `guide.xml` junto com as playlists (ele cai em `public/`, que o GitHub Pages já serve) e aponte a URL:
   ```toml
   [epg]
   url = "https://SEU_USUARIO.github.io/SEU_REPO/guide.xml"
   ```

> [!NOTE]
> O `channels.xml` usa 1 site de guia por canal. Para escolher quais sites têm prioridade, use `preferred_sites` em `[epg]`. Alguns sites do grabber exigem configuração extra; veja o README do iptv-org/epg.

Para automatizar, crie um segundo job no workflow que roda o grabber (use `actions/setup-node`) antes do `upload-pages-artifact`. Como é pesado, rode-o uma vez por dia, não a cada 6 horas.

