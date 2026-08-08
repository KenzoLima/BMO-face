"""O Cérebro do BMO — orquestra provedor principal, fallback e memória.

Fluxo de uma conversa:

    texto do usuário → Cerebro.responder()
        → provedor principal (loop de Tool Use interno)
        → se o principal falhar (ex.: quota do free tier), tenta a reserva
        → resposta final entra no histórico neutro (compartilhado entre provedores)

Configuração via .env:
    BMO_PROVIDER=gemini|groq|local   (padrão: gemini)
    GOOGLE_API_KEY / GROQ_API_KEY
    BMO_MODEL_GEMINI / BMO_MODEL_GROQ / BMO_MODEL_LOCAL  (opcionais)
"""

from __future__ import annotations

import os

from .providers import ProvedorGemini, ProvedorGroq, ProvedorLocal

MAX_MENSAGENS_HISTORICO = 20  # ~10 trocas; suficiente p/ conversa falada


def _criar_provedor(nome: str):
    nome = nome.lower().strip()
    if nome == "gemini":
        return ProvedorGemini()
    if nome == "groq":
        return ProvedorGroq()
    if nome == "local":
        return ProvedorLocal()
    raise ValueError(
        f"BMO_PROVIDER inválido: '{nome}' (use 'gemini', 'groq' ou 'local')"
    )


def _nome_da_reserva(nome_primario: str) -> str | None:
    """Qual provedor serve de reserva, olhando só as chaves disponíveis.

    No modo híbrido (primário = 'local'), a reserva é sempre a nuvem: assim,
    quando o modelo local falha ou estoura o timeout, o BMO ainda responde."""
    if nome_primario != "gemini" and os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if nome_primario != "groq" and os.getenv("GROQ_API_KEY"):
        return "groq"
    return None


def _criar_reserva(nome_primario: str):
    """Cria o provedor reserva automaticamente, se houver chave para ele."""
    nome = _nome_da_reserva(nome_primario)
    if nome is None:
        return None
    try:
        return _criar_provedor(nome)
    except Exception:
        return None


class Cerebro:
    """Mantém o histórico da conversa e decide qual provedor responde."""

    def __init__(self, provedor=None, reserva=None):
        nome_primario = os.getenv("BMO_PROVIDER", "gemini")
        self.provedor = provedor or _criar_provedor(nome_primario)
        self._reserva = reserva
        self._reserva_pronta = reserva is not None
        self.historico: list[dict] = []

    @property
    def reserva(self):
        """Provedor reserva, construído só quando realmente for preciso.

        Montá-lo importa um segundo SDK (segundos de boot) para algo que só
        entra em cena se o primário falhar — o que, no caso normal, nunca
        acontece. Adiar isso tira o custo do caminho crítico da inicialização.
        """
        if not self._reserva_pronta:
            self._reserva = _criar_reserva(self.provedor.nome)
            self._reserva_pronta = True
        return self._reserva

    @reserva.setter
    def reserva(self, valor) -> None:
        self._reserva = valor
        self._reserva_pronta = True

    @property
    def nome_reserva(self) -> str | None:
        """Nome da reserva para exibição — sem construí-la, se ainda não existe."""
        if self._reserva_pronta:
            return self._reserva.nome if self._reserva else None
        return _nome_da_reserva(self.provedor.nome)

    def _com_memorias(self, texto: str) -> str:
        """Anexa trechos do caderno relacionados à fala do usuário.

        Busca LOCAL (zero requisições); os trechos pegam carona na requisição
        que já ia acontecer."""
        try:
            from bmo.hands.notes import memorias_relevantes

            memorias = memorias_relevantes(texto)
            if memorias:
                return (
                    f"{texto}\n\n[Do caderno permanente do usuário — trechos "
                    f"possivelmente relevantes:\n{memorias}\n]"
                )
        except Exception:
            pass  # caderno nunca pode derrubar uma resposta
        return texto

    def _guardar(self, pergunta: str, resposta: str) -> None:
        self.historico.append({"role": "user", "content": pergunta})
        self.historico.append({"role": "assistant", "content": resposta})
        if len(self.historico) > MAX_MENSAGENS_HISTORICO:
            self.historico = self.historico[-MAX_MENSAGENS_HISTORICO:]

    def responder(self, texto: str) -> str:
        texto = texto.strip()
        if not texto:
            return "[pensativo] Você não disse nada... pode repetir?"

        texto_para_llm = self._com_memorias(texto)

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

        self._guardar(texto, resposta)
        return resposta

    def _fluxo(self, provedor, texto: str, ao_ferramenta=None):
        """Pedaços de resposta do provedor; inteiro de uma vez se ele não
        souber transmitir (Groq/Ollama e os dublês dos testes)."""
        em_partes = getattr(provedor, "responder_em_partes", None)
        if em_partes is None:
            return iter([provedor.responder(texto, self.historico)])
        try:
            return em_partes(texto, self.historico, ao_ferramenta=ao_ferramenta)
        except TypeError:  # provedor antigo, sem o aviso de ferramenta
            return em_partes(texto, self.historico)

    def responder_em_partes(self, texto: str, ao_ferramenta=None):
        """Gera a resposta em pedaços, para a boca começar antes do fim.

        Mesmo contrato do ``responder`` (memória, reserva, histórico), só que
        entregando o texto conforme ele chega. A diferença sutil está na
        reserva: uma vez que o BMO JÁ FALOU parte da resposta, recomeçar do
        zero com outro provedor sairia incoerente em voz alta — nesse caso ele
        encerra a frase admitindo o problema, em vez de se repetir.
        """
        texto = texto.strip()
        if not texto:
            yield "[pensativo] Você não disse nada... pode repetir?"
            return

        texto_para_llm = self._com_memorias(texto)
        ditos: list[str] = []

        try:
            for pedaco in self._fluxo(self.provedor, texto_para_llm, ao_ferramenta):
                ditos.append(pedaco)
                yield pedaco
        except Exception as erro_primario:
            print(f"[BMO] Provedor '{self.provedor.nome}' falhou: {erro_primario}")
            if ditos:
                yield " Ih, perdi o resto do meu raciocínio... pode repetir?"
                self._guardar(texto, "".join(ditos))
                return
            if self.reserva is None:
                yield (
                    "[triste] Meu cérebro principal falhou e não tenho reserva "
                    "configurada... Tente de novo daqui a pouco?"
                )
                return
            print(f"[BMO] Tentando reserva '{self.reserva.nome}'...")
            try:
                for pedaco in self._fluxo(self.reserva, texto_para_llm, ao_ferramenta):
                    ditos.append(pedaco)
                    yield pedaco
            except Exception as erro_reserva:
                print(f"[BMO] Reserva também falhou: {erro_reserva}")
                if not ditos:
                    yield "[triste] Meus dois cérebros falharam... Tente mais tarde?"
                return

        self._guardar(texto, "".join(ditos))

    def esquecer(self) -> None:
        """Limpa a memória da conversa atual."""
        self.historico.clear()
