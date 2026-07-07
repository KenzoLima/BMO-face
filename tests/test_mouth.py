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


def test_texto_sem_nada_falavel_vira_vazio():
    assert limpar_para_fala("[dormindo] 💤") == ""


def test_falar_texto_vazio_retorna_false_sem_tocar():
    assert Boca().falar("[dormindo]") is False


def test_configuracao_padrao_da_voz():
    boca = Boca()
    assert boca.voz.startswith("pt-BR-")
    assert boca.velocidade and boca.tom
