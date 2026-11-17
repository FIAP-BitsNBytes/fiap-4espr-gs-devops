# Guia: colocar no ar e coletar as evidências

Tempo estimado: 40 a 60 minutos. Faça com a conta Azure que tem créditos.

## Antes de começar

1. Crie um repositório **público** no GitHub e envie este código para a branch `main`.
   O pipeline já roda lint, testes e varreduras; o job de deploy fica em espera até a Azure existir.
2. Abra o [Azure Cloud Shell](https://shell.azure.com) em modo **Bash** e clone o repositório.

## Passo 1 — Provisionar

```bash
EMAIL_ALERTA="email1@exemplo.com email2@exemplo.com" \
LEITORES="email-do-professor@fiap.com.br" \
bash infra/provisionar.sh
```

Variáveis opcionais: `SKU=F1` (gratuito), `LOCAL=brazilsouth`, `ORCAMENTO_USD=30`.
Se a assinatura não tiver cota em Brazil South (erro *Operation cannot be completed without additional quota*), escolha outra região com `LOCAL=...` e registre a mudança no PDF. Nesta entrega foi usado `LOCAL=westus3`. Se o Resource Group já tiver sido criado vazio em outra região, apague-o antes de rodar de novo.
Confirme o convite que o Azure Monitor envia para cada e-mail de alerta.

## Passo 2 — Ligar o GitHub Actions

```bash
REPO=dono/repositorio bash infra/configurar-deploy.sh
```

Se aparecer erro de permissão ao criar o App Registration (comum em contas de estudante), use o plano B:

```bash
REPO=dono/repositorio MODO=publish-profile bash infra/configurar-deploy.sh
```

Depois crie as variáveis (ou o secret) no GitHub conforme o script indicar, e crie o environment `production` em Settings > Environments.

## Passo 3 — Primeiro deploy

Faça um commit qualquer na `main` (ou Actions > CI/CD > Run workflow). Ao final, abra `https://<app>.azurewebsites.net` e `https://<app>.azurewebsites.net/health`.

## Passo 4 — Evidências

Salve os prints em `docs/evidencias/` com exatamente estes nomes; o gerador do PDF encaixa cada um no lugar.

| Arquivo | O que mostrar | Critério |
|---|---|---|
| `01-site-no-ar.png` | Página inicial com a URL `https://...azurewebsites.net` e o cadeado visíveis | Deploy |
| `02-health.png` | `/health` respondendo `status: ok` com a versão | Deploy |
| `03-resource-group.png` | Resource Group com todos os recursos e as tags | Deploy |
| `04-app-service-tls.png` | Web App > Configuration/TLS: HTTPS Only, TLS 1.2, FTP desativado | Deploy / Segurança |
| `05-actions-verde.png` | Execução do workflow com os 4 jobs verdes | CI/CD |
| `06-actions-smoke.png` | Log do passo “Smoke test” mostrando a versão publicada | CI/CD |
| `07-deployment-center.png` | Histórico de execuções do workflow no GitHub Actions (ou Deployment Center > Logs) | CI/CD |
| `08-key-vault-segredos.png` | Lista de segredos do Key Vault (só os nomes) | Segurança |
| `09-app-settings-kv.png` | Environment variables do Web App com as referências ao Key Vault resolvidas (marca verde) | Segurança |
| `10-iam-rbac.png` | Access control (IAM) > Role assignments do Resource Group e do Key Vault | Segurança |
| `11-oidc-federado.png` | App Registration > Federated credentials (ou o secret do publish profile no GitHub) | Segurança |
| `12-consentimento.png` | Tela de autorização do responsável no site | Segurança (LGPD) |
| `13-app-insights.png` | Application Insights > Overview ou Live Metrics com tráfego | Monitoramento |
| `14-regras-de-alerta.png` | Monitor > Alerts > Alert rules com as 3 regras | Monitoramento |
| `15-alerta-disparado.png` | Alerta em estado Fired (ver [operacao.md](operacao.md)) | Monitoramento |
| `16-email-alerta.png` | E-mail do Azure Monitor recebido pela equipe | Monitoramento |
| `17-calculadora.png` | Calculadora de Preços com a estimativa | Custo |
| `18-orcamento.png` | Cost Management > Budgets | Custo |

Cuidado nos prints: não mostre valores de segredos, a senha do admin nem o conteúdo do publish profile.

## Passo 5 — Gerar o PDF

1. Preencha `docs/entrega/links.json` com a URL do MVP e do repositório.
2. Atualize os valores em `docs/custos.md` e na seção de custo de `docs/entrega/relatorio.html` com os números da calculadora.
3. Gere:

```bash
pip install playwright && playwright install chromium
python docs/entrega/gerar_pdf.py        # cria docs/entrega/entrega-secure-devops.pdf
```

Espaços sem print aparecem como caixas tracejadas “INSERIR PRINT”, então dá para ver o que falta.

## Passo 6 — Entregar

Um integrante envia o PDF no portal da disciplina até **19/11, 23h55**. O site e o repositório precisam continuar públicos e funcionando por até uma semana depois. Só então rode `bash infra/destruir.sh`.
