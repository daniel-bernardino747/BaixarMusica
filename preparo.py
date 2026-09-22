"""Preparo: obter e manter os componentes que o programa nao carrega dentro de si.

O spotdl, o yt-dlp, o ffmpeg e o deno vivem em %APPDATA%\\BaixarMusica e sao
baixados na primeira execucao. Fica tudo fora do executavel de proposito -- ver
docs/adr/0001, 0002 e 0003.

Duas regras sustentam o resto:

1. **Atualizar e um bonus, nunca um pre-requisito.** Sem internet, GitHub fora do ar
   ou download corrompido, seguimos com o que ja esta em disco. So a ausencia total
   de um componente e fatal.
2. **Binario quebrado nunca fica no lugar.** Todo teste de presenca aqui e um
   `exists()`; deixar um arquivo que nao executa significa reusa-lo para sempre.
"""

import gzip
import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
import urllib.request
import zipfile
from collections import namedtuple
from pathlib import Path

PASTA = Path(os.environ.get("APPDATA", Path.home())) / "BaixarMusica"
SPOTDL = PASTA / "spotdl.exe"
YTDLP = PASTA / "yt-dlp.exe"
FFMPEG = PASTA / "ffmpeg.exe"
DENO = PASTA / "deno.exe"
ESTADO = PASTA / "componentes.json"

API_SPOTDL = "https://api.github.com/repos/spotDL/spotify-downloader/releases/latest"
API_YTDLP = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
API_DENO = "https://api.github.com/repos/denoland/deno/releases/latest"

# .gz porque o binario cru tem 76 MB e o comprimido 26 MB; gzip e stdlib.
URL_FFMPEG = "https://github.com/eugeneware/ffmpeg-static/releases/download/b4.4/win32-x64.gz"

# O spotdl publica o digest de cada asset via API. O ffmpeg-static e antigo demais
# e nao tem, entao o hash abaixo esta fixado aqui -- conferido a mao em 22/07/2026.
SHA_FFMPEG = "c718a7b821e6458b25c33a58eea2507799e80aee1079e94419ee9e9be8308ddb"

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
BLOCO = 64 * 1024
ARQUITETURAS = {"amd64", "x86_64"}
TENTATIVAS = 3
ESPERA_PADRAO = 3  # segundos entre tentativas

Asset = namedtuple("Asset", "versao url sha256 tamanho")

# Componente que se atualiza sozinho a cada abertura, direto do release oficial.
# `sufixo` separa o asset do Windows dos das outras plataformas no mesmo release.
Atualizavel = namedtuple("Atualizavel", "nome api sufixo")
SPOTDL_C = Atualizavel("spotdl", API_SPOTDL, "win32.exe")
YTDLP_C = Atualizavel("yt-dlp", API_YTDLP, "yt-dlp.exe")

# O que `preparar` entrega. `deno` pode ser None: ver _preparar_deno().
Componentes = namedtuple("Componentes", "spotdl ytdlp ffmpeg deno")


class ErroDePreparo(Exception):
    """Falha que impede o programa de funcionar. A mensagem vai para o log."""


class MaquinaIncompativel(ErroDePreparo):
    """Falha que tentar de novo nunca resolve. A janela nao oferece retentativa."""


# ------------------------------------------------------------- plataforma

def arquitetura_suportada(maquina=None):
    """Nem o spotdl nem o ffmpeg-static publicam build para Windows ARM."""
    return (maquina or platform.machine()).lower() in ARQUITETURAS


# ------------------------------------------------------------------ asset

def escolher_asset(release, sufixo="win32.exe", nome="spotdl"):
    """Qual dos arquivos do release serve nesta maquina.

    O release traz binarios de varias plataformas com nomes parecidos; pegar o
    errado so daria erro na hora de executar.
    """
    for asset in release.get("assets", []):
        if asset["name"].endswith(sufixo):
            digest = (asset.get("digest") or "").removeprefix("sha256:")
            return Asset(
                versao=release["tag_name"].lstrip("v"),
                url=asset["browser_download_url"],
                sha256=digest or None,
                tamanho=asset["size"],
            )
    raise ErroDePreparo(
        f"o release mais recente do {nome} nao traz o binario {sufixo} -- "
        "provavelmente pararam de publicar para Windows."
    )


# ------------------------------------------------------------- arquivos

def _apagar(caminho):
    """unlink que nunca mascara o erro de verdade.

    No Windows um antivirus segurando o arquivo faz o unlink levantar; num
    bloco `finally` isso soterraria a causa real da falha.
    """
    try:
        caminho.unlink(missing_ok=True)
    except OSError:
        pass


def _anterior(alvo):
    return alvo.with_name(alvo.name + ".anterior")


def instalar(origem, alvo):
    """Poe `origem` no lugar de `alvo`, guardando o que estava la.

    O anterior fica para o caso de a versao nova nascer quebrada -- ver descartar().
    """
    if alvo.exists():
        os.replace(alvo, _anterior(alvo))
    os.replace(origem, alvo)
    return alvo


def reverter(alvo):
    """Devolve a versao anterior ao lugar. False se nao houver nenhuma guardada."""
    anterior = _anterior(alvo)
    if not anterior.exists():
        return False
    os.replace(anterior, alvo)
    return True


def descartar(alvo):
    """Tira do caminho um binario que nao executa: volta o anterior, ou apaga.

    Apagar importa tanto quanto reverter. Um binario quebrado deixado no lugar
    passaria no `exists()` de toda execucao seguinte e nunca seria rebaixado.
    """
    if reverter(alvo):
        return True
    _apagar(alvo)
    return False


def responde(binario, argumento="--version"):
    """Executa o binario. E a unica prova que interessa depois de uma troca."""
    try:
        feito = subprocess.run(
            [str(binario), argumento],
            capture_output=True,
            timeout=120,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return feito.returncode == 0


# --------------------------------------------------------------- download

def _abrir(url):
    pedido = urllib.request.Request(url, headers={"User-Agent": "BaixarMusica"})
    return urllib.request.urlopen(pedido, timeout=30)


def _transferir(url, parcial, nome, sha256, progresso, abrir):
    digestor = hashlib.sha256()
    ultimo = -1

    with abrir(url) as resposta, open(parcial, "wb") as arquivo:
        total = int(resposta.headers.get("Content-Length") or 0)
        lidos = 0
        while True:
            bloco = resposta.read(BLOCO)
            if not bloco:
                break
            arquivo.write(bloco)
            digestor.update(bloco)
            lidos += len(bloco)
            if progresso and total:
                porcento = min(100, lidos * 100 // total)
                if porcento != ultimo:
                    ultimo = porcento
                    progresso(porcento)

    if sha256 and digestor.hexdigest() != sha256:
        raise ErroDePreparo(f"o download de {nome} chegou corrompido (sha256 nao confere)")
    if progresso and ultimo != 100:
        progresso(100)


def baixar(url, destino, sha256=None, progresso=None, abrir=None,
           tentativas=TENTATIVAS, espera=None):
    """Baixa para um temporario, confere o hash, e so entao ocupa `destino`.

    Uma queda no meio do download some junto com o temporario: nunca sobra um
    arquivo pela metade ocupando o lugar de um que funcionava. Wi-fi domestico
    derrubando uma transferencia de 46 MB e comum demais para nao tentar de novo.
    """
    abrir = abrir or _abrir
    espera = ESPERA_PADRAO if espera is None else espera
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    ultimo_erro = None

    for tentativa in range(1, tentativas + 1):
        try:
            _transferir(url, parcial, destino.name, sha256, progresso, abrir)
        except (OSError, ErroDePreparo) as erro:
            ultimo_erro = erro
            _apagar(parcial)
            if tentativa < tentativas and espera:
                time.sleep(espera)
            continue
        os.replace(parcial, destino)
        return destino

    _apagar(parcial)
    raise ErroDePreparo(f"nao consegui baixar {destino.name}: {ultimo_erro}")


# ----------------------------------------------------------------- estado

def _estado():
    try:
        estado = json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return estado if isinstance(estado, dict) else {}


def _versao_instalada(nome="spotdl"):
    return _estado().get(nome)


def _gravar_versao(versao, nome="spotdl"):
    try:
        ESTADO.parent.mkdir(parents=True, exist_ok=True)
        ESTADO.write_text(json.dumps({**_estado(), nome: versao}), encoding="utf-8")
    except OSError:
        pass  # saber a versao e conveniencia; na duvida rebaixamos


# ---------------------------------------------------------------- preparo

def caminho_spotdl():
    """Onde o spotdl esta. A variavel de ambiente existe para desenvolvimento:
    por padrao ate `pythonw app.py` usa o mesmo binario que quem recebe o .exe."""
    return Path(os.environ.get("BAIXARMUSICA_SPOTDL") or SPOTDL)


def _progresso(reportar, nome):
    """Progresso de 10 em 10%: o log e uma lista de linhas, nao uma barra.

    Percentual que anda para tras significa que `baixar` recomecou -- vale
    dizer isso, senao o log parece ter congelado.
    """
    marcos = set()

    def relatar(porcento):
        marco = porcento // 10 * 10
        if marcos and marco < max(marcos):
            reportar(f"    {nome}: a conexao caiu, recomecando...")
            marcos.clear()
        if marco and marco not in marcos:
            marcos.add(marco)
            reportar(f"    {nome}: {marco}%")

    return relatar


def _preparar_ffmpeg(reportar):
    if FFMPEG.exists():
        return

    reportar("Preparando: baixando o ffmpeg (26 MB)...")
    comprimido = PASTA / "ffmpeg.gz"
    cru = PASTA / "ffmpeg.novo"
    try:
        baixar(URL_FFMPEG, comprimido, SHA_FFMPEG,
               progresso=_progresso(reportar, "ffmpeg"))
        reportar("Preparando: descompactando o ffmpeg (76 MB)...")
        with gzip.open(comprimido, "rb") as origem, open(cru, "wb") as saida:
            shutil.copyfileobj(origem, saida, BLOCO)
        instalar(cru, FFMPEG)
    finally:
        _apagar(comprimido)
        _apagar(cru)  # 76 MB de lixo se a descompactacao falhar no meio

    if not responde(FFMPEG, "-version"):
        descartar(FFMPEG)
        raise ErroDePreparo("o ffmpeg baixado nao executou nesta maquina")
    reportar("ffmpeg pronto.")


def _alvo(componente):
    # Resolvido na hora, e nao guardado no namedtuple: os testes trocam SPOTDL e
    # YTDLP por caminhos temporarios via monkeypatch.
    return {"spotdl": SPOTDL, "yt-dlp": YTDLP}[componente.nome]


def _atualizar(componente, reportar):
    nome, alvo = componente.nome, _alvo(componente)
    with _abrir(componente.api) as resposta:
        asset = escolher_asset(json.load(resposta), componente.sufixo, nome)

    ja_temos = alvo.exists()
    if ja_temos and _versao_instalada(nome) == asset.versao:
        return

    verbo = "atualizando para o" if ja_temos else "baixando o"
    megas = asset.tamanho // (1024 * 1024)
    reportar(f"Preparando: {verbo} {nome} {asset.versao} ({megas} MB)...")
    if not asset.sha256:
        reportar("    (este release nao publica sha256; confiro executando)")

    novo = PASTA / f"{nome}.novo"
    try:
        baixar(asset.url, novo, asset.sha256, progresso=_progresso(reportar, nome))
        instalar(novo, alvo)
    finally:
        _apagar(novo)

    if not responde(alvo):
        if descartar(alvo):
            reportar(f"O {nome} {asset.versao} nao executou aqui; voltei para a anterior.")
            return
        raise ErroDePreparo(f"o {nome} baixado nao executou nesta maquina")

    _gravar_versao(asset.versao, nome)
    reportar(f"{nome} {asset.versao} pronto.")


def _preparar_atualizavel(componente, reportar):
    nome = componente.nome
    ja_temos = _alvo(componente).exists()
    try:
        _atualizar(componente, reportar)
    except Exception as erro:
        # Falha ao atualizar nunca pode derrubar uma instalacao que funciona:
        # sem internet, GitHub fora, release corrompido -- o binario velho serve.
        if not ja_temos:
            raise ErroDePreparo(f"preciso baixar o {nome} e nao consegui: {erro}")
        reportar(f"Nao deu para atualizar o {nome}: {erro}")
        reportar(f"Seguindo com a versao {_versao_instalada(nome) or 'que ja esta aqui'}.")


def _preparar_spotdl(reportar):
    if os.environ.get("BAIXARMUSICA_SPOTDL"):
        reportar("Usando o spotdl apontado por BAIXARMUSICA_SPOTDL.")
        return
    _preparar_atualizavel(SPOTDL_C, reportar)


def _preparar_ytdlp(reportar):
    _preparar_atualizavel(YTDLP_C, reportar)


def _instalar_deno(reportar):
    with _abrir(API_DENO) as resposta:
        asset = escolher_asset(json.load(resposta), "x86_64-pc-windows-msvc.zip", "deno")

    megas = asset.tamanho // (1024 * 1024)
    reportar(f"Preparando: baixando o deno {asset.versao} ({megas} MB, uma vez so)...")
    compactado = PASTA / "deno.zip"
    novo = PASTA / "deno.novo"
    try:
        baixar(asset.url, compactado, asset.sha256, progresso=_progresso(reportar, "deno"))
        with zipfile.ZipFile(compactado) as arquivo, arquivo.open("deno.exe") as origem, \
                open(novo, "wb") as saida:
            shutil.copyfileobj(origem, saida, BLOCO)
        instalar(novo, DENO)
    finally:
        _apagar(compactado)
        _apagar(novo)

    if not responde(DENO):
        descartar(DENO)
        raise ErroDePreparo("o deno baixado nao executou nesta maquina")
    reportar("deno pronto.")


def _preparar_deno(reportar):
    """O deno e o unico componente opcional.

    O YouTube passou a exigir que o yt-dlp resolva um desafio em JavaScript, e o
    deno e o runtime que o yt-dlp usa para isso. Hoje a maioria dos videos ainda
    baixa sem ele, entao a falha aqui vira aviso e nao bloqueia o programa.
    Diferente do spotdl e do yt-dlp, nao atualizamos: qualquer deno recente serve.
    Retorna o caminho, ou None se nao houver deno utilizavel.
    """
    if DENO.exists():
        return DENO
    try:
        _instalar_deno(reportar)
    except Exception as erro:
        reportar(f"Nao consegui baixar o deno ({erro}); sigo sem ele.")
        return None
    return DENO


def preparar(reportar):
    """Deixa os componentes presentes e utilizaveis. Retorna um `Componentes`.

    `reportar` recebe linhas de texto -- na pratica, o log da janela.
    Levanta ErroDePreparo quando nao ha como o programa funcionar.
    """
    if not arquitetura_suportada():
        raise MaquinaIncompativel(
            f"este programa so funciona em Windows 64 bits Intel/AMD "
            f"(esta maquina e {platform.machine()})"
        )

    PASTA.mkdir(parents=True, exist_ok=True)
    _preparar_ffmpeg(reportar)
    _preparar_spotdl(reportar)
    _preparar_ytdlp(reportar)
    deno = _preparar_deno(reportar)
    return Componentes(caminho_spotdl(), YTDLP, FFMPEG, deno)
