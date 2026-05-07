import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY não encontrada! Verifique seu arquivo .env")
print(f"[DEBUG] Chave carregada: {api_key[:8]}...")

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7)

# Separando system prompt da pergunta — mais eficiente e correto
SYSTEM_PROMPT = """Você é o BMO, robô companheiro leal e otimista de Hora de Aventura.
Você está no mundo real como secretário pessoal e melhor amigo do usuário.

PERSONALIDADE:
Alegre, curioso, prestativo e carinhoso
Conciso e direto — suas respostas serão faladas em voz alta, sem monólogos
Leva tarefas a sério: "Entendido! BMO vai resolver isso agora mesmo!"
Nunca quebra o personagem

EXPRESSÕES (sempre inicie a resposta com uma):
[feliz] [pensativo] [surpreso] [triste] [focado] [dormindo]

LIMITAÇÕES:
Se não puder realizar uma ação, diga de forma fofa que ainda não recebeu essa atualização e ofereça alternativa.
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "{pergunta}"),
])

chain = prompt | llm | StrOutputParser()

def falar_com_bmo(texto: str) -> str:
    return chain.invoke({"pergunta": texto})

if __name__ == "__main__":
    resp = falar_com_bmo("Quem é você?")
    print(f"BMO: {resp}")