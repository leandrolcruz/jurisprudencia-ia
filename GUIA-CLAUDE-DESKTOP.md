# Instalar o jurisprudencia-ia no Claude Desktop

Guia para usar a ferramenta de busca semântica de jurisprudência (**jurisprudencia-ia**)
dentro do **Claude Desktop** (o app de computador — chat e Cowork).

Não precisa saber programar. São 3 passos. O código roda direto do GitHub, então
você **não precisa baixar nada** manualmente — o próprio computador busca e instala.

> Repositório: https://github.com/leandrolcruz/jurisprudencia-ia (público)

> Usa o **Claude Code no terminal** em vez do app? Pule para a seção
> [Claude Code (terminal)](#claude-code-terminal) no final — é um comando só.

---

## Windows

### 1. Instalar o `uv`
Abra o **PowerShell** (botão Iniciar → digite "PowerShell" → Enter) e cole:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Feche e reabra o PowerShell depois de instalar.

### 2. Instalar o Git
Necessário porque o `uv` vai baixar o código do GitHub.
Baixe em https://git-scm.com/download/win e instale clicando em "Next" até o fim
(pode aceitar tudo no padrão).

### 3. Registrar a ferramenta no Claude Desktop
1. No Claude Desktop: **Configurações → Desenvolvedor → Editar Config**.
   (Isso abre o arquivo `claude_desktop_config.json`, na pasta `%APPDATA%\Claude\`.)
2. Cole o conteúdo abaixo. Se o arquivo já tiver `"mcpServers"`, apenas acrescente
   a entrada `"jurisprudencia-ia"` dentro dele:

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

3. **Salve o arquivo, feche e reabra o Claude Desktop.**

---

## macOS

### 1. Instalar o `uv`
Abra o **Terminal** (Cmd+Espaço → digite "Terminal" → Enter) e cole:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Feche e reabra o Terminal depois de instalar.

### 2. Git
O macOS geralmente já tem o Git. Para conferir, digite `git --version` no Terminal.
Se pedir para instalar as "ferramentas de linha de comando", aceite.

### 3. Registrar a ferramenta no Claude Desktop
1. No Claude Desktop: **Configurações → Desenvolvedor → Editar Config**.
   (Isso abre o `claude_desktop_config.json`, em
   `~/Library/Application Support/Claude/`.)
2. Cole o conteúdo abaixo. Se o arquivo já tiver `"mcpServers"`, apenas acrescente
   a entrada `"jurisprudencia-ia"` dentro dele:

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

3. **Salve o arquivo, feche e reabra o Claude Desktop.**

---

## Testar
No chat do Claude Desktop, peça algo como:

> Busque no STJ jurisprudência sobre recuperação de consumo apurada por TOI que
> não autoriza corte de energia.

O Claude vai pedir permissão para usar a ferramenta **jurisprudencia-ia** e
retornar os acórdãos com ementa, número do processo, relator e link do inteiro
teor. Autorize e pronto.

Dica de consulta: descreva a **tese por extenso**, em linguagem natural. A busca é
semântica — **não** use operadores booleanos ("e", "ou", "aspas").
- ✅ "recuperação de consumo apurada unilateralmente via TOI não autoriza corte nem cobrança retroativa"
- ❌ "TOI e energia e dano moral"

---

## Se der erro

- **`spawn uvx ENOENT` / "comando não encontrado"** — o Claude Desktop não achou o
  `uvx`. Descubra o caminho completo (`where uvx` no Windows, `which uvx` no Mac) e
  troque o `"command": "uvx"` por esse caminho completo. No Windows costuma ser
  `C:\\Users\\SEU_USUARIO\\.local\\bin\\uvx.exe` (use barras duplas no JSON). No Mac,
  algo como `/Users/SEU_USUARIO/.local/bin/uvx`.
- **"failed to clone" / erro de git** — falta o Git (passo 2 do Windows). Instale e
  reinicie o Claude Desktop.
- **A ferramenta não aparece** — confirme que o JSON está válido (sem vírgula
  sobrando, chaves fechadas) e que você reiniciou o app por completo.

---

## Claude Code (terminal)

Se você usa o **Claude Code** pelo terminal (não o app desktop), não precisa
mexer em arquivo de config nenhum. Basta ter o `uv` e o `git` instalados
(passos 1 e 2 acima, conforme seu sistema) e rodar **um comando**:

```bash
claude mcp add --scope user jurisprudencia-ia -- uvx --from git+https://github.com/leandrolcruz/jurisprudencia-ia jurisprudencia-ia
```

O `--scope user` deixa a ferramenta disponível em qualquer pasta/projeto. Confira
com:

```bash
claude mcp list
```

Para remover depois, se quiser:

```bash
claude mcp remove --scope user jurisprudencia-ia
```

No Windows, o Claude Code roda tanto no PowerShell quanto no WSL — o comando é o
mesmo. Se aparecer `uvx: command not found`, feche e reabra o terminal (o passo 1
adiciona o `uv` ao PATH só nas janelas novas).

---

## Observações
- A ferramenta usa uma API pública de terceiro (jurisprudenciaia.com.br), sem
  login. Uso moderado — o serviço é gratuito e mantido por terceiros.
- **Atualizar para uma versão nova:** o `uvx` guarda a versão em cache. Para
  puxar a última do GitHub, rode uma vez no terminal
  `uvx --from git+https://github.com/leandrolcruz/jurisprudencia-ia jurisprudencia-ia`
  (ele reconstrói a partir do commit mais recente; pode dar Ctrl+C assim que
  aparecer "Built …"). Se ainda vier a versão antiga, `uv cache prune` limpa o
  cache. Depois, feche e reabra o Claude Desktop.
