# BaixarMusica

GUI mínima sobre o [spotdl](https://github.com/spotDL/spotify-downloader) e o
[yt-dlp](https://github.com/yt-dlp/yt-dlp): escolha uma pasta, cole um link, clique em
**Baixar**.

Não precisa instalar Python, nem spotdl, nem yt-dlp, nem ffmpeg. Um arquivo, duplo-clique.

## Instalar

Baixe e abra o `BaixarMusica.exe`. O link tem esta forma:

```
https://github.com/<usuario>/<repo>/releases/latest/download/BaixarMusica.exe
```

Ele aponta **sempre** para a versão mais nova, então mande o link aos amigos em vez do
arquivo — na próxima versão eles não precisam de nada seu.

> Este repositório ainda não tem `remote` no GitHub. O link exato é impresso por
> `build.ps1 -Publicar` depois do primeiro release; veja *Publicar uma versão*.

### O Windows vai reclamar

Na primeira abertura aparece uma tela azul: **"O Windows protegeu o seu PC"**. Clique
em **Mais informações** → **Executar assim mesmo**.

Isso acontece porque o executável não tem assinatura digital, que é um certificado pago
de algumas centenas de dólares por ano. Para um programa que circula entre amigos, o
aviso é o preço. O SHA256 de cada versão está publicado na página do release, se você
quiser conferir que o arquivo é o mesmo que saiu daqui.

### Primeira abertura

O programa abre imediatamente, mas o botão mostra **Preparando...** por alguns minutos
enquanto ele busca os componentes que faltam (**~130 MB**, uma vez só). O log mostra o
progresso. Escolha a pasta e cole o link enquanto isso — o botão libera sozinho.

Se a conexão cair no meio, ele tenta de novo sozinho três vezes antes de desistir. Se
desistir, o botão vira **Tentar de novo**. Em máquina incompatível ele vira
**Indisponível** — porque insistir não ia adiantar.

Da segunda vez em diante a abertura é instantânea.

## Usar

O campo **Link** aceita qualquer coisa que o spotdl entenda, e qualquer link do YouTube:

| Entrada | Resultado |
|---|---|
| `https://open.spotify.com/playlist/...` | subpasta com o nome da playlist |
| `https://open.spotify.com/album/...` | subpasta com o nome do álbum |
| `https://open.spotify.com/artist/...` | subpasta com o nome do artista |
| `https://open.spotify.com/track/...` | arquivo solto na raiz |
| `https://youtube.com/watch?v=...` | arquivo solto na raiz |
| `https://youtube.com/playlist?list=...` | subpasta com o nome da playlist |
| `bohemian rhapsody queen` | busca por texto, arquivo solto na raiz |

Tudo sai em **mp3 320k**, nomeado `{artistas} - {título}.mp3`, com capa e tags.

Por baixo, o link do Spotify ou a busca vão para o spotdl, que monta a lista de faixas
e acha o vídeo de cada uma no YouTube Music. Quem baixa o áudio é o yt-dlp. Links do
YouTube vão direto para o yt-dlp, com o nome e o artista do próprio vídeo. O porquê
está em [docs/adr/0003](docs/adr/0003-ytdlp-oficial-baixa-o-audio.md). A última pasta usada fica
guardada em `%APPDATA%\BaixarMusica\config.json`.

Durante o download o botão vira **Cancelar**, que derruba o yt-dlp e o ffmpeg junto.
A tecla Enter no campo de link **só inicia** download — nunca cancela.

## Verificar duplicados

Uma faixa cujo arquivo já existe no mesmo caminho é pulada. O que
escapa disso é a **mesma música salva com nome diferente**, vinda de outro upload. O
botão **Verificar duplicados** cobre esse caso comparando as tags ID3, não os nomes:

- **Repetidas** — mesmo artista e mesmo título. Lista no log, e pergunta antes de apagar;
  de cada grupo mantém o maior arquivo (melhor qualidade).
- **Possíveis repetidas** — mesmo título, artistas diferentes. Apenas reportadas,
  **nunca apagadas**: podem ser dois intérpretes do mesmo hino, ou uma versão ao vivo.

A varredura é **por pasta**, sem cruzar subpastas — cada pasta de playlist continua
completa e tocável sozinha. Marcadores como "(ao vivo)" e "(remix)" no título não são
ignorados, justamente para não fundir versões diferentes.

## Os componentes

O `.exe` tem ~12 MB e não carrega o spotdl, o yt-dlp, o ffmpeg nem o deno dentro de si.
Eles ficam em
`%APPDATA%\BaixarMusica\`:

| Arquivo | Tamanho | Origem |
|---|---|---|
| `spotdl.exe` | 46 MB | binário oficial do projeto spotDL, atualizado sozinho |
| `yt-dlp.exe` | 17 MB | binário oficial do projeto yt-dlp, atualizado sozinho |
| `deno.exe` | 93 MB | runtime JavaScript que o yt-dlp usa no YouTube; opcional, baixado zipado (40 MB) |
| `ffmpeg.exe` | 76 MB | `eugeneware/ffmpeg-static` b4.4, baixado comprimido (26 MB) |
| `*.exe.anterior` | — | versão anterior, para reverter se a nova nascer quebrada |

Toda abertura o programa checa se saiu uma versão nova do spotdl e do yt-dlp e atualiza. O download
é conferido por SHA256 e só substitui o binário bom depois de passar. Se o novo não
executar, o anterior volta sozinho.

**Sem internet o programa continua funcionando** com o que já está em disco — a checagem
nunca bloqueia a abertura. O porquê de tudo isso está em
[docs/adr/0001](docs/adr/0001-spotdl-como-componente-externo.md),
[docs/adr/0002](docs/adr/0002-baixamos-o-ffmpeg-nos-mesmos.md) e
[docs/adr/0003](docs/adr/0003-ytdlp-oficial-baixa-o-audio.md).

## Desenvolver

```
pip install -r requirements-dev.txt
python -m pytest              # testes do preparo
pythonw app.py                # roda sem rebuildar
```

O `build.ps1` roda os testes antes de empacotar e aborta se algum falhar.

`pythonw app.py` usa **os mesmos componentes** de `%APPDATA%` que a versão distribuída —
não o spotdl do seu `pip`. É proposital: o preparo é a parte frágil, e precisa rodar aqui
e não só na máquina de quem recebe. Para apontar para outro binário:

```
set BAIXARMUSICA_SPOTDL=C:\caminho\para\spotdl.exe
```

Para testar o primeiro uso do zero, apague `%APPDATA%\BaixarMusica\`.

## Publicar uma versão

```
powershell -ExecutionPolicy Bypass -File build.ps1 -Versao 1.1.0 -Publicar
```

Sem `-Publicar` ele só gera `dist\BaixarMusica.exe` e imprime o SHA256. Com, ele cria o
release no GitHub e imprime o link para mandar aos amigos.

O ícone (`icone.ico`) e os metadados de versão não são enfeite: executável sem metadado
nenhum pontua pior nas heurísticas de antivírus. Pelo mesmo motivo o build passa
`--noupx` — binário empacotado com UPX é gatilho clássico de falso positivo.

## Limites conhecidos

- **Windows 64 bits Intel/AMD apenas.** Em outra arquitetura o programa abre e explica no
  log em vez de falhar de forma incompreensível. Não há build para Mac nem Linux.
- **Quando o YouTube muda, o conserto depende do yt-dlp.** Ele costuma lançar em dias, e
  a versão nova chega sozinha na próxima abertura. Antes da v1.2.0 o áudio vinha do
  yt-dlp congelado dentro do spotdl, e aí o programa ficava parado até o spotdl lançar
  versão nova — ver [docs/adr/0003](docs/adr/0003-ytdlp-oficial-baixa-o-audio.md).
- **Dependemos de o spotDL continuar publicando o build `win32`.**
- O primeiro uso precisa de internet razoável para os ~130 MB.
