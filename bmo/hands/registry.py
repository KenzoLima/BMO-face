"""Registro central de ferramentas (Tool Use / Function Calling).

Este módulo é o contrato entre as "mãos" do BMO e qualquer LLM:

1. Cada ferramenta se registra com o decorador ``@ferramenta``, informando
   nome, descrição e um JSON Schema dos parâmetros.
2. O cérebro (Fase 3) pede os schemas no formato do provedor escolhido
   (``schemas_gemini()`` ou ``schemas_openai()`` — este último também serve
   para Ollama e Claude via proxy compatível).
3. Quando o LLM pede uma chamada de função, o cérebro delega para
   ``executar_ferramenta(nome, argumentos)``, que devolve sempre um ``dict``
   JSON-serializável — nunca levanta exceção — pronto para voltar ao modelo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict[str, Any] = field(default_factory=dict)  # JSON Schema
    executar: Callable[..., dict] = None  # type: ignore[assignment]


_REGISTRO: dict[str, Ferramenta] = {}


def ferramenta(nome: str, descricao: str, parametros: dict[str, Any]):
    """Decorador que registra uma função Python como ferramenta do agente."""

    def decorador(func: Callable[..., dict]) -> Callable[..., dict]:
        if nome in _REGISTRO:
            raise ValueError(f"Ferramenta duplicada: '{nome}'")
        _REGISTRO[nome] = Ferramenta(nome, descricao, parametros, func)
        return func

    return decorador


def listar_ferramentas() -> list[Ferramenta]:
    return list(_REGISTRO.values())


def schemas_gemini() -> list[dict]:
    """Function declarations no formato aceito pelo Gemini (google-genai)."""
    return [
        {"name": f.nome, "description": f.descricao, "parameters": f.parametros}
        for f in _REGISTRO.values()
    ]


def schemas_openai() -> list[dict]:
    """Schemas no formato OpenAI/Ollama, caso o provedor mude no futuro."""
    return [
        {
            "type": "function",
            "function": {
                "name": f.nome,
                "description": f.descricao,
                "parameters": f.parametros,
            },
        }
        for f in _REGISTRO.values()
    ]


def executar_ferramenta(nome: str, argumentos: dict[str, Any] | None = None) -> dict:
    """Executa a ferramenta pedida pelo LLM e devolve o resultado como dict.

    Erros viram parte do resultado (``sucesso: False``) em vez de exceção,
    para que o modelo receba o feedback e possa se corrigir.
    """
    alvo = _REGISTRO.get(nome)
    if alvo is None:
        return {
            "sucesso": False,
            "erro": f"Ferramenta desconhecida: '{nome}'. "
            f"Disponíveis: {sorted(_REGISTRO)}",
        }
    try:
        return alvo.executar(**(argumentos or {}))
    except TypeError as e:
        return {"sucesso": False, "erro": f"Argumentos inválidos para '{nome}': {e}"}
    except Exception as e:  # nunca derrubar o loop do agente por causa de uma tool
        return {"sucesso": False, "erro": f"Falha ao executar '{nome}': {e}"}
