# Por que links do YouTube / YouTube Music baixam a música errada

> **Atualização (v1.2.0):** links do YouTube não passam mais pelo spotdl. O yt-dlp
> baixa o próprio vídeo — ver [docs/adr/0003](adr/0003-ytdlp-oficial-baixa-o-audio.md).
> A análise abaixo continua valendo para o comportamento do spotdl em si.

> **Onde este arquivo está:** coloquei esta nota em `docs/` porque o repositório
> não tem uma pasta dedicada a pesquisa/notas (só existe `docs/adr/` para ADRs).
> Não é um ADR — é uma investigação de bug — então ficou solto em `docs/`.

> **Versão investigada:** spotdl **v4.5.2** (release mais recente em 2026-07-24,
> publicado em 2026-07-20). O `preparo.py` do BaixarMusica sempre busca o
> *latest release* pela API do GitHub (`escolher_asset` pega o asset `win32.exe`),
> então esta é a versão que o app instala hoje. Todas as citações de código abaixo
> apontam para a tag `v4.5.2`. Ver a seção "Diferença por versão" no fim.

---

## Resposta em uma frase (linguagem simples)

Quando você cola um link **puro do YouTube** (`youtube.com/watch?v=...` ou
`youtu.be/...`), o spotdl **não** baixa o áudio daquele vídeo: ele trata a URL
inteira como se fosse um **texto de busca**, joga esse texto na busca do Spotify,
pega o **primeiro resultado que aparecer** e baixa aquilo — por isso vem outra
música. Já um link do **Spotify** funciona porque o spotdl lê os metadados reais
da faixa direto na API do Spotify (título, artista, ISRC) e usa isso para achar o
áudio certo. Links do **YouTube Music** (`music.youtube.com/watch?v=...`) são um
caso intermediário: o áudio até fica preso ao vídeo certo, mas o **nome/artista do
arquivo** vêm de uma busca no Spotify pelo título do vídeo, então o arquivo pode
sair **com o nome de outra música** (e, sem `--ytm-data`, com tags trocadas).

---

## O mecanismo confirmado (com citações ao código-fonte)

Todo o roteamento de query acontece em `spotdl/utils/search.py`, na função
**`get_simple_songs`** — um grande `if/elif/.../else` que decide o que fazer com
cada string que você passa. A ordem dos ramos importa.

Permalink da função:
<https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L119-L363>

### 1. Link do Spotify → metadados reais (funciona)

```python
elif "open.spotify.com" in request and "track" in request:
    songs.append(Song.from_url(url=request))
```
`spotdl/utils/search.py`, `get_simple_songs`, linhas 258-259:
<https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L258-L259>

`Song.from_url` chama a API do Spotify e monta a faixa com título, artista, álbum,
duração e **ISRC** verdadeiros (`spotdl/types/song.py`, linhas 65-138):
<https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/types/song.py#L65-L138>

Com metadados exatos (principalmente o ISRC), o provedor de áudio consegue achar o
vídeo correto no YouTube Music. Por isso Spotify "sempre acerta".

### 2. Link puro do YouTube (`youtube.com/watch`, `youtu.be`) → busca de texto (erra)

Uma URL como `https://www.youtube.com/watch?v=XXXX` **não bate** com nenhum dos
ramos anteriores:

- o ramo do "pipe" exige, ao mesmo tempo, `open.spotify.com` + `track` + `|`
  no texto (linhas 145-173);
- o ramo de YouTube Music exige literalmente `music.youtube.com/watch?v`
  (linha 174);
- o ramo de playlist exige `youtube.com/playlist?list=` (linha 197).

Não casando com nada, a URL cai no **`else` final**:

```python
else:
    songs.append(Song.from_search_term(request))
```
`spotdl/utils/search.py`, `get_simple_songs`, linhas 300-301:
<https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L300-L301>

Aqui está o bug: `request` é a **string da URL inteira**. `Song.from_search_term`
joga esse texto na busca do Spotify e pega o **primeiro item** (`items[0]`):

```python
raw_search_results = Song.search(search_term)   # spotify_client.search(<a URL>)
...
return Song.from_url(
    "http://open.spotify.com/track/"
    + raw_search_results["tracks"]["items"][0]["id"]
)
```
`spotdl/types/song.py`, `Song.from_search_term`, linhas 159-179:
<https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/types/song.py#L159-L179>

Ou seja: o app manda `youtube.com/watch?v=...`, o spotdl pesquisa esse texto no
Spotify e baixa **seja lá qual for a primeira faixa** que a busca devolver. O
`download_url` **nunca é fixado** no vídeo original — fica `None`. Confirmação no
downloader: só existe re-busca quando `download_url is None`:

```python
if song.download_url is None:
    download_url = await loop.run_in_executor(None, self.search, song)
else:
    download_url = song.download_url
```
`spotdl/download/downloader.py`, linhas 708-712:
<https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/download/downloader.py#L708-L712>

Como o link puro do YouTube deixou `download_url = None`, o downloader roda
`self.search(song)`, que pergunta aos provedores de áudio (YouTube Music/YouTube)
qual vídeo casa com aquela faixa (a errada, vinda do `items[0]`) —
`spotdl/download/downloader.py`, linhas 378-396:
<https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/download/downloader.py#L378-L396>

**Resultado: baixa outra música.** Esse é o caso que explica exatamente o sintoma
relatado para links puros do YouTube.

### 3. Link do YouTube Music (`music.youtube.com/watch?v=...`) → áudio certo, rótulo pode sair errado

```python
elif "music.youtube.com/watch?v" in request:
    track_data = get_ytm_client().get_song(request.split("?v=", 1)[1])
    video_details = track_data.get("videoDetails")
    ...
    yt_song = Song.from_search_term(
        f"{video_details['author']} - {video_details['title']}"
    )
    if use_ytm_data:
        yt_song.name = video_details["title"]
        yt_song.artist = video_details["author"]
        yt_song.artists = [video_details["author"]]
        yt_song.duration = int(video_details["lengthSeconds"])
    yt_song.download_url = request
    songs.append(yt_song)
```
`spotdl/utils/search.py`, `get_simple_songs`, linhas 174-196:
<https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L174-L196>

Dois pontos importantes:

- **O áudio fica correto.** `yt_song.download_url = request` fixa o download no
  vídeo real, e o downloader respeita isso (linhas 708-712 acima), então **não há
  re-matching do áudio**.
- **Os metadados (nome/artista/álbum) NÃO vêm do vídeo por padrão.** Eles vêm de
  `Song.from_search_term("<autor> - <título>")`, ou seja, do **primeiro resultado
  de uma busca no Spotify** por aquele texto. Como o modelo de saída do app é
  `"{artists} - {title}"`, o arquivo pode ser **nomeado (e etiquetado) como outra
  música**, mesmo contendo o áudio certo. Só com `--ytm-data` (`use_ytm_data=True`)
  o spotdl usa título/artista/duração do próprio vídeo.

> **Observação honesta sobre o relato do usuário:** para links puros do YouTube o
> erro é inequívoco (áudio errado — item 2). Para `music.youtube.com`, o
> código-fonte mostra que o **áudio** fica preso ao vídeo certo; o que muda é o
> **nome/tags** do arquivo. É bem provável que (a) parte dos links relatados como
> "music.youtube" sejam na verdade `youtube.com`/`youtu.be` (o botão Compartilhar
> do YouTube gera `youtu.be`, não `music.youtube.com`), ou (b) o arquivo esteja
> saindo com o nome de outra faixa por causa da busca no Spotify. Sem as URLs
> exatas que ele colou não dá para afirmar qual dos dois; ambos são explicados
> pelo código acima.

### Como a query vira Song (visão geral)

`parse_query` chama `get_simple_songs` e depois roda `reinit_song` em cada faixa
(`spotdl/utils/search.py`, linhas 79-116 e 545-578). O `reinit_song` só re-busca
metadados a partir do `url` (Spotify) ou do `song_id`; ele **preserva** o
`download_url` já definido, então o pin do YouTube Music sobrevive.
<https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L545-L578>

---

## A sintaxe `YouTubeURL|SpotifyURL` (o "pipe")

O spotdl documenta e implementa um formato de **matching forçado**: você passa as
duas URLs juntas, separadas por `|`, entre aspas.

```python
if (("watch?v=" in request or "youtu.be/" in request
     or "soundcloud.com/" in request or "bandcamp.com/" in request)
    and "open.spotify.com" in request and "track" in request and "|" in request):
    split_urls = request.split("|")
    ...
    songs.append(
        Song.from_missing_data(url=split_urls[1], download_url=split_urls[0])
    )
```
`spotdl/utils/search.py`, `get_simple_songs`, linhas 145-173:
<https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L145-L173>

**O que ele resolve:** fixa o `download_url` no **áudio exato do YouTube**
(`split_urls[0]`) e tira os **metadados do Spotify** (`split_urls[1]`). É a
combinação perfeita — áudio que você escolheu + tags limpas do Spotify — e é
justamente a solução oficial para "o matching automático pegou o vídeo errado".

Documentação oficial (`docs/usage.md`): *"For manual audio matching, you can use
the format 'YouTubeURL|SpotifyURL'"* e *"You can only use album/playlist/tracks
urls when downloading/matching youtube urls."*
<https://github.com/spotDL/spotify-downloader/blob/v4.5.2/docs/usage.md>

**Limitação para este app:** exige que o usuário forneça **também** uma URL do
Spotify para cada faixa. Não dá para automatizar a partir de um único link do
YouTube. Serve como opção "avançada", não como conserto transparente da GUI.

---

## Flags que mudam (ou não) o comportamento de matching

Todas confirmadas em `spotdl/utils/arguments.py` (v4.5.2):

- **`--ytm-data`** — *"Use ytm data instead of spotify data when downloading using
  ytm link."* (linhas 510-515). Faz o ramo do `music.youtube.com` usar
  título/artista/duração **do próprio vídeo** como metadado. Ligado a
  `use_ytm_data` via `downloader.settings["ytm_data"]`
  (`spotdl/console/download.py`, linhas 25-32).
  <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/arguments.py#L510-L515>
  <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/console/download.py#L25-L32>
  **Só afeta links `music.youtube.com` (e playlists YTM).** Não toca no ramo
  `else` — logo, **não conserta** links puros `youtube.com`/`youtu.be`.
- **`--audio youtube-music|youtube|...`** (linhas 110-116). Escolhe/ordena os
  provedores usados na etapa de **re-matching**. Isso só entra em cena quando
  `download_url is None`, ou seja, quando o spotdl já está procurando um áudio a
  partir de metadados. Trocar `youtube-music` por `youtube` muda **onde** ele
  procura, não conserta o fato de que, para um link puro do YouTube, os metadados
  de partida já estão errados.
  <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/arguments.py#L108-L116>
- **`--dont-filter-results`** (linhas 156-162) e **`--only-verified-results`**
  (linhas 173-178). Ajustam a **filtragem/ordenação** dos resultados na etapa de
  matching de áudio (downstream). Não fixam `download_url`; para o link puro do
  YouTube o problema é upstream, então não resolvem.
  <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/arguments.py#L155-L178>
- **`--album-type`** (linhas 166-170). Filtra faixas por tipo de álbum. Irrelevante
  para o problema.

---

## Baixar EXATAMENTE o áudio de uma URL do YouTube, sem re-matching

Três caminhos, todos apoiados no código/docs acima:

1. **Reescrever o link para `music.youtube.com/watch?v=<id>`** antes de passar ao
   spotdl. Isso rota o link pelo ramo do item 3, que **fixa `download_url` no vídeo
   real**. É a forma de "pinar o áudio" sem exigir URL do Spotify.
2. **Sintaxe pipe `YouTubeURL|SpotifyURL`** (item acima) — pin perfeito, mas exige
   a URL do Spotify.
3. **yt-dlp direto** — o próprio spotdl usa yt-dlp por baixo. Para "baixe exatamente
   este vídeo", `yt-dlp -x --audio-format mp3 <url>` garante o áudio, mas você
   perde a nomeação/tags `{artists} - {title}` do spotdl (teria que montar isso à
   mão). Mudança grande demais para este app.

---

## Opções de conserto, ranqueadas (ancoradas no comando atual do app)

O `_worker` de `app.py` hoje monta:

```
spotdl download <link> --format mp3 --bitrate 320k \
  --output "<destino>/<subpasta>/{artists} - {title}.{output-ext}" \
  --ffmpeg <ffmpeg> --simple-tui
```

### Opção 1 (RECOMENDADA) — reescrever link do YouTube para `music.youtube.com` + `--ytm-data`

No app, antes de montar o comando, normalize o link:

- `https://www.youtube.com/watch?v=ID&...` → `https://music.youtube.com/watch?v=ID`
- `https://youtu.be/ID?...` → `https://music.youtube.com/watch?v=ID`
- extraia **só o id de 11 caracteres** do vídeo (importante: o ramo YTM faz
  `request.split("?v=", 1)[1]` e passa isso ao `ytmusicapi.get_song`; parâmetros
  extras como `&list=...` ou `&t=...` quebram a busca — ver
  `spotdl/utils/search.py#L174-L175`).

E adicione `--ytm-data` ao comando. O `_worker` passaria a rodar, para um link do
YouTube:

```
spotdl download "https://music.youtube.com/watch?v=ID" --format mp3 --bitrate 320k \
  --ytm-data \
  --output "<destino>/<subpasta>/{artists} - {title}.{output-ext}" \
  --ffmpeg <ffmpeg> --simple-tui
```

- **Por que funciona:** o ramo `music.youtube.com` fixa `download_url` no vídeo
  (áudio certo garantido), e `--ytm-data` faz o nome/artista/duração virem do
  próprio vídeo — então o arquivo sai com o nome certo.
- **`--ytm-data` pode ficar sempre ligado:** ele só é lido nos ramos de YouTube
  Music/playlist YTM; para links do Spotify é inócuo (aqueles ramos não olham
  `use_ytm_data`). Ainda assim, para manter os metadados do Spotify ricos nos
  links do Spotify, o mais limpo é adicionar `--ytm-data` **apenas** quando o link
  for de vídeo do YouTube.
- **Trade-offs:** os metadados vêm do YouTube (o "artista" costuma ser o nome do
  canal; o título pode conter "(Official Video)", "(Lyrics)" etc.); não há capa de
  álbum/tag de álbum tão limpas quanto as do Spotify. Precisa de rede para o
  `ytmusicapi.get_song`. Se o vídeo não existir no YouTube Music, o link falha.
  Em troca: **baixa a música certa.**

### Opção 2 — expor a sintaxe pipe `YouTubeURL|SpotifyURL`

Deixar o usuário colar `urlYouTube|urlSpotify`. O app já repassa o `link` cru ao
spotdl, então tecnicamente **já funciona hoje** se o usuário souber o formato —
basta documentar/instruir na UI. Pin de áudio perfeito + metadados limpos do
Spotify.
- **Trade-off:** exige que o usuário tenha e cole também o link do Spotify de cada
  faixa. UX ruim para o público-alvo (leigo) deste app; melhor como recurso
  opcional/documentado, não como padrão.

### Opção 3 — yt-dlp direto para links de vídeo do YouTube

Garante o áudio exato, mas abandona a nomeação/tags do spotdl e adiciona um
segundo binário/fluxo. **Não recomendado** aqui: contraria a arquitetura atual
(app é um wrapper fino de spotdl — ver `docs/adr/0001`).

---

## O que NÃO conserta

- **Trocar `--audio youtube` por `--audio youtube-music`** (ou vice-versa): só muda
  o provedor da re-busca; o link puro do YouTube continua entrando pelo `else` como
  texto e partindo de metadados errados.
- **`--dont-filter-results` / `--only-verified-results`**: mexem na filtragem
  downstream do matching; não fixam o `download_url` do vídeo que o usuário colou.
- **`--ytm-data` sozinho, sem reescrever o link**: não tem efeito em links puros
  `youtube.com`/`youtu.be` (eles nunca chegam ao ramo YTM). Só ajuda se o link já
  for `music.youtube.com`.
- **`--bitrate` / `--format` / `--album-type`**: não têm relação com a escolha da
  faixa.
- **Continuar mandando a URL crua do YouTube como está hoje**: é exatamente o que
  dispara o bug.

---

## Diferença por versão

O app instala sempre o *latest*. O roteamento de query descrito aqui (o `else` que
vira busca de texto, o ramo `music.youtube.com` com `--ytm-data`, e a sintaxe pipe)
faz parte do design do spotdl v4 há bastante tempo e está presente em `v4.5.2`
(citações acima, todas na tag). Se um dia o `preparo.py` instalar uma versão
diferente, vale reconferir `spotdl/utils/search.py::get_simple_songs` na tag
correspondente antes de confiar nas linhas citadas — os números de linha podem
mudar, mas a lógica dos ramos tem sido estável.

---

## Fontes

Todas em fonte primária (código-fonte do spotdl na tag `v4.5.2`, docs oficiais do
spotdl e API do GitHub):

- get_simple_songs (roteamento de query): <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L119-L363>
- Ramo pipe `YouTubeURL|SpotifyURL`: <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L145-L173>
- Ramo `music.youtube.com`: <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L174-L196>
- Ramo `open.spotify.com` track: <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L258-L259>
- `else` final (busca de texto): <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L300-L301>
- parse_query / reinit_song: <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L79-L116> e <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/search.py#L545-L578>
- Song.from_url (metadados do Spotify): <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/types/song.py#L65-L138>
- Song.from_search_term (pega `items[0]`): <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/types/song.py#L159-L179>
- Downloader: só re-busca se `download_url is None`: <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/download/downloader.py#L708-L712>
- Downloader.search (re-matching por provedor): <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/download/downloader.py#L378-L396>
- console/download.py (`ytm_data` → `use_ytm_data`): <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/console/download.py#L25-L32>
- Flags `--audio`, `--dont-filter-results`, `--album-type`, `--only-verified-results`, `--ytm-data`: <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/arguments.py#L108-L178> e <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/spotdl/utils/arguments.py#L510-L515>
- Documentação oficial (uso, sintaxe pipe, `--ytm-data`): <https://github.com/spotDL/spotify-downloader/blob/v4.5.2/docs/usage.md>
- Release mais recente instalado pelo app: <https://api.github.com/repos/spotDL/spotify-downloader/releases/latest> (v4.5.2, 2026-07-20)
