# Proposal

## Why

O PRD 001 descreve a marca d'agua em memoria como "otimizacao de janela de query", mas a API do Kubernetes nao filtra eventos por tempo no servidor: o filtro e sempre client-side. Na pratica a marca d'agua decide quem e recoletado, e isso perde eventos: um evento cujo processamento falhou (banco fora, MCP fora, erro na API do Claude) fica com timestamp anterior a marca e nunca volta, embora continue no cluster ate o TTL do apiserver (~1h). A marca tambem sofre com atraso de escrita de series e diferenca de relogio, e e perdida a cada restart.

Como o estado de "ja tratado" ja vive no PostgreSQL (relatorios com `event_uids`), a marca em memoria e redundante. Mover a decisao de reincidencia para a deduplicacao, comparando timestamps com o relatorio, torna a coleta sem estado, restart-safe e retentavel, sem reabrir o loop de reanalise que a marca d'agua evitava implicitamente.

## What Changes

- **Coletor (PRD 001)**: remover a marca d'agua em memoria; executar a primeira coleta imediatamente no start da aplicacao (nao esperar o primeiro intervalo); a cada ciclo listar todos os eventos Warning vivos em todos os namespaces (`field_selector` `type=Warning`), sem filtro temporal, e despacha-los fire-and-forget ao `EventHandler`.
- **Coletor**: manter a precedencia `series.lastObservedTime` → `eventTime` → `deprecatedLastTimestamp` para o campo `timestamp` do contrato de saida (agora usado pela dedup, nao pelo coletor); eventos sem nenhum dos tres continuam descartados com warning.
- **Coletor**: a decisao de disparar analise passa a ser pos-dedup no handler; o coletor despacha sempre que houver Warnings, e "nenhum evento novo" e resolvido no handler.
- **Dedup (PRD 002)**: eventos com relatorio ativo (EM_ANALISE, COMPLETO, CORRIGINDO, FALHA_CORRECAO) continuam ignorados; evento com relatorio CORRIGIDO so e reanalisado se `timestamp do evento > updated_at do relatorio` (reincidencia real); evento com relatorio INCOMPLETO e reanalisado por presenca, limitado por um contador de tentativas configuravel; evento sem relatorio e analisado (cobre one-shot perdido por falha de infraestrutura).
- **Dedup**: a checagem de dedup e a criacao do relatorio EM_ANALISE passam a ser atomicas na mesma transacao, eliminando a corrida entre ciclos com despacho fire-and-forget.
- **Relatorios**: nova coluna de contador de tentativas de analise no relatorio, com limite configuravel por variavel de ambiente.
- **BREAKING** (contrato entre PRDs): o handler passa a receber a lista completa de Warnings vivos a cada ciclo, e nao apenas eventos novos desde a ultima coleta.

## Capabilities

### New Capabilities
- `kubernetes-event-collection`: coleta periodica e sem estado de eventos Warning do cluster, com primeira coleta no start, contrato de saida e despacho fire-and-forget ao handler.
- `event-deduplication`: decisao de quais eventos coletados devem ser analisados, com base nos relatorios existentes (status, `updated_at`, tentativas) e criacao atomica do relatorio EM_ANALISE.

### Modified Capabilities

Nenhuma. O projeto ainda nao possui specs em `openspec/specs/`; os dois PRDs sao a fonte atual do comportamento.

## Impact

- **Documentacao**: `docs/prds/001-coleta-eventos-kubernetes.md` e `docs/prds/002-agente-analise-causa-raiz.md` devem ser reconciliados com esta change (remocao da marca d'agua, novas regras de dedup, coluna de tentativas, atomicidade).
- **Codigo**: `src/my_agent_app/collector/` (loop de coleta, transformacao para o contrato, handler) e `src/my_agent_app/models/` (tabela de relatorios com `event_uids`, `updated_at` e tentativas) e `src/my_agent_app/main.py` (iniciar a task do coletor no lifespan, com coleta imediata). Hoje esses modulos sao placeholders vazios.
- **Dependencias**: adicao de `kubernetes` ao `pyproject.toml`.
- **Configuracao**: nova variavel de ambiente para o limite de tentativas de reanalise de relatorios INCOMPLETO (nome definido em design.md); `EVENT_COLLECTION_INTERVAL_MINUTES` e `ANALYSIS_STALE_TIMEOUT_MINUTES` mantidas.
- **Carga**: uma consulta de overlap de arrays (`event_uids`, GIN index) por ciclo cobrindo todos os Warnings vivos; leitura completa de `list_event_for_all_namespaces` a cada ciclo (paginacao via `limit`/`continue` considerada no design).
- **Operacao**: eventos nao tratados passam a ser retentados a cada ciclo ate o TTL do apiserver; depois disso somem do cluster e sao perdidos.
