# Design

## Context

O `AnalysisHandler` (`analysis/handler.py`) ja faz dedup e cria o relatorio `EM_ANALISE` do lote, depois chama um `analyzer(report_id, events)` injetado que ainda nao existe. `recover_orphans` ja roda no startup. O `main.py` liga o coletor ao handler placeholder que imprime no stdout, entao o `AnalysisHandler` nunca e instanciado. A tabela `reports` tem `attempt_count` e nao tem severidade. As dependencias `langchain[anthropic]` e `langchain-mcp-adapters` ja estao no `pyproject.toml`. Motivacao e escopo: ver proposal.md; requisitos: ver specs.

## Goals / Non-Goals

**Goals:**
- Fechar o pipeline coleta, dedup, agente e relatorios por problema, com o limite de tentativas valendo em todos os caminhos de falha.
- Manter o agente estritamente somente leitura.

**Non-Goals:**
- Saida estruturada do LLM (`ProviderStrategy`); o mapeamento continua por parse do Markdown (decisao D1 do PRD 002).
- Deduplicacao por `involvedObject`, tela de relatorios e correcao automatica.

## Decisions

**1. Pacotes: `agents/` para o agente, `analysis/` para o fluxo.**
`agents/` ganha `analyst.py` (monta o agente e roda), `mcp.py` (conexao e filtro de tools), `prompt.py` e `config.py` (`AGENT_MODEL_NAME`, `AGENT_MAX_ITERATIONS`). `analysis/` ganha `parser.py` (Markdown para problemas), `swap.py` (persistencia) e `analyzer.py` (orquestra: agente, parser, swap). O `analyzer` e a funcao entregue ao `AnalysisHandler`, que ja trata excecoes. Alternativa descartada: um unico modulo grande, pois o parser e o swap precisam de teste sem LLM nem rede.

**2. Tools filtradas por nome, em lista de permissao.**
O cliente `MultiServerMCPClient` usa `transport: "http"` em `MCP_SERVER_URL`; as tools retornadas sao filtradas para `{kubectl_get, kubectl_describe, kubectl_logs}`. Lista de permissao, e nao de bloqueio, para que tools novas do MCP Server nao cheguem ao agente. As tools sao obtidas a cada analise (sem sessao persistente), de modo que um MCP Server reiniciado nao deixa o agente preso a uma conexao morta; falha ao obte-las e falha de infraestrutura.

**3. Modelo e retries.**
`ChatAnthropic(model=AGENT_MODEL_NAME, max_retries=3)` e `create_agent` com `ModelCallLimitMiddleware(run_limit=AGENT_MAX_ITERATIONS, exit_behavior="end")`. A validacao de `AGENT_MAX_ITERATIONS` reaproveita o helper de inteiro positivo de `analysis/config.py`. O limite e detectado pela mensagem sentinela que o middleware injeta ao encerrar (`exit_behavior="end"`), e nao pela contagem de chamadas, para nao marcar INCOMPLETO um agente que conclui exatamente na ultima iteracao permitida. Como cada chamada ao modelo consome varios passos do LangGraph (hooks do middleware, modelo e tools; cerca de 3 medidos), o `recursion_limit` da execucao e definido explicitamente, folgado acima do limite do middleware (4 x `AGENT_MAX_ITERATIONS` + margem); estourar esse limite tambem conta como limite atingido.

**4. Parser tolerante e sem LLM.**
O parser divide a resposta em secoes `## Problema N:`, extrai `Severidade`, `Eventos` e o texto de **Causa Raiz**, e valida os UIDs contra o lote (ignora desconhecidos; UID repetido fica no primeiro problema). Um problema que fica sem nenhum UID valido e descartado com warning, e seus eventos caem entre os nao referenciados. Causa raiz iniciada por "inconclusiva" (sem distincao de maiusculas) torna o problema INCOMPLETO. Alternativa descartada: saida estruturada, por decisao D1.

**5. Swap numa transacao, condicional ao status.**
`SELECT ... WHERE id = :batch AND status = 'EM_ANALISE' FOR UPDATE`; sem linha, descarta e avisa (D3 do PRD). Com linha, o relatorio do lote vira o primeiro problema (`UPDATE`: markdown, status, severity, event_uids) e os demais viram `INSERT`, todos com o `attempt_count` do lote. UIDs nao referenciados formam um relatorio INCOMPLETO adicional com `markdown` vazio. Sem problemas parseaveis, a linha do lote vira INCOMPLETO com a resposta bruta e todos os UIDs. O `updated_at` e preenchido pelo `onupdate` ja existente. Reaproveitar a linha preserva `created_at` e evita um DELETE; a alternativa de apagar e reinserir foi descartada.

**6. Falhas viram INCOMPLETO por um unico caminho.**
Um `mark_incomplete(report_id, markdown)` condicional a `EM_ANALISE` e usado para MCP indisponivel, erro do Claude, limite de iteracoes e resposta vazia. Isso garante que todo caminho de falha respeita D3 e que o evento volta pela regra de INCOMPLETO.

**7. Persistencia com retry curto.**
Gravacoes do swap e do `mark_incomplete` usam 3 tentativas com backoff exponencial em erros de conexao do banco; apos a ultima, loga erro com o Markdown. Nao ha fallback em arquivo (PRD 002).

**8. Severidade em coluna.**
Coluna `severity VARCHAR(16)` anulavel, adicionada por migration Alembic. Valores validos: CRITICO, ALTO, MEDIO, BAIXO; qualquer outro vira nulo com warning. Existe para a listagem do PRD 003 nao parsear Markdown por linha.

**9. Fiacao e remocao do placeholder.**
O `lifespan` cria o `AnalysisHandler(sessionmaker, analyzer)` e o passa ao `EventCollector`. `collector/handler.py` e `tests/collector/test_handler.py` sao removidos, junto do requisito de stdout (delta `REMOVED`).

## Risks / Trade-offs

- [Parse depende do formato que o LLM devolve] → O prompt exige o formato, o parser e tolerante, e o que nao e referenciado vira INCOMPLETO contado no limite de tentativas.
- [Deteccao do limite depende do texto da mensagem sentinela do middleware na versao instalada] → Teste que roda o agente com um modelo falso que nunca conclui e confirma o resultado INCOMPLETO; o teste quebra se a dependencia mudar a mensagem.
- [Analise mais longa que `ANALYSIS_STALE_TIMEOUT_MINUTES`] → O swap condicional descarta o resultado; o timeout deve ficar acima do pior caso do agente, e isso e documentado no CLAUDE.md.
- [Custo de tokens] → `AGENT_MAX_ITERATIONS` e `ANALYSIS_MAX_ATTEMPTS`; modelo padrao Haiku.
- [Prompt injection via logs e eventos] → O agente so le o cluster, nao tem tool de escrita. O conteudo do Markdown continua nao confiavel para quem o exibe (tratado no PRD 003).

## Migration Plan

1. Rodar `uv run alembic upgrade head` (nova coluna anulavel; sem backfill, relatorios antigos ficam sem severidade).
2. Subir o MCP Server e configurar `ANTHROPIC_API_KEY`.
3. Rollback: `alembic downgrade -1` remove a coluna; reverter o `main.py` restaura o handler que imprime no stdout.
