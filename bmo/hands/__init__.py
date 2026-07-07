"""As "mãos" do BMO — ferramentas que agem no sistema operacional.

Importar este pacote já registra todas as ferramentas no registry
(os decoradores ``@ferramenta`` rodam no import). O cérebro só precisa de:

    from bmo.hands import schemas_gemini, executar_ferramenta
"""

from . import apps, files, shell  # noqa: F401 - imports registram as ferramentas
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
