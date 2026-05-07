# BMO Virtual Friend --> Python 3.12.8

Rosto animado no estilo **BMO** de *Hora de Aventura*, projetado para rodar
em um display OLED SSD1306 de 0.96".

```
┌───────────────────z──────┐
│  ╔══════════════════z═╗  │
│  ║                 z  ║  │
│  ║  (  )       (  ) z ║  │
│  ║        ────        ║  │
│  ║                    ║  │
│  ╚════════════════════╝  │
└                          ┘
        BMO Virtual Friend
```

## Arquivos

| Arquivo        | Função |
|----------------|--------|
| `bmo_face.py`  | Toda a lógica de desenho + simulador Pygame |
| `bmo_oled.py`  | Port para o display OLED físico (SSD1306) |

## Instalação

### Teste local (PC)
```bash
pip install pygame
python bmo_face.py
```

### Display real (Esp-32 Wroom)
```bash
pip install luma.oled pillow
python bmo_oled.py
```

### Display real (CircuitPython / ESP32)
```bash
pip install adafruit-circuitpython-ssd1306
python bmo_oled.py
```

## Expressões disponíveis

| Tecla | Estado     | Animação                                  |
|-------|------------|-------------------------------------------|
| 1     | Idle       | Piscar olhos + cursor terminal            |
| 2     | Feliz      | Olhos `^` + sorriso + bochechas + bounce  |
| 3     | Triste     | Olhos `U` + boca virada + lágrimas        |
| 4     | Sonolento  | Olhos meio fechados + zzz flutuante       |
| 5     | Surpreso   | Olhos redondos + tremor + linhas de choque|
| 6     | Cantando   | Boca oscilando + notas flutuantes         |
| 7     | Wink       | Piscadinha + bochecha                     |
| 8     | Boot       | Barra de progresso + logo BMO             |
| ESC   | —          | Sair                                      |

## Memória de imagem

O `FrameBuffer` espelha exatamente a RAM do SSD1306:

```
128 × 64 pixels × 1 bit/pixel = 8192 bits = 1024 bytes = 1 KB
```

Apenas **1 buffer** é mantido em memória. Não há sprites ou bitmaps
pré-carregados — cada frame é desenhado pixel a pixel com geometria pura,
garantindo o menor uso de RAM possível.

## Ligação I2C (Raspberry Pi)

```
Display SSD1306   →   Raspberry Pi
VCC               →   3.3V  (pino 1)
GND               →   GND   (pino 6)
SDA               →   GPIO2 (pino 3)
SCL               →   GPIO3 (pino 5)
```

## Cores do BMO

| Elemento      | Hex       | RGB           |
|---------------|-----------|---------------|
| Corpo         | `#3ec9a7` | (62, 201, 167)|
| Face/Tela     | `#2aa88a` | (42, 168, 138)|
| Branco olho   | `#dff5ec` | (223, 245, 236)|
| Pupila        | `#0a2820` | (10, 40, 32)  |
| Boca          | `#1a6650` | (26, 102, 80) |
| Borda         | `#1a7a5a` | (26, 122, 90) |
| Bochechas     | `#5ad4b0` | (90, 212, 176)|

> O display SSD1306 de 0.96" é monocromático (1-bit).
> As cores são usadas apenas na simulação Pygame no PC.
> Para display colorido, use um SSD1331 ou ST7735 e ajuste o driver.
