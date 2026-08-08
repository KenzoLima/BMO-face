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

from bmo.paths import caminho_env, caminho_env_legado_instalacao

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


def _preparar_env(forcar: bool = False) -> None:
    """Garante um .env ao lado do programa e o carrega.

    ``forcar=True`` recarrega valores já definidos (usado após salvar
    a tela de configurações).
    """
    caminho = caminho_env()
    if not caminho.exists():
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text(MODELO_ENV, encoding="utf-8")
        except OSError:
            pass  # pasta somente leitura: segue com variáveis do sistema
    load_dotenv(caminho, override=forcar)
    legado = caminho_env_legado_instalacao()
    if legado is not None and legado != caminho and legado.exists():
        load_dotenv(legado, override=False)
    if not getattr(sys, "frozen", False):
        load_dotenv()  # .env do diretório atual, se houver, complementa


_preparar_env()

COMANDOS_SAIR = {"sair", "tchau", "exit", "quit", "tchau bimo", "até mais"}


def falar_com_seguranca(boca, texto: str):
    """Fala o texto; se a voz falhar, avisa e desliga a voz desta sessão."""
    if boca is None:
        return None
    try:
        boca.falar(texto)
        return boca
    except Exception as e:
        print(f"[BMO] Voz indisponível ({e}). Seguindo só com texto.")
        return None


def criar_cerebro():
    from bmo.brain import Cerebro

    print("BMO inicializando...")
    cerebro = Cerebro()
    # nome_reserva não constrói o provedor — ele só nasce se o primário falhar
    print(f"[cérebro: {cerebro.provedor.nome} | reserva: {cerebro.nome_reserva or 'nenhuma'}]")
    return cerebro


def modo_texto(cerebro) -> None:
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


def _responder_falando(cerebro, boca, comando: str) -> str | None:
    """Fala a resposta conforme ela chega, imprimindo o texto junto.

    Devolve o texto completo, ou None se a voz falhou (quem chama cai para
    o modo só-texto). Sem boca, só imprime — sem esperar síntese nenhuma.
    """
    pedacos: list[str] = []

    def acompanhando():
        for pedaco in cerebro.responder_em_partes(comando):
            pedacos.append(pedaco)
            print(pedaco, end="", flush=True)
            yield pedaco

    print("BMO: ", end="", flush=True)
    if boca is None:
        texto = "".join(acompanhando())
        print()
        return texto

    try:
        boca.falar_em_partes(acompanhando())
        print()
        return "".join(pedacos)
    except Exception as e:
        print(f"\n[BMO] Voz indisponível ({e}). Seguindo só com texto.")
        return None


def _conversar(cerebro, boca, ouvir_comando):
    """Conversa em turnos após a wake word: continua ouvindo até uma frase
    de encerramento ("obrigado", "só isso"...) ou silêncio."""
    from bmo.app import FRASES_ENCERRAR, TIMEOUT_PRIMEIRO_COMANDO, _timeout_conversa

    primeiro = True
    while True:
        timeout = TIMEOUT_PRIMEIRO_COMANDO if primeiro else _timeout_conversa()
        comando = ouvir_comando(timeout)

        if not comando:
            print("BMO: [assunto encerrado — me chame de novo com 'bimo']\n")
            return boca

        print(f"---> Você: {comando}")
        if comando.lower().strip() in FRASES_ENCERRAR:
            print("BMO: Até mais!")
            return falar_com_seguranca(boca, "Até mais!")

        primeiro = False
        print("BMO: [computando...]")
        resposta = _responder_falando(cerebro, boca, comando)
        if resposta is None:  # a voz falhou; segue só com texto
            boca = None
            resposta = cerebro.responder(comando)
            print(f"BMO: {resposta}")
        print("BMO: [ouvindo — continue, ou silêncio/'só isso' encerra]\n")


def _loop_local(cerebro, ouvidos, boca, ack: str | None) -> None:
    """Escuta passiva LOCAL (Porcupine ou Vosk): zero requisições em espera."""
    print("BMO: Pronto! Escuta local ativa. Diga 'Bimo'! (Ctrl+C encerra)\n")
    from bmo.mouth import Boca

    while True:
        ouvidos.esperar_wake_word()  # bloqueia, offline
        print("BMO: Oi! Pode falar!")
        if ack:
            Boca.tocar(ack)
        boca = _conversar(cerebro, boca, ouvidos.ouvir_comando)


def _loop_google(cerebro, ouvidos, boca, ack: str | None) -> None:
    """Escuta passiva via API do Google (fallback: gasta requisições)."""
    with ouvidos.abrir_microfone() as fonte:
        from bmo.mouth import Boca

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
            boca = _conversar(
                cerebro, boca,
                lambda t: ouvidos.ouvir_comando(fonte, timeout=t),
            )


def modo_voz(cerebro) -> None:
    from bmo.ears import OuvidosOpenWakeWord, OuvidosPorcupine, OuvidosVosk, criar_ouvidos
    from bmo.mouth import Boca

    ouvidos = criar_ouvidos()  # Porcupine → OpenWakeWord → Vosk → Google
    escuta_local = isinstance(ouvidos, (OuvidosPorcupine, OuvidosOpenWakeWord, OuvidosVosk))
    boca = None if os.getenv("BMO_MUDO") else Boca()
    print(f"[escuta: {type(ouvidos).__name__} | voz: {boca.voz if boca else 'desligada'}]")

    # frase de confirmação pré-sintetizada e aparada: ela BLOQUEIA a abertura
    # do microfone, então cada décimo de silêncio nela é espera do usuário
    from bmo.app import TEXTO_ACK

    ack = boca.sintetizar_curto(TEXTO_ACK) if boca else None

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
    parser.add_argument(
        "--config", action="store_true", help="abre só a tela de configurações"
    )
    args = parser.parse_args()

    if args.config:
        from bmo.config_ui import abrir_configuracoes

        abrir_configuracoes()
        return

    # primeira execução: sem chave, abre a tela de boas-vindas (Tela 3 do esboço)
    if not os.getenv("GOOGLE_API_KEY"):
        from bmo.config_ui import abrir_configuracoes

        if not abrir_configuracoes(primeira_vez=True):
            return  # usuário fechou sem salvar
        _preparar_env(forcar=True)  # recarrega o .env que acabou de ser salvo

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
