# Apoio Escolar Periférico

> FIAP · Global Solution 2026.2 · CitizenTech · Engenharia de Software 4º ano (4ESPR)
> Disciplina: **Secure DevOps Tools & Cloud Computing** — atividade *CitizenTech no Ar*

[![CI/CD](../../actions/workflows/ci-cd.yml/badge.svg)](../../actions/workflows/ci-cd.yml)

## Ficha Técnica do MVP

| Campo | Resposta |
|---|---|
| **Nome do produto** | Apoio Escolar Periférico |
| **Cidadão e território** | Estudantes de escolas públicas (6º ano do EF à 3ª série do EM) de comunidades periféricas; piloto pensado para bairros da periferia de São Paulo. Também atende responsáveis e voluntários. |
| **Problema, em uma frase** | Estudantes de periferia não encontram reforço escolar gratuito perto de casa, enquanto voluntários e materiais existem, mas estão espalhados e sem um ponto de encontro seguro para menores. |
| **Proposta de valor** | Um só lugar, leve no celular, que conecta o estudante a monitorias voluntárias no bairro, materiais gratuitos e um tutor virtual, guardando o mínimo de dados e com autorização do responsável. |
| **Arquitetura: componentes** | Web app Flask no Azure App Service (este repositório) · API v1 de integração · tutor IA (GenAI) · leitura de comprovante por foto (Visão) · robô UiPath de cadastro e boletim (RPA) · pipeline de dados educacionais (Big Data) · suporte físico para tablet comunitário (Maker Lab). Diagrama em [docs/arquitetura.md](docs/arquitetura.md). |
| **Fontes de dados** | Bases educacionais abertas (IDEB e indicadores escolares do INEP), tratadas pelo pipeline da disciplina de Dados. Neste repositório, as monitorias iniciais são **dados simulados** marcados como “[Demonstração]” e os materiais são links para recursos públicos gratuitos. |
| **Modelos de IA utilizados** | Tutor de estudos com IA generativa (disciplina de GenAI) e OCR de comprovantes (disciplina de Visão). Este app consome os dois por API e nunca envia a identidade do aluno. |
| **URL do MVP e repositório** | MVP: <https://app-apoioescolar-6e7462.azurewebsites.net> · Repositório: <https://github.com/FIAP-BitsNBytes/fiap-4espr-gs-devops> |
| **Indicadores de impacto** | Alunos ativos por bairro · inscrições em monitorias · vagas ofertadas × preenchidas · voluntários ativos · retenção de alunos (expostos de forma agregada em `/api/v1/indicadores`). |
| **ODS conectados** | ODS 4 (Educação de Qualidade) e ODS 10 (Redução das Desigualdades). |

**Equipe BitsNBytes (4ESPR):** Jó Sales (RM 552679) · Miguel Garcez de Carvalho (RM 553768) · Vinicius Souza e Silva (RM 552781) · Edson Leonardo (RM 553737) · Eduardo (RM a preencher).

## O que esta entrega cobre

| Critério (14 pts) | Onde está | Como comprovar |
|---|---|---|
| **Deploy** (3,5) | App Service Linux, HTTPS only, TLS 1.2, Health Check — [infra/provisionar.sh](infra/provisionar.sh) | URL pública abrindo, `/health` respondendo |
| **CI/CD** (3,0) | [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml): lint → testes → segurança → pacote → deploy → smoke test, a cada commit na `main` | Execução verde no Actions com o hash do commit igual ao de `/health` |
| **Segurança** (3,0) | Segredos no Key Vault via Managed Identity, OIDC no deploy, RBAC de menor privilégio, LGPD by design — [docs/seguranca-lgpd.md](docs/seguranca-lgpd.md) | Prints do Key Vault, IAM e App Settings |
| **Monitoramento** (3,0) | Application Insights + Log Analytics + 3 alertas com e-mail — [docs/operacao.md](docs/operacao.md) | Print do alerta disparado e do e-mail recebido |
| **Custo e documentação** (1,5) | [docs/custos.md](docs/custos.md), este README e o PDF em [docs/entrega](docs/entrega) | PDF único com links clicáveis |

## Rodar localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
flask --app wsgi run --debug          # http://127.0.0.1:5000
```

Em desenvolvimento as chaves são geradas sozinhas em `instance/` (fora do git). Para ter o usuário `admin`, defina `ADMIN_PASSWORD` antes de subir. Variáveis disponíveis em [.env.example](.env.example).

Verificações (as mesmas do pipeline):

```bash
ruff check . && pytest && bandit -q -r app -c pyproject.toml && pip-audit -r requirements.txt
```

## Publicar na Azure

Passo a passo completo, com a lista de prints de evidência, em [docs/guia-azure.md](docs/guia-azure.md). Resumo:

```bash
az login
EMAIL_ALERTA="voce@exemplo.com" LEITORES="professor@fiap.com.br" bash infra/provisionar.sh
REPO=dono/repositorio bash infra/configurar-deploy.sh
git push origin main        # o GitHub Actions publica e testa
```

## API v1 (contratos com os outros componentes)

| Método e rota | Quem usa | O que faz |
|---|---|---|
| `GET /health` | App Service, pipeline, alerta | Saúde da aplicação e do banco, com a versão publicada |
| `GET /api/v1/vagas` · `GET /api/v1/materiais` | Qualquer componente | Catálogo público, sem dado pessoal |
| `GET /api/v1/indicadores` | Dados / Business | Indicadores agregados; grupos com menos de 5 alunos são omitidos |
| `POST /api/v1/tutor` `{"pergunta": "..."}` | Página do tutor | Repassa a pergunta ao tutor IA (`TUTOR_API_URL`); se ele cair, responde com uma mensagem padrão |
| `POST /api/v1/endereco` | Visão | Recebe o endereço extraído do comprovante e devolve só bairro, cidade e UF; nada é gravado |
| `POST /api/v1/integracao/voluntarios` (`X-API-Key`) | Robô UiPath | Cadastro em lote de voluntários (entram como pendentes de aprovação) |
| `GET /api/v1/integracao/boletim/destinatarios` (`X-API-Key`) | Robô UiPath | E-mails de voluntários adultos que optaram pelo boletim |

## Estrutura

```
app/                 aplicação Flask (páginas, API, modelo, segurança)
tests/               25 testes (pytest), cobertura acima de 90%
infra/               scripts Azure CLI: provisionar, configurar deploy, destruir
.github/workflows/   CI/CD e CodeQL
docs/                arquitetura, segurança e LGPD, operação, custos, guia Azure, PDF de entrega
```
