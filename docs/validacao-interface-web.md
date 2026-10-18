# Validacao local da interface web de relatorios

Change: `interface-web-relatorios` — executada em 2026-10-18 contra o app real (`uvicorn` em
`127.0.0.1:8765`) e um banco PostgreSQL descartavel (`aiops_web_check`, removido ao final), com as
migrations aplicadas por `alembic upgrade head`. Os relatorios foram semeados por SQL **depois** do
startup, porque a recuperacao de orfaos marcaria um `EM_ANALISE` semeado antes como INCOMPLETO.

## Resultado

| Verificacao | Resultado |
|---|---|
| Link "Relatorios" no cabecalho da home | OK |
| `GET /reports` responde 200 `text/html`, mais recentes primeiro | OK — ordem: relatorio real, `22222222` (1 min), `44444444` (1 h), `33333333` (2 h), `11111111` (3 h) |
| Badges por status e severidade | OK — `badge-incomplete`, `badge-processing`, `badge-complete`; `sev-critico`, `sev-alto` |
| Titulo malicioso (`<script>` no titulo) | OK — escapado (`&lt;script&gt;`), nenhuma tag real |
| Detalhe completo: tabela, lista, `<h3>` | OK — 1 tabela, `Causa Raiz` como `<h3>` |
| Comando sugerido em bloco cercado | OK — `<pre><code class="language-bash">kubectl patch ... "*x*"`; 0 ocorrencias de `<em>x</em>` |
| Conteudo hostil no Markdown | OK — 0 ocorrencias de `<script`, `onerror`, `javascript:` e do texto do payload dentro de `<article>`; link `https://example.com/docs` mantido |
| `EM_ANALISE` sem Markdown | OK — "A analise esta em andamento. Recarregue a pagina em instantes." |
| `INCOMPLETO` com Markdown parcial | OK — renderizado (`<strong>sem formato</strong>`) |
| `INCOMPLETO` sem Markdown | OK — "Este relatorio nao tem conteudo de analise." |
| ID inexistente e ID malformado (`xyz`) | OK — ambos 404 com "Relatorio nao encontrado." |
| `POST`/`PUT`/`DELETE` em `/reports` e `POST` no detalhe | OK — 405 |
| Formulario ou botao no detalhe | OK — 0 |
| Banco inacessivel (porta fechada) | OK — 503 na listagem e no detalhe, "Banco de dados indisponivel, tente novamente em instantes", sem vazamento de porta, traceback, `ConnectionRefused`, `asyncpg` ou senha; `/api/health` continua 200 |

## Notas

- O proprio app gerou um relatorio real durante o teste: o coletor leu o Warning `ngnix`
  (`ImagePullBackOff`) do kind, a deduplicacao criou o relatorio `EM_ANALISE` e, como o MCP Server
  estava desligado, o analisador o marcou `INCOMPLETO` (caminho de falha de infraestrutura do PRD 002).
  Ele aparece na listagem como "Analise incompleta (xxxxxxxx)" e, no detalhe, sem conteudo.
- Nao foi aberto navegador: a conferencia foi por `curl` sobre o HTML. A aparencia (CSS) nao foi
  avaliada visualmente.
- Nenhuma chamada ao Claude foi feita nesta validacao.
