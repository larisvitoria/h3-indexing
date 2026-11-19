"""
cli.py - interface de linha de comando (h3-indexing).

Exemplo de uso:

    h3-indexing \\
        --input bairros.shp \\
        --output resultado.gpkg \\
        --resolution 8 \\
        --attr populacao:extensivo \\
        --attr renda_media:intensivo \\
        --attr renda_total:ponderado:populacao
"""

import argparse
import sys
from typing import Dict, List, Optional, Tuple

from .distribution import AttributeType, distribute_attributes
from .h3_grid import generate_hex_grid
from .io import read_vector_file, write_vector_file
from .overlay import compute_intersection
from .validation import validate_layer


def _parse_attr(value: str) -> Tuple[str, AttributeType, Optional[str]]:
    """
    Parse de flags no formato 'coluna:extensivo', 'coluna:intensivo' ou
    'coluna:ponderado:coluna_peso'.

    Args:
        value (str): string no formato 'coluna:extensivo', 'coluna:intensivo'
            ou 'coluna:ponderado:coluna_peso'.

    Returns:
        Tuple[str, AttributeType, Optional[str]]: tupla contendo o nome da
            coluna, o tipo de atributo e a coluna de ponderação (apenas para
            o tipo ponderado; None nos demais).
    """
    if ":" not in value:
        raise argparse.ArgumentTypeError(
            f"Formato inválido para --attr: '{value}'. "
            "Use 'coluna:extensivo', 'coluna:intensivo' ou "
            "'coluna:ponderado:coluna_peso'."
        )
    name, _, rest = value.partition(":")
    kind, _, weight = rest.partition(":")
    name = name.strip()
    kind = kind.strip().lower()
    weight = weight.strip() or None
    try:
        attr_type = AttributeType(kind)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Tipo inválido em '--attr {value}'. "
            "Use apenas 'extensivo', 'intensivo' ou 'ponderado'."
        )
    if attr_type == AttributeType.WEIGHTED and weight is None:
        raise argparse.ArgumentTypeError(
            f"Atributo ponderado sem coluna de ponderação em '--attr {value}'. "
            "Use 'coluna:ponderado:coluna_peso'."
        )
    if attr_type != AttributeType.WEIGHTED and weight is not None:
        raise argparse.ArgumentTypeError(
            f"Coluna de ponderação só é permitida para o tipo 'ponderado' "
            f"(em '--attr {value}')."
        )
    return name, attr_type, weight


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="h3-indexing",
        description=(
            "Transforma uma camada vetorial de polígonos em uma grade hexagonal H3, "
            "redistribuindo atributos numéricos conforme sua natureza "
            "(extensivo/intensivo/ponderado)."
        ),
    )
    parser.add_argument(
        "--input", required=True, help="Caminho do shapefile/GeoPackage de entrada."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Caminho do arquivo de saída (.shp, .gpkg ou .geojson).",
    )
    parser.add_argument(
        "--resolution", type=int, required=True, help="Resolução H3 (0 a 15)."
    )
    parser.add_argument(
        "--attr",
        dest="attrs",
        action="append",
        required=True,
        type=_parse_attr,
        metavar="COLUNA:TIPO",
        help=(
            "Atributo a redistribuir, no formato 'coluna:extensivo', "
            "'coluna:intensivo' ou 'coluna:ponderado:coluna_peso' (razão "
            "entre dois extensivos, ex.: 'renda_total:ponderado:populacao'). "
            "Pode ser repetido para vários atributos."
        ),
    )
    return parser


def run(
    input_path: str,
    output_path: str,
    resolution: int,
    attrs: Dict[str, AttributeType],
    ratios: Optional[List[Tuple[str, str]]] = None,
) -> None:
    print(f"[1/6] Lendo camada de entrada: {input_path}")
    gdf = read_vector_file(input_path)

    print("[2/6] Validando geometria e CRS...")
    gdf = validate_layer(gdf)

    print(f"[3/6] Gerando grade hexagonal H3 (resolução {resolution})...")
    hex_gdf = generate_hex_grid(gdf, resolution)
    print(f"        {len(hex_gdf)} hexágonos gerados.")

    print("[4/6] Executando sobreposição espacial (overlay)...")
    intersected = compute_intersection(gdf, hex_gdf)

    print("[5/6] Calculando distribuição dos atributos...")
    result = distribute_attributes(intersected, hex_gdf, attrs, ratios)
    print(f"        {len(result)} hexágonos com atributos calculados.")

    print(f"[6/6] Exportando resultado: {output_path}")
    write_vector_file(result, output_path)

    print("Concluído.")


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    attrs = {
        name: attr_type
        for name, attr_type, _ in args.attrs
        if attr_type != AttributeType.WEIGHTED
    }
    ratios = [(name, weight) for name, _, weight in args.attrs if weight]

    try:
        run(args.input, args.output, args.resolution, attrs, ratios)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc) or "Ocorreu um erro não especificado."
        print(f"Erro [{type(exc).__name__}]: {msg}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
