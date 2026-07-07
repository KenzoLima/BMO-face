"""BMO — chat no terminal com resposta falada.

Você digita, o BMO age (cérebro + ferramentas) e responde em texto E voz.
Se a voz falhar (sem internet/áudio), o chat continua só em texto.
A Fase 2 (microfone) vai se conectar por cima deste mesmo Cerebro.

Uso:  python main.py
      BMO_MUDO=1 python main.py   (desliga a voz)
"""

import os

from dotenv import load_dotenv

load_dotenv()

from bmo.brain import Cerebro  # noqa: E402 - precisa do .env carregado antes
from bmo.mouth import Boca  # noqa: E402

COMANDOS_SAIR = {"sair", "tchau", "exit", "quit"}


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


def main() -> None:
    print("BMO inicializando... bip bup!")
    cerebro = Cerebro()
    boca = None if os.getenv("BMO_MUDO") else Boca()
    reserva = cerebro.reserva.nome if cerebro.reserva else "nenhuma"
    voz = boca.voz if boca else "desligada"
    print(f"[cérebro: {cerebro.provedor.nome} | reserva: {reserva} | voz: {voz}]")
    print("BMO: Oi! O que vamos fazer hoje? (digite 'sair' para encerrar)\n")

    while True:
        try:
            texto = input("Você: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBMO: Até mais! Bip!")
            break

        if not texto:
            continue
        if texto.lower() in COMANDOS_SAIR:
            print("BMO: Até mais! Bip!")
            break

        print("BMO: [computando...]")
        resposta = cerebro.responder(texto)
        print(f"BMO: {resposta}\n")


if __name__ == "__main__":
    main()
