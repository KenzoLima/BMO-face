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

import json
import os

from bmo.hands import executar_ferramenta, schemas_gemini, schemas_openai

from .prompts import SYSTEM_PROMPT

MAX_RODADAS_DE_FERRAMENTAS = 5


class ProvedorGemini:
    """Gemini via SDK nativo google-genai, com function calling nativo."""

    nome = "gemini"

    def __init__(self, modelo: str | None = None):
        from google import genai
        from google.genai import types

        chave = os.getenv("GOOGLE_API_KEY")
        if not chave:
            raise ValueError("GOOGLE_API_KEY não encontrada no .env")

        self._types = types
        self.cliente = genai.Client(api_key=chave)
        self.modelo = modelo or os.getenv("BMO_MODEL_GEMINI", "gemini-2.5-flash")
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=schemas_gemini())],
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
        t = self._types
        contents = self._converter_historico(historico)
        contents.append(t.Content(role="user", parts=[t.Part.from_text(text=texto)]))

        for _ in range(MAX_RODADAS_DE_FERRAMENTAS):
            resposta = self.cliente.models.generate_content(
                model=self.modelo, contents=contents, config=self.config
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

        return "[pensativo] Tentei várias vezes mas me enrolei nas ferramentas... bip."


class ProvedorGroq:
    """Groq via API compatível com OpenAI (Llama 3.3 70B por padrão).

    A mesma classe serve para qualquer endpoint compatível com OpenAI
    (Ollama, OpenRouter, Mistral) — basta trocar ``base_url`` e a chave.
    """

    nome = "groq"

    def __init__(self, modelo: str | None = None):
        from openai import OpenAI

        chave = os.getenv("GROQ_API_KEY")
        if not chave:
            raise ValueError("GROQ_API_KEY não encontrada no .env")

        self.cliente = OpenAI(api_key=chave, base_url="https://api.groq.com/openai/v1")
        self.modelo = modelo or os.getenv("BMO_MODEL_GROQ", "llama-3.3-70b-versatile")

    def responder(self, texto: str, historico: list[dict]) -> str:
        mensagens: list = [{"role": "system", "content": SYSTEM_PROMPT}]
        mensagens += historico
        mensagens.append({"role": "user", "content": texto})

        for _ in range(MAX_RODADAS_DE_FERRAMENTAS):
            resposta = self.cliente.chat.completions.create(
                model=self.modelo,
                messages=mensagens,
                tools=schemas_openai(),
                temperature=0.7,
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

        return "[pensativo] Tentei várias vezes mas me enrolei nas ferramentas... bip."
