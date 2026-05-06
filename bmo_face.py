import pygame
import sys
import math

# ─── Resolucao OLED real ──────────────────────────────────────────────────────
OLED_W = 128
OLED_H = 64

# ─── Escala para teste no PC ──────────────────────────────────────────────────
SCALE = 5      # janela = 640 x 320
FPS   = 30

# ─── Paleta BMO ───────────────────────────────────────────────────────────────
C_BODY       = (62,  201, 167)
C_FACE       = (42,  168, 138)
C_EYE_WHITE  = (223, 245, 236)
C_EYE_DARK   = (26,  74,  56)
C_EYE_PUPIL  = (10,  40,  32)
C_MOUTH      = (26,  102, 80)
C_BORDER     = (26,  122, 90)
C_CHEEK      = (90,  212, 176)
C_TEAR       = (160, 232, 216)
C_ZZZ        = (160, 220, 200)
C_NOTE       = (160, 220, 200)
C_SHOCK      = (160, 220, 200)
C_WIN_BG     = (28,  43,  43)
C_PIXEL_ON   = C_EYE_DARK


# ─── FrameBuffer 1-bit: 128x64 = 1024 bytes exatos ───────────────────────────
class FrameBuffer:
    """
    Espelha exatamente a RAM de video do SSD1306.
    1 bit por pixel -> 1024 bytes totais.
    Pixels fora dos limites sao ignorados silenciosamente.
    """
    __slots__ = ('buf',)

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

    def rect(self, x, y, w, h, on=True, fill=True):
        if fill:
            for row in range(h):
                self.hline(x, y + row, w, on)
        else:
            self.hline(x, y, w, on)
            self.hline(x, y + h - 1, w, on)
            self.vline(x, y, h, on)
            self.vline(x + w - 1, y, h, on)

    def circle(self, cx, cy, r, on=True, fill=True):
        if fill:
            for dy in range(-r, r + 1):
                dx = int(math.sqrt(max(0, r * r - dy * dy)))
                self.hline(cx - dx, cy + dy, dx * 2 + 1, on)
        else:
            x, y, err = r, 0, 0
            while x >= y:
                for sx, sy in [(x,y),(-x,y),(x,-y),(-x,-y),(y,x),(-y,x),(y,-x),(-y,-x)]:
                    self.pixel(cx + sx, cy + sy, on)
                y += 1
                err += 1 + 2 * y
                if 2 * (err - x) + 1 > 0:
                    x -= 1
                    err += 1 - 2 * x

    def ellipse(self, cx, cy, rx, ry, on=True, fill=True):
        if fill:
            for dy in range(-ry, ry + 1):
                dx = round(rx * math.sqrt(max(0.0, 1 - (dy / ry) ** 2)))
                self.hline(cx - dx, cy + dy, dx * 2 + 1, on)
        else:
            for angle in range(360):
                rad = math.radians(angle)
                self.pixel(round(cx + rx * math.cos(rad)),
                           round(cy + ry * math.sin(rad)), on)

    def rounded_rect(self, x, y, w, h, r, on=True, fill=True):
        """Retangulo com cantos arredondados — essencial para visual BMO."""
        r = min(r, w // 2, h // 2)
        if fill:
            # interior
            self.rect(x + r, y,         w - 2 * r, h,         on)
            self.rect(x,     y + r,     r,         h - 2 * r, on)
            self.rect(x + w - r, y + r, r,         h - 2 * r, on)
            # quatro cantos arredondados
            for dy in range(r + 1):
                dx = round(math.sqrt(max(0, r * r - dy * dy)))
                self.hline(x + r - dx,         y + r - dy,         dx, on)
                self.hline(x + w - r,           y + r - dy,         dx, on)
                self.hline(x + r - dx,         y + h - r + dy - 1, dx, on)
                self.hline(x + w - r,           y + h - r + dy - 1, dx, on)
        else:
            # apenas contorno
            self.hline(x + r, y,         w - 2 * r, on)
            self.hline(x + r, y + h - 1, w - 2 * r, on)
            self.vline(x,         y + r, h - 2 * r, on)
            self.vline(x + w - 1, y + r, h - 2 * r, on)
            for a in range(91):
                rad = math.radians(a)
                dx  = round(r * math.cos(rad))
                dy  = round(r * math.sin(rad))
                self.pixel(x + r         - dx, y + r         - dy, on)
                self.pixel(x + w - r - 1 + dx, y + r         - dy, on)
                self.pixel(x + r         - dx, y + h - r - 1 + dy, on)
                self.pixel(x + w - r - 1 + dx, y + h - r - 1 + dy, on)

    def arc(self, cx, cy, r, start_deg, end_deg, on=True, thickness=2):
        """Arco de circulo. start_deg e end_deg em graus (0 = direita, 90 = baixo)."""
        step = 1
        a = start_deg
        while a <= end_deg:
            rad = math.radians(a)
            for t in range(thickness):
                self.pixel(round(cx + (r - t) * math.cos(rad)),
                           round(cy + (r - t) * math.sin(rad)), on)
            a += step

    def memory_bytes(self):
        return len(self.buf)


# ─── Faces do BMO ─────────────────────────────────────────────────────────────
class BMOFace:
    """
    Cada metodo draw_*() preenche o FrameBuffer com um frame completo.
    Usa exatamente 1 FrameBuffer = 1024 bytes de RAM de imagem.
    Todas as formas sao arredondadas para manter o estilo fofo do BMO.
    """

    EL  = (32, 28)    # centro olho esquerdo
    ER  = (93, 28)    # centro olho direito
    MX  = 64          # centro x da boca
    MY  = 42          # centro y da boca

    def __init__(self, fb):
        self.fb = fb

    # ── base: corpo + borda ───────────────────────────────────────────────────
    def _base(self):
        self.fb.clear()

    # ── olhos ─────────────────────────────────────────────────────────────────
    def _eye_normal(self, cx, cy, blink=False):
        fb = self.fb
        if blink:
            fb.hline(cx - 7, cy, 14)
            fb.hline(cx - 7, cy + 1, 14)
            return
        # Desenha o olho sólido clássico do BMO (uma elipse preenchida)
        fb.ellipse(cx, cy, 5, 7)                            

    def _eye_happy(self, cx, cy):
        """Olho feliz: arco virado para CIMA (curva ^)."""
        # arc de 180 a 360 graus = semicirculo superior = curva pra cima
        self.fb.arc(cx, cy + 5, 7, 180, 360, thickness=3)

    def _eye_sad(self, cx, cy):
        """Olho triste: arco virado para BAIXO (curva U)."""
        # arc de 0 a 180 graus = semicirculo inferior = curva pra baixo
        self.fb.arc(cx, cy - 5, 7, 0, 180, thickness=3)

    def _eye_surprised(self, cx, cy):
        self.fb.ellipse(cx, cy, 7, 9)

    def _eye_sleepy(self, cx, cy):
        fb = self.fb
        fb.ellipse(cx, cy, 5, 7)
        # Desenha um retângulo com a cor de fundo (on=False) para 'cortar' a metade de cima
        fb.rect(cx - 6, cy - 8, 12, 9, on=False)

    def _eye_singing(self, cx, cy, blink=False):
        fb = self.fb
        if blink:
            fb.hline(cx - 7, cy, 14)
            fb.hline(cx - 7, cy + 1, 14)
            return
        fb.ellipse(cx, cy, 4, 6)

    def _eye_wink_closed(self, cx, cy):
        """Olho fechado com sorriso para wink."""
        self.fb.arc(cx, cy + 5, 7, 180, 360, thickness=3)

    # ── bocas ─────────────────────────────────────────────────────────────────
    def _mouth_normal(self):

        self.fb.arc(self.MX, self.MY - 18, 24, 55, 125, thickness=4)

    def _mouth_happy(self):
        """Boca feliz: arco voltado para CIMA (sorriso aberto)."""
        # arc de 10 a 170 graus com centro acima = curva de sorriso
        self.fb.arc(self.MX, self.MY - 6, 10, 15, 165, thickness=3)

    def _mouth_sad(self):
        """Boca triste: arco voltado para BAIXO."""
        # arc de 190 a 350 graus com centro abaixo = franza o labio
        self.fb.arc(self.MX, self.MY + 6, 10, 195, 345, thickness=3)

    def _mouth_speaking(self, frame):
        mx, my = self.MX, self.MY

        f = (frame // 4) % 4

        if f == 0:
            self.fb.rounded_rect(mx -8, my - 8, 16, 16, 5)
        elif f == 1:
            self.fb.rounded_rect(mx -12, my - 4, 24, 8, 4)
        elif f == 2:
            self.fb.circle(mx, my, 5)
        elif f == 3:
            self.fb.rounded_rect(mx -15, my -2, 30, 4, 2)

    def _mouth_open(self):
        mx, my = self.MX, self.MY
        self.fb.rounded_rect(mx - 8, my - 5, 16, 10, 5)
        self.fb.rounded_rect(mx - 6, my - 3, 12, 6,  3, on=False)

    def _mouth_singing(self, frame):
        mx, my = self.MX, self.MY
        h = 4 + round(3 * math.sin(frame * 0.2))
        self.fb.rounded_rect(mx - 8, my - h, 16, h * 2, 6)
        self.fb.rounded_rect(mx - 6, my - h + 2, 12, h * 2 - 4, 4, on=False)

    def _mouth_tiny(self):
        self.fb.arc(self.MX, self.MY - 2, 5, 20, 160, thickness=2)

    # ── estados animados ──────────────────────────────────────────────────────
    def draw_idle(self, frame):
        blink = (frame % 180) < 5
        self._base()
        self._eye_normal(*self.EL, blink)
        self._eye_normal(*self.ER, blink)
        self._mouth_normal()
        # cursor terminal piscante
        if (frame // 15) % 2 == 0:
            self.fb.rounded_rect(14, OLED_H - 11, 5, 4, 2)

    def draw_speaking(self, frame):
        blink = (frame % 100) < 4

        self._base()

        self._eye_normal(*self.EL, blink)
        self._eye_normal(*self.ER, blink)
        
        # Chama a nossa nova máquina de frames da boca
        self._mouth_speaking(frame)

    def draw_happy(self, frame):
        bounce = round(math.sin(frame * 0.13) * 1.5)
        self._base()
        self._eye_happy(self.EL[0], self.EL[1] + bounce)
        self._eye_happy(self.ER[0], self.ER[1] + bounce)
        self._mouth_happy()
        # bochechas redondas
        self.fb.circle(22, 42, 4)
        self.fb.circle(106, 42, 4)

    def draw_sad(self, frame):
        self._base()
        self._eye_sad(*self.EL)
        self._eye_sad(*self.ER)
        self._mouth_sad()
        # lagrimas caidoras (elipses arredondadas)
        t = frame % 60
        if t < 55:
            ly = 38 + t
            if ly < OLED_H - 6:
                self.fb.ellipse(38, ly, 2, 3)
                self.fb.ellipse(86, ly, 2, 3)

    def draw_sleepy(self, frame):
        self._base()
        self._eye_sleepy(*self.EL)
        self._eye_sleepy(*self.ER)
        self._mouth_tiny()
        # zzz flutuante (pixels manuais para economizar memoria)
        for zi in range(3):
            t = (frame * 0.4 + zi * 15) % 40
            nx = 98 + zi * 8
            ny = round(18 - t)
            if 6 < ny < OLED_H - 8:
                self.fb.hline(nx,     ny,     5)
                self.fb.pixel(nx + 4, ny + 1)
                self.fb.pixel(nx + 3, ny + 2)
                self.fb.pixel(nx + 2, ny + 3)
                self.fb.pixel(nx + 1, ny + 4)
                self.fb.hline(nx,     ny + 5, 5)

    def draw_surprised(self, frame):
        shake = round(math.sin(frame * 0.9) * 1)
        self._base()
        self._eye_surprised(self.EL[0] + shake, self.EL[1])
        self._eye_surprised(self.ER[0] + shake, self.ER[1])
        self._mouth_open()
        # linhas de choque rotativas
        for a in range(6):
            ang = math.radians(a * 60 + frame * 3)
            for cx in (self.EL[0], self.ER[0]):
                x1 = round(cx + math.cos(ang) * 12)
                y1 = round(28 + math.sin(ang) * 12)
                x2 = round(cx + math.cos(ang) * 18)
                y2 = round(28 + math.sin(ang) * 18)
                for step in range(6):
                    t = step / 5
                    self.fb.pixel(round(x1 + (x2 - x1) * t),
                                  round(y1 + (y2 - y1) * t))

    def draw_singing(self, frame):
        blink = (frame % 100) < 4
        self._base()
        self._eye_singing(self.EL[0], self.EL[1], blink)
        self._eye_singing(self.ER[0], self.ER[1], blink)
        self._mouth_singing(frame)
        # notas musicais flutuantes
        for i, phase in enumerate([0, 18, 36]):
            t = (frame + phase) % 50
            nx = 98 + i * 7
            ny = round(20 - t)
            if 6 < ny < OLED_H - 8:
                self.fb.circle(nx, ny, 2)
                self.fb.vline(nx + 2, ny - 7, 7)
                self.fb.hline(nx + 2, ny - 7, 4)

    def draw_wink(self, frame):
        self._base()
        self._eye_normal(*self.EL)
        self._eye_wink_closed(*self.ER)
        self._mouth_happy()
        self.fb.circle(106, 42, 4)

    def draw_boot(self, frame):
        self.fb.clear()
        self.fb.rounded_rect(2, 2, 124, 60, 14, on=False, fill=False)
        p = min(frame / 80.0, 1.0)
        _draw_bmo_logo(self.fb, 44, 10)
        self.fb.rounded_rect(18, 32, 92, 10, 4, on=False, fill=False)
        if p > 0:
            self.fb.rounded_rect(19, 33, round(90 * p), 8, 3)
        if p >= 1.0 and (frame // 12) % 2 == 0:
            self.fb.hline(52, 50, 24)
            self.fb.hline(52, 51, 24)


# ─── Logo BMO em pixels (5x7 escala 2x) ──────────────────────────────────────
def _draw_bmo_logo(fb, x, y):
    glyphs = {
        'B': [(0,0,3,1),(0,0,1,5),(0,2,3,1),(3,0,1,2),(3,3,1,2),(0,4,3,1)],
        'M': [(0,0,1,5),(0,0,2,2),(2,2,1,1),(2,0,2,2),(4,0,1,5)],
        'O': [(1,0,3,1),(0,1,1,3),(4,1,1,3),(1,4,3,1)],
    }
    sc = 2
    for ch in 'BMO':
        for sx, sy, sw, sh in glyphs.get(ch, []):
            fb.rect(x + sx * sc, y + sy * sc, sw * sc, sh * sc)
        x += 7 * sc


# ─── Renderizador Pygame com cores BMO reais ──────────────────────────────────
class PygameRenderer:
    """
    Converte o FrameBuffer 1-bit em pixels coloridos do BMO.
    A superficie OLED usa as cores exatas do personagem.
    """

    def __init__(self, scale=SCALE):
        self.scale = scale
        self.win_w = OLED_W * scale
        self.win_h = OLED_H * scale + 60
        pygame.init()
        self.screen  = pygame.display.set_mode((self.win_w, self.win_h))
        pygame.display.set_caption("BMO Virtual Friend — Teste Local")
        self.surf    = pygame.Surface((OLED_W, OLED_H))
        self.font    = pygame.font.SysFont("monospace", 11)
        self.clock   = pygame.time.Clock()

    def render(self, fb, state_name, frame):
        self.screen.fill(C_WIN_BG)

        # preenche a superficie 1:1 com as cores do BMO
        self.surf.fill(C_BODY)                  # fundo = corpo verde-agua
        for py in range(OLED_H):
            for px in range(OLED_W):
                if fb.get(px, py):
                    self.surf.set_at((px, py), C_PIXEL_ON)

        scaled = pygame.transform.scale(
            self.surf, (OLED_W * self.scale, OLED_H * self.scale)
        )
        self.screen.blit(scaled, (0, 0))

        # barra de status
        bar_y = OLED_H * self.scale + 4
        self.screen.blit(
            self.font.render(f"  Estado: {state_name}", True, (77, 255, 180)), (0, bar_y))
        self.screen.blit(
            self.font.render(
                f"  RAM frame: {fb.memory_bytes()} bytes  |  FPS: {int(self.clock.get_fps())}",
                True, (42, 122, 90)), (0, bar_y + 16))
        self.screen.blit(
            self.font.render(
                "  [1]Idle [2]Feliz [3]Triste [4]Sonolento [5]Surpreso [6]Cantando [7]Wink [8]Boot",
                True, (30, 80, 60)), (0, bar_y + 32))

        pygame.display.flip()
        self.clock.tick(FPS)


# ─── Loop principal ───────────────────────────────────────────────────────────
def main():
    fb       = FrameBuffer()
    face     = BMOFace(fb)
    renderer = PygameRenderer()

    states = {
        pygame.K_1: ("IDLE", face.draw_idle),
        pygame.K_2: ("FELIZ", face.draw_happy),
        pygame.K_3: ("TRISTE", face.draw_sad),
        pygame.K_4: ("SONOLENTO", face.draw_sleepy),
        pygame.K_5: ("SURPRESO", face.draw_surprised),
        pygame.K_6: ("CANTANDO", face.draw_singing),
        pygame.K_7: ("WINK", face.draw_wink),
        pygame.K_8: ("BOOT", face.draw_boot),
        pygame.K_9: ("FALANDO", face.draw_speaking)
    }

    current_name = "IDLE"
    current_draw = face.draw_idle
    frame = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key in states:
                    current_name, current_draw = states[event.key]
                    frame = 0

        current_draw(frame)
        renderer.render(fb, current_name, frame)
        frame += 1


if __name__ == "__main__":
    main()