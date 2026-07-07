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
        texto = microfone.recognize_google(audio, language='pt-BR'). lower().strip()

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


def bmo_loop():
    microfone = sr.Recognizer()
    microfone.energy_threshold = 200        # era energy_threshol (typo)
    microfone.dynamic_energy_threshold = True # era dynamic_energy_threshol (typo)

    with sr.Microphone() as source:
        print("\nBMO: Calibrando...")
        microfone.adjust_for_ambient_noise(source, duration=1.5)
        print(f"[DEBUG] energy_threshold calibrado: {microfone.energy_threshold:.0f}")
        print("BMO: Pronto! Me chame pelo nome (ex: 'ei bimo')\n")  
        while True:
            #escuta passiva
            print("BMO: aguardando wake word...")   # feedback a cada iteração
            if not escutar_wake_word(microfone, source):
                continue

            #escuta ativa
            comando = escutar_comando(microfone, source)
            if not comando:
                continue

            print(f"---> Você: {comando}")
            print("Computando...")

            resposta = falar_com_bmo(comando)
            print(f"BMO: {resposta}\n")

            time.sleep(0.3)

if __name__ == "__main__":
    bmo_loop()