"""Modelo de dados — minimização por desenho.

O que NÃO guardamos de propósito: nome completo, CPF/RG, data de nascimento,
endereço, telefone, foto ou documento do estudante. O aluno é identificado
por um apelido; a idade é só uma faixa; a localização é só o bairro.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

PAPEIS = ("aluno", "voluntario", "admin")
FAIXAS = ("menor_12", "12_17", "18_mais")
SERIES = (
    "6º ano EF", "7º ano EF", "8º ano EF", "9º ano EF",
    "1ª série EM", "2ª série EM", "3ª série EM",
)
DISCIPLINAS = (
    "Matemática", "Português", "Ciências", "Inglês",
    "Redação", "Tecnologia e programação",
)


def agora() -> datetime:
    return datetime.now(UTC)


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    apelido = db.Column(db.String(30), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.String(12), nullable=False, default="aluno")
    status = db.Column(db.String(24), nullable=False, default="ativo")
    serie = db.Column(db.String(20))
    bairro = db.Column(db.String(60))
    faixa_etaria = db.Column(db.String(10))
    # E-mail do responsável (aluno menor) ou do próprio voluntário.
    # Sempre cifrado em repouso com Fernet (chave no Key Vault).
    contato_cifrado = db.Column(db.LargeBinary)
    aceita_boletim = db.Column(db.Boolean, nullable=False, default=False)
    consentimento_versao = db.Column(db.String(20))
    consentimento_em = db.Column(db.DateTime(timezone=True))
    consentimento_token_hash = db.Column(db.String(64), index=True)
    criado_em = db.Column(db.DateTime(timezone=True), default=agora, nullable=False)

    inscricoes = db.relationship(
        "Inscricao", backref="aluno", cascade="all, delete-orphan"
    )
    vagas = db.relationship("Vaga", backref="voluntario", cascade="all, delete-orphan")

    @property
    def ativo(self) -> bool:
        return self.status == "ativo"


class Vaga(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voluntario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    disciplina = db.Column(db.String(40), nullable=False)
    descricao = db.Column(db.String(280), nullable=False)
    bairro = db.Column(db.String(60), nullable=False)
    modalidade = db.Column(db.String(12), nullable=False, default="presencial")
    dia_horario = db.Column(db.String(60), nullable=False)
    vagas_total = db.Column(db.Integer, nullable=False, default=5)
    ativa = db.Column(db.Boolean, nullable=False, default=True)

    inscricoes = db.relationship(
        "Inscricao", backref="vaga", cascade="all, delete-orphan"
    )

    @property
    def vagas_livres(self) -> int:
        return max(self.vagas_total - len(self.inscricoes), 0)

    def publico(self) -> dict:
        return {
            "id": self.id,
            "disciplina": self.disciplina,
            "descricao": self.descricao,
            "bairro": self.bairro,
            "modalidade": self.modalidade,
            "dia_horario": self.dia_horario,
            "vagas_total": self.vagas_total,
            "vagas_livres": self.vagas_livres,
        }


class Inscricao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vaga_id = db.Column(db.Integer, db.ForeignKey("vaga.id"), nullable=False)
    aluno_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    criada_em = db.Column(db.DateTime(timezone=True), default=agora, nullable=False)
    __table_args__ = (db.UniqueConstraint("vaga_id", "aluno_id"),)


class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(120), nullable=False)
    disciplina = db.Column(db.String(40), nullable=False)
    serie = db.Column(db.String(40), nullable=False, default="Todas")
    url = db.Column(db.String(300), nullable=False)
    descricao = db.Column(db.String(280), nullable=False)

    def publico(self) -> dict:
        return {
            "id": self.id,
            "titulo": self.titulo,
            "disciplina": self.disciplina,
            "serie": self.serie,
            "url": self.url,
            "descricao": self.descricao,
        }


class Auditoria(db.Model):
    """Trilha de quem fez o quê. Nunca registra o conteúdo do dado pessoal."""

    id = db.Column(db.Integer, primary_key=True)
    quando = db.Column(db.DateTime(timezone=True), default=agora, nullable=False)
    ator = db.Column(db.String(40), nullable=False)  # "usuario:12", "integracao", "titular"
    acao = db.Column(db.String(60), nullable=False)
    alvo = db.Column(db.String(60), nullable=False, default="")


def auditar(ator: str, acao: str, alvo: str = "") -> None:
    db.session.add(Auditoria(ator=ator, acao=acao, alvo=alvo))


def expurgar_pendentes(dias: int = 30) -> int:
    """Retenção: apaga cadastros de menores sem autorização há mais de `dias`."""
    limite = agora() - timedelta(days=dias)
    velhos = Usuario.query.filter(
        Usuario.status == "pendente_consentimento", Usuario.criado_em < limite
    ).all()
    for u in velhos:
        db.session.delete(u)
    if velhos:
        auditar("sistema", "expurgo_pendentes", f"{len(velhos)} contas")
    db.session.commit()
    return len(velhos)
