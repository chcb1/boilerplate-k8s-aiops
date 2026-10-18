# Tasks

## 1. Setup

- [x] 1.1 Adicionar `kubernetes` com `uv add kubernetes` e `pytest`/`pytest-asyncio` como dependencias de desenvolvimento; verificar com `uv sync` e `uv run python -c "import kubernetes"`
- [x] 1.2 Documentar `ANALYSIS_MAX_ATTEMPTS` (padrao 3) e `EVENT_COLLECTION_INTERVAL_MINUTES` na tabela de variaveis do `CLAUDE.md`; verificar que a tabela lista as duas com padrao

## 2. Coletor sem estado (kubernetes-event-collection)

- [x] 2.1 Implementar a leitura de `EVENT_COLLECTION_INTERVAL_MINUTES` com fallback para 3 e warning em valor invalido; verificar com teste unitario para `5`, `abc`, `0` e `-2`
- [x] 2.2 Implementar a transformacao do evento do SDK para o contrato de saida, com precedencia `series.last_observed_time` → `event_time` → `deprecated_last_timestamp`, descarte com warning sem timestamp e namespace vazio para recurso cluster-scoped; verificar com testes unitarios para cada cenario da spec
- [x] 2.3 Implementar a listagem `type=Warning` de todos os namespaces, paginada com `limit`/`continue`, via `asyncio.to_thread`, com `load_incluster_config()` e fallback para `load_kube_config()`; verificar com teste que simula o cliente e confirma o `field_selector`, o agrupamento das paginas e a ausencia de filtro temporal
- [x] 2.4 Tratar falhas de conectividade e RBAC com log (incluindo a permissao necessaria) sem interromper o loop; verificar com teste que injeta `ApiException` 403 e erro de conexao e confirma o ciclo seguinte
- [x] 2.5 Criar `EventHandler` com `async def handle(events)` e implementacao placeholder que exibe os eventos coletados no stdout com `print(..., flush=True)` (nao via `logging`, que vai para stderr), um cabecalho por lote com a quantidade e um JSON por evento no formato do contrato, e captura suas proprias excecoes; verificar com teste (`capsys`) que o lote aparece no stdout com um JSON valido por evento, e com teste em que `handle` lanca erro e nada propaga
- [x] 2.6 Implementar o loop: coleta imediata, depois sleep do intervalo, despacho via `asyncio.create_task` com referencia forte guardada, sem despacho quando a lista e vazia; verificar com teste que usa handler lento e confirma que o ciclo seguinte executa no horario e que o start dispara a coleta sem esperar o intervalo
- [x] 2.7 Iniciar e cancelar a task do coletor no `lifespan` de `main.py`; verificar subindo a aplicacao com `uv run uvicorn my_agent_app.main:app` e conferindo o log da primeira coleta e o shutdown limpo

## 3. Modelo de relatorios

- [x] 3.1 Modelar a tabela de relatorios (id UUID, markdown, status, `event_uids` TEXT[] com GIN index, `attempt_count` inteiro padrao 1, `created_at`, `updated_at`) e configurar Alembic com a migration inicial; verificar com `uv run alembic upgrade head` em banco limpo e conferencia do schema no PostgreSQL
- [x] 3.2 Garantir que `updated_at` seja atualizado em toda transicao de status; verificar com teste de integracao que muda o status e compara `updated_at`

## 4. Deduplicacao (event-deduplication)

- [x] 4.1 Implementar a consulta de overlap `event_uids && :uids` e a classificacao por uid (sem relatorio, ativo, CORRIGIDO, INCOMPLETO) conforme D4, comparando datetimes em UTC; verificar com testes de integracao para os cenarios de relatorio ativo, sem relatorio, CORRIGIDO com reincidencia e sem reincidencia, e CORRIGIDO e ativo coexistindo
- [x] 4.2 Implementar a regra de INCOMPLETO por presenca com limite `ANALYSIS_MAX_ATTEMPTS`, incluindo a regra quando o uid tem CORRIGIDO e INCOMPLETO, e o warning ao atingir o limite; verificar com testes abaixo, no limite e acima dele
- [x] 4.3 Implementar a marcacao de EM_ANALISE estagnado como INCOMPLETO (`ANALYSIS_STALE_TIMEOUT_MINUTES`, padrao 30) dentro da dedup; verificar com teste de relatorio EM_ANALISE antigo seguido de nova dedup
- [x] 4.4 Implementar o trecho atomico: `pg_advisory_xact_lock`, estagnados, classificacao e insert do relatorio EM_ANALISE com `attempt_count = 1 + max` dos INCOMPLETO envolvidos, tudo na mesma transacao; verificar com teste de integracao que dispara dois lotes concorrentes com o mesmo uid e confirma um unico relatorio EM_ANALISE
- [x] 4.5 Garantir que o agente so seja chamado apos o commit e nao seja chamado quando nada resta a analisar; verificar com teste que usa agente simulado em lote totalmente ignorado e em lote misto
- [x] 4.6 Tratar banco indisponivel na dedup descartando o lote com log, sem propagar; verificar com teste que derruba a conexao e confirma que o coletor continua e o evento volta no ciclo seguinte
- [x] 4.7 Marcar relatorios EM_ANALISE orfaos como INCOMPLETO no startup; verificar com teste que insere um EM_ANALISE e reinicia o lifespan

## 5. Integracao e documentacao dos PRDs

- [x] 5.1 Teste de integracao ponta a ponta com cliente Kubernetes simulado e PostgreSQL local (`docker compose up -d`): Warning novo e analisado uma vez, repete no ciclo seguinte sem reanalise, falha de infraestrutura e retentada no ciclo seguinte; verificar com `uv run pytest` passando
- [x] 5.2 Reconciliar `docs/prds/001-coleta-eventos-kubernetes.md` (remover marca d'agua, adicionar coleta no start, novos edge cases e riscos) e `docs/prds/002-agente-analise-causa-raiz.md` (regras de dedup por timestamp, tentativas, atomicidade); verificar com busca por "marca d'agua" nos dois arquivos sem restar referencia ao comportamento antigo

## 6. Validacao local com kind

Usa o cluster kind ja existente (`kind-kube-news`) e os manifestos de `manifestos-k8s/`: `nginx.yaml` (imagem inexistente `ngin:latest`, esperado ErrImagePull/ImagePullBackOff) e `kube-news.yaml` (10 replicas do `kubenews` com senha de banco divergente do `postgre`, esperado BackOff/falhas). Os Warnings esperados devem ser confirmados com `kubectl get events` antes de comparar com a saida do coletor.

- [x] 6.1 Confirmar o ambiente: `kind get clusters` lista `kube-news`, `kubectl config current-context` e `kind-kube-news` e `kubectl get nodes` mostra os nos Ready; se o cluster nao existir, cria-lo com `kind create cluster --name kube-news`
- [x] 6.2 Aplicar `manifestos-k8s/nginx.yaml` e `manifestos-k8s/kube-news.yaml` (`kubectl apply -f manifestos-k8s/`) e registrar a referencia com `kubectl get events -A --field-selector type=Warning`; verificar que existem Warnings de ao menos dois workloads (ex.: `Failed`/`BackOff` do nginx e do kubenews)
- [x] 6.3 Subir a aplicacao com `uv run uvicorn my_agent_app.main:app` contra o kind (kubeconfig local, intervalo de 1 minuto via `EVENT_COLLECTION_INTERVAL_MINUTES=1`) e verificar no stdout que a primeira coleta ocorre logo apos o start, sem esperar o intervalo, e que cada Warning aparece como JSON no formato do contrato (`uid`, `type`, `reason`, `message`, `namespace`, `involved_object`, `timestamp`)
- [x] 6.4 Comparar a saida do coletor com `kubectl get events -A --field-selector type=Warning -o json`: verificar que todos os `metadata.uid` dos Warnings vivos aparecem no stdout, que nenhum evento Normal aparece e que o `timestamp` segue a precedencia (conferir ao menos um evento com `series` e um sem; se o cluster nao gerar `series`, criar um `Event` `events.k8s.io/v1` sintetico)
- [x] 6.5 Verificar o ciclo seguinte: os Warnings ainda vivos reaparecem no stdout (lote completo, sem filtro temporal) e o ciclo executa no intervalo configurado; verificar pelos cabecalhos de lote com horarios no stdout
- [x] 6.6 Verificar o restart: parar e subir a aplicacao de novo e confirmar que a primeira coleta entrega os Warnings ainda vivos sem depender de estado anterior
- [x] 6.7 Verificar resiliencia a falhas de acesso: com a aplicacao rodando, interromper o acesso ao cluster (ex.: kubeconfig apontando para uma porta local fechada, religada depois com `socat`; evita parar o control-plane de um cluster com outros workloads) e confirmar erro em log e loop vivo, e que a coleta volta no ciclo seguinte
- [x] 6.8 Verificar RBAC: executar com um kubeconfig/ServiceAccount sem permissao de `list` em `events` (ex.: `kubectl create serviceaccount sem-acesso` e token) e confirmar que o log indica a permissao necessaria e o loop continua
- [x] 6.9 Verificar a deduplicacao com eventos reais do kind, usando PostgreSQL local e um analisador simulado que apenas registra "analisando <uid>": no primeiro ciclo os uids sao analisados uma vez, nos ciclos seguintes sao ignorados (relatorio ativo), e ao marcar um relatorio como INCOMPLETO no banco o evento e reanalisado ate `ANALYSIS_MAX_ATTEMPTS`
- [x] 6.10 Limpar o ambiente de teste (`kubectl delete -f manifestos-k8s/`) e registrar o resultado das verificacoes 6.1 a 6.9 (evidencias de stdout e comandos usados) em um documento curto de validacao junto a change ou em `docs/`
