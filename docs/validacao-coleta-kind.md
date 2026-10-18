# Validacao local da coleta de eventos com kind

Change: `coleta-sem-marca-dagua-dedup-por-timestamp` — executada em 2026-10-18 contra o cluster
`kind-kube-news` (kind, Kubernetes v1.37.0, 1 control-plane + 1 worker) com os manifestos de
`manifestos-k8s/` aplicados no namespace `default`. Os workloads reais do namespace `kube-news`
nao foram tocados.

## Resultado

| Tarefa | Verificacao | Resultado |
|---|---|---|
| 6.1 | Cluster `kube-news` existe, contexto `kind-kube-news`, nos Ready | OK |
| 6.2 | `kubectl apply -f manifestos-k8s/` gera Warnings de 2 workloads (`kubenews`, `nginx`) | OK — 33 Warnings `Failed` (30 `kubenews`, 3 `nginx`) |
| 6.3 | Primeira coleta logo no start; um JSON por evento no stdout | OK — `lote: 33 evento(s) Warning`, JSON no contrato |
| 6.4 | UIDs do stdout x `kubectl get events`; nenhum Normal; precedencia de timestamp | OK — 33/33 UIDs iguais, 0 Normal no stdout (53 vivos no cluster); timestamps monotonicos (ver notas) |
| 6.5 | Lote completo repetido a cada ciclo no intervalo | OK — lotes as 18:18:25, 18:19:25 e seguinte (1 min), 33 eventos cada |
| 6.6 | Restart sem estado anterior | OK — nova execucao entregou os 35 Warnings vivos ja na primeira coleta |
| 6.7 | Cluster inacessivel e retorno | OK — 1 erro em log, HTTP 200 mantido, coleta voltou no ciclo seguinte |
| 6.8 | RBAC (ServiceAccount sem `list events`) | OK — erro claro a cada ciclo (2 ciclos), loop vivo, stdout vazio |
| 6.9 | Dedup com eventos reais, Postgres local e analisador simulado | OK — ver abaixo |
| 6.10 | Limpeza | OK — manifestos, pod, evento sintetico e ServiceAccount removidos |

### 6.9 Dedup com eventos reais

`RUN_KIND_TESTS=1 uv run pytest tests/integration/test_kind_dedup.py -s`

- Ciclo 1: 35 eventos analisados (um relatorio EM_ANALISE criado).
- Ciclo 2: os mesmos eventos continuam vivos e nao sao reanalisados (relatorio ativo).
- Relatorio marcado INCOMPLETO: reanalise nos ciclos seguintes (tentativas 2 e 3).
- Com `ANALYSIS_MAX_ATTEMPTS=3` atingido: nenhuma reanalise.

## Notas e achados

- **`eventTime: null` e universal aqui.** Todos os 86 eventos de `events.k8s.io/v1` do cluster
  (kubelet e scheduler incluidos) chegam com `eventTime: null`, sem `series`, e so com
  `deprecatedLastTimestamp`. O modelo pydantic do SDK `kubernetes` 37 rejeita `eventTime` nulo
  (a pagina inteira falharia), por isso a listagem le o JSON cru (`_preload_content=False`).
- **`series` nao ocorre naturalmente neste kind.** Para exercitar a precedencia, foi criado um
  `Event` `events.k8s.io/v1` sintetico com `eventTime` 30 min antes de `series.lastObservedTime`; o
  coletor entregou `timestamp = lastObservedTime`. Em controllers que usam o recorder novo isso e
  esperado, mas nao foi observado em um evento real do cluster.
- **Divergencias de timestamp contra o snapshot de `kubectl`**: 11 dos 33 eventos tinham
  `timestamp` posterior ao snapshot tirado antes da coleta. Sao recorrencias do kubelet (mesmo
  UID, `lastTimestamp` avancando por BackOff); `snapshot <= stdout <= estado atual` vale para todos.
- **`kubenews` nao entra em CrashLoopBackOff**: os pods ficam em `ImagePullBackOff`
  (`no match for platform in manifest` para `fabricioveronez/kube-news:v1`), entao a divergencia de
  senha do banco nao chega a ser exercitada. Os Warnings gerados (`Failed`) cobrem a validacao.
- **6.7 sem `docker stop`**: para nao derrubar o control-plane do cluster com outros workloads, a
  indisponibilidade foi simulada apontando o kubeconfig para uma porta local fechada e depois abrindo
  um encaminhamento (`socat`) para a API real.
- O PostgreSQL local (`docker compose up -d postgres`) foi mantido em execucao; os testes de
  integracao usam o banco `aiops_k8s_test`, criado automaticamente.
