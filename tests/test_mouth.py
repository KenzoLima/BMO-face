"""Testes da boca do BMO — só a lógica pura (sem rede, sem áudio)."""

from bmo.mouth import Boca, limpar_para_fala


def test_remove_expressao_do_rosto():
    assert limpar_para_fala("[feliz] Oi! Tudo bem?") == "Oi! Tudo bem?"


def test_remove_expressao_em_qualquer_posicao_e_caixa():
    assert limpar_para_fala("Estou [Pensativo] agora") == "Estou agora"


def test_remove_markdown():
    assert limpar_para_fala("**Pronto!** Abri o `code` para você") == (
        "Pronto! Abri o code para você"
    )


def test_remove_emoji():
    assert limpar_para_fala("Encontrei! 🎮👾") == "Encontrei!"


def test_normaliza_espacos():
    assert limpar_para_fala("[focado]   Feito!   Bip!") == "Feito! Bip!"


def test_bmo_vira_bimo_na_fala():
    assert limpar_para_fala("Eu sou o BMO!") == "Eu sou o Bímo!"
    assert limpar_para_fala("bmo está pronto") == "Bímo está pronto"


def test_bmo_dentro_de_palavra_nao_e_alterado():
    # 'bmo_face.py' é nome de arquivo, não o nome do robô
    # (o '_' sai junto com o markdown, mas o 'bmo' colado não vira 'Bímo')
    assert limpar_para_fala("abra o bmo_face.py") == "abra o bmoface.py"


def test_texto_sem_nada_falavel_vira_vazio():
    assert limpar_para_fala("[dormindo] 💤") == ""


def test_falar_texto_vazio_retorna_false_sem_tocar():
    assert Boca().falar("[dormindo]") is False


def test_configuracao_padrao_da_voz():
    boca = Boca()
    assert boca.voz.startswith("pt-BR-")
    assert boca.velocidade and boca.tom


def test_envelope_distingue_silencio_de_som(tmp_path):
    """Gera um wav com 0.5s de silêncio + 0.5s de tom e confere o envelope."""
    import math
    import struct
    import wave

    caminho = tmp_path / "tom.wav"
    taxa = 22050
    with wave.open(str(caminho), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(taxa)
        silencio = [0] * (taxa // 2)
        tom = [
            int(20000 * math.sin(2 * math.pi * 220 * i / taxa))
            for i in range(taxa // 2)
        ]
        wav.writeframes(struct.pack(f"<{len(silencio) + len(tom)}h", *silencio, *tom))

    pygame = Boca._mixer()
    envelope = Boca._calcular_envelope(pygame.mixer.Sound(str(caminho)))

    assert envelope is not None and len(envelope) >= 10
    metade = len(envelope) // 2
    inicio = sum(envelope[2 : metade - 2]) / (metade - 4)
    fim = sum(envelope[metade + 2 : -2]) / (metade - 4)
    assert inicio < 0.2, f"silêncio deveria ter amplitude ~0 (deu {inicio:.2f})"
    assert fim > 0.7, f"tom deveria ter amplitude alta (deu {fim:.2f})"


def test_polimento_do_envelope_remove_ruido_e_suaviza_quedas():
    envelope = Boca._polir_envelope([0.01, 0.2, 1.0, 0.15, 0.0])

    assert envelope is not None
    assert envelope[0] == 0.0
    assert max(envelope) == 1.0
    assert envelope[3] > envelope[4]  # a boca fecha sem bater seco


def test_lip_sync_comeca_depois_do_play(monkeypatch, tmp_path):
    caminho = tmp_path / "fala.mp3"
    caminho.write_bytes(b"fake")
    eventos = []

    class CanalFake:
        def get_busy(self):
            return False

    class SomFake:
        def play(self):
            eventos.append("play")
            return CanalFake()

    class MixerFake:
        def Sound(self, _caminho):
            return SomFake()

    class PygameFake:
        mixer = MixerFake()

    boca = Boca()
    monkeypatch.setattr(boca, "sintetizar", lambda _texto: str(caminho))
    monkeypatch.setattr(Boca, "_mixer", staticmethod(lambda: PygameFake()))

    def calcular(_som):
        eventos.append("envelope")
        return [0.4]

    monkeypatch.setattr(Boca, "_calcular_envelope", staticmethod(calcular))

    assert boca.falar("oi", ao_iniciar=lambda env: eventos.append(("iniciar", env)))
    assert eventos == ["envelope", "play", ("iniciar", [0.4])]
    assert eventos.index("play") < eventos.index(("iniciar", [0.4]))
