# Spec Delta

## Purpose

Decidir, a partir dos relatorios existentes, quais eventos coletados devem ser analisados, evitando analises duplicadas e reanalise infinita, e retentando eventos cuja analise falhou.

## ADDED Requirements

### Requirement: Evento com relatorio ativo e ignorado
O sistema SHALL ignorar um evento cujo `uid` esteja vinculado a ao menos um relatorio com status EM_ANALISE, COMPLETO, CORRIGINDO ou FALHA_CORRECAO, independentemente de existirem tambem relatorios antigos com o mesmo `uid` em outros status.

#### Scenario: Relatorio ativo
- **WHEN** um evento chega com `uid` vinculado a um relatorio COMPLETO
- **THEN** o evento nao e analisado

#### Scenario: Ativo e antigo coexistem
- **WHEN** o `uid` esta vinculado a um relatorio CORRIGIDO antigo e a um relatorio EM_ANALISE
- **THEN** o evento nao e analisado

### Requirement: Evento sem relatorio e analisado
O sistema SHALL analisar um evento cujo `uid` nao esteja vinculado a nenhum relatorio, em qualquer ciclo em que ele ainda esteja vivo no cluster.

#### Scenario: Evento novo
- **WHEN** um evento chega com `uid` sem relatorio
- **THEN** o evento e incluido na analise

#### Scenario: Retentativa apos falha de infraestrutura
- **WHEN** a analise de um evento falhou antes de existir relatorio para ele e o evento continua no cluster
- **THEN** ele e incluido na analise no ciclo seguinte

### Requirement: Reincidencia apos relatorio CORRIGIDO
O sistema SHALL reanalisar um evento vinculado apenas a relatorios CORRIGIDO somente quando o `timestamp` do evento for posterior ao `updated_at` do relatorio CORRIGIDO mais recente que contem o `uid`.

#### Scenario: Evento reincide depois da correcao
- **WHEN** o `timestamp` do evento e posterior ao `updated_at` do relatorio CORRIGIDO
- **THEN** o evento e reanalisado e gera novo relatorio

#### Scenario: Evento ainda vivo apos a correcao
- **WHEN** o `timestamp` do evento e anterior ou igual ao `updated_at` do relatorio CORRIGIDO
- **THEN** o evento nao e reanalisado

### Requirement: Reanalise de INCOMPLETO por presenca com limite
O sistema SHALL reanalisar um evento vinculado apenas a relatorios INCOMPLETO enquanto ele estiver presente no cluster e o total de tentativas de analise do `uid` for menor que o limite configurado.

#### Scenario: Analise incompleta retentada
- **WHEN** um evento vinculado a relatorio INCOMPLETO esta abaixo do limite de tentativas
- **THEN** o evento e reanalisado e o contador de tentativas e incrementado

#### Scenario: Limite de tentativas atingido
- **WHEN** o contador de tentativas do evento atinge o limite
- **THEN** o evento deixa de ser reanalisado e um warning e registrado no log

#### Scenario: Limite configuravel
- **WHEN** o limite e alterado por variavel de ambiente
- **THEN** o novo valor passa a valer sem mudanca de codigo

### Requirement: Deduplicacao e criacao do relatorio atomicas
O sistema SHALL decidir quais eventos analisar e criar o relatorio EM_ANALISE correspondente na mesma transacao, de modo que dois lotes concorrentes nao analisem o mesmo evento.

#### Scenario: Lotes sobrepostos
- **WHEN** dois lotes com o mesmo `uid` sao tratados ao mesmo tempo
- **THEN** apenas um cria o relatorio EM_ANALISE e analisa o evento

#### Scenario: Ciclo seguinte durante analise longa
- **WHEN** o ciclo seguinte entrega um `uid` cuja analise ainda esta em andamento
- **THEN** o evento e ignorado por ter relatorio EM_ANALISE

### Requirement: Recuperacao de EM_ANALISE estagnado
O sistema SHALL marcar como INCOMPLETO os relatorios EM_ANALISE com mais de `ANALYSIS_STALE_TIMEOUT_MINUTES` minutos (padrao 30) durante a deduplicacao, liberando seus eventos para reanalise conforme o limite de tentativas.

#### Scenario: Analise estagnada
- **WHEN** um relatorio esta em EM_ANALISE alem do timeout
- **THEN** ele e marcado INCOMPLETO e seus eventos passam a seguir a regra de INCOMPLETO

### Requirement: Lote sem eventos a analisar
O sistema SHALL nao disparar o agente quando, apos a deduplicacao, nao restar nenhum evento a analisar.

#### Scenario: Todos ja tratados
- **WHEN** todos os eventos do lote sao ignorados pela deduplicacao
- **THEN** nenhuma analise e iniciada

### Requirement: Falha do banco na deduplicacao
O sistema SHALL registrar em log o erro e descartar o lote quando o banco estiver indisponivel durante a deduplicacao, sem afetar o coletor.

#### Scenario: Banco indisponivel
- **WHEN** a consulta de deduplicacao falha
- **THEN** o lote e descartado, o erro e registrado e os eventos vivos sao retentados no ciclo seguinte
