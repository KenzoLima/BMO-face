import time
import speech_recognition as sr
from bmo_brain import falar_com_bmo

TAMANHO_MINIMO_FALA = 3
WAKE_WORDS = ["bimo", "ei bimo","oi bimo", "hey bimo"]

def escutar_wake_word(microfone: sr.Recognizer, source) -> bool:
    """
    Escuta leve e contínua esperando a wake word.
    Só transcreve se detectar energia de fala - não faz requisição sem motivo.
    """
    try:
        audio = microfone.listen(source, timeout=2, phrase_time_limit=3)
        texto = microfone.recognize_google(audio, langage='pt-BR'). lower().strip()

        if any (wake in texto for wake in WAKE_WORDS):
            print(f"BMO: Oi! 👾 (gatilho: '{texto}')")
            return True

    except (sr.UnknownValueError, sr.WaitTimeoutError):
        pass #ignora ruído e silêncio
    except Exception as e:
        print(f"BMO: Erro na escuta passiva: {e}")
    return False

def escutar_comando(microfone: sr.Recognizer, source) -> str | None:
    """
    Escuta ativa: só chamada após wake word confirmada. Aqui sim vale a pena uma janela maior de atenção.
    """
    print("BMO: Pode falar!")

    try:
        audio = microfone.listen(source, timeout=10, phrase_time_limit=15)
        texto = microfone.recognize_google(audio, language='pt-BR').strip()
        
        if len(texto) < TAMANHO_MINIMO_FALA:
            print("BMO: Hm, não entendi direito...")
            return None
        
        return texto
    
    except sr.UnknownValueError:
        print("BMO: Não entendi nada... pode repetir?")
    except sr.WaitTimeoutError:
        print("BMO: Não ouvi ninguém falar.")
    except Exception as e:
        print(f"BMO: Erro ao escutar comando: {e}")
    
    return None


def bmo_ouvir():
    microfone = sr.Recognizer()
    microfone.energy_threshol = 400
    microfone.dynamic_energy_threshol = True

    with sr.Microphone() as source:
        print("\nBMO:...")
        microfone.adjust_for_ambient_noise(source, duration=1.5)
        print("BMO: Pode falar!")
        
        try:
            audio = microfone.listen(source, timeout=10, phrase_time_limit=10)
            texto = microfone.recognize_google(audio, language='pt-BR')
            texto = texto.strip()

            if len(texto) < TAMANHO_MINIMO_FALA:
                print("ignorei o ruído...")
                return
            
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
        time.sleep(0.3)