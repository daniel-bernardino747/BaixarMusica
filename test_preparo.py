"""Testes do preparo: obter e manter os componentes (spotdl, yt-dlp, ffmpeg, deno).

O que importa aqui e o que da errado longe da nossa maquina: asset errado,
download corrompido, queda no meio da troca, versao nova quebrada.
"""

import gzip
import hashlib
import io
import json
import pytest

import preparo


RELEASE = {
    "tag_name": "v4.5.2",
    "assets": [
        {"name": "spotDL", "size": 116207,
         "browser_download_url": "https://exemplo/spotDL",
         "digest": "sha256:aa"},
        {"name": "spotdl-4.5.2-darwin", "size": 42453152,
         "browser_download_url": "https://exemplo/darwin",
         "digest": "sha256:bb"},
        {"name": "spotdl-4.5.2-win32.exe", "size": 45970977,
         "browser_download_url": "https://exemplo/win32.exe",
         "digest": "sha256:cc"},
    ],
}


# --------------------------------------------------------------- asset

def test_escolhe_o_asset_windows_e_nao_o_darwin():
    asset = preparo.escolher_asset(RELEASE)
    assert asset.versao == "4.5.2"
    assert asset.url == "https://exemplo/win32.exe"
    assert asset.sha256 == "cc"
    assert asset.tamanho == 45970977


def test_asset_ausente_e_erro_legivel():
    """Se pararem de publicar o build win32, o usuario precisa saber disso."""
    sem_windows = {"tag_name": "v9", "assets": [RELEASE["assets"][1]]}
    with pytest.raises(preparo.ErroDePreparo, match="win32"):
        preparo.escolher_asset(sem_windows)


# ------------------------------------------------------------ download

class FakeResposta(io.BytesIO):
    def __init__(self, dados):
        super().__init__(dados)
        self.headers = {"Content-Length": str(len(dados))}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_baixar_grava_verifica_o_hash_e_reporta_progresso(tmp_path):
    dados = b"x" * 5000
    digest = hashlib.sha256(dados).hexdigest()
    vistos = []

    destino = tmp_path / "spotdl.exe"
    preparo.baixar("https://exemplo/x", destino, digest,
                   progresso=vistos.append,
                   abrir=lambda _url: FakeResposta(dados))

    assert destino.read_bytes() == dados
    assert vistos, "o preparo e mostrado ao vivo; sem progresso ele parece travado"
    assert vistos[-1] == 100


def test_baixar_recusa_conteudo_corrompido_e_nao_deixa_lixo(tmp_path):
    destino = tmp_path / "spotdl.exe"
    with pytest.raises(preparo.ErroDePreparo, match="[Ss]ha256|corromp"):
        preparo.baixar("https://exemplo/x", destino, "0" * 64,
                       abrir=lambda _url: FakeResposta(b"conteudo errado"),
                       espera=0)

    assert not destino.exists()
    assert list(tmp_path.iterdir()) == [], "arquivo temporario ficou para tras"


# ------------------------------------------------- troca atomica e volta

def test_instalar_preserva_a_versao_anterior(tmp_path):
    alvo = tmp_path / "spotdl.exe"
    alvo.write_bytes(b"versao velha")
    novo = tmp_path / "novo.tmp"
    novo.write_bytes(b"versao nova")

    preparo.instalar(novo, alvo)

    assert alvo.read_bytes() == b"versao nova"
    assert (tmp_path / "spotdl.exe.anterior").read_bytes() == b"versao velha"


def test_reverter_traz_a_anterior_de_volta(tmp_path):
    alvo = tmp_path / "spotdl.exe"
    alvo.write_bytes(b"versao nova quebrada")
    (tmp_path / "spotdl.exe.anterior").write_bytes(b"versao velha")

    assert preparo.reverter(alvo) is True
    assert alvo.read_bytes() == b"versao velha"


def test_reverter_sem_anterior_nao_explode(tmp_path):
    alvo = tmp_path / "spotdl.exe"
    alvo.write_bytes(b"unica versao")

    assert preparo.reverter(alvo) is False
    assert alvo.read_bytes() == b"unica versao"


# ------------------------------------------------------------ plataforma

@pytest.mark.parametrize("maquina, esperado", [
    ("AMD64", True),
    ("x86_64", True),
    ("ARM64", False),
    ("x86", False),
])
def test_arquitetura_suportada(maquina, esperado):
    assert preparo.arquitetura_suportada(maquina) is esperado


def test_maquina_incompativel_nao_adianta_tentar_de_novo(monkeypatch):
    """A janela oferece 'Tentar de novo' quando o preparo falha. Numa maquina
    ARM tentar de novo nunca vai dar certo, entao o erro precisa se distinguir."""
    monkeypatch.setattr(preparo.platform, "machine", lambda: "ARM64")
    with pytest.raises(preparo.MaquinaIncompativel):
        preparo.preparar(lambda _linha: None)


# ------------------------------------------------------------ resiliencia

def test_baixar_tenta_de_novo_depois_de_uma_queda(tmp_path):
    dados = b"y" * 3000
    tentativas = []

    def abrir(_url):
        tentativas.append(1)
        if len(tentativas) < 3:
            raise OSError("conexao caiu")
        return FakeResposta(dados)

    destino = tmp_path / "spotdl.exe"
    preparo.baixar("https://exemplo/x", destino, hashlib.sha256(dados).hexdigest(),
                   abrir=abrir, espera=0)

    assert destino.read_bytes() == dados
    assert len(tentativas) == 3


def test_baixar_desiste_depois_de_esgotar_as_tentativas(tmp_path):
    def cair(_url):
        raise OSError("caiu")

    with pytest.raises(preparo.ErroDePreparo):
        preparo.baixar("https://exemplo/x", tmp_path / "x.exe",
                       abrir=cair, espera=0)


def test_descartar_apaga_o_binario_quebrado_quando_nao_ha_anterior(tmp_path):
    """Sem isto, um ffmpeg que nao executa fica no lugar e o preparo o reusa
    para sempre, porque o teste seguinte e so `if FFMPEG.exists()`."""
    alvo = tmp_path / "ffmpeg.exe"
    alvo.write_bytes(b"binario que nao executa")

    assert preparo.descartar(alvo) is False
    assert not alvo.exists()


def test_descartar_prefere_reverter_quando_ha_anterior(tmp_path):
    alvo = tmp_path / "ffmpeg.exe"
    alvo.write_bytes(b"novo quebrado")
    (tmp_path / "ffmpeg.exe.anterior").write_bytes(b"velho bom")

    assert preparo.descartar(alvo) is True
    assert alvo.read_bytes() == b"velho bom"


# ------------------------------------------- ffmpeg: o caminho da 1a vez

def _fingir_ffmpeg(tmp_path, monkeypatch, conteudo, executa):
    comprimido = gzip.compress(conteudo)
    monkeypatch.setattr(preparo, "PASTA", tmp_path)
    monkeypatch.setattr(preparo, "FFMPEG", tmp_path / "ffmpeg.exe")
    monkeypatch.setattr(preparo, "SHA_FFMPEG", hashlib.sha256(comprimido).hexdigest())
    monkeypatch.setattr(preparo, "_abrir", lambda _url: FakeResposta(comprimido))
    monkeypatch.setattr(preparo, "responde", lambda *_a, **_k: executa)
    return tmp_path / "ffmpeg.exe"


def test_ffmpeg_chega_comprimido_e_e_descompactado(tmp_path, monkeypatch):
    conteudo = b"MZ binario do ffmpeg" * 100
    ffmpeg = _fingir_ffmpeg(tmp_path, monkeypatch, conteudo, executa=True)

    preparo._preparar_ffmpeg(lambda _linha: None)

    assert ffmpeg.read_bytes() == conteudo
    assert not (tmp_path / "ffmpeg.gz").exists(), "sobrou o comprimido"
    assert not (tmp_path / "ffmpeg.novo").exists(), "sobraram 76 MB de intermediario"


def test_ffmpeg_que_nao_executa_nao_fica_no_lugar(tmp_path, monkeypatch):
    """Sem isto ele passaria no exists() de toda execucao seguinte, para sempre."""
    ffmpeg = _fingir_ffmpeg(tmp_path, monkeypatch, b"binario quebrado", executa=False)

    with pytest.raises(preparo.ErroDePreparo):
        preparo._preparar_ffmpeg(lambda _linha: None)

    assert not ffmpeg.exists()


# ------------------------------------- a atualizacao nunca pode ser fatal

def _isolar(tmp_path, monkeypatch):
    monkeypatch.setattr(preparo, "PASTA", tmp_path)
    monkeypatch.setattr(preparo, "SPOTDL", tmp_path / "spotdl.exe")
    monkeypatch.setattr(preparo, "ESTADO", tmp_path / "componentes.json")
    monkeypatch.delenv("BAIXARMUSICA_SPOTDL", raising=False)
    return tmp_path / "spotdl.exe"


def test_sem_internet_seguimos_com_o_spotdl_que_ja_esta_em_disco(tmp_path, monkeypatch):
    spotdl = _isolar(tmp_path, monkeypatch)
    spotdl.write_bytes(b"versao que funciona")

    def cair(_url):
        raise OSError("sem internet")
    monkeypatch.setattr(preparo, "_abrir", cair)

    linhas = []
    preparo._preparar_spotdl(linhas.append)  # nao pode levantar

    assert spotdl.read_bytes() == b"versao que funciona"
    assert any("sem internet" in linha for linha in linhas)


def test_atualizacao_corrompida_preserva_o_binario_bom(tmp_path, monkeypatch):
    """Uma queda no meio do download de uma atualizacao nao pode deixar o
    programa inutil: o binario velho continua servindo."""
    spotdl = _isolar(tmp_path, monkeypatch)
    spotdl.write_bytes(b"versao velha que funciona")

    def abrir(url):
        if url == preparo.API_SPOTDL:
            return FakeResposta(json.dumps(RELEASE).encode())
        return FakeResposta(b"bytes que nao batem com o digest")
    monkeypatch.setattr(preparo, "_abrir", abrir)
    monkeypatch.setattr(preparo, "ESPERA_PADRAO", 0)

    linhas = []
    preparo._preparar_spotdl(linhas.append)  # nao pode levantar

    assert spotdl.read_bytes() == b"versao velha que funciona"
    assert list(tmp_path.glob("*.parcial")) == []


def test_sem_spotdl_em_disco_a_falha_e_fatal(tmp_path, monkeypatch):
    """O contrario tambem vale: se nao ha nada em disco, nao da para fingir."""
    _isolar(tmp_path, monkeypatch)

    def cair(_url):
        raise OSError("sem internet")
    monkeypatch.setattr(preparo, "_abrir", cair)

    with pytest.raises(preparo.ErroDePreparo):
        preparo._preparar_spotdl(lambda _linha: None)


# ---------------------------------------------------- yt-dlp e deno

YTDLP_RELEASE = {
    "tag_name": "2026.08.19",
    "assets": [
        {"name": "yt-dlp", "size": 1, "browser_download_url": "https://exemplo/unix",
         "digest": "sha256:aa"},
        {"name": "yt-dlp_x86.exe", "size": 2, "browser_download_url": "https://exemplo/x86",
         "digest": "sha256:bb"},
        {"name": "yt-dlp.exe", "size": 3, "browser_download_url": "https://exemplo/yt-dlp.exe",
         "digest": "sha256:cc"},
    ],
}


def test_escolhe_o_ytdlp_64_bits_e_nao_o_x86():
    asset = preparo.escolher_asset(YTDLP_RELEASE, "yt-dlp.exe", "yt-dlp")
    assert asset.url == "https://exemplo/yt-dlp.exe"
    assert asset.versao == "2026.08.19"


def test_versoes_de_componentes_diferentes_nao_se_sobrescrevem(tmp_path, monkeypatch):
    monkeypatch.setattr(preparo, "ESTADO", tmp_path / "componentes.json")
    preparo._gravar_versao("4.5.2", "spotdl")
    preparo._gravar_versao("2026.08.19", "yt-dlp")
    assert preparo._versao_instalada("spotdl") == "4.5.2"
    assert preparo._versao_instalada("yt-dlp") == "2026.08.19"


def test_ytdlp_novo_e_baixado_e_a_versao_gravada(tmp_path, monkeypatch):
    dados = b"MZ yt-dlp"
    release = {"tag_name": "2026.08.19", "assets": [
        {"name": "yt-dlp.exe", "size": len(dados), "browser_download_url": "https://exemplo/y",
         "digest": "sha256:" + hashlib.sha256(dados).hexdigest()}]}
    monkeypatch.setattr(preparo, "PASTA", tmp_path)
    monkeypatch.setattr(preparo, "YTDLP", tmp_path / "yt-dlp.exe")
    monkeypatch.setattr(preparo, "ESTADO", tmp_path / "componentes.json")
    monkeypatch.setattr(preparo, "responde", lambda *_a, **_k: True)
    monkeypatch.setattr(preparo, "_abrir", lambda url: FakeResposta(
        json.dumps(release).encode() if url == preparo.API_YTDLP else dados))

    preparo._preparar_ytdlp(lambda _linha: None)

    assert (tmp_path / "yt-dlp.exe").read_bytes() == dados
    assert preparo._versao_instalada("yt-dlp") == "2026.08.19"


def test_sem_ytdlp_em_disco_a_falha_e_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(preparo, "PASTA", tmp_path)
    monkeypatch.setattr(preparo, "YTDLP", tmp_path / "yt-dlp.exe")

    def cair(_url):
        raise OSError("sem internet")
    monkeypatch.setattr(preparo, "_abrir", cair)

    with pytest.raises(preparo.ErroDePreparo, match="yt-dlp"):
        preparo._preparar_ytdlp(lambda _linha: None)


def test_falha_ao_baixar_o_deno_nao_impede_o_programa(tmp_path, monkeypatch):
    """O deno e opcional: o yt-dlp ainda baixa a maioria dos videos sem ele."""
    monkeypatch.setattr(preparo, "PASTA", tmp_path)
    monkeypatch.setattr(preparo, "DENO", tmp_path / "deno.exe")

    def cair(_url):
        raise OSError("sem internet")
    monkeypatch.setattr(preparo, "_abrir", cair)

    linhas = []
    assert preparo._preparar_deno(linhas.append) is None
    assert any("deno" in linha for linha in linhas)


def test_deno_chega_zipado_e_e_extraido(tmp_path, monkeypatch):
    import zipfile
    compactado = io.BytesIO()
    with zipfile.ZipFile(compactado, "w") as arquivo:
        arquivo.writestr("deno.exe", b"MZ deno")
    dados = compactado.getvalue()
    release = {"tag_name": "v2.9.7", "assets": [
        {"name": "deno-x86_64-pc-windows-msvc.zip", "size": len(dados),
         "browser_download_url": "https://exemplo/deno.zip",
         "digest": "sha256:" + hashlib.sha256(dados).hexdigest()}]}
    monkeypatch.setattr(preparo, "PASTA", tmp_path)
    monkeypatch.setattr(preparo, "DENO", tmp_path / "deno.exe")
    monkeypatch.setattr(preparo, "responde", lambda *_a, **_k: True)
    monkeypatch.setattr(preparo, "_abrir", lambda url: FakeResposta(
        json.dumps(release).encode() if url == preparo.API_DENO else dados))

    assert preparo._preparar_deno(lambda _linha: None) == tmp_path / "deno.exe"
    assert (tmp_path / "deno.exe").read_bytes() == b"MZ deno"
    assert not (tmp_path / "deno.zip").exists(), "sobrou o zip de 40 MB"
