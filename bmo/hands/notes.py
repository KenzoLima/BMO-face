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
from typing import NamedTuple

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


# Marcas de acento que o NFKD separa das letras (é → e + U+0301).
_RE_ACENTOS = re.compile(r"[̀-ͯ]")


def _normalizar(texto: str) -> str:
    """minúsculas + sem acentos — buscas encontram 'aniversário' ~ 'aniversario'.

    Roda sobre o caderno inteiro a cada busca, então o caminho importa: o
    ``isascii()`` resolve de graça o texto sem acento nenhum, e o regex faz o
    resto em C — bem mais rápido que filtrar caractere a caractere em Python.
    """
    if texto.isascii():  # caso comum e barato: não há o que decompor
        return texto.lower()
    return _RE_ACENTOS.sub("", unicodedata.normalize("NFKD", texto)).lower()


def _palavras_chave(texto: str) -> list[str]:
    palavras = re.findall(r"\w+", _normalizar(texto))
    return [p for p in palavras if len(p) >= 3 and p not in _STOPWORDS]


class Nota(NamedTuple):
    """Uma nota do caderno já lida e preparada para busca."""

    caminho: Path
    mtime: float
    conteudo: str           # texto original, como será mostrado ao usuário
    normalizado: str        # conteúdo sem acentos e em minúsculas (para casar)
    nome_normalizado: str   # idem para o nome do arquivo


# Cache das notas já lidas e normalizadas, por caminho.
# Sem ele, cada turno de conversa relia e renormalizava o caderno inteiro —
# num vault Obsidian de verdade isso vira mais de um segundo de latência ANTES
# da requisição ao LLM. A chave (mtime, tamanho) se invalida sozinha quando a
# nota muda no disco, então editar no Obsidian aparece na busca seguinte.
_CACHE_NOTAS: dict[Path, tuple[tuple[float, int], Nota]] = {}
MAX_NOTAS_EM_CACHE = 5_000


def _iterar_notas(caderno: Path):
    """Percorre o caderno devolvendo ``Nota``s (do cache quando não mudaram)."""
    if not caderno.is_dir():
        return
    if len(_CACHE_NOTAS) > MAX_NOTAS_EM_CACHE:
        _CACHE_NOTAS.clear()  # limite simples: vault gigante não vira vazamento
    for arquivo in caderno.rglob("*.md"):
        if ".obsidian" in arquivo.parts or ".trash" in arquivo.parts:
            continue
        try:
            info = arquivo.stat()
            if info.st_size > MAX_TAMANHO_ARQUIVO:
                continue
            versao = (info.st_mtime, info.st_size)
            em_cache = _CACHE_NOTAS.get(arquivo)
            if em_cache is not None and em_cache[0] == versao:
                yield em_cache[1]
                continue
            conteudo = arquivo.read_text(encoding="utf-8", errors="replace")
            nota = Nota(
                arquivo,
                info.st_mtime,
                conteudo,
                _normalizar(conteudo),
                _normalizar(arquivo.stem),
            )
            _CACHE_NOTAS[arquivo] = (versao, nota)
            yield nota
        except OSError:
            continue


def _trecho(conteudo: str, normalizado: str, palavra: str) -> str:
    """Recorte do conteúdo em volta de ``palavra`` (procurada no normalizado)."""
    pos = normalizado.find(palavra)
    if pos < 0:
        pos = 0
    inicio = max(0, pos - TAMANHO_TRECHO // 3)
    trecho = conteudo[inicio : inicio + TAMANHO_TRECHO].strip()
    return ("..." if inicio > 0 else "") + trecho


def _buscar(termo: str, max_resultados: int) -> list[dict]:
    """Busca local por palavras-chave; título vale mais que corpo."""
    palavras = _palavras_chave(termo) or [_normalizar(termo).strip()]
    resultados = []
    for nota in _iterar_notas(_dir_caderno()):
        pontos = 0.0
        primeira_palavra = None
        for p in palavras:
            no_corpo = nota.normalizado.count(p)
            no_titulo = nota.nome_normalizado.count(p)
            if (no_corpo or no_titulo) and primeira_palavra is None:
                primeira_palavra = p
            pontos += min(no_corpo, 3) + no_titulo * 5
        if pontos > 0:
            resultados.append(
                {
                    "nota": nota.caminho.stem,
                    "caminho": str(nota.caminho),
                    "pontuacao": pontos,
                    "trecho": _trecho(
                        nota.conteudo,
                        nota.normalizado,
                        primeira_palavra or palavras[0],
                    ),
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


def nota_espontanea(excluir: str | None = None) -> dict | None:
    """Uma nota recente do caderno para o BMO recordar sozinho (proatividade).

    Escolhe a anotação modificada mais recentemente (fora ``excluir``, para
    não repetir a última recordada) e devolve ``{"nota", "trecho"}`` ou None.
    Busca 100% local; nunca levanta exceção para não atrapalhar o laço."""
    try:
        candidatos = [
            nota for nota in _iterar_notas(_dir_caderno())
            if nota.caminho.stem != excluir and nota.conteudo.strip()
        ]
        if not candidatos:
            return None
        nota = max(candidatos, key=lambda n: n.mtime)
        return {
            "nota": nota.caminho.stem,
            "trecho": _trecho(
                nota.conteudo.strip(),
                nota.normalizado.strip(),
                nota.nome_normalizado.split(" ")[0],
            ),
        }
    except Exception:
        return None


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
