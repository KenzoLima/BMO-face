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


def test_boot_mostra_bem_vindo_e_barra():
    fb, rosto = novo_rosto()
    rosto.draw_boot(60)
    assert any(fb.buf)  # tem pixels (texto + barra)


def test_apresentacao_interpola_boot_e_rosto():
    fb, rosto = novo_rosto()

    rosto.draw_apresentacao(16, progresso=0.0)
    inicio = bytes(fb.buf)
    rosto.draw_boot(120)
    assert inicio == bytes(fb.buf)  # progresso 0 = tela de boot

    rosto.draw_apresentacao(16, progresso=1.0)
    fim = bytes(fb.buf)
    rosto.draw_idle(16)
    assert fim == bytes(fb.buf)  # progresso 1 = rosto

    rosto.draw_apresentacao(16, progresso=0.5)
    meio = bytes(fb.buf)
    assert meio != inicio and meio != fim  # no meio é a mistura


def test_modo_apresentacao_no_mapeamento():
    fb, rosto = novo_rosto()
    estado = EstadoBMO()
    estado.mudar("apresentacao")
    assert desenhar_estado(rosto, estado, 0) == "draw_apresentacao"


def test_animacao_da_boca_muda_entre_frames():
    fb, rosto = novo_rosto()
    estado = EstadoBMO()
    estado.mudar("falando")
    desenhar_estado(rosto, estado, frame=0)
    frame_a = _assinatura(fb)
    desenhar_estado(rosto, estado, frame=6)
    frame_b = _assinatura(fb)
    assert frame_a != frame_b


# ── lip sync ────────────────────────────────────────────────────────────────

def test_amplitude_segue_o_relogio_do_envelope():
    from bmo.face import JANELA_ENVELOPE

    estado = EstadoBMO()
    estado.iniciar_fala([0.1, 0.9, 0.2])

    estado.desde = time.monotonic()  # agora → janela 0
    assert estado.amplitude_boca() == 0.1

    estado.desde = time.monotonic() - JANELA_ENVELOPE * 1.5  # meio da janela 1
    assert estado.amplitude_boca() == 0.9

    estado.desde = time.monotonic() - JANELA_ENVELOPE * 10  # fala acabou
    assert estado.amplitude_boca() == 0.0


def test_sem_envelope_amplitude_e_none_e_boca_usa_fallback():
    estado = EstadoBMO()
    estado.iniciar_fala(None)
    assert estado.amplitude_boca() is None

    estado.mudar("standby")
    assert estado.amplitude_boca() is None


def test_boca_abre_conforme_a_amplitude():
    fb, rosto = novo_rosto()
    formas = {}
    for amplitude in (0.05, 0.25, 0.5, 0.9):
        rosto.draw_speaking(16, amplitude=amplitude)
        formas[amplitude] = _assinatura(fb)
        assert any(fb.buf)

    # cada faixa de volume produz uma boca diferente
    assert len(set(formas.values())) == 4

    # boca fechada (silêncio) tem menos pixels acesos que escancarada (pico)
    pixels = {a: sum(bin(b).count("1") for b in formas[a]) for a in formas}
    assert pixels[0.05] < pixels[0.9]


def test_mudar_de_estado_limpa_o_envelope():
    estado = EstadoBMO()
    estado.iniciar_fala([0.5])
    estado.mudar("standby")
    assert estado.envelope is None
