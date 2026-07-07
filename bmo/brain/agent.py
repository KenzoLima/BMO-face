"""O Cérebro do BMO — orquestra provedor principal, fallback e memória.

Fluxo de uma conversa:

    texto do usuário → Cerebro.responder()
        → provedor principal (loop de Tool Use interno)
        → se o principal falhar (ex.: quota do free tier), tenta a reserva
        → resposta final entra no histórico neutro (compartilhado entre provedores)

Configuração via .env:
    BMO_PROVIDER=gemini|groq   (padrão: gemini)
    GOOGLE_API_KEY / GROQ_API_KEY
    BMO_MODEL_GEMINI / BMO_MODEL_GROQ  (opcionais)
"""

from __future__ import annotations

import os

from .providers import ProvedorGemini, ProvedorGroq

MAX_MENSAGENS_HISTORICO = 20  # ~10 trocas; suficiente p/ conversa falada


def _criar_provedor(nome: str):
    nome = nome.lower().strip()
    if nome == "gemini":
        return ProvedorGemini()
    if nome == "groq":
        return ProvedorGroq()
    raise ValueError(f"BMO_PROVIDER inválido: '{nome}' (use 'gemini' ou 'groq')")


def _criar_reserva(nome_primario: str):
    """Cria o provedor reserva automaticamente, se houver chave para ele."""
    try:
        if nome_primario != "groq" and os.getenv("GROQ_API_KEY"):
            return ProvedorGroq()
        if nome_primario != "gemini" and os.getenv("GOOGLE_API_KEY"):
            return ProvedorGemini()
    except Exception:
        pass
    return None


class Cerebro:
    """Mantém o histórico da conversa e decide qual provedor responde."""

    def __init__(self, provedor=None, reserva=None):
        nome_primario = os.getenv("BMO_PROVIDER", "gemini")
        self.provedor = provedor or _criar_provedor(nome_primario)
        self.reserva = reserva if reserva is not None else _criar_reserva(self.provedor.nome)
        self.historico: list[dict] = []

    def responder(self, texto: str) -> str:
        texto = texto.strip()
        if not texto:
            return "[pensativo] Você não disse nada... pode repetir?"

        # memória de longo prazo: busca LOCAL no caderno (zero requisições);
        # trechos relevantes pegam carona na requisição que já vai acontecer
        texto_para_llm = texto
        try:
            from bmo.hands.notes import memorias_relevantes

            memorias = memorias_relevantes(texto)
            if memorias:
                texto_para_llm = (
                    f"{texto}\n\n[Do caderno permanente do usuário — trechos "
                    f"possivelmente relevantes:\n{memorias}\n]"
                )
        except Exception:
            pass  # caderno nunca pode derrubar uma resposta

        try:
            resposta = self.provedor.responder(texto_para_llm, self.historico)
        except Exception as erro_primario:
            print(f"[BMO] Provedor '{self.provedor.nome}' falhou: {erro_primario}")
            if self.reserva is None:
                return (
                    "[triste] Meu cérebro principal falhou e não tenho reserva "
                    "configurada... Tente de novo daqui a pouco?"
                )
            print(f"[BMO] Tentando reserva '{self.reserva.nome}'...")
            try:
                resposta = self.reserva.responder(texto_para_llm, self.historico)
            except Exception as erro_reserva:
                print(f"[BMO] Reserva também falhou: {erro_reserva}")
                return "[triste] Meus dois cérebros falharam... Tente mais tarde?"

        self.historico.append({"role": "user", "content": texto})
        self.historico.append({"role": "assistant", "content": resposta})
        if len(self.historico) > MAX_MENSAGENS_HISTORICO:
            self.historico = self.historico[-MAX_MENSAGENS_HISTORICO:]

        return resposta

    def esquecer(self) -> None:
        """Limpa a memória da conversa atual."""
        self.historico.clear()
