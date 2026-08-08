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

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

# Teto de tempo de UMA ferramenta. Existe porque uma ferramenta pendurada
# (busca na internet sem resposta, PowerShell travado) segurava a thread de
# voz para sempre: o BMO ficava calado e parecia morto, sem erro nenhum.
# Melhor devolver "demorei demais" ao modelo do que nunca mais responder.
TIMEOUT_PADRAO = 30.0


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict[str, Any] = field(default_factory=dict)  # JSON Schema
    executar: Callable[..., dict] = None  # type: ignore[assignment]
    timeout: float = TIMEOUT_PADRAO


_REGISTRO: dict[str, Ferramenta] = {}


def ferramenta(
    nome: str,
    descricao: str,
    parametros: dict[str, Any],
    timeout: float = TIMEOUT_PADRAO,
):
    """Decorador que registra uma função Python como ferramenta do agente.

    ``timeout`` é o teto de tempo desta ferramenta; ferramentas que legitimamente
    demoram (um comando de shell longo) declaram o seu.
    """

    def decorador(func: Callable[..., dict]) -> Callable[..., dict]:
        if nome in _REGISTRO:
            raise ValueError(f"Ferramenta duplicada: '{nome}'")
        _REGISTRO[nome] = Ferramenta(nome, descricao, parametros, func, timeout)
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

    saida: dict[str, Any] = {}

    def rodar() -> None:
        try:
            saida["resultado"] = alvo.executar(**(argumentos or {}))
        except TypeError as e:
            saida["resultado"] = {
                "sucesso": False, "erro": f"Argumentos inválidos para '{nome}': {e}"
            }
        except Exception as e:  # nunca derrubar o loop do agente por causa de uma tool
            saida["resultado"] = {
                "sucesso": False, "erro": f"Falha ao executar '{nome}': {e}"
            }

    # A ferramenta roda numa thread só para o relógio ser inescapável: uma
    # chamada de rede pendurada não tem como ser interrompida de fora, então
    # abandonamos a thread (daemon, morre com o processo) e devolvemos o erro.
    # Perder uma thread é bem melhor que perder a voz do BMO pelo resto do dia.
    trabalho = threading.Thread(target=rodar, name=f"bmo-tool-{nome}", daemon=True)
    trabalho.start()
    trabalho.join(alvo.timeout)
    if trabalho.is_alive():
        return {
            "sucesso": False,
            "erro": (
                f"A ferramenta '{nome}' passou de {alvo.timeout:.0f}s e foi "
                "abandonada. Responda ao usuário sem ela, ou tente outro caminho."
            ),
        }
    return saida.get("resultado", {"sucesso": False, "erro": f"'{nome}' não retornou nada."})
