"""Testes do cerebro local/hibrido (roteamento de provedor e fallback).

Nao dependem de openai/google instalados: usamos provedores falsos e
monkeypatch nas classes reais dentro de bmo.brain.agent.
"""

from __future__ import annotations

import pytest

from bmo.brain import agent


class _FakeProv:
    def __init__(self, *a, **k):
        pass

    def responder(self, texto, historico):
        return f"[feliz] {self.nome} respondeu"


class FakeLocal(_FakeProv):
    nome = "local"


class FakeGemini(_FakeProv):
    nome = "gemini"


class FakeGroq(_FakeProv):
    nome = "groq"


@pytest.fixture(autouse=True)
def _fakes(monkeypatch):
    monkeypatch.setattr(agent, "ProvedorLocal", FakeLocal)
    monkeypatch.setattr(agent, "ProvedorGemini", FakeGemini)
    monkeypatch.setattr(agent, "ProvedorGroq", FakeGroq)


# --- _criar_provedor ---


def test_local_e_um_provedor_valido():
    assert agent._criar_provedor("local").nome == "local"


def test_provedor_invalido_menciona_local():
    with pytest.raises(ValueError) as e:
        agent._criar_provedor("xpto")
    assert "local" in str(e.value)


# --- _criar_reserva (no modo local, a reserva e a nuvem) ---


def test_reserva_do_local_e_gemini_quando_ha_chave(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert agent._criar_reserva("local").nome == "gemini"


def test_reserva_do_local_cai_pra_groq_sem_gemini(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert agent._criar_reserva("local").nome == "groq"


def test_reserva_none_sem_nenhuma_chave(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert agent._criar_reserva("local") is None


# --- hibrido: local falha -> nuvem assume ---


def test_hibrido_local_falha_cai_pra_nuvem():
    class LocalQuebra:
        nome = "local"

        def responder(self, texto, historico):
            raise RuntimeError("timeout do modelo local")

    class NuvemOk:
        nome = "gemini"

        def responder(self, texto, historico):
            return "[feliz] resposta da nuvem"

    cerebro = agent.Cerebro(provedor=LocalQuebra(), reserva=NuvemOk())
    resposta = cerebro.responder("oi")
    assert "nuvem" in resposta
    # a conversa (com a resposta boa) entra no historico
    assert cerebro.historico[-1]["content"] == "[feliz] resposta da nuvem"
