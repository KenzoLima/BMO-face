"""Testes da boca do BMO — só a lógica pura (sem rede, sem áudio)."""

from bmo.mouth import Boca, limpar_para_fala


def test_remove_expressao_do_rosto():
    assert limpar_para_fala("[feliz] Oi! Tudo bem?") == "Oi! Tudo bem?"


def test_remove_expressao_em_qualquer_posicao_e_caixa():
    assert limpar_para_fala("Estou [Pensativo] agora") == "Estou agora"


def test_remove_markdown():
    assert limpar_para_fala("**Pronto!** Abri o `code` para você") == (
        "Pronto! Abri o code para você"
    )


def test_remove_emoji():
    assert limpar_para_fala("Encontrei! 🎮👾") == "Encontrei!"


def test_normaliza_espacos():
    assert limpar_para_fala("[focado]   Feito!   Bip!") == "Feito! Bip!"


def test_bmo_vira_bimo_na_fala():
    assert limpar_para_fala("Eu sou o BMO!") == "Eu sou o Bímo!"
    assert limpar_para_fala("bmo está pronto") == "Bímo está pronto"


def test_bmo_dentro_de_palavra_nao_e_alterado():
    # 'bmo_face.py' é nome de arquivo, não o nome do robô
    # (o '_' sai junto com o markdown, mas o 'bmo' colado não vira 'Bímo')
    assert limpar_para_fala("abra o bmo_face.py") == "abra o bmoface.py"


def test_texto_sem_nada_falavel_vira_vazio():
    assert limpar_para_fala("[dormindo] 💤") == ""


def test_falar_texto_vazio_retorna_false_sem_tocar():
    assert Boca().falar("[dormindo]") is False


def test_configuracao_padrao_da_voz():
    boca = Boca()
    assert boca.voz.startswith("pt-BR-")
    assert boca.velocidade and boca.tom
