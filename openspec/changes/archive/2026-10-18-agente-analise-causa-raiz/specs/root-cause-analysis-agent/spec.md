# Spec Delta

## Purpose

Investigar automaticamente a causa raiz dos eventos Warning de um lote por meio de um agente de IA com acesso somente leitura ao cluster Kubernetes, produzindo um diagnostico em Markdown e tratando as falhas de infraestrutura sem afetar o coletor.

## ADDED Requirements

### Requirement: Analise de cada lote deduplicado
O sistema SHALL, para cada lote que restar apos a deduplicacao, executar o agente de analise sobre os eventos selecionados, vinculado ao relatorio EM_ANALISE criado para o lote, e SHALL nao executar o agente quando nada restar a analisar.

#### Scenario: Lote com eventos novos
- **WHEN** a deduplicacao seleciona eventos e cria o relatorio EM_ANALISE
- **THEN** o agente e executado sobre esses eventos

#### Scenario: Lote sem eventos a analisar
- **WHEN** todos os eventos do lote sao ignorados pela deduplicacao
- **THEN** o agente nao e executado

#### Scenario: Handler de analise ligado ao coletor
- **WHEN** a aplicacao inicia
- **THEN** os lotes entregues pelo coletor sao tratados pelo fluxo de deduplicacao e analise

### Requirement: Acesso somente leitura ao cluster
O sistema SHALL expor ao agente apenas as tools `kubectl_get`, `kubectl_describe` e `kubectl_logs` do MCP Server Kubernetes, e SHALL nao expor nenhuma tool de escrita.

#### Scenario: Tools disponiveis ao agente
- **WHEN** o agente e criado
- **THEN** a lista de tools contem exatamente `kubectl_get`, `kubectl_describe` e `kubectl_logs`

#### Scenario: Tool de escrita presente no MCP Server
- **WHEN** o MCP Server oferece `kubectl_apply`, `kubectl_patch` ou `kubectl_delete`
- **THEN** essas tools nao sao vinculadas ao agente

### Requirement: Investigacao por problema agrupado
O sistema SHALL instruir o agente a investigar por problema agrupado, e nao por evento individual, e a responder somente com o relatorio em Markdown, com uma secao por problema contendo severidade, namespace, recursos afetados, eventos, causa raiz, evidencias, solucao recomendada e comando sugerido.

#### Scenario: Eventos do mesmo problema
- **WHEN** o lote contem varios eventos causados pelo mesmo problema
- **THEN** o agente os reporta em uma unica secao de problema

#### Scenario: Evento ja corrigido entre coleta e analise
- **WHEN** o recurso do evento ja esta saudavel durante a investigacao
- **THEN** o relatorio registra o estado saudavel como evidencia

### Requirement: Modelo e limite de iteracoes configuraveis
O sistema SHALL ler o modelo de `AGENT_MODEL_NAME` (padrao `claude-haiku-4-5`) e o limite de chamadas ao modelo de `AGENT_MAX_ITERATIONS` (padrao 25), e SHALL usar o padrao e registrar um warning quando `AGENT_MAX_ITERATIONS` for nao numerico, zero ou negativo.

#### Scenario: Modelo alterado por variavel
- **WHEN** `AGENT_MODEL_NAME` define outro modelo
- **THEN** o agente usa esse modelo sem mudanca de codigo

#### Scenario: Limite invalido
- **WHEN** `AGENT_MAX_ITERATIONS` e `abc`, `0` ou `-3`
- **THEN** o limite usado e 25 e um warning e registrado no log

### Requirement: Limite de iteracoes sem conclusao
O sistema SHALL encerrar a investigacao ao atingir `AGENT_MAX_ITERATIONS` chamadas ao modelo e SHALL marcar o relatorio do lote como INCOMPLETO, preservando em `markdown` o que o agente tiver produzido.

#### Scenario: Limite atingido
- **WHEN** o agente atinge o limite sem concluir a investigacao
- **THEN** o relatorio do lote fica INCOMPLETO e nenhum relatorio COMPLETO e criado a partir desse resultado

### Requirement: Falha de infraestrutura aborta a analise
O sistema SHALL, quando o MCP Server estiver indisponivel ou a API do Claude falhar apos as tentativas automaticas (`max_retries=3` com backoff), abortar a analise, marcar o relatorio do lote como INCOMPLETO e registrar o erro em log, sem propagar a falha ao coletor.

#### Scenario: MCP Server indisponivel
- **WHEN** a conexao com o MCP Server falha ao iniciar a analise
- **THEN** o relatorio do lote fica INCOMPLETO e o erro e registrado

#### Scenario: Erro persistente da API do Claude
- **WHEN** a API do Claude falha em todas as tentativas
- **THEN** o relatorio do lote fica INCOMPLETO e o loop de coleta continua

#### Scenario: Erro de execucao de uma tool
- **WHEN** uma tool retorna erro de execucao, como parametros invalidos
- **THEN** o erro volta ao modelo para auto-correcao e a analise nao e abortada

### Requirement: Analise nao bloqueia a coleta
O sistema SHALL executar a analise sem bloquear o ciclo de coleta, de modo que uma analise mais longa que o intervalo de coleta nao atrase o ciclo seguinte.

#### Scenario: Analise longa
- **WHEN** a analise de um lote dura mais que o intervalo de coleta
- **THEN** o ciclo seguinte executa no horario previsto e seus eventos ja em analise sao ignorados pela deduplicacao
