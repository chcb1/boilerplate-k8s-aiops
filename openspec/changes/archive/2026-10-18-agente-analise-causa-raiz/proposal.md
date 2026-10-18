# Proposal

## Why

A coleta (PRD 001) e a deduplicacao com relatorio `EM_ANALISE` (PRD 002, US01) ja existem, mas ninguem analisa os eventos: o `AnalysisHandler` recebe um `analyzer` injetado que nao foi implementado, e o `main.py` ainda liga o coletor ao handler placeholder que so imprime no stdout. Sem o agente, o diagnostico de causa raiz continua manual e nenhum relatorio chega a ser gerado para a interface web (PRD 003) nem para a correcao (PRD 004).

## What Changes

- Implementar o agente de analise (LangChain + Claude + MCP Server Kubernetes) que investiga os eventos do lote em loop de tool-calling, usando apenas as tools de leitura `kubectl_get`, `kubectl_describe` e `kubectl_logs`.
- Implementar o `analyzer` do `AnalysisHandler`: roda o agente sobre o relatorio `EM_ANALISE` do lote e persiste o resultado.
- Converter a resposta Markdown do agente em um relatorio por problema agrupado, mapeando os `event_uids` pelo campo **Eventos** e extraindo a severidade.
- Fazer a substituicao do relatorio do lote de forma condicional ao status (so se ainda `EM_ANALISE`), reaproveitando a linha do lote como primeiro problema e herdando o `attempt_count` do lote para que o limite `ANALYSIS_MAX_ATTEMPTS` continue valendo.
- Vincular os eventos do lote que o agente nao referenciou em nenhum problema a um relatorio `INCOMPLETO`, fechando o risco de reanalise sem teto.
- Marcar o relatorio do lote como `INCOMPLETO` nas falhas de infraestrutura (MCP indisponivel, erro da API do Claude, resposta vazia, limite de iteracoes sem causa raiz).
- Adicionar a coluna anulavel `severity` em `reports` (migration Alembic), preenchida no swap, para a listagem do PRD 003 nao precisar fazer parse do Markdown.
- Ligar o `AnalysisHandler` no `lifespan` do `main.py` no lugar do handler placeholder do coletor. **BREAKING**: o stdout deixa de listar os eventos coletados; o handler placeholder (`collector/handler.py`) e seus testes sao removidos.
- Novas variaveis de ambiente: `AGENT_MODEL_NAME` (padrao `claude-haiku-4-5`) e `AGENT_MAX_ITERATIONS` (padrao 25).

## Capabilities

### New Capabilities

- `root-cause-analysis-agent`: investigacao automatizada dos eventos de um lote via agente com tools Kubernetes somente leitura, com modelo e limite de iteracoes configuraveis e tratamento das falhas de infraestrutura.
- `analysis-report-persistence`: conversao da resposta do agente em relatorios por problema, substituicao condicional do relatorio do lote, tratamento de eventos nao referenciados e fluxo de status do relatorio.

### Modified Capabilities

- `kubernetes-event-collection`: remove o requisito de exibicao dos eventos no stdout, que so valia enquanto o processamento real nao existisse. As regras de coleta e de deduplicacao nao mudam.

## Impact

- **Codigo**: novo pacote `src/my_agent_app/agents/` (agente, cliente MCP, parser do relatorio) e `src/my_agent_app/analysis/` (analyzer e swap); `main.py` (fiacao do handler); `models/report.py` (coluna `severity`); `analysis/config.py` (novas variaveis); nova migration em `alembic/versions/`.
- **Dependencias**: `langchain[anthropic]` e `langchain-mcp-adapters` ja declaradas; requer Node/npx e o MCP Server Kubernetes em execucao em `MCP_SERVER_URL`, alem de `ANTHROPIC_API_KEY`.
- **Sistemas externos**: API da Anthropic (custo por tokens, mitigado por `AGENT_MAX_ITERATIONS` e `ANALYSIS_MAX_ATTEMPTS`) e o cluster Kubernetes, acessado somente para leitura.
- **Consumidores**: PRD 003 (le `severity`, `status`, `markdown`) e PRD 004 (parte de relatorios `COMPLETO`).
- **Fora do escopo**: interface web (PRD 003), execucao da correcao (PRD 004), saida estruturada do LLM e deduplicacao por `involvedObject`.
