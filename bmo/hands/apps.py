"""Ferramenta: abrir aplicativos no Windows.

Estratégia de resolução, na ordem:

1. Tabela de apelidos (``APP_ALIASES``) — traduz o que o usuário fala
   ("navegador", "código") para candidatos executáveis reais.
2. ``shutil.which`` — encontra executáveis no PATH.
3. ``os.startfile`` — usa o ShellExecute do Windows, que resolve apps
   registrados (App Paths), URIs (``ms-settings:``) e associações de arquivo.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from .registry import ferramenta

# Apelido falado (normalizado) → lista de candidatos, tentados em ordem.
# Candidatos podem ser executáveis do PATH, nomes registrados no Windows
# ou URIs (ms-settings:, https://...).
APP_ALIASES: dict[str, list[str]] = {
    "vs code": ["code"],
    "vscode": ["code"],
    "código": ["code"],
    "navegador": ["msedge", "chrome", "firefox"],
    "browser": ["msedge", "chrome", "firefox"],
    "chrome": ["chrome"],
    "edge": ["msedge"],
    "firefox": ["firefox"],
    "terminal": ["wt", "powershell", "cmd"],
    "prompt de comando": ["cmd"],
    "powershell": ["powershell"],
    "explorador": ["explorer"],
    "explorador de arquivos": ["explorer"],
    "arquivos": ["explorer"],
    "bloco de notas": ["notepad"],
    "notepad": ["notepad"],
    "calculadora": ["calc"],
    "configurações": ["ms-settings:"],
    "configuracoes": ["ms-settings:"],
    "spotify": ["spotify"],
    "discord": ["discord"],
    "steam": ["steam"],
    "whatsapp": ["whatsapp"],
}


def _normalizar(nome: str) -> str:
    return " ".join(nome.lower().strip().split())


def _candidatos(nome_app: str) -> list[str]:
    nome = _normalizar(nome_app)
    return APP_ALIASES.get(nome, [nome])


@ferramenta(
    nome="abrir_aplicativo",
    descricao=(
        "Abre um aplicativo no computador do usuário (Windows). "
        "Aceita nomes comuns em português, como 'vs code', 'navegador', "
        "'terminal', 'calculadora', 'spotify'."
    ),
    parametros={
        "type": "object",
        "properties": {
            "nome_app": {
                "type": "string",
                "description": "Nome do aplicativo a abrir, ex: 'vs code', 'navegador'.",
            }
        },
        "required": ["nome_app"],
    },
)
def abrir_aplicativo(nome_app: str) -> dict:
    """Tenta abrir o aplicativo e informa qual candidato funcionou."""
    tentados: list[str] = []

    for candidato in _candidatos(nome_app):
        tentados.append(candidato)

        # 1) Executável no PATH → processo independente, sem bloquear o agente
        caminho = shutil.which(candidato)
        if caminho:
            subprocess.Popen(
                [caminho],
                creationflags=subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
            return {
                "sucesso": True,
                "mensagem": f"Aplicativo '{nome_app}' aberto via '{caminho}'.",
            }

        # 2) ShellExecute: apps registrados no Windows, URIs e associações
        try:
            os.startfile(candidato)  # noqa: S606 - abertura intencional de app
            return {
                "sucesso": True,
                "mensagem": f"Aplicativo '{nome_app}' aberto via Windows ('{candidato}').",
            }
        except OSError:
            continue

    return {
        "sucesso": False,
        "erro": (
            f"Não encontrei o aplicativo '{nome_app}' "
            f"(tentei: {tentados}). Ele está instalado? "
            "Se souber o caminho do executável, posso tentar por ele."
        ),
    }
