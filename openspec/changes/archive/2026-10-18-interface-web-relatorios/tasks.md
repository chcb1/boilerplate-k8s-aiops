# Tasks

## 1. Titulo do problema e comando cercado (ajustes no pipeline de analise)

- [x] 1.1 Adicionar a coluna anulavel `title` (`VARCHAR(255)`) a `Report` e criar a migration Alembic; verificar com `uv run alembic upgrade head` e `downgrade -1` num banco descartavel, e estender `tests/integration/test_report_model.py` para a coluna
- [x] 1.2 Truncar o titulo em 255 caracteres no parser e grava-lo no swap (linha do lote reaproveitada e linhas inseridas), deixando-o vazio nos relatorios de eventos nao referenciados e de resposta sem problemas; verificar com testes em `tests/analysis/test_parser.py` (titulo extraido e truncado) e `tests/integration/test_swap.py` (titulo persistido e nulo)
- [x] 1.3 Alterar a secao "Comando Sugerido" do prompt em `agents/prompt.py` para um bloco ` ```bash `; verificar com teste que o prompt contem o bloco cercado e que `parse_report` continua extraindo severidade, UIDs e causa raiz de uma resposta com o comando cercado

## 2. Renderizacao segura do Markdown

- [x] 2.1 Adicionar a dependencia `nh3` (`uv add nh3`) e criar `web/markdown.py` com a funcao de render (`fenced_code`, `tables`) seguida de `nh3.clean` com a allowlist do design; verificar com testes unitarios em `tests/web/test_markdown.py` para `script`, `img onerror`, link `javascript:`, link `https` preservado, tabela, lista e bloco cercado com `*x*` sem `em`

## 3. Paginas de relatorios

- [x] 3.1 Criar `GET /reports` e o template `reports.html` com colunas de titulo (com texto substituto), severidade (com marcador de ausencia), badge de status, data e inicio do ID, ordem `created_at DESC`, consulta que nao carrega `markdown`, teto de 200 com aviso e mensagem "Nenhum relatório encontrado"; verificar com testes de integracao em `tests/integration/test_web_reports.py` (cliente `httpx` sobre o app com o `sessionmaker` de teste) para ordem, badges por status, vazio, titulo ausente e mais de 200 relatorios
- [x] 3.2 Criar `GET /reports/{id}` e o template `report_detail.html` com titulo, status, severidade, datas, tentativas, quantidade de eventos e conteudo renderizado, mensagens para Markdown vazio (EM_ANALISE e demais status), 404 para ID inexistente ou malformado e nenhum formulario; verificar com testes de integracao para completo, vazio, 404 nos dois casos, conteudo sanitizado (payload com `script` e `javascript:`) e ausencia de `<form`
- [x] 3.3 Adicionar o link "Relatórios" ao `nav` do `base.html`, estilos de severidade e do conteudo renderizado, e ajustar o texto do link de retorno em `error.html`; verificar com testes que a home, a listagem e a pagina de erro contem o link para `/reports`
- [x] 3.4 Registrar em `main.py` os tratadores de `SQLAlchemyError`, `ConnectionError` e `TimeoutError` que renderizam `error.html` com 503 e a mensagem "Banco de dados indisponível, tente novamente em instantes"; verificar com testes cujo `sessionmaker` levanta `OperationalError` e `ConnectionRefusedError` nas duas rotas, sem detalhe tecnico na resposta, e com teste de que `POST /reports` retorna 405

## 4. Documentacao e verificacao integrada

- [x] 4.1 Documentar no `CLAUDE.md` as rotas `/reports` e `/reports/{id}` e a ausencia de autenticacao (com o aviso sobre `--host 0.0.0.0`), e atualizar `docs/prds/003-interface-web.md` (severidade lida da coluna, botao e 409 movidos para o PRD 004, 404 tambem para UUID malformado, sanitizacao); verificar com `grep` que cada um dos pontos aparece nos dois arquivos
- [x] 4.2 Validar no processo real: aplicar as migrations num banco descartavel, semear relatorios (COMPLETO com tabela e comando cercado, EM_ANALISE vazio, INCOMPLETO sem titulo e um com payload de XSS), subir `uvicorn` e conferir com `curl` a listagem, os detalhes, o 404 e o payload neutralizado; registrar o resultado em `docs/validacao-interface-web.md`
- [x] 4.3 Rodar `openspec validate interface-web-relatorios --strict` e `uv run pytest`; verificar que ambos passam
