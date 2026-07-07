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

    def mudar(self, modo: str, emocao: str | None = None, detalhe: str = "") -> None:
        with self._lock:
            self.modo = modo
            self.emocao = emocao
            self.detalhe = detalhe
            self.desde = time.monotonic()

    def ler(self) -> tuple[str, str | None, float]:
        with self._lock:
            return self.modo, self.emocao, time.monotonic() - self.desde


# ─── FrameBuffer 1-bit (espelha a RAM de um OLED SSD1306) ───────────────────


class FrameBuffer:
    __slots__ = ("buf",)

    def __init__(self):
        self.buf = bytearray(OLED_W * OLED_H // 8)

    def clear(self):
        for i in range(len(self.buf)):
            self.buf[i] = 0

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

    def draw_speaking(self, frame):
        self.fb.clear()
        blink = (frame % 100) < 4
        self._eye_normal(*self.EL, blink)
        self._eye_normal(*self.ER, blink)
        self._mouth_speaking(frame)

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
        self.fb.clear()
        self.fb.rounded_rect(2, 2, 124, 60, 14, fill=False)
        p = min(frame / 80.0, 1.0)
        _draw_bmo_logo(self.fb, 44, 10)
        self.fb.rounded_rect(18, 32, 92, 10, 4, fill=False)
        if p > 0:
            self.fb.rounded_rect(19, 33, round(90 * p), 8, 3)
        if p >= 1.0 and (frame // 12) % 2 == 0:
            self.fb.hline(52, 50, 24)
            self.fb.hline(52, 51, 24)


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


def desenhar_estado(rosto: RostoBMO, estado: EstadoBMO, frame: int) -> str:
    """Desenha o frame certo para o estado atual. Retorna o nome do desenho
    usado (para testes e depuração)."""
    modo, emocao, ha_quanto = estado.ler()

    if modo == "boot":
        nome = "draw_boot"
    elif modo == "ouvindo":
        nome = "draw_listening"
    elif modo == "processando":
        nome = "draw_thinking"
    elif modo == "falando":
        nome = "draw_speaking"
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
