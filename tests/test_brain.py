"""Testes do Cerebro — lógica de fallback e histórico, sem chamadas de API.

Provedores falsos são injetados no Cerebro, então nenhuma chave é necessária.
"""

import pytest

from bmo.brain.agent import MAX_MENSAGENS_HISTORICO, Cerebro


class ProvedorFake:
    def __init__(self, nome="fake", resposta="[feliz] Oi! Bip!", falha=False):
        self.nome = nome
        self.resposta = resposta
        self.falha = falha
        self.chamadas = 0

    def responder(self, texto, historico):
        self.chamadas += 1
        if self.falha:
            raise RuntimeError("quota estourada (simulado)")
        return self.resposta


@pytest.fixture
def sem_reserva():
    """Reserva 'desligada' — objeto sentinela False evita autocriação via env."""
    return None


def novo_cerebro(provedor, reserva=None):
    cerebro = Cerebro(provedor=provedor, reserva=reserva or ProvedorFake("reserva-inerte"))
    if reserva is None:
        cerebro.reserva = None
    return cerebro


def test_resposta_normal_usa_so_o_primario():
    primario = ProvedorFake("primario")
    reserva = ProvedorFake("reserva")
    cerebro = novo_cerebro(primario, reserva)

    assert cerebro.responder("oi bmo") == "[feliz] Oi! Bip!"
    assert primario.chamadas == 1
    assert reserva.chamadas == 0


def test_fallback_assume_quando_primario_falha():
    primario = ProvedorFake("primario", falha=True)
    reserva = ProvedorFake("reserva", resposta="[focado] Reserva no comando!")
    cerebro = novo_cerebro(primario, reserva)

    assert cerebro.responder("oi") == "[focado] Reserva no comando!"
    assert reserva.chamadas == 1


def test_sem_reserva_vira_mensagem_falavel_e_nao_excecao():
    cerebro = novo_cerebro(ProvedorFake(falha=True))
    resposta = cerebro.responder("oi")
    assert resposta.startswith("[triste]")


def test_falha_dupla_vira_mensagem_falavel():
    cerebro = novo_cerebro(ProvedorFake(falha=True), ProvedorFake(falha=True))
    assert cerebro.responder("oi").startswith("[triste]")


def test_historico_guarda_a_conversa():
    cerebro = novo_cerebro(ProvedorFake())
    cerebro.responder("primeira mensagem")
    assert cerebro.historico == [
        {"role": "user", "content": "primeira mensagem"},
        {"role": "assistant", "content": "[feliz] Oi! Bip!"},
    ]


def test_falha_total_nao_entra_no_historico():
    cerebro = novo_cerebro(ProvedorFake(falha=True))
    cerebro.responder("oi")
    assert cerebro.historico == []


def test_historico_e_podado():
    cerebro = novo_cerebro(ProvedorFake())
    for i in range(MAX_MENSAGENS_HISTORICO):
        cerebro.responder(f"mensagem {i}")
    assert len(cerebro.historico) == MAX_MENSAGENS_HISTORICO


def test_esquecer_limpa_a_memoria():
    cerebro = novo_cerebro(ProvedorFake())
    cerebro.responder("oi")
    cerebro.esquecer()
    assert cerebro.historico == []
