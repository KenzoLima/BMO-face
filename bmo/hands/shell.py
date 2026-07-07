"""Ferramenta: executar comandos no terminal (PowerShell).

Camada de segurança: como quem decide o comando é um LLM, existe uma
lista de padrões destrutivos que são recusados antes de chegar ao shell.
A saída é truncada para não estourar o contexto do modelo.
"""

from __future__ import annotations

import subprocess

from .registry import ferramenta

# Padrões que o BMO se recusa a executar, mesmo que o LLM peça.
# Comparação por substring, sem diferenciar maiúsculas.
PADROES_BLOQUEADOS = [
    "format ",
    "shutdown",
    "restart-computer",
    "stop-computer",
    "rm -rf",
    "remove-item -recurse -force c:",
    "del /f",
    "del /s",
    "del /q",
    "rmdir /s",
    "rd /s",
    "diskpart",
    "reg delete",
    "cipher /w",
    "vssadmin delete",
    "bcdedit",
    "mkfs",
]

LIMITE_SAIDA = 3000  # caracteres por stream (stdout/stderr)
TIMEOUT_TETO = 120  # segundos


def _truncar(texto: str) -> str:
    texto = texto.strip()
    if len(texto) <= LIMITE_SAIDA:
        return texto
    return texto[:LIMITE_SAIDA] + f"\n[... saída truncada em {LIMITE_SAIDA} caracteres]"


@ferramenta(
    nome="executar_comando",
    descricao=(
        "Executa um comando no PowerShell do computador e retorna stdout, "
        "stderr e o código de saída. Use para consultas e automações "
        "(listar processos, ver espaço em disco, rodar scripts). Comandos "
        "destrutivos são bloqueados por segurança."
    ),
    parametros={
        "type": "object",
        "properties": {
            "comando": {
                "type": "string",
                "description": "Comando PowerShell a executar.",
            },
            "timeout_segundos": {
                "type": "integer",
                "description": "Tempo máximo de execução (padrão 30, teto 120).",
            },
        },
        "required": ["comando"],
    },
)
def executar_comando(comando: str, timeout_segundos: int = 30) -> dict:
    """Roda o comando no PowerShell e devolve o resultado estruturado."""
    comando = comando.strip()
    if not comando:
        return {"sucesso": False, "erro": "Comando vazio."}

    comando_lower = comando.lower()
    for padrao in PADROES_BLOQUEADOS:
        if padrao in comando_lower:
            return {
                "sucesso": False,
                "erro": (
                    f"Comando bloqueado por segurança (padrão '{padrao.strip()}'). "
                    "BMO não executa ações destrutivas no sistema."
                ),
            }

    timeout_segundos = max(1, min(timeout_segundos, TIMEOUT_TETO))

    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_segundos,
        )
    except subprocess.TimeoutExpired:
        return {
            "sucesso": False,
            "erro": f"Comando excedeu o tempo limite de {timeout_segundos}s.",
        }
    except FileNotFoundError:
        return {"sucesso": False, "erro": "PowerShell não encontrado no sistema."}

    return {
        "sucesso": resultado.returncode == 0,
        "codigo_saida": resultado.returncode,
        "stdout": _truncar(resultado.stdout),
        "stderr": _truncar(resultado.stderr),
    }
