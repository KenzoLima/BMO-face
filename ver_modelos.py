import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

print("Buscando modelos disponíveis para a sua chave...")
for m in genai.list_models():
    # Filtra apenas os modelos que geram texto
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")