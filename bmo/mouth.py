"""Resposta (TTS) — a boca do BMO.

Sintetiza a resposta final com edge-tts (vozes neurais da Microsoft, gratuitas,
requer internet) e toca o áudio com o mixer do pygame.

O texto passa por uma limpeza antes de ser falado: expressões como ``[feliz]``
são para o rosto do BMO (bmo_face.py), não para a voz — assim como markdown
e emojis, que soam mal quando lidos em voz alta.

Configuração via .env (opcionais):
    BMO_VOZ=pt-BR-FranciscaNeural     # ou pt-BR-AntonioNeural, pt-BR-ThalitaMultilingualNeural
    BMO_VOZ_VELOCIDADE=+10%
    BMO_VOZ_TOM=+15Hz                 # tom levemente agudo = mais cara de BMO
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time

# precisa ser definido antes de qualquer import do pygame
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import edge_tts

_RE_EXPRESSAO = re.compile(
    r"\[(?:feliz|pensativo|surpreso|triste|focado|dormindo)\]", re.IGNORECASE
)
_RE_MARKDOWN = re.compile(r"[*_`#~]+")
_RE_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿️]")


def limpar_para_fala(texto: str) -> str:
    """Remove tudo que faz sentido na tela mas não na voz."""
    texto = _RE_EXPRESSAO.sub("", texto)
    texto = _RE_MARKDOWN.sub("", texto)
    texto = _RE_EMOJI.sub("", texto)
    return " ".join(texto.split())


class Boca:
    """Sintetiza e fala texto com a voz do BMO."""

    def __init__(
        self,
        voz: str | None = None,
        velocidade: str | None = None,
        tom: str | None = None,
    ):
        self.voz = voz or os.getenv("BMO_VOZ", "pt-BR-FranciscaNeural")
        self.velocidade = velocidade or os.getenv("BMO_VOZ_VELOCIDADE", "+10%")
        self.tom = tom or os.getenv("BMO_VOZ_TOM", "+15Hz")

    # ── Síntese ──────────────────────────────────────────────────────────

    async def _sintetizar_async(self, texto: str, destino: str) -> None:
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

    # ── Reprodução ───────────────────────────────────────────────────────

    @staticmethod
    def _tocar(caminho: str) -> None:
        import pygame  # lazy: só carrega se realmente formos tocar áudio

        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(caminho)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.music.unload()  # libera o arquivo p/ podermos apagá-lo

    def falar(self, texto: str) -> bool:
        """Sintetiza e fala o texto, bloqueando até o fim do áudio.

        Retorna False se não havia nada falável no texto.
        Erros de rede/áudio sobem como exceção — quem chama decide o plano B
        (ex.: seguir só com texto).
        """
        caminho = self.sintetizar(texto)
        if caminho is None:
            return False
        try:
            self._tocar(caminho)
        finally:
            try:
                os.remove(caminho)
            except OSError:
                pass
        return True
