"""Controles de segurança: cifragem, papéis, cabeçalhos HTTP e chave de API."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from functools import wraps

from cryptography.fernet import Fernet, InvalidToken
from flask import abort, current_app, flash, g, redirect, request, session, url_for

from .models import Usuario, db

RE_APELIDO = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
RE_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


# ---------- cifragem de contato (dado pessoal em repouso) ----------
def _fernet() -> Fernet:
    return Fernet(current_app.config["FERNET_KEY"].encode())


def cifrar(texto: str) -> bytes:
    return _fernet().encrypt(texto.encode())


def decifrar(blob: bytes | None) -> str:
    if not blob:
        return ""
    try:
        return _fernet().decrypt(blob).decode()
    except InvalidToken:
        current_app.logger.error("falha ao decifrar contato (chave trocada?)")
        return ""


def mascarar_email(email: str) -> str:
    """j***@dominio.com — usado em telas, nunca o e-mail inteiro."""
    if "@" not in email:
        return ""
    nome, dominio = email.split("@", 1)
    return f"{nome[:1]}***@{dominio}"


# ---------- token de consentimento do responsável ----------
def novo_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- sessão e papéis ----------
def carregar_usuario() -> None:
    g.usuario = None
    uid = session.get("uid")
    if uid is not None:
        g.usuario = db.session.get(Usuario, uid)
        if g.usuario is None:
            session.clear()


def exige_login(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.usuario is None:
            flash("Entre na sua conta para continuar.", "aviso")
            return redirect(url_for("web.entrar"))
        return view(*args, **kwargs)

    return wrapper


def exige_papel(*papeis: str):
    """Acesso por papel dentro da aplicação (aluno, voluntario, admin)."""

    def decorador(view):
        @wraps(view)
        @exige_login
        def wrapper(*args, **kwargs):
            if g.usuario.papel not in papeis:
                abort(403)
            return view(*args, **kwargs)

        return wrapper

    return decorador


def exige_chave_api(view):
    """Integrações máquina-a-máquina (RPA, Visão) usam X-API-Key."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        esperada = current_app.config["INTEGRATION_API_KEY"]
        recebida = request.headers.get("X-API-Key", "")
        if not esperada or not hmac.compare_digest(esperada, recebida):
            abort(401)
        return view(*args, **kwargs)

    return wrapper


# ---------- cabeçalhos de segurança ----------
CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; "
    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)


def cabecalhos(resposta):
    resposta.headers.setdefault("Content-Security-Policy", CSP)
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    # same-origin: o Referer só é enviado para o próprio site (nunca para links
    # externos). "no-referrer" quebraria os formulários: a proteção CSRF do
    # Flask-WTF exige o Referer em requisições HTTPS.
    resposta.headers.setdefault("Referrer-Policy", "same-origin")
    resposta.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    if current_app.config["APP_ENV"] == "production":
        resposta.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    if g.get("usuario") is not None:
        resposta.headers.setdefault("Cache-Control", "no-store")
    return resposta
