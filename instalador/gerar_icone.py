"""Gera instalador/bmo.ico a partir do rosto do BMO (sem dependências extras).

O formato ICO aceita PNGs embutidos (desde o Vista), então empacotamos
renders do rosto em 16/32/48/256 px com struct puro.
"""

import io
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from bmo.face import FrameBuffer, RostoBMO

COR_CORPO = (62, 201, 167)
COR_PIXEL = (26, 74, 56)
COR_BORDA = (26, 122, 90)
TAMANHOS = (16, 32, 48, 256)


def _render_rosto() -> pygame.Surface:
    """Rosto clássico (olhos redondos + sorriso) num corpo quadrado."""
    fb = FrameBuffer()
    RostoBMO(fb).draw_idle(16)  # frame sem piscada e sem cursor

    lado = 128
    surf = pygame.Surface((lado, lado))
    surf.fill(COR_BORDA)
    pygame.draw.rect(surf, COR_CORPO, pygame.Rect(4, 4, lado - 8, lado - 8),
                     border_radius=18)

    # rosto (128x64) grande e centrado no corpo quadrado
    rosto = pygame.Surface((128, 64), pygame.SRCALPHA)
    for y in range(64):
        for x in range(128):
            if fb.get(x, y):
                rosto.set_at((x, y), COR_PIXEL)
    surf.blit(pygame.transform.smoothscale(rosto, (124, 62)), (2, 33))
    return surf


def _png_bytes(surf: pygame.Surface, tamanho: int) -> bytes:
    escala = pygame.transform.smoothscale(surf, (tamanho, tamanho))
    buffer = io.BytesIO()
    pygame.image.save(escala, buffer, "icone.png")
    return buffer.getvalue()


def main() -> None:
    pygame.init()
    base = _render_rosto()
    imagens = [(t, _png_bytes(base, t)) for t in TAMANHOS]

    destino = Path(__file__).parent / "bmo.ico"
    with open(destino, "wb") as ico:
        ico.write(struct.pack("<HHH", 0, 1, len(imagens)))  # cabeçalho ICONDIR
        offset = 6 + 16 * len(imagens)
        for tamanho, png in imagens:
            dim = 0 if tamanho == 256 else tamanho  # 0 = 256 no formato ICO
            ico.write(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                                  len(png), offset))
            offset += len(png)
        for _, png in imagens:
            ico.write(png)

    print(f"ícone gerado: {destino} ({destino.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
