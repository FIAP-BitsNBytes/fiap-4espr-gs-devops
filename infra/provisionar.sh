#!/usr/bin/env bash
# Provisiona toda a infraestrutura do Apoio Escolar Periférico na Azure.
# Rode no Azure Cloud Shell (Bash) ou em qualquer terminal com `az login` feito.
# O script é idempotente: pode ser executado de novo sem duplicar nem trocar segredos.
#
#   EMAIL_ALERTA="a@x.com b@y.com" LEITORES="prof@fiap.com.br" bash infra/provisionar.sh
#
# Nenhum segredo é impresso na tela nem gravado em arquivo.
set -euo pipefail

# ------------------------- parâmetros -------------------------
EMAIL_ALERTA="${EMAIL_ALERTA:?Informe EMAIL_ALERTA (um ou mais e-mails separados por espaço)}"
LEITORES="${LEITORES:-}"            # e-mails (contas Entra ID) que recebem papel Reader no RG
LOCAL="${LOCAL:-brazilsouth}"       # preferência: Brasil. Sem cota? rode com LOCAL=westus3 (ou outra região)
SKU="${SKU:-B1}"                    # B1 = Always On + Health Check; F1 = gratuito, sem Always On
ORCAMENTO_USD="${ORCAMENTO_USD:-30}"
PREFIXO="${PREFIXO:-apoioescolar}"
ASSINATURA="$(az account show --query id -o tsv)"
SUFIXO="${SUFIXO:-${ASSINATURA:0:6}}"   # torna os nomes globais únicos e estáveis

RG="${RG:-rg-apoio-escolar-gs}"
PLANO="plan-${PREFIXO}"
APP="${APP:-app-${PREFIXO}-${SUFIXO}}"
KV="${KV:-kv-${PREFIXO}-${SUFIXO}}"
LAW="log-${PREFIXO}"
APPI="appi-${PREFIXO}"
GRUPO_ACAO="ag-${PREFIXO}"
TAGS=(projeto=apoio-escolar-periferico disciplina=secure-devops-cloud equipe=BitsNBytes ambiente=producao)

passo() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
az config set extension.use_dynamic_install=yes_without_prompt --only-show-errors

# ------------------------- 1. Resource Group -------------------------
passo "1/9 Resource Group $RG ($LOCAL)"
for rp in Microsoft.Web Microsoft.KeyVault Microsoft.Insights Microsoft.OperationalInsights Microsoft.AlertsManagement; do
  az provider register --namespace "$rp" --only-show-errors >/dev/null
done
az group create -n "$RG" -l "$LOCAL" --tags "${TAGS[@]}" -o none
RG_ID="$(az group show -n "$RG" --query id -o tsv)"

# ------------------------- 2. App Service -------------------------
passo "2/9 App Service Plan ($SKU, Linux) e Web App $APP"
az appservice plan create -g "$RG" -n "$PLANO" -l "$LOCAL" --is-linux --sku "$SKU" --tags "${TAGS[@]}" -o none
if ! az webapp show -g "$RG" -n "$APP" -o none 2>/dev/null; then
  az webapp create -g "$RG" -p "$PLANO" -n "$APP" --runtime "PYTHON:3.12" \
    --https-only true --assign-identity '[system]' --basic-auth Disabled --tags "${TAGS[@]}" -o none
fi
APP_ID="$(az webapp show -g "$RG" -n "$APP" --query id -o tsv)"
APP_MI="$(az webapp identity assign -g "$RG" -n "$APP" --query principalId -o tsv)"

SEMPRE_LIGADO=true
[[ "$SKU" == "F1" || "$SKU" == "D1" ]] && SEMPRE_LIGADO=false
az webapp config set -g "$RG" -n "$APP" \
  --startup-file "gunicorn --bind=0.0.0.0:8000 --workers 1 --threads 8 --timeout 120 wsgi:app" \
  --min-tls-version 1.2 --ftps-state Disabled --http20-enabled true \
  --always-on "$SEMPRE_LIGADO" \
  --generic-configurations '{"healthCheckPath": "/health"}' -o none
az webapp update -g "$RG" -n "$APP" --https-only true -o none

# ------------------------- 3. Key Vault -------------------------
passo "3/9 Key Vault $KV (autorização por RBAC)"
if ! az keyvault show -n "$KV" -o none 2>/dev/null; then
  az keyvault create -g "$RG" -n "$KV" -l "$LOCAL" --enable-rbac-authorization true \
    --retention-days 7 --tags "${TAGS[@]}" -o none
fi
KV_ID="$(az keyvault show -n "$KV" --query id -o tsv)"
EU="$(az ad signed-in-user show --query id -o tsv)"
az role assignment create --assignee-object-id "$EU" --assignee-principal-type User \
  --role "Key Vault Secrets Officer" --scope "$KV_ID" -o none
# A aplicação só LÊ segredos, e só deste cofre (menor privilégio).
az role assignment create --assignee-object-id "$APP_MI" --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" --scope "$KV_ID" -o none

passo "4/9 Segredos gerados direto no cofre (nunca exibidos)"
gravar_se_faltar() {  # nome, valor — não sobrescreve: trocar FERNET-KEY tornaria os dados ilegíveis
  local nome="$1" valor="$2" tentativa
  for tentativa in 1 2 3 4 5 6; do
    if az keyvault secret show --vault-name "$KV" -n "$nome" -o none 2>/dev/null; then
      echo "  $nome já existe (mantido)"; return 0
    fi
    if az keyvault secret set --vault-name "$KV" -n "$nome" --value "$valor" -o none 2>/dev/null; then
      echo "  $nome criado"; return 0
    fi
    echo "  aguardando a permissão RBAC propagar ($tentativa/6)..."; sleep 20
  done
  echo "Não foi possível gravar $nome no Key Vault." >&2; return 1
}
gravar_se_faltar SECRET-KEY          "$(openssl rand -hex 32)"
gravar_se_faltar FERNET-KEY          "$(openssl rand -base64 32 | tr '+/' '-_')"
gravar_se_faltar ADMIN-PASSWORD      "$(openssl rand -base64 18 | tr '+/' '-_')"
gravar_se_faltar INTEGRATION-API-KEY "$(openssl rand -hex 24)"

# ------------------------- 5. Monitoramento -------------------------
passo "5/9 Log Analytics + Application Insights"
az monitor log-analytics workspace create -g "$RG" -n "$LAW" -l "$LOCAL" \
  --retention-time 30 --quota 1 --tags "${TAGS[@]}" -o none   # teto de 1 GB/dia protege o custo
LAW_ID="$(az monitor log-analytics workspace show -g "$RG" -n "$LAW" --query id -o tsv)"
az monitor app-insights component create -g "$RG" --app "$APPI" -l "$LOCAL" \
  --workspace "$LAW_ID" --application-type web --tags "${TAGS[@]}" -o none
APPI_CONN="$(az monitor app-insights component show -g "$RG" --app "$APPI" --query connectionString -o tsv)"

az monitor diagnostic-settings create --name diag-app --resource "$APP_ID" --workspace "$LAW_ID" \
  --logs '[{"category":"AppServiceHTTPLogs","enabled":true},{"category":"AppServiceConsoleLogs","enabled":true},{"category":"AppServiceAppLogs","enabled":true},{"category":"AppServiceAuditLogs","enabled":true},{"category":"AppServicePlatformLogs","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]' -o none \
  || echo "  aviso: diagnóstico não aplicado (o plano $SKU pode não suportar); siga sem ele."

# ------------------------- 6. Configuração da aplicação -------------------------
passo "6/9 App Settings com referências ao Key Vault (o valor nunca sai do cofre)"
ref() { echo "@Microsoft.KeyVault(VaultName=${KV};SecretName=$1)"; }
az webapp config appsettings set -g "$RG" -n "$APP" -o none --settings \
  APP_ENV=production \
  SCM_DO_BUILD_DURING_DEPLOYMENT=true \
  DATABASE_URL=sqlite:////home/data/apoio.db \
  SEED_DEMO=1 \
  OTEL_PYTHON_FLASK_EXCLUDED_URLS=consentimento \
  "SECRET_KEY=$(ref SECRET-KEY)" \
  "FERNET_KEY=$(ref FERNET-KEY)" \
  "ADMIN_PASSWORD=$(ref ADMIN-PASSWORD)" \
  "INTEGRATION_API_KEY=$(ref INTEGRATION-API-KEY)" \
  "APPLICATIONINSIGHTS_CONNECTION_STRING=${APPI_CONN}"

# ------------------------- 7. Alertas -------------------------
passo "7/9 Grupo de ação e alertas (avisam a equipe por e-mail)"
RECEPTORES=()
n=0
for email in $EMAIL_ALERTA; do n=$((n + 1)); RECEPTORES+=(--action email "equipe${n}" "$email"); done
az monitor action-group create -g "$RG" -n "$GRUPO_ACAO" --short-name apoioesc "${RECEPTORES[@]}" -o none
AG_ID="$(az monitor action-group show -g "$RG" -n "$GRUPO_ACAO" --query id -o tsv)"

alerta() {  # nome, severidade, condição, descrição
  az monitor metrics alert create -g "$RG" -n "$1" --scopes "$APP_ID" --severity "$2" \
    --condition "$3" --window-size 5m --evaluation-frequency 1m \
    --action "$AG_ID" --description "$4" -o none
  echo "  $1"
}
alerta "alerta-erros-5xx"       1 "total Http5xx > 5"            "Mais de 5 erros HTTP 5xx em 5 minutos"
alerta "alerta-lentidao"        2 "avg HttpResponseTime > 3"     "Tempo médio de resposta acima de 3 s por 5 minutos"
if [[ "$SEMPRE_LIGADO" == true ]]; then
  alerta "alerta-health-check"  0 "avg HealthCheckStatus < 100"  "O endpoint /health falhou: aplicação ou banco fora do ar"
fi

# ------------------------- 8. Acesso por papel (RBAC) -------------------------
passo "8/9 RBAC: leitores do Resource Group"
for email in $LEITORES; do
  az role assignment create --assignee "$email" --role Reader --scope "$RG_ID" -o none \
    && echo "  Reader -> $email" || echo "  aviso: não consegui atribuir Reader a $email"
done

# ------------------------- 9. Orçamento -------------------------
passo "9/9 Orçamento mensal de US\$ $ORCAMENTO_USD no Resource Group"
INICIO="$(date -u +%Y-%m-01)"; FIM="$(date -u -d "$INICIO +1 year" +%Y-%m-01)"
az consumption budget create --budget-name "orcamento-${PREFIXO}" --amount "$ORCAMENTO_USD" \
  --category cost --time-grain monthly --start-date "$INICIO" --end-date "$FIM" \
  --resource-group "$RG" -o none 2>/dev/null \
  || echo "  aviso: orçamento não criado por CLI (comum em contas de estudante). Crie em Cost Management > Budgets."

mkdir -p "$(dirname "$0")/.saida"
cat > "$(dirname "$0")/.saida/ambiente.env" <<EOF
RG=$RG
APP=$APP
KV=$KV
APPI=$APPI
EOF

cat <<EOF

Pronto.
  URL do MVP ........ https://${APP}.azurewebsites.net
  Resource Group .... $RG
  Web App ........... $APP
  Key Vault ......... $KV
  App Insights ...... $APPI

Próximos passos:
  1. Ligar o GitHub Actions:  REPO=dono/repositorio bash infra/configurar-deploy.sh
  2. Senha do usuário "admin" (mostre só para quem precisa):
       az keyvault secret show --vault-name $KV -n ADMIN-PASSWORD --query value -o tsv
  3. Cada e-mail em EMAIL_ALERTA recebe um convite do Azure Monitor: confirme.
EOF
