"""Deteccao de musicas repetidas dentro de uma mesma pasta.

O `--overwrite skip` do spotdl ja evita rebaixar um arquivo no mesmo caminho.
O que escapa dele e a mesma musica salva com nome diferente - outro upload,
metadados um pouco distintos. Por isso aqui a comparacao e feita pelas tags
ID3, nao pelo nome do arquivo.

A varredura e feita pasta a pasta, sem cruzar subpastas: e a regra escolhida
para o projeto ("cada pasta de playlist fica completa e toca sozinha").
"""

import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from mutagen import File as MutagenFile

AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav"}


def normalizar(texto):
    """Reduz um texto a uma forma comparavel: sem acento, caixa ou pontuacao.

    Nao remove marcadores como "ao vivo" ou "remix" de proposito: essas sao
    versoes legitimamente diferentes, e apaga-las seria perda de dado.
    """
    if not texto:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


def ler_chave(caminho):
    """(artista, titulo) normalizados, das tags ID3; cai no nome do arquivo."""
    artista = titulo = ""
    try:
        audio = MutagenFile(caminho, easy=True)
        if audio:
            artista = (audio.get("artist") or [""])[0]
            titulo = (audio.get("title") or [""])[0]
    except Exception:
        pass  # arquivo corrompido ou formato exotico: usamos o nome abaixo

    if not titulo:
        # spotdl nomeia como "{artistas} - {titulo}.ext"
        nome = Path(caminho).stem
        artista, _, titulo = nome.partition(" - ")
        if not titulo:
            artista, titulo = "", nome

    return normalizar(artista), normalizar(titulo)


def _maior_primeiro(caminhos):
    """Maior arquivo na frente: e o candidato a ser mantido (melhor bitrate)."""
    return sorted(caminhos, key=lambda p: (-os.path.getsize(p), str(p)))


def encontrar_duplicados(raiz):
    """Varre `raiz` e devolve (exatos, suspeitos), agrupados por pasta.

    exatos    - mesmo artista E mesmo titulo. Seguro apagar os extras.
    suspeitos - mesmo titulo, artistas diferentes. Apenas reportados, nunca
                apagados: pode ser o mesmo hino por dois interpretes, e pode
                ser uma versao que voce quer manter.

    Cada item e uma lista de caminhos, o primeiro sendo o maior arquivo.
    """
    exatos, suspeitos = [], []

    for pasta, _subpastas, arquivos in os.walk(raiz):
        faixas = []
        for nome in arquivos:
            if Path(nome).suffix.lower() in AUDIO_EXTS:
                caminho = Path(pasta) / nome
                artista, titulo = ler_chave(caminho)
                if titulo:
                    faixas.append((caminho, artista, titulo))

        por_artista_titulo = defaultdict(list)
        por_titulo = defaultdict(set)
        for caminho, artista, titulo in faixas:
            por_artista_titulo[(artista, titulo)].append(caminho)
            por_titulo[titulo].add(artista)

        for (_artista, titulo), grupo in por_artista_titulo.items():
            if len(grupo) > 1:
                exatos.append(_maior_primeiro(grupo))

        for titulo, artistas in por_titulo.items():
            if len(artistas) > 1:
                grupo = [c for c, _a, t in faixas if t == titulo]
                suspeitos.append(_maior_primeiro(grupo))

    return exatos, suspeitos


def apagar_extras(grupos):
    """Apaga tudo menos o primeiro de cada grupo. Devolve os caminhos apagados."""
    apagados = []
    for grupo in grupos:
        for caminho in grupo[1:]:
            try:
                os.remove(caminho)
                apagados.append(caminho)
            except OSError:
                pass
    return apagados
