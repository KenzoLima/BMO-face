"""Testes do módulo bmo.hands — as "mãos" do BMO.

Rodar da raiz do projeto:  python -m pytest tests/ -v

Nenhum teste abre janelas nem altera o sistema: a única execução real
é um comando inofensivo no PowerShell.
"""

from pathlib import Path

from bmo.hands import executar_ferramenta, listar_ferramentas, schemas_gemini
from bmo.hands.apps import _candidatos
from bmo.hands.files import buscar_arquivo
from bmo.hands.shell import executar_comando

RAIZ_PROJETO = str(Path(__file__).resolve().parents[1])


# ── Registry ────────────────────────────────────────────────────────────────

def test_tres_ferramentas_registradas():
    nomes = {f.nome for f in listar_ferramentas()}
    assert {"abrir_aplicativo", "buscar_arquivo", "executar_comando"} <= nomes


def test_schemas_gemini_bem_formados():
    for schema in schemas_gemini():
        assert schema["name"]
        assert schema["description"]
        assert schema["parameters"]["type"] == "object"


def test_ferramenta_desconhecida_vira_erro_e_nao_excecao():
    resultado = executar_ferramenta("hackear_nasa", {})
    assert resultado["sucesso"] is False
    assert "desconhecida" in resultado["erro"]


def test_argumentos_invalidos_viram_erro():
    resultado = executar_ferramenta("buscar_arquivo", {"argumento_errado": 1})
    assert resultado["sucesso"] is False


# ── abrir_aplicativo (só resolução de nomes; não abre nada) ─────────────────

def test_aliases_resolvem_para_candidatos():
    assert _candidatos("VS Code") == ["code"]
    assert _candidatos("  navegador ") == ["msedge", "chrome", "firefox"]
    assert _candidatos("app-que-nao-existe") == ["app-que-nao-existe"]


# ── buscar_arquivo ──────────────────────────────────────────────────────────

def test_busca_por_nome_encontra_arquivo_do_projeto():
    resultado = buscar_arquivo("bmo_brain", diretorio_base=RAIZ_PROJETO)
    assert resultado["sucesso"] is True
    assert any(caminho.endswith("bmo_brain.py") for caminho in resultado["arquivos"])


def test_busca_por_extensao():
    resultado = buscar_arquivo(".py", diretorio_base=RAIZ_PROJETO, max_resultados=5)
    assert resultado["sucesso"] is True
    assert 0 < resultado["total"] <= 5
    assert all(caminho.endswith(".py") for caminho in resultado["arquivos"])


def test_busca_ignora_venv_e_git():
    resultado = buscar_arquivo(".py", diretorio_base=RAIZ_PROJETO, max_resultados=50)
    assert not any(".venv" in caminho for caminho in resultado["arquivos"])


def test_diretorio_inexistente():
    resultado = buscar_arquivo("x", diretorio_base="C:/nao/existe/mesmo")
    assert resultado["sucesso"] is False


# ── executar_comando ────────────────────────────────────────────────────────

def test_comando_simples_retorna_stdout():
    resultado = executar_comando("Write-Output 'bmo vive'")
    assert resultado["sucesso"] is True
    assert resultado["codigo_saida"] == 0
    assert "bmo vive" in resultado["stdout"]


def test_comando_que_falha_retorna_stderr():
    resultado = executar_comando("comando-que-nao-existe-mesmo")
    assert resultado["sucesso"] is False
    assert resultado["codigo_saida"] != 0


def test_comando_destrutivo_e_bloqueado():
    resultado = executar_comando("shutdown /s /t 0")
    assert resultado["sucesso"] is False
    assert "bloqueado" in resultado["erro"].lower()


def test_dispatch_via_registry():
    resultado = executar_ferramenta(
        "executar_comando", {"comando": "Write-Output 'via registry'"}
    )
    assert resultado["sucesso"] is True
    assert "via registry" in resultado["stdout"]
