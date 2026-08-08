"""Contador de requisições ao LLM — a fonte de dados do velocímetro.

Conta **chamadas de API**, não falas do usuário: o loop de Tool Use dispara
uma requisição por rodada, então um único "abre o navegador e me diz o clima"
pode custar três. É exatamente esse gasto escondido que o medidor mostra.

O estado do dia vive em ``%APPDATA%\\BMO\\consumo.json`` e zera sozinho na
virada da data. Leituras saem da memória (o rosto consulta a cada frame, não
pode tocar o disco); só ``registrar()`` grava.

Nada aqui pode derrubar uma resposta do BMO: toda falha vira silêncio e o
contador segue valendo em memória.

Configuração (.env):
    BMO_LIMITE_REQUISICOES_DIA=250   # teto do SEU plano — veja abaixo
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date
from pathlib import Path

from .paths import dir_dados_usuario

ARQUIVO = "consumo.json"

# Palpite conservador só para o medidor ter uma escala no primeiro uso.
# O limite real depende do provedor e do plano (e muda com o tempo): confira
# no painel do seu provedor e ajuste BMO_LIMITE_REQUISICOES_DIA no .env.
LIMITE_PADRAO = 250

_trava = threading.Lock()
_estado: dict | None = None  # {"data": "YYYY-MM-DD", "provedores": {nome: n}}


def _caminho() -> Path:
    return dir_dados_usuario() / ARQUIVO


def limite_diario() -> int:
    """Teto de requisições por dia, do .env ou o padrão."""
    try:
        valor = int(os.getenv("BMO_LIMITE_REQUISICOES_DIA", "").strip())
    except (TypeError, ValueError):
        return LIMITE_PADRAO
    return valor if valor > 0 else LIMITE_PADRAO


def _carregar() -> dict:
    """Estado de hoje — do disco na primeira vez, da memória depois.

    Chamada com ``_trava`` já segurada.
    """
    global _estado
    if _estado is None:
        try:
            _estado = json.loads(_caminho().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _estado = {}
    if not isinstance(_estado, dict) or _estado.get("data") != date.today().isoformat():
        _estado = {"data": date.today().isoformat(), "provedores": {}}  # virou o dia
    if not isinstance(_estado.get("provedores"), dict):
        _estado["provedores"] = {}
    return _estado


def _gravar(estado: dict) -> None:
    try:
        caminho = _caminho()
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(estado), encoding="utf-8")
    except OSError:
        pass  # sem disco, o contador ainda vale para esta sessão


def registrar(provedor: str, quantas: int = 1) -> None:
    """Marca requisições feitas ao provedor.

    Chamado ANTES da requisição sair: uma chamada que falha no meio pode ter
    sido contabilizada pelo provedor do mesmo jeito, e é melhor o medidor
    errar para menos saldo do que prometer folga que não existe.
    """
    try:
        with _trava:
            estado = _carregar()
            atual = estado["provedores"].get(provedor, 0)
            estado["provedores"][provedor] = atual + quantas
            _gravar(estado)
    except Exception:
        pass  # contar nunca pode atrapalhar o BMO responder


def gastas_hoje(provedor: str | None = None) -> int:
    """Requisições já gastas hoje — de um provedor, ou de todos."""
    try:
        with _trava:
            provedores = _carregar()["provedores"]
            if provedor is None:
                return sum(provedores.values())
            return provedores.get(provedor, 0)
    except Exception:
        return 0


def restantes_hoje(provedor: str | None = None) -> int:
    return max(0, limite_diario() - gastas_hoje(provedor))


def fracao_restante(provedor: str | None = None) -> float:
    """Quanto sobrou do orçamento, de 0.0 a 1.0 — o que o medidor desenha."""
    limite = limite_diario()
    if limite <= 0:
        return 1.0
    return max(0.0, min(1.0, restantes_hoje(provedor) / limite))


def esquecer_cache() -> None:
    """Descarta o estado em memória (testes e troca de dia forçada)."""
    global _estado
    with _trava:
        _estado = None
