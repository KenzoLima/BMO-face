"""Provedores de LLM do BMO.

Cada provedor implementa a mesma interface informal:

    responder(texto: str, historico: list[dict]) -> str

- ``historico`` é neutro (independente de provedor): lista de dicts
  ``{"role": "user" | "assistant", "content": str}`` só com as falas finais.
- O loop de Tool Use acontece DENTRO de cada chamada: o provedor executa as
  ferramentas via ``bmo.hands`` quantas rodadas forem necessárias e devolve
  apenas o texto final. Chamadas de ferramenta não poluem o histórico.

Os SDKs são importados dentro dos construtores, para que a ausência de uma
dependência opcional não quebre o outro provedor.
"""

from __future__ import annotations

import os

from ..consumo import registrar
from .prompts import system_prompt_atual

MAX_RODADAS_DE_FERRAMENTAS = 5


def _avisar(ao_ferramenta, nomes: list[str], fase: str) -> None:
    """Notifica quem quiser mostrar progresso — nunca derruba a resposta."""
    if ao_ferramenta is None:
        return
    try:
        ao_ferramenta(nomes, fase)
    except Exception:
        pass


class ProvedorGemini:
    """Gemini via SDK nativo google-genai, com function calling nativo."""

    nome = "gemini"

    def __init__(self, modelo: str | None = None):
        from google import genai
        from google.genai import types
        from bmo.hands import schemas_gemini

        chave = os.getenv("GOOGLE_API_KEY")
        if not chave:
            raise ValueError("GOOGLE_API_KEY não encontrada no .env")

        self._types = types
        self.cliente = genai.Client(api_key=chave)
        self.modelo = modelo or os.getenv("BMO_MODEL_GEMINI", "gemini-2.5-flash")
        self._tools = [types.Tool(function_declarations=schemas_gemini())]

    def _config(self):
        """Config montada a cada chamada: o system prompt carrega o relógio."""
        return self._types.GenerateContentConfig(
            system_instruction=system_prompt_atual(),
            tools=self._tools,
            temperature=0.7,
        )

    def _converter_historico(self, historico: list[dict]) -> list:
        t = self._types
        papel = {"user": "user", "assistant": "model"}
        return [
            t.Content(role=papel[m["role"]], parts=[t.Part.from_text(text=m["content"])])
            for m in historico
        ]

    def responder(self, texto: str, historico: list[dict]) -> str:
        from bmo.hands import executar_ferramenta

        t = self._types
        contents = self._converter_historico(historico)
        contents.append(t.Content(role="user", parts=[t.Part.from_text(text=texto)]))

        config = self._config()
        for _ in range(MAX_RODADAS_DE_FERRAMENTAS):
            registrar(self.nome)  # cada rodada de ferramenta é uma requisição
            resposta = self.cliente.models.generate_content(
                model=self.modelo, contents=contents, config=config
            )

            chamadas = resposta.function_calls or []
            if not chamadas:
                return (resposta.text or "").strip()

            # devolve os resultados das ferramentas para o modelo continuar
            contents.append(resposta.candidates[0].content)
            partes = [
                t.Part.from_function_response(
                    name=chamada.name,
                    response={
                        "resultado": executar_ferramenta(
                            chamada.name, dict(chamada.args or {})
                        )
                    },
                )
                for chamada in chamadas
            ]
            contents.append(t.Content(role="tool", parts=partes))

        return "[pensativo] Tentei várias vezes mas me enrolei nas ferramentas..."

    def responder_em_partes(self, texto: str, historico: list[dict], ao_ferramenta=None):
        """Mesma conversa do ``responder``, entregando o texto conforme chega.

        É o que tira o TTS do caminho crítico: a boca sintetiza a primeira
        frase enquanto o modelo ainda escreve o resto, em vez de esperar a
        resposta inteira para só então começar a gerar áudio.

        As rodadas de ferramenta continuam no mesmo laço — se o modelo falar
        alguma coisa antes de chamar a ferramenta ("Deixa comigo!"), isso já
        sai pela boca e cobre justamente a espera da ferramenta.

        ``ao_ferramenta(nomes, fase)`` avisa quando uma rodada de ferramentas
        começa e termina (fase ``"inicio"``/``"fim"``). É o que permite o rosto
        mostrar a tela de pesquisa em vez de ficar parado enquanto uma busca
        na internet acontece.
        """
        from bmo.hands import executar_ferramenta

        t = self._types
        contents = self._converter_historico(historico)
        contents.append(t.Content(role="user", parts=[t.Part.from_text(text=texto)]))
        config = self._config()

        for _ in range(MAX_RODADAS_DE_FERRAMENTAS):
            registrar(self.nome)  # cada rodada de ferramenta é uma requisição
            chamadas: list = []
            partes_modelo: list = []

            for parcial in self.cliente.models.generate_content_stream(
                model=self.modelo, contents=contents, config=config
            ):
                candidato = (parcial.candidates or [None])[0]
                if candidato is None or not candidato.content:
                    continue
                for parte in candidato.content.parts or []:
                    # remonta o turno do modelo à mão: no streaming ele chega
                    # fatiado, e o laço de ferramentas precisa dele inteiro
                    partes_modelo.append(parte)
                    if getattr(parte, "function_call", None):
                        chamadas.append(parte.function_call)
                    elif getattr(parte, "text", None):
                        yield parte.text

            if not chamadas:
                return

            nomes = [chamada.name for chamada in chamadas]
            _avisar(ao_ferramenta, nomes, "inicio")
            try:
                respostas = [
                    t.Part.from_function_response(
                        name=chamada.name,
                        response={
                            "resultado": executar_ferramenta(
                                chamada.name, dict(chamada.args or {})
                            )
                        },
                    )
                    for chamada in chamadas
                ]
            finally:
                _avisar(ao_ferramenta, nomes, "fim")

            contents.append(t.Content(role="model", parts=partes_modelo))
            contents.append(t.Content(role="tool", parts=respostas))

        yield "[pensativo] Tentei várias vezes mas me enrolei nas ferramentas..."


class _ProvedorOpenAICompat:
    """Base para qualquer endpoint compatível com a API da OpenAI.

    Serve Groq (nuvem), Ollama (local) e afins — muda só ``base_url``, a chave
    e o modelo. O loop de Tool Use (schemas OpenAI + execução das ferramentas)
    é idêntico para todos. As subclasses só montam ``self.cliente``,
    ``self.modelo`` e, opcionalmente, ``self.timeout`` (segundos por chamada;
    útil no cérebro local, para escalar à nuvem se o modelo travar).
    """

    nome = "openai-compat"
    timeout: float | None = None

    def responder(self, texto: str, historico: list[dict]) -> str:
        import json

        from bmo.hands import executar_ferramenta, schemas_openai

        mensagens: list = [{"role": "system", "content": system_prompt_atual()}]
        mensagens += historico
        mensagens.append({"role": "user", "content": texto})

        ferramentas = schemas_openai()  # o registro não muda entre as rodadas

        for _ in range(MAX_RODADAS_DE_FERRAMENTAS):
            registrar(self.nome)  # cada rodada de ferramenta é uma requisição
            resposta = self.cliente.chat.completions.create(
                model=self.modelo,
                messages=mensagens,
                tools=ferramentas,
                temperature=0.7,
                timeout=self.timeout,
            )
            msg = resposta.choices[0].message

            if not msg.tool_calls:
                return (msg.content or "").strip()

            mensagens.append(msg)
            for chamada in msg.tool_calls:
                argumentos = json.loads(chamada.function.arguments or "{}")
                resultado = executar_ferramenta(chamada.function.name, argumentos)
                mensagens.append(
                    {
                        "role": "tool",
                        "tool_call_id": chamada.id,
                        "content": json.dumps(resultado, ensure_ascii=False),
                    }
                )

        return "[pensativo] Tentei várias vezes mas me enrolei nas ferramentas..."


class ProvedorGroq(_ProvedorOpenAICompat):
    """Groq via API compatível com OpenAI (Llama 3.3 70B por padrão)."""

    nome = "groq"

    def __init__(self, modelo: str | None = None):
        from openai import OpenAI

        chave = os.getenv("GROQ_API_KEY")
        if not chave:
            raise ValueError("GROQ_API_KEY não encontrada no .env")

        self.cliente = OpenAI(api_key=chave, base_url="https://api.groq.com/openai/v1")
        self.modelo = modelo or os.getenv("BMO_MODEL_GROQ", "llama-3.3-70b-versatile")


class ProvedorLocal(_ProvedorOpenAICompat):
    """Cérebro LOCAL via Ollama (ou qualquer servidor OpenAI-compatible).

    Zero requisições à nuvem: o modelo roda na própria máquina. Como um 4B
    pode travar ou demorar num notebook sem GPU, há um ``timeout`` — se ele
    estourar, o ``Cerebro`` cai automaticamente para a reserva na nuvem
    (é isso que dá o comportamento "híbrido": local no dia a dia, nuvem só
    quando o local não dá conta).

    Configuração (.env):
        BMO_MODEL_LOCAL=qwen3:4b        # modelo puxado com `ollama pull`
        BMO_LOCAL_BASE_URL=http://localhost:11434/v1
        BMO_LOCAL_API_KEY=ollama        # dummy; Ollama não exige chave
        BMO_LOCAL_TIMEOUT=45            # segundos por chamada antes de escalar
    """

    nome = "local"

    def __init__(self, modelo: str | None = None):
        from openai import OpenAI

        base = os.getenv("BMO_LOCAL_BASE_URL", "http://localhost:11434/v1")
        chave = os.getenv("BMO_LOCAL_API_KEY", "ollama")  # dummy; Ollama ignora
        self.cliente = OpenAI(api_key=chave, base_url=base)
        self.modelo = modelo or os.getenv("BMO_MODEL_LOCAL", "qwen3:4b")
        try:
            self.timeout = float(os.getenv("BMO_LOCAL_TIMEOUT", "45"))
        except ValueError:
            self.timeout = 45.0
