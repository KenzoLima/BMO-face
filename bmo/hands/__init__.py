"""As "mãos" do BMO — ferramentas que agem no sistema operacional.

Importar este pacote já registra todas as ferramentas no registry
(os decoradores ``@ferramenta`` rodam no import). O cérebro só precisa de:

    from bmo.hands import schemas_gemini, executar_ferramenta
"""

from . import apps, files, notes, reminders, shell, web  # noqa: F401 - registram as ferramentas
from .registry import (
    executar_ferramenta,
    listar_ferramentas,
    schemas_gemini,
    schemas_openai,
)

__all__ = [
    "executar_ferramenta",
    "listar_ferramentas",
    "schemas_gemini",
    "schemas_openai",
]
