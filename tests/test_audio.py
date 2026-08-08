"""Testes da escolha de dispositivos de audio — sem hardware, sem janela."""

from __future__ import annotations

import pytest

from bmo import audio
from bmo.audio import Dispositivo, _chave, _mesmo_aparelho

# Nomes reais de uma maquina Windows, com as duas armadilhas:
# o MME corta em 31 caracteres e o PvRecorder estraga o "®".
COMPLETO = "Grupo de microfones (Tecnologia Intel® Smart Sound para microfones digitais)"
TRUNCADO = "Grupo de microfones (Tecnologia"
MOJIBAKE = "Grupo de microfones (Tecnologia Intel� Smart Sound para microfones digitais)"
WEBCAM = "Microfone (Iriun Webcam)"


@pytest.fixture(autouse=True)
def sem_escolha(monkeypatch):
    monkeypatch.delenv(audio.CHAVE_ENTRADA, raising=False)
    monkeypatch.delenv(audio.CHAVE_SAIDA, raising=False)


# --- casamento de nomes ---


def test_nome_truncado_pelo_mme_e_o_mesmo_aparelho():
    assert _mesmo_aparelho(COMPLETO, TRUNCADO)


def test_acento_estragado_e_o_mesmo_aparelho():
    """PyAudio devolve 'Intel®', PvRecorder devolve 'Intel<lixo>'."""
    assert _mesmo_aparelho(COMPLETO, MOJIBAKE)
    assert _chave(COMPLETO) == _chave(MOJIBAKE)


def test_aparelhos_diferentes_nao_se_fundem():
    assert not _mesmo_aparelho(COMPLETO, WEBCAM)
    assert not _mesmo_aparelho("Microfone (USB)", "Microfone (USB) 2")


def test_prefixo_curto_nao_basta():
    """Dois nomes que so compartilham o comeco nao podem virar um."""
    assert not _mesmo_aparelho("Microfone A", "Microfone B")


# --- lista de microfones ---


def _fingir_dispositivos(monkeypatch, candidatos):
    monkeypatch.setattr(audio, "_candidatos_entrada", lambda: candidatos)


def test_mesmo_aparelho_em_varios_apis_vira_uma_entrada_so(monkeypatch):
    _fingir_dispositivos(monkeypatch, [
        Dispositivo(1, TRUNCADO, "MME"),
        Dispositivo(12, COMPLETO, "Windows WASAPI"),
        Dispositivo(6, COMPLETO, "Windows DirectSound"),
        Dispositivo(2, WEBCAM, "MME"),
    ])
    lista = audio.dispositivos_entrada()

    assert len(lista) == 2
    microfone = next(d for d in lista if "Grupo" in d.nome)
    assert microfone.nome == COMPLETO, "mostra o nome completo, nao o truncado"
    assert microfone.indice == 1, "usa o indice do MME, o mais compativel"


def test_lista_vazia_quando_nao_ha_audio(monkeypatch):
    _fingir_dispositivos(monkeypatch, [])
    assert audio.dispositivos_entrada() == []


# --- resolucao nome -> indice ---


def test_sem_escolha_usa_o_padrao_do_sistema():
    assert audio.indice_entrada() is None
    assert audio.indice_entrada_porcupine() == -1
    assert audio.nome_saida() is None


def test_nome_salvo_vira_indice(monkeypatch):
    _fingir_dispositivos(monkeypatch, [
        Dispositivo(1, TRUNCADO, "MME"),
        Dispositivo(12, COMPLETO, "Windows WASAPI"),
    ])
    monkeypatch.setenv(audio.CHAVE_ENTRADA, COMPLETO)
    assert audio.indice_entrada() == 1


def test_nome_salvo_truncado_ainda_resolve(monkeypatch):
    """Escolha salva por uma versao antiga (nome cortado) continua valendo."""
    _fingir_dispositivos(monkeypatch, [Dispositivo(12, COMPLETO, "Windows WASAPI")])
    monkeypatch.setenv(audio.CHAVE_ENTRADA, TRUNCADO)
    assert audio.indice_entrada() == 12


def test_dispositivo_desconectado_cai_no_padrao(monkeypatch):
    """Desplugar o microfone escolhido nao pode quebrar o BMO."""
    _fingir_dispositivos(monkeypatch, [Dispositivo(2, WEBCAM, "MME")])
    monkeypatch.setenv(audio.CHAVE_ENTRADA, COMPLETO)
    assert audio.indice_entrada() is None


def test_porcupine_usa_o_indice_do_espaco_dele(monkeypatch):
    """O PvRecorder numera so as capturas: a posicao nao bate com a do PyAudio."""
    class PvFake:
        @staticmethod
        def get_available_devices():
            return [WEBCAM, MOJIBAKE]  # e ainda com o acento torto

    monkeypatch.setitem(
        __import__("sys").modules, "pvrecorder",
        type("mod", (), {"PvRecorder": PvFake}),
    )
    monkeypatch.setenv(audio.CHAVE_ENTRADA, COMPLETO)
    assert audio.indice_entrada_porcupine() == 1

    monkeypatch.setenv(audio.CHAVE_ENTRADA, WEBCAM)
    assert audio.indice_entrada_porcupine() == 0

    monkeypatch.setenv(audio.CHAVE_ENTRADA, "Microfone fantasma")
    assert audio.indice_entrada_porcupine() == -1


def test_saida_escolhida_e_repassada():
    import os

    os.environ[audio.CHAVE_SAIDA] = "Alto-falantes (Realtek(R) Audio)"
    try:
        assert audio.nome_saida() == "Alto-falantes (Realtek(R) Audio)"
    finally:
        del os.environ[audio.CHAVE_SAIDA]
