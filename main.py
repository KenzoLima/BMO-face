"""BMO — assistente pessoal de voz.

Modos:
    python main.py            # janela flutuante com rosto + voz (padrão)
    python main.py --voz      # modo voz no terminal, sem janela
    python main.py --texto    # chat de texto no terminal (testes sem microfone)
    BMO_MUDO=1                # desliga a fala em qualquer modo

Se a janela ou o microfone falharem, o BMO cai para o modo mais simples
disponível em vez de quebrar.
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

MODELO_ENV = """\
# Configuracao do BMO - preencha a chave e abra o BMO de novo.
# Chave gratis do Gemini: https://aistudio.google.com/apikey
GOOGLE_API_KEY=

# Opcional: fallback gratis da Groq (https://console.groq.com)
GROQ_API_KEY=
"""


def _dir_instalacao() -> Path:
    """Pasta do programa: a do executável (instalado) ou a do projeto."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _preparar_env() -> None:
    """Garante um .env ao lado do programa e o carrega."""
    caminho = _dir_instalacao() / ".env"
    if not caminho.exists():
        try:
            caminho.write_text(MODELO_ENV, encoding="utf-8")
        except OSError:
            pass  # pasta somente leitura: segue com variáveis do sistema
    load_dotenv(caminho)
    load_dotenv()  # .env do diretório atual, se houver, complementa


_preparar_env()

from bmo.brain import Cerebro  # noqa: E402 - precisa do .env carregado antes
from bmo.mouth import Boca  # noqa: E402

COMANDOS_SAIR = {"sair", "tchau", "exit", "quit", "tchau bimo", "até mais"}


def falar_com_seguranca(boca: Boca | None, texto: str) -> Boca | None:
    """Fala o texto; se a voz falhar, avisa e desliga a voz desta sessão."""
    if boca is None:
        return None
    try:
        boca.falar(texto)
        return boca
    except Exception as e:
        print(f"[BMO] Voz indisponível ({e}). Seguindo só com texto.")
        return None


def criar_cerebro() -> Cerebro:
    print("BMO inicializando...")
    cerebro = Cerebro()
    reserva = cerebro.reserva.nome if cerebro.reserva else "nenhuma"
    print(f"[cérebro: {cerebro.provedor.nome} | reserva: {reserva}]")
    return cerebro


def modo_texto(cerebro: Cerebro) -> None:
    print("BMO: Oi! O que vamos fazer hoje? (digite 'sair' para encerrar)\n")

    while True:
        try:
            texto = input("Você: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBMO: Até mais!")
            break

        if not texto:
            continue
        if texto.lower() in COMANDOS_SAIR:
            print("BMO: Até mais!")
            break

        print("BMO: [computando...]")
        resposta = cerebro.responder(texto)
        print(f"BMO: {resposta}\n")


def _atender(cerebro: Cerebro, boca: Boca | None, comando: str) -> tuple[Boca | None, bool]:
    """Processa um comando falado. Retorna (boca, continuar_o_loop)."""
    print(f"---> Você: {comando}")
    if comando.lower() in COMANDOS_SAIR:
        print("BMO: Até mais!")
        falar_com_seguranca(boca, "Até mais!")
        return boca, False

    print("BMO: [computando...]")
    resposta = cerebro.responder(comando)
    print(f"BMO: {resposta}\n")
    return falar_com_seguranca(boca, resposta), True


def _loop_local(cerebro: Cerebro, ouvidos, boca: Boca | None, ack: str | None) -> None:
    """Escuta passiva LOCAL (Porcupine ou Vosk): zero requisições em espera."""
    print("BMO: Pronto! Escuta local ativa. Diga 'Bimo'! (Ctrl+C encerra)\n")
    while True:
        ouvidos.esperar_wake_word()  # bloqueia, offline
        print("BMO: Oi! Pode falar!")
        if ack:
            Boca.tocar(ack)

        comando = ouvidos.ouvir_comando()
        if not comando:
            print("BMO: Não entendi... me chame de novo!\n")
            continue

        boca, continuar = _atender(cerebro, boca, comando)
        if not continuar:
            break


def _loop_google(cerebro: Cerebro, ouvidos, boca: Boca | None, ack: str | None) -> None:
    """Escuta passiva via API do Google (fallback: gasta requisições)."""
    with ouvidos.abrir_microfone() as fonte:
        print("BMO: Calibrando o microfone...")
        limiar = ouvidos.calibrar(fonte)
        print(f"[limiar de energia: {limiar:.0f}]")
        print("BMO: Pronto! Me chame pelo nome (ex.: 'ei bimo'). Ctrl+C encerra.\n")

        while True:
            gatilho = ouvidos.esperar_wake_word(fonte)
            if not gatilho:
                continue

            print(f"BMO: Oi! (gatilho: '{gatilho}') Pode falar!")
            if ack:
                Boca.tocar(ack)

            comando = ouvidos.ouvir_comando(fonte)
            if not comando:
                print("BMO: Não entendi... me chame de novo!\n")
                continue

            boca, continuar = _atender(cerebro, boca, comando)
            if not continuar:
                break


def modo_voz(cerebro: Cerebro) -> None:
    from bmo.ears import OuvidosPorcupine, OuvidosVosk, criar_ouvidos

    ouvidos = criar_ouvidos()  # Porcupine → Vosk → Google
    escuta_local = isinstance(ouvidos, (OuvidosPorcupine, OuvidosVosk))
    boca = None if os.getenv("BMO_MUDO") else Boca()
    print(f"[escuta: {type(ouvidos).__name__} | voz: {boca.voz if boca else 'desligada'}]")

    # frase de confirmação pré-sintetizada: toca instantâneo a cada wake word
    ack = boca.sintetizar("Oi! Pode falar!") if boca else None

    try:
        if escuta_local:
            _loop_local(cerebro, ouvidos, boca, ack)
        else:
            _loop_google(cerebro, ouvidos, boca, ack)
    except KeyboardInterrupt:
        print("\nBMO: Até mais!")
    finally:
        if escuta_local:
            ouvidos.encerrar()
        if ack:
            try:
                os.remove(ack)
            except OSError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="BMO — assistente pessoal de voz")
    parser.add_argument(
        "--texto", action="store_true", help="chat de texto no terminal (sem microfone)"
    )
    parser.add_argument(
        "--voz", action="store_true", help="modo voz no terminal (sem janela)"
    )
    args = parser.parse_args()

    if not args.texto and not args.voz:
        try:
            from bmo.app import executar_app

            executar_app()
            return
        except Exception as e:
            print(f"[BMO] Janela indisponível ({e}). Caindo para o modo terminal.\n")

    cerebro = criar_cerebro()

    if args.texto:
        modo_texto(cerebro)
        return

    try:
        modo_voz(cerebro)
    except Exception as e:
        print(f"[BMO] Modo voz indisponível ({e}). Caindo para o modo texto.\n")
        modo_texto(cerebro)


if __name__ == "__main__":
    main()
