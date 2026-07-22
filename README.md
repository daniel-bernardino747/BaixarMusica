# BaixarMusica

GUI mínima sobre o [spotdl](https://github.com/spotDL/spotify-downloader): escolha uma
pasta, cole um link, clique em **Baixar**.

Não precisa instalar Python, nem spotdl, nem ffmpeg. Um arquivo, duplo-clique.

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
enquanto ele busca os componentes que faltam (**~72 MB**, uma vez só). O log mostra o
progresso. Escolha a pasta e cole o link enquanto isso — o botão libera sozinho.

Se a conexão cair no meio, ele tenta de novo sozinho três vezes antes de desistir. Se
desistir, o botão vira **Tentar de novo**. Em máquina incompatível ele vira
**Indisponível** — porque insistir não ia adiantar.

Da segunda vez em diante a abertura é instantânea.

## Usar

O campo **Link** aceita qualquer coisa que o spotdl entenda:

| Entrada | Resultado |
|---|---|
| `https://open.spotify.com/playlist/...` | subpasta com o nome da playlist |
| `https://open.spotify.com/album/...` | subpasta com o nome do álbum |
| `https://open.spotify.com/artist/...` | subpasta com o nome do artista |
| `https://open.spotify.com/track/...` | arquivo solto na raiz |
| `https://youtube.com/watch?v=...` | arquivo solto na raiz |
| `bohemian rhapsody queen` | busca por texto, arquivo solto na raiz |

Tudo sai em **mp3 320k**, nomeado `{artistas} - {título}.mp3`. A última pasta usada fica
guardada em `%APPDATA%\BaixarMusica\config.json`.

Durante o download o botão vira **Cancelar**, que derruba o spotdl e o ffmpeg junto.
A tecla Enter no campo de link **só inicia** download — nunca cancela.

## Verificar duplicados

O spotdl já pula um arquivo que existe no mesmo caminho (`--overwrite skip`). O que
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

O `.exe` tem ~11 MB e não carrega o spotdl nem o ffmpeg dentro de si. Eles ficam em
`%APPDATA%\BaixarMusica\`:

| Arquivo | Tamanho | Origem |
|---|---|---|
| `spotdl.exe` | 46 MB | binário oficial do projeto spotDL, atualizado sozinho |
| `ffmpeg.exe` | 76 MB | `eugeneware/ffmpeg-static` b4.4, baixado comprimido (26 MB) |
| `spotdl.exe.anterior` | 46 MB | versão anterior, para reverter se a nova nascer quebrada |

Toda abertura o programa checa se saiu uma versão nova do spotdl e atualiza. O download
é conferido por SHA256 e só substitui o binário bom depois de passar. Se o novo não
executar, o anterior volta sozinho.

**Sem internet o programa continua funcionando** com o que já está em disco — a checagem
nunca bloqueia a abertura. O porquê de tudo isso está em
[docs/adr/0001](docs/adr/0001-spotdl-como-componente-externo.md) e
[docs/adr/0002](docs/adr/0002-baixamos-o-ffmpeg-nos-mesmos.md).

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
- **O spotdl carrega uma cópia congelada do yt-dlp.** Quando o YouTube muda, o conserto
  depende de o spotdl lançar uma versão nova — e eles já passaram sete meses sem lançar
  (out/2025 a abr/2026). Nessas janelas não há nada que este programa possa fazer.
- **Dependemos de o spotDL continuar publicando o build `win32`.**
- O primeiro uso precisa de internet razoável para os 72 MB.
