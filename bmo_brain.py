import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

# Setup do modelo
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7)

# Prompt do BMO
template = "Você é o BMO de Hora de Aventura. Responda: {pergunta}"
prompt = PromptTemplate.from_template(template)

# O novo jeito de fazer "Chains" em 2026 (Usando o operador Pipe '|')
chain = prompt | llm | StrOutputParser()

def perguntar_ao_bmo(texto):
    return chain.invoke({"pergunta": texto})

if __name__ == "__main__":
    resp = perguntar_ao_bmo("Quem é você?")
    print(f"BMO: {resp}")


