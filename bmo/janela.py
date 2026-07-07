"""Janela flutuante do BMO — pequena, sempre no topo, arrastável.

Renderiza o FrameBuffer do rosto em uma janela pygame sem borda (256x128),
fixada sobre as demais janelas via SetWindowPos (ctypes, sem dependências).

Controles:
- arrastar com o botão esquerdo move a janela;
- "×" no canto (aparece ao passar o mouse) ou ESC fecham o BMO.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from .face import OLED_H, OLED_W, FrameBuffer

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
        self.tela = pygame.display.set_mode(
            (self.largura, self.altura), pygame.NOFRAME
        )
        self.surface = pygame.Surface((OLED_W, OLED_H))
        self.clock = pygame.time.Clock()

        self._hwnd = pygame.display.get_wm_info()["window"]
        self._arrastando = False
        self._offset_arraste = (0, 0)
        self._area_fechar = pygame.Rect(self.largura - 18, 2, 16, 16)

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
        self.surface.fill(COR_CORPO)
        for y in range(OLED_H):
            for x in range(OLED_W):
                if fb.get(x, y):
                    self.surface.set_at((x, y), COR_PIXEL)

        pygame.transform.scale(
            self.surface, (self.largura, self.altura), self.tela
        )
        pygame.draw.rect(
            self.tela, COR_BORDA, self.tela.get_rect(), width=2, border_radius=6
        )

        # botão de fechar só quando o mouse está sobre a janela
        if pygame.mouse.get_focused():
            centro = self._area_fechar.center
            pygame.draw.circle(self.tela, COR_FECHAR, centro, 7)
            for dx in (-3, 3):
                pygame.draw.line(
                    self.tela, (255, 235, 235),
                    (centro[0] - 3, centro[1] + dx),
                    (centro[0] + 3, centro[1] - dx), 2,
                )

        pygame.display.flip()
        self.clock.tick(self.fps)

    def fechar(self) -> None:
        pygame.quit()
