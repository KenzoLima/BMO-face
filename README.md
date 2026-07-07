# BMO — Assistente Virtual Pessoal 🎮

Assistente de voz para Windows inspirado no BMO de Hora de Aventura.
Ele mora numa janelinha flutuante na sua área de trabalho, escuta a
palavra **"Bimo"** sem gastar internet, executa ações reais no computador
e responde falando — com o rosto reagindo a cada fase.

## O que ele faz

- **Escuta local**: a espera pela wake word roda offline (Vosk/Porcupine),
  sem custo por requisição; só o comando após o gatilho usa a API do Google.
- **Age no PC**: abre aplicativos, busca arquivos, roda comandos no
  PowerShell (com bloqueio de comandos destrutivos), pesquisa na internet
  e agenda lembretes com notificação nativa do Windows.
- **Cérebro com fallback**: Gemini (padrão) com fallback automático para
  Groq — function calling nativo nos dois.
- **Rosto animado**: janela 256x128 sempre no topo, arrastável, com estados
  de standby, ouvindo, processando, falando, emoções e erro.

## Rodando do código

```powershell
# 1. dependências (uma vez)
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# 2. configuração (uma vez): o .env é criado sozinho na primeira execução;
#    edite e preencha GOOGLE_API_KEY (grátis em https://aistudio.google.com/apikey)

# 3. rodar
.\.venv\Scripts\python.exe main.py           # janela flutuante + voz (padrão)
.\.venv\Scripts\python.exe main.py --voz     # voz no terminal, sem janela
.\.venv\Scripts\python.exe main.py --texto   # chat de texto (sem microfone)
```

Fale **"Bimo"** e aguarde o "Pode falar!" — aí é só pedir:
*"abre a calculadora"*, *"quanto espaço tem no disco?"*, *"vai chover amanhã?"*,
*"me lembra de beber água às 15h"*.

## Instalando (usuário final)

Use o instalador gerado em `instalador/saida/` (veja abaixo como gerá-lo).
Pré-requisitos da máquina:

- Windows 10/11 de 64 bits, microfone e alto-falantes;
- uma chave (grátis) do Gemini em https://aistudio.google.com/apikey —
  o BMO cria o arquivo `.env` na pasta de instalação no primeiro uso e
  avisa onde colar a chave;
- internet para o cérebro (LLM), a fala (TTS) e a transcrição de comandos.
  A espera pela wake word funciona offline.

## Gerando o executável e o instalador

```powershell
.\.venv\Scripts\pip install pyinstaller
powershell -ExecutionPolicy Bypass -File instalador\build.ps1
# resultado: dist\BMO\ (app) e instalador em instalador\saida\
```

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -q         # suíte completa
.\.venv\Scripts\python.exe tests\calibrar_wake_word.py  # precisão da wake word
```

## Arquitetura

```
main.py            entrada: janela (padrão), --voz, --texto
bmo/
├── app.py         orquestra: janela (thread principal) + voz (worker)
├── janela.py      janela flutuante topmost, arrastável
├── face.py        rosto OLED 128x64: estados e emoções
├── ears.py        escuta: wake word local (Vosk/Porcupine) + STT Google
├── mouth.py       fala: edge-tts com voz do BMO ("Bímo")
├── brain/         cérebro: Gemini/Groq + loop de function calling
└── hands/         ferramentas: apps, arquivos, shell, internet, lembretes
modelos/           modelo Vosk pt-BR + params do Porcupine
```
