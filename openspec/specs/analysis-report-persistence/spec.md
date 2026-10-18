# analysis-report-persistence Specification

## Purpose

Persistir o resultado da analise como relatorios por problema no PostgreSQL, com status, severidade e eventos vinculados, substituindo o relatorio provisorio do lote de forma segura contra concorrencia e recuperando analises interrompidas.

## Requirements

### Requirement: Um relatorio por problema
O sistema SHALL converter a resposta do agente em um relatorio por problema identificado, cada um com ID unico, titulo, o Markdown da secao do problema, status, severidade e os `event_uids` listados no campo **Eventos** daquela secao.

#### Scenario: Dois problemas independentes
- **WHEN** a resposta contem duas secoes de problema com eventos distintos
- **THEN** sao persistidos dois relatorios, cada um com seus `event_uids`

#### Scenario: Severidade extraida
- **WHEN** a secao do problema traz `**Severidade:** ALTO`
- **THEN** o relatorio e persistido com severidade `ALTO`

#### Scenario: Severidade ausente ou invalida
- **WHEN** a secao nao traz severidade reconhecivel entre CRITICO, ALTO, MEDIO e BAIXO
- **THEN** a severidade do relatorio fica vazia e um warning e registrado

#### Scenario: Titulo extraido
- **WHEN** a secao do problema tem o cabecalho `## Problema 1: Pod em OOMKilled`
- **THEN** o relatorio e persistido com o titulo `Pod em OOMKilled`

#### Scenario: Titulo longo
- **WHEN** o titulo do problema excede 255 caracteres
- **THEN** o titulo persistido e truncado em 255 caracteres

#### Scenario: Relatorio sem problema identificavel
- **WHEN** o relatorio nao corresponde a um problema, como o de eventos nao referenciados
- **THEN** o titulo do relatorio fica vazio

### Requirement: Mapeamento de eventos tolerante
O sistema SHALL extrair os UIDs do campo **Eventos** separados por virgula, espaco ou quebra de linha, SHALL ignorar UIDs que nao pertencam ao lote, e SHALL atribuir a um UID repetido em mais de um problema apenas o primeiro, registrando warning.

#### Scenario: UID inventado
- **WHEN** o campo **Eventos** contem um UID que nao esta no lote
- **THEN** esse UID e ignorado e um warning e registrado

#### Scenario: UID em dois problemas
- **WHEN** o mesmo UID do lote aparece em dois problemas
- **THEN** ele fica vinculado somente ao primeiro

### Requirement: Substituicao condicional do relatorio do lote
O sistema SHALL substituir o relatorio EM_ANALISE do lote pelos relatorios por problema numa unica transacao, e SHALL faze-lo somente se esse relatorio ainda estiver EM_ANALISE; caso contrario, SHALL descartar o resultado do agente e registrar warning.

#### Scenario: Analise concluida a tempo
- **WHEN** o agente conclui e o relatorio do lote continua EM_ANALISE
- **THEN** os relatorios por problema sao persistidos na mesma transacao

#### Scenario: Relatorio liberado durante a analise
- **WHEN** o relatorio do lote foi marcado INCOMPLETO por estagnacao ou por recuperacao de startup enquanto o agente rodava
- **THEN** o resultado do agente e descartado e nenhum relatorio e criado

### Requirement: Relatorio do lote reaproveitado
O sistema SHALL reaproveitar o relatorio do lote como o primeiro relatorio por problema, preservando seu `id` e `created_at`, e inserir os demais problemas como novos relatorios.

#### Scenario: Lote com tres problemas
- **WHEN** a resposta tem tres problemas
- **THEN** o relatorio do lote passa a representar o primeiro e dois novos relatorios sao criados

### Requirement: Status do relatorio apos a analise
O sistema SHALL persistir cada relatorio por problema como COMPLETO, exceto quando a causa raiz for declarada inconclusiva, caso em que SHALL persisti-lo como INCOMPLETO.

#### Scenario: Causa raiz identificada
- **WHEN** a secao do problema traz uma causa raiz conclusiva
- **THEN** o relatorio fica COMPLETO

#### Scenario: Causa raiz inconclusiva
- **WHEN** a secao do problema declara a causa raiz como inconclusiva
- **THEN** o relatorio fica INCOMPLETO

### Requirement: Tentativas herdadas pelos novos relatorios
O sistema SHALL atribuir a todo relatorio criado na substituicao o `attempt_count` do relatorio do lote, de modo que o limite `ANALYSIS_MAX_ATTEMPTS` continue valendo.

#### Scenario: Reanalise inconclusiva
- **WHEN** a terceira tentativa de analise gera um relatorio INCOMPLETO por problema
- **THEN** o relatorio tem `attempt_count` 3 e o evento nao e reanalisado alem do limite

### Requirement: Eventos nao referenciados
O sistema SHALL vincular os eventos do lote que nao constam do campo **Eventos** de nenhum problema a um relatorio INCOMPLETO proprio, com o `attempt_count` do lote, e registrar um warning.

#### Scenario: Evento omitido pelo agente
- **WHEN** um UID do lote nao aparece em nenhum problema da resposta
- **THEN** ele e vinculado a um relatorio INCOMPLETO e deixa de ser reanalisado sem teto

### Requirement: Resposta sem problemas identificaveis
O sistema SHALL marcar o relatorio do lote como INCOMPLETO, preservando a resposta bruta em `markdown`, quando a resposta do agente for vazia ou nao contiver nenhuma secao de problema.

#### Scenario: Resposta vazia
- **WHEN** o agente responde sem texto
- **THEN** o relatorio do lote fica INCOMPLETO com todos os seus eventos

### Requirement: Persistencia resiliente
O sistema SHALL repetir a gravacao com backoff quando o PostgreSQL estiver indisponivel e, esgotadas as tentativas, SHALL registrar o erro em log incluindo o Markdown gerado, sem propagar a falha ao coletor.

#### Scenario: Banco volta durante as tentativas
- **WHEN** o banco falha na primeira gravacao e responde na seguinte
- **THEN** o relatorio e persistido normalmente

#### Scenario: Banco indisponivel definitivamente
- **WHEN** todas as tentativas falham
- **THEN** o erro e o Markdown gerado sao registrados no log e o relatorio EM_ANALISE e recuperado pela regra de estagnacao

### Requirement: Recuperacao no startup
O sistema SHALL marcar como INCOMPLETO, ao iniciar, os relatorios que estiverem EM_ANALISE, liberando seus eventos para reanalise conforme o limite de tentativas.

#### Scenario: Restart durante uma analise
- **WHEN** a aplicacao reinicia com um relatorio EM_ANALISE
- **THEN** ele passa a INCOMPLETO e um warning e registrado

### Requirement: Fluxo de status dos relatorios
O sistema SHALL restringir as transicoes feitas por esta capability a EM_ANALISE para COMPLETO ou INCOMPLETO, deixando CORRIGINDO, CORRIGIDO e FALHA_CORRECAO para a capability de correcao.

#### Scenario: Analise nao altera relatorio em correcao
- **WHEN** o resultado de uma analise chega para um relatorio que nao esta EM_ANALISE
- **THEN** o relatorio nao e alterado
