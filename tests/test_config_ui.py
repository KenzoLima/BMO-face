"""Testes da tela de configurações — só a camada de dados (sem abrir janela)."""

import pytest

import bmo.config_ui as config_ui
from bmo.config_ui import gravar_env, ler_env

# Teto de altura da tela de configuracoes. Uma tela de 768px de altura tem
# ~728px de area util depois da barra de tarefas; deixamos folga para fontes
# maiores. Se um campo novo estourar isso, e sinal de que ele precisa entrar
# numa das colunas em vez de esticar a janela.
ALTURA_MAXIMA = 640


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


# --- dispositivos de audio ---


def test_rotulos_da_lista_nao_vazam_para_o_env():
    """'(padrao do Windows)' e '(desconectado)' sao enfeite de tela: o que vai
    para o .env e o nome puro do dispositivo."""
    limpar = config_ui.TelaConfiguracoes._sem_rotulos

    assert limpar(config_ui.PADRAO_DO_SISTEMA) == ""
    assert limpar("") == ""
    assert limpar("Microfone (Webcam)") == "Microfone (Webcam)"
    assert limpar(f"Microfone (Webcam) {config_ui.SUFIXO_AUSENTE}") == "Microfone (Webcam)"


def test_dispositivo_desconectado_continua_na_lista_marcado():
    """Abrir a tela com o fone desligado nao pode apagar a escolha em silencio."""
    marcar = config_ui.TelaConfiguracoes._marcar_ausente

    disponiveis = ["Microfone A"]
    rotulo = marcar(disponiveis, "Microfone B")
    assert rotulo == f"Microfone B {config_ui.SUFIXO_AUSENTE}"
    assert rotulo in disponiveis, "o ausente entra na lista para poder ser reselecionado"

    presentes = ["Microfone A"]
    assert marcar(presentes, "Microfone A") == ""
    assert presentes == ["Microfone A"]  # nada foi acrescentado

    assert marcar(["Microfone A"], "") == ""  # sem escolha salva, nada a marcar


def test_dispositivos_sao_gravados_no_env(env_temporario):
    from bmo.audio import CHAVE_ENTRADA, CHAVE_SAIDA

    gravar_env({
        CHAVE_ENTRADA: "Microfone (Realtek HD Audio Mic input)",
        CHAVE_SAIDA: "Alto-falantes (Realtek(R) Audio)",
    })
    lidos = ler_env()
    assert lidos[CHAVE_ENTRADA] == "Microfone (Realtek HD Audio Mic input)"
    assert lidos[CHAVE_SAIDA] == "Alto-falantes (Realtek(R) Audio)"


def test_testar_microfone_avisa_quando_o_escolhido_sumiu(monkeypatch):
    monkeypatch.setattr("bmo.audio._candidatos_entrada", lambda: [])
    ok, mensagem = config_ui.testar_microfone("Microfone que foi desplugado")
    assert ok is False
    assert "não está conectado" in mensagem


# --- layout: a tela inteira precisa caber na area util ---


@pytest.fixture(scope="module")
def tela(tmp_path_factory):
    """Monta a tela de verdade UMA vez, escondida.

    Escopo de modulo de proposito: criar e destruir varios ``tk.Tk()`` no
    mesmo processo deixa o Tcl sem achar o init.tcl e os testes passam a
    pular de forma aleatoria. Estas verificacoes so leem geometria, entao
    uma janela compartilhada serve para todas.
    """
    if config_ui.tk is None:
        pytest.skip("Tkinter indisponivel")

    caminho = tmp_path_factory.mktemp("env") / ".env"
    original = config_ui._caminho_env
    config_ui._caminho_env = lambda: caminho
    try:
        janela = config_ui.TelaConfiguracoes()
    except Exception as e:  # sem display (CI headless)
        config_ui._caminho_env = original
        pytest.skip(f"sem display: {e}")

    janela.raiz.withdraw()
    janela.raiz.update_idletasks()
    yield janela
    janela.raiz.destroy()
    config_ui._caminho_env = original


def test_tela_cabe_na_area_util_com_o_salvar_visivel(tela):
    """O bug: em coluna unica a tela passava de 800px e o botao Salvar ficava
    atras da barra de tarefas, sem como salvar a configuracao."""
    altura = tela.raiz.winfo_reqheight()
    _, topo, _, base = tela._area_util()
    disponivel = base - topo

    assert altura <= disponivel, (
        f"a tela ({altura}px) nao cabe na area util ({disponivel}px) — "
        "o botao Salvar fica atras da barra de tarefas"
    )
    assert altura <= ALTURA_MAXIMA, (
        f"a tela cresceu para {altura}px; acima de {ALTURA_MAXIMA}px ela deixa "
        "de caber em telas menores ou com escala de DPI"
    )


def test_janela_e_mais_larga_que_alta(tela):
    """Monitor deitado: melhor gastar largura do que altura."""
    assert tela.raiz.winfo_reqwidth() > tela.raiz.winfo_reqheight()


def test_centraliza_dentro_da_area_util_e_nunca_acima_do_topo(tela, monkeypatch):
    # tela baixa de proposito: a janela tem que encostar no topo, nao subir
    monkeypatch.setattr(tela, "_area_util", lambda: (0, 40, 1280, 300))
    tela._centralizar()
    x, y = (int(v) for v in tela.raiz.geometry().split("+")[1:])
    assert y >= 40, "a janela subiu acima da area util"
    assert x >= 0


def test_nenhuma_celula_do_grid_e_usada_duas_vezes(tela):
    ocupadas: dict[tuple[int, int], str] = {}
    for widget in tela.raiz.winfo_children():
        info = widget.grid_info()
        if not info:
            continue
        linha, coluna = int(info["row"]), int(info["column"])
        for c in range(coluna, coluna + int(info.get("columnspan", 1))):
            assert (linha, c) not in ocupadas, f"widgets empilhados em {(linha, c)}"
            ocupadas[(linha, c)] = str(widget)


def test_as_duas_colunas_estao_preenchidas(tela):
    """Se um bloco escorregar para a coluna errada, a tela volta a esticar."""
    colunas = {
        int(w.grid_info()["column"])
        for w in tela.raiz.winfo_children() if w.grid_info()
    }
    assert colunas & {0, 1, 2}, "coluna da esquerda vazia"
    assert colunas & {3, 4, 5}, "coluna da direita vazia"


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
