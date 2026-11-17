"""API v1 — contratos de integração com os outros componentes da GS.

Públicos (somente leitura, sem dado pessoal):
  GET  /api/v1/vagas          GET /api/v1/materiais       GET /api/v1/indicadores
  POST /api/v1/tutor          (GenAI: repassa a pergunta ao tutor IA)
  POST /api/v1/endereco       (Visão: recebe o endereço extraído e devolve só o bairro)
Protegidos por X-API-Key (robô UiPath):
  POST /api/v1/integracao/voluntarios        cadastro em lote
  GET  /api/v1/integracao/boletim/destinatarios
"""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.request

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from . import limiter
from .config import VERSAO_TERMO
from .models import Material, Usuario, Vaga, agora, auditar, db
from .seguranca import RE_APELIDO, RE_EMAIL, cifrar, decifrar, exige_chave_api

api = Blueprint("api", __name__)
K_ANONIMATO = 5
RESPOSTA_PADRAO = (
    "O tutor virtual está fora do ar agora. Enquanto isso, veja os materiais de "
    "estudo ou procure uma monitoria perto de você."
)


@api.get("/vagas")
def vagas():
    return jsonify([v.publico() for v in Vaga.query.filter_by(ativa=True).all()])


@api.get("/materiais")
def materiais():
    return jsonify([m.publico() for m in Material.query.all()])


@api.get("/indicadores")
def indicadores():
    """Indicadores agregados de impacto. Grupos com menos de 5 alunos são omitidos."""
    por_bairro = (
        db.session.query(Usuario.bairro, func.count(Usuario.id))
        .filter_by(papel="aluno", status="ativo").group_by(Usuario.bairro).all()
    )
    return jsonify(
        alunos_ativos=Usuario.query.filter_by(papel="aluno", status="ativo").count(),
        voluntarios_ativos=Usuario.query.filter_by(papel="voluntario", status="ativo").count(),
        monitorias_ativas=Vaga.query.filter_by(ativa=True).count(),
        alunos_por_bairro={b: n for b, n in por_bairro if b and n >= K_ANONIMATO},
        k_anonimato=K_ANONIMATO,
    )


@api.post("/tutor")
@limiter.limit("20 per minute")
def tutor():
    """Repassa só a pergunta e a série ao tutor IA — nunca a identidade do aluno."""
    corpo = request.get_json(silent=True) or {}
    pergunta = str(corpo.get("pergunta", "")).strip()[:500]
    if len(pergunta) < 3:
        return jsonify(erro="Escreva sua dúvida."), 400
    destino = current_app.config["TUTOR_API_URL"]
    if not destino.startswith("https://"):
        return jsonify(resposta=RESPOSTA_PADRAO, fonte="indisponivel")
    dados = json.dumps({"pergunta": pergunta, "serie": str(corpo.get("serie", ""))[:20]})
    req = urllib.request.Request(  # noqa: S310 - esquema https validado acima
        destino, data=dados.encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310  # nosec B310
            resposta = str(json.loads(r.read(64 * 1024)).get("resposta", ""))[:4000]
    except (urllib.error.URLError, TimeoutError, ValueError):
        current_app.logger.warning("tutor IA indisponível; usando resposta padrão")
        return jsonify(resposta=RESPOSTA_PADRAO, fonte="indisponivel")
    return jsonify(resposta=resposta or RESPOSTA_PADRAO, fonte="tutor-ia")


@api.post("/endereco")
@limiter.limit("30 per minute")
def endereco():
    """Recebe o endereço extraído pelo componente de Visão e devolve só o
    necessário para o cadastro (bairro, cidade, UF). Nada é gravado: rua,
    número e CEP são descartados aqui (minimização)."""
    corpo = request.get_json(silent=True) or {}
    bairro = str(corpo.get("bairro", "")).strip()[:60]
    if not bairro:
        return jsonify(erro="Campo 'bairro' é obrigatório."), 400
    return jsonify(
        bairro=bairro.title(),
        cidade=str(corpo.get("cidade", "")).strip()[:60].title(),
        uf=str(corpo.get("uf", "")).strip()[:2].upper(),
        descartados=sorted(set(corpo) - {"bairro", "cidade", "uf"}),
    )


@api.post("/integracao/voluntarios")
@exige_chave_api
def voluntarios_lote():
    """Cadastro em lote feito pelo robô. Entram como 'pendente_aprovacao'."""
    itens = request.get_json(silent=True)
    if not isinstance(itens, list) or len(itens) > 200:
        return jsonify(erro="Envie uma lista JSON com até 200 voluntários."), 400
    criados, rejeitados = [], []
    for item in itens:
        item = item if isinstance(item, dict) else {}
        apelido = str(item.get("apelido", "")).strip()
        email = str(item.get("email", "")).strip()
        existe = Usuario.query.filter(func.lower(Usuario.apelido) == apelido.lower()).first()
        if not RE_APELIDO.match(apelido) or not RE_EMAIL.match(email) or existe:
            rejeitados.append(apelido or "(vazio)")
            continue
        db.session.add(Usuario(
            apelido=apelido,
            # o voluntário define a própria senha depois; esta é descartável
            senha_hash=generate_password_hash(secrets.token_urlsafe(32)),
            papel="voluntario", status="pendente_aprovacao", faixa_etaria="18_mais",
            bairro=str(item.get("bairro", "")).strip()[:60],
            contato_cifrado=cifrar(email),
            aceita_boletim=bool(item.get("aceita_boletim")),
            consentimento_versao=VERSAO_TERMO, consentimento_em=agora(),
        ))
        criados.append(apelido)
    auditar("integracao", "cadastro_lote_voluntarios", f"{len(criados)} criados")
    db.session.commit()
    return jsonify(criados=criados, rejeitados=rejeitados), 201


@api.get("/integracao/boletim/destinatarios")
@exige_chave_api
def destinatarios_boletim():
    """Só adultos (voluntários) que marcaram que querem o boletim."""
    q = Usuario.query.filter_by(papel="voluntario", status="ativo", aceita_boletim=True)
    lista = [{"apelido": u.apelido, "email": decifrar(u.contato_cifrado)} for u in q]
    auditar("integracao", "leu_destinatarios_boletim", f"{len(lista)} contatos")
    db.session.commit()
    return jsonify(lista)
