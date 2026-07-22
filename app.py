"""BaixarMusica - GUI minima sobre o spotdl.

Escolha uma pasta, cole um link, clique em Baixar. O download roda como
subprocesso e o log aparece ao vivo na janela.

O spotdl e o ffmpeg nao vem instalados na maquina de quem recebe o programa:
sao componentes que o modulo `preparo` baixa e mantem em %APPDATA%. O preparo
comeca sozinho ao abrir, enquanto a pessoa ainda escolhe a pasta e cola o link.
"""

import json
import os
import queue
import re
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import duplicados
import preparo

APP_NAME = "BaixarMusica"
# Mesma pasta dos componentes: se o nome mudar, config e binarios andam juntos.
CONFIG_PATH = preparo.PASTA / "config.json"

# Esconde o console preto que cada subprocesso abriria no modo --windowed.
NO_WINDOW = preparo.NO_WINDOW

# Link de colecao vira subpasta; faixa avulsa, busca por texto e YouTube caem na raiz.
COLLECTION_TEMPLATES = {
    "playlist": "{list-name}",
    "album": "{album}",
    "artist": "{artist}",
}


def subfolder_for(link):
    """Retorna o template de subpasta do link, ou '' se ele nao for uma colecao."""
    match = re.search(r"[:/](playlist|album|artist)[:/]", link, re.IGNORECASE)
    return COLLECTION_TEMPLATES[match.group(1).lower()] if match else ""


def build_output_template(destino, link):
    return str(Path(destino) / subfolder_for(link) / "{artists} - {title}.{output-ext}")


def _mb(caminho):
    try:
        return f"{os.path.getsize(caminho) / (1024 * 1024):.1f} MB"
    except OSError:
        return "?"


def load_last_dir():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("last_dir", "")
    except (OSError, ValueError):
        return ""


def save_last_dir(destino):
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({"last_dir": destino}), encoding="utf-8")
    except OSError:
        pass  # config e conveniencia, nunca motivo para quebrar o download


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("720x460")
        self.minsize(560, 360)

        self.linhas = queue.Queue()
        self.processo = None
        self.ocupado = False     # download em andamento
        self.varrendo = False    # busca por duplicados em andamento
        self.cancelado = False
        self.preparando = False    # buscando spotdl/ffmpeg
        self.pronto = False        # componentes utilizaveis
        self.falhou_preparo = False  # falhou, mas tentar de novo pode resolver
        self.incompativel = False    # falhou, e tentar de novo nunca resolve
        self.spotdl = None
        self.ffmpeg = None

        self._build_ui()
        self.after(100, self._drenar_log)
        # Comeca antes de a pessoa fazer qualquer coisa: os segundos que ela gasta
        # escolhendo pasta e colando link sao os mesmos em que os componentes chegam.
        self._iniciar_preparo()

    # ---------------------------------------------------------------- UI

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        form = ttk.Frame(self, padding=10)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Pasta:").grid(row=0, column=0, sticky="w", pady=4)
        self.destino = tk.StringVar(value=load_last_dir())
        ttk.Entry(form, textvariable=self.destino).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(form, text="Procurar", command=self._escolher_pasta).grid(row=0, column=2)

        ttk.Label(form, text="Link:").grid(row=1, column=0, sticky="w", pady=4)
        self.link = tk.StringVar()
        entrada = ttk.Entry(form, textvariable=self.link)
        entrada.grid(row=1, column=1, columnspan=2, sticky="ew", padx=6)
        entrada.bind("<Return>", lambda _: self._baixar())
        entrada.focus_set()

        botoes = ttk.Frame(form)
        botoes.grid(row=2, column=0, columnspan=3, pady=(10, 0))
        self.botao_baixar = ttk.Button(botoes, text="Baixar", command=self._acionar)
        self.botao_baixar.pack(side="left", padx=4)
        ttk.Button(botoes, text="Abrir pasta", command=self._abrir_pasta).pack(side="left", padx=4)
        ttk.Button(botoes, text="Verificar duplicados",
                   command=self._verificar_duplicados).pack(side="left", padx=4)

        area = ttk.Frame(self, padding=(10, 0, 10, 10))
        area.grid(row=1, column=0, sticky="nsew")
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)

        self.log = tk.Text(area, wrap="word", state="disabled", height=10,
                           bg="#1e1e1e", fg="#d4d4d4", insertbackground="#d4d4d4")
        self.log.grid(row=0, column=0, sticky="nsew")
        barra = ttk.Scrollbar(area, orient="vertical", command=self.log.yview)
        barra.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=barra.set)

    def _escolher_pasta(self):
        escolhida = filedialog.askdirectory(initialdir=self.destino.get() or None)
        if escolhida:
            self.destino.set(os.path.normpath(escolhida))

    def _abrir_pasta(self):
        destino = self.destino.get().strip()
        if destino and os.path.isdir(destino):
            os.startfile(destino)
        else:
            self._escrever("Pasta invalida ou ainda nao escolhida.")

    # ------------------------------------------------------------- Log

    def _escrever(self, texto):
        self.log.configure(state="normal")
        self.log.insert("end", texto.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drenar_log(self):
        """Bombeia a fila da thread de download para o widget, no main loop."""
        try:
            while True:
                self._escrever(self.linhas.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._drenar_log)

    # --------------------------------------------------------- Preparo

    def _iniciar_preparo(self):
        if self.preparando:
            return
        self.preparando = True
        self.falhou_preparo = False
        self.botao_baixar.configure(text="Preparando...", state="disabled")
        threading.Thread(target=self._worker_preparo, daemon=True).start()

    def _worker_preparo(self):
        caminhos = None
        falha = None
        try:
            caminhos = preparo.preparar(self.linhas.put)
        except preparo.ErroDePreparo as erro:
            self.linhas.put(f"ERRO: {erro}.")
            falha = erro
        except Exception as erro:  # nada aqui pode derrubar a janela
            self.linhas.put(f"ERRO inesperado no preparo: {erro}")
            falha = erro
        self.after(0, self._fim_preparo, caminhos, falha)

    def _fim_preparo(self, caminhos, falha):
        self.preparando = False
        if falha is not None:
            # Numa maquina ARM, oferecer "Tentar de novo" seria mentira.
            self.incompativel = isinstance(falha, preparo.MaquinaIncompativel)
            self.falhou_preparo = not self.incompativel
            if self.incompativel:
                self.botao_baixar.configure(text="Indisponivel", state="disabled")
            else:
                self.botao_baixar.configure(text="Tentar de novo", state="normal")
            return
        self.spotdl, self.ffmpeg = caminhos
        self.pronto = True
        self.botao_baixar.configure(text="Baixar", state="normal")

    # -------------------------------------------------------- Download

    def _acionar(self):
        """Clique no botao: o rotulo diz o que vai acontecer, entao pode cancelar."""
        if self.falhou_preparo:
            self._iniciar_preparo()
        elif self.ocupado:
            self._cancelar()
        else:
            self._baixar()

    def _baixar(self):
        # Enter tambem cai aqui, e Enter nunca cancela: cancelar exige o botao,
        # que ao menos esta escrito "Cancelar" na hora do clique.
        if self.ocupado:
            self._escrever("Ja existe um download em andamento.")
            return
        if self.varrendo:
            self._escrever("Espere a verificacao de duplicados terminar.")
            return
        # O botao fica desabilitado durante o preparo, mas o Enter no campo de
        # link chega aqui direto -- e precisa dizer a verdade sobre o estado.
        if not self.pronto:
            if self.incompativel:
                self._escrever("Este computador nao e compativel; nao ha o que tentar.")
            elif self.falhou_preparo:
                self._escrever("O preparo falhou. Clique em 'Tentar de novo'.")
            else:
                self._escrever("Ainda estou preparando os componentes; ja ja.")
            return

        destino = self.destino.get().strip()
        link = self.link.get().strip()

        if not destino or not os.path.isdir(destino):
            self._escrever("Escolha uma pasta de destino valida.")
            return
        if not link:
            self._escrever("Cole um link (ou o nome de uma musica).")
            return

        save_last_dir(destino)
        self.cancelado = False
        # Marcado aqui, no main loop, e nao na thread: self.processo so existe
        # segundos depois, e nesse vao um duplo-clique iniciava dois downloads.
        self.ocupado = True
        self.botao_baixar.configure(text="Cancelar")
        self._escrever(f"\n== Baixando: {link} ==")
        threading.Thread(target=self._worker, args=(destino, link), daemon=True).start()

    def _worker(self, destino, link):
        # --ffmpeg explicito: sem ele o spotdl prefere qualquer ffmpeg do PATH,
        # e o programa passaria a usar um binario diferente em cada maquina.
        comando = [
            str(self.spotdl), "download", link,
            "--format", "mp3",
            "--bitrate", "320k",
            "--output", build_output_template(destino, link),
            "--ffmpeg", str(self.ffmpeg),
            "--simple-tui",
        ]

        ambiente = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        try:
            self.processo = subprocess.Popen(
                comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=ambiente,
                creationflags=NO_WINDOW,
            )
        except OSError as erro:
            self.linhas.put(f"ERRO ao iniciar o spotdl: {erro}")
            self.after(0, self._finalizar, None)
            return

        for linha in self.processo.stdout:
            if linha.strip():
                self.linhas.put(linha)
        codigo = self.processo.wait()
        self.after(0, self._finalizar, codigo)

    def _cancelar(self):
        self.cancelado = True
        self._escrever("Cancelando...")
        if self.processo is None:
            # Clique no vao entre marcar ocupado e o Popen retornar; nada a matar.
            return
        if os.name == "nt":
            # /T derruba a arvore inteira: o spotdl deixa ffmpeg rodando atras dele.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self.processo.pid)],
                capture_output=True,
                creationflags=NO_WINDOW,
            )
        else:
            self.processo.terminate()

    def _finalizar(self, codigo):
        self.processo = None
        self.ocupado = False
        self.botao_baixar.configure(text="Baixar")
        if self.cancelado:
            self._escrever("== Cancelado ==")
        elif codigo == 0:
            self._escrever("== Concluido ==")
        elif codigo is not None:
            self._escrever(f"== Erro (codigo {codigo}) ==")

    # ------------------------------------------------------ Duplicados

    def _verificar_duplicados(self):
        if self.ocupado:
            self._escrever("Espere o download terminar para verificar duplicados.")
            return
        if self.varrendo:
            return

        destino = self.destino.get().strip()
        if not destino or not os.path.isdir(destino):
            self._escrever("Escolha uma pasta de destino valida.")
            return

        self.varrendo = True
        self._escrever(f"\n== Procurando repetidas em {destino} ==")
        threading.Thread(target=self._worker_duplicados, args=(destino,), daemon=True).start()

    def _worker_duplicados(self, destino):
        try:
            achados = duplicados.encontrar_duplicados(destino)
        except Exception as erro:
            self.linhas.put(f"ERRO ao varrer a pasta: {erro}")
            achados = ([], [])
        self.after(0, self._fim_duplicados, *achados)

    def _fim_duplicados(self, exatos, suspeitos):
        self.varrendo = False

        for grupo in suspeitos:
            self._escrever(f"[?] mesmo titulo, artistas diferentes  ({grupo[0].parent.name}):")
            for caminho in grupo:
                self._escrever(f"      {caminho.name}")
        if suspeitos:
            self._escrever("    ^ nao serao apagados: podem ser versoes diferentes.")

        if not exatos:
            self._escrever("== Nenhuma repetida para apagar ==")
            return

        extras = 0
        for grupo in exatos:
            self._escrever(f"[!] repetida em {grupo[0].parent.name}:")
            self._escrever(f"      manter: {grupo[0].name} ({_mb(grupo[0])})")
            for caminho in grupo[1:]:
                self._escrever(f"      apagar: {caminho.name} ({_mb(caminho)})")
                extras += 1

        pergunta = (f"Encontrei {extras} arquivo(s) repetido(s).\n\n"
                    "De cada grupo eu mantenho o maior (melhor qualidade) e apago o resto.\n"
                    "A lista completa esta no log. Apagar agora?")
        if messagebox.askyesno("Apagar repetidas?", pergunta, icon="warning", default="no"):
            apagados = duplicados.apagar_extras(exatos)
            self._escrever(f"== {len(apagados)} arquivo(s) apagado(s) ==")
        else:
            self._escrever("== Nada foi apagado ==")


if __name__ == "__main__":
    App().mainloop()
