"""Medidor de requisições — o "velocímetro" do BMO.

Um ponteiro estilo velocímetro que **começa cheio e vai esvaziando**: o arco
mostra quanto ainda resta do orçamento de requisições do dia, e o ponteiro
recua da direita (cheio) para a esquerda (vazio) conforme o BMO gasta.

Desenhado no mesmo framebuffer 1-bit do rosto (``bmo.face``), então ele é
puro, testável sem janela e reaproveitável em qualquer lugar que já saiba
desenhar o BMO — inclusive num OLED físico.

    fb = FrameBuffer()
    desenhar_medidor(fb, 64, 40, 26, fracao=0.62)

``fracao`` é o que SOBROU (1.0 = orçamento intacto, 0.0 = acabou).
"""

from __future__ import annotations

import math

from .face import OLED_H, OLED_W, FrameBuffer

# O arco varre a metade de cima, da esquerda (vazio) para a direita (cheio).
# No framebuffer o y cresce para baixo, então 180°→360° é o semicírculo
# superior — a mesma convenção que os olhos felizes do rosto usam.
GRAU_VAZIO = 180
GRAU_CHEIO = 360

SEGMENTOS = 10          # riscos da escala
FOLGA_SEGMENTO = 2      # graus de respiro entre um risco e o outro


def _ponto(cx: int, cy: int, raio: float, grau: float) -> tuple[int, int]:
    rad = math.radians(grau)
    return round(cx + raio * math.cos(rad)), round(cy + raio * math.sin(rad))


def _grau_da_fracao(fracao: float) -> float:
    return GRAU_VAZIO + (GRAU_CHEIO - GRAU_VAZIO) * fracao


def desenhar_medidor(
    fb: FrameBuffer,
    cx: int,
    cy: int,
    raio: int,
    fracao: float,
    *,
    segmentos: int = SEGMENTOS,
    espessura: int = 3,
) -> None:
    """Desenha o velocímetro cheio→vazio centrado em (cx, cy).

    ``cy`` é o eixo do ponteiro: o arco fica ACIMA dele, então o desenho ocupa
    de ``cy - raio`` a ``cy`` na vertical e ``2 * raio`` na horizontal.
    """
    fracao = max(0.0, min(1.0, fracao))
    limite = _grau_da_fracao(fracao)

    # 1) trilho: o arco inteiro, fininho — mostra a escala que existe
    fb.arc(cx, cy, raio, GRAU_VAZIO, GRAU_CHEIO, thickness=1)

    # 2) tanque: a parte que AINDA resta, grossa, da esquerda até o ponteiro
    if fracao > 0:
        fb.arc(cx, cy, raio, GRAU_VAZIO, round(limite), thickness=espessura)

    # 3) escala: riscos radiais, curtos, marcando as divisões do orçamento
    passo = (GRAU_CHEIO - GRAU_VAZIO) / segmentos
    for i in range(segmentos + 1):
        grau = GRAU_VAZIO + i * passo
        interno = raio - espessura - 1
        x0, y0 = _ponto(cx, cy, interno, grau)
        x1, y1 = _ponto(cx, cy, interno - 2, grau)
        fb.line(x0, y0, x1, y1)

    # 4) marcos das pontas: onde é "vazio" e onde é "cheio"
    for grau in (GRAU_VAZIO, GRAU_CHEIO):
        fb.vline(*_ponto(cx, cy, raio, grau), 3)

    # 5) ponteiro: sai do eixo e aponta o quanto sobrou.
    # Nos extremos ele fica horizontal, por isso a base é só um pé embaixo do
    # eixo — uma linha de ponta a ponta engoliria o ponteiro em 0% e 100%.
    px, py = _ponto(cx, cy, raio - espessura - 3, limite)
    fb.line(cx, cy, px, py, thickness=2)

    # 6) eixo, para o ponteiro ter de onde nascer
    fb.circle(cx, cy, 2)
    fb.hline(cx - 3, cy + 3, 7)


# Traçado já pronto, por nível — ver ``desenhar_medidor_cacheado``.
_CACHE_PIXELS: dict[tuple, tuple[tuple[int, int], ...]] = {}
NIVEIS_CACHE = 96


def desenhar_medidor_cacheado(
    fb: FrameBuffer,
    cx: int,
    cy: int,
    raio: int,
    fracao: float,
    *,
    segmentos: int = SEGMENTOS,
    espessura: int = 3,
) -> None:
    """Como ``desenhar_medidor``, mas memorizando o traçado por nível.

    O rosto redesenha 30 vezes por segundo; o saldo muda algumas vezes por
    minuto. Não vale refazer arcos, riscos e ponteiro a cada frame — desenha
    uma vez por nível e depois só repinta os pixels.

    O nível é arredondado em ``NIVEIS_CACHE`` degraus: num raio pequeno,
    frações vizinhas dariam exatamente o mesmo desenho de qualquer jeito.
    """
    nivel = round(max(0.0, min(1.0, fracao)) * NIVEIS_CACHE)
    chave = (cx, cy, raio, segmentos, espessura, nivel)
    pixels = _CACHE_PIXELS.get(chave)
    if pixels is None:
        molde = FrameBuffer()
        desenhar_medidor(
            molde, cx, cy, raio, nivel / NIVEIS_CACHE,
            segmentos=segmentos, espessura=espessura,
        )
        # varre só a caixa que o medidor pode ocupar, não o frame inteiro
        x0, x1 = max(0, cx - raio - 1), min(OLED_W, cx + raio + 2)
        y0, y1 = max(0, cy - raio - 1), min(OLED_H, cy + 6)
        pixels = tuple(
            (x, y)
            for y in range(y0, y1)
            for x in range(x0, x1)
            if molde.get(x, y)
        )
        _CACHE_PIXELS[chave] = pixels

    ponto = fb.pixel
    for x, y in pixels:
        ponto(x, y)


def desenhar_medidor_com_texto(
    fb: FrameBuffer,
    cx: int,
    cy: int,
    raio: int,
    fracao: float,
    restantes: int | None = None,
    **kwargs,
) -> None:
    """Igual ao ``desenhar_medidor``, com o número que sobrou embaixo do eixo."""
    desenhar_medidor(fb, cx, cy, raio, fracao, **kwargs)
    if restantes is None:
        return
    texto = str(restantes)
    largura = len(texto) * 4 - 1  # dígitos 3x5 com 1px de espaço
    _digitos(fb, texto, cx - largura // 2, cy + 6)


# Dígitos 3x5 — o menor tamanho ainda legível no OLED, para caber sob o arco.
_DIGITOS_3X5 = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "k": ("000", "101", "110", "101", "101"),
    "+": ("000", "010", "111", "010", "000"),
    "-": ("000", "000", "111", "000", "000"),
}


def _digitos(fb: FrameBuffer, texto: str, x: int, y: int) -> None:
    for ch in texto:
        linhas = _DIGITOS_3X5.get(ch)
        if linhas is None:
            x += 4
            continue
        for dy, linha in enumerate(linhas):
            for dx, bit in enumerate(linha):
                if bit == "1":
                    fb.pixel(x + dx, y + dy)
        x += 4
