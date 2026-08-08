"""Caminhos de arquivos do BMO."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def dir_projeto() -> Path:
    return Path(__file__).resolve().parent.parent


def dir_dados_usuario() -> Path:
    base = os.getenv("APPDATA")
    if base:
        return Path(base) / "BMO"
    return Path.home() / "AppData" / "Roaming" / "BMO"


def caminho_env() -> Path:
    """Arquivo .env ativo.

    App instalado usa %APPDATA%\\BMO\\.env, separado por usuario. Rodando do
    codigo-fonte, mantemos o .env na raiz do projeto.
    """
    if getattr(sys, "frozen", False):
        return dir_dados_usuario() / ".env"
    return dir_projeto() / ".env"


def caminho_env_legado_instalacao() -> Path | None:
    """Antigo .env ao lado do executavel, usado apenas como fallback."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / ".env"
    return None
