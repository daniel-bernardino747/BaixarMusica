"""Testes do app: a preparacao do link antes de chamar o spotdl.

O que importa aqui e o bug relatado -- link de video do YouTube baixava outra
musica -- e nao regredir os casos que ja funcionavam (Spotify, busca por texto,
playlists). Ver docs/pesquisa-links-youtube-baixam-musica-errada.md.
"""

import pytest

import app


# ------------------------------------------------ YouTube: reescreve e fixa audio

@pytest.mark.parametrize("link", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ?si=abcDEF123",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ",
    "https://www.youtube.com/embed/dQw4w9WgXcQ",
])
def test_video_do_youtube_vira_music_youtube_com_ytm_data(link):
    fonte, flags = app.source_for(link)
    assert fonte == "https://music.youtube.com/watch?v=dQw4w9WgXcQ"
    assert flags == ["--ytm-data"]


def test_id_extraido_mesmo_com_parametros_extras():
    # &list e &t nao podem sobrar: o spotdl faz request.split("?v=", 1)[1].
    fonte, flags = app.source_for(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxx&t=42s")
    assert fonte == "https://music.youtube.com/watch?v=dQw4w9WgXcQ"
    assert flags == ["--ytm-data"]


def test_v_nao_sendo_o_primeiro_parametro():
    fonte, _ = app.source_for(
        "https://www.youtube.com/watch?list=PLxxx&v=dQw4w9WgXcQ")
    assert fonte == "https://music.youtube.com/watch?v=dQw4w9WgXcQ"


def test_link_ja_do_youtube_music_e_normalizado():
    fonte, flags = app.source_for(
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=RDAMVMxxx")
    assert fonte == "https://music.youtube.com/watch?v=dQw4w9WgXcQ"
    assert flags == ["--ytm-data"]


# ------------------------------------------------------ o que passa intacto

def test_spotify_passa_sem_mexer():
    link = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
    assert app.source_for(link) == (link, [])


def test_pipe_youtube_spotify_e_preservado():
    # Sintaxe de matching manual do spotdl: nao pode ser reescrita.
    link = ("https://youtu.be/dQw4w9WgXcQ|"
            "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
    assert app.source_for(link) == (link, [])


def test_busca_por_texto_passa_sem_mexer():
    link = "Rick Astley - Never Gonna Give You Up"
    assert app.source_for(link) == (link, [])


def test_playlist_do_youtube_nao_vira_video_avulso():
    link = "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxx"
    assert app.source_for(link) == (link, [])


def test_link_de_outra_origem_passa_sem_mexer():
    link = "https://soundcloud.com/artista/faixa"
    assert app.source_for(link) == (link, [])
