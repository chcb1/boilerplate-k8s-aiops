# Spec Delta

## REMOVED Requirements

### Requirement: Exibicao dos eventos coletados no stdout
**Reason**: O requisito valia apenas enquanto o processamento real nao existisse. Com o handler de analise ligado ao coletor, os lotes passam a ser deduplicados e analisados, e o stdout deixa de ser o destino dos eventos.
**Migration**: Os eventos de cada lote sao tratados pelo fluxo de deduplicacao e analise (`event-deduplication`, `root-cause-analysis-agent`); para depuracao, usar o log da aplicacao.
