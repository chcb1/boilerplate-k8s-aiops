# Tasks

## 1. Modelo de dados e configuracao

- [x] 1.1 Adicionar a coluna anulavel `severity` a `Report` e criar a migration Alembic; verificar com `uv run alembic upgrade head` e `downgrade -1` num banco limpo, e ajustar `tests/integration/test_report_model.py` para cobrir a coluna
- [x] 1.2 Criar `agents/config.py` com `AGENT_MODEL_NAME` (padrao `claude-haiku-4-5`) e `AGENT_MAX_ITERATIONS` (padrao 25, invalido gera warning); verificar com testes unitarios para valor valido, ausente, nao numerico, zero e negativo
- [x] 1.3 Documentar as novas variaveis e a regra "stale timeout acima do pior caso do agente" no `CLAUDE.md`; verificar que a tabela de variaveis lista as duas

## 2. Parser do relatorio

- [x] 2.1 Criar `analysis/parser.py` que divide a resposta em problemas e extrai titulo, severidade, UIDs e se a causa raiz e inconclusiva; verificar com testes de um e de varios problemas e de severidade invalida ou ausente
- [x] 2.2 Tratar separadores de UID (virgula, espaco, quebra de linha), UID fora do lote e UID repetido em dois problemas; verificar com testes que cobrem cada caso e o warning emitido
- [x] 2.3 Tratar resposta vazia ou sem secao de problema; verificar com teste que o resultado indica "sem problemas"

## 3. Persistencia (swap)

- [x] 3.1 Criar `analysis/swap.py` com a substituicao condicional: bloqueio da linha do lote `EM_ANALISE`, reaproveitamento como primeiro problema, insercao dos demais e heranca do `attempt_count`; verificar com teste de integracao de dois e tres problemas
- [x] 3.2 Implementar o relatorio INCOMPLETO para UIDs nao referenciados e o caso de causa raiz inconclusiva; verificar com teste de integracao que o `attempt_count` herdado impede a reanalise ao atingir `ANALYSIS_MAX_ATTEMPTS`
- [x] 3.3 Implementar o descarte quando o relatorio do lote ja nao esta `EM_ANALISE`; verificar com teste em que o lote e marcado INCOMPLETO antes do swap e nenhum relatorio novo aparece
- [x] 3.4 Implementar `mark_incomplete` condicional e o retry com backoff das gravacoes, com log do Markdown na falha definitiva; verificar com testes que simulam falha transitoria e definitiva do banco

## 4. Agente

- [x] 4.1 Criar `agents/mcp.py` que conecta em `MCP_SERVER_URL` com `transport: "http"` e filtra as tools por lista de permissao; verificar com teste que so `kubectl_get`, `kubectl_describe` e `kubectl_logs` passam, mesmo quando o servidor oferece tools de escrita
- [x] 4.2 Criar `agents/prompt.py` com o prompt do PRD 002 e `agents/analyst.py` com `create_agent`, `ChatAnthropic(max_retries=3)` e `ModelCallLimitMiddleware`; verificar com teste usando modelo falso que o prompt recebe os eventos e que o agente roda ate o fim
- [x] 4.3 Detectar o limite de iteracoes no resultado; verificar com teste de modelo falso que nunca conclui e confirma o resultado INCOMPLETO

## 5. Orquestracao e fiacao

- [x] 5.1 Criar `analysis/analyzer.py` que executa o agente, o parser e o swap, e leva a `mark_incomplete` em MCP indisponivel, erro do Claude, limite de iteracoes e resposta vazia; verificar com testes de integracao de cada caminho de falha, sem propagar excecao
- [x] 5.2 No `lifespan` do `main.py`, instanciar o `AnalysisHandler` com o `analyzer` e passa-lo ao `EventCollector`; verificar que a aplicacao inicia e que o teste de startup existente continua passando
- [x] 5.3 Remover `collector/handler.py` e `tests/collector/test_handler.py`; verificar que `uv run pytest` passa sem eles e que nada mais os importa

## 6. Verificacao integrada

- [x] 6.1 Teste de ponta a ponta do coletor ao relatorio com cluster e agente falsos: um lote vira relatorios por problema e o ciclo seguinte ignora os eventos; adaptar `tests/integration/test_end_to_end.py`
- [ ] 6.2 Validar no kind (conforme `docs/validacao-coleta-kind.md`) um Warning real (por exemplo `ImagePullBackOff`), conferindo um relatorio `COMPLETO` com severidade e sem tool de escrita invocada; registrar o resultado no mesmo documento
- [x] 6.3 Rodar `openspec validate agente-analise-causa-raiz --strict`; verificar que passa
