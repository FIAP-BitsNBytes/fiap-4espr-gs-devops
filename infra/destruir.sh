#!/usr/bin/env bash
# Apaga TUDO depois da correção, para parar de consumir créditos.
# Atenção: os links precisam ficar no ar até uma semana após 19/11.
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/.saida/ambiente.env"
read -r -p "Apagar o Resource Group $RG e todos os dados? (digite o nome do RG) " confirma
[[ "$confirma" == "$RG" ]] || { echo "Cancelado."; exit 1; }
az group delete -n "$RG" --yes
az keyvault purge -n "$KV" || true   # libera o nome do cofre (soft delete)
APP_REG="$(az ad app list --display-name "gh-deploy-${APP}" --query '[0].appId' -o tsv)"
[[ -n "$APP_REG" ]] && az ad app delete --id "$APP_REG"
echo "Recursos removidos."
