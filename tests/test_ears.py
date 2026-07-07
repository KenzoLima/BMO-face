"""Testes dos ouvidos — só a lógica pura (sem microfone, sem rede)."""

from bmo.ears import Ouvidos, contem_wake_word


def test_wake_word_direta():
    assert contem_wake_word("bimo") is True


def test_wake_word_dentro_de_frase():
    assert contem_wake_word("Ei Bimo, tudo bem?") is True
    assert contem_wake_word("oi bimo") is True


def test_variantes_de_transcricao():
    # o reconhecedor às vezes transcreve "BMO" destas formas
    assert contem_wake_word("beemo abre o code") is True
    assert contem_wake_word("chama o bmo aí") is True


def test_fala_sem_wake_word_nao_ativa():
    assert contem_wake_word("que horas são?") is False
    assert contem_wake_word("") is False


def test_wake_words_customizadas():
    assert contem_wake_word("ok robô", wake_words=("robô",)) is True
    assert contem_wake_word("bimo", wake_words=("robô",)) is False


def test_configuracao_padrao_dos_ouvidos():
    ouvidos = Ouvidos()
    assert ouvidos.idioma == "pt-BR"
    assert ouvidos.reconhecedor.dynamic_energy_threshold is True
    assert "bimo" in ouvidos.wake_words


# ── Porcupine (só configuração; detecção real exige chave + microfone) ─────

def test_porcupine_sem_chave_explica_o_que_falta(monkeypatch):
    import pytest

    from bmo.ears import OuvidosPorcupine

    monkeypatch.delenv("PICOVOICE_ACCESS_KEY", raising=False)
    with pytest.raises(ValueError, match="PICOVOICE_ACCESS_KEY"):
        OuvidosPorcupine()


def test_porcupine_sem_modelo_ppn_explica_o_que_falta(monkeypatch):
    import pytest

    from bmo.ears import OuvidosPorcupine

    monkeypatch.setenv("PICOVOICE_ACCESS_KEY", "chave-de-teste")
    monkeypatch.setenv("BMO_WAKE_WORD_PPN", "C:/nao/existe/bimo.ppn")
    with pytest.raises(ValueError, match=r"\.ppn"):
        OuvidosPorcupine()


def test_vosk_sem_modelo_explica_o_que_falta(monkeypatch):
    import pytest

    from bmo.ears import OuvidosVosk

    monkeypatch.setenv("BMO_VOSK_MODELO", "C:/nao/existe/modelo-vosk")
    with pytest.raises(ValueError, match="Vosk"):
        OuvidosVosk()


def test_factory_escolhe_vosk_sem_porcupine(monkeypatch):
    from bmo.ears import OuvidosVosk, criar_ouvidos

    monkeypatch.delenv("PICOVOICE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("BMO_VOSK_MODELO", raising=False)
    assert isinstance(criar_ouvidos(), OuvidosVosk)


def test_factory_cai_para_google_sem_nada(monkeypatch):
    import bmo.ears as ears

    monkeypatch.delenv("PICOVOICE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("BMO_VOSK_MODELO", raising=False)
    monkeypatch.setattr(ears.OuvidosVosk, "_achar_modelo", staticmethod(lambda: None))
    assert isinstance(ears.criar_ouvidos(), Ouvidos)
