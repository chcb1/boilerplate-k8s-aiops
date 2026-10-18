# report-web-ui Specification

## Purpose

Permitir que o operador consulte pelo navegador os relatorios de analise de causa raiz, listando-os por recencia e exibindo o conteudo completo de cada um de forma segura, sem alterar nenhum dado.

## Requirements

### Requirement: Listagem de relatorios
O sistema SHALL oferecer em `GET /reports` uma pagina que lista os relatorios ordenados por `created_at` decrescente, exibindo para cada um o titulo, a severidade, o status, a data de criacao e o inicio do ID, com um link para a pagina de detalhe.

#### Scenario: Ordem por recencia
- **WHEN** existem relatorios criados em momentos diferentes
- **THEN** o mais recente aparece primeiro

#### Scenario: Item leva ao detalhe
- **WHEN** o operador clica no titulo de um relatorio
- **THEN** a pagina de detalhe daquele relatorio e aberta

#### Scenario: Relatorio sem severidade
- **WHEN** o relatorio nao tem severidade
- **THEN** a coluna de severidade exibe um marcador de ausencia

### Requirement: Titulo de relatorio ausente
O sistema SHALL exibir um texto substituto na listagem e no detalhe quando o relatorio nao tiver titulo, sem expor valor vazio.

#### Scenario: Relatorio sem titulo
- **WHEN** o relatorio nao tem titulo, como os de analise incompleta
- **THEN** a listagem exibe um texto substituto identificando o relatorio

### Requirement: Listagem limitada
O sistema SHALL exibir no maximo os 200 relatorios mais recentes e SHALL informar na pagina quando houver relatorios omitidos.

#### Scenario: Mais de 200 relatorios
- **WHEN** existem mais de 200 relatorios
- **THEN** somente os 200 mais recentes sao listados e a pagina avisa que ha outros

### Requirement: Listagem vazia
O sistema SHALL exibir a mensagem "Nenhum relatório encontrado" quando nao houver relatorios.

#### Scenario: Banco sem relatorios
- **WHEN** a tabela de relatorios esta vazia
- **THEN** a pagina exibe a mensagem informativa e nenhuma tabela

### Requirement: Status como badge
O sistema SHALL exibir o status de cada relatorio como badge cuja classe corresponda ao status: EM_ANALISE `badge-processing`, COMPLETO `badge-complete`, INCOMPLETO `badge-incomplete`, CORRIGINDO `badge-executing`, CORRIGIDO `badge-executed` e FALHA_CORRECAO `badge-execution-failed`.

#### Scenario: Badge de relatorio completo
- **WHEN** o relatorio esta COMPLETO
- **THEN** o badge usa a classe `badge-complete` e o texto do status

### Requirement: Acesso pelo cabecalho
O sistema SHALL exibir no cabecalho comum de todas as paginas um link "Relatórios" para a listagem.

#### Scenario: Link em qualquer pagina
- **WHEN** qualquer pagina e exibida, inclusive as de erro
- **THEN** o cabecalho contem o link "Relatórios" para `/reports`

### Requirement: Detalhe do relatorio
O sistema SHALL oferecer em `GET /reports/{id}` uma pagina que exibe o titulo, o status, a severidade, as datas de criacao e atualizacao, o numero de tentativas, a quantidade de eventos e o conteudo Markdown do relatorio renderizado em HTML.

#### Scenario: Relatorio completo
- **WHEN** o operador abre um relatorio COMPLETO
- **THEN** a pagina exibe os metadados e o conteudo renderizado

#### Scenario: Estrutura do Markdown
- **WHEN** o conteudo contem listas, tabelas e blocos de codigo
- **THEN** cada um e renderizado com a estrutura correspondente

### Requirement: Conteudo sanitizado
O sistema SHALL sanitizar o HTML gerado a partir do Markdown antes de exibi-lo, removendo scripts, atributos de evento e links com esquemas diferentes de http, https e mailto.

#### Scenario: Script no relatorio
- **WHEN** o Markdown contem uma tag `script` ou `img` com `onerror`
- **THEN** o HTML exibido nao contem o script nem o atributo de evento

#### Scenario: Link javascript
- **WHEN** o Markdown contem um link com destino `javascript:`
- **THEN** o HTML exibido nao contem esse destino

#### Scenario: Link seguro preservado
- **WHEN** o Markdown contem um link `https`
- **THEN** o link e exibido com o destino original

### Requirement: Comando sugerido preservado
O sistema SHALL exibir o conteudo de blocos de codigo cercados exatamente como foi escrito, sem aplicar formatacao Markdown ao seu interior.

#### Scenario: Comando com asteriscos
- **WHEN** o Markdown tem um bloco cercado contendo `kubectl patch ... "*x*"`
- **THEN** o texto exibido mantem os asteriscos e nao contem a tag `em`

### Requirement: Relatorio sem conteudo
O sistema SHALL exibir na pagina de detalhe uma mensagem informativa quando o Markdown do relatorio estiver vazio, indicando analise em andamento para EM_ANALISE e analise sem conteudo para os demais status.

#### Scenario: Relatorio em analise
- **WHEN** o relatorio esta EM_ANALISE e nao tem Markdown
- **THEN** a pagina informa que a analise esta em andamento

#### Scenario: Relatorio incompleto sem Markdown
- **WHEN** o relatorio esta INCOMPLETO e o Markdown esta vazio
- **THEN** a pagina informa que nao ha conteudo de analise

### Requirement: Relatorio inexistente
O sistema SHALL responder com status 404 e uma pagina informativa quando o ID nao corresponder a nenhum relatorio ou nao for um UUID valido.

#### Scenario: ID inexistente
- **WHEN** o ID e um UUID bem formado sem relatorio
- **THEN** a resposta tem status 404 e uma pagina informativa

#### Scenario: ID malformado
- **WHEN** o ID nao e um UUID
- **THEN** a resposta tem status 404 e a mesma pagina informativa

### Requirement: Banco indisponivel
O sistema SHALL responder com status 503 e a mensagem "Banco de dados indisponível, tente novamente em instantes" quando a consulta falhar por erro de banco ou de conexao, sem expor detalhes tecnicos.

#### Scenario: Erro de consulta
- **WHEN** o banco levanta um erro durante a consulta
- **THEN** a resposta tem status 503 e a mensagem informativa

#### Scenario: Conexao recusada
- **WHEN** a conexao com o banco e recusada
- **THEN** a resposta tem status 503 e a mensagem informativa

### Requirement: Interface somente leitura
O sistema SHALL expor as paginas de relatorios apenas por leitura, sem controles que alterem dados ou acionem a correcao.

#### Scenario: Detalhe sem acao de correcao
- **WHEN** a pagina de detalhe de um relatorio COMPLETO e exibida
- **THEN** ela nao contem formulario nem botao que altere dados

#### Scenario: Metodos que alteram dados
- **WHEN** uma requisicao POST e enviada a `/reports` ou `/reports/{id}`
- **THEN** a resposta tem status 405
