"""Ferramentas: caderno do BMO — memória de longo prazo em Markdown (Obsidian).

O caderno é uma pasta de arquivos .md compatível com o Obsidian: aponte
``BMO_VAULT`` no .env para (uma subpasta d)o seu vault e as anotações do BMO
aparecem lá, linkáveis e pesquisáveis. Sem Obsidian também funciona — são
só arquivos de texto.

Economia de requisições: TODA a leitura/busca é local (disco). A API só é
usada no fluxo normal do agente; a recordação automática
(``memorias_relevantes``) anexa trechos à requisição que já ia acontecer.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .registry import ferramenta

MAX_NOTAS_CONSULTA = 5
MAX_TAMANHO_ARQUIVO = 200_000  # ignora .md gigantes (exportações etc.)
TAMANHO_TRECHO = 300

# Recordação automática (injetada na requisição que já ia acontecer)
MAX_MEMORIAS_AUTO = 2
PONTUACAO_MINIMA_AUTO = 3.0

_STOPWORDS = {
    "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "em",
    "no", "na", "nos", "nas", "por", "para", "pra", "com", "sem", "sobre",
    "que", "qual", "quais", "quando", "onde", "como", "quem", "meu", "minha",
    "seu", "sua", "ele", "ela", "isso", "esse", "essa", "este", "esta",
    "bimo", "bmo", "você", "voce", "não", "nao", "sim", "mais", "muito",
    "anotei", "anotou", "anota", "lembra", "lembre", "sabe", "fala", "diga",
}


def _dir_caderno() -> Path:
    caminho = os.getenv("BMO_VAULT")
    if caminho:
        return Path(caminho).expanduser()
    return Path.home() / "Documents" / "BMO Caderno"


def _garantir_caderno() -> Path:
    caderno = _dir_caderno()
    caderno.mkdir(parents=True, exist_ok=True)
    return caderno


def _slug(texto: str, max_len: int = 40) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^\w\s-]", "", texto).strip()
    texto = re.sub(r"[\s_]+", "-", texto).lower()
    return texto[:max_len].rstrip("-") or "nota"


def _normalizar(texto: str) -> str:
    """minúsculas + sem acentos — buscas encontram 'aniversário' ~ 'aniversario'."""
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def _palavras_chave(texto: str) -> list[str]:
    palavras = re.findall(r"\w+", _normalizar(texto))
    return [p for p in palavras if len(p) >= 3 and p not in _STOPWORDS]


def _iterar_notas(caderno: Path):
    if not caderno.is_dir():
        return
    for arquivo in caderno.rglob("*.md"):
        if ".obsidian" in arquivo.parts or ".trash" in arquivo.parts:
            continue
        try:
            if arquivo.stat().st_size > MAX_TAMANHO_ARQUIVO:
                continue
            yield arquivo, arquivo.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue


def _trecho(conteudo: str, palavra: str) -> str:
    pos = _normalizar(conteudo).find(palavra)
    if pos < 0:
        pos = 0
    inicio = max(0, pos - TAMANHO_TRECHO // 3)
    trecho = conteudo[inicio : inicio + TAMANHO_TRECHO].strip()
    return ("..." if inicio > 0 else "") + trecho


def _buscar(termo: str, max_resultados: int) -> list[dict]:
    """Busca local por palavras-chave; título vale mais que corpo."""
    palavras = _palavras_chave(termo) or [_normalizar(termo).strip()]
    resultados = []
    for arquivo, conteudo in _iterar_notas(_dir_caderno()):
        texto = _normalizar(conteudo)
        nome = _normalizar(arquivo.stem)
        pontos = 0.0
        primeira_palavra = None
        for p in palavras:
            no_corpo = texto.count(p)
            no_titulo = nome.count(p)
            if (no_corpo or no_titulo) and primeira_palavra is None:
                primeira_palavra = p
            pontos += min(no_corpo, 3) + no_titulo * 5
        if pontos > 0:
            resultados.append(
                {
                    "nota": arquivo.stem,
                    "caminho": str(arquivo),
                    "pontuacao": pontos,
                    "trecho": _trecho(conteudo, primeira_palavra or palavras[0]),
                }
            )
    resultados.sort(key=lambda r: r["pontuacao"], reverse=True)
    return resultados[:max_resultados]


# ─── Ferramentas expostas ao LLM ─────────────────────────────────────────────


@ferramenta(
    nome="anotar",
    descricao=(
        "Guarda uma informação no caderno permanente do usuário (arquivos "
        "Markdown, compatível com Obsidian). Use quando o usuário pedir para "
        "anotar, lembrar ou guardar algo para depois."
    ),
    parametros={
        "type": "object",
        "properties": {
            "conteudo": {
                "type": "string",
                "description": "O que anotar, já redigido de forma clara.",
            },
            "titulo": {
                "type": "string",
                "description": "Título curto da nota (opcional).",
            },
        },
        "required": ["conteudo"],
    },
)
def anotar(conteudo: str, titulo: str | None = None) -> dict:
    conteudo = conteudo.strip()
    if not conteudo:
        return {"sucesso": False, "erro": "Nada para anotar."}

    caderno = _garantir_caderno()
    agora = datetime.now()
    titulo = (titulo or conteudo.split("\n")[0][:40]).strip()
    arquivo = caderno / f"{agora:%Y-%m-%d} {_slug(titulo)}.md"
    if arquivo.exists():  # mesma nota no mesmo dia → acrescenta
        texto = arquivo.read_text(encoding="utf-8") + f"\n- ({agora:%H:%M}) {conteudo}\n"
    else:
        texto = (
            f"---\ncriado: {agora:%Y-%m-%d %H:%M}\norigem: BMO\n---\n\n"
            f"# {titulo}\n\n- ({agora:%H:%M}) {conteudo}\n"
        )
    arquivo.write_text(texto, encoding="utf-8")
    return {
        "sucesso": True,
        "mensagem": f"Anotado em '{arquivo.stem}'.",
        "caminho": str(arquivo),
    }


@ferramenta(
    nome="consultar_anotacoes",
    descricao=(
        "Pesquisa no caderno permanente do usuário (busca local, sem custo). "
        "Use quando o usuário perguntar sobre algo que pode ter sido anotado "
        "antes: compromissos, preferências, fatos pessoais, decisões."
    ),
    parametros={
        "type": "object",
        "properties": {
            "termo": {
                "type": "string",
                "description": "Palavras-chave do que procurar.",
            },
        },
        "required": ["termo"],
    },
)
def consultar_anotacoes(termo: str) -> dict:
    termo = termo.strip()
    if not termo:
        return {"sucesso": False, "erro": "Termo de busca vazio."}
    resultados = _buscar(termo, MAX_NOTAS_CONSULTA)
    if not resultados:
        return {
            "sucesso": True,
            "total": 0,
            "resultados": [],
            "aviso": "Nenhuma anotação encontrada sobre isso.",
        }
    return {"sucesso": True, "total": len(resultados), "resultados": resultados}


# ─── Recordação automática (zero requisições extras) ─────────────────────────


def memorias_relevantes(texto: str) -> str:
    """Trechos do caderno relacionados à fala do usuário, para anexar à
    requisição que JÁ vai acontecer. Busca 100% local; devolve string vazia
    quando nada é relevante o bastante (o caso comum)."""
    try:
        candidatos = [
            r for r in _buscar(texto, MAX_MEMORIAS_AUTO)
            if r["pontuacao"] >= PONTUACAO_MINIMA_AUTO
        ]
    except Exception:
        return ""
    if not candidatos:
        return ""
    return "\n".join(f"- [{r['nota']}] {r['trecho']}" for r in candidatos)
