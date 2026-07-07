"""Testes da busca na internet — sem rede (a chamada real é substituída)."""

import bmo.hands.web as web
from bmo.hands import executar_ferramenta, listar_ferramentas
from bmo.hands.web import buscar_na_internet

RESULTADO_FALSO = [
    {
        "title": "Clima em Londrina hoje",
        "body": "Previsão do tempo: " + "x" * 500,  # maior que o limite de resumo
        "href": "https://exemplo.com/clima",
    }
]


def test_ferramenta_registrada():
    assert "buscar_na_internet" in {f.nome for f in listar_ferramentas()}


def test_busca_mapeia_e_trunca_resultados(monkeypatch):
    monkeypatch.setattr(web, "_executar_busca", lambda c, m: RESULTADO_FALSO)
    resultado = buscar_na_internet("clima londrina")

    assert resultado["sucesso"] is True
    assert resultado["total"] == 1
    item = resultado["resultados"][0]
    assert item["titulo"] == "Clima em Londrina hoje"
    assert len(item["resumo"]) <= web.LIMITE_RESUMO
    assert item["url"] == "https://exemplo.com/clima"


def test_consulta_vazia_e_recusada():
    assert buscar_na_internet("   ")["sucesso"] is False


def test_falha_de_rede_vira_erro_e_nao_excecao(monkeypatch):
    def explode(consulta, max_resultados):
        raise ConnectionError("sem internet")

    monkeypatch.setattr(web, "_executar_busca", explode)
    resultado = buscar_na_internet("qualquer coisa")
    assert resultado["sucesso"] is False
    assert "falhou" in resultado["erro"]


def test_zero_resultados_avisa_sem_erro(monkeypatch):
    monkeypatch.setattr(web, "_executar_busca", lambda c, m: [])
    resultado = buscar_na_internet("kjhsdkfjhsdkfjh")
    assert resultado["sucesso"] is True
    assert resultado["total"] == 0
    assert "aviso" in resultado


def test_dispatch_via_registry(monkeypatch):
    monkeypatch.setattr(web, "_executar_busca", lambda c, m: RESULTADO_FALSO)
    resultado = executar_ferramenta("buscar_na_internet", {"consulta": "teste"})
    assert resultado["sucesso"] is True
