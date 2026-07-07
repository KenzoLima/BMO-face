"""Testes dos lembretes — só validação e lógica pura (não toca o Agendador)."""

from bmo.brain.prompts import system_prompt_atual
from bmo.hands import listar_ferramentas
from bmo.hands.reminders import (
    LIMITE_MENSAGEM,
    _interpretar_data_hora,
    _sanitizar_mensagem,
    criar_lembrete,
)


def test_ferramentas_de_lembrete_registradas():
    nomes = {f.nome for f in listar_ferramentas()}
    assert {"criar_lembrete", "listar_lembretes", "cancelar_lembrete"} <= nomes


def test_data_hora_valida_e_interpretada():
    momento = _interpretar_data_hora("2030-12-25 09:30")
    assert (momento.year, momento.hour, momento.minute) == (2030, 9, 30)
    assert _interpretar_data_hora("2030-12-25T09:30") is not None


def test_formato_invalido_e_recusado():
    assert _interpretar_data_hora("25/12/2030 9h") is None
    resultado = criar_lembrete("tomar água", "amanhã de manhã")
    assert resultado["sucesso"] is False
    assert "YYYY-MM-DD" in resultado["erro"]


def test_data_no_passado_e_recusada():
    resultado = criar_lembrete("tarde demais", "2020-01-01 08:00")
    assert resultado["sucesso"] is False
    assert "passou" in resultado["erro"]


def test_sanitizacao_remove_caracteres_perigosos():
    limpo = _sanitizar_mensagem('tomar "remédio" `agora` por $10')
    assert '"' not in limpo and "`" not in limpo and "$" not in limpo


def test_mensagem_longa_e_cortada():
    assert len(_sanitizar_mensagem("x" * 500)) == LIMITE_MENSAGEM


def test_system_prompt_carrega_o_relogio():
    from datetime import datetime

    prompt = system_prompt_atual()
    assert "CONTEXTO ATUAL" in prompt
    assert f"{datetime.now():%d/%m/%Y}" in prompt
