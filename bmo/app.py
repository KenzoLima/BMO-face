"""Aplicativo de desktop do BMO: janela flutuante + assistente de voz.

Arquitetura:
- Thread principal: janela pygame (rosto animado, arrastar, fechar).
- Thread de trabalho (daemon): ciclo do assistente — wake word → comando →
  cérebro → fala — publicando cada fase no ``EstadoBMO`` compartilhado,
  que o rosto reflete em tempo real.

Erros no ciclo de voz nunca derrubam o app: viram o estado "erro" no rosto
por alguns segundos e o ciclo recomeça.
"""

from __future__ import annotations

import os
import threading
import time

from .brain import Cerebro
from .face import EstadoBMO, FrameBuffer, RostoBMO, desenhar_estado, extrair_emocao
from .mouth import Boca

# Frases que encerram o ASSUNTO (a conversa volta ao modo wake word).
# Casamento exato da fala inteira — "obrigado pela dica, e amanhã?" não encerra.
FRASES_ENCERRAR = {
    "sair", "tchau", "exit", "quit", "tchau bimo", "até mais",
    "obrigado", "obrigada", "valeu", "só isso", "é só isso",
    "só isso mesmo", "por enquanto é só", "pode dormir",
}

TIMEOUT_PRIMEIRO_COMANDO = 10.0  # após a wake word


def _timeout_conversa() -> float:
    """Silêncio (s) que encerra o assunto no modo conversa."""
    return float(os.getenv("BMO_CONVERSA_TIMEOUT", "6"))


def _avisar_usuario(titulo: str, mensagem: str) -> None:
    """Caixa de diálogo nativa — o app roda sem console, então erros de
    configuração precisam de um aviso visível."""
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, mensagem, titulo, 0x30)  # MB_ICONWARNING


class AssistenteDeVoz(threading.Thread):
    """Ciclo de voz do BMO rodando em segundo plano."""

    def __init__(self, estado: EstadoBMO):
        super().__init__(daemon=True, name="bmo-voz")
        self.estado = estado
        self.encerrar = threading.Event()

    # ── inicialização pesada (mostra o boot na janela enquanto roda) ─────
    def _preparar(self) -> None:
        from .ears import criar_ouvidos

        self.cerebro = Cerebro()
        self.ouvidos = criar_ouvidos()
        self.boca = None if os.getenv("BMO_MUDO") else Boca()
        self.ack = self.boca.sintetizar("Oi! Pode falar!") if self.boca else None

    # ── um ciclo completo: gatilho → CONVERSA (vários turnos) → standby ──
    def _ciclo(self, esperar_gatilho, ouvir_comando) -> None:
        """Após a wake word, o BMO conversa em turnos seguidos — sem exigir
        novo "bimo" a cada pergunta — até uma frase de encerramento ou
        silêncio (BMO_CONVERSA_TIMEOUT segundos)."""
        self.estado.mudar("standby")
        gatilho = esperar_gatilho()
        if not gatilho or self.encerrar.is_set():
            return

        if self.ack:
            Boca.tocar(self.ack)

        emocao = None
        primeiro_turno = True
        while not self.encerrar.is_set():
            self.estado.mudar("ouvindo")
            timeout = TIMEOUT_PRIMEIRO_COMANDO if primeiro_turno else _timeout_conversa()
            comando = ouvir_comando(timeout)

            if not comando:  # silêncio: assunto encerrado, volta a esperar "bimo"
                break

            if comando.lower().strip() in FRASES_ENCERRAR:
                self._falar("Até mais!", emocao="feliz")
                emocao = "dormindo"
                break

            primeiro_turno = False
            self.estado.mudar("processando")
            resposta = self.cerebro.responder(comando)
            emocao = extrair_emocao(resposta)

            self._falar(resposta, emocao=emocao)
            # continua no laço: ouvindo o próximo turno da conversa

        self.estado.mudar("standby", emocao=emocao)

    def _falar(self, texto: str, emocao: str | None = None) -> None:
        """Fala com lip sync: o rosto entra em 'falando' no instante em que o
        áudio começa, e a boca segue o envelope de amplitude da voz."""
        if self.boca is None:
            self.estado.mudar("falando", emocao=emocao)
            time.sleep(1.0)  # aceno visual mesmo no modo mudo
            return
        try:
            self.boca.falar(
                texto,
                ao_iniciar=lambda env: self.estado.iniciar_fala(env, emocao),
            )
        except Exception:
            self.boca = None  # sem voz nesta sessão; rosto e ação continuam

    def run(self) -> None:
        try:
            self._preparar()
        except Exception as e:
            self.estado.mudar("erro", detalhe=str(e))
            _avisar_usuario(
                "BMO não conseguiu iniciar",
                f"{e}\n\nConfigure o arquivo .env (veja o .env.example) e abra o BMO de novo.",
            )
            return

        # Tela 2 do esboço: boot se dissolve no rosto e o BMO se apresenta
        from .face import DURACAO_APRESENTACAO

        self.estado.mudar("apresentacao")
        time.sleep(DURACAO_APRESENTACAO + 0.2)
        self._falar("Oi, sou o Bimo!", emocao="feliz")
        self.estado.mudar("standby", emocao="feliz")

        from .ears import Ouvidos

        while not self.encerrar.is_set():
            try:
                if isinstance(self.ouvidos, Ouvidos):
                    # motor Google: precisa do microfone aberto no ciclo todo
                    with self.ouvidos.abrir_microfone() as fonte:
                        self.ouvidos.calibrar(fonte)
                        while not self.encerrar.is_set():
                            self._ciclo(
                                lambda: self.ouvidos.esperar_wake_word(fonte),
                                lambda t: self.ouvidos.ouvir_comando(fonte, timeout=t),
                            )
                else:
                    # motores locais (Vosk/Porcupine)
                    self._ciclo(
                        self.ouvidos.esperar_wake_word,
                        self.ouvidos.ouvir_comando,
                    )
            except Exception as e:
                self.estado.mudar("erro", detalhe=str(e)[:120])
                time.sleep(4.0)


class _DemoDeEstados(threading.Thread):
    """BMO_DEMO=1: percorre todos os estados do rosto (demonstração/validação)."""

    ROTEIRO = [
        ("boot", None, 3), ("apresentacao", None, 2), ("standby", None, 3), ("ouvindo", None, 3),
        ("processando", None, 3), ("falando", "feliz", 3),
        ("standby", "feliz", 3), ("falando", "triste", 3),
        ("standby", "surpreso", 3), ("erro", None, 3), ("standby", None, 3),
    ]

    def __init__(self, estado: EstadoBMO):
        super().__init__(daemon=True, name="bmo-demo")
        self.estado = estado
        self.encerrar = threading.Event()

    def run(self) -> None:
        for modo, emocao, segundos in self.ROTEIRO:
            if self.encerrar.is_set():
                return
            self.estado.mudar(modo, emocao=emocao)
            time.sleep(segundos)


def _caminho_env():
    import sys
    from pathlib import Path

    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / ".env"
    return Path(__file__).resolve().parent.parent / ".env"


def _abrir_configuracoes_externas() -> None:
    """Lança a tela de configurações como processo separado (Tkinter e
    pygame não dividem bem o mesmo processo)."""
    import subprocess
    import sys

    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable, "--config"], close_fds=True)
    else:
        subprocess.Popen(
            [sys.executable, str(_caminho_env().parent / "main.py"), "--config"],
            close_fds=True,
        )


def _reiniciar_app() -> None:
    """Reabre o BMO (para aplicar configurações novas) e encerra este processo."""
    import subprocess
    import sys

    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable], close_fds=True)
    else:
        subprocess.Popen(
            [sys.executable, str(_caminho_env().parent / "main.py")], close_fds=True
        )


def executar_app() -> None:
    """Sobe a janela flutuante com o assistente completo."""
    from .janela import JanelaBMO  # import local: exige ambiente gráfico

    estado = EstadoBMO()
    if os.getenv("BMO_DEMO"):
        assistente = _DemoDeEstados(estado)
    else:
        assistente = AssistenteDeVoz(estado)
    assistente.start()

    janela = JanelaBMO()
    fb = FrameBuffer()
    rosto = RostoBMO(fb)
    frame = 0

    env = _caminho_env()
    mtime_env = env.stat().st_mtime if env.exists() else 0
    reiniciar = False

    try:
        while janela.processar_eventos():
            if janela.abrir_config_pedido:
                janela.abrir_config_pedido = False
                _abrir_configuracoes_externas()

            desenhar_estado(rosto, estado, frame)
            janela.render(fb)
            frame += 1
            if frame % 300 == 0:
                janela.fixar_no_topo()  # reafirma o topmost periodicamente
            if frame % 60 == 0 and env.exists():  # configurações mudaram?
                novo_mtime = env.stat().st_mtime
                if mtime_env and novo_mtime != mtime_env:
                    reiniciar = True
                    break
                mtime_env = novo_mtime
    finally:
        assistente.encerrar.set()
        janela.fechar()
        if reiniciar:
            _reiniciar_app()
