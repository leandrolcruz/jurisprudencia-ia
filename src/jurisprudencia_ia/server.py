"""
MCP Server: Jurisprudência IA

Busca SEMÂNTICA de jurisprudência via API não documentada do
https://www.jurisprudenciaia.com.br/ (Next.js/Vercel). Sem auth, sem
CAPTCHA, sem cookie — POST JSON puro.

Endpoints (engenharia reversa 15/07/2026):
- POST /api/tribunais/{slug}/search   body: {query, from, to, relator}
- POST /api/tribunais/{slug}/similar  body: {texto, excludeId}

A busca é VETORIAL (embedding + rerank via LLM): NÃO existe sintaxe
booleana — a "query" ideal é a tese descrita em linguagem natural,
como se explicasse o caso a um colega. Filtros estruturados: período
(from/to, ISO yyyy-mm-dd) e relator (substring do nome).

STF/STJ retornam, além dos acórdãos, buckets de precedentes
qualificados relacionados semanticamente: repetitivos (com tese
firmada), súmulas, PUIL e IACs — unificados em `reranked_results`
com `__kind` e `rerank_score`.

Seção INFORMATIVOS (v0.2.0): o site também publica os informativos
oficiais de STF, STJ e TST (2.400+ edições, 32.000+ julgados,
atualização diária) com análise editorial própria (texto, PDF e
podcast). Não há API JSON — as páginas são server-rendered:
- GET /informativos/{trib}                (índice de edições)
- GET /informativos/{trib}/{numero}       (edição + análise editorial)
- GET /informativos/busca?q=&tribunal=    (busca nos julgados)

Seção RAG + utilidades (v0.3.0, engenharia reversa 04/08/2026):
- POST /api/chat-jurisprudencia/session   {tribunalSelectionMode, tribunaisPermitidos}
- POST /api/chat-jurisprudencia           (SSE, protocolo AI SDK) → resposta fundamentada
- GET  /api/chat-jurisprudencia/registry?chatId=  → precedentes citados
- POST /api/extrair-temas                 {texto ≥200} → temas pesquisáveis
- GET  /api/jurisprudencia-link?tribunal=&id=      → link oficial por id
- GET  /api/tribunais/{slug}/integra/{id} → inteiro teor (só tjmrs/tjmsp/tjrn)

Tools:
- buscar_jurisprudencia_ia: retorna XML estruturado
- buscar_similares_ia: busca por semelhança a partir de texto livre (XML)
- gerar_relatorio_ia: retorna Markdown formatado
- listar_tribunais_ia: lista os 98 tribunais suportados (slugs)
- buscar_informativos: busca nos informativos STF/STJ/TST (Markdown)
- obter_informativo: edição completa com análise editorial (Markdown)
- listar_informativos: últimas edições de um tribunal (Markdown)
- perguntar_jurisprudencia_ia: chat RAG — resposta fundamentada + fontes (Markdown)
- extrair_temas_ia: extrai temas pesquisáveis de um texto (Markdown)
- resolver_link_ia: resolve o link oficial de um julgado por id
- obter_inteiro_teor_ia: inteiro teor (texto onde a API expõe; senão, link)
"""

import json
import re
import uuid
from typing import Optional
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("jurisprudencia-ia")

BASE_URL = "https://www.jurisprudenciaia.com.br"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Origin": BASE_URL,
    "Referer": BASE_URL + "/",
}

# Registro completo extraído do bundle JS do site (98 tribunais).
TRIBUNAIS = {
    # Superiores
    "stf": ("STF", "Supremo Tribunal Federal", "Superiores"),
    "stj": ("STJ", "Superior Tribunal de Justiça", "Superiores"),
    "tst": ("TST", "Tribunal Superior do Trabalho", "Superiores"),
    "tse": ("TSE", "Tribunal Superior Eleitoral", "Superiores"),
    "stm": ("STM", "Superior Tribunal Militar", "Superiores"),
    # Justiça Federal
    "trf1": ("TRF1", "Tribunal Regional Federal da 1ª Região", "Justiça Federal"),
    "trf2": ("TRF2", "Tribunal Regional Federal da 2ª Região", "Justiça Federal"),
    "trf3": ("TRF3", "Tribunal Regional Federal da 3ª Região", "Justiça Federal"),
    "trf4": ("TRF4", "Tribunal Regional Federal da 4ª Região", "Justiça Federal"),
    "trf5": ("TRF5", "Tribunal Regional Federal da 5ª Região", "Justiça Federal"),
    "trf6": ("TRF6", "Tribunal Regional Federal da 6ª Região", "Justiça Federal"),
    # Justiça Estadual
    "tjac": ("TJAC", "Tribunal de Justiça do Acre", "Justiça Estadual"),
    "tjal": ("TJAL", "Tribunal de Justiça de Alagoas", "Justiça Estadual"),
    "tjam": ("TJAM", "Tribunal de Justiça do Amazonas", "Justiça Estadual"),
    "tjap": ("TJAP", "Tribunal de Justiça do Amapá", "Justiça Estadual"),
    "tjba": ("TJBA", "Tribunal de Justiça da Bahia", "Justiça Estadual"),
    "tjce": ("TJCE", "Tribunal de Justiça do Ceará", "Justiça Estadual"),
    "tjdft": ("TJDFT", "Tribunal de Justiça do DF e Territórios", "Justiça Estadual"),
    "tjes": ("TJES", "Tribunal de Justiça do Espírito Santo", "Justiça Estadual"),
    "tjgo": ("TJGO", "Tribunal de Justiça de Goiás", "Justiça Estadual"),
    "tjma": ("TJMA", "Tribunal de Justiça do Maranhão", "Justiça Estadual"),
    "tjmg": ("TJMG", "Tribunal de Justiça de Minas Gerais", "Justiça Estadual"),
    "tjms": ("TJMS", "Tribunal de Justiça de Mato Grosso do Sul", "Justiça Estadual"),
    "tjmt": ("TJMT", "Tribunal de Justiça de Mato Grosso", "Justiça Estadual"),
    "tjpa": ("TJPA", "Tribunal de Justiça do Pará", "Justiça Estadual"),
    "tjpb": ("TJPB", "Tribunal de Justiça da Paraíba", "Justiça Estadual"),
    "tjpe": ("TJPE", "Tribunal de Justiça de Pernambuco", "Justiça Estadual"),
    "tjpi": ("TJPI", "Tribunal de Justiça do Piauí", "Justiça Estadual"),
    "tjpr": ("TJPR", "Tribunal de Justiça do Paraná", "Justiça Estadual"),
    "tjrj": ("TJRJ", "Tribunal de Justiça do Rio de Janeiro", "Justiça Estadual"),
    "tjrn": ("TJRN", "Tribunal de Justiça do Rio Grande do Norte", "Justiça Estadual"),
    "tjro": ("TJRO", "Tribunal de Justiça de Rondônia", "Justiça Estadual"),
    "tjrr": ("TJRR", "Tribunal de Justiça de Roraima", "Justiça Estadual"),
    "tjrs": ("TJRS", "Tribunal de Justiça do Rio Grande do Sul", "Justiça Estadual"),
    "tjsc": ("TJSC", "Tribunal de Justiça de Santa Catarina", "Justiça Estadual"),
    "tjse": ("TJSE", "Tribunal de Justiça de Sergipe", "Justiça Estadual"),
    "tjsp": ("TJSP", "Tribunal de Justiça de São Paulo", "Justiça Estadual"),
    "tjto": ("TJTO", "Tribunal de Justiça do Tocantins", "Justiça Estadual"),
    # Justiça Militar estadual
    "tjmmg": ("TJMMG", "Tribunal de Justiça Militar de MG", "Justiça Militar"),
    "tjmrs": ("TJMRS", "Tribunal de Justiça Militar do RS", "Justiça Militar"),
    "tjmsp": ("TJMSP", "Tribunal de Justiça Militar de SP", "Justiça Militar"),
    # Justiça do Trabalho
    **{f"trt{n}": (f"TRT{n}", f"Tribunal Regional do Trabalho da {n}ª Região", "Justiça do Trabalho")
       for n in range(1, 25)},
    # Justiça Eleitoral
    **{f"tre{uf}": (f"TRE-{uf.upper()}", f"Tribunal Regional Eleitoral ({uf.upper()})", "Justiça Eleitoral")
       for uf in ["ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms",
                  "mt", "pa", "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc",
                  "se", "sp", "to"]},
    # Tribunais de Contas
    "tcu": ("TCU", "Tribunal de Contas da União", "Tribunais de Contas"),
    "tceba": ("TCE-BA", "Tribunal de Contas da Bahia", "Tribunais de Contas"),
    "tcego": ("TCE-GO", "Tribunal de Contas de Goiás", "Tribunais de Contas"),
    "tcemg": ("TCE-MG", "Tribunal de Contas de Minas Gerais", "Tribunais de Contas"),
    "tcmba": ("TCM-BA", "Tribunal de Contas dos Municípios da Bahia", "Tribunais de Contas"),
    "tcmsp": ("TCM-SP", "Tribunal de Contas do Município de SP", "Tribunais de Contas"),
}


def _fmt_data(iso: Optional[str]) -> str:
    """ISO 2024-08-12T00:00:00.000Z → 12/08/2024."""
    if not iso:
        return ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(iso)


def _norm_data_param(d: Optional[str]) -> Optional[str]:
    """Aceita dd/mm/aaaa ou aaaa-mm-dd; API espera aaaa-mm-dd."""
    if not d:
        return None
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", d.strip())
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return d.strip()


def _validar_tribunal(slug: str) -> str:
    s = slug.strip().lower().replace("-", "")
    if s not in TRIBUNAIS:
        raise ValueError(
            f"Tribunal '{slug}' não suportado. Use listar_tribunais_ia() "
            f"para ver os {len(TRIBUNAIS)} slugs válidos (ex.: stj, stf, tjgo, trf1, tst)."
        )
    return s


def _api_search(tribunal: str, consulta: str, data_inicio: Optional[str],
                data_fim: Optional[str], relator: Optional[str]) -> dict:
    body = {"query": consulta}
    if data_inicio:
        body["from"] = _norm_data_param(data_inicio)
    if data_fim:
        body["to"] = _norm_data_param(data_fim)
    if relator:
        body["relator"] = relator
    r = requests.post(
        f"{BASE_URL}/api/tribunais/{tribunal}/search",
        json=body, headers=DEFAULT_HEADERS, timeout=90,
    )
    r.raise_for_status()
    return r.json()


def _api_similar(tribunal: str, texto: str, excluir_id: Optional[str]) -> dict:
    body = {"texto": texto}
    if excluir_id:
        body["excludeId"] = str(excluir_id)
    r = requests.post(
        f"{BASE_URL}/api/tribunais/{tribunal}/similar",
        json=body, headers=DEFAULT_HEADERS, timeout=90,
    )
    if r.status_code == 422:
        detalhe = ""
        try:
            detalhe = r.json().get("message", "")
        except Exception:
            pass
        raise ValueError(
            f"Tribunal '{tribunal}' não suporta busca por semelhança. {detalhe}".strip()
        )
    r.raise_for_status()
    return r.json()


def _corte(texto: str, max_chars: int) -> str:
    if not texto:
        return ""
    if max_chars and len(texto) > max_chars:
        return texto[:max_chars].rstrip() + " [...]"
    return texto


# ------------------------------------------------------------------ #
# Chat RAG, extração de temas, resolução de link e inteiro teor       #
# (v0.3.0 — engenharia reversa 04/08/2026)                            #
# ------------------------------------------------------------------ #

CHAT_URL = f"{BASE_URL}/api/chat-jurisprudencia"
# Tribunais com inteiro teor integral via API (/integra); nos demais só há link.
TRIBUNAIS_INTEGRA = {"tjmrs", "tjmsp", "tjrn"}
# Marcadores de citação embutidos na resposta do chat: ⟦=J1⟧, ⟦J2⟧...
_CITE_RE = re.compile(r"⟦=?\s*(J\d+)\s*⟧")


def _chat_session(slugs: list, modo: str) -> dict:
    body = {"tribunalSelectionMode": modo}
    if modo == "manual":
        body["tribunaisPermitidos"] = slugs
    r = requests.post(f"{CHAT_URL}/session", json=body,
                      headers=DEFAULT_HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def _chat_registry(chat_id: str) -> list:
    r = requests.get(f"{CHAT_URL}/registry", params={"chatId": chat_id},
                     headers=DEFAULT_HEADERS, timeout=40)
    r.raise_for_status()
    return r.json().get("entries", [])


def _chat_perguntar(pergunta: str, slugs: list, modo: str) -> tuple:
    """Cria sessão, envia a pergunta, consome o stream SSE (protocolo AI SDK)
    e devolve (texto_resposta, entradas_do_registry). As citações do registry
    já trazem o precedente completo (título, relator, órgão, ementa, link)."""
    sess = _chat_session(slugs, modo)
    msg_id = uuid.uuid4().hex[:12]
    body = {
        "messages": [{"id": msg_id, "role": "user",
                      "parts": [{"type": "text", "text": pergunta}]}],
        "chatId": sess["chatId"],
        "signature": sess["signature"],
        "issuedAt": sess["issuedAt"],
        "origin": "typed",
        "originMessageId": msg_id,
    }
    r = requests.post(CHAT_URL, json=body, stream=True, timeout=180,
                      headers={**DEFAULT_HEADERS, "Accept": "text/event-stream"})
    r.raise_for_status()
    r.encoding = "utf-8"
    partes = []
    for linha in r.iter_lines(decode_unicode=True):
        if not linha or not linha.startswith("data:"):
            continue
        payload = linha[5:].strip()
        if payload == "[DONE]":
            break
        try:
            ev = json.loads(payload)
        except Exception:
            continue
        if ev.get("type") == "text-delta":
            partes.append(ev.get("delta", ""))
    entradas = _chat_registry(sess["chatId"])
    return "".join(partes), entradas


def _api_extrair_temas(texto: str) -> list:
    r = requests.post(f"{BASE_URL}/api/extrair-temas", json={"texto": texto},
                      headers=DEFAULT_HEADERS, timeout=60)
    if r.status_code == 400:
        raise ValueError("O texto precisa ter ao menos 200 caracteres "
                         "para a extração de temas.")
    r.raise_for_status()
    return r.json().get("temas", [])


def _api_resolver_link(tribunal: str, id_: str) -> str:
    r = requests.get(f"{BASE_URL}/api/jurisprudencia-link",
                     params={"tribunal": tribunal, "id": str(id_)},
                     headers=DEFAULT_HEADERS, timeout=40)
    r.raise_for_status()
    return r.json().get("link", "") or ""


def _api_integra(tribunal: str, id_: str) -> dict:
    r = requests.get(f"{BASE_URL}/api/tribunais/{tribunal}/integra/{id_}",
                     headers=DEFAULT_HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def _xml_acordao(item: dict, indice: int, max_chars: int) -> str:
    campos = [
        ("tipo", "Acórdão"),
        ("id_interno", str(item.get("id") or "")),
        ("classe", item.get("classe_processual") or ""),
        ("numero", item.get("numero_processo_cnj") or item.get("numero_processo") or ""),
        ("orgao", item.get("orgao_julgador") or ""),
        ("relator", item.get("relator") or ""),
        ("data_julgamento", _fmt_data(item.get("data_julgamento"))),
        ("data_publicacao", _fmt_data(item.get("data_publicacao_extraida"))),
        ("ementa", _corte(item.get("texto_ementa") or "", max_chars)),
        ("link_inteiro_teor", item.get("link_pdf") or item.get("link") or item.get("link_acordao") or ""),
    ]
    linhas = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in campos if v)
    return f'<item indice="{indice}">{linhas}</item>'


def _xml_repetitivo(item: dict, indice: int, max_chars: int) -> str:
    campos = [
        ("tipo", item.get("tipo") or "Repetitivo"),
        ("numero", str(item.get("numero") or "")),
        ("orgao", item.get("orgao_julgador") or ""),
        ("ramo_direito", item.get("ramo_direito") or ""),
        ("tese_firmada", _corte(item.get("tese_firmada") or "", max_chars)),
        ("processo_paradigma", item.get("numero_processo_paradigma") or ""),
        ("link_inteiro_teor", item.get("link") or item.get("link_acordao") or ""),
    ]
    linhas = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in campos if v)
    return f'<item indice="{indice}">{linhas}</item>'


def _xml_sumula(item: dict, indice: int, max_chars: int) -> str:
    campos = [
        ("tipo", item.get("tipo") or "Súmula"),
        ("numero", str(item.get("numero") or "")),
        ("orgao", item.get("orgao_julgador") or ""),
        ("ramo_direito", item.get("ramo_direito") or ""),
        ("enunciado", _corte(item.get("enunciado") or "", max_chars)),
        ("data_julgamento", _fmt_data(item.get("data_julgamento"))),
        ("link_inteiro_teor", item.get("link_pdf") or item.get("link") or ""),
    ]
    linhas = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in campos if v)
    return f'<item indice="{indice}">{linhas}</item>'


def _montar_xml(tribunal: str, dados: dict, max_resultados: int, max_chars: int,
                incluir_precedentes: bool) -> str:
    sigla = TRIBUNAIS[tribunal][0]
    partes = []

    acordaos = (dados.get("results") or [])[:max_resultados]
    blocos = "".join(_xml_acordao(a, i + 1, max_chars) for i, a in enumerate(acordaos))
    partes.append(f'<acordaos total="{len(acordaos)}">{blocos}</acordaos>')

    if incluir_precedentes:
        reps = (dados.get("repetitivos") or [])[:max_resultados]
        if reps:
            blocos = "".join(_xml_repetitivo(x, i + 1, max_chars) for i, x in enumerate(reps))
            partes.append(f'<repetitivos total="{len(reps)}">{blocos}</repetitivos>')
        sums = (dados.get("sumulas") or [])[:max_resultados]
        if sums:
            blocos = "".join(_xml_sumula(x, i + 1, max_chars) for i, x in enumerate(sums))
            partes.append(f'<sumulas total="{len(sums)}">{blocos}</sumulas>')
        for chave in ("puil", "iacs"):
            extras = (dados.get(chave) or [])[:max_resultados]
            if extras:
                blocos = "".join(_xml_repetitivo(x, i + 1, max_chars) for i, x in enumerate(extras))
                partes.append(f'<{chave} total="{len(extras)}">{blocos}</{chave}>')

    return f'<jurisprudencia_ia tribunal="{sigla}">{"".join(partes)}</jurisprudencia_ia>'


@mcp.tool()
def buscar_jurisprudencia_ia(
    consulta: str,
    tribunais: str = "stj",
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    relator: Optional[str] = None,
    max_resultados: int = 10,
    max_chars_ementa: int = 1500,
    incluir_precedentes: bool = True,
) -> str:
    """Busca SEMÂNTICA de jurisprudência em 98 tribunais (jurisprudenciaia.com.br).

    IMPORTANTE — como escrever a consulta: a busca é VETORIAL (embeddings +
    rerank por LLM). NÃO use operadores booleanos (E/OU/ADJ/aspas/$) — não
    existem aqui. Escreva a TESE em linguagem natural, como se explicasse o
    caso a um colega. Quanto mais contexto fático-jurídico, melhor o ranking.

    Exemplo bom: "recuperação de consumo apurada unilateralmente pela
    concessionária de energia via TOI não autoriza corte nem cobrança"
    Exemplo ruim: "TOI e energia e dano moral"

    Args:
        consulta: tese/questão em linguagem natural (frase completa).
        tribunais: slug(s) separados por vírgula (ex.: "stj" ou "stj,stf,tjgo").
            Slugs: stf, stj, tst, tse, stm, trf1..trf6, tj<uf> (tjgo, tjsp...),
            trt1..trt24, tre<uf>, tcu, tce<uf>. Ver listar_tribunais_ia().
        data_inicio: filtro de data de julgamento (dd/mm/aaaa ou aaaa-mm-dd).
        data_fim: idem.
        relator: filtra por nome do relator (substring, ex.: "Nancy Andrighi").
        max_resultados: máximo de acórdãos por tribunal (padrão 10, API retorna até 20).
        max_chars_ementa: truncar ementas nesse tamanho (0 = ementa completa).
        incluir_precedentes: STF/STJ retornam também repetitivos (com tese
            firmada), súmulas, PUIL e IACs relacionados semanticamente.

    Returns:
        XML com <acordaos> (ementa, nº CNJ, relator, órgão, datas e o link em
        <link_inteiro_teor>) e, quando houver, <repetitivos>, <sumulas>,
        <puil>, <iacs>. IMPORTANTE: ao apresentar cada resultado ao usuário,
        cite SEMPRE o <link_inteiro_teor> correspondente — é a fonte oficial
        para auditoria e não deve ser omitido no resumo.
    """
    slugs = [_validar_tribunal(s) for s in tribunais.split(",") if s.strip()]
    if not slugs:
        raise ValueError("Informe ao menos um tribunal (ex.: tribunais='stj').")
    if len(slugs) > 7:
        raise ValueError("Máximo de 7 tribunais por busca (limite do próprio site).")

    saidas = []
    for slug in slugs:
        try:
            dados = _api_search(slug, consulta, data_inicio, data_fim, relator)
            saidas.append(_montar_xml(slug, dados, max_resultados,
                                      max_chars_ementa, incluir_precedentes))
        except Exception as e:
            sigla = TRIBUNAIS[slug][0]
            saidas.append(f'<jurisprudencia_ia tribunal="{sigla}">'
                          f'<erro>{escape(str(e))}</erro></jurisprudencia_ia>')
    return "\n".join(saidas)


@mcp.tool()
def buscar_similares_ia(
    texto: str,
    tribunal: str = "stj",
    excluir_id: Optional[str] = None,
    max_resultados: int = 10,
    max_chars_ementa: int = 1500,
) -> str:
    """Busca julgados SEMELHANTES a um texto livre (busca por semelhança).

    Diferente da buscar_jurisprudencia_ia (que recebe uma tese curta), aqui
    você cola um TEXTO LONGO — o resumo do caso, um trecho de ementa, a
    fundamentação de uma peça — e a API devolve os acórdãos semanticamente
    mais próximos daquele texto inteiro. Ideal para "achar acórdão parecido
    com o meu caso" ou localizar precedente análogo a partir de uma minuta.

    Args:
        texto: texto-base da comparação (parágrafos inteiros funcionam bem).
        tribunal: UM slug (ex.: "stj", "tjgo"). Nem todo tribunal suporta —
            erro 422 é reportado com mensagem clara.
        excluir_id: id interno de um julgado a excluir do resultado (útil
            para buscar semelhantes A PARTIR de um resultado anterior).
        max_resultados: máximo de acórdãos (padrão 10).
        max_chars_ementa: truncar ementas nesse tamanho (0 = completa).

    Returns:
        XML com <acordaos> semelhantes (ementa, nº CNJ, relator, órgão e o link
        em <link_inteiro_teor>). IMPORTANTE: cite SEMPRE o <link_inteiro_teor>
        de cada resultado ao apresentá-lo — é a fonte oficial para auditoria.
    """
    slug = _validar_tribunal(tribunal)
    dados = _api_similar(slug, texto, excluir_id)
    return _montar_xml(slug, dados, max_resultados, max_chars_ementa,
                       incluir_precedentes=False)


@mcp.tool()
def gerar_relatorio_ia(
    consulta: str,
    tribunais: str = "stj",
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    relator: Optional[str] = None,
    max_resultados: int = 10,
) -> str:
    """Gera relatório Markdown formatado da busca semântica de jurisprudência.

    Mesmos parâmetros da buscar_jurisprudencia_ia (consulta em linguagem
    natural, SEM operadores booleanos). Saída pronta para leitura humana ou
    para colar em nota do Obsidian: acórdãos com ementa, metadados e link, e
    (STF/STJ) repetitivos com tese firmada + súmulas relacionadas.
    """
    slugs = [_validar_tribunal(s) for s in tribunais.split(",") if s.strip()]
    if len(slugs) > 7:
        raise ValueError("Máximo de 7 tribunais por busca.")

    linhas = [f"# Pesquisa de jurisprudência — Jurisprudência IA",
              f"", f"**Consulta:** {consulta}"]
    filtros = []
    if data_inicio or data_fim:
        filtros.append(f"período {data_inicio or '…'} a {data_fim or '…'}")
    if relator:
        filtros.append(f"relator ~ {relator}")
    if filtros:
        linhas.append(f"**Filtros:** {'; '.join(filtros)}")

    for slug in slugs:
        sigla, nome, _ = TRIBUNAIS[slug]
        linhas += ["", f"## {sigla} — {nome}"]
        try:
            dados = _api_search(slug, consulta, data_inicio, data_fim, relator)
        except Exception as e:
            linhas.append(f"> ⚠️ Erro na consulta: {e}")
            continue

        reps = dados.get("repetitivos") or []
        if reps:
            linhas.append("\n### Precedentes qualificados (repetitivos/temas)")
            for x in reps[:5]:
                tese = (x.get("tese_firmada") or "").strip()
                link = x.get("link") or x.get("link_acordao") or ""
                linhas.append(f"- **{x.get('tipo', 'Tema')} {x.get('numero', '')}** "
                              f"({x.get('orgao_julgador', '')}): {tese}"
                              + (f" [→ fonte]({link})" if link else ""))
        sums = dados.get("sumulas") or []
        if sums:
            linhas.append("\n### Súmulas relacionadas")
            for x in sums[:5]:
                linhas.append(f"- **{x.get('tipo', 'Súmula')} {x.get('numero', '')}**: "
                              f"{(x.get('enunciado') or '').strip()}")

        acordaos = (dados.get("results") or [])[:max_resultados]
        linhas.append(f"\n### Acórdãos ({len(acordaos)})")
        if not acordaos:
            linhas.append("_Nenhum acórdão retornado._")
        for i, a in enumerate(acordaos, 1):
            numero = a.get("numero_processo_cnj") or a.get("numero_processo") or "s/n"
            cab = f"**{i}. {a.get('classe_processual') or 'Acórdão'} {numero}**"
            meta = " — ".join(p for p in [
                a.get("relator") or "",
                a.get("orgao_julgador") or "",
                f"j. {_fmt_data(a.get('data_julgamento'))}" if a.get("data_julgamento") else "",
            ] if p)
            linhas.append(f"\n{cab}")
            if meta:
                linhas.append(f"_{meta}_")
            ementa = _corte((a.get("texto_ementa") or "").strip(), 900)
            linhas.append(f"\n> {ementa}")
            if a.get("link_pdf"):
                linhas.append(f"\n[Inteiro teor]({a['link_pdf']})")
    return "\n".join(linhas)


@mcp.tool()
def listar_tribunais_ia() -> str:
    """Lista os 98 tribunais suportados, agrupados, com o slug a usar nas buscas.

    A busca cobre: Superiores (STF, STJ, TST, TSE, STM), Justiça Federal
    (TRF1-6), TODOS os 27 TJs estaduais (incl. TJGO), Justiça Militar
    estadual, TRT1-24, TREs e Tribunais de Contas (TCU + TCEs).
    """
    grupos: dict[str, list[str]] = {}
    for slug, (sigla, nome, grupo) in TRIBUNAIS.items():
        grupos.setdefault(grupo, []).append(f"- `{slug}` — {sigla} ({nome})")
    linhas = [f"# Tribunais suportados ({len(TRIBUNAIS)})"]
    for grupo, itens in grupos.items():
        linhas += ["", f"## {grupo} ({len(itens)})"] + itens
    linhas += ["", "Busca SEMÂNTICA: consulta em linguagem natural, sem operadores booleanos.",
               "Filtros disponíveis: data_inicio/data_fim (data de julgamento) e relator."]
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# INFORMATIVOS (STF/STJ/TST) — páginas server-rendered, sem API JSON.
# ---------------------------------------------------------------------------

INFORMATIVOS_TRIBUNAIS = ("stf", "stj", "tst")

HTML_HEADERS = {
    "User-Agent": DEFAULT_HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def _get_soup(path: str, params: Optional[dict] = None) -> BeautifulSoup:
    r = requests.get(f"{BASE_URL}{path}", params=params,
                     headers=HTML_HEADERS, timeout=60)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def _validar_trib_informativo(tribunal: str) -> str:
    t = tribunal.strip().lower()
    if t not in INFORMATIVOS_TRIBUNAIS:
        raise ValueError(
            f"Informativos cobrem apenas STF, STJ e TST (recebi '{tribunal}')."
        )
    return t


def _texto(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


@mcp.tool()
def buscar_informativos(
    consulta: str,
    tribunal: str = "",
    max_resultados: int = 15,
) -> str:
    """Busca nos INFORMATIVOS oficiais de STF, STJ e TST (jurisprudenciaia.com.br).

    Pesquisa dentro dos 32.000+ julgados publicados nos informativos de
    jurisprudência dos três tribunais (2.400+ edições, atualização diária).
    A busca aceita tema, tese ou número de processo/tema; funciona bem em
    linguagem natural (sem operadores booleanos). Cada resultado indica a
    EDIÇÃO do informativo (citável: "Informativo STJ 634"), a data, o
    tema/processo de referência e o resumo oficial da tese.

    Args:
        consulta: tema, tese ou processo (linguagem natural).
        tribunal: "" = todos; ou "stf", "stj", "tst".
        max_resultados: máximo de julgados no retorno (padrão 15).

    Returns:
        Markdown com os julgados encontrados (tribunal, edição, data,
        referência, título, resumo e link da edição).
    """
    params = {"q": consulta}
    if tribunal.strip():
        params["tribunal"] = _validar_trib_informativo(tribunal)
    soup = _get_soup("/informativos/busca", params)

    linhas = ["# Busca nos informativos — Jurisprudência IA", "",
              f"**Consulta:** {consulta}"]
    if tribunal.strip():
        linhas.append(f"**Tribunal:** {tribunal.strip().upper()}")

    nota = soup.find("p", string=re.compile(r"julgados encontrados|Nenhum"))
    if nota:
        linhas += ["", f"_{_texto(nota)}_"]

    cards = [a for a in soup.select("ul li a[href]")
             if re.match(r"^/informativos/(stf|stj|tst)/\d+", a["href"])]
    if not cards:
        linhas += ["", "Nenhum julgado encontrado para essa consulta."]
        return "\n".join(linhas)

    for i, a in enumerate(cards[:max_resultados], 1):
        href = a["href"]
        m = re.match(r"^/informativos/(stf|stj|tst)/(\d+)", href)
        trib, num = m.group(1).upper(), m.group(2)
        meta = _texto(a.find("div"))          # "STJ Informativo 634 · 26 out 2018 · Tema 699"
        titulo = _texto(a.find("h2") or a.find("h3"))
        resumo = ""
        for p in a.find_all("p"):
            t = _texto(p)
            if t and t not in meta:
                resumo = t
                break
        linhas += ["", f"## {i}. {trib} — Informativo {num}"]
        if meta:
            linhas.append(f"_{meta}_")
        if titulo:
            linhas.append(f"\n**{titulo}**")
        if resumo:
            linhas.append(f"\n> {resumo}")
        linhas.append(f"\n[Edição completa]({BASE_URL}{href})")
    return "\n".join(linhas)


@mcp.tool()
def obter_informativo(
    tribunal: str,
    numero: int,
    incluir_analise: bool = True,
    max_julgados: int = 0,
) -> str:
    """Obtém uma EDIÇÃO de informativo (STF/STJ/TST) com a análise editorial.

    Retorna a edição completa: metadados, a análise editorial da casa
    (panorama da edição + tendências), links diretos do PDF da análise e
    do podcast (MP3), e todos os julgados da edição (ramo do direito,
    título oficial, referência Tema/processo, resumo da tese e link da
    análise individual quando houver).

    Args:
        tribunal: "stf", "stj" ou "tst".
        numero: número da edição (ex.: 894 p/ STJ, 1222 p/ STF, 311 p/ TST).
        incluir_analise: incluir o texto da análise editorial (padrão sim).
        max_julgados: limitar a quantidade de julgados (0 = todos).

    Returns:
        Markdown da edição. Cita-se como "Informativo {TRIB} {numero}".
    """
    trib = _validar_trib_informativo(tribunal)
    soup = _get_soup(f"/informativos/{trib}/{numero}")

    linhas = [f"# Informativo {trib.upper()} {numero}"]
    sub = next((p for p in soup.find_all("p")
                if re.search(r"(Edição de|julgados?)", _texto(p))
                and len(_texto(p)) < 120), None)
    if sub:
        linhas.append(f"_{_texto(sub)}_")

    oficial = next((a for a in soup.find_all("a", href=True)
                    if "Edição oficial" in _texto(a)), None)
    if oficial:
        linhas.append(f"\n[Edição oficial no site do tribunal]({oficial['href']})")

    pdf = soup.find("a", href=re.compile(r"\.pdf($|\?)"))
    if pdf:
        url = pdf["href"]
        if url.startswith("/"):
            url = BASE_URL + url
        linhas.append(f"[PDF da análise]({url})")
    mp3 = soup.find(["a", "audio", "source"], attrs={"href": re.compile(r"\.mp3($|\?)")}) \
        or soup.find(["audio", "source"], attrs={"src": re.compile(r"\.mp3($|\?)")})
    if mp3:
        url = mp3.get("href") or mp3.get("src")
        if url.startswith("/"):
            url = BASE_URL + url
        linhas.append(f"[Podcast da edição (MP3)]({url})")

    if incluir_analise:
        for h in soup.find_all(["h2", "h3"]):
            titulo_sec = _texto(h)
            if titulo_sec in ("O panorama da edição", "Tendências que a edição revela",
                              "O essencial desta edição"):
                corpo = []
                for sib in h.find_next_siblings():
                    if sib.name in ("h2", "h3", "section", "ul"):
                        break
                    if sib.name in ("p", "blockquote", "figure"):
                        t = _texto(sib)
                        if t:
                            corpo.append(t)
                if corpo:
                    linhas += ["", f"## {titulo_sec}", ""] + [f"{c}" for c in corpo]

    itens = soup.select("li[id^=item-]")
    total = len(itens)
    if max_julgados:
        itens = itens[:max_julgados]
    linhas += ["", f"## Julgados da edição ({total})"]
    for li in itens:
        spans = li.find_all("span", recursive=True)
        ordem = _texto(spans[0]) if spans else ""
        ramo = _texto(spans[1]) if len(spans) > 1 else ""
        titulo = _texto(li.find("h3"))
        ref = ""
        p_ref = li.find("p", class_=re.compile(r"text-\[12"))
        if p_ref:
            ref = _texto(p_ref)
        resumos = [_texto(p) for p in li.select("div p.whitespace-pre-line")]
        analise = li.find("a", href=re.compile(rf"^/informativos/{trib}/{numero}/"))
        linhas += ["", f"### {ordem or '•'} {ramo}".rstrip()]
        if titulo:
            linhas.append(f"**{titulo}**")
        if ref and ref not in titulo:
            linhas.append(f"_{ref}_")
        for rtxt in resumos:
            if rtxt:
                linhas.append(f"\n> {rtxt}")
        if analise:
            linhas.append(f"\n[Análise editorial deste julgado]({BASE_URL}{analise['href']})")
    if max_julgados and total > max_julgados:
        linhas += ["", f"_Exibindo {max_julgados} de {total} julgados "
                       f"(max_julgados={max_julgados})._"]
    return "\n".join(linhas)


@mcp.tool()
def listar_informativos(
    tribunal: str = "stj",
    max_edicoes: int = 15,
) -> str:
    """Lista as edições mais recentes do informativo de um tribunal (STF/STJ/TST).

    O índice do site mostra as ~60 edições mais recentes; edições antigas
    são acessíveis direto por obter_informativo(tribunal, numero).

    Args:
        tribunal: "stf", "stj" ou "tst".
        max_edicoes: quantas edições listar (padrão 15).

    Returns:
        Markdown com número da edição, data, quantidade de julgados e
        comentários editoriais.
    """
    trib = _validar_trib_informativo(tribunal)
    soup = _get_soup(f"/informativos/{trib}")

    linhas = [f"# Informativos do {trib.upper()} — edições recentes"]
    intro = soup.find("p", string=re.compile(r"edições e .* julgados"))
    if intro:
        linhas.append(f"_{_texto(intro)}_")
    linhas.append("")

    cards = [a for a in soup.select("ul li a[href]")
             if re.match(rf"^/informativos/{trib}/\d+$", a["href"])]
    vistos = set()
    n = 0
    for a in cards:
        num = a["href"].rsplit("/", 1)[-1]
        if num in vistos:
            continue
        vistos.add(num)
        meta = ""
        p = a.find("p")
        if p:
            meta = _texto(p)
        linhas.append(f"- **Informativo {num}**"
                      + (f" — {meta}" if meta else "")
                      + f" · [abrir]({BASE_URL}{a['href']})")
        n += 1
        if n >= max_edicoes:
            break
    if not vistos:
        linhas.append("Nenhuma edição encontrada no índice.")
    return "\n".join(linhas)


@mcp.tool()
def perguntar_jurisprudencia_ia(
    pergunta: str,
    tribunais: str = "stj,tjgo",
    max_chars_ementa: int = 700,
) -> str:
    """Pergunta em linguagem natural ao CHAT RAG da Jurisprudência IA.

    Diferente da buscar_jurisprudencia_ia (que devolve uma lista de acórdãos),
    aqui um assistente do próprio site LÊ os julgados e RESPONDE à sua pergunta
    de forma fundamentada, citando os precedentes que embasam a resposta. Ideal
    para "qual o entendimento do STJ sobre X?" ou "há divergência entre as
    turmas quanto a Y?". A resposta traz marcadores [J1], [J2]... que remetem à
    seção "Fontes citadas", com título, relator, órgão, ementa e link oficial de
    cada precedente — tudo auditável.

    Args:
        pergunta: a questão jurídica em linguagem natural (frase completa).
        tribunais: slug(s) separados por vírgula (ex.: "stj,tjgo") para restringir
            a busca; use "auto" para deixar o assistente escolher os tribunais.
        max_chars_ementa: truncar as ementas das fontes citadas (0 = completa).

    Returns:
        Markdown com a resposta fundamentada + as fontes citadas (auditoria).
        IMPORTANTE: preserve os links de cada fonte ao repassar ao usuário.
    """
    alvo = tribunais.strip().lower()
    if alvo in ("", "auto", "todos", "automatico", "automático"):
        modo, slugs = "auto", []
    else:
        modo = "manual"
        slugs = [_validar_tribunal(s) for s in tribunais.split(",") if s.strip()]
        if len(slugs) > 7:
            raise ValueError("Máximo de 7 tribunais por conversa (limite do site).")

    texto, entradas = _chat_perguntar(pergunta, slugs, modo)
    texto = _CITE_RE.sub(r"[\1]", texto).strip()

    linhas = ["# Resposta — Jurisprudência IA (chat RAG)", "",
              f"**Pergunta:** {pergunta}",
              f"**Tribunais:** {'automático' if modo == 'auto' else tribunais}",
              "", texto]

    if entradas:
        linhas += ["", "---", "## Fontes citadas (auditoria)"]
        for d in entradas:
            ref = d.get("ref", "")
            trib = (d.get("tribunal") or "").upper()
            titulo = d.get("titulo") or "(sem título)"
            prec = d.get("precedente") or {}
            meta_partes = " — ".join(p for p in [
                prec.get("relator") or "",
                prec.get("orgao_julgador") or "",
                f"j. {_fmt_data(prec.get('data_julgamento'))}" if prec.get("data_julgamento") else "",
            ] if p)
            linhas.append(f"\n**[{ref}] {trib} — {titulo}**")
            if meta_partes:
                linhas.append(f"_{meta_partes}_")
            ementa = _corte((prec.get("texto_ementa") or "").strip(), max_chars_ementa)
            if ementa:
                linhas.append(f"> {ementa}")
            link = prec.get("link_pdf") or ""
            if not link:
                try:
                    link = _api_resolver_link(d.get("tribunal"),
                                              (d.get("meta") or {}).get("id"))
                except Exception:
                    link = ""
            if link:
                linhas.append(f"[Inteiro teor]({link})")
    else:
        linhas += ["", "_(Esta resposta não registrou precedentes no registry.)_"]

    return "\n".join(linhas)


@mcp.tool()
def extrair_temas_ia(texto: str) -> str:
    """Extrai os TEMAS jurídicos pesquisáveis de um texto livre.

    Cole um texto longo (resumo do caso, trecho de peça, ementa) — MÍNIMO de
    200 caracteres — e a API devolve os temas jurídicos identificados, cada um
    com uma sugestão de consulta e os tribunais mais indicados. Útil para
    transformar um caso concreto em pautas de pesquisa antes de rodar a
    buscar_jurisprudencia_ia ou a perguntar_jurisprudencia_ia.

    Args:
        texto: o texto-base (≥ 200 caracteres).

    Returns:
        Markdown com a lista de temas (tema + tribunais sugeridos).
    """
    temas = _api_extrair_temas(texto)
    if not temas:
        return "Nenhum tema foi extraído do texto."
    linhas = ["# Temas extraídos", ""]
    for t in temas:
        if isinstance(t, dict):
            nome = t.get("tema") or t.get("titulo") or t.get("nome") or "(tema)"
            tribs = ", ".join((t.get("tribunais") or []))
            linhas.append(f"- **{nome}**" + (f" — sugeridos: {tribs}" if tribs else ""))
        else:
            linhas.append(f"- **{t}**")
    return "\n".join(linhas)


@mcp.tool()
def resolver_link_ia(tribunal: str, id: str) -> str:
    """Resolve o LINK oficial do inteiro teor de um julgado pelo id interno.

    Útil como fallback quando um resultado da busca veio sem link (acontece com
    acórdãos recentes de índice incompleto): informe o tribunal e o id_interno
    do resultado e receba a URL da fonte oficial (SCON/STJ, Projudi/TJGO etc.).

    Args:
        tribunal: slug do tribunal (ex.: "stj", "tjgo").
        id: id interno do julgado (campo id_interno da busca).

    Returns:
        A URL do inteiro teor, ou aviso se indisponível.
    """
    slug = _validar_tribunal(tribunal)
    link = _api_resolver_link(slug, id)
    return link or "(link não disponível para este julgado)"


@mcp.tool()
def obter_inteiro_teor_ia(tribunal: str, id: str, max_chars: int = 0) -> str:
    """Obtém o INTEIRO TEOR de um julgado (equivale ao 'Baixar .txt' do site).

    Para tjmrs, tjmsp e tjrn a API entrega o TEXTO INTEGRAL do acórdão; para os
    demais tribunais (STJ, TJGO, STF etc.) o texto completo não é exposto pela
    API — nesse caso devolve o link oficial, onde o inteiro teor pode ser lido
    ou baixado (frequentemente um PDF que exigiria OCR).

    Args:
        tribunal: slug do tribunal (ex.: "stj", "tjgo", "tjrn").
        id: id interno do julgado (campo id_interno da busca).
        max_chars: truncar o texto integral nesse tamanho (0 = completo).

    Returns:
        O texto integral (tribunais suportados) ou o link oficial.
    """
    slug = _validar_tribunal(tribunal)
    if slug in TRIBUNAIS_INTEGRA:
        data = _api_integra(slug, id)
        tipo = str(data.get("type") or "")
        conteudo = str(data.get("content") or "")
        if not conteudo:
            return "Inteiro teor vazio para este julgado."
        if tipo == "url" or conteudo.startswith("http"):
            return f"Inteiro teor disponível como documento: {conteudo}"
        return _corte(conteudo, max_chars) if max_chars else conteudo
    link = _api_resolver_link(slug, id)
    if link:
        return (f"O inteiro teor de {TRIBUNAIS[slug][0]} não é exposto como texto "
                f"pela API. Fonte oficial (leitura/download): {link}")
    return "Inteiro teor indisponível como texto e link não resolvido."


def main():
    mcp.run()


if __name__ == "__main__":
    main()
