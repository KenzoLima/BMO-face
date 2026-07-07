"""BMO — Agente pessoal e assistente virtual de sistema operacional.

Pacote principal, organizado em módulos independentes:

- ``bmo.hands``  → Execução física: ferramentas do OS expostas ao LLM (Tool Use)
- ``bmo.ears``   → Percepção: captura de voz e transcrição (STT)      [Fase 2]
- ``bmo.brain``  → Raciocínio: LLM, persona e loop do agente          [Fase 3]
- ``bmo.mouth``  → Resposta: síntese de voz (TTS)                     [Fase 4]
"""
