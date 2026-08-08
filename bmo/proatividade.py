"""Proatividade — a "vida própria" do BMO.

Sem esperar a wake word, o BMO toma pequenas iniciativas quando está ocioso:
um **briefing de manhã**, uma **sugestão de pausa** depois de horas de uso e
uma **recordação espontânea do caderno**. É o que o diferencia de um assistente
100% reativo — ele parece morar ali, e não só responder quando chamado.

Princípios de bom-mocismo (para nunca ser inconveniente):
- Desativável por completo (``BMO_PROATIVIDADE``), com botão na tela de config.
- Só fala quando o rosto está em **standby** (nunca corta uma conversa).
- Intervalo mínimo global entre falas espontâneas (``cooldown``).
- Cada comportamento tem seu próprio ritmo (o briefing é 1x/dia, etc.).

Arquitetura (separação para testabilidade):
- ``MotorProatividade``: lógica **pura** — dado o relógio, decide se há algo a
  dizer e o quê. Não fala, não usa threads, não toca em áudio. Fácil de testar.
- ``LacoProatividade`` (thread, em ``app.py``): de tempos em tempos consulta o
  motor e, quando o BMO está ocioso, entrega a fala ao assistente.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Optional

_DIAS_SEMANA = (
    "segunda-feira", "terça-feira", "quarta-feira",
    "quinta-feira", "sexta-feira", "sábado", "domingo",
)


def _env_bool(chave: str, padrao: bool) -> bool:
    valor = os.getenv(chave)
    if valor is None:
        return padrao
    return valor.strip() not in ("", "0", "false", "False", "nao", "não")


def _env_float(chave: str, padrao: float) -> float:
    try:
        return float(os.getenv(chave, "").strip())
    except (TypeError, ValueError):
        return padrao


def _env_int(chave: str, padrao: int) -> int:
    try:
        return int(os.getenv(chave, "").strip())
    except (TypeError, ValueError):
        return padrao


@dataclass
class Fala:
    """Uma iniciativa do BMO, pronta para ser falada.

    ``chave`` identifica o comportamento (briefing/pausa/caderno) e serve para
    o motor registrar quando ele foi usado. ``texto`` já vem com o prefixo de
    emoção (ex.: ``[feliz] Bom dia!``) que o rosto entende.

    O texto pode ser **preguiçoso**: quando montá-lo custa caro (o briefing
    consulta os lembretes, o que abre um PowerShell de ~3s), passe ``fabrica``
    em vez do texto pronto. Ele só é gerado — uma única vez — no primeiro
    acesso a ``.texto``, ou seja, quando a fala já passou por todas as guardas
    e vai mesmo sair. Sem isso, um briefing avaliado e descartado (porque o
    BMO saiu do standby) pagaria o custo à toa a cada checagem.
    """

    chave: str
    _texto: str | None = None
    ref: str | None = None  # dado auxiliar (ex.: título da nota recordada)
    fabrica: Callable[[], str] | None = field(default=None, repr=False)

    @property
    def texto(self) -> str:
        if self._texto is None and self.fabrica is not None:
            self._texto = self.fabrica()
            self.fabrica = None  # gerado uma vez só
        return self._texto or ""


# Provedores opcionais injetados pelo app (mantêm o motor puro e testável):
# - lembretes de hoje: lista de dicts {"mensagem": str, ...}
# - nota espontânea: dict {"nota": str, "trecho": str} ou None
ProvedorLembretes = Callable[[], list]
ProvedorNota = Callable[[], Optional[dict]]


class MotorProatividade:
    """Decide, a cada consulta, se o BMO deve tomar alguma iniciativa.

    Uso::

        motor = MotorProatividade()
        fala = motor.avaliar(datetime.now())
        if fala:              # há algo a dizer
            falar(fala.texto)
            motor.registrar(fala, datetime.now())  # só DEPOIS de falar

    ``avaliar`` é puro (não muda estado): pode ser chamado à vontade. O estado
    interno só avança em ``registrar``, para não "gastar" um briefing que
    acabou não sendo falado (ex.: o BMO saiu do standby no meio do caminho).
    """

    def __init__(
        self,
        *,
        ativo: bool | None = None,
        hora_briefing: int | None = None,
        pausa_horas: float | None = None,
        cooldown_min: float | None = None,
        intervalo_caderno_horas: float | None = None,
        inicio: datetime | None = None,
        provedor_lembretes: ProvedorLembretes | None = None,
        provedor_nota: ProvedorNota | None = None,
    ):
        self.ativo = _env_bool("BMO_PROATIVIDADE", True) if ativo is None else ativo
        self.hora_briefing = (
            _env_int("BMO_PROATIVIDADE_BRIEFING_HORA", 8)
            if hora_briefing is None else hora_briefing
        )
        self.pausa_horas = (
            _env_float("BMO_PROATIVIDADE_PAUSA_HORAS", 3.0)
            if pausa_horas is None else pausa_horas
        )
        cd = (
            _env_float("BMO_PROATIVIDADE_COOLDOWN_MIN", 45.0)
            if cooldown_min is None else cooldown_min
        )
        self.cooldown = timedelta(minutes=cd)
        self.intervalo_caderno = timedelta(
            hours=_env_float("BMO_PROATIVIDADE_CADERNO_HORAS", 6.0)
            if intervalo_caderno_horas is None else intervalo_caderno_horas
        )

        self.inicio = inicio or datetime.now()
        self.provedor_lembretes = provedor_lembretes
        self.provedor_nota = provedor_nota

        # estado que avança em registrar()
        self.ultima_fala: datetime | None = None
        self.ultimo_briefing: date | None = None
        self.ultima_pausa: datetime | None = None
        self.ultimo_caderno: datetime | None = None
        self.ultima_nota: str | None = None  # evita repetir a mesma nota

    # ── decisão (pura) ───────────────────────────────────────────────────
    def avaliar(self, agora: datetime) -> Fala | None:
        """Retorna a próxima iniciativa, ou None se não há nada a dizer agora.

        Não altera o estado interno (veja ``registrar``) e é **barato**: a
        decisão olha só o relógio. O texto do briefing, que custa uma consulta
        aos lembretes, é montado sob demanda no acesso a ``Fala.texto``."""
        if not self.ativo:
            return None
        if self.ultima_fala is not None and agora - self.ultima_fala < self.cooldown:
            return None  # respeita o intervalo mínimo entre falas espontâneas

        # ordem = prioridade
        return (
            self._briefing(agora)
            or self._pausa(agora)
            or self._caderno(agora)
        )

    def registrar(self, fala: Fala, agora: datetime) -> None:
        """Marca que ``fala`` foi realmente dita — chame só depois de falar."""
        self.ultima_fala = agora
        if fala.chave == "briefing":
            self.ultimo_briefing = agora.date()
        elif fala.chave == "pausa":
            self.ultima_pausa = agora
        elif fala.chave == "caderno":
            self.ultimo_caderno = agora
            self.ultima_nota = fala.ref

    # ── comportamentos ───────────────────────────────────────────────────
    def _briefing(self, agora: datetime) -> Fala | None:
        """Uma vez por dia, na primeira ociosidade após a hora configurada."""
        if agora.hour < self.hora_briefing:
            return None
        if self.ultimo_briefing == agora.date():
            return None
        # texto preguiçoso: montá-lo consulta os lembretes (PowerShell, ~3s)
        return Fala("briefing", fabrica=lambda: self._texto_briefing(agora))

    def _pausa(self, agora: datetime) -> Fala | None:
        """A cada N horas de uso contínuo, sugere uma pausa."""
        base = self.ultima_pausa or self.inicio
        if agora - base < timedelta(hours=self.pausa_horas):
            return None
        return Fala(
            "pausa",
            "[pensativo] Ei, você já está aqui faz um tempão sem parar... "
            "que tal levantar, beber uma água e descansar os olhos um "
            "pouquinho? O BMO fica de olho aqui!",
        )

    def _caderno(self, agora: datetime) -> Fala | None:
        """De vez em quando, recorda algo que o usuário anotou no caderno."""
        if self.provedor_nota is None:
            return None
        if self.ultimo_caderno is not None and agora - self.ultimo_caderno < self.intervalo_caderno:
            return None
        try:
            nota = self.provedor_nota()
        except Exception:
            return None
        if not nota:
            return None
        titulo = str(nota.get("nota") or "").strip()
        trecho = str(nota.get("trecho") or "").strip()
        if not trecho or titulo == self.ultima_nota:
            return None
        return Fala(
            "caderno",
            f"[feliz] Ei, lembrei de uma coisa que você me contou: {trecho}",
            ref=titulo,
        )

    # ── composição de texto ──────────────────────────────────────────────
    def _texto_briefing(self, agora: datetime) -> str:
        nome = os.getenv("BMO_USUARIO_NOME", "").strip()
        saudacao = self._saudacao(agora.hour)
        alvo = f"{saudacao}, {nome}!" if nome else f"{saudacao}!"
        dia = _DIAS_SEMANA[agora.weekday()]
        partes = [f"[feliz] {alvo}", f"Hoje é {dia}, {agora:%d/%m}."]

        linha = self._linha_lembretes()
        if linha:
            partes.append(linha)
        partes.append("Se precisar de mim, é só chamar Bimo!")
        return " ".join(partes)

    @staticmethod
    def _saudacao(hora: int) -> str:
        if hora < 12:
            return "Bom dia"
        if hora < 18:
            return "Boa tarde"
        return "Boa noite"

    def _linha_lembretes(self) -> str:
        if self.provedor_lembretes is None:
            return ""
        try:
            lembretes = self.provedor_lembretes() or []
        except Exception:
            return ""
        n = len(lembretes)
        if n == 0:
            return "Você não tem lembretes marcados pra hoje."
        if n == 1:
            msg = str(lembretes[0].get("mensagem") or "").strip()
            return f"Você tem um lembrete hoje: {msg}." if msg else "Você tem um lembrete hoje."
        return f"Você tem {n} lembretes marcados pra hoje."


class LacoProatividade(threading.Thread):
    """Thread que dá "vida" ao BMO: de tempos em tempos pergunta ao assistente
    se ele quer tomar alguma iniciativa. Toda a decisão fica no assistente
    (que sabe se o rosto está ocioso); aqui só existe o relógio de fundo.

    O ``assistente`` precisa expor ``encerrar`` (threading.Event) e
    ``tentar_proativo()``. O intervalo curto é barato: a checagem é pura e só
    vira fala quando o motor libera e o BMO está em standby.
    """

    def __init__(self, assistente, intervalo_s: float | None = None):
        super().__init__(daemon=True, name="bmo-proatividade")
        self.assistente = assistente
        self.intervalo_s = intervalo_s or _env_float("BMO_PROATIVIDADE_CHECAR_S", 30.0)

    def run(self) -> None:
        encerrar = self.assistente.encerrar
        # espera inicial: não fala no primeiro segundo em que o BMO liga
        if encerrar.wait(self.intervalo_s):
            return
        while not encerrar.is_set():
            try:
                self.assistente.tentar_proativo()
            except Exception:
                pass  # a vida própria nunca pode derrubar o assistente
            if encerrar.wait(self.intervalo_s):
                return
