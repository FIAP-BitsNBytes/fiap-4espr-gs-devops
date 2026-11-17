# Operação e monitoramento

## O que é monitorado

| Sinal | Origem | Para que serve |
|---|---|---|
| Requisições, tempo de resposta, falhas e exceções | Application Insights (OpenTelemetry) | Ver o que o usuário está sentindo |
| Logs da aplicação e do contêiner | Log Analytics (`AppServiceConsoleLogs`, `AppServiceAppLogs`) | Investigar erros |
| Logs HTTP e de auditoria da plataforma | Log Analytics (`AppServiceHTTPLogs`, `AppServiceAuditLogs`) | Tráfego e tentativas de acesso ao deploy |
| Saúde | Health Check do App Service em `/health` | Detectar app ou banco fora do ar |

## Alertas (avisam a equipe por e-mail antes de o cidadão reclamar)

| Alerta | Condição | Severidade | Primeira ação |
|---|---|---|---|
| `alerta-health-check` | `/health` falhando (média < 100% em 5 min) | 0 – crítico | Ver Log stream; reiniciar o app; conferir referências do Key Vault |
| `alerta-erros-5xx` | Mais de 5 respostas 5xx em 5 min | 1 – erro | Abrir Failures no Application Insights e achar a exceção |
| `alerta-lentidao` | Tempo médio de resposta > 3 s em 5 min | 2 – aviso | Ver Performance; checar CPU e memória do plano |

Todos usam o Action Group `ag-apoioescolar`, com os e-mails de `EMAIL_ALERTA`.

## Como provocar um alerta para a evidência

Aprendizados do teste real desta entrega:

- O e-mail de cada destinatário do Action Group precisa ser **verificado** (a Azure envia um link que expira em 30 minutos). Sem isso o alerta dispara no portal, mas nenhum e-mail é enviado. Para reenviar: Action Group > Visão geral > Reenviar.
- **Parar o Web App não dispara alerta**: com o app parado a plataforma deixa de emitir métricas e nenhuma regra é avaliada.
- O que funcionou: parar o app por alguns minutos e **religar**. As primeiras respostas após a partida a frio são lentas e disparam o `alerta-lentidao`; poucos minutos depois chega o e-mail de resolução.

```bash
source infra/.saida/ambiente.env
az webapp stop -g "$RG" -n "$APP"
sleep 300
az webapp start -g "$RG" -n "$APP"
# em cerca de 5 minutos: e-mail "Your Azure Monitor alert was triggered" e, depois, "was resolved"
```

Tire print dos e-mails e da tela Alertas do Resource Group mostrando o disparo.

## Consultas úteis (Application Insights > Logs)

```kusto
// Requisições por rota e taxa de falha na última hora
AppRequests
| where TimeGenerated > ago(1h)
| summarize total = count(), falhas = countif(Success == false), p95_ms = percentile(DurationMs, 95) by Name
| order by total desc
```

```kusto
// Exceções mais recentes
AppExceptions
| where TimeGenerated > ago(24h)
| project TimeGenerated, ProblemId, OuterMessage
| order by TimeGenerated desc
```

```kusto
// Logins recusados (possível tentativa de adivinhar senha)
AppTraces
| where Message has "login recusado"
| summarize tentativas = count() by bin(TimeGenerated, 5m)
```

## Rotinas

| Situação | O que fazer |
|---|---|
| Deploy quebrou o site | Em Actions, reexecute o workflow do último commit bom (*Re-run all jobs*) ou faça `git revert` e push |
| Trocar a senha do admin ou a chave de API | Grave nova versão do segredo no Key Vault e reinicie o Web App |
| Trocar a `FERNET-KEY` | **Não troque sem migração**: os e-mails cifrados ficariam ilegíveis |
| Backup do banco | Baixe `/home/data/apoio.db` pelo Kudu/SSH; ao migrar para PostgreSQL, use o backup gerenciado |
| Fim da correção | `bash infra/destruir.sh` para encerrar o consumo de créditos |
