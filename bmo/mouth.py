"""Resposta (TTS) — a boca do BMO.

Sintetiza a resposta final com edge-tts (vozes neurais da Microsoft, gratuitas,
requer internet) e toca o áudio com o mixer do pygame.

O texto passa por uma limpeza antes de ser falado: expressões como ``[feliz]``
são para o rosto do BMO (bmo_face.py), não para a voz — assim como markdown
e emojis, que soam mal quando lidos em voz alta.

Configuração via .env (opcionais):
    BMO_VOZ=pt-BR-AntonioNeural       # masculina amigável; alternativas femininas:
                                      # pt-BR-FranciscaNeural, pt-BR-ThalitaMultilingualNeural
    BMO_VOZ_VELOCIDADE=+10%
    BMO_VOZ_TOM=+25Hz                 # tom agudo deixa a voz mais jovem, como no desenho
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time

# precisa ser definido antes de qualquer import do pygame
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

_RE_EXPRESSAO = re.compile(
    r"\[(?:feliz|pensativo|surpreso|triste|focado|dormindo)\]", re.IGNORECASE
)
_RE_MARKDOWN = re.compile(r"[*_`#~]+")
_RE_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿️]")

# Grafia → pronúncia: sem isso o TTS soletra "bê-eme-ó"
_PRONUNCIAS = [
    (re.compile(r"\bBMO\b", re.IGNORECASE), "Bímo"),
]


def limpar_para_fala(texto: str) -> str:
    """Remove o que só faz sentido na tela e ajusta pronúncias para a voz."""
    texto = _RE_EXPRESSAO.sub("", texto)
    texto = _RE_MARKDOWN.sub("", texto)
    texto = _RE_EMOJI.sub("", texto)
    for padrao, pronuncia in _PRONUNCIAS:
        texto = padrao.sub(pronuncia, texto)
    return " ".join(texto.split())


class Boca:
    """Sintetiza e fala texto com a voz do BMO."""

    def __init__(
        self,
        voz: str | None = None,
        velocidade: str | None = None,
        tom: str | None = None,
    ):
        self.voz = voz or os.getenv("BMO_VOZ", "pt-BR-AntonioNeural")
        self.velocidade = velocidade or os.getenv("BMO_VOZ_VELOCIDADE", "+10%")
        self.tom = tom or os.getenv("BMO_VOZ_TOM", "+25Hz")

    # ── Síntese ──────────────────────────────────────────────────────────

    async def _sintetizar_async(self, texto: str, destino: str) -> None:
        import edge_tts

        comunicador = edge_tts.Communicate(
            texto, self.voz, rate=self.velocidade, pitch=self.tom
        )
        await comunicador.save(destino)

    def sintetizar(self, texto: str, destino: str | None = None) -> str | None:
        """Gera um .mp3 com a fala e retorna o caminho (None se não há o que falar)."""
        texto = limpar_para_fala(texto)
        if not texto:
            return None

        if destino is None:
            fd, destino = tempfile.mkstemp(suffix=".mp3", prefix="bmo_fala_")
            os.close(fd)

        asyncio.run(self._sintetizar_async(texto, destino))
        return destino

    # ── Reprodução e lip sync ────────────────────────────────────────────

    @staticmethod
    def _mixer():
        import pygame  # lazy: só carrega se realmente formos tocar áudio

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        return pygame

    @staticmethod
    def _polir_envelope(valores: list[float]) -> list[float] | None:
        """Suaviza o volume para virar movimento de boca, nao grafico de audio."""
        if not valores:
            return None

        piso_ruido = 0.04
        ultimo = 0.0
        polido: list[float] = []
        for valor in valores:
            valor = max(0.0, min(1.0, float(valor)))
            if valor < piso_ruido:
                valor = 0.0
            else:
                valor = (valor - piso_ruido) / (1.0 - piso_ruido)

            peso = 0.65 if valor > ultimo else 0.28
            ultimo = ultimo * (1.0 - peso) + valor * peso
            polido.append(max(0.0, min(1.0, ultimo)))

        pico = max(polido)
        if pico <= 0.0:
            return polido
        return [valor / pico for valor in polido]

    @staticmethod
    def _calcular_envelope(som) -> list[float] | None:
        """Amplitude (0..1) da fala em janelas de 50ms — guia a boca do rosto.

        Retorna None se a análise não for possível (ex.: sem numpy);
        o rosto então usa a animação genérica.
        """
        try:
            import numpy as np
            import pygame.sndarray as sndarray

            from .face import JANELA_ENVELOPE

            amostras = sndarray.array(som).astype(np.float32)
            if amostras.ndim == 2:  # estéreo → mono
                amostras = amostras.mean(axis=1)

            taxa = Boca._mixer().mixer.get_init()[0]
            janela = max(1, int(taxa * JANELA_ENVELOPE))
            n_janelas = len(amostras) // janela
            if n_janelas == 0:
                return None

            blocos = amostras[: n_janelas * janela].reshape(n_janelas, janela)
            rms = np.sqrt((blocos**2).mean(axis=1))
            pico = float(rms.max()) or 1.0
            # raiz para dar mais "vida" aos trechos médios da fala
            return Boca._polir_envelope(list(np.sqrt(rms / pico)))
        except Exception:
            return None

    @staticmethod
    def tocar(caminho: str) -> None:
        """Toca um áudio já sintetizado (ex.: frases fixas em cache)."""
        pygame = Boca._mixer()
        canal = pygame.mixer.Sound(caminho).play()
        while canal is not None and canal.get_busy():
            time.sleep(0.03)

    def falar(self, texto: str, ao_iniciar=None) -> bool:
        """Sintetiza e fala o texto, bloqueando até o fim do áudio.

        ``ao_iniciar(envelope)`` é chamado no instante em que o som começa,
        com as amplitudes por janela de 50ms — é o gancho do lip sync.
        Retorna False se não havia nada falável no texto. Erros de rede/áudio
        sobem como exceção — quem chama decide o plano B.
        """
        caminho = self.sintetizar(texto)
        if caminho is None:
            return False
        try:
            pygame = self._mixer()
            som = pygame.mixer.Sound(caminho)
            envelope = self._calcular_envelope(som)
            canal = som.play()
            if ao_iniciar is not None and canal is not None:
                ao_iniciar(envelope)
            while canal is not None and canal.get_busy():
                time.sleep(0.03)
        finally:
            try:
                os.remove(caminho)
            except OSError:
                pass
        return True
