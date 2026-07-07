# BMO — Assistente Virtual Pessoal 🎮

Assistente de voz para Windows inspirado no BMO de Hora de Aventura.
Ele mora numa janelinha flutuante na sua área de trabalho, escuta a
palavra **"Bimo"** sem gastar internet, executa ações reais no computador
e responde falando — com o rosto reagindo a cada fase.

---

## 🚀 Instalação para amigos (passo a passo)

Sem código, sem terminal. Leva uns 5 minutos.

### 1. Instale o BMO

1. Pegue o arquivo **`BMO-Setup-1.0.0.exe`** (te mando por WhatsApp/Drive).
2. Dê **dois cliques** nele.
3. Se o Windows mostrar uma tela azul *"O Windows protegeu o seu PC"*, clique em
   **"Mais informações" → "Executar mesmo assim"** (isso aparece só porque o
   instalador não é assinado; é seguro).
4. Siga o assistente: **Avançar → Avançar → Instalar**. Pode marcar
   *"Criar atalho na Área de Trabalho"*.
5. No fim, deixe marcado **"Abrir o BMO agora"** e clique em **Concluir**.

> Não precisa ser administrador — o BMO instala só para o seu usuário.

### 2. Pegue sua chave grátis do Gemini

Na primeira vez que o BMO abre, aparece a tela **"Oi! Vamos me configurar?"**.

1. Clique no botão que abre o **Google AI Studio** (ou acesse
   👉 https://aistudio.google.com/apikey ).
2. Entre com uma conta Google e clique em **"Create API key"** / *"Criar chave de API"*.
3. **Copie** a chave gerada (uma linha grande de letras e números).
4. Volte ao BMO, **cole a chave** no campo *"Chave Gemini"* e clique em **Salvar**.

> A chave é grátis e pessoal. Ela fica guardada só no seu PC (num arquivo `.env`
> na pasta do BMO) — ninguém mais tem acesso.

### 3. Fale com o BMO

- Diga **"Bimo"** e espere o *"Pode falar!"*.
- Depois é só pedir, por exemplo:
  - *"abre a calculadora"*
  - *"quanto espaço tem no disco?"*
  - *"vai chover amanhã?"*
  - *"me lembra de beber água às 3 da tarde"*
  - *"anota que a senha do wifi é 12345"*
- Para encerrar o assunto, diga **"obrigado"**, **"só isso"** ou fique em silêncio.
  Depois é só chamar *"Bimo"* de novo.

### O que o seu amigo precisa ter

- **Windows 10 ou 11** (64 bits);
- **microfone e alto-falantes/fones** funcionando;
- **internet** — para o BMO pensar (LLM), falar (voz) e entender os comandos.
  *(Só a espera pela palavra "Bimo" funciona offline.)*

### Desinstalar

Menu Iniciar → procure **BMO** → *Desinstalar*, ou pelo
**Configurações do Windows → Aplicativos**. Simples assim.

---

## O que ele faz

- **Escuta local**: a espera pela wake word roda offline (Vosk/Porcupine),
  sem custo por requisição; só o comando após o gatilho usa a API do Google.
- **Age no PC**: abre aplicativos, busca arquivos, roda comandos no
  PowerShell (com bloqueio de comandos destrutivos), pesquisa na internet
  e agenda lembretes com notificação nativa do Windows.
- **Cérebro com fallback**: Gemini (padrão) com fallback automático para
  Groq — function calling nativo nos dois.
- **Memória de longo prazo**: caderno em Markdown compatível com Obsidian
  (aponte `BMO_VAULT` para seu vault). "Bimo, anota que..." vira nota; em
  conversas futuras ele recorda sozinho — a busca é 100% local, sem gastar
  requisições de API.
- **Modo conversa**: uma wake word, vários turnos; encerre com "obrigado",
  "só isso" ou silêncio.
- **Rosto animado**: janela 256x128 sempre no topo, arrastável, com estados
  de standby, ouvindo, processando, falando, emoções e erro.

---

## 👩‍💻 Para desenvolvedores

### Rodando do código

```powershell
# 1. dependências (uma vez)
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# 2. configuração (uma vez): na primeira execução abre a tela de
#    configuração; cole a GOOGLE_API_KEY (grátis em
#    https://aistudio.google.com/apikey). O .env é criado sozinho.

# 3. rodar
.\.venv\Scripts\python.exe main.py           # janela flutuante + voz (padrão)
.\.venv\Scripts\python.exe main.py --voz     # voz no terminal, sem janela
.\.venv\Scripts\python.exe main.py --texto   # chat de texto (sem microfone)
.\.venv\Scripts\python.exe main.py --config  # abre só a tela de configurações
```

### Gerando o executável e o instalador

```powershell
.\.venv\Scripts\pip install pyinstaller
powershell -ExecutionPolicy Bypass -File instalador\build.ps1
# resultado: dist\BMO\ (app) e instalador em instalador\saida\BMO-Setup-<versao>.exe
```

O `build.ps1` gera o ícone, valida o Tkinter (tela de configuração), empacota
com o PyInstaller usando **caminhos absolutos** para `--add-data`/`--icon`
(necessário porque o `--specpath` fica numa subpasta com timestamp) e, por fim,
compila o instalador com o Inno Setup 6.

### Testes

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -q          # suíte completa
.\.venv\Scripts\python.exe tests\calibrar_wake_word.py  # precisão da wake word
```

### Arquitetura

```
main.py            entrada: janela (padrão), --voz, --texto, --config
bmo/
├── app.py         orquestra: janela (thread principal) + voz (worker)
├── janela.py      janela flutuante topmost, arrastável
├── face.py        rosto OLED 128x64: estados e emoções
├── ears.py        escuta: wake word local (Vosk/Porcupine) + STT Google
├── mouth.py       fala: edge-tts com voz do BMO ("Bímo") + lip sync
├── config_ui.py   tela de configuração / boas-vindas (Tkinter)
├── brain/         cérebro: Gemini/Groq + loop de function calling
└── hands/         ferramentas: apps, arquivos, shell, internet, lembretes, notas
modelos/           modelo Vosk pt-BR + params do Porcupine
instalador/        build.ps1, bmo.iss (Inno Setup), gerar_icone.py
```

### Configuração avançada

Veja [`.env.example`](.env.example) para todas as opções: provedor e modelos do
cérebro, voz (velocidade/tom), motores de wake word (Porcupine/Vosk), timeout do
modo conversa e a pasta do caderno (`BMO_VAULT`, para integrar ao Obsidian).
