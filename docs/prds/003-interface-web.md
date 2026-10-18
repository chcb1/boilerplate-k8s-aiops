---
prd_number: "003"
status: rascunho
priority: alta
created: 2026-06-16
issue:
depends_on: ["002"]
references: []
---

# PRD 003: Interface Web de Relatórios

## 1. Contexto

- **Sistema/produto**: Agente AIOps para Kubernetes — aplicação Python com FastAPI. O PRD 002 gera relatórios de análise de causa raiz e os persiste no PostgreSQL. Stack: Python, FastAPI, Jinja2, PostgreSQL.
- **Estado atual**: Os relatórios são gerados e armazenados no banco, mas não há forma de visualizá-los. O operador precisaria consultar o banco diretamente para acessar os resultados da análise.
- **Problema**: Sem interface de visualização, os relatórios não chegam a quem precisa agir. Além disso, não há ponto de acionamento para a correção (PRD 004) — o operador não consegue revisar o diagnóstico e disparar a resolução.

## 2. Solução Proposta

### Visão geral

- Interface web server-side renderizada com Jinja2 pela própria API FastAPI
- Página de listagem com todos os relatórios e seus status
- Página de detalhe com renderização segura do Markdown completo (somente leitura; o botão de correção pertence ao PRD 004)

### Decisões-chave

1. **Jinja2 para interface web** — Interface server-side renderizada pela própria API FastAPI, sem necessidade de frontend separado (React, Vue, etc.)
2. **Sem autenticação na v1** — Não haverá controle de acesso. Decisão aceita para simplificar a primeira entrega.

### Fora do escopo

- **Autenticação e autorização** — Não contemplado nesta versão
- **Filtros avançados ou busca na listagem** — Listagem simples sem paginação ou filtro
- **Dashboard com métricas agregadas** — Apenas listagem e detalhe de relatórios
- **Botão "Executar correção" e execução da correção** — Pertencem ao PRD 004 (o endpoint `POST /reports/{id}/fix`, o tratamento do 409 e a seção "Resultado da Correção"); esta entrega é somente leitura

## 3. Funcionalidades

### US01: Listagem de relatórios

Como engenheiro de plataforma, quero acessar uma página web com a listagem de todos os relatórios de análise, para ter visibilidade do histórico de problemas investigados no cluster.

**Rules:**
- A página exibe os relatórios ordenados por `created_at` decrescente (mais recente primeiro), limitada aos 200 mais recentes, com aviso quando houver omitidos; a consulta não carrega o Markdown
- Cada item da lista exibe: título do problema (coluna `title`, com texto substituto quando ausente), severidade (coluna `severity`; "—" quando ausente), status, data de criação (`created_at`) e o início do ID (cada relatório corresponde a um único problema — PRD 002)
- Cada item é clicável e leva à página de detalhe
- A página é servida pela própria API FastAPI com template Jinja2
- A listagem é alcançável a partir de qualquer página por um link "Relatórios" no cabeçalho comum (`base.html`)
- O status é exibido como badge com mapeamento para classes CSS do `base.html`: EM_ANALISE → `badge-processing`, COMPLETO → `badge-complete`, INCOMPLETO → `badge-incomplete`, CORRIGINDO → `badge-executing`, CORRIGIDO → `badge-executed`, FALHA_CORRECAO → `badge-execution-failed`

**Edge cases:**
- Nenhum relatório no banco → exibir página com mensagem informativa ("Nenhum relatório encontrado")
- Erro de conexão com o PostgreSQL → capturar exceção SQLAlchemy e renderizar `error.html` com `status_code=503` e mensagem "Banco de dados indisponível, tente novamente em instantes"

### US02: Visualização detalhada do relatório

Como engenheiro de plataforma, quero visualizar o conteúdo completo de um relatório, para avaliar a causa raiz identificada e os passos de correção recomendados.

**Rules:**
- A página renderiza o conteúdo Markdown completo do relatório em HTML
- Exibe o status atual do relatório
- O HTML gerado a partir do Markdown é sanitizado (`nh3`) antes de ser exibido, pois o texto vem de um LLM que lê logs arbitrários do cluster; blocos de código cercados são exibidos sem formatação Markdown
- Não há botão nem formulário nesta entrega: o botão "Executar correção" (COMPLETO ou FALHA_CORRECAO) e o tratamento do 409 são entregues pelo PRD 004
- O `id` do relatório é do tipo UUID; a rota recebe o parâmetro como texto e o converte, de modo que um ID malformado também resulta em 404 (e não em 422)

**Edge cases:**
- Relatório com Markdown malformado → comportamento nativo da biblioteca `markdown`: produz HTML parcial sem lançar exceção
- Relatório sem Markdown (EM_ANALISE, ou INCOMPLETO de eventos não referenciados) → mensagem informativa no lugar do conteúdo
- Relatório não encontrado ou ID malformado → página 404 com mensagem informativa

## 4. Critérios de Aceite

### Técnicos

| Critério | Método de verificação |
|----------|----------------------|
| Interface web lista os relatórios com status | Teste automatizado de integração e conferência com `curl` (`docs/validacao-interface-web.md`) |
| Página de detalhe renderiza Markdown completo | Teste automatizado com relatórios de diferentes complexidades |
| Conteúdo hostil (script, `onerror`, link `javascript:`) não chega ao navegador | Teste automatizado com payload no Markdown |
| Detalhe e listagem não oferecem controles que alterem dados | Teste automatizado (sem formulário; POST retorna 405) |

### De negócio

Este PRD é um habilitador de visualização; não possui métrica de negócio própria na v1. O valor é viabilizar o acesso aos relatórios gerados pelo PRD 002 e o acionamento da correção (PRD 004).

## 5. Milestones

### Milestone 1: Implementar Interface Web

**Objetivo:** Permitir visualização dos relatórios via navegador.

**Funcionalidades:** US01, US02

- [ ] Criar template Jinja2 de listagem de relatórios (US01)
- [ ] Criar rota FastAPI para listagem (`GET /reports`) (US01)
- [ ] Criar template Jinja2 de detalhe do relatório com renderização Markdown (US02)
- [ ] Criar rota FastAPI para detalhe (`GET /reports/{id: UUID}`) (US02)
- [ ] Tratar cenários de erro (banco indisponível, relatório não encontrado) (US01, US02)
- [ ] Sanitizar o HTML renderizado e persistir o título do problema (`title`) (US01, US02)
- [ ] Adicionar estilos CSS para conteúdo Markdown renderizado no template de detalhe (US02)
- [ ] Adicionar link "Relatórios" no cabeçalho (`base.html`) para tornar a listagem alcançável pela navegação (US01)

**Critério de conclusão:**
- Condição: Interface web exibe listagem e detalhe dos relatórios corretamente
- Verificação: Demo em navegador com relatórios reais gerados pelo PRD 002
- Aprovador: Time de SRE

## 6. Riscos e Dependências

| Risco | Impacto | Mitigação | Status |
|-------|---------|-----------|--------|
| Interface sem autenticação exposta indevidamente | Médio | Restringir acesso via rede (VPN, ingress interno). Documentar que v1 não tem auth | Pendente |

**Dependências:**

| Dependência | Tipo | Status | Impacto se bloqueado |
|-------------|------|--------|----------------------|
| PRD 002 — Relatórios no PostgreSQL | Interna | Em desenvolvimento | Sem relatórios, não há o que exibir |
| Jinja2 | Externa | Disponível | Renderização dos templates |
| Biblioteca de renderização Markdown → HTML (`markdown`) | Externa | Disponível — `markdown>=3.7` declarado em `pyproject.toml` | Necessária para exibir relatórios formatados |

## 7. Referências

- [PRD 002 - Agente de Análise](./002-agente-analise-causa-raiz.md) — fornece os relatórios exibidos
- [PRD 004 - Agente de Correção](./004-agente-correcao-automatica.md) — acionado pelo botão de correção na interface

## 8. Registro de Decisões

- **2026-10-18** — Escopo da v1 reduzido a leitura e requisitos de segurança acrescentados (change `interface-web-relatorios`): (1) o botão "Executar correção" e o tratamento do 409 passam para o PRD 004, que já define o endpoint e a seção "Resultado da Correção"; (2) a severidade vem da coluna `severity`, e não de parse do Markdown, e o título da coluna `title`; (3) o HTML é sanitizado, porque a biblioteca `markdown` deixa passar `<script>`, `onerror` e links `javascript:` e o texto vem de um LLM que lê logs arbitrários; (4) o 503 cobre também `ConnectionError` e `TimeoutError`, pois conexão recusada com asyncpg não é `SQLAlchemyError`; (5) ID malformado resulta em 404.
- **2026-07-23** — Adicionado link "Relatórios" no cabeçalho (`base.html`). Durante a validação manual (Milestone 1), constatou-se que a listagem só era acessível digitando a URL `/reports`: a navegação não oferecia caminho até ela. O menu comum passa a expor o link, tornando a feature alcançável a partir de qualquer página.
