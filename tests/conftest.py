import pytest

from app import create_app
from app.models import Usuario, db


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/t.db",
        "ADMIN_PASSWORD": "senha-admin-teste",
        "INTEGRATION_API_KEY": "chave-teste",
    })
    with app.app_context():
        from app.seed import semear
        db.drop_all()
        db.create_all()
        semear(app)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def cadastrar(client, **extra):
    dados = {
        "tipo": "aluno", "apelido": "ana_9", "senha": "segredo123", "bairro": "Grajaú",
        "serie": "9º ano EF", "faixa_etaria": "18_mais", "aceite": "sim",
    }
    dados.update(extra)
    return client.post("/cadastro", data=dados)


def entrar(client, apelido="ana_9", senha="segredo123"):
    return client.post("/entrar", data={"apelido": apelido, "senha": senha})


def usuario(app, apelido):
    with app.app_context():
        return Usuario.query.filter_by(apelido=apelido).first()


def n_inscricoes(app, apelido):
    with app.app_context():
        return len(Usuario.query.filter_by(apelido=apelido).first().inscricoes)


def vagas_de(app, apelido):
    with app.app_context():
        u = Usuario.query.filter_by(apelido=apelido).first()
        return [(v.id, v.ativa) for v in u.vagas]
