"""
app.py - Interface Streamlit para o h3-indexing

Envolve a CLI existente (cli.py) em uma interface web, permitindo:
    - Upload do arquivo vetorial de entrada (.shp/.gpkg/.geojson, com
      suporte a .zip para shapefiles com múltiplos arquivos)
    - Configuração da resolução H3
    - Configuração dinâmica dos atributos: as colunas disponíveis são lidas
      diretamente do arquivo enviado e oferecidas em uma lista de seleção,
      evitando erros de digitação
    - Prévia interativa das fórmulas de cada atributo, simulando um
      hexágono com polígonos reais do arquivo antes de gerar a grade
    - Execução do pipeline e download do resultado
"""

from __future__ import annotations

import html
import io
import tempfile
import traceback
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Polygon
import streamlit as st
from branca.colormap import LinearColormap
from streamlit_folium import st_folium
import folium

from src.h3_indexing.cli import run as run_pipeline
from src.h3_indexing.distribution import (
    AttributeType,
    distribute_attributes,
    weighted_column_name,
)
from src.h3_indexing.overlay import EQUAL_AREA_CRS
from src.h3_indexing.validation import validate_layer

# ---------------------------------------------------------------------------
# Paleta de cores - identidade TRAMA (verde-floresta + verde-limão), com um
# tom dourado complementar para diferenciar atributos intensivos. As cores
# base dos widgets ficam em .streamlit/config.toml; estas são usadas no HTML
# próprio (cabeçalho, cartões, pills) e no mapa.
# ---------------------------------------------------------------------------
COR_FUNDO_ESCURO = "#1f3d24"
COR_FUNDO_ESCURO_2 = "#16291b"
COR_VERDE = "#2f6b3a"
COR_VERDE_MEDIO = "#5f9a3c"
COR_VERDE_LIMAO = "#c8e639"
COR_VERDE_LIMAO_SUAVE = "#eef6c8"
COR_DOURADO = "#c9952f"
COR_DOURADO_SUAVE = "#fbf1da"
COR_TEXTO_CLARO = "#e9f1df"
COR_TEXTO_ESCURO = "#1c2a1f"
COR_TEXTO_SUAVE = "#5d6b5f"
COR_FUNDO_CLARO = "#f6f7f2"
COR_BORDA_SUAVE = "#dde3d3"
FONTE = "'Inter', 'Helvetica', 'Arial', sans-serif"

# ---------------------------------------------------------------------------
# Ícones em SVG puro (sem depender de fontes externas ou de conversão de
# shortcode em HTML bruto, que não é aplicada de forma confiável fora dos
# elementos nativos do Streamlit). Usam stroke="currentColor" para herdar
# automaticamente a cor do texto ao redor.
# ---------------------------------------------------------------------------
_TRACOS_ICONES = {
    "hexagono": '<polygon points="12,2.5 20.5,7.5 20.5,16.5 12,21.5 3.5,16.5 3.5,7.5"/>',
    "caixa": (
        '<path d="M3.5 8.5 5.8 4.7A1.7 1.7 0 0 1 7.3 3.9h9.4a1.7 1.7 0 0 1 1.5.8l2.3 3.8"/>'
        '<rect x="3.5" y="8.5" width="17" height="11.6" rx="1.4"/>'
        '<path d="M3.5 8.5h17"/>'
    ),
    "tendencia": '<polyline points="3,17 9,11 13,15 21,6"/><polyline points="15,6 21,6 21,12"/>',
    "divisao": (
        '<circle cx="12" cy="6" r="1.5"/><line x1="5" y1="12" x2="19" y2="12"/>'
        '<circle cx="12" cy="18" r="1.5"/>'
    ),
    "camadas": (
        '<polygon points="12,3 21,8 12,13 3,8"/>'
        '<polyline points="3,12.5 12,17.5 21,12.5"/>'
        '<polyline points="3,16.5 12,21.5 21,16.5"/>'
    ),
    "grade": (
        '<polygon points="7.5,3 11,5 11,9 7.5,11 4,9 4,5"/>'
        '<polygon points="16.5,3 20,5 20,9 16.5,11 13,9 13,5"/>'
        '<polygon points="12,12 15.5,14 15.5,18 12,20 8.5,18 8.5,14"/>'
    ),
    "arquivo": (
        '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14,3 14,8 19,8"/>'
    ),
    "lista": (
        '<line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/>'
        '<line x1="9" y1="18" x2="20" y2="18"/><circle cx="4.5" cy="6" r="1"/>'
        '<circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>'
    ),
    "funcao": (
        '<path d="M14.5 4.5c-1.8-.6-3.4.2-3.9 2.2L8.4 17.3c-.5 2-2.1 2.8-3.9 2.2"/>'
        '<line x1="7" y1="9.5" x2="14" y2="9.5"/>'
        '<path d="m15 13 5 5"/><path d="m20 13-5 5"/>'
    ),
    "terminal": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/>'
        '<polyline points="7,9 10,12 7,15"/><line x1="12.5" y1="15" x2="17" y2="15"/>'
    ),
    "mapa": (
        '<polygon points="3,6 9,3.5 15,6 21,3.5 21,18 15,20.5 9,18 3,20.5"/>'
        '<line x1="9" y1="3.5" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="20.5"/>'
    ),
    "relogio": '<circle cx="12" cy="12" r="9"/><polyline points="12,7 12,12 15.5,14"/>',
}


def _icone(nome: str, classe: str = "icone-inline") -> str:
    """Devolve o SVG inline do ícone `nome`."""
    return (
        f'<svg class="{classe}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f"{_TRACOS_ICONES[nome]}</svg>"
    )


st.set_page_config(
    page_title="h3-indexing · TRAMA",
    page_icon=":material/hexagon:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Padrão de hexágonos usado como textura no cabeçalho (SVG em data URI).
_PADRAO_HEX = (
    "url(\"data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='56' height='97' viewBox='0 0 56 97'>"
    "<path d='M28 66 0 50V17L28 1l28 16v33zM28 97 0 81' fill='none' "
    "stroke='%23c8e639' stroke-opacity='0.10' stroke-width='1.2'/>"
    "<path d='M56 81 28 97' fill='none' stroke='%23c8e639' stroke-opacity='0.10' "
    "stroke-width='1.2'/></svg>\")"
)

CSS = f"""
<style>
    /* ---------- Layout geral ---------- */
    [data-testid="stMainBlockContainer"] {{
        max-width: 1240px;
        padding-top: 2.2rem;
        padding-bottom: 4rem;
    }}
    [data-testid="stHeader"] {{
        background: transparent;
    }}

    /* ---------- Cabeçalho ---------- */
    .hero {{
        position: relative;
        overflow: hidden;
        background: {_PADRAO_HEX}, radial-gradient(120% 140% at 100% 0%,
            #2f6b3a 0%, {COR_FUNDO_ESCURO} 45%, {COR_FUNDO_ESCURO_2} 100%);
        color: {COR_TEXTO_CLARO};
        padding: 2rem 2.2rem 1.6rem;
        border-radius: 20px;
        margin-bottom: 1.6rem;
        box-shadow: 0 18px 40px -22px rgba(22, 41, 27, 0.55);
    }}
    .hero-eyebrow {{
        display: inline-flex;
        align-items: center;
        gap: 0.45em;
        font-size: 0.74rem;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: {COR_VERDE_LIMAO};
        background: rgba(200, 230, 57, 0.12);
        border: 1px solid rgba(200, 230, 57, 0.28);
        padding: 0.3em 0.8em;
        border-radius: 999px;
    }}
    .hero-titulo {{
        font-family: 'Plus Jakarta Sans', {FONTE};
        font-size: 2.3rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: #ffffff;
        margin: 0.6rem 0 0.2rem;
        line-height: 1.15;
    }}
    .hero-titulo span {{
        color: {COR_VERDE_LIMAO};
    }}
    .hero-sub {{
        font-size: 1rem;
        color: rgba(233, 241, 223, 0.78);
        max-width: 640px;
        margin: 0;
    }}

    /* ---------- Etapas ---------- */
    .etapas {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-top: 1.5rem;
    }}
    .etapa {{
        display: inline-flex;
        align-items: center;
        gap: 0.55em;
        padding: 0.42em 0.95em 0.42em 0.45em;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 500;
        color: rgba(233, 241, 223, 0.65);
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .etapa-num {{
        display: inline-grid;
        place-items: center;
        width: 1.55em;
        height: 1.55em;
        border-radius: 50%;
        font-size: 0.8rem;
        font-weight: 700;
        background: rgba(255, 255, 255, 0.1);
    }}
    .etapa-ativa {{
        color: #ffffff;
        background: rgba(200, 230, 57, 0.14);
        border-color: rgba(200, 230, 57, 0.45);
    }}
    .etapa-ativa .etapa-num {{
        background: {COR_VERDE_LIMAO};
        color: {COR_FUNDO_ESCURO_2};
    }}
    .etapa-feita {{
        color: {COR_TEXTO_CLARO};
    }}
    .etapa-feita .etapa-num {{
        background: {COR_VERDE_MEDIO};
        color: #ffffff;
    }}

    /* ---------- Cartões de resumo (KPIs) ---------- */
    .kpis {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 0.9rem;
        margin-bottom: 0.4rem;
    }}
    .kpi {{
        display: flex;
        gap: 0.85rem;
        align-items: flex-start;
        background: #ffffff;
        border: 1px solid {COR_BORDA_SUAVE};
        border-radius: 16px;
        padding: 1rem 1.1rem;
        box-shadow: 0 1px 2px rgba(28, 42, 31, 0.04);
        min-width: 0;
    }}
    .kpi-icone {{
        flex-shrink: 0;
        display: grid;
        place-items: center;
        width: 2.4rem;
        height: 2.4rem;
        border-radius: 12px;
        background: {COR_VERDE_LIMAO_SUAVE};
        color: {COR_VERDE};
    }}
    .kpi-icone svg {{
        width: 1.2rem;
        height: 1.2rem;
    }}
    .kpi-corpo {{
        min-width: 0;
    }}
    .kpi-rotulo {{
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: {COR_TEXTO_SUAVE};
    }}
    .kpi-valor {{
        font-size: 1.08rem;
        font-weight: 700;
        color: {COR_TEXTO_ESCURO};
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-top: 0.1rem;
    }}
    .kpi-detalhe {{
        font-size: 0.82rem;
        color: {COR_TEXTO_SUAVE};
        margin-top: 0.1rem;
    }}
    .kpi-vazio .kpi-valor {{
        color: #9aa59b;
        font-weight: 500;
    }}

    /* ---------- Cabeçalhos de seção ---------- */
    .secao {{
        display: flex;
        align-items: center;
        gap: 0.8rem;
        margin: 2.1rem 0 0.9rem;
    }}
    .secao-icone {{
        flex-shrink: 0;
        display: grid;
        place-items: center;
        width: 2.3rem;
        height: 2.3rem;
        border-radius: 11px;
        background: {COR_FUNDO_ESCURO};
        color: {COR_VERDE_LIMAO};
    }}
    .secao-icone svg {{
        width: 1.15rem;
        height: 1.15rem;
    }}
    .secao-titulo {{
        font-family: 'Plus Jakarta Sans', {FONTE};
        font-size: 1.22rem;
        font-weight: 700;
        color: {COR_TEXTO_ESCURO};
        line-height: 1.2;
    }}
    .secao-sub {{
        font-size: 0.88rem;
        color: {COR_TEXTO_SUAVE};
        margin-top: 0.1rem;
    }}

    /* ---------- Estado vazio ---------- */
    .vazio {{
        display: flex;
        align-items: center;
        gap: 0.9rem;
        background: #ffffff;
        border: 1px dashed #c9d2bd;
        border-radius: 16px;
        padding: 1.1rem 1.3rem;
        color: {COR_TEXTO_SUAVE};
        font-size: 0.93rem;
    }}
    .vazio svg {{
        width: 1.4rem;
        height: 1.4rem;
        flex-shrink: 0;
        color: #9aa59b;
    }}
    .vazio strong {{
        color: {COR_TEXTO_ESCURO};
        font-weight: 600;
    }}

    /* ---------- Pills de atributos ---------- */
    .pill-container {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.5em;
        margin: 0.9rem 0 0.3rem;
    }}
    .pill {{
        display: inline-flex;
        align-items: center;
        gap: 0.4em;
        padding: 0.38em 0.85em;
        border-radius: 999px;
        font-size: 0.84rem;
        font-weight: 600;
        border: 1px solid transparent;
        white-space: nowrap;
    }}
    .pill small {{
        font-weight: 500;
        opacity: 0.75;
    }}
    .pill-extensivo {{
        background-color: {COR_VERDE_LIMAO_SUAVE};
        color: {COR_FUNDO_ESCURO};
        border-color: #cfe08a;
    }}
    .pill-intensivo {{
        background-color: {COR_DOURADO_SUAVE};
        color: #7a5c15;
        border-color: #ecd29a;
    }}
    .pill-ponderado {{
        background-color: #ffffff;
        color: {COR_FUNDO_ESCURO};
        border-color: {COR_DOURADO};
        border-style: dashed;
    }}

    /* ---------- Ícones inline ---------- */
    .icone-inline {{
        width: 1em;
        height: 1em;
        vertical-align: -0.15em;
        flex-shrink: 0;
    }}

    /* ---------- Sidebar ---------- */
    [data-testid="stSidebar"] {{
        background-image: linear-gradient(180deg, #1b3321 0%, {COR_FUNDO_ESCURO_2} 60%);
    }}
    [data-testid="stSidebarUserContent"] {{
        padding-top: 0.5rem;
    }}
    .marca {{
        display: flex;
        align-items: center;
        gap: 0.7rem;
        padding-bottom: 1.1rem;
        margin-bottom: 0.4rem;
        border-bottom: 1px solid rgba(233, 241, 223, 0.12);
    }}
    .marca-icone {{
        display: grid;
        place-items: center;
        width: 2.4rem;
        height: 2.4rem;
        border-radius: 12px;
        background: {COR_VERDE_LIMAO};
        color: {COR_FUNDO_ESCURO_2};
    }}
    .marca-icone svg {{
        width: 1.3rem;
        height: 1.3rem;
    }}
    .marca-nome {{
        font-family: 'Plus Jakarta Sans', {FONTE};
        font-weight: 800;
        font-size: 1.12rem;
        color: #ffffff;
        line-height: 1.1;
    }}
    .marca-sub {{
        font-size: 0.75rem;
        color: rgba(233, 241, 223, 0.6);
        letter-spacing: 0.04em;
    }}
    .rotulo-sidebar {{
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: {COR_VERDE_LIMAO};
        margin: 1.2rem 0 0.35rem;
    }}
    [data-testid="stSidebar"] hr {{
        border-color: rgba(233, 241, 223, 0.12);
        margin: 1.1rem 0 0.4rem;
    }}
    /* Botão principal da sidebar: limão com texto escuro para contraste */
    [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {{
        color: {COR_FUNDO_ESCURO_2};
        font-weight: 700;
        box-shadow: 0 8px 20px -10px rgba(200, 230, 57, 0.7);
    }}
    [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] * {{
        color: {COR_FUNDO_ESCURO_2};
    }}

    /* ---------- Botões ---------- */
    [data-testid^="stBaseButton"] {{
        font-weight: 600;
        transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
    }}
    [data-testid^="stBaseButton"]:hover:not(:disabled) {{
        transform: translateY(-1px);
    }}
    [data-testid="stBaseButton-primary"]:hover:not(:disabled) {{
        filter: brightness(1.06);
    }}

    /* ---------- Contêineres com borda ---------- */
    [data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"],
    [data-testid="stMain"] [data-testid="stMetric"] {{
        background: #ffffff;
    }}

    /* ---------- Log (estilo terminal) ---------- */
    [data-testid="stMain"] [data-testid="stCode"] pre {{
        background: {COR_FUNDO_ESCURO_2} !important;
        border-radius: 14px;
        padding: 1.1rem 1.3rem !important;
    }}
    [data-testid="stMain"] [data-testid="stCode"] code {{
        color: {COR_TEXTO_CLARO} !important;
        font-size: 0.84rem;
        line-height: 1.7;
    }}

    /* ---------- Fórmulas ---------- */
    [data-testid="stMain"] .katex-display {{
        background: {COR_FUNDO_CLARO};
        border: 1px solid {COR_BORDA_SUAVE};
        border-radius: 12px;
        padding: 0.9rem 1rem;
        overflow-x: auto;
        overflow-y: hidden;
    }}

    /* ---------- Mapa ---------- */
    iframe[title="streamlit_folium.st_folium"] {{
        border-radius: 14px;
    }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


EXTENSOES_ACEITAS = ["shp", "gpkg", "geojson", "json", "zip"]
FORMATOS_SAIDA = {
    "GeoPackage (.gpkg)": "gpkg",
    "Shapefile (.shp)": "shp",
    "GeoJSON (.geojson)": "geojson",
}


def _extrair_shapefile_zip(zip_bytes: bytes, destino: Path) -> Path:
    """
    Extrai um .zip contendo um shapefile e retorna o caminho do .shp.

    Args:
        zip_bytes (bytes): conteúdo do arquivo .zip.
        destino (Path): diretório onde os arquivos serão extraídos.

    Returns:
        Path: caminho do arquivo .shp extraído.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(destino)
    shp_files = list(destino.rglob("*.shp"))
    if not shp_files:
        raise ValueError("Nenhum arquivo .shp encontrado dentro do .zip enviado.")
    return shp_files[0]


def _resolver_caminho_leitura(nome: str, conteudo: bytes, destino: Path) -> Path:
    """
    Salva os bytes de um upload em `destino` e retorna o caminho utilizável
    pelo GeoPandas, extraindo o .zip automaticamente quando necessário.

    Args:
        nome (str): nome original do arquivo enviado.
        conteudo (bytes): conteúdo bruto do arquivo.
        destino (Path): diretório onde o arquivo será salvo/extraído.

    Returns:
        Path: caminho pronto para ser lido pelo GeoPandas.
    """
    caminho = destino / nome
    caminho.write_bytes(conteudo)
    if nome.lower().endswith(".zip"):
        return _extrair_shapefile_zip(conteudo, destino)
    return caminho


def _salvar_upload(arquivo, destino_dir: Path) -> Path:
    """
    Salva o UploadedFile do Streamlit em disco e retorna o caminho utilizável.

    Args:
        arquivo: UploadedFile do Streamlit.
        destino_dir (Path): diretório onde o arquivo será salvo.

    Returns:
        Path: caminho do arquivo salvo.
    """
    return _resolver_caminho_leitura(arquivo.name, arquivo.getvalue(), destino_dir)


@st.cache_data(show_spinner=False)
def _listar_colunas(conteudo: bytes, nome: str) -> list[str]:
    """
    Lê apenas o esquema do arquivo de entrada e retorna as colunas
    disponíveis para redistribuição (a coluna de geometria é excluída).
    Prioriza colunas numéricas; se nenhuma for encontrada, retorna todas.

    O cache é indexado pelo conteúdo e nome do arquivo, então trocar o
    upload atualiza a lista automaticamente.

    Args:
        conteudo (bytes): conteúdo bruto do arquivo enviado.
        nome (str): nome original do arquivo (usado para decidir extração de .zip).

    Returns:
        list[str]: nomes das colunas disponíveis para configuração.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        caminho_leitura = _resolver_caminho_leitura(nome, conteudo, tmp_path)
        gdf = gpd.read_file(caminho_leitura, rows=1)

    nome_geom = gdf.geometry.name if hasattr(gdf, "geometry") else "geometry"
    numericas = [
        coluna
        for coluna in gdf.columns
        if coluna != nome_geom and pd.api.types.is_numeric_dtype(gdf[coluna])
    ]
    if numericas:
        return numericas
    return [coluna for coluna in gdf.columns if coluna != nome_geom]


@st.cache_data(show_spinner=False)
def _ler_tabela_atributos(conteudo: bytes, nome: str) -> pd.DataFrame:
    """
    Lê a tabela de atributos do arquivo de entrada (sem geometria) e acrescenta
    a área de cada polígono, calculada exatamente como no pipeline: após
    `validate_layer` e no CRS de área equivalente usado por `overlay.py`.

    Args:
        conteudo (bytes): conteúdo bruto do arquivo enviado.
        nome (str): nome original do arquivo (usado para decidir extração de .zip).

    Returns:
        pd.DataFrame: atributos originais + coluna "_orig_area" (m²).
    """
    with tempfile.TemporaryDirectory() as tmp:
        caminho_leitura = _resolver_caminho_leitura(nome, conteudo, Path(tmp))
        gdf = validate_layer(gpd.read_file(caminho_leitura))

    tabela = pd.DataFrame(gdf.drop(columns=gdf.geometry.name))
    tabela["_orig_area"] = gdf.to_crs(EQUAL_AREA_CRS).geometry.area.to_numpy()
    return tabela.reset_index(drop=True)


def _rotulo_poligono(tabela: pd.DataFrame, indice: int) -> str:
    """Rótulo legível de um polígono: primeira coluna de texto, se houver."""
    colunas_texto = [
        c for c in tabela.columns
        if not c.startswith("_") and not pd.api.types.is_numeric_dtype(tabela[c])
    ]
    if colunas_texto:
        return f"{tabela.at[indice, colunas_texto[0]]} (#{indice})"
    return f"Polígono #{indice}"


def _fmt(valor: float, casas: int = 2) -> str:
    """Formata número no padrão brasileiro (1.234,56); NaN vira travessão."""
    if valor is None or pd.isna(valor):
        return "—"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _tex(texto: str) -> str:
    """Escapa um nome de coluna para uso dentro de \\text{} no LaTeX."""
    escapes = {
        "\\": r"\textbackslash{}",
        "^": r"\textasciicircum{}",
        "~": r"\textasciitilde{}",
        **{c: "\\" + c for c in "{}_%&#$"},
    }
    return r"\text{" + "".join(escapes.get(c, c) for c in texto) + "}"


def _num(valor: float, casas: int = 2) -> str:
    """Como `_fmt`, mas protege a vírgula decimal para o modo matemático do LaTeX."""
    return _fmt(valor, casas).replace(",", "{,}")


def _formula_latex(coluna: str, tipo: str, peso: str | None) -> str:
    """Fórmula geral do atributo, com os nomes reais das colunas."""
    v = _tex(coluna)
    if tipo == "extensivo":
        return (
            v + r"_{hex} = \sum_i " + v + r"_i \cdot "
            r"\frac{\text{área}_{\cap i}}{\text{área}_{poli\,i}}"
        )
    if tipo == "intensivo":
        return (
            v + r"_{hex} = \frac{\sum_i " + v + r"_i \cdot \text{área}_{\cap i}}"
            r"{\sum_i \text{área}_{\cap i}}"
        )
    p = _tex(peso)
    return (
        _tex(weighted_column_name(coluna, peso)) + r"_{hex} = "
        r"\frac{\sum_i " + v + r"_i \cdot f_i}{\sum_i " + p + r"_i \cdot f_i}"
        r",\quad f_i = \frac{\text{área}_{\cap i}}{\text{área}_{poli\,i}}"
    )


EXPLICACAO_TIPO = {
    "extensivo": (
        "Cada polígono entrega ao hexágono a fração do seu valor proporcional à "
        "parte da sua área que cai dentro dele. A soma é conservada: um polígono "
        "100% coberto entrega o valor inteiro."
    ),
    "intensivo": (
        "O hexágono recebe a média dos valores dos polígonos que o cobrem, "
        "ponderada pela área de interseção. O valor nunca sai da faixa dos "
        "valores de entrada."
    ),
    "ponderado": (
        "Numerador e denominador são repartidos como extensivos e a divisão é "
        "feita no hexágono (razão das somas). Polígonos com mais peso (ex.: "
        "mais população) dentro do hexágono influenciam mais o resultado."
    ),
}


def _simular_hexagono(
    tabela: pd.DataFrame,
    coluna: str,
    tipo: str,
    peso: str | None,
    fracoes: dict[int, float],
) -> tuple[float, pd.DataFrame, str]:
    """
    Simula um hexágono hipotético que cobre a fração `fracoes[i]` (0 a 1) da
    área de cada polígono `i`, calculando o valor com o mesmo
    `distribute_attributes` do pipeline.

    Returns:
        tuple: (valor no hexágono, tabela de contribuições por polígono,
            LaTeX com a substituição numérica da fórmula).
    """
    indices = [i for i, f in fracoes.items() if f > 0]
    if not indices:
        return float("nan"), pd.DataFrame(), ""

    linhas = tabela.loc[indices]
    f = pd.Series([fracoes[i] for i in indices], index=indices)
    area_inter = linhas["_orig_area"] * f
    colunas_dados = [coluna] + ([peso] if peso else [])
    intersected = gpd.GeoDataFrame(
        {
            "h3_index": ["hex"] * len(indices),
            **{c: linhas[c].to_numpy(dtype=float) for c in colunas_dados},
            "_orig_area": linhas["_orig_area"].to_numpy(),
            "_intersection_area": area_inter.to_numpy(),
            "geometry": [Polygon()] * len(indices),
        }
    )
    hex_gdf = gpd.GeoDataFrame({"h3_index": ["hex"], "geometry": [Polygon()]})

    if tipo == "ponderado":
        saida = distribute_attributes(intersected, hex_gdf, {}, [(coluna, peso)])
        coluna_saida = weighted_column_name(coluna, peso)
    else:
        saida = distribute_attributes(
            intersected, hex_gdf, {coluna: AttributeType(tipo)}
        )
        coluna_saida = coluna
    valor = saida[coluna_saida].iloc[0] if not saida.empty else float("nan")

    contrib = pd.DataFrame(
        {
            "Polígono": [_rotulo_poligono(tabela, i) for i in indices],
            coluna: linhas[coluna].to_numpy(),
            "Área do polígono (km²)": (linhas["_orig_area"] / 1e6).to_numpy(),
            "% dentro do hexágono": (f * 100).to_numpy(),
            "Área ∩ (km²)": (area_inter / 1e6).to_numpy(),
        }
    )
    if tipo == "extensivo":
        contrib["Contribuição"] = (linhas[coluna] * f).to_numpy()
        termos = [rf"{_num(linhas.at[i, coluna])} \cdot {_num(f[i], 3)}" for i in indices]
        conta = " + ".join(termos)
    elif tipo == "intensivo":
        contrib["Peso na média (%)"] = (area_inter / area_inter.sum() * 100).to_numpy()
        num = " + ".join(
            rf"{_num(linhas.at[i, coluna])} \cdot {_num(area_inter[i] / 1e6, 3)}"
            for i in indices
        )
        den = " + ".join(_num(area_inter[i] / 1e6, 3) for i in indices)
        conta = rf"\frac{{{num}}}{{{den}}}"
    else:
        contrib[peso] = linhas[peso].to_numpy()
        contrib[f"{coluna} repartido"] = (linhas[coluna] * f).to_numpy()
        contrib[f"{peso} repartido"] = (linhas[peso] * f).to_numpy()
        num = " + ".join(
            rf"{_num(linhas.at[i, coluna])} \cdot {_num(f[i], 3)}" for i in indices
        )
        den = " + ".join(
            rf"{_num(linhas.at[i, peso])} \cdot {_num(f[i], 3)}" for i in indices
        )
        conta = rf"\frac{{{num}}}{{{den}}}"

    latex = _tex(coluna_saida) + r"_{hex} = " + conta + " = " + _num(valor)
    return valor, contrib, latex


def _montar_mapa(
    gdf: "gpd.GeoDataFrame",
    coluna_cor: str | None,
    gdf_original: "gpd.GeoDataFrame | None" = None,
) -> folium.Map:
    """
    Monta um mapa Folium dos hexágonos, coloridos por `coluna_cor` se houver.

    Se `gdf_original` for informado, a camada de entrada é sobreposta como
    um contorno tracejado, em um FeatureGroup próprio, para que o usuário
    possa ligar/desligar cada camada pelo controle no canto do mapa.
    """
    gdf_wgs84 = gdf.to_crs(epsg=4326)
    centro = gdf_wgs84.geometry.union_all().centroid
    mapa = folium.Map(
        location=[centro.y, centro.x],
        zoom_start=10,
        tiles="OpenStreetMap",
    )

    # Estilo da legenda do branca e dos controles do Leaflet
    mapa.get_root().html.add_child(
        folium.Element(
            f"""
            <link rel="stylesheet"
                  href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap">
            <style>
                .leaflet-container {{
                    font-family: {FONTE};
                }}
                /* Mapa de fundo (OpenStreetMap) dessaturado, para que as
                   cores dos hexágonos se destaquem */
                .leaflet-tile-pane {{
                    filter: grayscale(0.85) brightness(1.06) contrast(0.92);
                }}
                .leaflet-control.legend,
                .leaflet-control-layers {{
                    background-color: rgba(255, 255, 255, 0.96) !important;
                    border: 1px solid {COR_BORDA_SUAVE} !important;
                    border-radius: 12px !important;
                    box-shadow: 0 6px 20px -8px rgba(28, 42, 31, 0.35) !important;
                    padding: 8px 12px !important;
                    font-size: 12px;
                    color: {COR_TEXTO_ESCURO};
                }}
                .leaflet-bar {{
                    border: 1px solid {COR_BORDA_SUAVE} !important;
                    border-radius: 10px !important;
                    overflow: hidden;
                    box-shadow: 0 6px 20px -8px rgba(28, 42, 31, 0.35) !important;
                }}
                .leaflet-control.legend .axis path,
                .leaflet-control.legend .axis line {{
                    fill: none;
                    stroke: {COR_TEXTO_SUAVE};
                    stroke-width: 1px;
                    shape-rendering: crispEdges;
                }}
                .leaflet-control.legend .axis text {{
                    fill: {COR_TEXTO_ESCURO};
                    font-family: {FONTE};
                    font-size: 10px;
                }}
                .leaflet-control.legend .caption {{
                    fill: {COR_TEXTO_ESCURO};
                    font-family: {FONTE};
                    font-size: 12px;
                    font-weight: 700;
                }}
                .leaflet-tooltip {{
                    font-family: {FONTE};
                    border-radius: 8px;
                    border: 1px solid {COR_BORDA_SUAVE};
                    box-shadow: 0 6px 16px -8px rgba(28, 42, 31, 0.4);
                }}
            </style>
            """
        )
    )

    destaque = lambda _: {"weight": 2.2, "color": COR_FUNDO_ESCURO, "fillOpacity": 0.92}  # noqa: E731

    # ---------- Camada dos hexágonos H3 (resultado) ----------
    grupo_hexagonos = folium.FeatureGroup(name="Hexágonos H3 (resultado)", show=True)

    if coluna_cor and coluna_cor in gdf_wgs84.columns:
        valores = gdf_wgs84[coluna_cor].astype(float)
        # Escala sequencial clara → escura: valores altos ficam mais escuros
        colormap = LinearColormap(
            colors=["#f3f8d6", COR_VERDE_LIMAO, COR_VERDE_MEDIO, COR_FUNDO_ESCURO],
            vmin=float(valores.min()),
            vmax=float(valores.max()),
            caption=coluna_cor,
            text_color=COR_TEXTO_ESCURO,
        )
        colormap.height = 58

        def estilo(feature):
            valor = feature["properties"].get(coluna_cor)
            cor = colormap(valor) if valor is not None else "#d5d9cf"
            return {
                "fillColor": cor,
                "color": "#ffffff",
                "weight": 0.8,
                "fillOpacity": 0.82,
            }

        folium.GeoJson(
            gdf_wgs84.__geo_interface__,
            style_function=estilo,
            highlight_function=destaque,
            tooltip=folium.GeoJsonTooltip(
                fields=[coluna_cor], aliases=[f"{coluna_cor}:"], localize=True
            ),
        ).add_to(grupo_hexagonos)
        colormap.add_to(mapa)  # legenda de cor fica fixa no mapa, fora do grupo
    else:
        folium.GeoJson(
            gdf_wgs84.__geo_interface__,
            style_function=lambda _: {
                "fillColor": COR_VERDE_LIMAO,
                "color": COR_FUNDO_ESCURO,
                "weight": 0.8,
                "fillOpacity": 0.55,
            },
            highlight_function=destaque,
        ).add_to(grupo_hexagonos)

    grupo_hexagonos.add_to(mapa)

    # ---------- Camada original (entrada), para referência ----------
    bounds = gdf_wgs84.total_bounds  # minx, miny, maxx, maxy
    if gdf_original is not None and not gdf_original.empty:
        gdf_original_wgs84 = gdf_original.to_crs(epsg=4326)
        grupo_original = folium.FeatureGroup(name="Camada original (entrada)", show=True)
        folium.GeoJson(
            gdf_original_wgs84.__geo_interface__,
            style_function=lambda _: {
                "fillColor": "transparent",
                "fillOpacity": 0,
                "color": COR_DOURADO,
                "weight": 1.8,
                "dashArray": "5,4",
            },
        ).add_to(grupo_original)
        grupo_original.add_to(mapa)

        bounds_original = gdf_original_wgs84.total_bounds
        bounds = [
            min(bounds[0], bounds_original[0]),
            min(bounds[1], bounds_original[1]),
            max(bounds[2], bounds_original[2]),
            max(bounds[3], bounds_original[3]),
        ]

    folium.LayerControl(collapsed=True).add_to(mapa)
    mapa.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    return mapa


# ---------------------------------------------------------------------------
# Blocos de HTML reutilizados na interface
# ---------------------------------------------------------------------------
def _secao(icone: str, titulo: str, subtitulo: str = "") -> None:
    """Cabeçalho de seção da área principal: ícone + título + subtítulo."""
    sub = f'<div class="secao-sub">{subtitulo}</div>' if subtitulo else ""
    st.markdown(
        f'<div class="secao"><div class="secao-icone">{_icone(icone)}</div>'
        f'<div><div class="secao-titulo">{titulo}</div>{sub}</div></div>',
        unsafe_allow_html=True,
    )


def _kpi(icone: str, rotulo: str, valor: str, detalhe: str = "", vazio: bool = False) -> str:
    """HTML de um cartão de resumo."""
    classe = "kpi kpi-vazio" if vazio else "kpi"
    return (
        f'<div class="{classe}"><div class="kpi-icone">{_icone(icone)}</div>'
        f'<div class="kpi-corpo"><div class="kpi-rotulo">{rotulo}</div>'
        f'<div class="kpi-valor" title="{valor}">{valor}</div>'
        f'<div class="kpi-detalhe">{detalhe}</div></div></div>'
    )


def _vazio(icone: str, titulo: str, texto: str) -> str:
    """HTML de um estado vazio (nada para mostrar ainda)."""
    return f'<div class="vazio">{_icone(icone)}<div><strong>{titulo}</strong><br>{texto}</div></div>'


def _rotulo_sidebar(texto: str) -> None:
    st.markdown(f'<div class="rotulo-sidebar">{texto}</div>', unsafe_allow_html=True)


def _tamanho_arquivo(n_bytes: int) -> str:
    if n_bytes >= 1024 * 1024:
        return f"{_fmt(n_bytes / 1024 / 1024, 1)} MB"
    return f"{_fmt(n_bytes / 1024, 1)} KB"


# Sidebar - configuração
with st.sidebar:
    st.markdown(
        f"""
        <div class="marca">
            <div class="marca-icone">{_icone("hexagono")}</div>
            <div>
                <div class="marca-nome">h3-indexing</div>
                <div class="marca-sub">TRAMA · Agregação hexagonal</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _rotulo_sidebar("1 · Camada de entrada")
    arquivo_entrada = st.file_uploader(
        "Camada de entrada",
        type=EXTENSOES_ACEITAS,
        label_visibility="collapsed",
        help=(
            "Envie um GeoPackage (.gpkg), GeoJSON, ou um shapefile. "
            "Para shapefiles, envie um .zip contendo .shp, .shx, .dbf e .prj."
        ),
    )

    # Inicialização segura do estado (evita erros no primeiro carregamento)
    if "n_attrs" not in st.session_state:
        st.session_state.n_attrs = 1
    if "_arquivo_atual" not in st.session_state:
        st.session_state._arquivo_atual = None
    if "resultado" not in st.session_state:
        # Guarda o resultado da última execução do pipeline (log, bytes de
        # saída, GeoDataFrame já lido, etc.) para que trocar de widget --
        # como o seletor "Colorir por atributo" -- não exija reexecutar tudo.
        st.session_state.resultado = None

    identidade_arquivo = (
        (arquivo_entrada.name, arquivo_entrada.size) if arquivo_entrada else None
    )
    if st.session_state._arquivo_atual != identidade_arquivo:
        # Arquivo trocado: limpa seleções antigas para evitar colunas inválidas
        st.session_state._arquivo_atual = identidade_arquivo
        for chave in [k for k in st.session_state if k.startswith(("col_", "tipo_", "peso_", "sim_"))]:
            del st.session_state[chave]
        st.session_state.n_attrs = 1
        st.session_state.resultado = None

    colunas_disponiveis: list[str] = []
    erro_colunas: str | None = None
    if arquivo_entrada is not None:
        try:
            colunas_disponiveis = _listar_colunas(arquivo_entrada.getvalue(), arquivo_entrada.name)
        except Exception as exc:  # noqa: BLE001
            erro_colunas = str(exc)

    _rotulo_sidebar("2 · Grade e saída")
    resolucao = st.slider(
        "Resolução H3",
        min_value=0,
        max_value=15,
        value=8,
        help="Resolução da grade hexagonal H3 (0 = hexágonos enormes, 15 = minúsculos).",
    )
    area_hexagono_km2 = h3.average_hexagon_area(resolucao, unit="km^2")

    formato_saida_label = st.selectbox("Formato de saída", list(FORMATOS_SAIDA.keys()))
    formato_saida = FORMATOS_SAIDA[formato_saida_label]

    nome_saida = st.text_input("Nome do arquivo (sem extensão)", value="resultado")

    _rotulo_sidebar("3 · Atributos")
    st.caption(
        "**Extensivo**: grandezas somáveis (população, total). "
        "**Intensivo**: médias e taxas (renda média, densidade). "
        "**Ponderado**: razão entre duas colunas extensivas "
        "(ex.: renda total ÷ população)."
    )

    atributos_config: list[tuple[str, str, str | None]] = []

    if arquivo_entrada is None:
        st.info(
            "Envie uma camada para listar as colunas disponíveis.",
            icon=":material/info:",
        )
    elif erro_colunas:
        st.error(
            f"Não foi possível ler as colunas do arquivo enviado: {erro_colunas}",
            icon=":material/error:",
        )
    elif not colunas_disponiveis:
        st.warning(
            "Nenhuma coluna foi encontrada no arquivo enviado.",
            icon=":material/warning:",
        )
    else:
        for i in range(st.session_state.n_attrs):
            with st.container(border=True):
                st.caption(f"Atributo {i + 1}")
                coluna = st.selectbox(
                    "Coluna",
                    options=colunas_disponiveis,
                    index=min(i, len(colunas_disponiveis) - 1),
                    key=f"col_{i}",
                    label_visibility="collapsed",
                )
                tipo = st.selectbox(
                    "Tipo",
                    options=["extensivo", "intensivo", "ponderado"],
                    key=f"tipo_{i}",
                    label_visibility="collapsed",
                )
                peso = None
                if tipo == "ponderado":
                    peso = st.selectbox(
                        "Ponderar por (denominador)",
                        options=colunas_disponiveis,
                        key=f"peso_{i}",
                        help=(
                            "Coluna extensiva usada como denominador. O resultado é "
                            "Σ coluna / Σ peso em cada hexágono, gravado como "
                            "'coluna_por_peso'."
                        ),
                    )
            atributos_config.append((coluna, tipo, peso))

        # Os botões ficam abaixo da lista, então forçamos um rerun para que a
        # lista já reflita a mudança no mesmo clique.
        col_a, col_b = st.columns([4, 1])
        with col_a:
            if st.button(
                "Adicionar atributo",
                width="stretch",
                icon=":material/add:",
                disabled=st.session_state.n_attrs >= len(colunas_disponiveis),
            ):
                st.session_state.n_attrs += 1
                st.rerun()
        with col_b:
            if st.button(
                "",
                width="stretch",
                icon=":material/delete:",
                help="Remover o último atributo",
                disabled=st.session_state.n_attrs <= 1,
            ):
                st.session_state.n_attrs -= 1
                st.rerun()
        st.caption(f":material/database: {len(colunas_disponiveis)} coluna(s) disponível(is) no arquivo.")

    st.divider()
    executar = st.button(
        "Executar pipeline",
        width="stretch",
        type="primary",
        icon=":material/play_arrow:",
    )

# Área principal

# Um atributo ponderado gera a coluna "coluna_por_peso", então a mesma coluna
# pode aparecer como extensiva e ponderada; a duplicidade é checada na saída.
colunas_saida = [
    weighted_column_name(coluna, peso) if peso else coluna
    for coluna, _, peso in atributos_config
]
colunas_duplicadas = sorted({c for c in colunas_saida if colunas_saida.count(c) > 1})
pesos_invalidos = sorted({coluna for coluna, _, peso in atributos_config if peso == coluna})

# Cabeçalho com o andamento das etapas
etapas_concluidas = [
    arquivo_entrada is not None and not erro_colunas and bool(colunas_disponiveis),
    bool(atributos_config) and not colunas_duplicadas and not pesos_invalidos,
    bool(st.session_state.resultado and st.session_state.resultado.get("sucesso")),
]
etapa_ativa = next((n for n, feita in enumerate(etapas_concluidas) if not feita), None)
etapas_html = []
for n, (nome_etapa, feita) in enumerate(
    zip(["Enviar camada", "Configurar atributos", "Gerar hexágonos"], etapas_concluidas)
):
    classe = "etapa-feita" if feita else ("etapa-ativa" if n == etapa_ativa else "")
    marcador = "✓" if feita else str(n + 1)
    etapas_html.append(
        f'<span class="etapa {classe}"><span class="etapa-num">{marcador}</span>{nome_etapa}</span>'
    )

st.markdown(
    f"""
    <div class="hero">
        <span class="hero-eyebrow">{_icone("hexagono")} Plugin H3</span>
        <div class="hero-titulo">Agregação hexagonal <span>H3</span></div>
        <p class="hero-sub">
            Transforme camadas de polígonos em uma grade hexagonal H3,
            redistribuindo os atributos numéricos originais para cada hexágono.
        </p>
        <div class="etapas">{"".join(etapas_html)}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Resumo da configuração atual
contagem_tipos = {
    t: sum(1 for _, tipo, _ in atributos_config if tipo == t)
    for t in ["extensivo", "intensivo", "ponderado"]
}
detalhe_tipos = " · ".join(f"{n} {t}" for t, n in contagem_tipos.items() if n) or "nenhum configurado"
st.markdown(
    '<div class="kpis">'
    + _kpi(
        "camadas",
        "Camada de entrada",
        html.escape(arquivo_entrada.name) if arquivo_entrada else "Nenhum arquivo",
        f"{len(colunas_disponiveis)} coluna(s) disponível(is)"
        if colunas_disponiveis
        else "Envie pela barra lateral",
        vazio=arquivo_entrada is None,
    )
    + _kpi(
        "grade",
        "Resolução H3",
        f"Nível {resolucao}",
        f"≈ {_fmt(area_hexagono_km2, 4 if area_hexagono_km2 < 0.01 else 2)} km² por hexágono",
    )
    + _kpi(
        "arquivo",
        "Arquivo de saída",
        html.escape(f"{nome_saida}.{formato_saida}"),
        formato_saida_label.split(" (")[0],
    )
    + _kpi(
        "lista",
        "Atributos",
        str(len(atributos_config)),
        detalhe_tipos,
        vazio=not atributos_config,
    )
    + "</div>",
    unsafe_allow_html=True,
)

if atributos_config:
    pills_html = ['<div class="pill-container">']
    for coluna, tipo, peso in atributos_config:
        if tipo == "ponderado":
            pills_html.append(
                f'<span class="pill pill-ponderado">{_icone("divisao")} '
                f"{html.escape(coluna)} ÷ {html.escape(peso)} <small>{tipo}</small></span>"
            )
            continue
        classe = "pill-extensivo" if tipo == "extensivo" else "pill-intensivo"
        icone = _icone("caixa") if tipo == "extensivo" else _icone("tendencia")
        pills_html.append(
            f'<span class="pill {classe}">{icone} {html.escape(coluna)} <small>{tipo}</small></span>'
        )
    pills_html.append("</div>")
    st.markdown("".join(pills_html), unsafe_allow_html=True)

    if colunas_duplicadas:
        st.warning(
            f"Coluna(s) de saída repetida(s) (mesma coluna e tipo selecionados mais de uma vez): {', '.join(colunas_duplicadas)}.",
            icon=":material/warning:",
        )
    if pesos_invalidos:
        st.warning(
            "Atributo(s) ponderado(s) pela própria coluna: "
            f"{', '.join(pesos_invalidos)}.",
            icon=":material/warning:",
        )


# Prévia interativa das fórmulas
#
# Roda antes do pipeline: para cada atributo configurado, mostra a fórmula com
# os nomes reais das colunas e simula um hexágono hipotético sobre polígonos
# reais do arquivo. O valor simulado vem do próprio distribute_attributes, então
# a prévia usa exatamente a mesma lógica da execução.
if atributos_config and arquivo_entrada is not None and not erro_colunas:
    _secao(
        "funcao",
        "Prévia das fórmulas",
        "Escolha polígonos do arquivo e quanto da área de cada um cai dentro de "
        "um hexágono hipotético para acompanhar a conta passo a passo.",
    )
    try:
        with st.spinner("Lendo atributos do arquivo..."):
            tabela_atributos = _ler_tabela_atributos(
                arquivo_entrada.getvalue(), arquivo_entrada.name
            )
    except Exception as exc_tabela:  # noqa: BLE001
        tabela_atributos = None
        st.warning(
            f"Não foi possível ler os atributos para a prévia: {exc_tabela}",
            icon=":material/warning:",
        )

    if tabela_atributos is not None and not tabela_atributos.empty:
        rotulos_abas = [
            f"{coluna} ÷ {peso}" if peso else f"{coluna} · {tipo}"
            for coluna, tipo, peso in atributos_config
        ]
        indices_poligonos = list(range(len(tabela_atributos)))

        with st.container(border=True):
            abas = st.tabs(rotulos_abas)
            for i, (aba, (coluna, tipo, peso)) in enumerate(zip(abas, atributos_config)):
                with aba:
                    st.latex(_formula_latex(coluna, tipo, peso))
                    st.caption(EXPLICACAO_TIPO[tipo])

                    if peso == coluna:
                        st.info(
                            "Escolha uma coluna de ponderação diferente para simular.",
                            icon=":material/info:",
                        )
                        continue

                    selecionados = st.multiselect(
                        "Polígonos que cobrem o hexágono simulado",
                        options=indices_poligonos,
                        default=indices_poligonos[:2],
                        format_func=lambda idx: _rotulo_poligono(tabela_atributos, idx),
                        max_selections=4,
                        key=f"sim_{i}_poligonos",
                    )
                    if not selecionados:
                        st.info(
                            "Selecione ao menos um polígono para simular.",
                            icon=":material/info:",
                        )
                        continue

                    colunas_slider = st.columns(len(selecionados))
                    fracoes: dict[int, float] = {}
                    for col_slider, idx in zip(colunas_slider, selecionados):
                        with col_slider:
                            fracoes[idx] = (
                                st.slider(
                                    f"% de {_rotulo_poligono(tabela_atributos, idx)} no hexágono",
                                    min_value=0,
                                    max_value=100,
                                    value=50,
                                    step=5,
                                    format="%d%%",
                                    key=f"sim_{i}_fracao_{idx}",
                                )
                                / 100
                            )

                    try:
                        valor_hex, contribuicoes, conta_latex = _simular_hexagono(
                            tabela_atributos, coluna, tipo, peso, fracoes
                        )
                    except Exception as exc_sim:  # noqa: BLE001
                        st.warning(
                            f"Não foi possível simular este atributo: {exc_sim}",
                            icon=":material/warning:",
                        )
                        continue

                    if contribuicoes.empty:
                        st.info(
                            "O hexágono não cobre nenhum polígono: ele seria descartado.",
                            icon=":material/info:",
                        )
                        continue

                    st.latex(conta_latex)
                    coluna_saida = weighted_column_name(coluna, peso) if peso else coluna
                    col_metrica, col_tabela = st.columns([1, 3], vertical_alignment="center")
                    with col_metrica:
                        st.metric(f"{coluna_saida} no hexágono", _fmt(valor_hex), border=True)
                    with col_tabela:
                        st.dataframe(
                            contribuicoes,
                            hide_index=True,
                            width="stretch",
                            column_config={
                                c: st.column_config.NumberColumn(format="%.2f")
                                for c in contribuicoes.columns
                                if c != "Polígono"
                            },
                        )

_secao("terminal", "Execução", "Saída do pipeline, etapa por etapa.")
log_placeholder = st.empty()
log_placeholder.markdown(
    _vazio(
        "relogio",
        "Aguardando execução",
        "Configure a camada e os atributos e clique em <em>Executar pipeline</em> na barra lateral.",
    ),
    unsafe_allow_html=True,
)

# Execução do pipeline
#
# IMPORTANTE: o resultado é guardado em st.session_state (chave "resultado")
# em vez de ser renderizado apenas dentro deste "if executar:". Um botão do
# Streamlit só retorna True no rerun em que foi clicado -- em qualquer rerun
# seguinte (por exemplo, ao trocar o seletor "Colorir por atributo" mais
# abaixo) ele volta a ser False. Se o mapa/log fossem montados só aqui
# dentro, eles sumiriam a cada interação e o pipeline precisaria ser
# executado de novo. Guardando o resultado, a seção de exibição (fora deste
# bloco) consegue redesenhar o mapa com a nova cor sem reprocessar nada.
if executar:
    if arquivo_entrada is None:
        st.error("Envie um arquivo de entrada antes de executar.", icon=":material/error:")
    elif not atributos_config:
        st.error("Configure ao menos um atributo antes de executar.", icon=":material/error:")
    elif colunas_duplicadas:
        st.error(
            f"Corrija as colunas repetidas antes de executar: {', '.join(colunas_duplicadas)}.",
            icon=":material/error:",
        )
    elif pesos_invalidos:
        st.error(
            "Escolha uma coluna de ponderação diferente da própria coluna para: "
            f"{', '.join(pesos_invalidos)}.",
            icon=":material/error:",
        )
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            try:
                caminho_entrada = _salvar_upload(arquivo_entrada, tmp_path)
                caminho_saida = tmp_path / f"{nome_saida}.{formato_saida}"

                attrs_dict = {
                    coluna: AttributeType(tipo)
                    for coluna, tipo, peso in atributos_config
                    if not peso
                }
                ratios = [
                    (coluna, peso) for coluna, _, peso in atributos_config if peso
                ]

                buffer_log = io.StringIO()
                with st.spinner("Executando pipeline geoespacial..."):
                    with redirect_stdout(buffer_log):
                        run_pipeline(
                            input_path=str(caminho_entrada),
                            output_path=str(caminho_saida),
                            resolution=resolucao,
                            attrs=attrs_dict,
                            ratios=ratios,
                        )

                if caminho_saida.exists():
                    gdf_resultado = gpd.read_file(caminho_saida)
                    colunas_numericas = [
                        coluna for coluna in colunas_saida
                        if coluna in gdf_resultado.columns
                    ]
                    try:
                        gdf_original = gpd.read_file(caminho_entrada)
                    except Exception:  # noqa: BLE001
                        gdf_original = None
                    st.session_state.resultado = {
                        "sucesso": True,
                        "log": buffer_log.getvalue(),
                        "output_bytes": caminho_saida.read_bytes(),
                        "output_name": caminho_saida.name,
                        "gdf": gdf_resultado,
                        "colunas_numericas": colunas_numericas,
                        "gdf_original": gdf_original,
                    }
                else:
                    st.session_state.resultado = {
                        "sucesso": False,
                        "log": buffer_log.getvalue(),
                        "aviso": (
                            "O pipeline terminou, mas o arquivo de saída não foi "
                            f"encontrado em {caminho_saida}."
                        ),
                    }

            except Exception as exc:  # noqa: BLE001
                st.session_state.resultado = {
                    "sucesso": False,
                    "log": traceback.format_exc(),
                    "erro": str(exc),
                }
        # O cabeçalho (etapas) já foi desenhado neste rerun; redesenha para
        # refletir o novo resultado.
        st.rerun()

# Renderização do resultado -- roda em toda execução do script (não só
# quando o botão é clicado), lendo o que está guardado em session_state.
resultado = st.session_state.resultado
if resultado is not None:
    log_placeholder.code(resultado["log"], language="text")

    if resultado.get("erro") is not None:
        st.error(f"Erro ao executar o pipeline: {resultado['erro']}", icon=":material/error:")
    elif not resultado["sucesso"]:
        st.warning(resultado["aviso"], icon=":material/warning:")
    else:
        _secao("mapa", "Resultado", "Baixe o arquivo gerado e explore os hexágonos no mapa.")
        m1, m2, m3 = st.columns(3)
        m1.metric("Hexágonos gerados", _fmt(len(resultado["gdf"]), 0), border=True)
        m2.metric("Atributos calculados", len(resultado["colunas_numericas"]), border=True)
        m3.metric("Tamanho do arquivo", _tamanho_arquivo(len(resultado["output_bytes"])), border=True)

        st.download_button(
            f"Baixar {resultado['output_name']}",
            data=resultado["output_bytes"],
            file_name=resultado["output_name"],
            mime="application/octet-stream",
            type="primary",
            width="stretch",
            icon=":material/download:",
        )

        with st.container(border=True):
            try:
                colunas_numericas = resultado["colunas_numericas"]
                coluna_escolhida = st.selectbox(
                    "Colorir por atributo",
                    options=["(nenhum)"] + colunas_numericas,
                    index=1 if colunas_numericas else 0,
                    key="mapa_coluna_cor",
                )
                coluna_cor = None if coluna_escolhida == "(nenhum)" else coluna_escolhida
                mapa = _montar_mapa(resultado["gdf"], coluna_cor, resultado.get("gdf_original"))
                st_folium(mapa, width=None, height=560, returned_objects=[])
            except Exception as exc_mapa:  # noqa: BLE001
                st.warning(
                    f"Não foi possível gerar o mapa: {exc_mapa}",
                    icon=":material/warning:",
                )
