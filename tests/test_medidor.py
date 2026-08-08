"""Testes do medidor de requisicoes — o velocimetro que esvazia.

Desenho puro no framebuffer 1-bit: nada de janela, nada de rede.
"""

from __future__ import annotations

import pytest

from bmo.face import OLED_H, OLED_W, FrameBuffer
from bmo.medidor import (
    GRAU_CHEIO,
    GRAU_VAZIO,
    NIVEIS_CACHE,
    desenhar_medidor,
    desenhar_medidor_cacheado,
    desenhar_medidor_com_texto,
)

CX, CY, RAIO = 64, 44, 30


def desenhar(fracao, **kwargs) -> FrameBuffer:
    fb = FrameBuffer()
    desenhar_medidor(fb, CX, CY, RAIO, fracao, **kwargs)
    return fb


def acesos(fb: FrameBuffer) -> int:
    return sum(bin(b).count("1") for b in fb.buf)


def acesos_em(fb: FrameBuffer, x0, y0, x1, y1) -> int:
    return sum(
        1
        for y in range(y0, y1)
        for x in range(x0, x1)
        if fb.get(x, y)
    )


# --- o essencial: comeca cheio e vai esvaziando ---


def test_cheio_acende_mais_que_pela_metade_que_vazio():
    assert acesos(desenhar(1.0)) > acesos(desenhar(0.5)) > acesos(desenhar(0.0))


def test_esvaziar_e_monotonico():
    """Cada gole de requisicao so pode apagar pixels, nunca acender."""
    contagens = [acesos(desenhar(f / 20)) for f in range(21)]
    assert contagens == sorted(contagens), "o medidor tem que encolher sem oscilar"


def test_ponteiro_vai_da_direita_para_a_esquerda():
    """Cheio: ponteiro apontando pra direita. Vazio: pra esquerda."""
    metade_esquerda = (0, CY - RAIO, CX - 4, CY)
    metade_direita = (CX + 4, CY - RAIO, OLED_W, CY)

    cheio, vazio = desenhar(1.0), desenhar(0.0)
    assert acesos_em(cheio, *metade_direita) > acesos_em(vazio, *metade_direita)
    assert acesos_em(vazio, *metade_esquerda) < acesos_em(cheio, *metade_esquerda)


def test_vazio_ainda_mostra_a_escala():
    """Sem requisicao nenhuma o medidor nao pode sumir — o trilho fica."""
    fb = desenhar(0.0)
    assert acesos(fb) > 40, "o trilho e os riscos continuam visiveis no zero"


# --- robustez ---


@pytest.mark.parametrize("fora", [-5.0, -0.1, 1.1, 42.0, float("inf")])
def test_fracao_fora_da_faixa_e_grampeada(fora):
    esperado = desenhar(0.0) if fora < 0 else desenhar(1.0)
    assert bytes(desenhar(fora).buf) == bytes(esperado.buf)


def test_desenho_nao_vaza_para_fora_da_area():
    """O arco fica ACIMA do eixo; nada pode aparecer muito abaixo dele."""
    fb = desenhar(0.7)
    assert acesos_em(fb, 0, 0, OLED_W, CY - RAIO - 1) == 0  # acima do arco
    assert acesos_em(fb, 0, CY + 6, OLED_W, OLED_H) == 0    # abaixo do pe


def test_medidor_no_canto_nao_estoura_o_framebuffer():
    """Desenhar colado na borda nao pode dar erro nem enrolar para o outro lado."""
    fb = FrameBuffer()
    desenhar_medidor(fb, 2, 2, 12, 0.5, segmentos=6, espessura=2)
    assert acesos(fb) > 0
    # a coluna direita tem que continuar apagada (sem wrap horizontal)
    assert acesos_em(fb, OLED_W - 2, 0, OLED_W, OLED_H) == 0


def test_convencao_dos_graus():
    """O arco varre a metade de cima, da esquerda (vazio) para a direita."""
    assert (GRAU_VAZIO, GRAU_CHEIO) == (180, 360)


# --- numero embaixo ---


def test_texto_acende_pixels_extras_e_e_opcional():
    sem = FrameBuffer()
    desenhar_medidor_com_texto(sem, CX, CY, RAIO, 0.5, None)
    com = FrameBuffer()
    desenhar_medidor_com_texto(com, CX, CY, RAIO, 0.5, 125)

    assert bytes(sem.buf) == bytes(desenhar(0.5).buf)  # sem numero = medidor puro
    assert acesos(com) > acesos(sem)


# --- versao memorizada (a que o rosto usa a 30fps) ---


def cacheado(fracao, **kwargs) -> FrameBuffer:
    fb = FrameBuffer()
    desenhar_medidor_cacheado(fb, CX, CY, RAIO, fracao, **kwargs)
    return fb


@pytest.mark.parametrize("nivel", range(0, NIVEIS_CACHE + 1, 8))
def test_cache_desenha_o_mesmo_que_a_versao_direta(nivel):
    """Nos niveis exatos do cache, o traçado tem que bater bit a bit."""
    fracao = nivel / NIVEIS_CACHE
    assert bytes(cacheado(fracao).buf) == bytes(desenhar(fracao).buf)


def test_cache_arredonda_para_o_nivel_mais_proximo():
    passo = 1 / NIVEIS_CACHE
    meio = 0.5
    assert bytes(cacheado(meio + passo / 4).buf) == bytes(cacheado(meio).buf)


def test_cache_nao_acumula_entre_chamadas():
    """Repintar duas vezes no mesmo frame nao pode dobrar nada, e um frame
    novo nao pode herdar o desenho do anterior."""
    uma = cacheado(0.4)
    duas = FrameBuffer()
    desenhar_medidor_cacheado(duas, CX, CY, RAIO, 0.4)
    desenhar_medidor_cacheado(duas, CX, CY, RAIO, 0.4)
    assert bytes(uma.buf) == bytes(duas.buf)


def test_cache_continua_esvaziando_monotonicamente():
    contagens = [acesos(cacheado(f / 20)) for f in range(21)]
    assert contagens == sorted(contagens)


def test_numeros_diferentes_desenham_diferente():
    a, b = FrameBuffer(), FrameBuffer()
    desenhar_medidor_com_texto(a, CX, CY, RAIO, 0.5, 250)
    desenhar_medidor_com_texto(b, CX, CY, RAIO, 0.5, 111)
    assert bytes(a.buf) != bytes(b.buf)
