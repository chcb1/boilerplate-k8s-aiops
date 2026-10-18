# Spec Delta

## MODIFIED Requirements

### Requirement: Investigacao por problema agrupado
O sistema SHALL instruir o agente a investigar por problema agrupado, e nao por evento individual, e a responder somente com o relatorio em Markdown, com uma secao por problema contendo severidade, namespace, recursos afetados, eventos, causa raiz, evidencias, solucao recomendada e comando sugerido, este em bloco de codigo cercado.

#### Scenario: Eventos do mesmo problema
- **WHEN** o lote contem varios eventos causados pelo mesmo problema
- **THEN** o agente os reporta em uma unica secao de problema

#### Scenario: Evento ja corrigido entre coleta e analise
- **WHEN** o recurso do evento ja esta saudavel durante a investigacao
- **THEN** o relatorio registra o estado saudavel como evidencia

#### Scenario: Comando sugerido em bloco cercado
- **WHEN** o agente propoe um comando de correcao
- **THEN** o comando aparece em um bloco de codigo cercado, e nao como texto corrido
