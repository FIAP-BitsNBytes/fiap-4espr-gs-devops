"""Apoio Escolar Periférico — MVP (FIAP Global Solution 2026.2, CitizenTech)."""
from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from . import config, seguranca
from .models import db, expurgar_pendentes

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["300 per minute"])


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(config.carregar(app.instance_path))
    if overrides:
        app.config.update(overrides)

    # O App Service termina o TLS e repassa o IP/esquema reais por cabeçalho.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    app.logger.setLevel(logging.INFO)

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from .api import api
    from .web import web

    app.register_blueprint(web)
    app.register_blueprint(api, url_prefix="/api/v1")
    csrf.exempt(api)  # API não usa cookie de sessão; integrações usam X-API-Key

    app.before_request(seguranca.carregar_usuario)
    app.after_request(seguranca.cabecalhos)

    @app.get("/health")
    @limiter.exempt
    def health():
        """Usado pelo Health Check do App Service, pelo smoke test e pelo alerta."""
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - qualquer falha de banco derruba o health
            app.logger.exception("health: banco indisponível")
            return jsonify(status="erro", banco="indisponivel"), 503
        return jsonify(status="ok", banco="ok", versao=app.config["VERSAO_APP"])

    def _erro(codigo: int, titulo: str, mensagem: str):
        if request.path.startswith("/api/"):
            return jsonify(erro=titulo), codigo
        return render_template("erro.html", titulo=titulo, mensagem=mensagem), codigo

    @app.errorhandler(400)
    def requisicao_invalida(_e):
        return _erro(
            400, "Não foi possível enviar",
            "A página ficou aberta por muito tempo ou o envio veio de outro lugar. "
            "Volte, recarregue a página e tente de novo.",
        )

    @app.errorhandler(401)
    def nao_autenticado(_e):
        return _erro(401, "Não autorizado", "Credencial ausente ou inválida.")

    @app.errorhandler(403)
    def proibido(_e):
        return _erro(403, "Acesso negado", "Seu perfil não tem permissão para esta página.")

    @app.errorhandler(404)
    def nao_encontrado(_e):
        return _erro(404, "Página não encontrada", "O endereço não existe ou mudou.")

    @app.errorhandler(429)
    def muitas_tentativas(_e):
        return _erro(429, "Muitas tentativas", "Espere um minuto e tente de novo.")

    @app.errorhandler(500)
    def erro_interno(_e):
        return _erro(500, "Algo deu errado", "Já fomos avisados. Tente de novo em instantes.")

    with app.app_context():
        db.create_all()
        from .seed import semear

        semear(app)
        expurgar_pendentes()

    return app
