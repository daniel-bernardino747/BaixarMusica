"""Do link ao mp3: quem acha a musica, quem baixa o audio, onde o arquivo cai.

O spotdl continua sendo quem *entende* o link -- le a playlist do Spotify, acha
o video certo no YouTube Music, traz titulo, artista, album e capa. Mas quem
baixa o audio e o yt-dlp oficial, atualizado a cada abertura. O yt-dlp que vai
congelado dentro do spotdl envelhece entre um release e outro deles, e o YouTube
passa a recusar os downloads com HTTP 403. Ver docs/adr/0003.

Links do YouTube nem passam pelo spotdl: o yt-dlp le o proprio video, entao o
audio e o nome sao os do link que a pessoa mandou.
"""

import json
import re
from pathlib import Path

from mutagen.id3 import (APIC, ID3, TALB, TDRC, TIT2, TPE1, TPE2, TPOS, TPUB,
                         TRCK, ID3NoHeaderError)

# Hosts do YouTube (cobre www./m./music.youtube.com e o encurtado youtu.be).
YT_HOSTS = ("youtube.com", "youtu.be")
# O id de 11 caracteres de um video, em qualquer forma de link do YouTube.
YT_VIDEO_ID = re.compile(r"(?:youtu\.be/|/shorts/|/embed/|[?&]v=)([\w-]{11})",
                         re.IGNORECASE)

# De onde sai o nome da subpasta de cada tipo de colecao, no .spotdl.
CAMPO_DA_COLECAO = {
    "playlist": "list_name",
    "album": "album_name",
    "artist": "artist",
}

# Letras que o Windows nao aceita em nome de arquivo, e caracteres de controle.
PROIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# "Artista - Titulo (Official Video)" -> "Titulo", com "Artista" nas tags.
# Sem isso o arquivo de um clipe sai "Canal - Canal - Titulo (Official Video).mp3".
YT_ARTISTA_NO_TITULO = r"title:(?P<artist>.+?) - (?P<title>.+)"
YT_SUFIXOS = (r"(?i)\s*[\[(](?:official|oficial|clipe|lyric|letra|video|v[ií]deo|"
              r"audio|[áa]udio|visualizer|hd|4k)[^\])]*[\])]")

MP3 = ["-x", "--audio-format", "mp3", "--audio-quality", "320K"]


# ----------------------------------------------------------------- rota

def e_do_youtube(link):
    """Link que o yt-dlp baixa sozinho, sem o spotdl no meio.

    A sintaxe pipe do spotdl (`youtube|spotify`) fica com o spotdl: e justamente
    o pedido de "audio deste video com os metadados daquela faixa".
    """
    baixo = link.lower()
    return (any(host in baixo for host in YT_HOSTS)
            and "open.spotify.com" not in baixo)


def fonte_youtube(link):
    """Normaliza o link do YouTube. Retorna (url, e_colecao).

    Um video vira music.youtube.com/watch?v=<id>: o &list= que vem junto quando se
    copia de dentro de uma playlist faria o yt-dlp baixar a playlist inteira, e o
    YouTube Music traz artista e titulo separados quando o video e uma musica.
    Sem id de video, o link e uma colecao (playlist, album) e passa intacto.
    """
    match = YT_VIDEO_ID.search(link)
    if not match:
        return link, True
    return f"https://music.youtube.com/watch?v={match.group(1)}", False


def tipo_de_colecao(link):
    """'playlist', 'album' ou 'artist' num link do Spotify; None se for avulsa."""
    match = re.search(r"[:/](playlist|album|artist)[:/]", link, re.IGNORECASE)
    return match.group(1).lower() if match else None


# ------------------------------------------------------------- comandos

def _escapar(caminho):
    """O -o do yt-dlp e um template: um % no nome de uma musica viraria campo."""
    return str(caminho).replace("%", "%%")


def comando_base(ytdlp, ffmpeg, deno):
    """O que todo yt-dlp chamado aqui leva.

    --ignore-config: um yt-dlp.conf na maquina de alguem mudaria o comportamento.
    --ffmpeg-location explicito pelo mesmo motivo do ADR 0002.
    """
    comando = [str(ytdlp), "--ignore-config", "--no-progress",
               "--ffmpeg-location", str(ffmpeg)]
    if deno:
        comando += ["--js-runtimes", f"deno:{deno}"]
    return comando


def comando_youtube(base, url, destino, e_colecao):
    """Baixa um video (ou uma playlist) do YouTube com os metadados dele mesmo."""
    pasta = Path(destino)
    if e_colecao:
        pasta = pasta / "%(playlist_title)s"
    nome = "%(artist,creator,uploader)s - %(track,title)s.%(ext)s"
    return [
        *base, url, *MP3,
        "--parse-metadata", YT_ARTISTA_NO_TITULO,
        "--replace-in-metadata", "title,track", YT_SUFIXOS, "",
        "--embed-metadata", "--embed-thumbnail",
        "--ignore-errors",  # um video privado nao derruba a playlist inteira
        "--print", "after_move:Baixado: %(filepath)s",
        "-o", _escapar(pasta) + "/" + nome,
    ]


def comando_audio(base, url, arquivo):
    """Baixa so o audio de `url` para `arquivo`. As tags vem depois, de etiquetar()."""
    sem_extensao = Path(arquivo).with_suffix("")
    return [*base, url, *MP3, "--no-playlist", "--quiet",
            "-o", _escapar(sem_extensao) + ".%(ext)s"]


def comando_lista(spotdl, link, arquivo_lista):
    """Pede ao spotdl so a lista: metadados e o link do audio de cada faixa.

    --preload e o que faz ele procurar o video de cada faixa agora, sem baixar.
    """
    return [str(spotdl), "save", link, "--save-file", str(arquivo_lista),
            "--preload", "--simple-tui"]


# ---------------------------------------------------------- lista e nomes

def ler_lista(arquivo_lista):
    return json.loads(Path(arquivo_lista).read_text(encoding="utf-8"))


def limpar(nome):
    """Nome utilizavel como arquivo no Windows. Ponto e espaco no fim somem."""
    return PROIBIDOS.sub("", nome).strip().rstrip(". ") or "sem nome"


def artistas(musica):
    return ", ".join(musica.get("artists") or [musica.get("artist") or "?"])


def caminho_da_faixa(destino, link, musica):
    """Onde a faixa cai: `{artistas} - {titulo}.mp3`, numa subpasta se for colecao.

    O formato e o mesmo que o spotdl usava sozinho, entao o que ja foi baixado
    nas versoes anteriores e reconhecido como existente e nao baixa de novo.
    """
    pasta = Path(destino)
    tipo = tipo_de_colecao(link)
    if tipo:
        pasta = pasta / limpar(musica.get(CAMPO_DA_COLECAO[tipo]) or "")
    return pasta / f"{limpar(artistas(musica) + ' - ' + musica['name'])}.mp3"


# ----------------------------------------------------------------- tags

def etiquetar(arquivo, musica, capa=None):
    """Grava as tags ID3 que o spotdl gravaria. `capa` sao os bytes do jpeg."""
    try:
        tags = ID3(arquivo)
    except ID3NoHeaderError:
        tags = ID3()

    tags.add(TIT2(encoding=3, text=musica["name"]))
    tags.add(TPE1(encoding=3, text=artistas(musica)))
    if musica.get("album_name"):
        tags.add(TALB(encoding=3, text=musica["album_name"]))
    if musica.get("album_artist"):
        tags.add(TPE2(encoding=3, text=musica["album_artist"]))
    if musica.get("track_number"):
        total = musica.get("tracks_count")
        numero = f"{musica['track_number']}/{total}" if total else str(musica["track_number"])
        tags.add(TRCK(encoding=3, text=numero))
    if musica.get("disc_number"):
        tags.add(TPOS(encoding=3, text=str(musica["disc_number"])))
    if musica.get("date") or musica.get("year"):
        tags.add(TDRC(encoding=3, text=str(musica.get("date") or musica["year"])))
    if musica.get("publisher"):
        tags.add(TPUB(encoding=3, text=musica["publisher"]))
    if capa:
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=capa))

    tags.save(arquivo, v2_version=3)
