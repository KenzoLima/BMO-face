"""Telas 3 e 4 do esboço — Configurações do BMO (Tkinter, sem dependências).

Aberta:
- automaticamente na primeira execução (sem chave de API configurada);
- pela engrenagem na janela do BMO;
- por ``BMO.exe --config`` / ``python main.py --config``.

É um editor amigável do arquivo .env, com testes embutidos (chave, voz e
microfone) para o usuário leigo descobrir na hora o que está errado.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .audio import (
    CHAVE_ENTRADA,
    CHAVE_SAIDA,
    PADRAO_DO_SISTEMA,
    dispositivos_entrada,
    dispositivos_saida,
)
from .paths import caminho_env as _caminho_env_padrao

try:
    import tkinter as tk
    from tkinter import filedialog, ttk

    _ERRO_TK = None
except Exception as e:
    tk = None
    filedialog = None
    ttk = None
    _ERRO_TK = e

# Paleta do BMO
COR_FUNDO = "#3ec9a7"
COR_PAINEL = "#dff5ec"
COR_TEXTO = "#1a4a38"
COR_BOTAO = "#1a7a5a"

VOZES = ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural"]

# Marca o dispositivo salvo que não está plugado agora — reabrir a tela com o
# fone desligado não pode apagar a escolha do usuário sem ele perceber.
SUFIXO_AUSENTE = "(desconectado)"

# Layout em duas colunas (0-2 à esquerda, 3-5 à direita) — ver o comentário
# no construtor. Campos mais estreitos para as duas colunas caberem lado a lado.
COLUNAS_TOTAIS = 6
LARGURA_CAMPO = 28
LINHA_RODAPE = 12

MODELO_ENV = """\
# Configuracao do BMO - preencha a chave e abra o BMO de novo.
# Chave gratis do Gemini: https://aistudio.google.com/apikey
GOOGLE_API_KEY=

# Opcional: fallback gratis da Groq (https://console.groq.com)
GROQ_API_KEY=

# Opcional
BMO_USUARIO_NOME=
BMO_USUARIO_IDADE=
BMO_VOZ=pt-BR-AntonioNeural
BMO_MUDO=
BMO_VAULT=
BMO_CONVERSA_TIMEOUT=6
BMO_PROATIVIDADE=1
BMO_PROVIDER=gemini
BMO_TTS=edge
BMO_STT_SEM_GOOGLE=
"""

CAMPOS_ENV = [
    "BMO_USUARIO_NOME", "BMO_USUARIO_IDADE",
    "GOOGLE_API_KEY", "GROQ_API_KEY",
    "BMO_VOZ", "BMO_MUDO", "BMO_VAULT", "BMO_CONVERSA_TIMEOUT",
    "BMO_PROATIVIDADE", "BMO_PROVIDER", "BMO_TTS", "BMO_STT_SEM_GOOGLE",
    CHAVE_ENTRADA, CHAVE_SAIDA,
]


def _caminho_env() -> Path:
    return _caminho_env_padrao()


def _caminho_icone() -> Path:
    base = getattr(sys, "_MEIPASS", None)  # pasta _internal no app congelado
    if base:
        return Path(base) / "bmo.ico"
    return Path(__file__).resolve().parent.parent / "instalador" / "bmo.ico"


def ler_env() -> dict[str, str]:
    valores: dict[str, str] = {}
    caminho = _caminho_env()
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, _, valor = linha.partition("=")
                valores[chave.strip()] = valor.strip()
    return valores


def gravar_env(novos: dict[str, str]) -> None:
    """Atualiza as chaves conhecidas preservando o resto do arquivo."""
    caminho = _caminho_env()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.exists() else []

    vistas = set()
    saida = []
    for linha in linhas:
        limpa = linha.strip()
        chave = limpa.partition("=")[0].strip() if "=" in limpa else None
        if chave in novos and not limpa.startswith("#"):
            saida.append(f"{chave}={novos[chave]}")
            vistas.add(chave)
        else:
            saida.append(linha)
    for chave, valor in novos.items():
        if chave not in vistas:
            saida.append(f"{chave}={valor}")

    caminho.write_text("\n".join(saida) + "\n", encoding="utf-8")


def _mostrar_aviso_nativo(titulo: str, mensagem: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, mensagem, titulo, 0x40)
    except Exception:
        print(mensagem)


def _avisar_tk_indisponivel(primeira_vez: bool = False, erro: Exception | None = None) -> bool:
    mensagem = (
        "Nao consegui abrir a janela de configuracao do BMO.\n\n"
        "A chave Gemini deve ser digitada dentro da janela de configuracao, "
        "nao editando arquivos manualmente.\n\n"
        "Este pacote precisa ser reconstruido com Tkinter/Tcl habilitado."
    )
    detalhe = erro or _ERRO_TK
    if detalhe:
        mensagem += f"\n\nDetalhe tecnico: {str(detalhe)[:160]}"

    _mostrar_aviso_nativo(
        "Configurar BMO" if primeira_vez else "Configuracoes do BMO",
        mensagem,
    )
    return False


# --- Testes embutidos ---


def testar_chave_gemini(chave: str) -> tuple[bool, str]:
    if not chave.strip():
        return False, "Cole a chave primeiro."
    try:
        from google import genai

        cliente = genai.Client(api_key=chave.strip())
        cliente.models.generate_content(
            model="gemini-2.5-flash-lite", contents="responda apenas: ok"
        )
        return True, "Cérebro funcionando! ✓"
    except Exception as e:
        texto = str(e)
        if "API_KEY_INVALID" in texto or "API key not valid" in texto:
            return False, "Chave inválida — confira se copiou inteira."
        if "getaddrinfo" in texto or "Connection" in texto:
            return False, "Sem internet — conecte e tente de novo."
        return False, f"Falhou: {texto[:120]}"


def testar_voz(voz: str, saida: str = "") -> tuple[bool, str]:
    """Fala uma amostra. ``saida`` vazia = dispositivo padrão do Windows."""
    try:
        import os

        from .audio import CHAVE_SAIDA
        from .mouth import Boca

        anterior = os.environ.get(CHAVE_SAIDA)
        os.environ[CHAVE_SAIDA] = saida  # a Boca lê daqui ao abrir o mixer
        try:
            _reabrir_mixer()
            Boca(voz=voz).falar("Oi! Eu sou o BMO, e esta é a minha voz!")
        finally:
            if anterior is None:
                os.environ.pop(CHAVE_SAIDA, None)
            else:
                os.environ[CHAVE_SAIDA] = anterior
        onde = saida or "saída padrão do Windows"
        return True, f"Ouviu? Essa é a voz escolhida, em '{onde[:40]}'."
    except Exception as e:
        return False, f"Voz falhou: {str(e)[:120]}"


def _reabrir_mixer() -> None:
    """Fecha o mixer para que ele seja reaberto na saída recém-escolhida."""
    try:
        import pygame

        if pygame.mixer.get_init():
            pygame.mixer.quit()
    except Exception:
        pass


def testar_microfone(entrada: str = "") -> tuple[bool, str]:
    """Grava ~2s e mede o volume. ``entrada`` vazia = microfone padrão."""
    pa = fluxo = None
    try:
        import audioop

        import pyaudio

        from .audio import CHAVE_ENTRADA, indice_entrada

        import os

        anterior = os.environ.get(CHAVE_ENTRADA)
        os.environ[CHAVE_ENTRADA] = entrada
        try:
            indice = indice_entrada()
        finally:
            if anterior is None:
                os.environ.pop(CHAVE_ENTRADA, None)
            else:
                os.environ[CHAVE_ENTRADA] = anterior

        if entrada and indice is None:
            return False, f"'{entrada[:40]}' não está conectado agora."

        pa = pyaudio.PyAudio()
        fluxo = pa.open(rate=16000, channels=1, format=pyaudio.paInt16,
                        input=True, input_device_index=indice,
                        frames_per_buffer=4000)
        dados = b"".join(
            fluxo.read(4000, exception_on_overflow=False) for _ in range(8)  # ~2s
        )
        rms = audioop.rms(dados, 2)
        if rms < 50:
            return False, f"Captou silêncio (nível {rms}). Microfone certo? Está mudo?"
        return True, f"Microfone OK! (nível de som: {rms})"
    except Exception as e:
        return False, f"Microfone falhou: {str(e)[:120]}"
    finally:
        for fechar in (
            lambda: fluxo.stop_stream(), lambda: fluxo.close(), lambda: pa.terminate()
        ):
            try:
                fechar()
            except Exception:
                pass


# --- Janela ---


class TelaConfiguracoes:
    def __init__(self, primeira_vez: bool = False):
        self.raiz = tk.Tk()
        self.raiz.title("BMO — Configurações")
        self.raiz.configure(bg=COR_FUNDO)
        self.raiz.resizable(False, False)
        self.salvou = False
        try:
            self.raiz.iconbitmap(str(_caminho_icone()))
        except Exception:
            pass  # sem ícone não é motivo para não configurar

        atuais = ler_env()

        titulo = "Oi! Vamos me configurar?" if primeira_vez else "Configurações do BMO"
        tk.Label(
            self.raiz, text=titulo, font=("Segoe UI", 14, "bold"),
            bg=COR_FUNDO, fg=COR_TEXTO,
        ).grid(row=0, column=0, columnspan=COLUNAS_TOTAIS, padx=12, pady=(12, 8))

        # Duas colunas: a tela em coluna única passava de 800px de altura e o
        # botão Salvar ficava atrás da barra de tarefas em telas com escala de
        # DPI. Lado a lado, a altura cai pela metade e cabe em qualquer
        # monitor deitado. ESQ = colunas 0-2, DIR = colunas 3-5.
        self._coluna_esquerda(atuais)
        self._coluna_direita(atuais)

        # rodapé, atravessando as duas colunas
        self.status = tk.Label(self.raiz, text="", bg=COR_FUNDO, fg=COR_TEXTO,
                               wraplength=760, justify="left")
        self.status.grid(row=LINHA_RODAPE, column=0, columnspan=COLUNAS_TOTAIS,
                         padx=12, pady=4)

        tk.Button(
            self.raiz, text="Salvar e ligar o BMO", command=self._salvar,
            bg=COR_BOTAO, fg="white", font=("Segoe UI", 11, "bold"),
            padx=16, pady=6, relief="flat",
        ).grid(row=LINHA_RODAPE + 1, column=0, columnspan=COLUNAS_TOTAIS,
               pady=(8, 14))

    # ── conteúdo, uma coluna de cada vez ─────────────────────────────────
    def _coluna_esquerda(self, atuais: dict[str, str]) -> None:
        ESQ = 0
        pad = {"padx": 12, "pady": 4}

        self._secao("Sobre você", 1, ESQ)
        self.nome = self._campo("Seu nome", atuais.get("BMO_USUARIO_NOME", ""), 2, ESQ)
        self.idade = self._campo("Sua idade", atuais.get("BMO_USUARIO_IDADE", ""), 3, ESQ)

        self._secao("Cérebro (obrigatório)", 4, ESQ)
        self.chave_google = self._campo(
            "Chave Gemini", atuais.get("GOOGLE_API_KEY", ""), 5, ESQ, segredo=True
        )
        self._botao("Obter chave grátis", 5, ESQ + 2, self._abrir_site_chave)
        self.chave_groq = self._campo(
            "Chave Groq (opcional)", atuais.get("GROQ_API_KEY", ""), 6, ESQ, segredo=True
        )
        self._botao("Testar chave", 6, ESQ + 2, self._testar_chave)

        self._secao("Voz e escuta", 7, ESQ)
        tk.Label(self.raiz, text="Voz", bg=COR_FUNDO, fg=COR_TEXTO).grid(
            row=8, column=ESQ, sticky="e", **pad
        )
        self.voz = ttk.Combobox(
            self.raiz, values=VOZES, width=LARGURA_CAMPO, state="readonly"
        )
        self.voz.set(atuais.get("BMO_VOZ", VOZES[0]))
        self.voz.grid(row=8, column=ESQ + 1, **pad)
        self._botao("Ouvir", 8, ESQ + 2, self._testar_voz)

        self.mudo = tk.BooleanVar(value=atuais.get("BMO_MUDO", "") not in ("", "0"))
        tk.Checkbutton(
            self.raiz, text="Modo mudo (só texto na tela)", variable=self.mudo,
            bg=COR_FUNDO, fg=COR_TEXTO, selectcolor=COR_PAINEL,
            activebackground=COR_FUNDO,
        ).grid(row=9, column=ESQ + 1, sticky="w", **pad)

        self._secao("Caderno (memória — pasta do Obsidian, opcional)", 10, ESQ)
        self.vault = self._campo("Pasta", atuais.get("BMO_VAULT", ""), 11, ESQ)
        self._botao("Escolher...", 11, ESQ + 2, self._escolher_pasta)

    def _coluna_direita(self, atuais: dict[str, str]) -> None:
        DIR = 3
        pad = {"padx": 12, "pady": 4}
        marcar = {
            "bg": COR_FUNDO, "fg": COR_TEXTO, "selectcolor": COR_PAINEL,
            "activebackground": COR_FUNDO, "wraplength": 330, "justify": "left",
        }

        self._secao("Dispositivos de áudio", 1, DIR)
        tk.Label(self.raiz, text="Microfone", bg=COR_FUNDO, fg=COR_TEXTO).grid(
            row=2, column=DIR, sticky="e", **pad
        )
        self.entrada = ttk.Combobox(self.raiz, width=LARGURA_CAMPO, state="readonly")
        self.entrada.grid(row=2, column=DIR + 1, **pad)
        self._botao("Testar", 2, DIR + 2, self._testar_microfone)

        tk.Label(self.raiz, text="Saída de som", bg=COR_FUNDO, fg=COR_TEXTO).grid(
            row=3, column=DIR, sticky="e", **pad
        )
        self.saida = ttk.Combobox(self.raiz, width=LARGURA_CAMPO, state="readonly")
        self.saida.grid(row=3, column=DIR + 1, **pad)
        self._botao("Testar", 3, DIR + 2, self._testar_voz)

        self._botao("Procurar dispositivos", 4, DIR + 1, self._recarregar_dispositivos)
        self._carregar_dispositivos(
            atuais.get(CHAVE_ENTRADA, ""), atuais.get(CHAVE_SAIDA, "")
        )

        self._secao("Vida própria", 5, DIR)
        self.proatividade = tk.BooleanVar(
            value=atuais.get("BMO_PROATIVIDADE", "1") not in ("", "0")
        )
        tk.Checkbutton(
            self.raiz,
            text="Deixar o BMO tomar iniciativas (bom dia, pausas, lembranças)",
            variable=self.proatividade, **marcar,
        ).grid(row=6, column=DIR, columnspan=3, sticky="w", **pad)

        self._secao("Offline / menos internet", 7, DIR)
        self._provider_original = atuais.get("BMO_PROVIDER", "gemini")
        self.cerebro_local = tk.BooleanVar(value=self._provider_original == "local")
        tk.Checkbutton(
            self.raiz,
            text="Cérebro local (Ollama) — pensa sem internet, cai pra nuvem se precisar",
            variable=self.cerebro_local, **marcar,
        ).grid(row=8, column=DIR, columnspan=3, sticky="w", **pad)

        self.voz_offline = tk.BooleanVar(value=atuais.get("BMO_TTS", "edge") == "piper")
        tk.Checkbutton(
            self.raiz,
            text="Voz offline (Piper) — fala sem internet",
            variable=self.voz_offline, **marcar,
        ).grid(row=9, column=DIR, columnspan=3, sticky="w", **pad)

        self.escuta_offline = tk.BooleanVar(
            value=atuais.get("BMO_STT_SEM_GOOGLE", "") not in ("", "0")
        )
        tk.Checkbutton(
            self.raiz,
            text="Escuta sem Google — transcreve o comando localmente (Whisper)",
            variable=self.escuta_offline, **marcar,
        ).grid(row=10, column=DIR, columnspan=3, sticky="w", **pad)

    # helpers de layout (``coluna`` = coluna-base do bloco: 0 = esq, 3 = dir)
    def _secao(self, texto, linha, coluna=0):
        tk.Label(
            self.raiz, text=texto, font=("Segoe UI", 10, "bold"),
            bg=COR_FUNDO, fg=COR_TEXTO,
        ).grid(row=linha, column=coluna, columnspan=3, sticky="w",
               padx=12, pady=(10, 0))

    def _campo(self, rotulo, valor, linha, coluna=0, segredo=False):
        tk.Label(self.raiz, text=rotulo, bg=COR_FUNDO, fg=COR_TEXTO).grid(
            row=linha, column=coluna, sticky="e", padx=12, pady=4
        )
        entrada = tk.Entry(
            self.raiz, width=LARGURA_CAMPO + 3, show="•" if segredo else ""
        )
        entrada.insert(0, valor)
        entrada.grid(row=linha, column=coluna + 1, padx=12, pady=4)
        return entrada

    def _botao(self, texto, linha, coluna, comando):
        tk.Button(
            self.raiz, text=texto, command=comando, bg=COR_PAINEL, fg=COR_TEXTO,
            relief="flat", padx=8,
        ).grid(row=linha, column=coluna, padx=(0, 12), pady=4)

    def _avisar(self, ok: bool, mensagem: str):
        self.status.config(text=("✓ " if ok else "✗ ") + mensagem,
                           fg="#0a5c38" if ok else "#8a1f1f")
        self.raiz.update_idletasks()

    # dispositivos de áudio
    def _carregar_dispositivos(self, entrada_salva: str, saida_salva: str) -> None:
        """Preenche as listas e reseleciona o que estava salvo.

        Um dispositivo salvo que não está conectado agora continua na lista,
        marcado como ausente: assim reabrir a tela com o fone desligado não
        apaga silenciosamente a escolha do usuário.
        """
        entradas = [d.nome for d in dispositivos_entrada()]
        saidas = dispositivos_saida()
        self._entradas_ausentes = self._marcar_ausente(entradas, entrada_salva)
        self._saidas_ausentes = self._marcar_ausente(saidas, saida_salva)

        self.entrada["values"] = [PADRAO_DO_SISTEMA] + entradas
        self.saida["values"] = [PADRAO_DO_SISTEMA] + saidas
        self.entrada.set(self._entradas_ausentes or entrada_salva or PADRAO_DO_SISTEMA)
        self.saida.set(self._saidas_ausentes or saida_salva or PADRAO_DO_SISTEMA)

    @staticmethod
    def _marcar_ausente(disponiveis: list[str], salvo: str) -> str:
        """Rótulo do dispositivo salvo que sumiu, ou '' se está tudo certo."""
        if not salvo or salvo in disponiveis:
            return ""
        rotulo = f"{salvo} {SUFIXO_AUSENTE}"
        disponiveis.append(rotulo)
        return rotulo

    def _recarregar_dispositivos(self):
        """Reprocura o hardware — para quem plugou o fone com a tela aberta."""
        self._avisar(True, "Procurando dispositivos...")
        _reabrir_mixer()  # sem isso o SDL2 devolve a lista velha em cache
        self._carregar_dispositivos(self._entrada_escolhida(), self._saida_escolhida())
        achados = len(self.entrada["values"]) - 1, len(self.saida["values"]) - 1
        self._avisar(True, f"{achados[0]} microfone(s) e {achados[1]} saída(s) de som.")

    @staticmethod
    def _sem_rotulos(valor: str) -> str:
        """Tira o '(desconectado)' e o rótulo de padrão antes de salvar."""
        valor = (valor or "").strip()
        if valor == PADRAO_DO_SISTEMA:
            return ""
        return valor.removesuffix(SUFIXO_AUSENTE).strip()

    def _entrada_escolhida(self) -> str:
        return self._sem_rotulos(self.entrada.get())

    def _saida_escolhida(self) -> str:
        return self._sem_rotulos(self.saida.get())

    # ações
    def _abrir_site_chave(self):
        import webbrowser

        webbrowser.open("https://aistudio.google.com/apikey")

    def _testar_chave(self):
        self._avisar(True, "Testando a chave...")
        self._avisar(*testar_chave_gemini(self.chave_google.get()))

    def _testar_voz(self):
        self._avisar(True, "Sintetizando amostra...")
        self._avisar(*testar_voz(self.voz.get(), self._saida_escolhida()))

    def _testar_microfone(self):
        self._avisar(True, "Gravando 2 segundos — fale algo!")
        self._avisar(*testar_microfone(self._entrada_escolhida()))

    def _escolher_pasta(self):
        pasta = filedialog.askdirectory(title="Pasta do caderno (vault do Obsidian)")
        if pasta:
            self.vault.delete(0, tk.END)
            self.vault.insert(0, pasta)

    def _provider_escolhido(self) -> str:
        """'local' quando o cérebro local está marcado; senão preserva a
        escolha anterior (gemini/groq), evitando forçar gemini sem querer."""
        if self.cerebro_local.get():
            return "local"
        return self._provider_original if self._provider_original != "local" else "gemini"

    def _salvar(self):
        # com o cérebro local ligado, a chave do Gemini é só a reserva (opcional)
        if not self.cerebro_local.get() and not self.chave_google.get().strip():
            self._avisar(False, "A chave do Gemini é obrigatória — é o cérebro do BMO.")
            return
        gravar_env(
            {
                "BMO_USUARIO_NOME": self.nome.get().strip(),
                "BMO_USUARIO_IDADE": self.idade.get().strip(),
                "GOOGLE_API_KEY": self.chave_google.get().strip(),
                "GROQ_API_KEY": self.chave_groq.get().strip(),
                "BMO_VOZ": self.voz.get(),
                "BMO_MUDO": "1" if self.mudo.get() else "",
                CHAVE_ENTRADA: self._entrada_escolhida(),
                CHAVE_SAIDA: self._saida_escolhida(),
                "BMO_VAULT": self.vault.get().strip(),
                "BMO_PROATIVIDADE": "1" if self.proatividade.get() else "",
                "BMO_PROVIDER": self._provider_escolhido(),
                "BMO_TTS": "piper" if self.voz_offline.get() else "edge",
                "BMO_STT_SEM_GOOGLE": "1" if self.escuta_offline.get() else "",
            }
        )
        self.salvou = True
        self.raiz.destroy()

    def _centralizar(self) -> None:
        """Centraliza na ÁREA DE TRABALHO, não na tela inteira.

        ``tk::PlaceWindow center`` usa a altura total do monitor e ignora a
        barra de tarefas — numa tela apertada isso empurrava o botão Salvar
        para debaixo dela. Aqui a janela é grampeada dentro da área útil, e
        se ainda assim não couber ela encosta no topo (com o Salvar visível)
        em vez de vazar para baixo.
        """
        self.raiz.update_idletasks()
        largura = self.raiz.winfo_reqwidth()
        altura = self.raiz.winfo_reqheight()

        esquerda, topo, direita, base = self._area_util()
        x = esquerda + max(0, (direita - esquerda - largura) // 2)
        y = topo + max(0, (base - topo - altura) // 2)
        self.raiz.geometry(f"+{int(x)}+{int(y)}")

    def _area_util(self) -> tuple[int, int, int, int]:
        """Retângulo da tela sem a barra de tarefas; cai na tela toda se falhar."""
        tela = (0, 0, self.raiz.winfo_screenwidth(), self.raiz.winfo_screenheight())
        try:
            import ctypes
            from ctypes import wintypes

            area = wintypes.RECT()
            ok = ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(area), 0  # SPI_GETWORKAREA
            )
            if ok and area.right > area.left and area.bottom > area.top:
                return area.left, area.top, area.right, area.bottom
        except Exception:
            pass
        return tela

    def executar(self) -> bool:
        """Mostra a janela; retorna True se o usuário salvou."""
        self._centralizar()
        self.raiz.mainloop()
        return self.salvou


def abrir_configuracoes(primeira_vez: bool = False) -> bool:
    if tk is None:
        return _avisar_tk_indisponivel(primeira_vez=primeira_vez)
    try:
        return TelaConfiguracoes(primeira_vez=primeira_vez).executar()
    except Exception as e:
        return _avisar_tk_indisponivel(primeira_vez=primeira_vez, erro=e)
