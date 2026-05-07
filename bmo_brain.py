import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise valueError("GOOGLE_API_KEY não encontrada! Verifique seu arquivo .env")
print(f"[DEBUG] Chave carregada: {api_key[:8]}...")  # mostra só o início

# Setup do modelo
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7)

# Prompt do BMO
template = "Você é o BMO, o adorável robô-videogame de Hora de Aventura.\
Responda de forma curta, animada, como o BMO fala na série.\
Use expressões como 'BMO!', fale sobre circuitos, jogos e aventuras.\
Responda sempre em português brasileiro. Não utilize emojis, não precisa fazer onomatopeias e não seja tão fofo\
Caso o usuário pergunte algo que o BMO só tenha acesso pela internet, ele deve pesquisar sem exitar\
Pergunta: {pergunta}"

prompt = PromptTemplate.from_template(template)
# O novo jeito de fazer "Chains" em 2026 (Usando o operador Pipe '|')
chain = prompt | llm | StrOutputParser()

def falar_com_bmo(texto : str) -> str:
    return chain.invoke({"pergunta": texto})

if __name__ == "__main__":
    resp = falar_com_bmo("Quem é você?")
    print(f"BMO: {resp}")