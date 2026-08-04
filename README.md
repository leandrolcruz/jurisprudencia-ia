# jurisprudencia-ia (MCP)

MCP server de busca **semântica** de jurisprudência via API não documentada do
[jurisprudenciaia.com.br](https://www.jurisprudenciaia.com.br/) — sem login, sem
CAPTCHA, sem cookie. Engenharia reversa em 15/07/2026.

## O que diferencia esta fonte

- **Busca vetorial em linguagem natural** — a query é a tese descrita por extenso
  (embeddings + rerank por LLM no servidor). Não existe sintaxe booleana.
- **98 tribunais**: STF, STJ, TST, TSE, STM, TRF1-6, todos os 27 TJs (incl. TJGO),
  Justiça Militar estadual, TRT1-24, 27 TREs, TCU e TCEs.
- **STF/STJ retornam de brinde precedentes qualificados** relacionados
  semanticamente: repetitivos (com tese firmada), súmulas, PUIL e IACs.
- **Busca por semelhança** (`/similar`): cola-se um texto longo (resumo do caso,
  trecho de peça) e volta o acórdão mais parecido.
- Todo resultado traz **link do inteiro teor** na fonte oficial (SCON/STJ,
  Projudi ConsultaJurisprudencia/TJGO etc.).
- **Informativos STF/STJ/TST** (v0.2.0): 2.400+ edições e 32.000+ julgados dos
  informativos oficiais, atualização diária, com **análise editorial** própria
  do site (panorama + tendências, PDF e podcast MP3 com link direto). Busca
  interna própria; cada resultado indica a edição citável ("Informativo STJ 634").

## API (engenharia reversa)

| Endpoint | Método | Body | Nota |
|---|---|---|---|
| `/api/tribunais/{slug}/search` | POST JSON | `{query, from, to, relator}` | 20 resultados, datas ISO `aaaa-mm-dd` |
| `/api/tribunais/{slug}/similar` | POST JSON | `{texto, excludeId}` | 422 se o tribunal não suportar |
| `/api/tribunais/{slug}/integra/{id}` | GET | — | só tjmrs/tjmsp/tjrn; dispensável (há `link_pdf`) |
| `/api/chat-jurisprudencia/session` | POST JSON | `{tribunalSelectionMode, tribunaisPermitidos}` | → `{chatId, signature, issuedAt}` |
| `/api/chat-jurisprudencia` | POST SSE | `{messages, chatId, signature, issuedAt, origin:"typed", originMessageId}` | stream AI SDK; `text-delta` + `data-registry-update` |
| `/api/chat-jurisprudencia/registry` | GET | `?chatId=` | precedentes citados (título, relator, ementa, `link_pdf`) |
| `/api/extrair-temas` | POST JSON | `{texto}` (≥200 chars) | → `{temas:[{tema, query, tribunais}]}` |
| `/api/jurisprudencia-link` | GET | `?tribunal=&id=` | → `{link}` oficial por id interno |
| `/informativos/{trib}` | GET HTML | — | índice (~60 edições recentes); trib ∈ stf/stj/tst |
| `/informativos/{trib}/{numero}` | GET HTML | — | edição + análise editorial + PDF/MP3 |
| `/informativos/busca` | GET HTML | `?q=&tribunal=` | busca nos julgados dos informativos |

Os informativos NÃO têm API JSON — são páginas server-rendered (parse com
BeautifulSoup). Edições antigas não têm análise editorial (a saída degrada
limpa, só com os julgados).

Resposta do `/search`: `results` (acórdãos), e no STF/STJ também `repetitivos`,
`sumulas`, `puil`, `iacs` + `reranked_results` (ranking unificado com `__kind`
e `rerank_score`).

## Tools

1. `buscar_jurisprudencia_ia(consulta, tribunais="stj,stf,tjgo", data_inicio, data_fim, relator, ...)` → XML
2. `buscar_similares_ia(texto, tribunal, excluir_id, ...)` → XML
3. `gerar_relatorio_ia(...)` → Markdown
4. `listar_tribunais_ia()` → slugs agrupados
5. `buscar_informativos(consulta, tribunal="", max_resultados)` → Markdown
6. `obter_informativo(tribunal, numero, incluir_analise, max_julgados)` → Markdown
7. `listar_informativos(tribunal, max_edicoes)` → Markdown
8. `perguntar_jurisprudencia_ia(pergunta, tribunais="stj,tjgo", ...)` → **chat RAG**: resposta fundamentada + fontes citadas auditáveis (Markdown)
9. `extrair_temas_ia(texto)` → temas pesquisáveis a partir de um texto ≥200 chars (Markdown)
10. `resolver_link_ia(tribunal, id)` → link oficial de um julgado pelo id (fallback p/ resultado sem link)
11. `obter_inteiro_teor_ia(tribunal, id)` → texto integral (tjmrs/tjmsp/tjrn) ou link oficial (demais)

## Como escrever a consulta

- ✅ "recuperação de consumo apurada unilateralmente pela concessionária via TOI
  não autoriza corte nem cobrança retroativa"
- ❌ "TOI e energia e dano moral" (operadores booleanos não existem aqui)

## Instalação

Pré-requisitos: [`uv`](https://docs.astral.sh/uv/) instalado e, para rodar
direto do GitHub, o `git` também. A primeira execução baixa as dependências
(`mcp`, `requests`, `beautifulsoup4`) sozinha.

### Claude Code

Direto do GitHub (recomendado — sem clonar):

```bash
claude mcp add --scope user jurisprudencia-ia -- uvx --from git+https://github.com/leandrolcruz/jurisprudencia-ia jurisprudencia-ia
```

Ou a partir de um clone local:

```bash
claude mcp add --scope user jurisprudencia-ia -- uvx --from ~/Documents/plugins/jurisprudencia-ia jurisprudencia-ia
```

### Claude Desktop (Windows / macOS)

Passo a passo completo (incluindo instalação do `uv`/`git` e os erros mais
comuns) em [`GUIA-CLAUDE-DESKTOP.md`](GUIA-CLAUDE-DESKTOP.md). Resumo — editar o
`claude_desktop_config.json` (Configurações → Desenvolvedor → Editar Config) e
acrescentar:

```json
{
  "mcpServers": {
    "jurisprudencia-ia": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/leandrolcruz/jurisprudencia-ia", "jurisprudencia-ia"]
    }
  }
}
```

Depois salvar e reiniciar o Claude Desktop. Config:
`%APPDATA%\Claude\claude_desktop_config.json` (Windows) ou
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).

## Avisos

- API de terceiro, não documentada — pode mudar sem aviso. Se quebrar, refazer o
  recon: baixar chunks JS de `/_next/static/chunks/` e grepar `api/tribunais`.
- Uso moderado: sem rate-limit conhecido, mas o serviço é gratuito e mantido
  por terceiros (mesmo grupo do minutaia.com.br).
