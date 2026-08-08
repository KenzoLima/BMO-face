"""Testes do modo streaming: falar enquanto o modelo ainda escreve."""

from __future__ import annotations

import pytest

from bmo.brain.agent import Cerebro
from bmo.mouth import LIMITE_FRASE, frases


def picar(texto: str, tamanho: int = 4):
    """Simula a chegada do texto em pedacos, como no streaming de verdade."""
    for i in range(0, len(texto), tamanho):
        yield texto[i:i + tamanho]


# --- quebra em frases ---


def test_primeira_frase_sai_antes_do_texto_acabar():
    """O ponto todo: nao esperar o texto inteiro para comecar a falar."""
    saiu = list(frases(picar("[feliz] Claro! Abri a calculadora pra voce.")))
    assert saiu[0] == "[feliz] Claro!"
    assert saiu[1] == "Abri a calculadora pra voce."


@pytest.mark.parametrize("tamanho", [1, 2, 3, 7, 50, 500])
def test_o_texto_falado_nao_depende_do_tamanho_do_pedaco(tamanho):
    """O modelo pode picar onde quiser — inclusive no meio da pontuacao."""
    texto = "[feliz] Oi! Tudo bem? Eu sou o BMO... prazer!"
    assert " ".join(frases(picar(texto, tamanho))) == texto


def test_nada_se_perde_nem_se_duplica():
    texto = "Uma. Duas! Tres? Quatro"
    partes = list(frases(picar(texto, 3)))
    assert partes == ["Uma.", "Duas!", "Tres?", "Quatro"]


def test_texto_sem_pontuacao_nao_segura_o_audio_para_sempre():
    longo = "palavra " * 60  # bem mais que LIMITE_FRASE
    partes = list(frases([longo]))
    assert len(partes) > 1
    assert all(len(p) <= LIMITE_FRASE for p in partes)
    assert "".join(p + " " for p in partes).split() == longo.split()


def test_numeros_e_precos_nao_viram_frase():
    """Cortar em '14.' quebraria 'R$ 14.50' no meio."""
    assert list(frases(["Custa R$ 14.50 e chega em 3.5 dias."])) == [
        "Custa R$ 14.50 e chega em 3.5 dias."
    ]


def test_fluxo_vazio_nao_gera_frase():
    assert list(frases([])) == []
    assert list(frases(["", "   ", "\n"])) == []


def test_aspas_e_parenteses_ficam_com_a_frase():
    partes = list(frases(['Ele disse "oi!" e saiu. Depois voltou.']))
    assert partes == ['Ele disse "oi!" e saiu.', "Depois voltou."]


# --- Cerebro.responder_em_partes ---


class ProvedorStream:
    nome = "stream"

    def __init__(self, texto="[feliz] Oi! Tudo certo.", falha_em=None):
        self.texto = texto
        self.falha_em = falha_em  # indice do pedaco em que explode
        self.chamadas = 0

    def responder(self, texto, historico):
        return self.texto

    def responder_em_partes(self, texto, historico):
        self.chamadas += 1
        for i, pedaco in enumerate(picar(self.texto)):
            if self.falha_em is not None and i == self.falha_em:
                raise RuntimeError("conexao caiu no meio")
            yield pedaco


def test_resposta_em_partes_reconstroi_o_texto_e_guarda_no_historico():
    cerebro = Cerebro(provedor=ProvedorStream(), reserva=None)
    texto = "".join(cerebro.responder_em_partes("oi bmo"))

    assert texto == "[feliz] Oi! Tudo certo."
    assert cerebro.historico == [
        {"role": "user", "content": "oi bmo"},
        {"role": "assistant", "content": "[feliz] Oi! Tudo certo."},
    ]


def test_falha_antes_de_falar_qualquer_coisa_usa_a_reserva():
    primario = ProvedorStream(falha_em=0)
    reserva = ProvedorStream("[focado] Reserva no comando!")
    cerebro = Cerebro(provedor=primario, reserva=reserva)

    assert "".join(cerebro.responder_em_partes("oi")) == "[focado] Reserva no comando!"
    assert reserva.chamadas == 1


def test_falha_no_MEIO_da_fala_nao_recomeca_com_a_reserva():
    """O BMO ja falou em voz alta: reiniciar com outro provedor sairia
    incoerente. Ele encerra a frase admitindo o problema."""
    primario = ProvedorStream("[feliz] Deixa comigo! Vou procurar isso.", falha_em=4)
    reserva = ProvedorStream("[focado] Resposta completamente diferente.")
    cerebro = Cerebro(provedor=primario, reserva=reserva)

    texto = "".join(cerebro.responder_em_partes("oi"))

    assert reserva.chamadas == 0, "a reserva nao pode atropelar o que ja foi dito"
    assert texto.startswith("[feliz] Deixa")
    assert "pode repetir" in texto
    assert cerebro.historico[-1]["content"].startswith("[feliz] Deixa")


def test_provedor_sem_streaming_ainda_funciona():
    """Groq/Ollama nao transmitem ainda: devolvem tudo num pedaco so."""
    class SoInteiro:
        nome = "inteiro"

        def responder(self, texto, historico):
            return "[feliz] Resposta inteira de uma vez."

    cerebro = Cerebro(provedor=SoInteiro(), reserva=None)
    assert "".join(cerebro.responder_em_partes("oi")) == (
        "[feliz] Resposta inteira de uma vez."
    )


# --- aparo de silencio (o ack bloqueia a abertura do microfone) ---


@pytest.fixture
def audio_disponivel():
    """O aparo mexe no mixer; sem placa de som nao ha o que testar."""
    from bmo.mouth import Boca

    try:
        Boca._mixer()
    except Exception as e:
        pytest.skip(f"sem audio: {e}")


def _wav_com_silencio(caminho, taxa, canais, silencio_s, tom_s):
    """Gera silencio + tom + silencio, no formato que o mixer devolve."""
    import wave

    import numpy as np

    quieto = np.zeros(int(taxa * silencio_s), dtype=np.int16)
    t = np.arange(int(taxa * tom_s)) / taxa
    tom = (np.sin(2 * np.pi * 440 * t) * 12000).astype(np.int16)
    mono = np.concatenate([quieto, tom, quieto])
    dados = np.column_stack([mono] * canais) if canais > 1 else mono

    with wave.open(str(caminho), "wb") as wav:
        wav.setnchannels(canais)
        wav.setsampwidth(2)
        wav.setframerate(taxa)
        wav.writeframes(np.ascontiguousarray(dados).tobytes())
    return str(caminho)


def test_aparo_corta_o_silencio_das_pontas(audio_disponivel, tmp_path):
    from bmo.mouth import MARGEM_SILENCIO, Boca, _aparar_silencio

    pygame = Boca._mixer()
    taxa, _, canais = pygame.mixer.get_init()
    origem = _wav_com_silencio(tmp_path / "com_silencio.wav", taxa, canais, 1.0, 0.30)

    antes = pygame.mixer.Sound(origem).get_length()
    aparado = _aparar_silencio(origem)
    depois = pygame.mixer.Sound(aparado).get_length()

    assert antes == pytest.approx(2.30, abs=0.05)
    # sobra o tom + a margem dos dois lados
    assert depois == pytest.approx(0.30 + 2 * MARGEM_SILENCIO, abs=0.08)
    assert depois < antes


def test_aparo_nao_estraga_audio_sem_silencio(audio_disponivel, tmp_path):
    from bmo.mouth import Boca, _aparar_silencio

    pygame = Boca._mixer()
    taxa, _, canais = pygame.mixer.get_init()
    origem = _wav_com_silencio(tmp_path / "sem_silencio.wav", taxa, canais, 0.0, 0.50)

    antes = pygame.mixer.Sound(origem).get_length()
    depois = pygame.mixer.Sound(_aparar_silencio(origem)).get_length()
    assert depois == pytest.approx(antes, abs=0.05)


def test_aparo_devolve_o_original_se_algo_der_errado(tmp_path):
    """Aparar e otimizacao: falhar aqui nao pode custar a fala."""
    from bmo.mouth import _aparar_silencio

    inexistente = str(tmp_path / "nao_existe.mp3")
    assert _aparar_silencio(inexistente) == inexistente


def test_texto_vazio_nao_chama_o_provedor():
    provedor = ProvedorStream()
    cerebro = Cerebro(provedor=provedor, reserva=None)

    assert "pode repetir" in "".join(cerebro.responder_em_partes("   "))
    assert provedor.chamadas == 0
    assert cerebro.historico == []
