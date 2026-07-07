"""Testes do ciclo de conversa do app — com dublês, sem microfone/API."""

from bmo.app import AssistenteDeVoz, _timeout_conversa
from bmo.face import EstadoBMO


class CerebroFake:
    def __init__(self):
        self.perguntas = []

    def responder(self, texto):
        self.perguntas.append(texto)
        return f"[feliz] resposta {len(self.perguntas)}"


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
