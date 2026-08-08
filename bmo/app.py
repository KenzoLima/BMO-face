"""Aplicativo de desktop do BMO: janela flutuante + assistente de voz.

Arquitetura:
- Thread principal: janela pygame (rosto animado, arrastar, fechar).
- Thread de trabalho (daemon): ciclo do assistente — wake word → comando →
  cérebro → fala — publicando cada fase no ``EstadoBMO`` compartilhado,
  que o rosto reflete em tempo real.

Erros no ciclo de voz nunca derrubam o app: viram o estado "erro" no rosto
por alguns segundos e o ciclo recomeça.
"""

from __future__ import annotations

import os
import threading
import time

from .brain import Cerebro
from .consumo import fracao_restante
from .face import EstadoBMO, FrameBuffer, RostoBMO, desenhar_estado, extrair_emocao
from .medidor import desenhar_medidor_cacheado
from .mouth import Boca
from .proatividade import LacoProatividade, MotorProatividade

# Frases que encerram o ASSUNTO (a conversa volta ao modo wake word).
# Casamento exato da fala inteira — "obrigado pela dica, e amanhã?" não encerra.
FRASES_ENCERRAR = {
    "sair", "tchau", "exit", "quit", "tchau bimo", "até mais",
    "obrigado", "obrigada", "valeu", "só isso", "é só isso",
    "só isso mesmo", "por enquanto é só", "pode dormir",
}

TIMEOUT_PRIMEIRO_COMANDO = 10.0  # após a wake word

# Aviso que toca ao ouvir a wake word. Ele BLOQUEIA a abertura do microfone,
# então cada décimo aqui é tempo em que o usuário espera sem poder falar:
# "Oi! Pode falar!" custava 2,7s de áudio. Curto e aparado, custa ~0,4s.
TEXTO_ACK = os.getenv("BMO_ACK", "Oi!")

# Medidor de requisições no canto do rosto. Fica no alto à esquerda, a única
# região livre em todos os estados (os olhos começam em y=21, as ondas do
# "ouvindo" em y=16). Pequeno o bastante para não competir com a carinha.
MEDIDOR_CX, MEDIDOR_CY, MEDIDOR_RAIO = 16, 14, 11
MEDIDOR_LIMIAR_PADRAO = 0.5

# Estados em que o medidor NÃO aparece: telas de abertura e de erro têm
# composição própria e o medidor por cima delas só faria bagunça.
MODOS_SEM_MEDIDOR = frozenset(
    {"boot", "apresentacao", "erro", "pesquisando", "pesquisa_concluida"}
)

# Quanto tempo a tela de pesquisa fica CHEIA antes de sair — o suficiente para
# o usuário ver que a busca terminou, em vez de a tela sumir do nada.
SEGUNDOS_PESQUISA_CONCLUIDA = 0.45

# Falhas de fala seguidas antes de desistir da voz. Uma só não pode emudecer
# o BMO pelo resto da sessão (era o bug: uma oscilação de rede no meio de uma
# resposta e ele nunca mais falava, sem avisar).
MAX_FALHAS_DE_VOZ = 3


def _timeout_conversa() -> float:
    """Silêncio (s) que encerra o assunto no modo conversa."""
    return float(os.getenv("BMO_CONVERSA_TIMEOUT", "6"))


def _limiar_medidor() -> float:
    try:
        return float(os.getenv("BMO_MEDIDOR_LIMIAR", "").strip())
    except (TypeError, ValueError):
        return MEDIDOR_LIMIAR_PADRAO


def _mostrar_medidor(modo: str, fracao: float) -> bool:
    """Decide se o velocímetro entra no frame.

    ``BMO_MEDIDOR``: ``auto`` (padrão — só quando o saldo cai abaixo do
    limiar), ``sempre`` ou ``nunca``.
    """
    if modo in MODOS_SEM_MEDIDOR:
        return False
    escolha = os.getenv("BMO_MEDIDOR", "auto").strip().lower()
    if escolha in ("0", "nunca", "nao", "não", "off"):
        return False
    if escolha in ("1", "sempre", "sim", "on"):
        return True
    return fracao < _limiar_medidor()


def _avisar_usuario(titulo: str, mensagem: str) -> None:
    """Caixa de diálogo nativa — o app roda sem console, então erros de
    configuração precisam de um aviso visível."""
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, mensagem, titulo, 0x30)  # MB_ICONWARNING


class AssistenteDeVoz(threading.Thread):
    """Ciclo de voz do BMO rodando em segundo plano."""

    def __init__(self, estado: EstadoBMO):
        super().__init__(daemon=True, name="bmo-voz")
        self.estado = estado
        self.encerrar = threading.Event()
        # serializa a fala: a proatividade nunca corta uma conversa em curso
        self.trava_fala = threading.Lock()
        self._falhas_de_voz = 0  # ver _voz_falhou: falha isolada não emudece
        self.motor_proativo = MotorProatividade(
            provedor_lembretes=self._lembretes_hoje,
            provedor_nota=self._nota_espontanea,
        )
        self._laco_proativo: LacoProatividade | None = None

    # ── inicialização pesada (mostra o boot na janela enquanto roda) ─────
    def _preparar(self) -> None:
        """Sobe cérebro, ouvidos e a frase de confirmação — em paralelo.

        As três partes não dependem uma da outra e todas são lentas por
        motivos diferentes: o cérebro importa o SDK do provedor (~4s), os
        ouvidos carregam o modelo de wake word e o ``ack`` vai à rede do
        edge-tts. Em série, o boot custava a soma; juntas, custa o mais lento.
        """
        from .ears import criar_ouvidos

        self.boca = None if os.getenv("BMO_MUDO") else Boca()
        self.ack = None
        erros: dict[str, BaseException] = {}

        def em_thread(nome: str, criar):
            def alvo():
                try:
                    setattr(self, nome, criar())
                except BaseException as e:  # relançado na thread principal
                    erros[nome] = e

            return threading.Thread(target=alvo, name=f"bmo-init-{nome}", daemon=True)

        tarefas = [em_thread("cerebro", Cerebro), em_thread("ouvidos", criar_ouvidos)]
        if self.boca is not None:
            tarefas.append(
                em_thread("ack", lambda: self.boca.sintetizar_curto(TEXTO_ACK))
            )

        for tarefa in tarefas:
            tarefa.start()
        for tarefa in tarefas:
            tarefa.join()

        # ordem de prioridade: o erro do cérebro (ex.: chave de API ausente) é
        # o que o usuário precisa ver na caixa de diálogo
        for nome in ("cerebro", "ouvidos", "ack"):
            if nome in erros:
                raise erros[nome]

    # ── um ciclo completo: gatilho → CONVERSA (vários turnos) → standby ──
    def _ciclo(self, esperar_gatilho, ouvir_comando) -> None:
        """Após a wake word, o BMO conversa em turnos seguidos — sem exigir
        novo "bimo" a cada pergunta — até uma frase de encerramento ou
        silêncio (BMO_CONVERSA_TIMEOUT segundos)."""
        self.estado.mudar("standby")
        gatilho = esperar_gatilho()
        if not gatilho or self.encerrar.is_set():
            return

        # a conversa inteira roda sob a trava: a proatividade espera terminar
        with self.trava_fala:
            if self.ack:
                Boca.tocar(self.ack)

            emocao = None
            primeiro_turno = True
            while not self.encerrar.is_set():
                self.estado.mudar("ouvindo")
                timeout = TIMEOUT_PRIMEIRO_COMANDO if primeiro_turno else _timeout_conversa()
                comando = ouvir_comando(timeout)

                if not comando:  # silêncio: assunto encerrado, volta a esperar "bimo"
                    break

                if comando.lower().strip() in FRASES_ENCERRAR:
                    self._falar("Até mais!", emocao="feliz")
                    emocao = "dormindo"
                    break

                primeiro_turno = False
                self.estado.mudar("processando")
                resposta = self._responder_falando(comando)
                emocao = extrair_emocao(resposta)
                # continua no laço: ouvindo o próximo turno da conversa

            self.estado.mudar("standby", emocao=emocao)

    def _responder_falando(self, comando: str) -> str:
        """Pergunta ao cérebro e vai falando conforme a resposta chega.

        Antes eram dois bloqueios em série — o modelo escrevia a resposta
        inteira e só então o TTS gerava o áudio inteiro. Agora a primeira
        frase já vira voz enquanto o resto ainda está sendo escrito.
        Devolve o texto completo (para a emoção e o histórico).
        """
        ditos: list[str] = []

        def acompanhando():
            fluxo = self.cerebro.responder_em_partes(
                comando, ao_ferramenta=self._mostrar_ferramenta
            )
            for pedaco in fluxo:
                ditos.append(pedaco)
                yield pedaco

        if self.boca is None:
            resposta = "".join(acompanhando())
            self.estado.mudar("falando", emocao=extrair_emocao(resposta))
            time.sleep(1.0)  # aceno visual mesmo no modo mudo
            return resposta

        def ao_iniciar(envelope):
            # a emoção vem no prefixo [feliz], que chega no primeiro pedaço —
            # já está em 'ditos' quando a primeira frase começa a tocar
            self.estado.iniciar_fala(envelope, extrair_emocao("".join(ditos)))

        try:
            self.boca.falar_em_partes(acompanhando(), ao_iniciar=ao_iniciar)
            self._voz_funcionou()
        except Exception as e:
            self._voz_falhou(e)
        return "".join(ditos)

    def _mostrar_ferramenta(self, nomes: list[str], fase: str) -> None:
        """Mostra a tela de pesquisa enquanto uma ferramenta lenta trabalha.

        Sem isso o rosto ficava parado durante uma busca na internet e o BMO
        parecia travado — foi exatamente o sintoma relatado. A tela sempre
        FECHA: a fase 'fim' pinta a barra cheia por um instante, para o
        usuário ver que a pesquisa terminou, e só então a resposta continua.
        """
        if fase == "inicio":
            self.estado.mudar("pesquisando", detalhe=", ".join(nomes))
            return
        self.estado.mudar("pesquisa_concluida", detalhe=", ".join(nomes))
        time.sleep(SEGUNDOS_PESQUISA_CONCLUIDA)
        self.estado.mudar("processando")

    def _voz_falhou(self, erro: Exception) -> None:
        """Registra uma falha de fala — sem emudecer o BMO para sempre.

        Antes, QUALQUER exceção aqui zerava ``self.boca`` e o BMO nunca mais
        falava na sessão, em silêncio total: uma oscilação de rede no edge-tts
        durante uma resposta deixava o resto do dia mudo. Agora a falha é
        pontual; só depois de várias seguidas a voz é desligada, e nesse caso
        o rosto avisa.
        """
        self._falhas_de_voz += 1
        print(f"[BMO] Falha ao falar ({self._falhas_de_voz}/{MAX_FALHAS_DE_VOZ}): {erro}")
        if self._falhas_de_voz >= MAX_FALHAS_DE_VOZ:
            self.boca = None
            self.estado.mudar("erro", detalhe="voz indisponível")
            time.sleep(2.0)

    def _voz_funcionou(self) -> None:
        """Uma fala bem-sucedida zera o placar de falhas."""
        self._falhas_de_voz = 0

    def _falar(self, texto: str, emocao: str | None = None) -> None:
        """Fala com lip sync: o rosto entra em 'falando' no instante em que o
        áudio começa, e a boca segue o envelope de amplitude da voz."""
        if self.boca is None:
            self.estado.mudar("falando", emocao=emocao)
            time.sleep(1.0)  # aceno visual mesmo no modo mudo
            return
        try:
            self.boca.falar(
                texto,
                ao_iniciar=lambda env: self.estado.iniciar_fala(env, emocao),
            )
            self._voz_funcionou()
        except Exception as e:
            self._voz_falhou(e)

    # ── proatividade ("vida própria") ────────────────────────────────────
    def tentar_proativo(self) -> None:
        """Chamado pelo laço de fundo: se o motor liberar E o BMO estiver
        ocioso, o BMO toma uma pequena iniciativa (fala sozinho).

        As guardas vêm em ordem de custo: primeiro as de graça (standby, trava),
        só depois o motor — cuja avaliação pode ler o caderno — e por último o
        texto da fala, que é o mais caro de montar. Assim uma conversa em curso
        não paga nada pelo laço de fundo."""
        from datetime import datetime

        # 1) barato: se o BMO não está ocioso, não há o que fazer
        modo, _, _ = self.estado.ler()
        if modo != "standby" or self.encerrar.is_set():
            return
        # 2) barato: sem bloquear — se a trava está tomada, há conversa em curso
        if not self.trava_fala.acquire(blocking=False):
            return
        try:
            # reconfere sob a trava: o estado pode ter mudado no meio do caminho
            modo, _, _ = self.estado.ler()
            if modo != "standby" or self.encerrar.is_set():
                return
            # 3) caro: só agora o motor decide, e só agora o texto é montado
            fala = self.motor_proativo.avaliar(datetime.now())
            if fala is None:
                return
            texto = fala.texto
            emocao = extrair_emocao(texto)
            self._falar(texto, emocao=emocao)
            self.estado.mudar("standby", emocao=emocao)
            self.motor_proativo.registrar(fala, datetime.now())
        finally:
            self.trava_fala.release()

    def _lembretes_hoje(self) -> list:
        """Lembretes agendados para a data de hoje (para o briefing matinal)."""
        try:
            from datetime import datetime

            from .hands.reminders import listar_lembretes

            resultado = listar_lembretes()
            hoje = datetime.now().strftime("%Y-%m-%d")
            return [
                lem for lem in resultado.get("lembretes", [])
                if str(lem.get("proximo_disparo") or "").startswith(hoje)
            ]
        except Exception:
            return []

    def _nota_espontanea(self) -> dict | None:
        """Uma nota recente do caderno para o BMO recordar sozinho."""
        try:
            from .hands.notes import nota_espontanea

            return nota_espontanea(excluir=self.motor_proativo.ultima_nota)
        except Exception:
            return None

    def run(self) -> None:
        try:
            self._preparar()
        except Exception as e:
            self.estado.mudar("erro", detalhe=str(e))
            _avisar_usuario(
                "BMO não conseguiu iniciar",
                f"{e}\n\nConfigure o arquivo .env (veja o .env.example) e abra o BMO de novo.",
            )
            return

        # Tela 2 do esboço: boot se dissolve no rosto e o BMO se apresenta
        from .face import DURACAO_APRESENTACAO

        self.estado.mudar("apresentacao")
        time.sleep(DURACAO_APRESENTACAO + 0.2)
        self._falar("Oi, sou o Bimo!", emocao="feliz")
        self.estado.mudar("standby", emocao="feliz")

        # "vida própria": só sobe o laço de fundo se a proatividade estiver ligada
        if self.motor_proativo.ativo and self.boca is not None:
            self._laco_proativo = LacoProatividade(self)
            self._laco_proativo.start()

        from .ears import Ouvidos

        while not self.encerrar.is_set():
            try:
                if isinstance(self.ouvidos, Ouvidos):
                    # motor Google: precisa do microfone aberto no ciclo todo
                    with self.ouvidos.abrir_microfone() as fonte:
                        self.ouvidos.calibrar(fonte)
                        while not self.encerrar.is_set():
                            self._ciclo(
                                lambda: self.ouvidos.esperar_wake_word(fonte),
                                lambda t: self.ouvidos.ouvir_comando(fonte, timeout=t),
                            )
                else:
                    # motores locais (Vosk/Porcupine)
                    self._ciclo(
                        self.ouvidos.esperar_wake_word,
                        self.ouvidos.ouvir_comando,
                    )
            except Exception as e:
                self.estado.mudar("erro", detalhe=str(e)[:120])
                time.sleep(4.0)


class _DemoDeEstados(threading.Thread):
    """BMO_DEMO=1: percorre todos os estados do rosto (demonstração/validação)."""

    ROTEIRO = [
        ("boot", None, 3), ("apresentacao", None, 2), ("standby", None, 3), ("ouvindo", None, 3),
        ("processando", None, 3), ("falando", "feliz", 3),
        ("standby", "feliz", 3), ("falando", "triste", 3),
        ("standby", "surpreso", 3), ("erro", None, 3), ("standby", None, 3),
    ]

    def __init__(self, estado: EstadoBMO):
        super().__init__(daemon=True, name="bmo-demo")
        self.estado = estado
        self.encerrar = threading.Event()

    def run(self) -> None:
        for modo, emocao, segundos in self.ROTEIRO:
            if self.encerrar.is_set():
                return
            self.estado.mudar(modo, emocao=emocao)
            time.sleep(segundos)


def _caminho_env():
    from .paths import caminho_env

    return caminho_env()


def _abrir_configuracoes_externas() -> None:
    """Lança a tela de configurações como processo separado (Tkinter e
    pygame não dividem bem o mesmo processo)."""
    import subprocess
    import sys

    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable, "--config"], close_fds=True)
    else:
        subprocess.Popen(
            [sys.executable, str(_caminho_env().parent / "main.py"), "--config"],
            close_fds=True,
        )


def _reiniciar_app() -> None:
    """Reabre o BMO (para aplicar configurações novas) e encerra este processo."""
    import subprocess
    import sys

    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable], close_fds=True)
    else:
        subprocess.Popen(
            [sys.executable, str(_caminho_env().parent / "main.py")], close_fds=True
        )


def executar_app() -> None:
    """Sobe a janela flutuante com o assistente completo."""
    from .janela import JanelaBMO  # import local: exige ambiente gráfico

    estado = EstadoBMO()
    if os.getenv("BMO_DEMO"):
        assistente = _DemoDeEstados(estado)
    else:
        assistente = AssistenteDeVoz(estado)
    assistente.start()

    janela = JanelaBMO()
    fb = FrameBuffer()
    rosto = RostoBMO(fb)
    frame = 0

    env = _caminho_env()
    mtime_env = env.stat().st_mtime if env.exists() else 0
    reiniciar = False

    try:
        while janela.processar_eventos():
            if janela.abrir_config_pedido:
                janela.abrir_config_pedido = False
                _abrir_configuracoes_externas()

            desenhar_estado(rosto, estado, frame)
            # o medidor entra DEPOIS do rosto: desenhar_estado limpa o frame
            fracao = fracao_restante()
            if _mostrar_medidor(estado.ler()[0], fracao):
                desenhar_medidor_cacheado(
                    fb, MEDIDOR_CX, MEDIDOR_CY, MEDIDOR_RAIO, fracao,
                    segmentos=6, espessura=2,
                )
            janela.render(fb)
            frame += 1
            if frame % 300 == 0:
                janela.fixar_no_topo()  # reafirma o topmost periodicamente
            if frame % 60 == 0 and env.exists():  # configurações mudaram?
                novo_mtime = env.stat().st_mtime
                if mtime_env and novo_mtime != mtime_env:
                    reiniciar = True
                    break
                mtime_env = novo_mtime
    finally:
        assistente.encerrar.set()
        janela.fechar()
        if reiniciar:
            _reiniciar_app()
