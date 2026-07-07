"""Calibrador da wake word local (Vosk) — não roda no pytest.

Sintetiza áudios com a voz do Windows (SAPI, 16kHz mono) e mede a precisão
do detector pelo MESMO caminho de decisão do esperar_wake_word():
parciais curtos com token exato, finais com confiança mínima.

Uso:  python tests/calibrar_wake_word.py
"""

import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bmo.ears import OuvidosVosk  # noqa: E402

# (rótulo, texto falado, taxa de fala SAPI, deve_disparar)
CASOS = [
    ("bimo seco",            "bimo",                              0,  True),
    ("bimo lento",           "bimo",                             -3,  True),
    ("bimo rápido",          "bimo",                              3,  True),
    ("ei bimo",              "ei bimo",                           0,  True),
    ("oi bimo + comando",    "oi bimo, abre a calculadora",       0,  True),
    ("bimo repetido",        "bimo. bimo.",                      -1,  True),
    ("conversa neutra",      "vou ao mercado comprar pão e leite", 0, False),
    ("pegadinha biologia",   "a aula de biologia foi muito legal", 0, False),
    ("pegadinha bico",       "o bico do passarinho é amarelo",     0, False),
    ("pegadinha vimos",      "nós vimos o filme ontem à noite",    0, False),
    ("pegadinha mimo",       "que mimo lindo você me deu",         0, False),
    ("pegadinha bicicleta",  "bicicleta",                          0, False),
    ("pegadinha vi",         "eu vi você ontem",                   0, False),
]


def sintetizar(texto: str, taxa: int, destino: str) -> None:
    comando = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SelectVoice('Microsoft Maria Desktop'); "
        f"$s.Rate = {taxa}; "
        "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, "
        "[System.Speech.AudioFormat.AudioChannel]::Mono); "
        f"$s.SetOutputToWaveFile('{destino}', $fmt); "
        f"$s.Speak('{texto}'); $s.Dispose()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", comando],
        capture_output=True, timeout=60, check=True,
    )


def detectar(ouvidos: OuvidosVosk, arquivo: str) -> str | None:
    """Reproduz a decisão de esperar_wake_word() lendo do arquivo."""
    rec = ouvidos._criar_reconhecedor()
    with wave.open(arquivo, "rb") as wav:
        while True:
            dados = wav.readframes(ouvidos.TAMANHO_BLOCO)
            if not dados:
                return ouvidos._checar_final(json.loads(rec.FinalResult()))
            if rec.AcceptWaveform(dados):
                palavra = ouvidos._checar_final(json.loads(rec.Result()))
                if palavra:
                    return palavra


def main() -> int:
    ouvidos = OuvidosVosk()
    print(f"palavras-âncora: {ouvidos.wake_words}")
    print(f"banda de confiança: {ouvidos._banda_confianca()}\n")

    falhas = 0
    for rotulo, texto, taxa, esperado in CASOS:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            arquivo = tmp.name
        try:
            sintetizar(texto, taxa, arquivo)
            disparou = detectar(ouvidos, arquivo)
        finally:
            Path(arquivo).unlink(missing_ok=True)

        ok = bool(disparou) == esperado
        falhas += not ok
        status = "OK " if ok else "FALHOU"
        alvo = "deve disparar" if esperado else "NÃO deve disparar"
        print(f"[{status}] {rotulo:22s} ({alvo}) -> {disparou!r}")

    print(f"\n{len(CASOS) - falhas}/{len(CASOS)} casos corretos")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
