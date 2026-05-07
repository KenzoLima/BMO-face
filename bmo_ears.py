import speech_recognition as sr

def processar_cerebro(texto):
    texto = texto.lower() # Transformar tudo em minúsculo para facilitar a busca
    
    # Dicionário de respostas e expressões
    if "quem é você" in texto or "seu nome" in texto:
        print("BMO: Eu sou o BMO! Sou muito mais que um videogame.")
        return "FELIZ"

    elif "como você está" in texto or "tudo bem" in texto:
        print("BMO: Estou excelente! Acabei de rodar um check-up no meu sistema.")
        return "FELIZ"

    elif "hora de aventura" in texto:
        print("BMO: Finn! Jake! Onde vocês estão?")
        return "SURPRESO"

    elif "piada" in texto:
        print("BMO: Por que o robô foi ao médico? Porque ele tinha um vírus!")
        return "FALANDO"

    elif "tchau" in texto or "desligar" in texto:
        print("BMO: Tchau tchau! Vou entrar em modo de hibernação.")
        return "SONOLENTO"

    else:
        print(f"BMO: Hum, você disse '{texto}', mas não sei o que significa ainda.")
        return "NEUTRO"

def bmo_ouvir():
    microfone = sr.Recognizer()
    with sr.Microphone() as source:
        print("\nBMO: Ajustando ouvidos...")
        microfone.adjust_for_ambient_noise(source, duration=1)
        print("BMO: Pode falar!")
        
        try:
            audio = microfone.listen(source, timeout=5, phrase_time_limit=8)
            texto = microfone.recognize_google(audio, language='pt-BR')
            
            print(f"---> Você: {texto}")
            
            # O cérebro decide o que fazer com o texto
            expressao_escolhida = processar_cerebro(texto)
            print(f"BMO: [Expressão sugerida: {expressao_escolhida}]")
            
        except sr.UnknownValueError:
            print("BMO: Não entendi...")
        except Exception as e:
            print(f"BMO: Erro no sistema: {e}")

if __name__ == "__main__":
    while True:
        bmo_ouvir()