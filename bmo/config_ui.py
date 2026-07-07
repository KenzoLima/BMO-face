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
"""

CAMPOS_ENV = [
    "BMO_USUARIO_NOME", "BMO_USUARIO_IDADE",
    "GOOGLE_API_KEY", "GROQ_API_KEY",
    "BMO_VOZ", "BMO_MUDO", "BMO_VAULT", "BMO_CONVERSA_TIMEOUT",
]


def _caminho_env() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / ".env"
    return Path(__file__).resolve().parent.parent / ".env"


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


# ─── Testes embutidos ────────────────────────────────────────────────────────


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


def testar_voz(voz: str) -> tuple[bool, str]:
    try:
        from .mouth import Boca

        Boca(voz=voz).falar("Oi! Eu sou o BMO, e esta é a minha voz!")
        return True, "Ouviu? Essa é a voz escolhida."
    except Exception as e:
        return False, f"Voz falhou: {str(e)[:120]}"


def testar_microfone() -> tuple[bool, str]:
    try:
        import audioop

        import pyaudio

        pa = pyaudio.PyAudio()
        fluxo = pa.open(rate=16000, channels=1, format=pyaudio.paInt16,
                        input=True, frames_per_buffer=4000)
        dados = b"".join(
            fluxo.read(4000, exception_on_overflow=False) for _ in range(8)  # ~2s
        )
        fluxo.stop_stream(); fluxo.close(); pa.terminate()
        rms = audioop.rms(dados, 2)
        if rms < 50:
            return False, f"Microfone captou silêncio (nível {rms}). Está mudo?"
        return True, f"Microfone OK! (nível de som: {rms})"
    except Exception as e:
        return False, f"Microfone falhou: {str(e)[:120]}"


# ─── Janela ──────────────────────────────────────────────────────────────────


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
        pad = {"padx": 12, "pady": 4}

        titulo = "Oi! Vamos me configurar?" if primeira_vez else "Configurações do BMO"
        tk.Label(
            self.raiz, text=titulo, font=("Segoe UI", 14, "bold"),
            bg=COR_FUNDO, fg=COR_TEXTO,
        ).grid(row=0, column=0, columnspan=3, padx=12, pady=(12, 8))

        # ── sobre você (Tela 3 do esboço) ────────────────────────────────
        self._secao("Sobre você", 1)
        self.nome = self._campo("Seu nome", atuais.get("BMO_USUARIO_NOME", ""), 2)
        self.idade = self._campo("Sua idade", atuais.get("BMO_USUARIO_IDADE", ""), 3)

        # ── cérebro ──────────────────────────────────────────────────────
        self._secao("Cérebro (obrigatório)", 4)
        self.chave_google = self._campo(
            "Chave Gemini", atuais.get("GOOGLE_API_KEY", ""), 5, segredo=True
        )
        self._botao("Obter chave grátis", 5, 2, self._abrir_site_chave)
        self.chave_groq = self._campo(
            "Chave Groq (opcional)", atuais.get("GROQ_API_KEY", ""), 6, segredo=True
        )
        self._botao("Testar chave", 6, 2, self._testar_chave)

        # ── voz e escuta ─────────────────────────────────────────────────
        self._secao("Voz e escuta", 7)
        tk.Label(self.raiz, text="Voz", bg=COR_FUNDO, fg=COR_TEXTO).grid(
            row=8, column=0, sticky="e", **pad
        )
        self.voz = ttk.Combobox(self.raiz, values=VOZES, width=37, state="readonly")
        self.voz.set(atuais.get("BMO_VOZ", VOZES[0]))
        self.voz.grid(row=8, column=1, **pad)
        self._botao("Ouvir", 8, 2, self._testar_voz)

        self.mudo = tk.BooleanVar(value=atuais.get("BMO_MUDO", "") not in ("", "0"))
        tk.Checkbutton(
            self.raiz, text="Modo mudo (só texto na tela)", variable=self.mudo,
            bg=COR_FUNDO, fg=COR_TEXTO, selectcolor=COR_PAINEL,
            activebackground=COR_FUNDO,
        ).grid(row=9, column=1, sticky="w", **pad)
        self._botao("Testar microfone", 9, 2, self._testar_microfone)

        # ── caderno ──────────────────────────────────────────────────────
        self._secao("Caderno (memória — pasta do Obsidian, opcional)", 10)
        self.vault = self._campo("Pasta", atuais.get("BMO_VAULT", ""), 11)
        self._botao("Escolher...", 11, 2, self._escolher_pasta)

        # ── rodapé ───────────────────────────────────────────────────────
        self.status = tk.Label(self.raiz, text="", bg=COR_FUNDO, fg=COR_TEXTO,
                               wraplength=420, justify="left")
        self.status.grid(row=12, column=0, columnspan=3, **pad)

        tk.Button(
            self.raiz, text="Salvar e ligar o BMO", command=self._salvar,
            bg=COR_BOTAO, fg="white", font=("Segoe UI", 11, "bold"),
            padx=16, pady=6, relief="flat",
        ).grid(row=13, column=0, columnspan=3, pady=(8, 14))

    # ── helpers de layout ────────────────────────────────────────────────
    def _secao(self, texto, linha):
        tk.Label(
            self.raiz, text=texto, font=("Segoe UI", 10, "bold"),
            bg=COR_FUNDO, fg=COR_TEXTO,
        ).grid(row=linha, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 0))

    def _campo(self, rotulo, valor, linha, segredo=False):
        tk.Label(self.raiz, text=rotulo, bg=COR_FUNDO, fg=COR_TEXTO).grid(
            row=linha, column=0, sticky="e", padx=12, pady=4
        )
        entrada = tk.Entry(self.raiz, width=40, show="•" if segredo else "")
        entrada.insert(0, valor)
        entrada.grid(row=linha, column=1, padx=12, pady=4)
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

    # ── ações ────────────────────────────────────────────────────────────
    def _abrir_site_chave(self):
        import webbrowser

        webbrowser.open("https://aistudio.google.com/apikey")

    def _testar_chave(self):
        self._avisar(True, "Testando a chave...")
        self._avisar(*testar_chave_gemini(self.chave_google.get()))

    def _testar_voz(self):
        self._avisar(True, "Sintetizando amostra...")
        self._avisar(*testar_voz(self.voz.get()))

    def _testar_microfone(self):
        self._avisar(True, "Gravando 2 segundos — fale algo!")
        self._avisar(*testar_microfone())

    def _escolher_pasta(self):
        pasta = filedialog.askdirectory(title="Pasta do caderno (vault do Obsidian)")
        if pasta:
            self.vault.delete(0, tk.END)
            self.vault.insert(0, pasta)

    def _salvar(self):
        if not self.chave_google.get().strip():
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
                "BMO_VAULT": self.vault.get().strip(),
            }
        )
        self.salvou = True
        self.raiz.destroy()

    def executar(self) -> bool:
        """Mostra a janela; retorna True se o usuário salvou."""
        self.raiz.eval("tk::PlaceWindow . center")
        self.raiz.mainloop()
        return self.salvou


def abrir_configuracoes(primeira_vez: bool = False) -> bool:
    if tk is None:
        return _avisar_tk_indisponivel(primeira_vez=primeira_vez)
    try:
        return TelaConfiguracoes(primeira_vez=primeira_vez).executar()
    except Exception as e:
        return _avisar_tk_indisponivel(primeira_vez=primeira_vez, erro=e)
