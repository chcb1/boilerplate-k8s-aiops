# Design

## Context

A aplicacao ja serve a pagina inicial com Jinja2 (`web/router.py`, `templates/base.html`, `error.html`) e guarda o `sessionmaker` em `app.state` no `lifespan`. A tabela `reports` tem `status`, `severity`, `markdown`, `event_uids`, `attempt_count` e timestamps, mas nao tem titulo. O `base.html` ja define as classes de badge dos seis status e um cabecalho com links "Tasks" e "Health". O `Problem.title` ja e extraido pelo parser e descartado no swap. Motivacao e escopo: ver proposal.md; requisitos: ver specs.

Dois fatos medidos com a biblioteca `markdown` 3.10.2 moldam o desenho: HTML cru e links `javascript:` passam sem alteracao, e um comando com `*x*` fora de bloco cercado sai com `<em>`.

## Goals / Non-Goals

**Goals:**
- Paginas de leitura simples, testaveis sem navegador, que nao exponham XSS a partir de texto gerado por LLM.
- Falhas de banco reconhecidas como indisponibilidade (503), inclusive conexao recusada.

**Non-Goals:**
- Botao de correcao, endpoint `fix` e tratamento do 409 (PRD 004).
- Autenticacao, paginacao, filtros, busca e atualizacao automatica da pagina.
- Backfill de titulo para relatorios anteriores.

## Decisions

**1. Rotas em `web/router.py`, renderizacao em `web/markdown.py`.**
As rotas `GET /reports` e `GET /reports/{id}` ficam no router existente, que e onde o PRD 004 vai colocar o `POST .../fix`. A conversao Markdown para HTML seguro fica num modulo proprio, funcao pura testavel sem banco. A sessao vem de `request.app.state.sessionmaker`, o que permite aos testes injetarem o `sessionmaker` de integracao sem executar o `lifespan` (que sobe o coletor).

**2. Sanitizacao com `nh3` depois do render.**
`markdown.markdown(texto, extensions=["fenced_code", "tables"])` seguido de `nh3.clean` com lista de tags permitidas (titulos, paragrafos, listas, enfase, `code`, `pre`, `blockquote`, tabelas, `a`, `hr`, `br`), atributos restritos (`href` em `a`, `class` em `code`) e esquemas `http`, `https` e `mailto`. O resultado e marcado como seguro no template somente apos a limpeza. Alternativas descartadas: escapar `<` antes do render (quebra citacoes `>` e nao cobre `javascript:`) e `bleach` (descontinuado).

**3. Titulo como coluna, nao parse na listagem.**
Coluna `title VARCHAR(255)` anulavel, gravada pelo swap a partir de `Problem.title` (truncado em 255 no parser). Evita carregar o Markdown de todas as linhas para montar a listagem. Relatorios sem titulo (analise incompleta, eventos nao referenciados) exibem texto substituto montado a partir do status e do inicio do ID. Alternativa descartada: regex sobre `markdown` na listagem, por custo e fragilidade.

**4. Listagem seleciona so colunas necessarias, com teto de 200.**
A consulta le `id`, `title`, `severity`, `status`, `created_at` e a quantidade de eventos, ordena por `created_at DESC` e aplica `LIMIT 201`; a 201a linha so serve para decidir se o aviso de omissao aparece. O Markdown nunca e carregado na listagem.

**5. Erros de banco por tratadores de excecao do app.**
Tratadores registrados em `main.py` para `SQLAlchemyError`, `ConnectionError` e `TimeoutError` renderizam `error.html` com 503. Nao se captura `OSError` inteiro para nao mascarar falhas nao relacionadas, como arquivo de template ausente. Conexao recusada com asyncpg levanta `ConnectionRefusedError`, que e `ConnectionError` e nao `SQLAlchemyError`, motivo pelo qual capturar so SQLAlchemy nao basta.

**6. ID como `str`, convertido na rota.**
Declarar `{id}` como `uuid.UUID` faria o FastAPI responder 422 em JSON para um ID malformado. A rota recebe `str`, converte com `uuid.UUID` e trata `ValueError` e relatorio ausente da mesma forma: 404 com `error.html`.

**7. Interface sem mutacao.**
Somente rotas `GET`; o FastAPI responde 405 para outros metodos. O template de detalhe nao tem formularios. O PRD 004 acrescenta o botao, o `POST` e a secao "Resultado da Correcao" sobre estas paginas.

**8. Prompt: comando em bloco cercado.**
A secao "Comando Sugerido" do formato de resposta passa a mostrar o comando dentro de um bloco ` ```bash `. O parser nao depende dessa secao, entao o parse existente nao muda.

**9. Estilos e navegacao no `base.html`.**
Link "Relatórios" no `nav` ao lado dos existentes; classes de severidade e estilos do conteudo renderizado (titulos, listas, tabelas, `pre`) em `extra_style` dos templates, para nao inflar o estilo global.

## Risks / Trade-offs

- [Sem autenticacao, qualquer um com acesso de rede le dados internos do cluster] → Documentado no `CLAUDE.md`; o comando padrao ainda usa `--host 0.0.0.0`, entao quem expoe a porta deve restringir por rede. A exposicao passa a ser grave quando o PRD 004 acrescentar a execucao, e deve ser reavaliada la.
- [Allowlist do `nh3` pode remover marcacao legitima que o modelo produza] → Testes com tabelas, listas e blocos; ampliar a lista se aparecerem casos reais.
- [Relatorios anteriores ficam sem titulo] → Texto substituto na interface; sem backfill por serem poucos e de desenvolvimento.
- [`LIMIT 200` esconde relatorios antigos] → Aviso explicito na pagina; paginacao fica para quando o volume justificar.
- [Prompt alterado pode mudar o formato que o LLM devolve] → O parser so usa cabecalho, severidade, eventos e causa raiz; ha teste do prompt cobrindo o bloco cercado.

## Migration Plan

1. `uv add nh3` e `uv run alembic upgrade head` (coluna `title` anulavel, sem backfill).
2. Subir a aplicacao e abrir `/reports`.
3. Rollback: `alembic downgrade -1` remove a coluna; as rotas novas podem ser removidas sem efeito sobre o restante.
