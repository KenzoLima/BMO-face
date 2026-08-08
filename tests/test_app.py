"""Testes do ciclo de conversa do app — com dublês, sem microfone/API."""

import time

import pytest

import bmo.app as app_mod
from bmo.app import AssistenteDeVoz, _timeout_conversa
from bmo.face import EstadoBMO


class CerebroFake:
    def __init__(self):
        self.perguntas = []

    def responder(self, texto):
        self.perguntas.append(texto)
        return f"[feliz] resposta {len(self.perguntas)}"

    def responder_em_partes(self, texto, ao_ferramenta=None):
        """Entrega picado, como o streaming de verdade — inclusive quebrando
        o prefixo [feliz] no meio, que e o caso chato para a emocao."""
        resposta = self.responder(texto)
        for i in range(0, len(resposta), 3):
            yield resposta[i:i + 3]


def novo_assistente():
    a = AssistenteDeVoz(EstadoBMO())
    a.cerebro = CerebroFake()
    a.boca = None
    a.ack = None
    return a


def executar_ciclo(assistente, falas):
    """Roda um ciclo com a sequência de falas simuladas (None = silêncio)."""
    iterador = iter(falas)
    assistente._ciclo(lambda: "bi", lambda timeout: next(iterador))


def test_conversa_continua_sem_nova_wake_word():
    a = novo_assistente()
    executar_ciclo(a, ["que horas são", "e em londres?", "e em tóquio?", None])

    # três turnos respondidos com UMA única wake word
    assert a.cerebro.perguntas == ["que horas são", "e em londres?", "e em tóquio?"]
    assert a.estado.ler()[0] == "standby"


def test_frase_de_encerramento_fecha_o_assunto():
    a = novo_assistente()
    executar_ciclo(a, ["abre a calculadora", "obrigado"])

    assert a.cerebro.perguntas == ["abre a calculadora"]  # "obrigado" não vai ao LLM
    modo, emocao, _ = a.estado.ler()
    assert modo == "standby"
    assert emocao == "dormindo"


def test_silencio_no_primeiro_comando_volta_ao_standby():
    a = novo_assistente()
    executar_ciclo(a, [None])

    assert a.cerebro.perguntas == []
    assert a.estado.ler()[0] == "standby"


def test_primeiro_turno_tem_timeout_maior_que_os_seguintes():
    a = novo_assistente()
    timeouts = []

    def ouvir(timeout):
        timeouts.append(timeout)
        return "pergunta" if len(timeouts) < 3 else None

    a._ciclo(lambda: "bi", ouvir)
    assert timeouts[0] > timeouts[1]  # 1º comando espera mais; conversa é ágil
    assert timeouts[1] == timeouts[2] == _timeout_conversa()


def test_emocao_da_ultima_resposta_fica_no_rosto():
    a = novo_assistente()
    executar_ciclo(a, ["conta uma piada", None])

    _, emocao, _ = a.estado.ler()
    assert emocao == "feliz"  # veio do prefixo [feliz] da resposta


# --- inicializacao ---


def test_preparar_roda_as_partes_pesadas_em_paralelo(monkeypatch):
    """Cerebro, ouvidos e ack sao independentes: o boot deve custar o mais
    lento, nao a soma dos tres."""
    ATRASO = 0.3

    def lento(valor):
        def criar(*_):
            time.sleep(ATRASO)
            return valor
        return criar

    class BocaFake:
        sintetizar_curto = lento("ack.wav")

    monkeypatch.setenv("BMO_MUDO", "")
    monkeypatch.setattr(app_mod, "Cerebro", lento("cerebro"))
    monkeypatch.setattr(app_mod, "Boca", lambda: BocaFake())
    monkeypatch.setattr("bmo.ears.criar_ouvidos", lento("ouvidos"))

    a = AssistenteDeVoz(EstadoBMO())
    inicio = time.perf_counter()
    a._preparar()
    decorrido = time.perf_counter() - inicio

    assert (a.cerebro, a.ack) == ("cerebro", "ack.wav")
    assert a.ouvidos == "ouvidos"
    assert decorrido < ATRASO * 2, f"boot serializado ({decorrido:.2f}s para 3x{ATRASO}s)"


def test_falha_do_cerebro_sobe_para_a_thread_principal(monkeypatch):
    def explode():
        raise ValueError("GOOGLE_API_KEY nao encontrada no .env")

    monkeypatch.setenv("BMO_MUDO", "1")  # sem boca: isola o cerebro
    monkeypatch.setattr(app_mod, "Cerebro", explode)
    monkeypatch.setattr("bmo.ears.criar_ouvidos", lambda: "ouvidos")

    a = AssistenteDeVoz(EstadoBMO())
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        a._preparar()


# --- proatividade ---


def test_proatividade_nao_consulta_o_motor_fora_do_standby():
    """As guardas baratas (standby/trava) vem antes do motor, que pode ler o
    caderno e abrir um PowerShell."""
    a = novo_assistente()
    consultas = []
    a.motor_proativo.avaliar = lambda agora: consultas.append(agora)

    a.estado.mudar("ouvindo")
    a.tentar_proativo()
    assert consultas == []

    a.estado.mudar("processando")
    a.tentar_proativo()
    assert consultas == []

    a.estado.mudar("standby")
    a.tentar_proativo()
    assert len(consultas) == 1  # ocioso: agora sim vale perguntar ao motor


def test_medidor_aparece_no_auto_so_quando_o_saldo_cai(monkeypatch):
    monkeypatch.delenv("BMO_MEDIDOR", raising=False)
    monkeypatch.delenv("BMO_MEDIDOR_LIMIAR", raising=False)

    assert app_mod._mostrar_medidor("standby", 1.0) is False
    assert app_mod._mostrar_medidor("standby", 0.6) is False
    assert app_mod._mostrar_medidor("standby", 0.2) is True
    assert app_mod._mostrar_medidor("standby", 0.0) is True


def test_medidor_respeita_sempre_e_nunca(monkeypatch):
    monkeypatch.setenv("BMO_MEDIDOR", "sempre")
    assert app_mod._mostrar_medidor("standby", 1.0) is True

    monkeypatch.setenv("BMO_MEDIDOR", "nunca")
    assert app_mod._mostrar_medidor("standby", 0.0) is False


def test_medidor_fica_fora_das_telas_de_abertura_e_erro(monkeypatch):
    monkeypatch.setenv("BMO_MEDIDOR", "sempre")
    for modo in ("boot", "apresentacao", "erro"):
        assert app_mod._mostrar_medidor(modo, 0.0) is False
    for modo in ("standby", "ouvindo", "processando", "falando"):
        assert app_mod._mostrar_medidor(modo, 0.0) is True


def test_limiar_do_medidor_e_configuravel(monkeypatch):
    monkeypatch.delenv("BMO_MEDIDOR", raising=False)
    monkeypatch.setenv("BMO_MEDIDOR_LIMIAR", "0.9")
    assert app_mod._mostrar_medidor("standby", 0.8) is True

    monkeypatch.setenv("BMO_MEDIDOR_LIMIAR", "nao-e-numero")
    assert app_mod._mostrar_medidor("standby", 0.8) is False  # cai no padrao 0.5


def test_medidor_no_canto_nao_encosta_no_rosto():
    """O medidor divide o framebuffer com a carinha: nao pode invadir a area
    dos olhos (y >= 21) nem passar da metade da tela."""
    from bmo.app import MEDIDOR_CX, MEDIDOR_CY, MEDIDOR_RAIO
    from bmo.face import FrameBuffer
    from bmo.medidor import desenhar_medidor

    fb = FrameBuffer()
    desenhar_medidor(fb, MEDIDOR_CX, MEDIDOR_CY, MEDIDOR_RAIO, 0.5,
                     segmentos=6, espessura=2)

    acesos = [(x, y) for y in range(64) for x in range(128) if fb.get(x, y)]
    assert acesos, "o medidor precisa desenhar alguma coisa"
    assert max(y for _, y in acesos) < 21, "invadiu a altura dos olhos"
    assert max(x for x, _ in acesos) < 64, "passou da metade da tela"


def test_proatividade_nao_espera_a_trava_de_uma_conversa():
    a = novo_assistente()
    consultas = []
    a.motor_proativo.avaliar = lambda agora: consultas.append(agora)

    a.estado.mudar("standby")
    a.trava_fala.acquire()  # simula conversa em curso segurando a fala
    try:
        a.tentar_proativo()
    finally:
        a.trava_fala.release()

    assert consultas == []
