"""Percepção (STT) — os ouvidos do BMO.

Quatro motores de escuta passiva (wake word), escolhidos por ``criar_ouvidos()``
nesta ordem de preferência:

1. **OuvidosPorcupine**: detecção 100% local via Picovoice — zero requisições.
   Requer PICOVOICE_ACCESS_KEY no .env e um modelo .ppn em ``modelos/``.
2. **OuvidosOpenWakeWord**: wake word local via openWakeWord — sem conta, sem chave.
   Requer o modelo ``modelos/bimo.onnx`` (gerado com ``python treinar_bimo.py``).
3. **OuvidosVosk**: STT offline leve — zero requisições, SEM conta nem chave.
   Requer só o modelo pt-BR em ``modelos/vosk-model-small-pt-*``.
4. **Ouvidos** (último recurso): janelas curtas transcritas na API gratuita do
   Google; cada janela com som gasta requisição.

A escuta **ativa** (o comando após o gatilho) usa **faster-whisper** quando
disponível (local, offline, qualidade superior ao Google gratuito), caindo
para o Google como reserva automática.

O módulo não imprime nada: devolve valores e quem chama decide o feedback.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import speech_recognition as sr

from .audio import indice_entrada, indice_entrada_porcupine

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


def _sem_google() -> bool:
    """Modo offline: BMO_STT_SEM_GOOGLE=1 desliga a reserva na nuvem (Google).

    Com isso, a transcrição do comando fica 100% local (faster-whisper) e o
    BMO nunca gasta requisição de STT. Exige um motor de wake word local
    (Porcupine/OpenWakeWord/Vosk) e o faster-whisper instalado."""
    return os.getenv("BMO_STT_SEM_GOOGLE", "").strip() not in ("", "0")


def contem_wake_word(texto: str, wake_words=WAKE_WORDS_PADRAO) -> bool:
    """True se alguma wake word aparece na transcrição."""
    texto = texto.lower()
    return any(wake in texto for wake in wake_words)


# ── Transcritor Whisper compartilhado ──────────────────────────────────────

class TranscritorWhisper:
    """Transcritor local via faster-whisper — sem rede, sem chave.

    Singleton com carregamento tardio: o modelo só é baixado/carregado na
    primeira chamada a ``transcrever()``. Use ``BMO_WHISPER_MODELO`` no .env
    para escolher o tamanho (tiny/base/small/medium; padrão: small).
    """

    _instancia: "TranscritorWhisper | None" = None
    _indisponivel = False  # True quando faster-whisper não está instalado

    @classmethod
    def obter(cls) -> "TranscritorWhisper | None":
        if cls._indisponivel:
            return None
        if cls._instancia is None:
            try:
                import faster_whisper  # noqa — verifica disponibilidade
                cls._instancia = cls()
            except ImportError:
                cls._indisponivel = True
                return None
        return cls._instancia

    @classmethod
    def precarregar(cls) -> None:
        """Inicia download/carregamento do modelo em thread de fundo.

        Chame logo após criar os ouvidos para que o modelo esteja pronto
        antes do primeiro comando, sem bloquear o boot.
        """
        t = threading.Thread(target=cls.obter, name="whisper-preload", daemon=True)
        t.start()

    def __init__(self) -> None:
        self._nome = os.getenv("BMO_WHISPER_MODELO", "small")
        self._modelo = None
        self._lock = threading.Lock()

    def _carregar(self):
        with self._lock:
            if self._modelo is None:
                from faster_whisper import WhisperModel
                self._modelo = WhisperModel(self._nome, compute_type="int8")
        return self._modelo

    def transcrever(self, audio: sr.AudioData) -> str | None:
        """Converte AudioData → float32 numpy → texto via Whisper."""
        import io
        import wave

        import numpy as np

        modelo = self._carregar()
        wav = audio.get_wav_data(convert_rate=16000, convert_width=2)
        with io.BytesIO(wav) as buf:
            with wave.open(buf) as wf:
                frames = wf.readframes(wf.getnframes())
        amostras = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        segmentos, _ = modelo.transcribe(amostras, language="pt", beam_size=5)
        texto = " ".join(seg.text for seg in segmentos).strip()
        return texto if len(texto) >= TAMANHO_MINIMO_FALA else None


# ── Motores de escuta ───────────────────────────────────────────────────────

class Ouvidos:
    """Captura de voz do microfone com wake word e escuta de comando."""

    def __init__(self, idioma: str = "pt-BR", wake_words=WAKE_WORDS_PADRAO):
        self.idioma = idioma
        self.wake_words = wake_words
        self.reconhecedor = sr.Recognizer()
        self.reconhecedor.energy_threshold = 200
        self.reconhecedor.dynamic_energy_threshold = True

    def abrir_microfone(self) -> sr.Microphone:
        """Cria a fonte de áudio; use como context manager em volta do loop.

        Respeita o microfone escolhido na tela de configurações; sem escolha
        (ou com o dispositivo desconectado), usa o padrão do Windows.
        """
        return sr.Microphone(device_index=indice_entrada())

    def calibrar(self, fonte, duracao: float = 1.5) -> float:
        """Ajusta o limiar de energia ao ruído ambiente; retorna o valor final."""
        self.reconhecedor.adjust_for_ambient_noise(fonte, duration=duracao)
        return self.reconhecedor.energy_threshold

    def _transcrever_google(self, audio) -> str | None:
        if _sem_google():
            return None  # modo offline: sem reserva na nuvem
        try:
            return self.reconhecedor.recognize_google(audio, language=self.idioma)
        except sr.UnknownValueError:
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

        texto = self._transcrever_google(audio)
        if texto and contem_wake_word(texto, self.wake_words):
            return texto
        return None

    def ouvir_comando(self, fonte, timeout: float = 10) -> str | None:
        """Escuta ativa: usa faster-whisper quando disponível, Google como reserva.

        Todas as subclasses que delegam para ``_google.ouvir_comando()``
        herdam automaticamente a melhoria sem nenhuma alteração.
        """
        try:
            audio = self.reconhecedor.listen(fonte, timeout=timeout, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            return None

        whisper = TranscritorWhisper.obter()
        if whisper is not None:
            try:
                texto = whisper.transcrever(audio)
            except Exception:
                texto = self._transcrever_google(audio)
        else:
            texto = self._transcrever_google(audio)

        if texto is None or len(texto.strip()) < TAMANHO_MINIMO_FALA:
            return None
        return texto.strip()


class OuvidosPorcupine:
    """Wake word local (Porcupine) + comando via Whisper/Google.

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

        gravador = PvRecorder(
            frame_length=self.porcupine.frame_length,
            device_index=indice_entrada_porcupine(),  # -1 = padrão do sistema
        )
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
        """Escuta ativa: Whisper quando disponível, Google como reserva."""
        with sr.Microphone(device_index=indice_entrada()) as fonte:
            self._google.calibrar(fonte, duracao=0.5)
            return self._google.ouvir_comando(fonte, timeout=timeout)

    def encerrar(self) -> None:
        self.porcupine.delete()


class OuvidosOpenWakeWord:
    """Wake word local via openWakeWord — sem conta, sem chave, sem rede após setup.

    Detecta "bimo" usando um modelo ONNX leve (~500 KB) que roda em CPU.
    Requer o arquivo ``modelos/bimo.onnx`` — gere-o com::

        python treinar_bimo.py

    O limiar de ativação é ajustável via ``BMO_OWW_LIMIAR`` no .env (padrão: 0.5).
    Valores menores aumentam a sensibilidade; maiores reduzem falsos positivos.
    """

    MODELO_PATH = DIR_MODELOS / "bimo.onnx"
    TAMANHO_CHUNK = 1280   # 80 ms a 16 kHz — janela padrão do openWakeWord
    TAXA_AMOSTRAGEM = 16000

    def __init__(self, limiar: float | None = None, idioma: str = "pt-BR"):
        if not self.MODELO_PATH.is_file():
            raise ValueError(
                f"Modelo openWakeWord não encontrado em '{self.MODELO_PATH}'. "
                "Execute 'python treinar_bimo.py' para gerá-lo automaticamente."
            )
        self._limiar = float(os.getenv("BMO_OWW_LIMIAR", str(limiar or 0.5)))
        self._google = Ouvidos(idioma=idioma)
        self._oww = self._carregar_modelo()

    def _carregar_modelo(self):
        from openwakeword.model import Model
        return Model(wakeword_models=[str(self.MODELO_PATH)], inference_framework="onnx")

    def esperar_wake_word(self) -> str:
        """Bloqueia até ouvir a wake word. 100% local, ~2% CPU."""
        import pyaudio
        import numpy as np

        audio = pyaudio.PyAudio()
        fluxo = audio.open(
            rate=self.TAXA_AMOSTRAGEM,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            input_device_index=indice_entrada(),
            frames_per_buffer=self.TAMANHO_CHUNK,
        )
        try:
            while True:
                dados = fluxo.read(self.TAMANHO_CHUNK, exception_on_overflow=False)
                chunk = np.frombuffer(dados, dtype=np.int16)
                predicoes = self._oww.predict(chunk)
                if any(v >= self._limiar for v in predicoes.values()):
                    return "wake word local"
        finally:
            fluxo.stop_stream()
            fluxo.close()
            audio.terminate()

    def ouvir_comando(self, timeout: float = 10) -> str | None:
        """Escuta ativa: Whisper quando disponível, Google como reserva."""
        with sr.Microphone(device_index=indice_entrada()) as fonte:
            self._google.calibrar(fonte, duracao=0.5)
            return self._google.ouvir_comando(fonte, timeout=timeout)

    def encerrar(self) -> None:
        pass


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
            input_device_index=indice_entrada(),
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
        """Escuta ativa: Whisper quando disponível, Google como reserva."""
        with sr.Microphone(device_index=indice_entrada()) as fonte:
            self._google.calibrar(fonte, duracao=0.5)
            return self._google.ouvir_comando(fonte, timeout=timeout)

    def encerrar(self) -> None:
        pass  # o modelo é liberado com o processo


def criar_ouvidos() -> OuvidosPorcupine | OuvidosOpenWakeWord | OuvidosVosk | Ouvidos:
    """Escolhe o melhor motor disponível: Porcupine → OpenWakeWord → Vosk → Google.

    Após escolher o motor, pré-carrega o Whisper em background para que o
    modelo esteja pronto antes do primeiro comando do usuário.
    """
    motor: OuvidosPorcupine | OuvidosOpenWakeWord | OuvidosVosk | Ouvidos

    try:
        motor = OuvidosPorcupine()
    except Exception as e:
        print(f"[BMO] Porcupine indisponível: {e}")
        try:
            motor = OuvidosOpenWakeWord()
        except Exception as e:
            print(f"[BMO] OpenWakeWord indisponível: {e}")
            try:
                motor = OuvidosVosk()
            except Exception as e:
                print(f"[BMO] Vosk indisponível: {e}")
                print("[BMO] Usando escuta passiva via Google (gasta requisições).")
                motor = Ouvidos()

    # Pré-aquece o Whisper em background — elimina latência no 1º comando
    TranscritorWhisper.precarregar()
    return motor
