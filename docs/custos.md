# Estimativa de custo mensal

> Valores em dólar, pagamento conforme o uso. O preço do App Service foi lido no portal da Azure (tela *Selecionar Plano de Preços* do próprio plano, região West US 3) em 17/11/2026 e está no print `17-calculadora.png`. Os demais itens são de baixo valor e foram estimados pelos preços de lista conhecidos; para valores exatos use a [Calculadora de Preços da Azure](https://azure.microsoft.com/pricing/calculator/).

## Cenário 1 — MVP em avaliação (o que o script cria)

| Recurso | Configuração | Custo mensal aproximado |
|---|---|---|
| App Service Plan Linux | B1 (1 vCPU, 1,75 GB), 1 instância, West US 3 | US$ 12,41 (US$ 0,017 por hora) |
| Key Vault | Standard, poucas centenas de leituras | menos de US$ 0,10 |
| Log Analytics + Application Insights | Menos de 1 GB/mês, retenção de 30 dias; os primeiros 5 GB/mês não são cobrados | US$ 0 |
| Alertas de métrica | 3 regras, 1 série cada | até US$ 0,30 |
| Notificações por e-mail | Dentro da franquia mensal | US$ 0 |
| Tráfego de saída | Páginas de poucos kB; dentro dos 100 GB gratuitos | US$ 0 |
| GitHub Actions | Repositório público | US$ 0 |
| **Total** | | **≈ US$ 13 por mês** |

## Cenário 0 — Custo zero (se os créditos forem curtos)

Rodar com `SKU=F1 bash infra/provisionar.sh`. O plano gratuito mantém HTTPS e a URL pública, mas tem limite diário de CPU, não tem Always On (a primeira visita depois de um tempo parado demora) e o script não cria o alerta de saúde nesse plano. Os alertas de erro 5xx e de lentidão continuam.

## Cenário 2 — Piloto real (ordem de grandeza)

Para alguns milhares de alunos: plano Premium v3 pequeno (P0v3 custa US$ 56,58 por instância na mesma tela do portal) com 2 instâncias, Azure Database for PostgreSQL Flexible Server (Burstable), Azure Communication Services para o e-mail do responsável e Redis básico para o limite de requisições. A ordem de grandeza passa a dezenas ou poucas centenas de dólares por mês; o valor exato deve sair da calculadora quando o volume for conhecido.

## Como o custo é controlado

- Teto diário de 1 GB na ingestão do Log Analytics (`--quota 1`).
- Orçamento mensal de R$ 150 no Resource Group (`orcamento-apoioescolar`), com aviso por e-mail ao atingir 80%. O script tenta criar por CLI; nesta conta de avaliação ele foi criado pelo portal (Cost Management > Budgets).
- O ambiente roda com o crédito da conta gratuita da Azure, que tem limite de gastos: se o crédito acabar, os serviços são suspensos e nada é cobrado.
- Tags `projeto`, `disciplina`, `equipe` e `ambiente` em todos os recursos para filtrar no Cost Analysis.
- Tudo em um único Resource Group: `bash infra/destruir.sh` apaga tudo depois da correção.
