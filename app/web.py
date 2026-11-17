"""Páginas do MVP (HTML renderizado no servidor: leve para celular de entrada)."""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from . import limiter
from .config import VERSAO_TERMO
from .models import (
    DISCIPLINAS,
    FAIXAS,
    SERIES,
    Auditoria,
    Inscricao,
    Material,
    Usuario,
    Vaga,
    agora,
    auditar,
    db,
    expurgar_pendentes,
)
from .seguranca import (
    RE_APELIDO,
    RE_EMAIL,
    cifrar,
    decifrar,
    exige_login,
    exige_papel,
    hash_token,
    mascarar_email,
    novo_token,
)

web = Blueprint("web", __name__)
K_ANONIMATO = 5  # grupos menores que isso não aparecem nos indicadores


@web.app_context_processor
def _globais():
    return {
        "DISCIPLINAS": DISCIPLINAS, "SERIES": SERIES, "VERSAO_TERMO": VERSAO_TERMO,
        "CONTATO_PRIVACIDADE": current_app.config.get("PRIVACY_CONTACT", ""),
    }


# ---------------- páginas públicas ----------------
@web.get("/")
def inicio():
    vagas = Vaga.query.filter_by(ativa=True).order_by(Vaga.id.desc()).limit(3).all()
    numeros = {
        "vagas": Vaga.query.filter_by(ativa=True).count(),
        "materiais": Material.query.count(),
        "voluntarios": Usuario.query.filter_by(papel="voluntario", status="ativo").count(),
    }
    return render_template("inicio.html", vagas=vagas, numeros=numeros)


@web.get("/vagas")
def vagas():
    disciplina = request.args.get("disciplina", "")
    bairro = request.args.get("bairro", "").strip()[:60]
    q = Vaga.query.filter_by(ativa=True)
    if disciplina in DISCIPLINAS:
        q = q.filter_by(disciplina=disciplina)
    if bairro:
        q = q.filter(Vaga.bairro.ilike(f"%{bairro}%"))
    minhas = set()
    if g.usuario and g.usuario.papel == "aluno":
        minhas = {i.vaga_id for i in g.usuario.inscricoes}
    return render_template(
        "vagas.html", vagas=q.order_by(Vaga.disciplina).all(),
        disciplina=disciplina, bairro=bairro, minhas=minhas,
    )


@web.get("/materiais")
def materiais():
    disciplina = request.args.get("disciplina", "")
    q = Material.query
    if disciplina in DISCIPLINAS:
        q = q.filter_by(disciplina=disciplina)
    return render_template(
        "materiais.html", materiais=q.order_by(Material.disciplina).all(),
        disciplina=disciplina,
    )


@web.get("/tutor")
def tutor():
    return render_template("tutor.html")


@web.get("/privacidade")
def privacidade():
    return render_template("privacidade.html")


# ---------------- cadastro, consentimento e sessão ----------------
@web.route("/cadastro", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def cadastro():
    tipo = request.values.get("tipo", "aluno")
    if tipo not in ("aluno", "voluntario"):
        tipo = "aluno"
    if request.method == "GET":
        return render_template("cadastro.html", tipo=tipo, form={})

    f = {k: request.form.get(k, "").strip() for k in
         ("apelido", "senha", "serie", "bairro", "faixa_etaria", "contato")}
    erros = []
    if not RE_APELIDO.match(f["apelido"]):
        erros.append("O apelido deve ter de 3 a 30 letras, números, ponto, traço ou _.")
    elif Usuario.query.filter(func.lower(Usuario.apelido) == f["apelido"].lower()).first():
        erros.append("Esse apelido já está em uso. Escolha outro.")
    if len(f["senha"]) < 8:
        erros.append("A senha precisa ter pelo menos 8 caracteres.")
    if not f["bairro"] or len(f["bairro"]) > 60:
        erros.append("Informe o bairro (só o bairro, sem rua nem número).")
    if request.form.get("aceite") != "sim":
        erros.append("É preciso ler e aceitar o Aviso de Privacidade.")

    menor = False
    if tipo == "aluno":
        if f["serie"] not in SERIES:
            erros.append("Escolha a série.")
        if f["faixa_etaria"] not in FAIXAS:
            erros.append("Escolha a faixa de idade.")
        menor = f["faixa_etaria"] in ("menor_12", "12_17")
        if menor and not RE_EMAIL.match(f["contato"]):
            erros.append("Para menores de 18 anos, informe o e-mail de um responsável.")
    elif not RE_EMAIL.match(f["contato"]):
        erros.append("Informe um e-mail válido para contato da coordenação.")

    if erros:
        for e in erros:
            flash(e, "erro")
        f["senha"] = ""
        return render_template("cadastro.html", tipo=tipo, form=f), 400

    u = Usuario(
        apelido=f["apelido"],
        senha_hash=generate_password_hash(f["senha"]),
        papel=tipo,
        bairro=f["bairro"],
        aceita_boletim=tipo == "voluntario" and request.form.get("boletim") == "sim",
    )
    link = None
    if tipo == "aluno":
        u.serie, u.faixa_etaria = f["serie"], f["faixa_etaria"]
        if menor:
            token, u.consentimento_token_hash = novo_token()
            u.contato_cifrado = cifrar(f["contato"])
            u.status = "pendente_consentimento"
            link = url_for("web.consentimento", token=token, _external=True)
        else:
            u.status = "ativo"
            u.consentimento_versao, u.consentimento_em = VERSAO_TERMO, agora()
    else:
        u.faixa_etaria = "18_mais"
        u.contato_cifrado = cifrar(f["contato"])
        u.status = "pendente_aprovacao"
        u.consentimento_versao, u.consentimento_em = VERSAO_TERMO, agora()

    expurgar_pendentes()
    db.session.add(u)
    db.session.flush()
    auditar("titular", "cadastro_" + tipo, f"usuario:{u.id}")
    db.session.commit()
    current_app.logger.info("cadastro papel=%s status=%s", u.papel, u.status)
    return render_template("cadastro_ok.html", usuario=u, link=link)


@web.route("/consentimento/<token>", methods=["GET", "POST"])
def consentimento(token: str):
    u = Usuario.query.filter_by(consentimento_token_hash=hash_token(token)).first()
    if u is None or u.status != "pendente_consentimento":
        abort(404)
    if request.method == "POST":
        if request.form.get("decisao") == "autorizo":
            u.status = "ativo"
            u.consentimento_versao, u.consentimento_em = VERSAO_TERMO, agora()
            u.consentimento_token_hash = None
            auditar("responsavel", "consentimento_concedido", f"usuario:{u.id}")
            db.session.commit()
            return render_template("consentimento_ok.html", autorizado=True)
        # Recusa: o cadastro do menor é apagado na hora.
        auditar("responsavel", "consentimento_negado", f"usuario:{u.id}")
        db.session.delete(u)
        db.session.commit()
        return render_template("consentimento_ok.html", autorizado=False)
    return render_template("consentimento.html", aluno=u)


@web.route("/entrar", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def entrar():
    if request.method == "POST":
        apelido = request.form.get("apelido", "").strip()
        u = Usuario.query.filter(func.lower(Usuario.apelido) == apelido.lower()).first()
        if u and check_password_hash(u.senha_hash, request.form.get("senha", "")):
            session.clear()
            session["uid"] = u.id
            session.permanent = True
            return redirect(url_for("web.painel"))
        current_app.logger.warning("login recusado")  # sem apelido nem IP no log
        flash("Apelido ou senha incorretos.", "erro")
        return render_template("entrar.html"), 401
    return render_template("entrar.html")


@web.post("/sair")
def sair():
    session.clear()
    return redirect(url_for("web.inicio"))


# ---------------- área logada ----------------
@web.get("/painel")
@exige_login
def painel():
    u = g.usuario
    if u.papel == "admin":
        pendentes = Usuario.query.filter_by(status="pendente_aprovacao").all()
        por_bairro = (
            db.session.query(Usuario.bairro, func.count(Usuario.id))
            .filter_by(papel="aluno", status="ativo")
            .group_by(Usuario.bairro).all()
        )
        indicadores = [
            (b, n if n >= K_ANONIMATO else None) for b, n in por_bairro if b
        ]
        trilha = Auditoria.query.order_by(Auditoria.id.desc()).limit(20).all()
        return render_template(
            "painel_admin.html", pendentes=pendentes, indicadores=indicadores,
            trilha=trilha, k=K_ANONIMATO,
        )
    contato = mascarar_email(decifrar(u.contato_cifrado))
    if u.papel == "voluntario":
        return render_template("painel_voluntario.html", contato=contato)
    return render_template("painel_aluno.html", contato=contato)


@web.post("/vagas/<int:vaga_id>/inscrever")
@exige_papel("aluno")
def inscrever(vaga_id: int):
    vaga = db.get_or_404(Vaga, vaga_id)
    u = g.usuario
    if not u.ativo:
        flash("Sua conta ainda espera a autorização do responsável.", "aviso")
    elif Inscricao.query.filter_by(vaga_id=vaga.id, aluno_id=u.id).first():
        flash("Você já está inscrito nesta monitoria.", "aviso")
    elif not vaga.ativa or vaga.vagas_livres == 0:
        flash("Esta monitoria não tem mais vagas.", "aviso")
    else:
        db.session.add(Inscricao(vaga_id=vaga.id, aluno_id=u.id))
        db.session.commit()
        flash("Inscrição feita! Veja os detalhes no seu painel.", "ok")
    return redirect(url_for("web.vagas"))


@web.post("/vagas/<int:vaga_id>/cancelar")
@exige_papel("aluno")
def cancelar(vaga_id: int):
    i = Inscricao.query.filter_by(vaga_id=vaga_id, aluno_id=g.usuario.id).first_or_404()
    db.session.delete(i)
    db.session.commit()
    flash("Inscrição cancelada.", "ok")
    return redirect(url_for("web.painel"))


@web.post("/vagas/nova")
@exige_papel("voluntario")
def nova_vaga():
    u = g.usuario
    if not u.ativo:
        flash("Seu cadastro de voluntário ainda espera aprovação da coordenação.", "aviso")
        return redirect(url_for("web.painel"))
    f = {k: request.form.get(k, "").strip() for k in
         ("disciplina", "descricao", "bairro", "modalidade", "dia_horario", "vagas_total")}
    try:
        total = int(f["vagas_total"])
    except ValueError:
        total = 0
    if (
        f["disciplina"] not in DISCIPLINAS or f["modalidade"] not in ("presencial", "online")
        or not (5 <= len(f["descricao"]) <= 280) or not f["bairro"] or len(f["bairro"]) > 60
        or not f["dia_horario"] or len(f["dia_horario"]) > 60 or not (1 <= total <= 40)
    ):
        flash("Confira os campos da monitoria (vagas de 1 a 40).", "erro")
        return redirect(url_for("web.painel"))
    db.session.add(Vaga(
        voluntario_id=u.id, disciplina=f["disciplina"], descricao=f["descricao"],
        bairro=f["bairro"], modalidade=f["modalidade"], dia_horario=f["dia_horario"],
        vagas_total=total,
    ))
    db.session.commit()
    flash("Monitoria publicada.", "ok")
    return redirect(url_for("web.painel"))


@web.post("/vagas/<int:vaga_id>/encerrar")
@exige_papel("voluntario")
def encerrar_vaga(vaga_id: int):
    vaga = db.get_or_404(Vaga, vaga_id)
    if vaga.voluntario_id != g.usuario.id:
        abort(403)
    vaga.ativa = False
    db.session.commit()
    flash("Monitoria encerrada.", "ok")
    return redirect(url_for("web.painel"))


@web.post("/admin/voluntarios/<int:uid>/<decisao>")
@exige_papel("admin")
def decidir_voluntario(uid: int, decisao: str):
    alvo = db.get_or_404(Usuario, uid)
    if alvo.status != "pendente_aprovacao" or decisao not in ("aprovar", "recusar"):
        abort(400)
    if decisao == "aprovar":
        alvo.status = "ativo"
    else:
        db.session.delete(alvo)
    auditar(f"usuario:{g.usuario.id}", "voluntario_" + decisao, f"usuario:{uid}")
    db.session.commit()
    flash("Decisão registrada.", "ok")
    return redirect(url_for("web.painel"))


# ---------------- direitos do titular (LGPD art. 18) ----------------
@web.get("/meus-dados/exportar")
@exige_login
def exportar():
    u = g.usuario
    auditar("titular", "exportou_dados", f"usuario:{u.id}")
    db.session.commit()
    dados = {
        "apelido": u.apelido, "papel": u.papel, "status": u.status, "serie": u.serie,
        "bairro": u.bairro, "faixa_etaria": u.faixa_etaria,
        "contato": decifrar(u.contato_cifrado), "aceita_boletim": u.aceita_boletim,
        "consentimento": {
            "versao": u.consentimento_versao,
            "em": u.consentimento_em.isoformat() if u.consentimento_em else None,
        },
        "criado_em": u.criado_em.isoformat(),
        "inscricoes": [
            {"monitoria": i.vaga.disciplina, "bairro": i.vaga.bairro,
             "em": i.criada_em.isoformat()} for i in u.inscricoes
        ],
        "monitorias_oferecidas": [v.publico() for v in u.vagas],
    }
    resp = jsonify(dados)
    resp.headers["Content-Disposition"] = "attachment; filename=meus-dados.json"
    return resp


@web.post("/meus-dados/excluir")
@exige_login
def excluir():
    u = g.usuario
    if u.papel == "admin":
        abort(400)
    if not check_password_hash(u.senha_hash, request.form.get("senha", "")):
        flash("Senha incorreta. Nada foi apagado.", "erro")
        return redirect(url_for("web.painel"))
    auditar("titular", "excluiu_conta", u.papel)  # sem identificador do titular
    db.session.delete(u)  # cascata apaga inscrições e monitorias
    db.session.commit()
    session.clear()
    flash("Sua conta e seus dados foram apagados.", "ok")
    return redirect(url_for("web.inicio"))
