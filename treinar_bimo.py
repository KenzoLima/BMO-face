"""
Gera o modelo de wake word 'bimo' para o OuvidosOpenWakeWord.

Pré-requisitos (instale uma vez):
    pip install "openwakeword[train]" gTTS pydub

Execute uma vez antes de usar o BMO com o motor OpenWakeWord:
    python treinar_bimo.py

O modelo será salvo em modelos/bimo.onnx (~500 KB).
O treinamento leva 3-10 minutos dependendo da CPU.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DIR_MODELOS = Path(__file__).parent / "modelos"
MODELO_SAIDA = DIR_MODELOS / "bimo.onnx"

# Variantes fonéticas de "bimo" para cobrir diferentes pronúncias e velocidades
VARIANTES = [
    "bimo",
    "ei bimo",
    "oi bimo",
    "bimo!",
    "hey bimo",
    "bemo",
    "bimo tá aqui",
    "bimo pode ouvir",
    "oi bimo tudo bem",
    "bimo me ajuda",
]


def verificar_dependencias() -> None:
    faltando = []

    try:
        import openwakeword  # noqa
        try:
            from openwakeword.train import train_model  # noqa
        except ImportError:
            faltando.append('"openwakeword[train]"')
    except ImportError:
        faltando.append('"openwakeword[train]"')

    try:
        from gtts import gTTS  # noqa
    except ImportError:
        faltando.append("gTTS")

    try:
        import pydub  # noqa
    except ImportError:
        faltando.append("pydub")

    if faltando:
        print("Pacotes faltando. Instale com:")
        print(f"    pip install {' '.join(faltando)}")
        sys.exit(1)


def gerar_amostras_tts(dir_saida: Path) -> None:
    """Gera amostras de áudio WAV das variantes de 'bimo' via gTTS."""
    from gtts import gTTS
    from pydub import AudioSegment

    dir_saida.mkdir(parents=True, exist_ok=True)
    total = len(VARIANTES) * 4  # 4 repetições = 40 amostras
    print(f"Gerando {total} amostras de áudio...")

    idx = 0
    for repeticao in range(4):
        for variante in VARIANTES:
            # Alterna velocidade para cobrir fala rápida e pausada
            devagar = repeticao % 2 == 1
            tts = gTTS(variante, lang="pt", slow=devagar)

            mp3_path = dir_saida / f"tmp_{idx:03d}.mp3"
            tts.save(str(mp3_path))

            # Converte para WAV 16 kHz mono (formato esperado pelo openWakeWord)
            wav_path = dir_saida / f"bimo_{idx:03d}.wav"
            audio = AudioSegment.from_mp3(str(mp3_path))
            audio = audio.set_frame_rate(16000).set_channels(1)
            audio.export(str(wav_path), format="wav")
            mp3_path.unlink()

            idx += 1
            if idx % 10 == 0:
                print(f"  {idx}/{total} amostras geradas...")

    print(f"Amostras WAV salvas em: {dir_saida}")


def treinar(dir_amostras: Path, dir_saida: Path) -> None:
    """Treina o modelo openWakeWord usando as amostras geradas."""
    from openwakeword.train import train_model

    print("Treinando modelo (3-10 min dependendo da CPU)...")
    dir_saida.mkdir(parents=True, exist_ok=True)

    train_model(
        positive_dir=str(dir_amostras),
        output_dir=str(dir_saida),
        model_name="bimo",
        # Amostras negativas: openWakeWord usa conjunto interno de ruído de fundo
    )


def main() -> None:
    if MODELO_SAIDA.exists():
        resp = input(f"Modelo já existe em '{MODELO_SAIDA}'. Recriar? [s/N] ").strip()
        if resp.lower() != "s":
            print("Cancelado.")
            return

    print("=== Treinamento de wake word 'bimo' para o BMO ===\n")
    verificar_dependencias()

    with tempfile.TemporaryDirectory(prefix="bmo_treino_") as tmp:
        dir_tmp = Path(tmp)
        dir_amostras = dir_tmp / "amostras"

        gerar_amostras_tts(dir_amostras)
        treinar(dir_amostras, DIR_MODELOS)

    if MODELO_SAIDA.exists():
        tamanho_kb = MODELO_SAIDA.stat().st_size // 1024
        print(f"\nModelo gerado: {MODELO_SAIDA} ({tamanho_kb} KB)")
        print("Reinicie o BMO — ele usará automaticamente o OpenWakeWord.")
    else:
        print("\nERRO: o modelo não foi gerado. Verifique os logs acima.")
        print("Se train_model não existir na versão instalada, tente:")
        print("    pip install --upgrade 'openwakeword[train]'")
        sys.exit(1)


if __name__ == "__main__":
    main()
