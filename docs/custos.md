# Estimativa de custo mensal

> **Importante:** os valores abaixo são preços de lista aproximados (pagamento conforme o uso, em dólar) que conhecíamos ao escrever este documento. Preços mudam e variam por região. Antes de entregar, refaça a conta na [Calculadora de Preços da Azure](https://azure.microsoft.com/pricing/calculator/) para a região **West US 3** (onde o ambiente foi criado), substitua os números e anexe o print da calculadora ao PDF.

## Cenário 1 — MVP em avaliação (o que o script cria)

| Recurso | Configuração | Custo mensal aproximado |
|---|---|---|
| App Service Plan Linux | B1 (1 vCPU, 1,75 GB), 1 instância, 730 h | US$ 13 a 19 (varia por região) |
| Key Vault | Standard, poucas centenas de leituras | menos de US$ 0,10 |
| Log Analytics + Application Insights | Menos de 1 GB/mês, retenção de 30 dias; os primeiros 5 GB/mês não são cobrados | US$ 0 |
| Alertas de métrica | 3 regras, 1 série cada | até US$ 0,30 |
| Notificações por e-mail | Dentro da franquia mensal | US$ 0 |
| Tráfego de saída | Páginas de poucos kB; dentro dos 100 GB gratuitos | US$ 0 |
| GitHub Actions | Repositório público | US$ 0 |
| **Total** | | **≈ US$ 14 a 20 por mês** |

## Cenário 0 — Custo zero (se os créditos forem curtos)

Rodar com `SKU=F1 bash infra/provisionar.sh`. O plano gratuito mantém HTTPS e a URL pública, mas tem limite diário de CPU, não tem Always On (a primeira visita depois de um tempo parado demora) e o script não cria o alerta de saúde nesse plano. Os alertas de erro 5xx e de lentidão continuam.

## Cenário 2 — Piloto real (ordem de grandeza)

Para alguns milhares de alunos: plano Premium v3 pequeno ou Standard com 2 instâncias, Azure Database for PostgreSQL Flexible Server (Burstable), Azure Communication Services para o e-mail do responsável e Redis básico para o limite de requisições. A ordem de grandeza passa a dezenas ou poucas centenas de dólares por mês; o valor exato deve sair da calculadora quando o volume for conhecido.

## Como o custo é controlado

- Teto diário de 1 GB na ingestão do Log Analytics (`--quota 1`).
- Orçamento mensal no Resource Group (`ORCAMENTO_USD`, padrão US$ 30) criado pelo script; se a conta de estudante não permitir por CLI, criar em Cost Management > Budgets.
- Tags `projeto`, `disciplina`, `equipe` e `ambiente` em todos os recursos para filtrar no Cost Analysis.
- Tudo em um único Resource Group: `bash infra/destruir.sh` apaga tudo depois da correção.
