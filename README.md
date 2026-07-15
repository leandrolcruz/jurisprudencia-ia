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

## Como escrever a consulta

- ✅ "recuperação de consumo apurada unilateralmente pela concessionária via TOI
  não autoriza corte nem cobrança retroativa"
- ❌ "TOI e energia e dano moral" (operadores booleanos não existem aqui)

## Instalação

```bash
claude mcp add --scope user jurisprudencia-ia -- uvx --from ~/Documents/plugins/jurisprudencia-ia jurisprudencia-ia
```

## Avisos

- API de terceiro, não documentada — pode mudar sem aviso. Se quebrar, refazer o
  recon: baixar chunks JS de `/_next/static/chunks/` e grepar `api/tribunais`.
- Uso moderado: sem rate-limit conhecido, mas o serviço é gratuito e mantido
  por terceiros (mesmo grupo do minutaia.com.br).
