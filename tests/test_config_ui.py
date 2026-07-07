"""Testes da tela de configurações — só a camada de dados (sem abrir janela)."""

import pytest

import bmo.config_ui as config_ui
from bmo.config_ui import gravar_env, ler_env


@pytest.fixture(autouse=True)
def env_temporario(tmp_path, monkeypatch):
    caminho = tmp_path / ".env"
    monkeypatch.setattr(config_ui, "_caminho_env", lambda: caminho)
    return caminho


def test_ler_env_ignora_comentarios(env_temporario):
    env_temporario.write_text(
        "# comentario\nGOOGLE_API_KEY=abc123\n\nBMO_VOZ=pt-BR-AntonioNeural\n",
        encoding="utf-8",
    )
    valores = ler_env()
    assert valores["GOOGLE_API_KEY"] == "abc123"
    assert valores["BMO_VOZ"] == "pt-BR-AntonioNeural"


def test_gravar_preserva_comentarios_e_linhas_desconhecidas(env_temporario):
    env_temporario.write_text(
        "# Configuracao do BMO\nGOOGLE_API_KEY=antiga\nBMO_WAKE_CONF_MIN=0.4\n",
        encoding="utf-8",
    )
    gravar_env({"GOOGLE_API_KEY": "nova", "BMO_USUARIO_NOME": "Kenzo"})

    texto = env_temporario.read_text(encoding="utf-8")
    assert "# Configuracao do BMO" in texto        # comentário preservado
    assert "GOOGLE_API_KEY=nova" in texto          # atualizada no lugar
    assert "BMO_WAKE_CONF_MIN=0.4" in texto        # linha alheia intacta
    assert "BMO_USUARIO_NOME=Kenzo" in texto       # nova chave adicionada


def test_gravar_em_env_inexistente_cria_arquivo(env_temporario):
    gravar_env({"GOOGLE_API_KEY": "abc"})
    assert ler_env()["GOOGLE_API_KEY"] == "abc"


def test_round_trip_completo(env_temporario):
    dados = {
        "BMO_USUARIO_NOME": "Ana Clara",
        "BMO_USUARIO_IDADE": "23",
        "GOOGLE_API_KEY": "chave-google",
        "BMO_VAULT": r"C:\Users\ana\Vault\BMO",
    }
    gravar_env(dados)
    lidos = ler_env()
    for chave, valor in dados.items():
        assert lidos[chave] == valor


def test_prompt_inclui_nome_do_usuario(monkeypatch):
    from bmo.brain.prompts import system_prompt_atual

    monkeypatch.setenv("BMO_USUARIO_NOME", "Kenzo")
    monkeypatch.setenv("BMO_USUARIO_IDADE", "21")
    prompt = system_prompt_atual()
    assert "Kenzo" in prompt and "21 anos" in prompt

    monkeypatch.delenv("BMO_USUARIO_NOME")
    monkeypatch.delenv("BMO_USUARIO_IDADE")
    assert "se chama" not in system_prompt_atual()


def test_sem_tkinter_nao_abre_env_para_edicao(env_temporario, monkeypatch):
    chamadas = []

    monkeypatch.setattr(config_ui, "tk", None)
    monkeypatch.setattr(config_ui, "_ERRO_TK", RuntimeError("tk ausente"))
    monkeypatch.setattr(
        config_ui,
        "_mostrar_aviso_nativo",
        lambda titulo, mensagem: chamadas.append((titulo, mensagem)),
    )

    assert config_ui.abrir_configuracoes(primeira_vez=True) is False
    assert not env_temporario.exists()
    assert chamadas
    assert "janela de configuracao" in chamadas[0][1]
    assert "editando arquivos manualmente" in chamadas[0][1]
