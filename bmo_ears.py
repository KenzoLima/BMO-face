import speech_recognition as sr
from bmo_brain import falar_com_bmo

def bmo_ouvir():
    microfone = sr.Recognizer()
    with sr.Microphone() as source:
        print("\nBMO: Ajustando ouvidos...")
        microfone.adjust_for_ambient_noise(source, duration=1)
        print("BMO: Pode falar!")
        
        try:
            audio = microfone.listen(source, timeout=10, phrase_time_limit=15)
            texto = microfone.recognize_google(audio, language='pt-BR')
            
            print(f"---> Você: {texto}")
            print("Computando...")

            resposta = falar_com_bmo(texto)
            print(f"BMO: {resposta}")
            
            
        except sr.UnknownValueError:
            print("BMO: Hm? Não entendi nada... pode repetir?")
        except sr.WaitTimeoutError:
            print("BMO: Zzz... não ouvi ninguém falar.")
        except Exception as e:
            print(f"BMO: Erro no sistema: {e}")

if __name__ == "__main__":
    print("=== BMO ligado! Fale comigo ===")
    while True:
        bmo_ouvir()