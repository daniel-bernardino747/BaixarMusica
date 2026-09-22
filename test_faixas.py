"""Testes do caminho do link ao mp3: quem baixa, com que comando, para onde.

Dois bugs relatados guiam isto: link de video do YouTube baixava outra musica
(docs/pesquisa-links-youtube-baixam-musica-errada.md), e depois o yt-dlp congelado
dentro do spotdl passou a levar HTTP 403 do YouTube (docs/adr/0003).
"""

from pathlib import Path

import pytest
from mutagen.id3 import ID3

import faixas


# ------------------------------------------------------------------ rota

@pytest.mark.parametrize("link", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ?si=abc",
    "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/playlist?list=PLxxxxxxxx",
])
def test_youtube_vai_direto_para_o_ytdlp(link):
    assert faixas.e_do_youtube(link)


@pytest.mark.parametrize("link", [
    "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
    "Rick Astley - Never Gonna Give You Up",
    # Sintaxe pipe: e o spotdl quem entende "audio daqui, metadados dali".
    "https://youtu.be/dQw4w9WgXcQ|https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
])
def test_spotify_busca_e_pipe_passam_pelo_spotdl(link):
    assert not faixas.e_do_youtube(link)


@pytest.mark.parametrize("link", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ?si=abcDEF123",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
    "https://www.youtube.com/embed/dQw4w9WgXcQ",
    "https://www.youtube.com/watch?list=PLxxx&v=dQw4w9WgXcQ",
    "https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=RDAMVMxxx",
])
def test_video_do_youtube_e_normalizado_pelo_id(link):
    assert faixas.fonte_youtube(link) == (
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ", False)


def test_video_copiado_de_dentro_de_uma_playlist_baixa_so_o_video():
    """O &list= sobrando faria o yt-dlp baixar a playlist inteira."""
    url, e_colecao = faixas.fonte_youtube(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxx&t=42s")
    assert "list=" not in url
    assert not e_colecao


def test_playlist_do_youtube_e_colecao_e_passa_intacta():
    link = "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxx"
    assert faixas.fonte_youtube(link) == (link, True)


# -------------------------------------------------------------- comandos

def test_base_usa_o_ffmpeg_e_o_deno_nossos_e_ignora_config_da_maquina():
    base = faixas.comando_base(Path("C:/c/yt-dlp.exe"), Path("C:/c/ffmpeg.exe"),
                               Path("C:/c/deno.exe"))
    assert "--ignore-config" in base
    assert base[base.index("--ffmpeg-location") + 1] == str(Path("C:/c/ffmpeg.exe"))
    assert base[base.index("--js-runtimes") + 1] == f"deno:{Path('C:/c/deno.exe')}"


def test_sem_deno_o_ytdlp_roda_assim_mesmo():
    base = faixas.comando_base("yt-dlp.exe", "ffmpeg.exe", None)
    assert "--js-runtimes" not in base


def test_video_do_youtube_cai_na_raiz_e_playlist_em_subpasta():
    video = faixas.comando_youtube([], "u", "C:/Musica", e_colecao=False)
    playlist = faixas.comando_youtube([], "u", "C:/Musica", e_colecao=True)
    saida_video = video[video.index("-o") + 1]
    saida_playlist = playlist[playlist.index("-o") + 1]
    assert "playlist_title" not in saida_video
    assert "%(playlist_title)s" in saida_playlist


def test_youtube_sai_em_mp3_320_com_tags_e_capa():
    comando = faixas.comando_youtube([], "u", "C:/Musica", e_colecao=False)
    assert comando[comando.index("--audio-format") + 1] == "mp3"
    assert comando[comando.index("--audio-quality") + 1] == "320K"
    assert "--embed-metadata" in comando and "--embed-thumbnail" in comando


def test_porcento_no_nome_nao_vira_campo_do_template():
    comando = faixas.comando_audio([], "u", Path("C:/M/Artista - 100% Voce.mp3"))
    assert comando[comando.index("-o") + 1].endswith("100%% Voce.%(ext)s")


def test_audio_de_faixa_da_lista_nao_puxa_playlist():
    assert "--no-playlist" in faixas.comando_audio([], "u", Path("C:/M/x.mp3"))


def test_lista_do_spotdl_pede_o_link_do_audio_sem_baixar():
    comando = faixas.comando_lista("spotdl.exe", "link", "C:/t/lista.spotdl")
    assert comando[1] == "save"
    assert "--preload" in comando


# ------------------------------------------------------------ onde cai

MUSICA = {
    "name": "Never Gonna Give You Up",
    "artists": ["Rick Astley"],
    "artist": "Rick Astley",
    "album_name": "Whenever You Need Somebody",
    "album_artist": "Rick Astley",
    "list_name": "Anos 80",
    "track_number": 1,
    "tracks_count": 10,
    "disc_number": 1,
    "date": "1987-11-12",
    "year": 1987,
    "publisher": "BMG",
    "download_url": "https://music.youtube.com/watch?v=lYBUbBu4W08",
}


@pytest.mark.parametrize("link, subpasta", [
    ("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT", None),
    ("rick astley", None),
    ("https://open.spotify.com/playlist/37i9dQZF1DX", "Anos 80"),
    ("https://open.spotify.com/album/5Z9iiGl2FcIfa3BMiv6OIw", "Whenever You Need Somebody"),
    ("https://open.spotify.com/artist/0gxyHStUsqpMadRV0Di1Qt", "Rick Astley"),
])
def test_colecao_ganha_subpasta_e_avulsa_cai_na_raiz(link, subpasta):
    destino = Path("C:/Musica")
    esperado = destino / subpasta if subpasta else destino
    caminho = faixas.caminho_da_faixa(destino, link, MUSICA)
    assert caminho == esperado / "Rick Astley - Never Gonna Give You Up.mp3"


def test_nome_igual_ao_do_spotdl_para_reconhecer_o_ja_baixado():
    musica = {**MUSICA, "artists": ["Anitta", "J Balvin"], "name": "Downtown"}
    caminho = faixas.caminho_da_faixa("C:/M", "x", musica)
    assert caminho.name == "Anitta, J Balvin - Downtown.mp3"


def test_caracteres_proibidos_no_windows_somem():
    musica = {**MUSICA, "artists": ["AC/DC"], "name": 'Who Made Who? "Live".'}
    assert faixas.caminho_da_faixa("C:/M", "x", musica).name == \
        "ACDC - Who Made Who Live.mp3"


# ------------------------------------------------------------------ tags

def test_etiquetar_grava_o_que_o_verificador_de_duplicados_le(tmp_path):
    arquivo = tmp_path / "x.mp3"
    arquivo.write_bytes(b"")
    faixas.etiquetar(arquivo, MUSICA, capa=b"\xff\xd8jpeg")

    tags = ID3(arquivo)
    assert str(tags["TIT2"]) == "Never Gonna Give You Up"
    assert str(tags["TPE1"]) == "Rick Astley"
    assert str(tags["TALB"]) == "Whenever You Need Somebody"
    assert str(tags["TRCK"]) == "1/10"
    assert tags.getall("APIC")[0].data == b"\xff\xd8jpeg"


def test_etiquetar_sem_capa_nem_album_nao_explode(tmp_path):
    arquivo = tmp_path / "x.mp3"
    arquivo.write_bytes(b"")
    faixas.etiquetar(arquivo, {"name": "So o titulo", "artists": ["Alguem"]})
    assert str(ID3(arquivo)["TIT2"]) == "So o titulo"
