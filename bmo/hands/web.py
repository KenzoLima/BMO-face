"""Ferramenta: buscar informações na internet.

Usa o DuckDuckGo via biblioteca ``ddgs`` — gratuito e sem chave de API.
Os resultados voltam enxutos (título + resumo curto + url) para não
inundar o contexto do LLM.
"""

from __future__ import annotations

from .registry import ferramenta

MAX_RESULTADOS_TETO = 8
LIMITE_RESUMO = 300  # caracteres por resumo


def _executar_busca(consulta: str, max_resultados: int) -> list[dict]:
    from ddgs import DDGS  # lazy: só carrega quando a busca é usada

    with DDGS() as cliente:
        return list(cliente.text(consulta, region="br-pt", max_results=max_resultados))


@ferramenta(
    nome="buscar_na_internet",
    descricao=(
        "Pesquisa na internet e retorna títulos, resumos e links. Use para "
        "fatos atuais que você não sabe: clima, notícias, preços, resultados "
        "de jogos, eventos recentes. NÃO use para agir no computador do usuário."
    ),
    parametros={
        "type": "object",
        "properties": {
            "consulta": {
                "type": "string",
                "description": "O que pesquisar, como se digitasse no buscador.",
            },
            "max_resultados": {
                "type": "integer",
                "description": "Quantos resultados retornar (padrão 5, teto 8).",
            },
        },
        "required": ["consulta"],
    },
)
def buscar_na_internet(consulta: str, max_resultados: int = 5) -> dict:
    """Busca no DuckDuckGo e devolve resultados resumidos."""
    consulta = consulta.strip()
    if not consulta:
        return {"sucesso": False, "erro": "Consulta de busca vazia."}

    max_resultados = max(1, min(max_resultados, MAX_RESULTADOS_TETO))

    try:
        brutos = _executar_busca(consulta, max_resultados)
    except Exception as e:
        return {"sucesso": False, "erro": f"A busca na internet falhou: {e}"}

    resultados = [
        {
            "titulo": r.get("title", ""),
            "resumo": (r.get("body") or "")[:LIMITE_RESUMO],
            "url": r.get("href", ""),
        }
        for r in brutos
    ]

    if not resultados:
        return {"sucesso": True, "total": 0, "resultados": [],
                "aviso": "Nenhum resultado encontrado para essa consulta."}

    return {"sucesso": True, "total": len(resultados), "resultados": resultados}
