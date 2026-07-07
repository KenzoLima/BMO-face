"""Testes do rosto — máquina de estados e desenho, sem janela."""

import time

from bmo.face import (
    SEGUNDOS_ATE_DORMIR,
    SEGUNDOS_EXIBINDO_EMOCAO,
    EstadoBMO,
    FrameBuffer,
    RostoBMO,
    desenhar_estado,
    extrair_emocao,
)


def novo_rosto():
    fb = FrameBuffer()
    return fb, RostoBMO(fb)


# ── extração de emoção ──────────────────────────────────────────────────────

def test_extrai_emocao_do_prefixo():
    assert extrair_emocao("[feliz] Oi! Tudo bem?") == "feliz"
    assert extrair_emocao("[Surpreso] o que?!") == "surpreso"


def test_sem_emocao_retorna_none():
    assert extrair_emocao("resposta sem prefixo") is None
    assert extrair_emocao("") is None


# ── mapeamento estado → desenho ─────────────────────────────────────────────

def test_cada_modo_usa_o_desenho_certo():
    fb, rosto = novo_rosto()
    esperado = {
        "boot": "draw_boot",
        "ouvindo": "draw_listening",
        "processando": "draw_thinking",
        "falando": "draw_speaking",
        "erro": "draw_error",
        "standby": "draw_idle",
    }
    for modo, desenho in esperado.items():
        estado = EstadoBMO()
        estado.mudar(modo)
        assert desenhar_estado(rosto, estado, frame=10) == desenho


def test_emocao_aparece_apos_falar_e_depois_some():
    fb, rosto = novo_rosto()
    estado = EstadoBMO()
    estado.mudar("standby", emocao="feliz")
    assert desenhar_estado(rosto, estado, 0) == "draw_happy"

    # envelhece o estado além da janela de exibição da emoção
    estado.desde = time.monotonic() - (SEGUNDOS_EXIBINDO_EMOCAO + 1)
    assert desenhar_estado(rosto, estado, 0) == "draw_idle"


def test_standby_prolongado_vira_sonolento():
    fb, rosto = novo_rosto()
    estado = EstadoBMO()
    estado.mudar("standby")
    estado.desde = time.monotonic() - (SEGUNDOS_ATE_DORMIR + 1)
    assert desenhar_estado(rosto, estado, 0) == "draw_sleepy"


def test_todas_emocoes_tem_desenho():
    fb, rosto = novo_rosto()
    for emocao in ("feliz", "triste", "surpreso", "dormindo", "pensativo", "focado"):
        estado = EstadoBMO()
        estado.mudar("standby", emocao=emocao)
        nome = desenhar_estado(rosto, estado, 0)
        assert nome.startswith("draw_")


# ── desenho de fato acontece e difere entre estados ─────────────────────────

def _assinatura(fb):
    return bytes(fb.buf)


def test_estados_desenham_pixels_diferentes():
    fb, rosto = novo_rosto()
    assinaturas = {}
    for modo in ("standby", "ouvindo", "processando", "falando", "erro"):
        estado = EstadoBMO()
        estado.mudar(modo)
        desenhar_estado(rosto, estado, frame=10)
        assinatura = _assinatura(fb)
        assert any(assinatura), f"modo '{modo}' desenhou um frame vazio"
        assinaturas[modo] = assinatura

    assert len(set(assinaturas.values())) == len(assinaturas), (
        "estados diferentes produziram o MESMO desenho"
    )


def test_animacao_da_boca_muda_entre_frames():
    fb, rosto = novo_rosto()
    estado = EstadoBMO()
    estado.mudar("falando")
    desenhar_estado(rosto, estado, frame=0)
    frame_a = _assinatura(fb)
    desenhar_estado(rosto, estado, frame=6)
    frame_b = _assinatura(fb)
    assert frame_a != frame_b
