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
import queue
import re
import tempfile
import threading
import time
from typing import Iterable, Iterator

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


# ── Quebra em frases (para falar enquanto o modelo ainda escreve) ───────────

# Fim de frase = pontuação (+ aspas/parênteses de fecho) + espaço + algo que
# comece uma frase nova. As duas exigências evitam cortes errados:
#   - o espaço protege números — "R$ 14.50" e "3.5 dias" não são duas frases;
#   - a maiúscula protege citação embutida — em 'disse "oi!" e saiu', o "e"
#     minúsculo mostra que a frase continua.
_FIM_DE_FRASE = re.compile(
    r"[.!?…]+[\"'”’)\]]*\s+(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ\"'“¿¡(\[])"
)

# Se o modelo escrever um parágrafo sem pontuação, não dá para segurar o áudio
# até o fim — cortamos num espaço para a fala começar assim mesmo.
LIMITE_FRASE = 180


def _proximo_corte(texto: str) -> int | None:
    achado = _FIM_DE_FRASE.search(texto)
    if achado:
        return achado.end()
    if len(texto) > LIMITE_FRASE:
        espaco = texto.rfind(" ", 0, LIMITE_FRASE)
        return espaco + 1 if espaco > 0 else LIMITE_FRASE
    return None


def frases(pedacos: Iterable[str]) -> Iterator[str]:
    """Junta os pedaços que o LLM vai escrevendo em frases faláveis.

    É o que permite o BMO começar a falar a primeira frase enquanto o modelo
    ainda está escrevendo o resto — o texto completo deixa de ser pré-requisito
    para o áudio começar.
    """
    resto = ""
    for pedaco in pedacos:
        resto += pedaco
        while True:
            corte = _proximo_corte(resto)
            if corte is None:
                break
            frase, resto = resto[:corte].strip(), resto[corte:].lstrip()
            if frase:
                yield frase
    if resto.strip():
        yield resto.strip()


# Aparo de silêncio: o que estiver abaixo desta fração do pico é silêncio, e
# deixamos uma folga para a fala não começar/terminar cortada.
LIMIAR_SILENCIO = 0.02
MARGEM_SILENCIO = 0.06  # segundos — avisos curtos, o mais justo possível
MARGEM_FRASE = 0.14     # entre frases do streaming, p/ a pausa soar natural


def _apagar(caminho: str) -> None:
    try:
        os.remove(caminho)
    except OSError:
        pass


def _esvaziar(fila: queue.Queue) -> None:
    """Apaga os áudios que sobraram na fila sem serem tocados."""
    while True:
        try:
            item = fila.get_nowait()
        except queue.Empty:
            return
        if item:
            _apagar(item)


def _aparar_silencio(caminho: str, margem: float = MARGEM_SILENCIO) -> str:
    """Corta o silêncio das pontas; devolve um .wav novo (ou o original).

    Aparar é otimização: qualquer falha aqui devolve o áudio intacto, porque
    perder a fala seria muito pior do que perder alguns décimos de segundo.
    """
    try:
        import wave

        import numpy as np

        pygame = Boca._mixer()
        amostras = pygame.sndarray.array(pygame.mixer.Sound(caminho))
        taxa, _, canais = pygame.mixer.get_init()

        mono = amostras.mean(axis=1) if amostras.ndim == 2 else amostras
        amplitude = np.abs(mono.astype(np.float32))
        pico = float(amplitude.max())
        if pico <= 0:
            return caminho
        acima = np.flatnonzero(amplitude > pico * LIMIAR_SILENCIO)
        if acima.size == 0:
            return caminho

        margem = int(taxa * margem)
        inicio = max(0, int(acima[0]) - margem)
        fim = min(len(mono), int(acima[-1]) + margem)
        recorte = np.ascontiguousarray(amostras[inicio:fim]).astype(np.int16)

        fd, destino = tempfile.mkstemp(suffix=".wav", prefix="bmo_aviso_")
        os.close(fd)
        with wave.open(destino, "wb") as wav:
            wav.setnchannels(canais)
            wav.setsampwidth(2)
            wav.setframerate(taxa)
            wav.writeframes(recorte.tobytes())
        try:
            os.remove(caminho)
        except OSError:
            pass
        return destino
    except Exception:
        return caminho


class Boca:
    """Sintetiza e fala texto com a voz do BMO."""

    def __init__(
        self,
        voz: str | None = None,
        velocidade: str | None = None,
        tom: str | None = None,
        motor: str | None = None,
    ):
        # motor de síntese: "edge" (nuvem, padrão) ou "piper" (offline, local)
        self.motor = (motor or os.getenv("BMO_TTS", "edge")).strip().lower()
        self.voz = voz or os.getenv("BMO_VOZ", "pt-BR-AntonioNeural")
        self.velocidade = velocidade or os.getenv("BMO_VOZ_VELOCIDADE", "+10%")
        self.tom = tom or os.getenv("BMO_VOZ_TOM", "+25Hz")
        # caminho do modelo .onnx do Piper (voz pt-BR baixada localmente)
        self.piper_voz = os.getenv("BMO_PIPER_VOZ", "").strip()

    # ── Síntese ──────────────────────────────────────────────────────────

    async def _sintetizar_async(self, texto: str, destino: str) -> None:
        import edge_tts

        comunicador = edge_tts.Communicate(
            texto, self.voz, rate=self.velocidade, pitch=self.tom
        )
        await comunicador.save(destino)

    def _sintetizar_piper(self, texto: str, destino: str) -> None:
        """Síntese 100% local com Piper — nada sai da máquina.

        Requer o pacote ``piper-tts`` e um modelo de voz .onnx pt-BR apontado
        por ``BMO_PIPER_VOZ`` (baixe em github.com/rhasspy/piper voices)."""
        import wave

        if not self.piper_voz:
            raise ValueError(
                "Voz offline (Piper) ativada, mas BMO_PIPER_VOZ não aponta para "
                "um modelo .onnx. Baixe uma voz pt-BR do Piper e configure o caminho."
            )
        from piper.voice import PiperVoice

        voz = PiperVoice.load(self.piper_voz)
        with wave.open(destino, "wb") as wav:
            voz.synthesize(texto, wav)

    def _extensao(self) -> str:
        return ".wav" if self.motor == "piper" else ".mp3"

    def sintetizar(self, texto: str, destino: str | None = None) -> str | None:
        """Gera o áudio da fala e retorna o caminho (None se não há o que falar).

        Formato conforme o motor: .mp3 (edge-tts) ou .wav (Piper, offline)."""
        texto = limpar_para_fala(texto)
        if not texto:
            return None

        if destino is None:
            fd, destino = tempfile.mkstemp(suffix=self._extensao(), prefix="bmo_fala_")
            os.close(fd)

        if self.motor == "piper":
            self._sintetizar_piper(texto, destino)
        else:
            asyncio.run(self._sintetizar_async(texto, destino))
        return destino

    def sintetizar_curto(self, texto: str, destino: str | None = None) -> str | None:
        """Sintetiza um aviso fixo e apara o silêncio das pontas.

        O edge-tts devolve o áudio acolchoado: um "Oi!" de 0,26s vem dentro de
        1,77s de arquivo, quase tudo silêncio. Para o aviso que toca ANTES de
        o microfone abrir isso é tempo morto puro — o usuário fica esperando
        sem poder falar. Como a frase é fixa e sintetizada uma vez só no boot,
        aparar sai de graça.
        """
        caminho = self.sintetizar(texto, destino)
        return _aparar_silencio(caminho) if caminho else None

    # ── Reprodução e lip sync ────────────────────────────────────────────

    @staticmethod
    def _mixer():
        import pygame  # lazy: só carrega se realmente formos tocar áudio

        if not pygame.mixer.get_init():
            from .audio import nome_saida

            saida = nome_saida()
            try:
                pygame.mixer.init(devicename=saida) if saida else pygame.mixer.init()
            except pygame.error:
                # saída escolhida sumiu (fone desconectado): volta ao padrão
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

    def _tocar_arquivo(self, caminho: str, ao_iniciar=None) -> None:
        """Toca um áudio já sintetizado, com lip sync, até o fim."""
        pygame = self._mixer()
        som = pygame.mixer.Sound(caminho)
        envelope = self._calcular_envelope(som)
        canal = som.play()
        if ao_iniciar is not None and canal is not None:
            ao_iniciar(envelope)
        while canal is not None and canal.get_busy():
            time.sleep(0.03)

    def falar_em_partes(self, pedacos: Iterable[str], ao_iniciar=None) -> bool:
        """Fala um texto que ainda está sendo escrito, frase a frase.

        Em vez de esperar o modelo terminar E o TTS sintetizar tudo (dois
        bloqueios em série), a primeira frase já vira áudio assim que fecha.
        Uma thread sintetiza a frase seguinte enquanto a atual toca, então
        só a PRIMEIRA síntese aparece como espera para o usuário.

        ``ao_iniciar(envelope)`` é chamado no começo de CADA frase, com o
        envelope daquela frase — o lip sync acompanha pedaço por pedaço.
        Retorna False se não havia nada falável.
        """
        prontas: queue.Queue = queue.Queue(maxsize=3)
        falhas: list[BaseException] = []

        def sintetizar_em_fundo() -> None:
            try:
                for frase in frases(pedacos):
                    caminho = self.sintetizar(frase)
                    if caminho:
                        # cada frase vem com ~0,9s de silêncio nas pontas; sem
                        # aparar, falar em N frases ficaria MAIS lento que falar
                        # de uma vez só, mesmo começando antes
                        prontas.put(_aparar_silencio(caminho, MARGEM_FRASE))
            except BaseException as e:  # noqa: BLE001 - relançado na thread principal
                falhas.append(e)
            finally:
                prontas.put(None)  # sentinela de fim

        thread = threading.Thread(
            target=sintetizar_em_fundo, name="bmo-tts-stream", daemon=True
        )
        thread.start()

        falou = False
        try:
            while True:
                caminho = prontas.get()
                if caminho is None:
                    break
                try:
                    self._tocar_arquivo(caminho, ao_iniciar)
                    falou = True
                finally:
                    _apagar(caminho)
        finally:
            thread.join(timeout=30)
            _esvaziar(prontas)  # sobras se a reprodução parou no meio

        if falhas and not falou:
            raise falhas[0]  # nada foi dito: quem chamou decide o plano B
        return falou

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
            self._tocar_arquivo(caminho, ao_iniciar)
        finally:
            _apagar(caminho)
        return True
