"""Testes do motor de proatividade — a 'vida própria' do BMO.

Testamos só o ``MotorProatividade`` (lógica pura): dado o relógio, ele decide
se há algo a dizer. Sem threads, sem áudio, sem rede.
"""

from __future__ import annotations

from datetime import datetime

from bmo.proatividade import Fala, MotorProatividade


def novo_motor(**kwargs) -> MotorProatividade:
    """Motor com configuração explícita (ignora o ambiente) para testes
    determinísticos. Início às 08:00 de uma segunda-feira."""
    base = dict(
        ativo=True,
        hora_briefing=8,
        pausa_horas=3.0,
        cooldown_min=45.0,
        intervalo_caderno_horas=6.0,
        inicio=datetime(2026, 7, 6, 8, 0),  # segunda-feira
    )
    base.update(kwargs)
    return MotorProatividade(**base)


# --- liga/desliga ---


def test_desativado_nunca_fala():
    motor = novo_motor(ativo=False)
    assert motor.avaliar(datetime(2026, 7, 6, 9, 0)) is None
    assert motor.avaliar(datetime(2026, 7, 6, 20, 0)) is None


# --- briefing matinal ---


def test_briefing_nao_fala_antes_da_hora():
    motor = novo_motor(hora_briefing=8)
    assert motor.avaliar(datetime(2026, 7, 6, 7, 59)) is None


def test_briefing_fala_na_hora_com_nome_e_data(monkeypatch):
    monkeypatch.setenv("BMO_USUARIO_NOME", "Kenzo")
    motor = novo_motor()
    fala = motor.avaliar(datetime(2026, 7, 6, 8, 30))
    assert isinstance(fala, Fala)
    assert fala.chave == "briefing"
    assert fala.texto.startswith("[feliz]")
    assert "Kenzo" in fala.texto
    assert "06/07" in fala.texto
    assert "segunda-feira" in fala.texto


def test_briefing_so_uma_vez_por_dia():
    motor = novo_motor(pausa_horas=999)  # isola o briefing da sugestao de pausa
    manha = datetime(2026, 7, 6, 8, 30)
    fala = motor.avaliar(manha)
    assert fala.chave == "briefing"
    motor.registrar(fala, manha)
    # mais tarde no MESMO dia (fora do cooldown) -> nada de briefing de novo
    assert motor.avaliar(datetime(2026, 7, 6, 15, 0)) is None
    # no dia seguinte, volta a dar bom dia
    fala2 = motor.avaliar(datetime(2026, 7, 7, 8, 30))
    assert fala2 is not None and fala2.chave == "briefing"


def test_briefing_saudacao_muda_com_a_hora():
    motor = novo_motor()
    assert "Boa tarde" in motor.avaliar(datetime(2026, 7, 6, 14, 0)).texto
    motor2 = novo_motor()
    assert "Boa noite" in motor2.avaliar(datetime(2026, 7, 6, 20, 0)).texto


def test_briefing_conta_lembretes_do_dia():
    motor = novo_motor(provedor_lembretes=lambda: [{"mensagem": "beber agua"}, {"mensagem": "reuniao"}])
    fala = motor.avaliar(datetime(2026, 7, 6, 9, 0))
    assert "2 lembretes" in fala.texto

    motor_zero = novo_motor(provedor_lembretes=lambda: [])
    assert "nao tem lembretes" in motor_zero.avaliar(datetime(2026, 7, 6, 9, 0)).texto.replace("ã", "a")

    motor_um = novo_motor(provedor_lembretes=lambda: [{"mensagem": "ligar pro dentista"}])
    assert "ligar pro dentista" in motor_um.avaliar(datetime(2026, 7, 6, 9, 0)).texto


def test_provedor_de_lembretes_quebrado_nao_derruba_briefing():
    def explode():
        raise RuntimeError("powershell falhou")

    motor = novo_motor(provedor_lembretes=explode)
    fala = motor.avaliar(datetime(2026, 7, 6, 9, 0))
    assert fala is not None and fala.chave == "briefing"


# --- sugestao de pausa ---


def test_pausa_so_depois_de_n_horas():
    motor = novo_motor(hora_briefing=99)  # briefing desligado p/ isolar a pausa
    assert motor.avaliar(datetime(2026, 7, 6, 10, 59)) is None  # < 3h de uso
    fala = motor.avaliar(datetime(2026, 7, 6, 11, 1))           # > 3h de uso
    assert fala is not None and fala.chave == "pausa"


def test_pausa_reinicia_a_contagem_apos_falar():
    motor = novo_motor(hora_briefing=99)
    t1 = datetime(2026, 7, 6, 11, 1)
    fala = motor.avaliar(t1)
    assert fala.chave == "pausa"
    motor.registrar(fala, t1)
    assert motor.avaliar(datetime(2026, 7, 6, 12, 0)) is None
    fala2 = motor.avaliar(datetime(2026, 7, 6, 14, 5))
    assert fala2 is not None and fala2.chave == "pausa"


# --- cooldown global ---


def test_cooldown_bloqueia_falas_seguidas():
    motor = novo_motor(hora_briefing=99, provedor_nota=lambda: {"nota": "wifi", "trecho": "senha 123"})
    t1 = datetime(2026, 7, 6, 11, 1)
    fala = motor.avaliar(t1)  # pausa (3h de uso)
    assert fala.chave == "pausa"
    motor.registrar(fala, t1)
    assert motor.avaliar(datetime(2026, 7, 6, 11, 31)) is None  # cooldown 45min segura
    fala2 = motor.avaliar(datetime(2026, 7, 6, 11, 50))
    assert fala2 is not None and fala2.chave == "caderno"


# --- recordacao do caderno ---


def test_caderno_sem_provedor_nao_fala():
    motor = novo_motor(hora_briefing=99, pausa_horas=999)
    assert motor.avaliar(datetime(2026, 7, 6, 12, 0)) is None


def test_caderno_recorda_e_nao_repete_a_mesma_nota():
    nota = {"nota": "aniversario-da-mae", "trecho": "dia 12 de agosto"}
    motor = novo_motor(hora_briefing=99, pausa_horas=999, provedor_nota=lambda: nota)
    t1 = datetime(2026, 7, 6, 12, 0)
    fala = motor.avaliar(t1)
    assert fala.chave == "caderno"
    assert "dia 12 de agosto" in fala.texto
    assert fala.ref == "aniversario-da-mae"
    motor.registrar(fala, t1)
    assert motor.avaliar(datetime(2026, 7, 6, 20, 0)) is None  # mesma nota -> nada


def test_caderno_respeita_o_intervalo_proprio():
    contador = {"n": 0}

    def provedor():
        contador["n"] += 1
        return {"nota": f"nota-{contador['n']}", "trecho": f"conteudo {contador['n']}"}

    motor = novo_motor(hora_briefing=99, pausa_horas=999, provedor_nota=provedor,
                       intervalo_caderno_horas=6.0)
    t1 = datetime(2026, 7, 6, 12, 0)
    fala = motor.avaliar(t1)
    assert fala.chave == "caderno"
    motor.registrar(fala, t1)
    assert motor.avaliar(datetime(2026, 7, 6, 14, 0)) is None  # dentro do intervalo
    fala2 = motor.avaliar(datetime(2026, 7, 6, 18, 30))
    assert fala2 is not None and fala2.chave == "caderno"


# --- prioridade ---


def test_briefing_tem_prioridade_sobre_pausa():
    motor = novo_motor(provedor_nota=lambda: {"nota": "x", "trecho": "y"})
    fala = motor.avaliar(datetime(2026, 7, 6, 12, 0))
    assert fala.chave == "briefing"


# --- custo: avaliar() nao pode disparar I/O caro ---


def test_avaliar_nao_consulta_lembretes_antes_de_ler_o_texto():
    """Listar lembretes abre um PowerShell (~3s). Enquanto ninguem le
    ``fala.texto``, o provedor nao pode ser chamado — senao uma avaliacao
    descartada (BMO fora do standby) pagaria o custo a toa."""
    chamadas = {"n": 0}

    def provedor():
        chamadas["n"] += 1
        return [{"mensagem": "reuniao"}]

    motor = novo_motor(provedor_lembretes=provedor)
    fala = motor.avaliar(datetime(2026, 7, 6, 9, 0))
    assert fala is not None and fala.chave == "briefing"
    assert chamadas["n"] == 0, "avaliar() nao pode consultar os lembretes"

    assert "reuniao" in fala.texto  # so agora o texto e montado
    assert chamadas["n"] == 1

    fala.texto  # segundo acesso reaproveita o texto ja gerado
    assert chamadas["n"] == 1
