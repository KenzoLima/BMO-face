"""Percepção (STT) — os ouvidos do BMO.

Três motores de escuta passiva (wake word), escolhidos por ``criar_ouvidos()``
nesta ordem de preferência:

1. **OuvidosPorcupine**: detecção 100% local via Picovoice — zero requisições.
   Requer PICOVOICE_ACCESS_KEY no .env e um modelo .ppn em ``modelos/``.
2. **OuvidosVosk**: STT offline leve — zero requisições, SEM conta nem chave.
   Requer só o modelo pt-BR em ``modelos/vosk-model-small-pt-*``.
3. **Ouvidos** (último recurso): o esquema original — janelas curtas
   transcritas na API gratuita do Google; cada janela com som gasta requisição.

A escuta **ativa** (o comando após o gatilho) usa o Google nos três casos.
O módulo não imprime nada: devolve valores e quem chama decide o feedback.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import speech_recognition as sr

DIR_MODELOS = Path(__file__).resolve().parent.parent / "modelos"

# O reconhecedor ouve "BMO" falado como "bimo"/"beemo"; casamento por
# substring, então "ei bimo" e "oi bimo" já estão cobertos por "bimo".
WAKE_WORDS_PADRAO = ("bimo", "beemo", "bemo", "bmo")

# "bimo" não existe no vocabulário do modelo Vosk pt-BR; estas são as
# palavras reais do vocabulário que soam como "bimo" — quando você fala
# "bimo", o reconhecedor (restrito a elas) acende uma destas. Conjunto
# calibrado empiricamente (ver tests/calibrar_wake_word.py).
WAKE_WORDS_VOSK = ("bio", "bico", "mimo", "bi")

# "bi" é sílaba, não palavra do português falada sozinha — quando aparece
# como token isolado é quase certamente alguém chamando o BMO, então ela
# não passa pelo teto de confiança (que existe para palavras reais).
ANCORAS_SEM_TETO = ("bi",)



TAMANHO_MINIMO_FALA = 3  # transcrições menores que isso são ruído


def contem_wake_word(texto: str, wake_words=WAKE_WORDS_PADRAO) -> bool:
    """True se alguma wake word aparece na transcrição."""
    texto = texto.lower()
    return any(wake in texto for wake in wake_words)


class Ouvidos:
    """Captura de voz do microfone com wake word e escuta de comando."""

    def __init__(self, idioma: str = "pt-BR", wake_words=WAKE_WORDS_PADRAO):
        self.idioma = idioma
        self.wake_words = wake_words
        self.reconhecedor = sr.Recognizer()
        self.reconhecedor.energy_threshold = 200
        self.reconhecedor.dynamic_energy_threshold = True

    def abrir_microfone(self) -> sr.Microphone:
        """Cria a fonte de áudio; use como context manager em volta do loop."""
        return sr.Microphone()

    def calibrar(self, fonte, duracao: float = 1.5) -> float:
        """Ajusta o limiar de energia ao ruído ambiente; retorna o valor final."""
        self.reconhecedor.adjust_for_ambient_noise(fonte, duration=duracao)
        return self.reconhecedor.energy_threshold

    def _transcrever(self, audio) -> str | None:
        try:
            return self.reconhecedor.recognize_google(audio, language=self.idioma)
        except sr.UnknownValueError:  # fala ininteligível / ruído
            return None

    def esperar_wake_word(self, fonte) -> str | None:
        """Uma janela curta de escuta passiva.

        Retorna a transcrição que ativou o gatilho, ou None se nada foi ouvido
        (chame de novo em loop — janelas curtas mantêm o Ctrl+C responsivo).
        """
        try:
            audio = self.reconhecedor.listen(fonte, timeout=2, phrase_time_limit=3)
        except sr.WaitTimeoutError:
            return None

        texto = self._transcrever(audio)
        if texto and contem_wake_word(texto, self.wake_words):
            return texto
        return None

    def ouvir_comando(self, fonte, timeout: float = 10) -> str | None:
        """Escuta ativa: captura o comando completo após a wake word.

        ``timeout`` menor é usado no modo conversa (respostas encadeadas).
        """
        try:
            audio = self.reconhecedor.listen(fonte, timeout=timeout, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            return None

        texto = self._transcrever(audio)
        if texto is None or len(texto.strip()) < TAMANHO_MINIMO_FALA:
            return None
        return texto.strip()


class OuvidosPorcupine:
    """Wake word local (Porcupine) + comando via Google.

    A fase passiva processa o áudio em CPU, offline, sem custo por requisição.
    Detectou o gatilho → abre o microfone do SpeechRecognition só para o comando.
    """

    def __init__(self, sensibilidade: float | None = None, idioma: str = "pt-BR"):
        chave = os.getenv("PICOVOICE_ACCESS_KEY")
        if not chave:
            raise ValueError(
                "PICOVOICE_ACCESS_KEY ausente no .env "
                "(crie grátis em console.picovoice.ai)"
            )

        caminho_ppn = os.getenv("BMO_WAKE_WORD_PPN") or self._achar_ppn()
        if not caminho_ppn or not Path(caminho_ppn).is_file():
            raise ValueError(
                "Modelo de wake word (.ppn) não encontrado. Treine a palavra "
                "'Bimo' (Português, Windows) em console.picovoice.ai e salve o "
                f"arquivo em '{DIR_MODELOS}' (ou aponte BMO_WAKE_WORD_PPN no .env)."
            )

        params_pt = DIR_MODELOS / "porcupine_params_pt.pv"
        if not params_pt.is_file():
            raise ValueError(f"Modelo de idioma ausente: '{params_pt}'")

        if sensibilidade is None:
            sensibilidade = float(os.getenv("BMO_WAKE_SENSIBILIDADE", "0.6"))

        import pvporcupine  # lazy: dependência opcional do modo local

        self.porcupine = pvporcupine.create(
            access_key=chave,
            keyword_paths=[str(caminho_ppn)],
            model_path=str(params_pt),
            sensitivities=[sensibilidade],
        )
        self._google = Ouvidos(idioma=idioma)  # reuso para a fase ativa

    @staticmethod
    def _achar_ppn() -> str | None:
        candidatos = sorted(DIR_MODELOS.glob("*.ppn")) if DIR_MODELOS.is_dir() else []
        return str(candidatos[0]) if candidatos else None

    def esperar_wake_word(self) -> str:
        """Bloqueia até ouvir a wake word. Local, sem rede, ~1% de CPU."""
        from pvrecorder import PvRecorder

        gravador = PvRecorder(frame_length=self.porcupine.frame_length)
        gravador.start()
        try:
            while True:
                quadro = gravador.read()
                if self.porcupine.process(quadro) >= 0:
                    return "wake word local"
        finally:
            gravador.stop()
            gravador.delete()

    def ouvir_comando(self, timeout: float = 10) -> str | None:
        """Escuta ativa via Google (1 requisição por comando)."""
        with sr.Microphone() as fonte:
            self._google.calibrar(fonte, duracao=0.5)
            return self._google.ouvir_comando(fonte, timeout=timeout)

    def encerrar(self) -> None:
        self.porcupine.delete()


class OuvidosVosk:
    """Wake word local via Vosk (STT offline) — sem conta, sem chave, sem rede.

    Transcreve continuamente no CPU com uma gramática restrita às wake words:
    o reconhecedor só "enxerga" essas palavras (o resto vira [unk]), o que o
    transforma num detector de palavra-chave barato e razoavelmente preciso.
    """

    TAXA_AMOSTRAGEM = 16000
    TAMANHO_BLOCO = 4000  # 0.25s por leitura

    def __init__(self, wake_words=None, idioma: str = "pt-BR"):
        caminho = os.getenv("BMO_VOSK_MODELO") or self._achar_modelo()
        if not caminho or not Path(caminho).is_dir():
            raise ValueError(
                "Modelo Vosk não encontrado. Baixe 'vosk-model-small-pt-0.3' de "
                f"alphacephei.com/vosk/models e extraia em '{DIR_MODELOS}'."
            )

        if wake_words is None:
            personalizadas = os.getenv("BMO_WAKE_VOSK", "")
            wake_words = (
                tuple(w.strip().lower() for w in personalizadas.split(",") if w.strip())
                or WAKE_WORDS_VOSK
            )

        from vosk import Model, SetLogLevel

        SetLogLevel(-1)  # silencia o log interno do Kaldi
        self.modelo = Model(str(caminho))
        self.wake_words = wake_words
        self._google = Ouvidos(idioma=idioma)  # reuso para a fase ativa

    @staticmethod
    def _achar_modelo() -> str | None:
        if not DIR_MODELOS.is_dir():
            return None
        candidatos = sorted(DIR_MODELOS.glob("vosk-model-*"))
        return str(candidatos[0]) if candidatos else None

    def _criar_reconhecedor(self):
        from vosk import KaldiRecognizer

        try:
            gramatica = json.dumps(list(self.wake_words) + ["[unk]"])
            rec = KaldiRecognizer(self.modelo, self.TAXA_AMOSTRAGEM, gramatica)
        except Exception:  # gramática indisponível → decodificação aberta
            rec = KaldiRecognizer(self.modelo, self.TAXA_AMOSTRAGEM)
        rec.SetWords(True)  # habilita confiança por palavra nos resultados finais
        return rec

    # Precisão do gatilho — regras calibradas empiricamente
    # (tests/calibrar_wake_word.py). A sacada: "bimo" não existe no
    # vocabulário, então quando o usuário CHAMA o BMO a âncora acende com
    # confiança MÉDIA (soa parecido, não igual); quando alguém fala a
    # palavra real em conversa ("o bico do passarinho"), a confiança é ~1.0.
    # Aceitamos só a banda do meio, em falas curtas.
    MAX_TOKENS_FINAL = 4

    def _banda_confianca(self) -> tuple[float, float]:
        minimo = float(os.getenv("BMO_WAKE_CONF_MIN", "0.30"))
        maximo = float(os.getenv("BMO_WAKE_CONF_MAX", "0.92"))
        return minimo, maximo

    def _duracao_minima(self) -> float:
        # "bimo" inteiro absorvido numa âncora dura ≥0.24s; palavras curtas
        # dentro de frases ("vi" em "eu vi você") duram ~0.15s.
        return float(os.getenv("BMO_WAKE_DURACAO_MIN", "0.18"))

    def _checar_final(self, resultado: dict) -> str | None:
        palavras = resultado.get("result", [])
        if not palavras or len(palavras) > self.MAX_TOKENS_FINAL:
            return None  # fala longa = conversa, não chamada

        minimo, maximo = self._banda_confianca()
        dur_min = self._duracao_minima()
        ancoras = [p for p in palavras if p.get("word") in self.wake_words]
        if any(
            p.get("conf", 0) > maximo and p["word"] not in ANCORAS_SEM_TETO
            for p in ancoras
        ):
            return None  # palavra real dita com clareza = conversa
        for p in ancoras:
            duracao = p.get("end", 0) - p.get("start", 0)
            if p.get("conf", 0) >= minimo and duracao >= dur_min:
                return p["word"]
        return None

    def esperar_wake_word(self) -> str:
        """Bloqueia até ouvir a wake word. Local, sem rede."""
        import pyaudio

        reconhecedor = self._criar_reconhecedor()
        audio = pyaudio.PyAudio()
        fluxo = audio.open(
            rate=self.TAXA_AMOSTRAGEM,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.TAMANHO_BLOCO,
        )
        try:
            while True:
                dados = fluxo.read(self.TAMANHO_BLOCO, exception_on_overflow=False)
                if reconhecedor.AcceptWaveform(dados):
                    palavra = self._checar_final(json.loads(reconhecedor.Result()))
                    if palavra:
                        return palavra
        finally:
            fluxo.stop_stream()
            fluxo.close()
            audio.terminate()

    def ouvir_comando(self, timeout: float = 10) -> str | None:
        """Escuta ativa via Google (1 requisição por comando)."""
        with sr.Microphone() as fonte:
            self._google.calibrar(fonte, duracao=0.5)
            return self._google.ouvir_comando(fonte, timeout=timeout)

    def encerrar(self) -> None:
        pass  # o modelo é liberado com o processo


def criar_ouvidos() -> OuvidosPorcupine | OuvidosVosk | Ouvidos:
    """Escolhe o melhor motor disponível: Porcupine → Vosk → Google."""
    try:
        return OuvidosPorcupine()
    except Exception as e:
        print(f"[BMO] Porcupine indisponível: {e}")

    try:
        return OuvidosVosk()
    except Exception as e:
        print(f"[BMO] Vosk indisponível: {e}")

    print("[BMO] Usando escuta passiva via Google (gasta requisições).")
    return Ouvidos()
