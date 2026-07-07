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

COMANDOS_SAIR = {"sair", "tchau", "exit", "quit", "tchau bimo", "até mais"}


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

    # ── um ciclo completo: gatilho → comando → resposta ──────────────────
    def _ciclo(self, esperar_gatilho, ouvir_comando) -> None:
        self.estado.mudar("standby")
        gatilho = esperar_gatilho()
        if not gatilho or self.encerrar.is_set():
            return

        self.estado.mudar("ouvindo")
        if self.ack:
            Boca.tocar(self.ack)
        comando = ouvir_comando()
        if not comando:
            self.estado.mudar("standby")
            return

        if comando.lower().strip() in COMANDOS_SAIR:
            self.estado.mudar("falando", emocao="feliz")
            self._falar("Até mais!")
            self.estado.mudar("standby", emocao="dormindo")
            return

        self.estado.mudar("processando")
        resposta = self.cerebro.responder(comando)
        emocao = extrair_emocao(resposta)

        self.estado.mudar("falando", emocao=emocao)
        self._falar(resposta)
        self.estado.mudar("standby", emocao=emocao)

    def _falar(self, texto: str) -> None:
        if self.boca is None:
            return
        try:
            self.boca.falar(texto)
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
                                lambda: self.ouvidos.ouvir_comando(fonte),
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
        ("boot", None, 3), ("standby", None, 3), ("ouvindo", None, 3),
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

    try:
        while janela.processar_eventos():
            desenhar_estado(rosto, estado, frame)
            janela.render(fb)
            frame += 1
            if frame % 300 == 0:
                janela.fixar_no_topo()  # reafirma o topmost periodicamente
    finally:
        assistente.encerrar.set()
        janela.fechar()
