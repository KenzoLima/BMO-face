# BMO — Assistente Virtual Pessoal

Assistente de voz para Windows inspirado no BMO de Hora de Aventura.
Ele mora numa janelinha flutuante na sua área de trabalho, escuta a
palavra **"Bimo"** sem gastar internet, executa ações reais no computador
e responde falando — com o rosto reagindo a cada fase.

---

## 🚀 Instalação para amigos (passo a passo)

Sem código, sem terminal. Leva uns 5 minutos.

### 1. Instale o BMO

1. Pegue o arquivo **`BMO-Setup-1.0.0.exe`**.
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

> A chave é grátis e pessoal. Ela fica guardada só no seu usuário do Windows
> (`%APPDATA%\BMO\.env`) — o instalador não leva a chave de ninguém.

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
- **Fala enquanto pensa**: a resposta é falada frase a frase, conforme o
  modelo escreve — em vez de esperar o texto inteiro e só então sintetizar
  o áudio. Corta ~2,8s da espera até a primeira palavra.
- **Vida própria**: quando ocioso, o BMO toma pequenas iniciativas — bom dia
  com os lembretes do dia, sugestão de pausa e lembranças do caderno. Nunca
  corta uma conversa, e é desligável na tela de configuração.
- **Rosto animado**: janela 256x128 sempre no topo, arrastável, com estados
  de standby, ouvindo, **pesquisando**, processando, falando, emoções e erro.
  A tela de pesquisa mostra a lupa e a barra enchendo enquanto uma ferramenta
  lenta trabalha, e fecha com a barra cheia quando termina.
- **Medidor de requisições**: um velocímetro no canto do rosto que começa
  cheio e vai esvaziando conforme o BMO gasta chamadas ao LLM. Conta chamadas
  de API, não falas — o loop de ferramentas pode gastar várias por comando.
- **Dispositivos de áudio**: escolha o microfone e a saída de som na tela de
  configuração, com teste embutido para cada um.

---

## 🔒 Segurança

O BMO executa ações reais no seu computador a partir de texto escolhido por um
LLM — que, por sua vez, lê resultados de busca da internet. Todo argumento de
ferramenta é tratado como **não confiável**:

- **Comandos destrutivos são recusados** antes de chegar ao shell (apagar
  recursivamente à força, desligar, formatar, `Invoke-Expression`, comandos
  em Base64, matar processos, mexer no Defender, criar tarefas agendadas).
- **Nada de texto interpolado em linha de comando**: o texto dos lembretes vai
  em Base64 até o script do toast, e todo valor interpolado passa por um
  literal PowerShell com aspas devidamente escapadas.
- **Toda ferramenta tem teto de tempo** — uma busca pendurada não trava mais
  o BMO. Ela desiste e avisa o modelo.
- **A chave de API fica só no seu usuário** (`%APPDATA%\BMO\.env`), nunca é
  impressa em log nem versionada.

A lista de bloqueio do shell é uma barreira, não uma prova: se você não
confia no ambiente, deixe o BMO sem a ferramenta de shell.

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
├── medidor.py     velocímetro de requisições (desenho puro, 1-bit)
├── ears.py        escuta: wake word local (Vosk/Porcupine) + STT Google
├── mouth.py       fala: edge-tts, lip sync e streaming frase a frase
├── audio.py       escolha do microfone e da saída de som
├── consumo.py     contador de requisições ao LLM (fonte do medidor)
├── proatividade.py "vida própria": briefing, pausas, lembranças
├── paths.py       caminhos do .env e dos dados do usuário
├── config_ui.py   tela de configuração / boas-vindas (Tkinter)
├── brain/         cérebro: Gemini/Groq + loop de function calling
└── hands/         ferramentas: apps, arquivos, shell, internet, lembretes, notas
modelos/           modelo Vosk pt-BR + params do Porcupine
instalador/        build.ps1, bmo.iss (Inno Setup), gerar_icone.py
```

### Configuração avançada

Veja [`.env.example`](.env.example) para todas as opções: provedor e modelos do
cérebro, voz (velocidade/tom), motores de wake word (Porcupine/Vosk), timeout do
modo conversa, a pasta do caderno (`BMO_VAULT`, para integrar ao Obsidian),
proatividade, dispositivos de áudio e o medidor de requisições.

Alguns que valem destaque:

| Variável | Para quê |
|---|---|
| `BMO_LIMITE_REQUISICOES_DIA` | Escala do medidor — ajuste ao teto do seu plano |
| `BMO_MEDIDOR` | `auto` (só com pouco saldo), `sempre` ou `nunca` |
| `BMO_AUDIO_ENTRADA` / `BMO_AUDIO_SAIDA` | Microfone e saída (guardados por nome) |
| `BMO_ACK` | O que ele fala ao ouvir "Bimo" (curto = responde antes) |
| `BMO_PROATIVIDADE` | Liga/desliga a vida própria |
| `BMO_STT_SEM_GOOGLE` | Transcrição 100% local (exige `faster-whisper`) |
