"""Gera o PDF único de entrega a partir de relatorio.html.

Uso:  python docs/entrega/gerar_pdf.py
Requer: pip install playwright && playwright install chromium

- Links vêm de links.json (ficam clicáveis no PDF).
- Cada <figure data-print="NN-nome.png"> vira a imagem de docs/evidencias/,
  ou uma caixa tracejada "INSERIR PRINT" se o arquivo ainda não existir.
"""
from __future__ import annotations

import base64
import html
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
DOCS = AQUI.parent
SAIDA = AQUI / "entrega-secure-devops.pdf"


def _img(caminho: Path) -> str:
    tipo = "jpeg" if caminho.suffix.lower() in (".jpg", ".jpeg") else "png"
    return f"data:image/{tipo};base64,{base64.b64encode(caminho.read_bytes()).decode()}"


def _link(url: str, rotulo_vazio: str) -> str:
    if not url:
        return f'<span class="falta">{rotulo_vazio}</span>'
    u = html.escape(url, quote=True)
    return f'<a href="{u}">{u}</a>'


def montar() -> tuple[str, list[str]]:
    links = json.loads((AQUI / "links.json").read_text(encoding="utf-8"))
    pagina = (AQUI / "relatorio.html").read_text(encoding="utf-8")
    pagina = pagina.replace("{{URL_MVP}}", _link(links.get("url_mvp", ""), "PREENCHER URL DO MVP"))
    pagina = pagina.replace(
        "{{URL_REPO}}", _link(links.get("url_repositorio", ""), "PREENCHER URL DO REPOSITÓRIO")
    )
    pagina = pagina.replace("{{DIAGRAMA}}", _img(DOCS / "arquitetura.png"))
    faltando: list[str] = []

    def figura(m: re.Match) -> str:
        arquivo, legenda = m.group(1), m.group(2)
        caminho = DOCS / "evidencias" / arquivo
        if caminho.exists():
            corpo = f'<img src="{_img(caminho)}" alt="{html.escape(legenda)}">'
        else:
            faltando.append(arquivo)
            corpo = (
                '<div class="vazio">INSERIR PRINT<br>'
                f"<code>docs/evidencias/{arquivo}</code></div>"
            )
        return f"<figure>{corpo}<figcaption>{legenda}</figcaption></figure>"

    pagina = re.sub(r'<figure data-print="([^"]+)">(.*?)</figure>', figura, pagina, flags=re.S)
    return pagina, faltando


def main() -> int:
    pagina, faltando = montar()
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        aba = navegador.new_page()
        aba.set_content(pagina, wait_until="load")
        aba.pdf(
            path=str(SAIDA), format="A4", print_background=True,
            margin={"top": "16mm", "bottom": "16mm", "left": "15mm", "right": "15mm"},
        )
        navegador.close()
    print(f"PDF gerado: {SAIDA}")
    if faltando:
        print(f"Faltam {len(faltando)} prints: " + ", ".join(faltando))
    return 0


if __name__ == "__main__":
    sys.exit(main())
