"""Ferramentas: lembretes locais via Agendador de Tarefas do Windows.

Cada lembrete vira uma tarefa agendada na pasta ``\\BMO`` do Task Scheduler,
que dispara uma notificação toast nativa do Windows na hora marcada.
Vantagens: persiste com o BMO fechado, sobrevive a reinicializações e
dispara atrasado se o PC estava desligado na hora (StartWhenAvailable).

A mensagem do lembrete fica na Description da tarefa; o nome da tarefa
carrega a data/hora, então listar é auto-explicativo.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from .registry import ferramenta

PASTA_TAREFAS = "\\BMO"  # pasta das tarefas do BMO no Task Scheduler
DIR_DADOS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BMO"
SCRIPT_TOAST = DIR_DADOS / "bmo_toast.ps1"
LIMITE_MENSAGEM = 120

# Toast nativo via WinRT; o AppId do PowerShell garante que a notificação
# aparece sem precisar registrar um aplicativo próprio.
_CONTEUDO_TOAST = """param([string]$Mensagem)
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textos = $template.GetElementsByTagName('text')
$null = $textos.Item(0).AppendChild($template.CreateTextNode('Lembrete do BMO'))
$null = $textos.Item(1).AppendChild($template.CreateTextNode($Mensagem))
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show($toast)
"""


def _ps(comando: str) -> subprocess.CompletedProcess:
    # PS 5.1 emite no codepage OEM por padrão; forçamos UTF-8 p/ não perder acentos
    comando = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " + comando
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def _sanitizar_mensagem(mensagem: str) -> str:
    """Remove caracteres que quebrariam o comando PowerShell gerado."""
    mensagem = re.sub(r'["`$\\]', "'", mensagem).strip()
    return mensagem[:LIMITE_MENSAGEM]


def _interpretar_data_hora(data_hora: str) -> datetime | None:
    for formato in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(data_hora.strip(), formato)
        except ValueError:
            continue
    return None


def _garantir_script_toast() -> None:
    DIR_DADOS.mkdir(parents=True, exist_ok=True)
    if not SCRIPT_TOAST.exists() or SCRIPT_TOAST.read_text(encoding="utf-8") != _CONTEUDO_TOAST:
        SCRIPT_TOAST.write_text(_CONTEUDO_TOAST, encoding="utf-8")


@ferramenta(
    nome="criar_lembrete",
    descricao=(
        "Agenda um lembrete no Windows: na data/hora marcada, uma notificação "
        "aparece na tela do usuário, mesmo que o BMO esteja fechado. "
        "Calcule a data/hora absoluta a partir do relógio atual informado no "
        "seu contexto (ex.: 'amanhã às 9' vira a data de amanhã, 09:00)."
    ),
    parametros={
        "type": "object",
        "properties": {
            "mensagem": {
                "type": "string",
                "description": "Texto do lembrete, curto e direto (até 120 caracteres).",
            },
            "data_hora": {
                "type": "string",
                "description": "Quando disparar, no formato 'YYYY-MM-DD HH:MM' (24h).",
            },
        },
        "required": ["mensagem", "data_hora"],
    },
)
def criar_lembrete(mensagem: str, data_hora: str) -> dict:
    momento = _interpretar_data_hora(data_hora)
    if momento is None:
        return {"sucesso": False, "erro": f"Data/hora inválida: '{data_hora}'. Use 'YYYY-MM-DD HH:MM'."}
    if momento <= datetime.now():
        return {"sucesso": False, "erro": f"'{data_hora}' já passou. Lembretes precisam ser no futuro."}

    mensagem = _sanitizar_mensagem(mensagem)
    if not mensagem:
        return {"sucesso": False, "erro": "Mensagem do lembrete vazia."}

    _garantir_script_toast()

    nome = f"Lembrete {momento:%d-%m-%Y %H-%M} ({datetime.now():%H%M%S})"
    argumento = (
        f'-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass '
        f'-File "{SCRIPT_TOAST}" -Mensagem "{mensagem}"'
    )
    comando = (
        f"$acao = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '{argumento}'; "
        f"$gatilho = New-ScheduledTaskTrigger -Once -At ([datetime]'{momento:%Y-%m-%dT%H:%M:00}'); "
        f"$config = New-ScheduledTaskSettingsSet -StartWhenAvailable; "
        f"Register-ScheduledTask -TaskName '{nome}' -TaskPath '{PASTA_TAREFAS}' "
        f"-Action $acao -Trigger $gatilho -Settings $config "
        f"-Description '{mensagem.replace(chr(39), chr(39) * 2)}' -Force | Out-Null"
    )

    resultado = _ps(comando)
    if resultado.returncode != 0:
        return {"sucesso": False, "erro": f"Falha ao agendar: {resultado.stderr.strip()[:300]}"}

    return {
        "sucesso": True,
        "mensagem": f"Lembrete agendado para {momento:%d/%m/%Y às %H:%M}.",
        "nome_tarefa": nome,
    }


@ferramenta(
    nome="listar_lembretes",
    descricao="Lista os lembretes agendados no Windows (nome, mensagem e próximo disparo).",
    parametros={"type": "object", "properties": {}},
)
def listar_lembretes() -> dict:
    comando = (
        f"Get-ScheduledTask -TaskPath '{PASTA_TAREFAS}\\' -ErrorAction SilentlyContinue | "
        "ForEach-Object { $info = $_ | Get-ScheduledTaskInfo; [pscustomobject]@{ "
        "nome = $_.TaskName; mensagem = $_.Description; "
        "proximo_disparo = if ($info.NextRunTime) { $info.NextRunTime.ToString('yyyy-MM-dd HH:mm') } else { $null } "
        "} } | ConvertTo-Json -Compress"
    )
    resultado = _ps(comando)
    saida = resultado.stdout.strip()

    if not saida:
        return {"sucesso": True, "total": 0, "lembretes": []}

    try:
        dados = json.loads(saida)
    except json.JSONDecodeError:
        return {"sucesso": False, "erro": f"Não consegui ler a lista de tarefas: {saida[:200]}"}

    lembretes = dados if isinstance(dados, list) else [dados]
    return {"sucesso": True, "total": len(lembretes), "lembretes": lembretes}


@ferramenta(
    nome="cancelar_lembrete",
    descricao=(
        "Cancela um lembrete agendado. Use o nome_tarefa exato retornado por "
        "listar_lembretes ou criar_lembrete."
    ),
    parametros={
        "type": "object",
        "properties": {
            "nome_tarefa": {
                "type": "string",
                "description": "Nome exato da tarefa, ex.: 'Lembrete 08-07-2026 09-00 (153012)'.",
            }
        },
        "required": ["nome_tarefa"],
    },
)
def cancelar_lembrete(nome_tarefa: str) -> dict:
    nome = _sanitizar_mensagem(nome_tarefa)
    comando = (
        f"Unregister-ScheduledTask -TaskName '{nome}' -TaskPath '{PASTA_TAREFAS}\\' "
        "-Confirm:$false -ErrorAction Stop"
    )
    resultado = _ps(comando)
    if resultado.returncode != 0:
        return {
            "sucesso": False,
            "erro": f"Não achei o lembrete '{nome}'. Confira o nome com listar_lembretes.",
        }
    return {"sucesso": True, "mensagem": f"Lembrete '{nome}' cancelado."}
