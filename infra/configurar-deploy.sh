#!/usr/bin/env bash
# Liga o GitHub Actions ao App Service.
#
#   REPO=dono/repositorio bash infra/configurar-deploy.sh            # OIDC (recomendado)
#   REPO=dono/repositorio MODO=publish-profile bash infra/configurar-deploy.sh   # plano B
#
# OIDC: o GitHub recebe um token de curta duração a cada execução; nenhuma senha
# fica guardada. A identidade só pode publicar NESTE Web App (Website Contributor
# no escopo do app) e só a partir do environment "production" DESTE repositório.
#
# Plano B: algumas contas de estudante não deixam criar App Registration no
# Entra ID. Nesse caso use MODO=publish-profile (o perfil vira um secret do GitHub).
set -euo pipefail

REPO="${REPO:?Informe REPO=dono/repositorio}"
MODO="${MODO:-oidc}"
# shellcheck disable=SC1091
source "$(dirname "$0")/.saida/ambiente.env"   # RG e APP gravados pelo provisionar.sh
APP_ID="$(az webapp show -g "$RG" -n "$APP" --query id -o tsv)"
TEM_GH=false; command -v gh >/dev/null && gh auth status >/dev/null 2>&1 && TEM_GH=true

if [[ "$MODO" == "oidc" ]]; then
  NOME="gh-deploy-${APP}"
  CLIENT_ID="$(az ad app list --display-name "$NOME" --query '[0].appId' -o tsv)"
  if [[ -z "$CLIENT_ID" ]]; then
    CLIENT_ID="$(az ad app create --display-name "$NOME" --query appId -o tsv)"
  fi
  az ad sp show --id "$CLIENT_ID" -o none 2>/dev/null || az ad sp create --id "$CLIENT_ID" -o none
  SP_OBJ="$(az ad sp show --id "$CLIENT_ID" --query id -o tsv)"

  credencial() {  # nome, subject
    if ! az ad app federated-credential list --id "$CLIENT_ID" --query "[?name=='$1']" -o tsv | grep -q .; then
      az ad app federated-credential create --id "$CLIENT_ID" -o none --parameters "{
        \"name\": \"$1\",
        \"issuer\": \"https://token.actions.githubusercontent.com\",
        \"subject\": \"$2\",
        \"audiences\": [\"api://AzureADTokenExchange\"]
      }"
    fi
  }
  # Formato clássico do subject.
  credencial github-production "repo:${REPO}:environment:production"
  # Formato novo: o GitHub passou a incluir os IDs imutáveis do dono e do repositório
  # (repo:DONO@ID/REPO@ID:...). Sem esta credencial o login falha com AADSTS700213.
  META="$(curl -fsS "https://api.github.com/repos/${REPO}" || true)"
  DONO_ID="$(echo "$META" | jq -r '.owner.id // empty' 2>/dev/null || true)"
  REPO_ID="$(echo "$META" | jq -r '.id // empty' 2>/dev/null || true)"
  if [[ -n "$DONO_ID" && -n "$REPO_ID" ]]; then
    credencial github-production-ids "repo:${REPO%%/*}@${DONO_ID}/${REPO##*/}@${REPO_ID}:environment:production"
  else
    echo "aviso: não consegui ler os IDs do repositório (ele é público?). Se o deploy falhar com"
    echo "       AADSTS700213, crie uma credencial federada com o subject exato mostrado no erro."
  fi
  az role assignment create --assignee-object-id "$SP_OBJ" --assignee-principal-type ServicePrincipal \
    --role "Website Contributor" --scope "$APP_ID" -o none

  TENANT="$(az account show --query tenantId -o tsv)"
  SUB="$(az account show --query id -o tsv)"
  if $TEM_GH; then
    gh variable set AZURE_WEBAPP_NAME     -R "$REPO" -b "$APP"
    gh variable set AZURE_CLIENT_ID       -R "$REPO" -b "$CLIENT_ID"
    gh variable set AZURE_TENANT_ID       -R "$REPO" -b "$TENANT"
    gh variable set AZURE_SUBSCRIPTION_ID -R "$REPO" -b "$SUB"
    echo "Variáveis gravadas em $REPO. Faça um commit na main para disparar o deploy."
  else
    cat <<EOF
Crie estas VARIÁVEIS (não são segredos) em
https://github.com/${REPO}/settings/variables/actions :

  AZURE_WEBAPP_NAME      = $APP
  AZURE_CLIENT_ID        = $CLIENT_ID
  AZURE_TENANT_ID        = $TENANT
  AZURE_SUBSCRIPTION_ID  = $SUB
EOF
  fi
else
  # Plano B: exige autenticação básica no endpoint de deploy (SCM). O FTP continua desligado.
  az resource update -g "$RG" --namespace Microsoft.Web --resource-type basicPublishingCredentialsPolicies \
    --parent "sites/$APP" -n scm --set properties.allow=true -o none
  if $TEM_GH; then
    az webapp deployment list-publishing-profiles -g "$RG" -n "$APP" --xml \
      | gh secret set AZURE_WEBAPP_PUBLISH_PROFILE -R "$REPO"
    gh variable set AZURE_WEBAPP_NAME -R "$REPO" -b "$APP"
    echo "Secret e variável gravados em $REPO (o perfil não passou por arquivo nem pela tela)."
  else
    cat <<EOF
1. No Portal: Web App $APP > Overview > "Download publish profile".
2. Em https://github.com/${REPO}/settings/secrets/actions crie o SECRET
   AZURE_WEBAPP_PUBLISH_PROFILE com o conteúdo do arquivo e apague o arquivo.
3. Em https://github.com/${REPO}/settings/variables/actions crie a VARIÁVEL
   AZURE_WEBAPP_NAME = $APP
EOF
  fi
fi
