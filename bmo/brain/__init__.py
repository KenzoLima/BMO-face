"""Cérebro do agente — LLM, persona e loop de Tool Use.

Uso:
    from bmo.brain import Cerebro
    cerebro = Cerebro()
    print(cerebro.responder("abre a calculadora"))
"""

from .agent import Cerebro

__all__ = ["Cerebro"]
