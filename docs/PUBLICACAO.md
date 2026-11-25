# Publicar a URL e cadastrar no IBO Player

## Parte 1 — Publicar no GitHub Pages

1. Crie uma conta no [GitHub](https://github.com) e um repositório **público** (ex.: `minha-iptv`). O Pages grátis exige repositório público.
2. Envie o projeto:
   ```bash
   git init
   git add .
   git commit -m "Projeto inicial"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/minha-iptv.git
   git push -u origin main
   ```
3. No GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
4. Aba **Actions**: o workflow *Atualizar playlists e publicar* roda sozinho no push. Para rodar na hora, clique em **Run workflow**. Depois disso ele roda a cada 6 horas.
5. Quando ficar verde, as listas estarão em:
   ```
   https://SEU_USUARIO.github.io/minha-iptv/brasil.m3u
   https://SEU_USUARIO.github.io/minha-iptv/portugues.m3u
   https://SEU_USUARIO.github.io/minha-iptv/noticias_mundo.m3u
   ```
   A página `https://SEU_USUARIO.github.io/minha-iptv/` lista os links e mostra o status de cada playlist (`report.json` traz contagens e motivos de descarte).
6. Abra o link no navegador do celular: deve baixar/mostrar texto começando com `#EXTM3U`.

### Alternativa sem Pages (link "raw")
Remova `public/` do `.gitignore`, rode `python -m iptv_builder build --check` localmente, faça commit de `public/` e use:
`https://raw.githubusercontent.com/SEU_USUARIO/minha-iptv/main/public/brasil.m3u`
Aqui a atualização é manual (você precisa rodar o script e dar push).

## Parte 2 — Cadastrar no IBO Player

O IBO Player é cadastrado pelo site, não pela TV. Os nomes dos botões podem mudar entre versões do app (IBO Player, IBO Player Pro, IBO Pro).

1. Instale o IBO Player na TV e abra. A tela inicial mostra **MAC Address** e **Device Key**.
2. No computador ou celular, acesse o site oficial do app (`iboplayer.com`), entre em **Manage Playlists** e faça login com o MAC e a Device Key.
3. Em **Manage Playlists**, clique em **Add Playlist** (o botão **Add XC Playlist** é só para Xtream Codes; não use) e preencha:
   - **Playlist name:** `Brasil` (qualquer nome)
   - **Playlist URL (.M3U or .M3u8):** `https://SEU_USUARIO.github.io/minha-iptv/brasil.m3u`
   - **XMLTV EPG URL (Optional):** sua URL de `guide.xml`, ou deixe vazio.
   - **Protect this playlist:** opcional (pede o Parent PIN para ver ou alterar a lista).
4. Clique em **SAVE**, volte para a TV e reabra o app ou atualize a lista.

> [!IMPORTANT]
> - O IBO Player tem período de teste e depois exige licença paga **do aplicativo**. Isso é cobrado pelo app, não tem relação com este projeto.
> - Alguns guias de terceiros recomendam usar `http://` em vez de `https://`. O GitHub Pages força HTTPS, então teste primeiro com `https`. Se o app recusar a lista, hospede em outro lugar que aceite `http` (ex.: um servidor seu) ou escolha outro player. Não consegui confirmar esse comportamento no app; teste na sua TV.
> - O IBO Player não é de código aberto e sua interface muda. Se algum campo for diferente, o essencial é: tipo **M3U URL** + a URL da playlist.

## Solução de problemas

| Sintoma | O que fazer |
|---|---|
| Lista carrega, mas vários canais não tocam | Normal em streams públicos. Ative `[check] enabled = true` (o workflow já usa `--check`). |
| Canal específico não toca | Pode estar com geoblock só para você. Adicione o ID em `exclude_channels`. |
| Logo ou nome errado | Os dados vêm do iptv-org/database; sugira correção no [repositório](https://github.com/iptv-org/database). |
| Lista vazia | Veja `report.json` → `descartados`; filtros muito restritivos. |
| Actions falhou no Pages | Confirme **Settings → Pages → Source: GitHub Actions** e repositório público. |

