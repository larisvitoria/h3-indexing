#!/usr/bin/env python3
"""
md_to_pdf.py — Converte um arquivo Markdown em um PDF estilizado
(tema verde-escuro / verde-limão, inspirado no design anexado).

Uso:
    python3 md_to_pdf.py entrada.md saida.pdf

Dependências:
    pip install markdown weasyprint --break-system-packages
"""

import sys
import os
import markdown
from weasyprint import HTML, CSS

# ---------- Paleta de cores (baseada no anexo) ----------
COR_FUNDO_ESCURO = "#1f3d24"     # verde escuro (fundo)
COR_VERDE_LIMAO  = "#c8e639"     # verde-limão (destaque)
COR_TEXTO_CLARO  = "#f2f7e8"     # texto claro sobre fundo escuro
COR_TEXTO_ESCURO = "#1a1a1a"     # texto escuro sobre fundo claro

CSS_TEMA = f"""
@page {{
    size: A4;
    margin: 1cm 1cm;

    @top-center {{
        content: "";
    }}
    @bottom-center {{
        content: counter(page);
        font-size: 9pt;
        color: {COR_FUNDO_ESCURO};
    }}
}}

body {{
    font-family: 'Helvetica', 'Arial', sans-serif;
    color: {COR_TEXTO_ESCURO};
    line-height: 1.65;
    font-size: 11pt;
}}

/* Capa / cabeçalho de página com faixa verde escura */
.capa {{
    background-color: {COR_FUNDO_ESCURO};
    color: {COR_TEXTO_CLARO};
    padding: 1.4cm 2cm;
    text-align: center;
    border-radius: 8px;
    margin-bottom: 1.3cm;
}}
.capa h1 {{
    color: {COR_VERDE_LIMAO};
    font-size: 22pt;
    font-weight: 600;
    letter-spacing: 0.3px;
    margin: 0;
    border: none;
}}
.capa p {{
    color: {COR_TEXTO_CLARO};
    font-size: 10.5pt;
    opacity: 0.85;
    margin-top: 0.3cm;
}}

h1 {{
    color: {COR_FUNDO_ESCURO};
    border-bottom: 3px solid {COR_VERDE_LIMAO};
    padding-bottom: 6px;
    font-size: 19pt;
    font-weight: 600;
    margin-top: 1.2cm;
}}

h2 {{
    color: {COR_FUNDO_ESCURO};
    border-left: 5px solid {COR_VERDE_LIMAO};
    padding-left: 10px;
    font-size: 14.5pt;
    font-weight: 600;
    margin-top: 1cm;
}}

h3 {{
    color: {COR_FUNDO_ESCURO};
    font-size: 12pt;
    font-weight: 600;
    margin-top: 0.8cm;
}}

a {{
    color: {COR_FUNDO_ESCURO};
    font-weight: bold;
    text-decoration: none;
    border-bottom: 1px solid {COR_VERDE_LIMAO};
}}

strong {{
    color: {COR_FUNDO_ESCURO};
}}

blockquote {{
    background-color: #f3f8e9;
    border-left: 4px solid {COR_VERDE_LIMAO};
    margin: 0.6cm 0;
    padding: 0.35cm 0.8cm;
    color: #3a3a3a;
    font-style: italic;
    border-radius: 0 4px 4px 0;
}}

code {{
    background-color: #eef2e4;
    color: {COR_FUNDO_ESCURO};
    padding: 2px 5px;
    border-radius: 4px;
    font-family: 'Courier New', monospace;
    font-size: 10pt;
}}

pre {{
    background-color: {COR_FUNDO_ESCURO};
    color: {COR_TEXTO_CLARO};
    padding: 0.5cm;
    border-radius: 6px;
    overflow-x: auto;
}}
pre code {{
    background: none;
    color: {COR_TEXTO_CLARO};
}}

table {{
    width: 100%;
    border-collapse: collapse;
    margin: 0.6cm 0;
    font-size: 10.5pt;
}}
th {{
    background-color: {COR_FUNDO_ESCURO};
    color: {COR_VERDE_LIMAO};
    padding: 7px 10px;
    text-align: left;
    font-weight: 600;
}}
td {{
    padding: 7px 10px;
    border-bottom: 1px solid #e0e0e0;
}}
tr:nth-child(even) {{
    background-color: #f6f9ef;
}}

hr {{
    border: none;
    border-top: 2px solid {COR_VERDE_LIMAO};
    margin: 1cm 0;
}}

ul, ol {{
    margin-left: 0.4cm;
}}
li::marker {{
    color: {COR_FUNDO_ESCURO};
}}

img {{
  max-width: 75%;
  height: auto;
  display: block;
  
  margin: 1.5rem auto;

  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}}

#header img {{
  max-width: 100%;
}}
"""


def converter_md_para_pdf(caminho_md: str, caminho_pdf: str, titulo_capa: str = None, subtitulo_capa: str = None):
    with open(caminho_md, "r", encoding="utf-8") as f:
        texto_md = f.read()

    corpo_html = markdown.markdown(
        texto_md,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"]
    )

    capa_html = ""
    if titulo_capa:
        capa_html = f"""
        <div class="capa">
            <h1>{titulo_capa}</h1>
            {f'<p>{subtitulo_capa}</p>' if subtitulo_capa else ''}
        </div>
        """

    html_final = f"""
    <html>
    <head><meta charset="utf-8"></head>
    <body>
        {capa_html}
        {corpo_html}
    </body>
    </html>
    """

    # base_url aponta para a pasta do .md, permitindo que imagens
    # referenciadas com caminho relativo (ex: ![alt](imagens/foto.png))
    # sejam localizadas corretamente pelo WeasyPrint.
    pasta_base = os.path.dirname(os.path.abspath(caminho_md))

    HTML(string=html_final, base_url=pasta_base).write_pdf(
        caminho_pdf,
        stylesheets=[CSS(string=CSS_TEMA)]
    )
    print(f"PDF gerado com sucesso: {caminho_pdf}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python3 md_to_pdf.py entrada.md saida.pdf [\"Título da capa\"] [\"Subtítulo\"]")
        sys.exit(1)

    entrada = sys.argv[1]
    saida = sys.argv[2]
    titulo = sys.argv[3] if len(sys.argv) > 3 else None
    subtitulo = sys.argv[4] if len(sys.argv) > 4 else None

    converter_md_para_pdf(entrada, saida, titulo, subtitulo)
