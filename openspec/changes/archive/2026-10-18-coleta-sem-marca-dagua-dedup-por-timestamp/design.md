# Design

## Context

Ver proposal.md (Why) para a motivacao. Estado atual: `collector/`, `agents/` e `models/` sao placeholders vazios; `main.py` so cria o engine async e o sessionmaker no `lifespan`; `kubernetes` nao esta no `pyproject.toml`. Os PRDs 001 e 002 descrevem a versao com marca d'agua em memoria e dedup sem comparacao de timestamp, e serao reconciliados com esta change.

Restricoes relevantes:
- A API do Kubernetes nao filtra eventos por tempo no servidor; so `type` vai como `field_selector`.
- Eventos vivem ate o TTL do apiserver (padrao 1h; clusters gerenciados podem variar).
- O SDK `kubernetes` e sincrono: chamadas via `asyncio.to_thread`.
- Uma instancia da aplicacao por cluster; sem coordenacao entre replicas na v1.

## Goals / Non-Goals

**Goals:**
- Coletor sem estado: restart seguro e retentativa natural de eventos nao tratados dentro do TTL.
- Reincidencia decidida no banco, por relatorio, e nao por relogio em memoria.
- Nenhuma analise duplicada entre ciclos, mesmo com despacho fire-and-forget.
- Teto no gasto de tokens com reanalise de INCOMPLETO.

**Non-Goals:**
- Dedup por `involvedObject` + `reason` + `namespace` (limitacao do EventAggregator segue como risco aceito do PRD 002).
- Persistencia de eventos brutos.
- Coordenacao entre multiplas replicas.
- Reanalise de INCOMPLETO apos o evento sumir do cluster (TTL).

## Decisions

### D1. Coletor lista tudo a cada ciclo e nao guarda estado
O ciclo chama `EventsV1Api.list_event_for_all_namespaces(field_selector="type=Warning")` e transforma cada evento no contrato; o `timestamp` segue a precedencia `series.lastObservedTime` → `eventTime` → `deprecatedLastTimestamp`. A listagem usa `_preload_content=False` e le o JSON cru: o modelo pydantic do SDK (v37) rejeita `eventTime: null`, que e como a API serve eventos de controllers legados, derrubando a pagina inteira; por isso a transformacao opera sobre dicts com os nomes camelCase da API. Alternativa descartada: manter a marca d'agua. Ela nao reduz trafego (filtro e client-side), perde eventos cujo processamento falhou e some no restart.

### D2. Primeira coleta antes do primeiro sleep
O loop executa `collect()` e so depois `sleep(intervalo)`. A task nasce no `lifespan` do FastAPI e e cancelada no shutdown. A primeira coleta nao bloqueia o start: roda como task. A task guarda referencia forte (atributo em `app.state`) para nao ser coletada pelo GC; o mesmo vale para as tasks do handler (conjunto com `add_done_callback(discard)`).

### D3. Paginacao com `limit` e `continue`
A listagem usa paginas (ex.: 500) acumulando em memoria ate montar o lote do ciclo. Alternativa: sem paginacao, como no PRD. Escolhida a paginacao por custo baixo e para evitar picos em clusters grandes; o lote continua unico por ciclo.

### D4. Dedup decide em SQL, no handler
O handler consulta os relatorios cujo `event_uids` sobrepoe os uids do lote (`&&`, GIN) e classifica cada uid:

```
 uid -> relatorios que o contem
   sem nenhum                     -> ANALISAR
   algum ativo                    -> IGNORAR
   so CORRIGIDO                   -> ANALISAR se ts_evento > max(updated_at)
   so INCOMPLETO (e/ou CORRIGIDO) -> ANALISAR se tentativas < limite
```

Quando o uid tem CORRIGIDO e INCOMPLETO, vale a regra de INCOMPLETO apenas se o INCOMPLETO for mais recente que o CORRIGIDO; caso contrario vale a de CORRIGIDO. A comparacao usa datetimes com timezone (UTC). Alternativa descartada: comparar com `created_at`, pois a transicao para CORRIGIDO e o instante relevante e so `updated_at` o reflete.

### D5. Tentativas como coluna do relatorio
Nova coluna `attempt_count` (inteiro, padrao 1). Um novo relatorio criado pela reanalise de uids INCOMPLETO recebe `1 + max(attempt_count)` dos INCOMPLETO que contem esses uids. O limite vem de `ANALYSIS_MAX_ATTEMPTS` (padrao 3). Alternativa: contador por uid em tabela propria — mais preciso, mas exige tabela adicional; o maximo por relatorio basta porque o lote reanalisado e tratado como uma unidade.

### D6. Atomicidade com advisory lock transacional
Na mesma transacao: `pg_advisory_xact_lock(chave fixa)`, consulta de dedup, marcacao de EM_ANALISE estagnado como INCOMPLETO e insert do relatorio EM_ANALISE com os uids a analisar. O lock serializa apenas esse trecho (curto), nao a analise do agente. Alternativas: constraint unica em array (nao expressa overlap de `TEXT[]`), `SERIALIZABLE` com retry (mais complexo), tabela auxiliar uid→relatorio com PK (mais robusta, porem muda o modelo). Escolhido o advisory lock pela simplicidade na v1 com instancia unica; ele tambem funciona com mais replicas, pois o lock e do banco.

### D7. Ordem do trecho transacional
(1) marcar EM_ANALISE estagnados como INCOMPLETO; (2) classificar uids; (3) se nada a analisar, commit e sair sem chamar o agente; (4) inserir o relatorio EM_ANALISE e commitar; (5) so entao chamar o agente. O relatorio e criado antes da chamada ao LLM (insert-first, como no PRD 002).

### D8. Estrategia de testes e validacao
Tres niveis: (1) testes unitarios com pytest (transformacao, precedencia de timestamp, intervalo, handler via `capsys`); (2) testes de integracao com PostgreSQL local do `docker compose` e cliente Kubernetes simulado (dedup, atomicidade, tentativas); (3) validacao manual guiada no kind existente `kind-kube-news` com `manifestos-k8s/nginx.yaml` (imagem inexistente) e `manifestos-k8s/kube-news.yaml` (banco com senha divergente), comparando o stdout do coletor com `kubectl get events`. A exibicao no stdout usa `print(flush=True)` e nao `logging`, que o `basicConfig` envia a stderr. Alternativa descartada: depender so de mocks, que nao exercitam `series`, TTL e RBAC reais.

## Risks / Trade-offs

- [Lock de dedup vira gargalo] → o trecho e curto e roda uma vez por ciclo; reavaliar se o intervalo diminuir muito.
- [Consulta `&&` sobre todos os Warnings vivos a cada ciclo] → GIN index em `event_uids`; carga constante e pequena para o volume esperado.
- [Reanalise de INCOMPLETO consome tokens ate o limite] → `ANALYSIS_MAX_ATTEMPTS` limita o gasto por incidente; warning ao atingir o limite.
- [INCOMPLETO por estagnacao conta como tentativa] → intencional, para evitar loop; o limite default (3) deve acomodar falhas transitorias.
- [Evento one-shot e o TTL] → fora do TTL o evento some do cluster e e perdido; mitigado pela retentativa a cada ciclo.
- [Diferenca de relogio entre cluster e banco ao comparar `timestamp` com `updated_at`] → ambos em UTC; reincidencia muito proxima da transicao pode ser classificada errada; aceito na v1.
- [EventAggregator gera novos UIDs em alta frequencia] → continua risco aceito do PRD 002.
- [Handler recebe lote completo a cada ciclo] → quebra o contrato implicito de "so novidades"; qualquer consumidor futuro do handler deve assumir repeticao.
