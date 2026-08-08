"""Janela flutuante do BMO — pequena, sempre no topo, arrastável.

Renderiza o FrameBuffer do rosto em uma janela pygame sem borda (256x128),
fixada sobre as demais janelas via SetWindowPos (ctypes, sem dependências).

Controles:
- arrastar com o botão esquerdo move a janela;
- "×" no canto (aparece ao passar o mouse) ou ESC fecham o BMO.
"""

from __future__ import annotations

import ctypes
import math
import os
from ctypes import wintypes

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from .face import OLED_H, OLED_W, FrameBuffer

try:  # numpy vetoriza a conversão framebuffer → surface (13x mais rápido)
    import numpy as np
    import pygame.surfarray  # noqa: F401 - registra o backend de arrays
except ImportError:  # sem numpy o rosto ainda desenha, só que pixel a pixel
    np = None

_user32 = ctypes.windll.user32

# Sem argtypes, HWND vira int de 32 bits e HWND_TOPMOST (-1) é corrompido
# em processos de 64 bits — o SetWindowPos falha silenciosamente.
_user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]

# Paleta do BMO
COR_CORPO = (62, 201, 167)
COR_PIXEL = (26, 74, 56)
COR_BORDA = (26, 122, 90)
COR_FECHAR = (200, 80, 80)

# Win32
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
MARGEM_CANTO = 24

# Deslocamentos dos "dentes" da engrenagem — fixos, calculados uma vez só
# (antes saíam de seno/cosseno recalculados a cada frame com o mouse na janela)
_DENTES_ENGRENAGEM = tuple(
    (round(8 * math.cos(math.radians(a))), round(8 * math.sin(math.radians(a))))
    for a in range(0, 360, 60)
)


_PALETA = np.array([COR_CORPO, COR_PIXEL], dtype=np.uint8) if np is not None else None


def _pintar(surface: "pygame.Surface", fb: FrameBuffer) -> None:
    """Framebuffer 1-bit → surface 128x64 colorida.

    Com numpy a conversão é uma operação de array só; sem ele, cai no laço
    pixel a pixel (mesmo resultado, ~13x mais lento). Como isto roda a cada
    frame, a diferença aparece direto no uso de CPU do BMO parado na tela.
    """
    if np is None:
        surface.fill(COR_CORPO)
        for y in range(OLED_H):
            for x in range(OLED_W):
                if fb.get(x, y):
                    surface.set_at((x, y), COR_PIXEL)
        return

    # Layout do SSD1306: buf[(y >> 3) * OLED_W + x], com o bit (y & 7).
    # unpackbits desdobra cada byte-página nas 8 linhas que ele guarda.
    paginas = np.frombuffer(fb.buf, dtype=np.uint8).reshape(OLED_H // 8, OLED_W)
    bits = np.unpackbits(paginas[:, :, None], axis=2, bitorder="little")
    mascara = bits.transpose(0, 2, 1).reshape(OLED_H, OLED_W)  # (página, bit, x) → (y, x)
    pygame.surfarray.blit_array(surface, _PALETA[mascara].transpose(1, 0, 2))


def _icone_janela() -> "pygame.Surface":
    """Ícone da barra de tarefas: corpo quadrado com o rosto clássico.

    Segue pixel a pixel de propósito: precisa do fundo TRANSPARENTE (SRCALPHA)
    para o smoothscale suavizar só o rosto, e roda uma única vez no boot.
    """
    from .face import RostoBMO

    fb = FrameBuffer()
    RostoBMO(fb).draw_idle(16)  # frame sem piscada e sem cursor

    corpo = pygame.Surface((128, 128))
    corpo.fill(COR_BORDA)
    pygame.draw.rect(corpo, COR_CORPO, pygame.Rect(4, 4, 120, 120), border_radius=18)

    rosto = pygame.Surface((OLED_W, OLED_H), pygame.SRCALPHA)
    for y in range(OLED_H):
        for x in range(OLED_W):
            if fb.get(x, y):
                rosto.set_at((x, y), COR_PIXEL)
    corpo.blit(pygame.transform.smoothscale(rosto, (124, 62)), (2, 33))
    return pygame.transform.smoothscale(corpo, (32, 32))


class JanelaBMO:
    def __init__(self, escala: int = 2, fps: int = 30):
        self.escala = escala
        self.fps = fps
        self.largura = OLED_W * escala
        self.altura = OLED_H * escala

        # coordenadas físicas (senão o Windows "virtualiza" posições em
        # telas com escala de DPI, e a janela vai parar no lugar errado)
        try:
            _user32.SetProcessDPIAware()
        except OSError:
            pass

        pygame.init()
        pygame.display.set_caption("BMO")
        pygame.display.set_icon(_icone_janela())  # carinha na barra de tarefas
        self.tela = pygame.display.set_mode(
            (self.largura, self.altura), pygame.NOFRAME
        )
        self.surface = pygame.Surface((OLED_W, OLED_H))
        self.clock = pygame.time.Clock()

        self._hwnd = pygame.display.get_wm_info()["window"]
        self._arrastando = False
        self._offset_arraste = (0, 0)
        self._area_fechar = pygame.Rect(self.largura - 18, 2, 16, 16)
        self._area_config = pygame.Rect(self.largura - 38, 2, 16, 16)
        self.abrir_config_pedido = False  # setado pelo clique na engrenagem

        self._posicionar_no_canto()
        self.fixar_no_topo()

    # ── Win32 ────────────────────────────────────────────────────────────
    def fixar_no_topo(self) -> None:
        """Mantém a janela sobre todas as outras (reaplicável a qualquer momento)."""
        ok = _user32.SetWindowPos(
            self._hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE,
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())

    def _posicionar_no_canto(self) -> None:
        """Canto inferior direito, acima da barra de tarefas."""
        # área de trabalho (desconta a barra de tarefas)
        area = wintypes.RECT()
        _user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0)
        x = area.right - self.largura - MARGEM_CANTO
        y = area.bottom - self.altura - MARGEM_CANTO
        _user32.SetWindowPos(
            self._hwnd, HWND_TOPMOST, x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE
        )

    def _posicao_cursor(self) -> tuple[int, int]:
        p = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def _posicao_janela(self) -> tuple[int, int]:
        r = wintypes.RECT()
        _user32.GetWindowRect(self._hwnd, ctypes.byref(r))
        return r.left, r.top

    def esta_no_topo(self) -> bool:
        """Confere o estilo WS_EX_TOPMOST (usado nos testes de validação)."""
        GWL_EXSTYLE, WS_EX_TOPMOST = -20, 0x0008
        estilo = _user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)
        return bool(estilo & WS_EX_TOPMOST)

    # ── eventos ──────────────────────────────────────────────────────────
    def processar_eventos(self) -> bool:
        """Trata mouse/teclado. Retorna False quando o usuário fechar."""
        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                return False
            if evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE:
                return False
            if evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
                if self._area_fechar.collidepoint(evento.pos):
                    return False
                if self._area_config.collidepoint(evento.pos):
                    self.abrir_config_pedido = True
                    continue
                cx, cy = self._posicao_cursor()
                jx, jy = self._posicao_janela()
                self._arrastando = True
                self._offset_arraste = (cx - jx, cy - jy)
            elif evento.type == pygame.MOUSEBUTTONUP and evento.button == 1:
                self._arrastando = False
            elif evento.type == pygame.MOUSEMOTION and self._arrastando:
                cx, cy = self._posicao_cursor()
                ox, oy = self._offset_arraste
                _user32.SetWindowPos(
                    self._hwnd, HWND_TOPMOST, cx - ox, cy - oy, 0, 0,
                    SWP_NOSIZE | SWP_NOACTIVATE,
                )
        return True

    # ── renderização ─────────────────────────────────────────────────────
    def render(self, fb: FrameBuffer) -> None:
        _pintar(self.surface, fb)

        pygame.transform.scale(
            self.surface, (self.largura, self.altura), self.tela
        )
        pygame.draw.rect(
            self.tela, COR_BORDA, self.tela.get_rect(), width=2, border_radius=6
        )

        # botões (fechar + engrenagem) só quando o mouse está sobre a janela
        if pygame.mouse.get_focused():
            centro = self._area_fechar.center
            pygame.draw.circle(self.tela, COR_FECHAR, centro, 7)
            for dx in (-3, 3):
                pygame.draw.line(
                    self.tela, (255, 235, 235),
                    (centro[0] - 3, centro[1] + dx),
                    (centro[0] + 3, centro[1] - dx), 2,
                )
            # engrenagem: círculo com "dentes" (Tela 3 do esboço)
            cx, cy = self._area_config.center
            pygame.draw.circle(self.tela, COR_BORDA, (cx, cy), 7)
            for dx, dy in _DENTES_ENGRENAGEM:
                pygame.draw.circle(self.tela, COR_BORDA, (cx + dx, cy + dy), 2)
            pygame.draw.circle(self.tela, COR_CORPO, (cx, cy), 3)

        pygame.display.flip()
        self.clock.tick(self.fps)

    def fechar(self) -> None:
        pygame.quit()
