"""Configuração lida somente de variáveis de ambiente (nenhum segredo no código).

Em produção (APP_ENV=production) os segredos chegam por App Settings do
Azure App Service, que por sua vez são referências ao Azure Key Vault.
"""
from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path

from cryptography.fernet import Fernet

VERSAO_TERMO = "2026-11-v1"
SEGREDOS_OBRIGATORIOS = ("SECRET_KEY", "FERNET_KEY")


class ConfigError(RuntimeError):
    """Configuração obrigatória ausente."""


def _chave_dev(instance_path: str, nome: str, gerar) -> str:
    """Em desenvolvimento, gera e guarda a chave em instance/ (fora do git)."""
    pasta = Path(instance_path)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome
    if not arquivo.exists():
        arquivo.write_text(gerar())
        arquivo.chmod(0o600)
    return arquivo.read_text().strip()


def _versao() -> str:
    """O pipeline grava o hash do commit no arquivo VERSAO dentro do pacote."""
    arquivo = Path(__file__).resolve().parent.parent / "VERSAO"
    if arquivo.exists():
        return arquivo.read_text().strip()[:40] or "dev"
    return os.environ.get("VERSAO_APP", "dev")


def carregar(instance_path: str) -> dict:
    env = os.environ.get("APP_ENV", "development").lower()
    producao = env == "production"

    if producao:
        faltando = [s for s in SEGREDOS_OBRIGATORIOS if not os.environ.get(s)]
        if faltando:
            raise ConfigError(
                "Segredos obrigatórios ausentes em produção: " + ", ".join(faltando)
            )
        secret_key = os.environ["SECRET_KEY"]
        fernet_key = os.environ["FERNET_KEY"]
    else:
        secret_key = os.environ.get("SECRET_KEY") or _chave_dev(
            instance_path, "dev_secret.key", lambda: secrets.token_hex(32)
        )
        fernet_key = os.environ.get("FERNET_KEY") or _chave_dev(
            instance_path, "dev_fernet.key", lambda: Fernet.generate_key().decode()
        )

    banco = os.environ.get("DATABASE_URL") or "sqlite:///" + str(
        Path(instance_path) / "apoio.db"
    )

    if banco.startswith("sqlite:///"):
        # No App Service o banco fica em /home/data (armazenamento persistente).
        Path(banco.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

    return {
        "APP_ENV": env,
        "SECRET_KEY": secret_key,
        "FERNET_KEY": fernet_key,
        "SQLALCHEMY_DATABASE_URI": banco,
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        # Cookies de sessão: só HTTPS em produção, inacessíveis a JavaScript.
        "SESSION_COOKIE_SECURE": producao,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=2),
        "MAX_CONTENT_LENGTH": 64 * 1024,  # o MVP não recebe arquivos
        "ADMIN_PASSWORD": os.environ.get("ADMIN_PASSWORD", ""),
        "INTEGRATION_API_KEY": os.environ.get("INTEGRATION_API_KEY", ""),
        "PRIVACY_CONTACT": os.environ.get("PRIVACY_CONTACT", ""),
        "TUTOR_API_URL": os.environ.get("TUTOR_API_URL", ""),
        "SEED_DEMO": os.environ.get("SEED_DEMO", "1") == "1",
        "RATELIMIT_ENABLED": os.environ.get("RATELIMIT_ENABLED", "1") == "1",
        "RATELIMIT_STORAGE_URI": "memory://",
        "VERSAO_APP": _versao(),
    }
