"""Testes do bug: 'ele falou que ia pesquisar e nunca mais respondeu'.

Tres causas separadas, tres grupos de teste:
  1. nao havia tela de pesquisa — o rosto ficava parado e parecia travado;
  2. uma falha de fala emudecia o BMO pela sessao INTEIRA, em silencio;
  3. a busca nao tinha teto de tempo e pendurava a thread de voz.
"""

from __future__ import annotations

import time

import pytest

import bmo.app as app_mod
from bmo.app import MAX_FALHAS_DE_VOZ, AssistenteDeVoz
from bmo.face import EstadoBMO, FrameBuffer, RostoBMO, desenhar_estado
from bmo.hands.registry import TIMEOUT_PADRAO, executar_ferramenta, ferramenta


def novo_assistente():
    a = AssistenteDeVoz(EstadoBMO())
    a.boca = None
    a.ack = None
    return a


def acesos(fb: FrameBuffer) -> int:
    return sum(bin(b).count("1") for b in fb.buf)


# --- 1) a tela de pesquisa existe, anda e CONCLUI ---


def test_estado_de_pesquisa_tem_desenho_proprio():
    estado, fb = EstadoBMO(), FrameBuffer()
    rosto = RostoBMO(fb)

    estado.mudar("pesquisando")
    assert desenhar_estado(rosto, estado, 30) == "draw_pesquisando"
    assert acesos(fb) > 0

    estado.mudar("pesquisa_concluida")
    assert desenhar_estado(rosto, estado, 30) == "draw_pesquisando"


def test_barra_de_pesquisa_enche_com_o_tempo():
    fb = FrameBuffer()
    rosto = RostoBMO(fb)
    enchendo = []
    for frame in (0, 30, 90, 150):
        rosto.draw_pesquisando(frame)
        enchendo.append(acesos(fb))
    assert enchendo == sorted(enchendo), "a barra tem que avancar, nunca voltar"


def test_tela_concluida_mostra_mais_que_a_tela_em_andamento():
    """O usuario pediu que a tela CONCLUA — 100% precisa ser distinguivel."""
    andando, concluida = FrameBuffer(), FrameBuffer()
    RostoBMO(andando).draw_pesquisando(150)            # para em 95%
    RostoBMO(concluida).draw_pesquisando(150, progresso=1.0)
    assert bytes(andando.buf) != bytes(concluida.buf)
    assert acesos(concluida) > acesos(andando)


def test_ferramenta_leva_o_rosto_para_a_pesquisa_e_traz_de_volta():
    a = novo_assistente()
    vistos = []

    a._mostrar_ferramenta(["buscar_na_internet"], "inicio")
    vistos.append(a.estado.ler()[0])

    a._mostrar_ferramenta(["buscar_na_internet"], "fim")
    # depois do 'fim' a tela cheia aparece e o rosto volta a processar
    vistos.append(a.estado.ler()[0])

    assert vistos == ["pesquisando", "processando"]


def test_o_aviso_de_ferramenta_chega_do_cerebro_ate_o_rosto():
    """O caminho inteiro: provedor -> Cerebro -> app."""
    from bmo.brain.agent import Cerebro

    fases = []

    class ProvedorComFerramenta:
        nome = "fake"

        def responder(self, texto, historico):
            return "[feliz] Achei!"

        def responder_em_partes(self, texto, historico, ao_ferramenta=None):
            yield "[feliz] Vou pesquisar! "
            ao_ferramenta(["buscar_na_internet"], "inicio")
            ao_ferramenta(["buscar_na_internet"], "fim")
            yield "Achei a resposta."

    cerebro = Cerebro(provedor=ProvedorComFerramenta(), reserva=None)
    texto = "".join(
        cerebro.responder_em_partes(
            "qual a previsao do tempo?",
            ao_ferramenta=lambda nomes, fase: fases.append((nomes[0], fase)),
        )
    )

    assert fases == [("buscar_na_internet", "inicio"), ("buscar_na_internet", "fim")]
    assert texto == "[feliz] Vou pesquisar! Achei a resposta."


# --- 2) uma falha de fala nao pode emudecer a sessao inteira ---


def test_falha_isolada_de_voz_nao_emudece_o_bmo():
    a = novo_assistente()
    a.boca = object()  # so precisa nao ser None

    a._voz_falhou(RuntimeError("oscilacao de rede no edge-tts"))

    assert a.boca is not None, "uma falha isolada emudecia o BMO para sempre"
    assert a._falhas_de_voz == 1


def test_voz_so_desliga_depois_de_varias_falhas_seguidas():
    a = novo_assistente()
    a.boca = object()

    for _ in range(MAX_FALHAS_DE_VOZ):
        a._voz_falhou(RuntimeError("sem rede"))

    assert a.boca is None
    assert a.estado.ler()[0] == "erro", "desligar a voz precisa aparecer no rosto"


def test_uma_fala_bem_sucedida_zera_o_placar():
    a = novo_assistente()
    a.boca = object()

    a._voz_falhou(RuntimeError("falhou"))
    a._voz_falhou(RuntimeError("falhou"))
    a._voz_funcionou()
    a._voz_falhou(RuntimeError("falhou"))

    assert a.boca is not None, "falhas espacadas nao podem somar ate emudecer"
    assert a._falhas_de_voz == 1


# --- 3) nenhuma ferramenta pode pendurar a thread de voz ---


@ferramenta(
    nome="_ferramenta_pendurada",
    descricao="so para teste: nunca retorna",
    parametros={"type": "object", "properties": {}},
    timeout=0.4,
)
def _ferramenta_pendurada() -> dict:
    time.sleep(30)
    return {"sucesso": True}


def test_ferramenta_pendurada_devolve_erro_em_vez_de_travar():
    inicio = time.perf_counter()
    resultado = executar_ferramenta("_ferramenta_pendurada")
    decorrido = time.perf_counter() - inicio

    assert decorrido < 3, f"ficou {decorrido:.1f}s presa — deveria desistir em 0.4s"
    assert resultado["sucesso"] is False
    assert "abandonada" in resultado["erro"]


def test_busca_na_internet_tem_teto_de_tempo():
    from bmo.hands.web import TIMEOUT_BUSCA

    assert 0 < TIMEOUT_BUSCA <= 30


def test_comando_de_shell_pode_declarar_teto_maior():
    """O shell se limita sozinho; o teto do registry nao pode cortar antes."""
    from bmo.hands.registry import _REGISTRO
    from bmo.hands.shell import TIMEOUT_TETO

    assert _REGISTRO["executar_comando"].timeout > TIMEOUT_TETO
    assert _REGISTRO["buscar_na_internet"].timeout == TIMEOUT_PADRAO


def test_ferramenta_normal_continua_rapida():
    """O teto nao pode adicionar espera perceptivel ao caminho feliz."""
    inicio = time.perf_counter()
    r = executar_ferramenta("consultar_anotacoes", {"termo": "nada"})
    assert time.perf_counter() - inicio < 2
    assert r["sucesso"] is True
