"""Dados iniciais.

Materiais: links para recursos educacionais públicos e gratuitos.
Vagas de monitoria: DADOS SIMULADOS, marcados como demonstração, criados só
quando SEED_DEMO=1. Nenhum dado pessoal real é usado.
"""
from __future__ import annotations

import secrets

from werkzeug.security import generate_password_hash

from .models import Material, Usuario, Vaga, db

MATERIAIS = [
    ("Khan Academy — Matemática", "Matemática", "Todas",
     "https://pt.khanacademy.org/math",
     "Aulas em vídeo e exercícios gratuitos, do básico ao ensino médio."),
    ("Portal da OBMEP", "Matemática", "Todas",
     "https://portaldaobmep.impa.br/",
     "Videoaulas e exercícios da Olimpíada Brasileira de Matemática das Escolas Públicas."),
    ("Khan Academy — todas as matérias", "Português", "Todas",
     "https://pt.khanacademy.org/",
     "Português, ciências humanas e outras matérias com exercícios gratuitos."),
    ("Khan Academy — Ciências", "Ciências", "Todas",
     "https://pt.khanacademy.org/science",
     "Biologia, física e química com explicações passo a passo."),
    ("Scratch", "Tecnologia e programação", "Todas",
     "https://scratch.mit.edu/",
     "Aprenda lógica de programação criando jogos e animações com blocos."),
    ("Code.org", "Tecnologia e programação", "Todas",
     "https://code.org/",
     "Cursos gratuitos de introdução à computação, direto no navegador."),
]

VAGAS_DEMO = [
    ("Matemática", "[Demonstração] Reforço de frações e equações do 1º grau.",
     "Capão Redondo", "presencial", "Sábados, 9h às 11h", 8),
    ("Português", "[Demonstração] Leitura e interpretação de texto para o 9º ano.",
     "Grajaú", "presencial", "Terças, 18h às 19h30", 6),
    ("Redação", "[Demonstração] Oficina de redação para o ENEM.",
     "Cidade Tiradentes", "online", "Quintas, 19h às 20h30", 12),
    ("Tecnologia e programação", "[Demonstração] Primeiros passos em programação com Scratch.",
     "Brasilândia", "presencial", "Sábados, 14h às 16h", 10),
]


def semear(app) -> None:
    if not Material.query.first():
        for titulo, disc, serie, url, desc in MATERIAIS:
            db.session.add(
                Material(titulo=titulo, disciplina=disc, serie=serie, url=url, descricao=desc)
            )

    # Administrador: a senha vem do Key Vault (App Setting ADMIN_PASSWORD).
    senha_admin = app.config.get("ADMIN_PASSWORD")
    if senha_admin and not Usuario.query.filter_by(papel="admin").first():
        db.session.add(
            Usuario(
                apelido="admin",
                senha_hash=generate_password_hash(senha_admin),
                papel="admin",
                status="ativo",
                faixa_etaria="18_mais",
            )
        )

    if app.config.get("SEED_DEMO") and not Vaga.query.first():
        demo = Usuario.query.filter_by(apelido="voluntario_demo").first()
        if demo is None:
            demo = Usuario(
                apelido="voluntario_demo",
                # senha aleatória descartada: a conta de demonstração não faz login
                senha_hash=generate_password_hash(secrets.token_urlsafe(32)),
                papel="voluntario",
                status="ativo",
                faixa_etaria="18_mais",
            )
            db.session.add(demo)
            db.session.flush()
        for disc, desc, bairro, modalidade, quando, total in VAGAS_DEMO:
            db.session.add(
                Vaga(
                    voluntario_id=demo.id, disciplina=disc, descricao=desc, bairro=bairro,
                    modalidade=modalidade, dia_horario=quando, vagas_total=total,
                )
            )

    db.session.commit()
