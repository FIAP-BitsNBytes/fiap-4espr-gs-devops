import re

from app import create_app
from app.config import ConfigError
from app.models import Auditoria, Usuario, agora, db, expurgar_pendentes
from tests.conftest import cadastrar, entrar, n_inscricoes, usuario, vagas_de


# ---------- disponibilidade e segurança de transporte ----------
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json["status"] == "ok"


def test_paginas_publicas(client):
    for rota in ("/", "/vagas", "/materiais", "/tutor", "/privacidade", "/cadastro", "/entrar"):
        assert client.get(rota).status_code == 200


def test_cabecalhos_de_seguranca(client):
    h = client.get("/").headers
    assert "default-src 'self'" in h["Content-Security-Policy"]
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"


def test_producao_exige_segredos(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FERNET_KEY", raising=False)
    try:
        create_app()
    except ConfigError as e:
        assert "SECRET_KEY" in str(e)
    else:
        raise AssertionError("deveria falhar sem segredos")


def test_csrf_ativo_por_padrao(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    app = create_app({"TESTING": True, "RATELIMIT_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/c.db"})
    assert app.test_client().post("/entrar", data={"apelido": "x", "senha": "y"}).status_code == 400


# ---------- cadastro, minimização e consentimento ----------
def test_cadastro_adulto_fica_ativo(app, client):
    assert cadastrar(client).status_code == 200
    u = usuario(app, "ana_9")
    assert u.status == "ativo" and u.consentimento_em is not None
    assert u.contato_cifrado is None  # adulto não precisa informar e-mail


def test_cadastro_invalido(client):
    r = cadastrar(client, apelido="a", senha="123", aceite="")
    assert r.status_code == 400


def test_menor_exige_email_do_responsavel(client):
    assert cadastrar(client, faixa_etaria="12_17").status_code == 400


def test_fluxo_consentimento_do_responsavel(app, client):
    r = cadastrar(client, faixa_etaria="menor_12", contato="mae@example.com")
    u = usuario(app, "ana_9")
    assert u.status == "pendente_consentimento"
    # e-mail cifrado em repouso: o texto puro não aparece no banco
    assert b"mae@example.com" not in u.contato_cifrado
    token = re.search(r"/consentimento/([\w-]+)", r.text).group(1)

    # sem autorização o menor não consegue se inscrever
    entrar(client)
    client.post("/vagas/1/inscrever")
    assert n_inscricoes(app, "ana_9") == 0

    assert client.get(f"/consentimento/{token}").status_code == 200
    client.post(f"/consentimento/{token}", data={"decisao": "autorizo"})
    assert usuario(app, "ana_9").status == "ativo"
    assert client.get(f"/consentimento/{token}").status_code == 404  # uso único

    client.post("/vagas/1/inscrever")
    assert n_inscricoes(app, "ana_9") == 1


def test_responsavel_nega_e_cadastro_some(app, client):
    r = cadastrar(client, faixa_etaria="12_17", contato="pai@example.com")
    token = re.search(r"/consentimento/([\w-]+)", r.text).group(1)
    client.post(f"/consentimento/{token}", data={"decisao": "nao"})
    assert usuario(app, "ana_9") is None


def test_expurgo_de_pendentes_antigos(app, client):
    from datetime import timedelta
    cadastrar(client, faixa_etaria="12_17", contato="pai@example.com")
    with app.app_context():
        u = Usuario.query.filter_by(apelido="ana_9").first()
        u.criado_em = agora() - timedelta(days=31)
        db.session.commit()
        assert expurgar_pendentes() == 1
        assert Usuario.query.filter_by(apelido="ana_9").first() is None


# ---------- sessão e papéis ----------
def test_login_errado(client):
    cadastrar(client)
    assert entrar(client, senha="errada").status_code == 401


def test_painel_exige_login(client):
    assert client.get("/painel").status_code == 302


def test_aluno_inscreve_cancela_e_ve_painel(app, client):
    cadastrar(client)
    entrar(client)
    client.post("/vagas/1/inscrever")
    assert "Cancelar inscrição" in client.get("/painel").text
    client.post("/vagas/1/inscrever")  # repetida não duplica
    assert n_inscricoes(app, "ana_9") == 1
    client.post("/vagas/1/cancelar")
    assert n_inscricoes(app, "ana_9") == 0


def test_aluno_nao_publica_vaga_nem_acessa_admin(client):
    cadastrar(client)
    entrar(client)
    assert client.post("/vagas/nova", data={}).status_code == 403
    assert client.post("/admin/voluntarios/1/aprovar").status_code == 403


def test_voluntario_precisa_de_aprovacao_do_admin(app, client):
    cadastrar(client, tipo="voluntario", apelido="vol_1", contato="vol@example.com",
              boletim="sim")
    assert usuario(app, "vol_1").status == "pendente_aprovacao"
    vaga = {"disciplina": "Matemática", "descricao": "Reforço de álgebra", "bairro": "Grajaú",
            "modalidade": "online", "dia_horario": "Sábados 10h", "vagas_total": "5"}
    entrar(client, "vol_1")
    client.post("/vagas/nova", data=vaga)
    assert vagas_de(app, "vol_1") == []
    client.post("/sair")

    entrar(client, "admin", "senha-admin-teste")
    assert "vol_1" in client.get("/painel").text
    client.post(f"/admin/voluntarios/{usuario(app, 'vol_1').id}/aprovar")
    client.post("/sair")

    entrar(client, "vol_1")
    client.post("/vagas/nova", data=vaga)
    client.post("/vagas/nova", data={**vaga, "vagas_total": "999"})  # inválida
    vagas = vagas_de(app, "vol_1")
    assert len(vagas) == 1
    assert "Encerrar" in client.get("/painel").text
    client.post(f"/vagas/{vagas[0][0]}/encerrar")
    assert vagas_de(app, "vol_1")[0][1] is False
    assert client.post("/vagas/1/encerrar").status_code == 403  # vaga de outro


def test_admin_recusa_voluntario(app, client):
    cadastrar(client, tipo="voluntario", apelido="vol_2", contato="v2@example.com")
    entrar(client, "admin", "senha-admin-teste")
    client.post(f"/admin/voluntarios/{usuario(app, 'vol_2').id}/recusar")
    assert usuario(app, "vol_2") is None


# ---------- direitos do titular ----------
def test_exportar_dados(client):
    cadastrar(client, faixa_etaria="12_17", contato="pai@example.com")
    entrar(client)
    r = client.get("/meus-dados/exportar")
    assert r.json["apelido"] == "ana_9" and r.json["contato"] == "pai@example.com"
    assert "attachment" in r.headers["Content-Disposition"]


def test_excluir_conta(app, client):
    cadastrar(client)
    entrar(client)
    client.post("/vagas/1/inscrever")
    client.post("/meus-dados/excluir", data={"senha": "errada"})
    assert usuario(app, "ana_9") is not None
    client.post("/meus-dados/excluir", data={"senha": "segredo123"})
    assert usuario(app, "ana_9") is None
    with app.app_context():
        ultimo = Auditoria.query.order_by(Auditoria.id.desc()).first()
        assert ultimo.acao == "excluiu_conta" and "usuario:" not in ultimo.alvo


# ---------- API ----------
def test_api_publica(client):
    assert len(client.get("/api/v1/vagas").json) == 4
    assert len(client.get("/api/v1/materiais").json) >= 5
    assert client.get("/api/v1/nada").json["erro"]


def test_indicadores_respeitam_k_anonimato(client):
    cadastrar(client)
    ind = client.get("/api/v1/indicadores").json
    assert ind["alunos_ativos"] == 1 and ind["alunos_por_bairro"] == {}


def test_tutor_degrada_com_elegancia(client):
    assert client.post("/api/v1/tutor", json={"pergunta": ""}).status_code == 400
    r = client.post("/api/v1/tutor", json={"pergunta": "Como somar frações?"})
    assert r.status_code == 200 and r.json["fonte"] == "indisponivel"


def test_endereco_descarta_rua_e_cep(client):
    r = client.post("/api/v1/endereco", json={
        "logradouro": "Rua A, 10", "cep": "00000-000", "bairro": "capão redondo",
        "cidade": "são paulo", "uf": "sp"})
    assert r.json == {"bairro": "Capão Redondo", "cidade": "São Paulo", "uf": "SP",
                      "descartados": ["cep", "logradouro"]}
    assert client.post("/api/v1/endereco", json={}).status_code == 400


def test_integracao_exige_chave(client):
    assert client.post("/api/v1/integracao/voluntarios", json=[]).status_code == 401
    assert client.get("/api/v1/integracao/boletim/destinatarios",
                      headers={"X-API-Key": "errada"}).status_code == 401


def test_integracao_rpa_lote_e_boletim(app, client):
    h = {"X-API-Key": "chave-teste"}
    r = client.post("/api/v1/integracao/voluntarios", headers=h, json=[
        {"apelido": "rpa_vol", "email": "rpa@example.com", "aceita_boletim": True},
        {"apelido": "x", "email": "invalido"},
    ])
    assert r.status_code == 201 and r.json == {"criados": ["rpa_vol"], "rejeitados": ["x"]}
    assert client.post("/api/v1/integracao/voluntarios", headers=h, json={}).status_code == 400
    # pendente não entra na lista do boletim
    assert client.get("/api/v1/integracao/boletim/destinatarios", headers=h).json == []
    with app.app_context():
        Usuario.query.filter_by(apelido="rpa_vol").first().status = "ativo"
        db.session.commit()
    lista = client.get("/api/v1/integracao/boletim/destinatarios", headers=h).json
    assert lista == [{"apelido": "rpa_vol", "email": "rpa@example.com"}]
