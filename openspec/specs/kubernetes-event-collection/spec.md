# kubernetes-event-collection Specification

## Purpose

Coletar periodicamente e sem estado os eventos Warning vivos do cluster Kubernetes e entrega-los, no formato de um contrato definido, ao pipeline de analise sem bloquear o ciclo de coleta.

## Requirements

### Requirement: Coleta imediata no start
O sistema SHALL executar a primeira coleta de eventos logo apos o start da aplicacao, sem aguardar o primeiro intervalo configurado.

#### Scenario: Primeira coleta no start
- **WHEN** a aplicacao e iniciada
- **THEN** uma coleta e executada imediatamente e as seguintes ocorrem a cada intervalo configurado

#### Scenario: Restart nao depende de estado anterior
- **WHEN** a aplicacao reinicia com Warnings ainda vivos no cluster
- **THEN** a primeira coleta apos o restart entrega esses Warnings sem usar nenhum estado de coletas anteriores

### Requirement: Coleta periodica de Warnings de todos os namespaces
O sistema SHALL, a cada ciclo, listar os eventos do tipo Warning de todos os namespaces do cluster, sem filtro temporal, usando o Python SDK do Kubernetes.

#### Scenario: Apenas Warning
- **WHEN** o cluster contem eventos Warning e Normal
- **THEN** somente os eventos Warning sao entregues

#### Scenario: Todos os namespaces
- **WHEN** existem Warnings em namespaces distintos
- **THEN** todos sao incluidos no mesmo ciclo

#### Scenario: Warning ja entregue em ciclo anterior
- **WHEN** um Warning continua vivo no cluster no ciclo seguinte
- **THEN** ele e entregue novamente, e a decisao de nao reprocessa-lo cabe a deduplicacao

### Requirement: Intervalo de coleta configuravel
O sistema SHALL ler o intervalo do ciclo, em minutos, da variavel de ambiente `EVENT_COLLECTION_INTERVAL_MINUTES`, com padrao de 3 minutos.

#### Scenario: Valor valido
- **WHEN** a variavel e `5`
- **THEN** o ciclo executa a cada 5 minutos

#### Scenario: Valor invalido
- **WHEN** a variavel e nao numerica, zero ou negativa
- **THEN** o sistema usa 3 minutos e registra um warning no log

### Requirement: Timestamp do evento por precedencia
O sistema SHALL definir o campo `timestamp` de cada evento entregue, em ISO 8601, pela precedencia `series.lastObservedTime`, `eventTime`, `deprecatedLastTimestamp`.

#### Scenario: Evento recorrente com series
- **WHEN** o evento tem `series.lastObservedTime` e um `eventTime` anterior
- **THEN** o `timestamp` entregue e o `series.lastObservedTime`

#### Scenario: Evento sem series
- **WHEN** o evento nao tem `series` mas tem `eventTime`
- **THEN** o `timestamp` entregue e o `eventTime`

#### Scenario: Evento de controller legado
- **WHEN** o evento so tem `deprecatedLastTimestamp`
- **THEN** o `timestamp` entregue e o `deprecatedLastTimestamp`

#### Scenario: Evento sem nenhum timestamp
- **WHEN** o evento nao tem nenhum dos tres campos
- **THEN** o evento e descartado e um warning e registrado no log

### Requirement: Contrato de saida dos eventos
O sistema SHALL entregar cada evento como um dicionario com `uid`, `type`, `reason`, `message`, `namespace`, `involved_object` (`kind`, `name`, `namespace`) e `timestamp`, com nomes desacoplados do SDK.

#### Scenario: Mapeamento de campos
- **WHEN** um evento e transformado
- **THEN** `message` vem de `note` e `involved_object` vem de `regarding`

#### Scenario: Recurso cluster-scoped
- **WHEN** o evento se refere a um recurso sem namespace, como um Node
- **THEN** `involved_object.namespace` e uma string vazia

### Requirement: Despacho assincrono sem bloqueio
O sistema SHALL agrupar os eventos de um ciclo e despacha-los ao handler de forma assincrona, sem aguardar sua conclusao e sem que erros do handler afetem o ciclo de coleta.

#### Scenario: Ciclo nao espera o handler
- **WHEN** o handler leva mais tempo que o intervalo de coleta
- **THEN** o proximo ciclo executa no horario previsto

#### Scenario: Erro no handler
- **WHEN** o handler lanca erro ao processar um lote
- **THEN** o erro e tratado pelo handler e o loop de coleta continua

#### Scenario: Nenhum Warning no cluster
- **WHEN** a listagem nao retorna nenhum Warning
- **THEN** nenhum lote e despachado

### Requirement: Resiliencia a falhas de acesso ao cluster
O sistema SHALL registrar em log as falhas de conectividade ou de permissao (RBAC) ao listar eventos e continuar o loop, tentando novamente no proximo ciclo.

#### Scenario: Cluster inacessivel
- **WHEN** a listagem falha por falta de conectividade
- **THEN** o erro e registrado e o loop segue para o proximo ciclo

#### Scenario: Permissao insuficiente
- **WHEN** a listagem falha por falta de permissao para listar eventos
- **THEN** o log indica a permissao necessaria e o loop continua
