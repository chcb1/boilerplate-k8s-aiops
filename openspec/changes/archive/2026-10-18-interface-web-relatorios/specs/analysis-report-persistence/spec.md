# Spec Delta

## MODIFIED Requirements

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
