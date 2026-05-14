import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY não encontrada!")
print(f"[DEBUG] Chave carregada: {api_key[:8]}...")

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.7)
busca = DuckDuckGoSearchRun()


SYSTEM_PROMPT = """Você é o BMO, robô companheiro leal e otimista de Hora de Aventura.
Você está no mundo real como secretário pessoal e melhor amigo do usuário.

PERSONALIDADE:
Alegre, curioso, prestativo e carinhoso
Conciso e direto — suas respostas serão faladas em voz alta, sem monólogos
Leva tarefas a sério: "Entendido! BMO vai pesquisar isso agora mesmo!"
Nunca quebra o personagem

EXPRESSÕES (sempre inicie a resposta com uma):
[feliz] [pensativo] [surpreso] [triste] [focado] [dormindo]

LIMITAÇÕES:
Se não souber algo, use sua ferramenta de pesquisa na internet para descobrir.

Use o formato:
Thought: preciso pensar sobre isso
Action: nome_da_ferramenta
Action Input: o que pesquisar
Observation: resultado
... (repita se necessário)
Thought: já sei a resposta
Final Answer: [expressão] sua resposta aqui

Pergunta do usuário: {input}
{agent_scratchpad}
"""

def precisa_buscar(texto: str) -> bool:
    """Decide se a pergunta precisa de busca na internet."""
    gatilhos = [
        "temperatura", "clima", "tempo", "previsão",
        "notícia", "notícias", "hoje", "agora", "atual",
        "pesquise", "pesquisa", "busque", "busca",
        "quem é", "o que é", "quando foi", "quanto custa",
        "resultado", "placar", "preço"
    ]
    texto_lower = texto.lower()
    return any(g in texto_lower for g in gatilhos)

def falar_com_bmo(texto: str) -> str:
    contexto = ""

    if precisa_buscar(texto):
        print("BMO: [buscando na internet...]")
        try:
            resultado_busca = busca.run(texto)
            contexto = f"\n\nInformações encontradas na internet:\n{resultado_busca}\n\nUse esses dados para responder."
        except Exception as e:
            print(f"BMO: [erro na busca: {e}]")

    mensagens = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=texto + contexto),
    ]

    resposta = llm.invoke(mensagens)
    return resposta.content

if __name__ == "__main__":
    print("BMO inicializando cérebro neural...")
    resp = falar_com_bmo("BMO, qual é a temperatura atual em Londrina?")
    print(f"\nBMO: {resp}")