import speech_recognition as sr

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