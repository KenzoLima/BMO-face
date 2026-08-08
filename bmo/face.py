"""O rosto do BMO — renderização em framebuffer estilo OLED (128x64, 1-bit).

Portado do bmo_face.py original e integrado ao assistente:

- ``FrameBuffer``/``RostoBMO``: desenho puro, sem janela — testável e reusável
  (inclusive num display OLED físico no futuro).
- ``EstadoBMO``: objeto thread-safe que o loop de voz atualiza e o loop da
  janela lê a cada frame.
- ``desenhar_estado()``: mapeia (modo, emoção, tempo) → frame do rosto.

Modos: boot, standby, ouvindo, processando, falando, erro.
Emoções (vindas do prefixo [feliz] etc. das respostas): feliz, triste,
surpreso, dormindo, pensativo, focado.
"""

from __future__ import annotations

import math
import re
import threading
import time

OLED_W = 128
OLED_H = 64

SEGUNDOS_EXIBINDO_EMOCAO = 3.0   # após falar, segura a emoção no rosto
SEGUNDOS_ATE_DORMIR = 90.0       # standby prolongado → rosto sonolento
JANELA_ENVELOPE = 0.05           # lip sync: 1 amostra de amplitude a cada 50ms

_RE_EMOCAO = re.compile(
    r"\[(feliz|pensativo|surpreso|triste|focado|dormindo)\]", re.IGNORECASE
)


def extrair_emocao(texto: str) -> str | None:
    """Lê a emoção do prefixo [feliz] etc. de uma resposta do BMO."""
    achado = _RE_EMOCAO.search(texto or "")
    return achado.group(1).lower() if achado else None


class EstadoBMO:
    """Estado compartilhado entre o loop de voz (worker) e a janela (UI)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.modo = "boot"
        self.emocao: str | None = None
        self.detalhe = ""          # ex.: mensagem de erro curta
        self.desde = time.monotonic()
        self.envelope: list[float] | None = None  # amplitudes da fala atual

    def mudar(self, modo: str, emocao: str | None = None, detalhe: str = "") -> None:
        with self._lock:
            self.modo = modo
            self.emocao = emocao
            self.detalhe = detalhe
            self.envelope = None
            self.desde = time.monotonic()

    def iniciar_fala(self, envelope: list[float] | None, emocao: str | None = None) -> None:
        """Chamado no instante em que o áudio COMEÇA a tocar — o relógio do
        lip sync parte daqui."""
        with self._lock:
            self.modo = "falando"
            self.emocao = emocao
            self.envelope = envelope or None
            self.desde = time.monotonic()

    def amplitude_boca(self) -> float | None:
        """Amplitude (0..1) da fala neste instante; None = sem lip sync."""
        with self._lock:
            if self.modo != "falando" or not self.envelope:
                return None
            indice = int((time.monotonic() - self.desde) / JANELA_ENVELOPE)
            if indice >= len(self.envelope):
                return 0.0
            return self.envelope[indice]

    def ler(self) -> tuple[str, str | None, float]:
        with self._lock:
            return self.modo, self.emocao, time.monotonic() - self.desde


# ─── FrameBuffer 1-bit (espelha a RAM de um OLED SSD1306) ───────────────────


_BYTES_FRAME = OLED_W * OLED_H // 8
_FRAME_VAZIO = bytes(_BYTES_FRAME)  # zeros prontos: clear() vira uma cópia só

# Trigonometria por grau inteiro, pré-calculada para o arc() (ver FrameBuffer).
# A faixa cobre com folga o que o rosto usa (de -50° a 360°).
_GRAUS_BASE = 360
_GRAUS_LIMITE = 721
_GRAUS_COS = tuple(math.cos(math.radians(a)) for a in range(-_GRAUS_BASE, _GRAUS_LIMITE))
_GRAUS_SIN = tuple(math.sin(math.radians(a)) for a in range(-_GRAUS_BASE, _GRAUS_LIMITE))


class FrameBuffer:
    __slots__ = ("buf",)

    def __init__(self):
        self.buf = bytearray(_BYTES_FRAME)

    def clear(self):
        self.buf[:] = _FRAME_VAZIO

    def pixel(self, x, y, on=True):
        if 0 <= x < OLED_W and 0 <= y < OLED_H:
            idx = (y >> 3) * OLED_W + x
            bit = 1 << (y & 7)
            if on:
                self.buf[idx] |= bit
            else:
                self.buf[idx] &= ~bit

    def get(self, x, y):
        if 0 <= x < OLED_W and 0 <= y < OLED_H:
            return bool(self.buf[(y >> 3) * OLED_W + x] & (1 << (y & 7)))
        return False

    def hline(self, x, y, w, on=True):
        for i in range(w):
            self.pixel(x + i, y, on)

    def vline(self, x, y, h, on=True):
        for i in range(h):
            self.pixel(x, y + i, on)

    def line(self, x0, y0, x1, y1, on=True, thickness=1):
        """Linha de Bresenham (para os olhos em X do estado de erro)."""
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            for t in range(thickness):
                self.pixel(x0 + t, y0, on)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def rect(self, x, y, w, h, on=True):
        for row in range(h):
            self.hline(x, y + row, w, on)

    def circle(self, cx, cy, r, on=True):
        for dy in range(-r, r + 1):
            dx = int(math.sqrt(max(0, r * r - dy * dy)))
            self.hline(cx - dx, cy + dy, dx * 2 + 1, on)

    def ellipse(self, cx, cy, rx, ry, on=True):
        for dy in range(-ry, ry + 1):
            dx = round(rx * math.sqrt(max(0.0, 1 - (dy / ry) ** 2)))
            self.hline(cx - dx, cy + dy, dx * 2 + 1, on)

    def rounded_rect(self, x, y, w, h, r, on=True, fill=True):
        r = min(r, w // 2, h // 2)
        if fill:
            self.rect(x + r, y, w - 2 * r, h, on)
            self.rect(x, y + r, r, h - 2 * r, on)
            self.rect(x + w - r, y + r, r, h - 2 * r, on)
            for dy in range(r + 1):
                dx = round(math.sqrt(max(0, r * r - dy * dy)))
                self.hline(x + r - dx, y + r - dy, dx, on)
                self.hline(x + w - r, y + r - dy, dx, on)
                self.hline(x + r - dx, y + h - r + dy - 1, dx, on)
                self.hline(x + w - r, y + h - r + dy - 1, dx, on)
        else:
            self.hline(x + r, y, w - 2 * r, on)
            self.hline(x + r, y + h - 1, w - 2 * r, on)
            self.vline(x, y + r, h - 2 * r, on)
            self.vline(x + w - 1, y + r, h - 2 * r, on)
            for a in range(91):
                rad = math.radians(a)
                dx = round(r * math.cos(rad))
                dy = round(r * math.sin(rad))
                self.pixel(x + r - dx, y + r - dy, on)
                self.pixel(x + w - r - 1 + dx, y + r - dy, on)
                self.pixel(x + r - dx, y + h - r - 1 + dy, on)
                self.pixel(x + w - r - 1 + dx, y + h - r - 1 + dy, on)

    def arc(self, cx, cy, r, start_deg, end_deg, on=True, thickness=2):
        """Arco desenhado de grau em grau.

        É o primitivo mais usado do rosto (todos os olhos e bocas curvos), por
        isso o seno/cosseno de cada grau inteiro sai de tabela. Ângulos
        quebrados ou fora da faixa tabelada caem no cálculo direto.
        """
        inicio, fim = int(start_deg), int(end_deg)
        if inicio == start_deg and -_GRAUS_BASE <= inicio and fim < _GRAUS_LIMITE:
            pixel = self.pixel
            for a in range(inicio, fim + 1):
                cos_a, sen_a = _GRAUS_COS[a + _GRAUS_BASE], _GRAUS_SIN[a + _GRAUS_BASE]
                for t in range(thickness):
                    raio = r - t
                    pixel(round(cx + raio * cos_a), round(cy + raio * sen_a), on)
            return

        a = start_deg
        while a <= end_deg:
            rad = math.radians(a)
            for t in range(thickness):
                self.pixel(round(cx + (r - t) * math.cos(rad)),
                           round(cy + (r - t) * math.sin(rad)), on)
            a += 1


# ─── Rosto do BMO ────────────────────────────────────────────────────────────


class RostoBMO:
    """Cada método draw_*() desenha um frame completo no FrameBuffer."""

    EL = (32, 28)   # olho esquerdo
    ER = (93, 28)   # olho direito
    MX = 64         # centro x da boca
    MY = 42         # centro y da boca

    def __init__(self, fb: FrameBuffer):
        self.fb = fb

    # ── olhos ────────────────────────────────────────────────────────────
    def _eye_normal(self, cx, cy, blink=False):
        if blink:
            self.fb.hline(cx - 7, cy, 14)
            self.fb.hline(cx - 7, cy + 1, 14)
        else:
            self.fb.ellipse(cx, cy, 5, 7)

    def _eye_happy(self, cx, cy):
        self.fb.arc(cx, cy + 5, 7, 180, 360, thickness=3)

    def _eye_sad(self, cx, cy):
        self.fb.arc(cx, cy - 5, 7, 0, 180, thickness=3)

    def _eye_surprised(self, cx, cy):
        self.fb.ellipse(cx, cy, 7, 9)

    def _eye_sleepy(self, cx, cy):
        self.fb.ellipse(cx, cy, 5, 7)
        self.fb.rect(cx - 6, cy - 8, 12, 9, on=False)

    def _eye_x(self, cx, cy):
        self.fb.line(cx - 5, cy - 6, cx + 5, cy + 6, thickness=2)
        self.fb.line(cx - 5, cy + 6, cx + 5, cy - 6, thickness=2)

    # ── bocas ────────────────────────────────────────────────────────────
    def _mouth_normal(self):
        self.fb.arc(self.MX, self.MY - 18, 24, 55, 125, thickness=4)

    def _mouth_happy(self):
        self.fb.arc(self.MX, self.MY - 6, 10, 15, 165, thickness=3)

    def _mouth_sad(self):
        self.fb.arc(self.MX, self.MY + 6, 10, 195, 345, thickness=3)

    def _mouth_open(self):
        self.fb.rounded_rect(self.MX - 8, self.MY - 5, 16, 10, 5)
        self.fb.rounded_rect(self.MX - 6, self.MY - 3, 12, 6, 3, on=False)

    def _mouth_tiny(self):
        self.fb.arc(self.MX, self.MY - 2, 5, 20, 160, thickness=2)

    def _mouth_flat(self):
        self.fb.hline(self.MX - 10, self.MY, 20)
        self.fb.hline(self.MX - 10, self.MY + 1, 20)

    def _mouth_speaking(self, frame):
        """Animação genérica (fallback quando não há envelope de áudio)."""
        mx, my = self.MX, self.MY
        f = (frame // 4) % 4
        if f == 0:
            self.fb.rounded_rect(mx - 8, my - 8, 16, 16, 5)
        elif f == 1:
            self.fb.rounded_rect(mx - 12, my - 4, 24, 8, 4)
        elif f == 2:
            self.fb.circle(mx, my, 5)
        else:
            self.fb.rounded_rect(mx - 15, my - 2, 30, 4, 2)

    def _mouth_sync(self, amplitude: float):
        """Boca guiada pelo volume da voz (lip sync): fechada no silêncio,
        escancarada nos picos."""
        mx, my = self.MX, self.MY
        if amplitude < 0.12:    # pausa/respiro → boca fechada
            self.fb.rounded_rect(mx - 10, my - 1, 20, 3, 1)
        elif amplitude < 0.35:  # fala baixa → boca pequena
            self.fb.circle(mx, my, 4)
        elif amplitude < 0.65:  # fala média → boca aberta larga
            self.fb.rounded_rect(mx - 12, my - 5, 24, 10, 5)
        else:                   # pico → escancarada, com "garganta"
            self.fb.rounded_rect(mx - 9, my - 8, 18, 17, 6)
            self.fb.rounded_rect(mx - 5, my + 2, 10, 5, 2, on=False)

    # ── estados ──────────────────────────────────────────────────────────
    def draw_idle(self, frame):
        self.fb.clear()
        blink = (frame % 180) < 5
        self._eye_normal(*self.EL, blink)
        self._eye_normal(*self.ER, blink)
        self._mouth_normal()
        if (frame // 15) % 2 == 0:  # cursor de terminal piscante
            self.fb.rounded_rect(14, OLED_H - 11, 5, 4, 2)

    def draw_listening(self, frame):
        """Ouvindo: olhos grandes e atentos + ondas sonoras pulsando."""
        self.fb.clear()
        self._eye_normal(self.EL[0], self.EL[1] - 2)
        self._eye_normal(self.ER[0], self.ER[1] - 2)
        self._mouth_tiny()
        # ondas de som nas laterais, pulsando
        pulso = (frame // 6) % 3
        for i in range(pulso + 1):
            r = 6 + i * 5
            self.fb.arc(10, 32, r, -50, 50, thickness=2)          # esquerda
            self.fb.arc(OLED_W - 10, 32, r, 130, 230, thickness=2)  # direita

    def draw_thinking(self, frame):
        """Processando: olhos olhando para cima + reticências animadas."""
        self.fb.clear()
        self._eye_normal(self.EL[0] + 3, self.EL[1] - 3)
        self._eye_normal(self.ER[0] + 3, self.ER[1] - 3)
        self._mouth_tiny()
        pontos = (frame // 10) % 4
        for i in range(pontos):
            self.fb.circle(52 + i * 12, 56, 2)

    def draw_speaking(self, frame, amplitude: float | None = None):
        self.fb.clear()
        blink = (frame % 100) < 4
        self._eye_normal(*self.EL, blink)
        self._eye_normal(*self.ER, blink)
        if amplitude is None:
            self._mouth_speaking(frame)
        else:
            self._mouth_sync(amplitude)

    def draw_happy(self, frame):
        self.fb.clear()
        bounce = round(math.sin(frame * 0.13) * 1.5)
        self._eye_happy(self.EL[0], self.EL[1] + bounce)
        self._eye_happy(self.ER[0], self.ER[1] + bounce)
        self._mouth_happy()
        self.fb.circle(22, 42, 4)
        self.fb.circle(106, 42, 4)

    def draw_sad(self, frame):
        self.fb.clear()
        self._eye_sad(*self.EL)
        self._eye_sad(*self.ER)
        self._mouth_sad()
        t = frame % 60
        if t < 55:
            ly = 38 + t
            if ly < OLED_H - 6:
                self.fb.ellipse(38, ly, 2, 3)
                self.fb.ellipse(86, ly, 2, 3)

    def draw_surprised(self, frame):
        self.fb.clear()
        shake = round(math.sin(frame * 0.9))
        self._eye_surprised(self.EL[0] + shake, self.EL[1])
        self._eye_surprised(self.ER[0] + shake, self.ER[1])
        self._mouth_open()

    def draw_sleepy(self, frame):
        self.fb.clear()
        self._eye_sleepy(*self.EL)
        self._eye_sleepy(*self.ER)
        self._mouth_tiny()
        for zi in range(3):
            t = (frame * 0.4 + zi * 15) % 40
            nx = 98 + zi * 8
            ny = round(18 - t)
            if 6 < ny < OLED_H - 8:
                self.fb.hline(nx, ny, 5)
                self.fb.pixel(nx + 4, ny + 1)
                self.fb.pixel(nx + 3, ny + 2)
                self.fb.pixel(nx + 2, ny + 3)
                self.fb.pixel(nx + 1, ny + 4)
                self.fb.hline(nx, ny + 5, 5)

    def draw_pesquisando(self, frame, progresso: float | None = None):
        """Pesquisando na internet: lupa varrendo + barra de carregamento.

        Existe porque uma ferramenta lenta (busca na web, lembretes) deixava
        o rosto parado, e o usuário não tinha como saber se o BMO estava
        trabalhando ou travado. ``progresso=None`` sobe sozinho e para em 95%
        (não sabemos quanto falta); ``1.0`` é a tela concluída.
        """
        self.fb.clear()
        olhos_y = self.EL[1] - 6
        # olhos acompanham a lupa, de um lado para o outro
        desvio = round(math.sin(frame * 0.08) * 4)
        self._eye_normal(self.EL[0] + desvio, olhos_y)
        self._eye_normal(self.ER[0] + desvio, olhos_y)

        # lupa deslizando sobre a barra
        if progresso is None:
            progresso = min(frame / 150.0, 0.95)
        cheio = max(4, round(90 * progresso))
        self.fb.rounded_rect(18, 42, 92, 10, 4, fill=False)
        self.fb.rounded_rect(19, 43, cheio, 8, 3)

        lupa_x = 19 + min(cheio, 86)
        self.fb.circle(lupa_x, 34, 5, on=True)
        self.fb.circle(lupa_x, 34, 3, on=False)   # lente vazada
        self.fb.line(lupa_x + 3, 37, lupa_x + 6, 40, thickness=2)

        if progresso >= 1.0:  # concluída: confirma antes de sair da tela
            self.fb.rect(60, 6, 3, 3)
            self.fb.rect(63, 9, 3, 3)
            self.fb.rect(66, 6, 3, 3)
            self.fb.rect(69, 3, 3, 3)
        elif (frame // 10) % 4 < 3:  # reticências pulsando
            for i in range((frame // 10) % 4):
                self.fb.circle(56 + i * 8, 20, 2)

    def draw_error(self, frame):
        """Erro: olhos em X e boca reta — pisca devagar para chamar atenção."""
        self.fb.clear()
        self._eye_x(*self.EL)
        self._eye_x(*self.ER)
        self._mouth_flat()
        if (frame // 20) % 2 == 0:  # ponto de exclamação piscando
            self.fb.rect(62, 6, 4, 8)
            self.fb.rect(62, 17, 4, 3)

    def draw_boot(self, frame):
        """Tela 1 do esboço: 'BEM VINDO!' + barra de carregamento."""
        self.fb.clear()
        _texto_pixel(self.fb, "BEM VINDO!", 35, 14)
        # a barra enche em ~4s e fica pulsando perto do fim enquanto carrega
        p = min(frame / 120.0, 0.95)
        self.fb.rounded_rect(18, 36, 92, 10, 4, fill=False)
        self.fb.rounded_rect(19, 37, max(4, round(90 * p)), 8, 3)
        if (frame // 15) % 2 == 0:  # cursor piscante estilo terminal
            self.fb.rounded_rect(14, OLED_H - 11, 5, 4, 2)

    def draw_apresentacao(self, frame, progresso: float):
        """Tela 1 → Tela 2 do esboço: as letras e a barra se dissolvem,
        pixel a pixel, no rosto do BMO.

        A origem (boot com a barra cheia) e o ruído por pixel são constantes:
        ficam em cache de módulo em vez de serem refeitos a cada frame — este
        era, de longe, o frame mais caro do BMO.
        """
        origem = _origem_apresentacao()
        destino = FrameBuffer()
        RostoBMO(destino).draw_idle(frame)

        self.fb.clear()
        for y in range(OLED_H):
            limiares = _LIMIARES_DISSOLUCAO[y]
            for x in range(OLED_W):
                fonte = destino if limiares[x] < progresso else origem
                if fonte.get(x, y):
                    self.fb.pixel(x, y)


# Fonte pixelada 5x7 (só os glifos usados nas telas do BMO)
_FONTE_5X7 = {
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    " ": ("00000",) * 7,
}


def _texto_pixel(fb: FrameBuffer, texto: str, x: int, y: int) -> None:
    for ch in texto.upper():
        linhas = _FONTE_5X7.get(ch, _FONTE_5X7[" "])
        for dy, linha in enumerate(linhas):
            for dx, bit in enumerate(linha):
                if bit == "1":
                    fb.pixel(x + dx, y + dy)
        x += 6


def _limiar_dissolucao(x: int, y: int) -> float:
    """Ruído determinístico por pixel (0..1) — dita a ordem da dissolução."""
    return ((x * 73_856_093) ^ (y * 19_349_663)) % 997 / 997.0


# Tabela do ruído (constante) — evita recalcular 8192 limiares por frame.
_LIMIARES_DISSOLUCAO = tuple(
    tuple(_limiar_dissolucao(x, y) for x in range(OLED_W)) for y in range(OLED_H)
)

_origem_cache: "FrameBuffer | None" = None


def _origem_apresentacao() -> "FrameBuffer":
    """Frame de onde a dissolução parte: o boot com a barra cheia (constante)."""
    global _origem_cache
    if _origem_cache is None:
        _origem_cache = FrameBuffer()
        RostoBMO(_origem_cache).draw_boot(120)
    return _origem_cache


def _draw_bmo_logo(fb: FrameBuffer, x: int, y: int) -> None:
    glyphs = {
        "B": [(0, 0, 3, 1), (0, 0, 1, 5), (0, 2, 3, 1), (3, 0, 1, 2), (3, 3, 1, 2), (0, 4, 3, 1)],
        "M": [(0, 0, 1, 5), (0, 0, 2, 2), (2, 2, 1, 1), (2, 0, 2, 2), (4, 0, 1, 5)],
        "O": [(1, 0, 3, 1), (0, 1, 1, 3), (4, 1, 1, 3), (1, 4, 3, 1)],
    }
    sc = 2
    for ch in "BMO":
        for sx, sy, sw, sh in glyphs[ch]:
            fb.rect(x + sx * sc, y + sy * sc, sw * sc, sh * sc)
        x += 7 * sc


# ─── Mapeamento estado → frame ───────────────────────────────────────────────

_EMOCAO_PARA_DRAW = {
    "feliz": "draw_happy",
    "triste": "draw_sad",
    "surpreso": "draw_surprised",
    "dormindo": "draw_sleepy",
    "pensativo": "draw_thinking",
    "focado": "draw_idle",
}


DURACAO_APRESENTACAO = 1.4  # segundos da dissolução boot → rosto


def desenhar_estado(rosto: RostoBMO, estado: EstadoBMO, frame: int) -> str:
    """Desenha o frame certo para o estado atual. Retorna o nome do desenho
    usado (para testes e depuração)."""
    modo, emocao, ha_quanto = estado.ler()

    if modo == "apresentacao":
        progresso = min(1.0, ha_quanto / DURACAO_APRESENTACAO)
        rosto.draw_apresentacao(frame, progresso)
        return "draw_apresentacao"

    if modo == "falando":
        rosto.draw_speaking(frame, amplitude=estado.amplitude_boca())
        return "draw_speaking"

    if modo == "pesquisando":
        rosto.draw_pesquisando(frame)
        return "draw_pesquisando"

    if modo == "pesquisa_concluida":
        rosto.draw_pesquisando(frame, progresso=1.0)
        return "draw_pesquisando"

    if modo == "boot":
        nome = "draw_boot"
    elif modo == "ouvindo":
        nome = "draw_listening"
    elif modo == "processando":
        nome = "draw_thinking"
    elif modo == "erro":
        nome = "draw_error"
    else:  # standby
        if emocao and ha_quanto < SEGUNDOS_EXIBINDO_EMOCAO:
            nome = _EMOCAO_PARA_DRAW.get(emocao, "draw_idle")
        elif ha_quanto > SEGUNDOS_ATE_DORMIR:
            nome = "draw_sleepy"
        else:
            nome = "draw_idle"

    getattr(rosto, nome)(frame)
    return nome
