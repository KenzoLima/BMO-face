"""Escolha dos dispositivos de áudio — de onde o BMO ouve e por onde ele fala.

Por que guardamos o **nome** e não o índice: os índices do PyAudio mudam de
posição quando você pluga um fone ou liga uma webcam, e o índice salvo ontem
pode ser outro microfone hoje. Pior, cada biblioteca tem seu próprio espaço
de índices — o PvRecorder (Porcupine) numera só os dispositivos de captura,
o PyAudio numera tudo, o SDL2 (pygame) usa nomes. O nome é o único
identificador que atravessa as três.

Então o .env guarda nomes, e cada motor resolve o nome para o índice dele na
hora de abrir o áudio. Nome não encontrado (dispositivo desconectado) cai no
padrão do sistema, que é o comportamento de sempre.

Configuração (.env):
    BMO_AUDIO_ENTRADA=Microfone (Realtek HD Audio Mic input)
    BMO_AUDIO_SAIDA=Alto-falantes (Realtek(R) Audio)

Vazio nos dois = usa o dispositivo padrão do Windows.
"""

from __future__ import annotations

import os
from typing import NamedTuple

CHAVE_ENTRADA = "BMO_AUDIO_ENTRADA"
CHAVE_SAIDA = "BMO_AUDIO_SAIDA"

PADRAO_DO_SISTEMA = "(padrão do Windows)"

# O Windows expõe o mesmo microfone por vários host APIs. Listamos um de cada
# aparelho, preferindo o índice mais compatível com o PyAudio/SpeechRecognition.
_PREFERENCIA_HOST = ("MME", "Windows WASAPI", "Windows DirectSound")

# O WDM-KS fica de fora de propósito: é a camada de kernel streaming, que o
# próprio Windows não mostra nas configurações de som. Ela repete todo mundo
# e ainda inventa entradas sem sentido para um microfone ("MIDI (...)",
# "Alto-falante (... output)", "Grupo de microfones 1 ()").

# Dois motivos para o mesmo microfone chegar com nomes diferentes:
#
# 1. O MME corta em 31 caracteres — "Grupo de microfones (Tecnologia" (MME)
#    é o mesmo que "Grupo de microfones (Tecnologia Intel® Smart..." (WASAPI).
# 2. Cada biblioteca decodifica os acentos do driver do seu jeito: o PyAudio
#    entrega "Intel®" e o PvRecorder entrega "Intel<lixo>" para o mesmo texto.
#
# Comparar só a espinha ASCII resolve os dois: acentos, símbolos e pontuação
# saem fora, e sobra o que é estável. Exigimos um prefixo longo para não
# fundir dois aparelhos de nomes parecidos.
_MINIMO_PREFIXO = 20


def _chave(nome: str) -> str:
    """Espinha ASCII do nome — o que sobrevive a truncagem e a acento torto."""
    return "".join(c for c in nome.lower() if c.isascii() and c.isalnum())


def _mesmo_aparelho(a: str, b: str) -> bool:
    chave_a, chave_b = _chave(a), _chave(b)
    if chave_a == chave_b:
        return True
    curta, longa = sorted((chave_a, chave_b), key=len)
    return len(curta) >= _MINIMO_PREFIXO and longa.startswith(curta)


class Dispositivo(NamedTuple):
    indice: int   # índice do PyAudio — válido só nesta execução
    nome: str
    api: str


def _limpar(nome: object) -> str:
    """Conserta o nome vindo do driver antes de mostrá-lo ao usuário.

    O PyAudio entrega os bytes do driver decodificados como latin-1, então
    "Intel®" chega como "IntelÂ®" (mojibake clássico de UTF-8 lido byte a
    byte). Quando a volta latin-1 → UTF-8 funciona, o texto original estava
    ali — se não funcionar, o nome já era latin-1 de verdade e fica como está.
    """
    texto = str(nome or "").strip()
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def _candidatos_entrada() -> list[Dispositivo]:
    """Tudo que o PyAudio enxerga como captura, sem filtrar nem agrupar."""
    try:
        import pyaudio
    except ImportError:
        return []

    pa = None
    try:
        pa = pyaudio.PyAudio()
        achados: list[Dispositivo] = []
        for indice in range(pa.get_device_count()):
            try:
                info = pa.get_device_info_by_index(indice)
                if not info.get("maxInputChannels"):
                    continue  # é só saída
                api = _limpar(pa.get_host_api_info_by_index(info["hostApi"])["name"])
                if api not in _PREFERENCIA_HOST:
                    continue  # WDM-KS e afins: ver comentário lá em cima
                achados.append(Dispositivo(indice, _limpar(info["name"]), api))
            except Exception:
                continue  # um dispositivo problemático não some com a lista
        return achados
    except Exception:
        return []
    finally:
        if pa is not None:
            try:
                pa.terminate()
            except Exception:
                pass


def _prioridade(disp: Dispositivo) -> int:
    return _PREFERENCIA_HOST.index(disp.api) if disp.api in _PREFERENCIA_HOST else 99


def dispositivos_entrada() -> list[Dispositivo]:
    """Microfones disponíveis — um por aparelho, com o nome mais descritivo.

    Cada aparelho vira uma entrada só, mostrando o nome completo (que costuma
    vir do WASAPI) mas guardando o índice do host API mais compatível (MME).
    """
    grupos: list[list[Dispositivo]] = []
    for disp in _candidatos_entrada():
        for grupo in grupos:
            if _mesmo_aparelho(grupo[0].nome, disp.nome):
                grupo.append(disp)
                break
        else:
            grupos.append([disp])

    saida = []
    for grupo in grupos:
        melhor = min(grupo, key=_prioridade)  # índice que mais funciona
        nome = max((d.nome for d in grupo), key=len)  # nome que melhor descreve
        saida.append(Dispositivo(melhor.indice, nome, melhor.api))
    return sorted(saida, key=lambda d: (_prioridade(d), d.nome))


def dispositivos_saida() -> list[str]:
    """Saídas de som que o pygame (SDL2) sabe abrir."""
    try:
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        from pygame._sdl2 import audio as sdl2audio

        return [_limpar(n) for n in sdl2audio.get_audio_device_names(False)]
    except Exception:
        return []


# ── o que está escolhido ────────────────────────────────────────────────────


def entrada_escolhida() -> str:
    return os.getenv(CHAVE_ENTRADA, "").strip()


def saida_escolhida() -> str:
    return os.getenv(CHAVE_SAIDA, "").strip()


def indice_entrada() -> int | None:
    """Índice PyAudio do microfone escolhido; None = padrão do sistema.

    Serve para ``sr.Microphone(device_index=...)`` e para
    ``PyAudio.open(input_device_index=...)``.
    """
    nome = entrada_escolhida()
    if not nome:
        return None
    disponiveis = dispositivos_entrada()
    for disp in disponiveis:
        if disp.nome == nome:
            return disp.indice
    # o nome pode ter sido salvo truncado (ou completo) numa outra sessão
    for disp in disponiveis:
        if _mesmo_aparelho(disp.nome, nome):
            return disp.indice
    return None  # desconectado: volta ao padrão em vez de estourar


def indice_entrada_porcupine() -> int:
    """Índice do MESMO microfone no espaço de índices do PvRecorder.

    O PvRecorder enumera só dispositivos de captura, então a numeração dele
    não bate com a do PyAudio — casamos pelo nome. -1 = padrão do sistema.
    """
    nome = entrada_escolhida()
    if not nome:
        return -1
    try:
        from pvrecorder import PvRecorder

        disponiveis = [_limpar(n) for n in PvRecorder.get_available_devices()]
    except Exception:
        return -1
    if nome in disponiveis:
        return disponiveis.index(nome)
    for i, disponivel in enumerate(disponiveis):
        if _mesmo_aparelho(disponivel, nome):
            return i
    return -1


def nome_saida() -> str | None:
    """Nome da saída escolhida para ``pygame.mixer.init(devicename=...)``."""
    return saida_escolhida() or None
