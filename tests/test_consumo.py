"""Testes do contador de requisicoes ao LLM — disco temporario, sem API."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from bmo import consumo


@pytest.fixture(autouse=True)
def dados_temporarios(tmp_path, monkeypatch):
    """Isola o consumo.json e zera o cache entre os testes."""
    monkeypatch.setattr(consumo, "_caminho", lambda: tmp_path / "consumo.json")
    monkeypatch.delenv("BMO_LIMITE_REQUISICOES_DIA", raising=False)
    consumo.esquecer_cache()
    yield tmp_path
    consumo.esquecer_cache()


# --- contagem ---


def test_comeca_zerado_e_cheio():
    assert consumo.gastas_hoje() == 0
    assert consumo.fracao_restante() == 1.0
    assert consumo.restantes_hoje() == consumo.limite_diario()


def test_registrar_gasta_e_o_medidor_esvazia():
    monta = consumo.fracao_restante()
    for _ in range(10):
        consumo.registrar("gemini")

    assert consumo.gastas_hoje() == 10
    assert consumo.gastas_hoje("gemini") == 10
    assert consumo.fracao_restante() < monta


def test_conta_por_provedor_e_no_total():
    consumo.registrar("gemini", 7)
    consumo.registrar("groq", 3)

    assert consumo.gastas_hoje("gemini") == 7
    assert consumo.gastas_hoje("groq") == 3
    assert consumo.gastas_hoje("local") == 0
    assert consumo.gastas_hoje() == 10


def test_persiste_entre_sessoes(dados_temporarios):
    consumo.registrar("gemini", 5)
    consumo.esquecer_cache()  # simula reabrir o BMO

    assert consumo.gastas_hoje("gemini") == 5
    assert (dados_temporarios / "consumo.json").exists()


def test_vira_o_dia_e_zera(dados_temporarios):
    ontem = (date.today() - timedelta(days=1)).isoformat()
    (dados_temporarios / "consumo.json").write_text(
        json.dumps({"data": ontem, "provedores": {"gemini": 200}}), encoding="utf-8"
    )
    consumo.esquecer_cache()

    assert consumo.gastas_hoje() == 0
    assert consumo.fracao_restante() == 1.0


# --- limite ---


def test_limite_vem_do_env(monkeypatch):
    monkeypatch.setenv("BMO_LIMITE_REQUISICOES_DIA", "40")
    consumo.registrar("gemini", 10)
    assert consumo.limite_diario() == 40
    assert consumo.restantes_hoje() == 30
    assert consumo.fracao_restante() == pytest.approx(0.75)


@pytest.mark.parametrize("lixo", ["", "  ", "abc", "0", "-5", "3.7"])
def test_limite_invalido_cai_no_padrao(monkeypatch, lixo):
    monkeypatch.setenv("BMO_LIMITE_REQUISICOES_DIA", lixo)
    assert consumo.limite_diario() == consumo.LIMITE_PADRAO


def test_estourar_o_limite_para_em_zero(monkeypatch):
    monkeypatch.setenv("BMO_LIMITE_REQUISICOES_DIA", "5")
    consumo.registrar("gemini", 50)
    assert consumo.restantes_hoje() == 0
    assert consumo.fracao_restante() == 0.0  # nunca negativo


# --- robustez: contar nao pode derrubar o BMO ---


def test_json_corrompido_nao_quebra(dados_temporarios):
    (dados_temporarios / "consumo.json").write_text("{{{ isto nao e json", encoding="utf-8")
    consumo.esquecer_cache()

    assert consumo.gastas_hoje() == 0
    consumo.registrar("gemini")
    assert consumo.gastas_hoje() == 1


def test_disco_somente_leitura_nao_quebra(monkeypatch, tmp_path):
    def falhar(*_a, **_k):
        raise OSError("disco somente leitura")

    monkeypatch.setattr(consumo.Path, "write_text", falhar)
    consumo.registrar("gemini", 3)
    assert consumo.gastas_hoje() == 3  # segue valendo em memoria
