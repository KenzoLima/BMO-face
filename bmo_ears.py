import speech_recognition as sr

def bmo_ouvir():
    # Cria o objeto que vai atuar como o "ouvido" do BMO
    microfone = sr.Recognizer()
    
    # Inicia a comunicação com o microfone padrão do seu computador
    with sr.Microphone() as source:
        print("BMO: Ajustando os ouvidos (calibrando ruído do ambiente)...")
        microfone.adjust_for_ambient_noise(source, duration=1)
        
        print("\nBMO: Pode falar! Estou ouvindo...")
        try:
            audio = microfone.listen(source, timeout=5, phrase_time_limit=10)
            
            print("BMO: Processando o que você disse...")
            
            # Manda o áudio para o Google e pede a resposta em Português do Brasil
            texto = microfone.recognize_google(audio, language='pt-BR')
            
            print(f"\n---> Você disse: '{texto}'")
            
        # Tratamento de erros comuns na captação de voz
        except sr.UnknownValueError:
            print("\nBMO: Escutei um barulho, mas não entendi as palavras.")
        except sr.WaitTimeoutError:
            print("\nBMO: Você demorou muito para falar, acabei dormindo.")
        except sr.RequestError:
            print("\nBMO: Estou sem internet para processar as palavras.")

if __name__ == "__main__":
    # Um loop infinito para você testar várias vezes sem precisar rodar o script de novo
    while True:
        bmo_ouvir()
        print("-" * 40)