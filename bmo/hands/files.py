"""Ferramenta: buscar arquivos no sistema.

Varre diretórios com ``os.walk`` respeitando limites de profundidade e de
quantidade de resultados, para nunca travar o PC nem inundar o contexto
do LLM com milhares de caminhos.
"""

from __future__ import annotations

import os
from pathlib import Path

from .registry import ferramenta

# Diretórios que nunca valem a pena varrer (pesados ou irrelevantes p/ usuário)
DIRETORIOS_IGNORADOS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "AppData",
    "$RECYCLE.BIN",
    "System Volume Information",
    ".cache",
}

MAX_RESULTADOS_TETO = 50  # teto rígido, mesmo que o LLM peça mais


@ferramenta(
    nome="buscar_arquivo",
    descricao=(
        "Busca arquivos no computador pelo nome (parcial, sem diferenciar "
        "maiúsculas) ou por extensão (comece o termo com ponto, ex: '.pdf'). "
        "Retorna caminhos absolutos. Se o usuário não disser onde procurar, "
        "a busca parte da pasta pessoal dele."
    ),
    parametros={
        "type": "object",
        "properties": {
            "termo": {
                "type": "string",
                "description": "Parte do nome do arquivo, ou extensão como '.pdf'.",
            },
            "diretorio_base": {
                "type": "string",
                "description": (
                    "Pasta onde começar a busca (caminho absoluto). "
                    "Opcional: padrão é a pasta pessoal do usuário."
                ),
            },
            "max_resultados": {
                "type": "integer",
                "description": "Máximo de arquivos a retornar (padrão 20, teto 50).",
            },
            "profundidade_maxima": {
                "type": "integer",
                "description": "Níveis de subpastas a descer (padrão 5).",
            },
        },
        "required": ["termo"],
    },
)
def buscar_arquivo(
    termo: str,
    diretorio_base: str | None = None,
    max_resultados: int = 20,
    profundidade_maxima: int = 5,
) -> dict:
    """Retorna caminhos absolutos dos arquivos que casam com o termo."""
    base = Path(diretorio_base).expanduser() if diretorio_base else Path.home()
    if not base.is_dir():
        return {"sucesso": False, "erro": f"Diretório não existe: '{base}'"}

    termo = termo.strip().lower()
    if not termo:
        return {"sucesso": False, "erro": "Termo de busca vazio."}

    max_resultados = max(1, min(max_resultados, MAX_RESULTADOS_TETO))
    por_extensao = termo.startswith(".")

    encontrados: list[str] = []
    truncado = False

    for raiz, pastas, arquivos in os.walk(base):
        profundidade = len(Path(raiz).relative_to(base).parts)
        if profundidade >= profundidade_maxima:
            pastas.clear()  # não desce mais neste galho
        else:
            # editar 'pastas' in-place é o mecanismo do os.walk para podar a árvore
            pastas[:] = [
                p for p in pastas
                if p not in DIRETORIOS_IGNORADOS and not p.startswith(".")
            ]

        for arquivo in arquivos:
            nome = arquivo.lower()
            casou = nome.endswith(termo) if por_extensao else termo in nome
            if casou:
                encontrados.append(str(Path(raiz) / arquivo))
                if len(encontrados) >= max_resultados:
                    truncado = True
                    break
        if truncado:
            break

    return {
        "sucesso": True,
        "total": len(encontrados),
        "truncado": truncado,
        "base_da_busca": str(base),
        "arquivos": encontrados,
    }
