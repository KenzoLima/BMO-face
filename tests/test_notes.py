"""Testes do caderno (memória de longo prazo) — vault temporário, sem API."""

import pytest

from bmo.hands import executar_ferramenta, listar_ferramentas
from bmo.hands.notes import anotar, consultar_anotacoes, memorias_relevantes


@pytest.fixture(autouse=True)
def caderno_temporario(tmp_path, monkeypatch):
    monkeypatch.setenv("BMO_VAULT", str(tmp_path / "vault"))
    return tmp_path / "vault"


def test_ferramentas_do_caderno_registradas():
    nomes = {f.nome for f in listar_ferramentas()}
    assert {"anotar", "consultar_anotacoes"} <= nomes


def test_anotar_cria_nota_markdown(caderno_temporario):
    r = anotar("A reunião foi remarcada para sexta às 14h", titulo="Reunião do projeto")
    assert r["sucesso"] is True

    arquivos = list(caderno_temporario.glob("*.md"))
    assert len(arquivos) == 1
    texto = arquivos[0].read_text(encoding="utf-8")
    assert "remarcada para sexta" in texto
    assert "origem: BMO" in texto  # frontmatter compatível com Obsidian


def test_anotar_mesmo_titulo_no_dia_acrescenta(caderno_temporario):
    anotar("primeira parte", titulo="Diário")
    anotar("segunda parte", titulo="Diário")

    arquivos = list(caderno_temporario.glob("*.md"))
    assert len(arquivos) == 1
    texto = arquivos[0].read_text(encoding="utf-8")
    assert "primeira parte" in texto and "segunda parte" in texto


def test_consulta_encontra_por_palavra_chave():
    anotar("O aniversário da Ana é dia 12 de setembro", titulo="Aniversário Ana")
    anotar("Senha do wifi da casa nova: coelho42", titulo="Wifi casa nova")

    r = consultar_anotacoes("quando é o aniversário da Ana?")
    assert r["sucesso"] is True and r["total"] >= 1
    assert "setembro" in r["resultados"][0]["trecho"]


def test_consulta_sem_resultado_avisa_sem_erro():
    r = consultar_anotacoes("assunto jamais anotado")
    assert r["sucesso"] is True
    assert r["total"] == 0


def test_memoria_automatica_so_aparece_quando_relevante():
    anotar("O aniversário da Ana é dia 12 de setembro", titulo="Aniversário Ana")

    relevante = memorias_relevantes("me lembra do aniversário da Ana?")
    assert "setembro" in relevante

    irrelevante = memorias_relevantes("qual a previsão do tempo?")
    assert irrelevante == ""


def test_caderno_inexistente_nao_quebra(monkeypatch):
    monkeypatch.setenv("BMO_VAULT", "C:/nao/existe/vault")
    assert memorias_relevantes("qualquer coisa") == ""
    r = consultar_anotacoes("qualquer coisa")
    assert r["sucesso"] is True and r["total"] == 0


def test_dispatch_via_registry(caderno_temporario):
    r = executar_ferramenta("anotar", {"conteudo": "teste via registry"})
    assert r["sucesso"] is True


def test_busca_enxerga_nota_editada_por_fora(caderno_temporario):
    """O cache de notas normalizadas e chaveado por (mtime, tamanho): editar
    a nota no Obsidian tem que aparecer na busca seguinte."""
    anotar("conteudo antigo sobre girassol", titulo="Jardim")
    assert consultar_anotacoes("girassol")["total"] == 1

    nota = next(caderno_temporario.glob("*.md"))
    nota.write_text("# Jardim\n\nagora fala de bromelia\n", encoding="utf-8")

    assert consultar_anotacoes("girassol")["total"] == 0
    assert consultar_anotacoes("bromelia")["total"] == 1


def test_acentos_e_maiusculas_casam_na_busca(caderno_temporario):
    anotar("Comprar açúcar e pão no mercado", titulo="Mercado")
    assert consultar_anotacoes("acucar")["total"] == 1
    assert consultar_anotacoes("AÇÚCAR")["total"] == 1
