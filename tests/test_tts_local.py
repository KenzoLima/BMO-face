"""Testes da selecao de motor de voz (edge nuvem x piper offline).

So exercitam a logica pura da Boca; nao sintetizam audio de verdade."""

from __future__ import annotations

import pytest

from bmo.mouth import Boca, limpar_para_fala


def test_extensao_por_motor():
    assert Boca(motor="piper")._extensao() == ".wav"
    assert Boca(motor="edge")._extensao() == ".mp3"


def test_motor_padrao_e_edge(monkeypatch):
    monkeypatch.delenv("BMO_TTS", raising=False)
    assert Boca().motor == "edge"


def test_env_bmo_tts_seleciona_piper(monkeypatch):
    monkeypatch.setenv("BMO_TTS", "piper")
    assert Boca().motor == "piper"


def test_piper_sem_voz_configurada_da_erro_claro(monkeypatch):
    monkeypatch.delenv("BMO_PIPER_VOZ", raising=False)
    boca = Boca(motor="piper")
    with pytest.raises(ValueError):
        boca._sintetizar_piper("oi", "/tmp/x.wav")


def test_texto_vazio_nao_chama_sintese():
    # "[feliz]" e so expressao de rosto -> vira vazio -> None (nao toca no piper)
    assert limpar_para_fala("[feliz]") == ""
    assert Boca(motor="piper").sintetizar("[feliz]") is None
