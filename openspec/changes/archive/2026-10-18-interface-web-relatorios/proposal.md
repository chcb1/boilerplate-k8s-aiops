# Proposal

## Why

O agente de analise (PRD 002) ja gera e persiste relatorios por problema, mas a unica forma de le-los e consultar o banco. Sem uma interface de leitura, o diagnostico nao chega a quem precisa agir. Ao revisar o PRD 003 contra o codigo e a biblioteca de Markdown instalada, apareceram requisitos que o PRD nao cobre: o texto do relatorio vem de um LLM que le logs de pods arbitrarios, entao renderiza-lo sem sanitizar permite XSS (`<script>`, `onerror` e links `javascript:` passam intactos); e o Comando Sugerido, hoje texto solto, e corrompido pelo Markdown (`*x*` dentro do JSON de um `kubectl patch` vira `<em>x</em>`).

## What Changes

- Adicionar a interface web de leitura: listagem `GET /reports` (mais recentes primeiro, limitada) e detalhe `GET /reports/{id}`, renderizados com Jinja2 pela propria API FastAPI.
- Exibir o status como badge e a severidade a partir da coluna `severity` (e nao por parse do Markdown, como o PRD 003 previa); adicionar o link "Relatórios" ao cabecalho comum.
- Renderizar o Markdown com `fenced_code` e `tables` e sanitizar o HTML resultante com `nh3` antes de exibi-lo.
- Tratar os estados vazio, relatorio sem conteudo, relatorio inexistente ou ID malformado (404) e banco indisponivel (503, incluindo falhas de conexao que nao sao `SQLAlchemyError`).
- Persistir o titulo do problema em uma nova coluna anulavel `title` (migration Alembic), para a listagem identificar cada relatorio por mais que seu UUID.
- Pedir ao agente de analise que apresente o Comando Sugerido em bloco de codigo cercado, para que o comando seja exibido e copiado sem alteracao.
- **Fora desta change**: o botao "Executar correcao", o `POST /reports/{id}/fix` e o tratamento do 409 pertencem ao PRD 004; esta change entrega uma interface somente leitura, sem nenhum controle que altere dados.

## Capabilities

### New Capabilities

- `report-web-ui`: paginas de listagem e detalhe dos relatorios de analise, com badges de status, severidade, renderizacao segura do Markdown e tratamento de estados vazios e de erro.

### Modified Capabilities

- `analysis-report-persistence`: o relatorio por problema passa a persistir tambem o titulo do problema.
- `root-cause-analysis-agent`: o prompt passa a exigir que o comando sugerido de cada problema venha em bloco de codigo cercado.

## Impact

- **Codigo**: `web/router.py` (rotas e tratadores de erro), novo `web/markdown.py` (render e sanitizacao), templates `reports.html` e `report_detail.html`, `base.html` (link no cabecalho e estilos), `error.html`; `models/report.py` e nova migration (coluna `title`); `analysis/parser.py` e `analysis/swap.py` (titulo); `agents/prompt.py` (comando cercado); `main.py` (registro dos tratadores de erro).
- **Dependencias**: nova `nh3` (sanitizacao de HTML).
- **Dados**: coluna `title` anulavel, sem backfill; relatorios anteriores aparecem sem titulo.
- **Seguranca**: a interface nao tem autenticacao na v1 e le dados do cluster; o `CLAUDE.md` passa a documentar essa limitacao.
- **Consumidores**: o PRD 004 acrescentara o botao e a secao "Resultado da Correcao" sobre estas paginas.
- **Fora do escopo**: autenticacao, filtros, paginacao, dashboard, execucao da correcao e atualizacao automatica da pagina.
