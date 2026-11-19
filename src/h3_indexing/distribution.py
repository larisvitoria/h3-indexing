"""
distribution.py - cálculo de distribuição de atributos (extensivo/intensivo).

Fórmulas:

  Extensivo:  valor_hex = Σ valor_i × (área_∩i / área_poli_i)
  Intensivo:  valor_hex = Σ(valor_i × área_∩i) / Σ área_∩i
  Ponderado:  valor_hex = Σ(valor_i × f_i) / Σ(peso_i × f_i),
              com f_i = área_∩i / área_poli_i

O tipo ponderado gera a razão entre dois atributos extensivos (ex.: renda
total / população = renda per capita): numerador e denominador são
repartidos como extensivos e a divisão é feita no hexágono. O resultado é
gravado em uma nova coluna "{atributo}_por_{peso}".

A distinção entre os dois tipos é sempre um parâmetro explícito por
atributo, nunca inferida automaticamente.
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd


class AttributeType(str, Enum):
    EXTENSIVE = "extensivo"
    INTENSIVE = "intensivo"
    WEIGHTED = "ponderado"


def weighted_column_name(attr: str, weight: str) -> str:
    """Nome da coluna de saída de um atributo ponderado (ex.: 'renda_por_pop')."""
    return f"{attr}_por_{weight}"


def _distribute_extensive(intersected: gpd.GeoDataFrame, attr: str) -> pd.Series:
    """
    Atributo extensivo é definido como aquele cujo valor total em uma região é a soma
    dos valores das sub-regiões, proporcionalmente à área de interseção. A fórmula é:
    valor_hex = Σ valor_i × (área_∩i / área_poli_i)

    Args:
        intersected (gpd.GeoDataFrame): GeoDataFrame contendo a interseção entre
            os hexágonos H3 e as geometrias de entrada, com colunas:
              - "h3_index": índice H3 do hexágono
              - "_intersection_area": área da interseção entre o hexágono e a geometria
              - "_orig_area": área da geometria original
              - attr: coluna do atributo extensivo a ser distribuído
        attr (str): nome da coluna do atributo extensivo a ser distribuído.
    
    Returns:
        pd.Series: Série pandas com o valor agregado do atributo por hexágono,
            indexada pelo "h3_index".
    """
    weight = intersected["_intersection_area"] / intersected["_orig_area"]
    weighted_value = intersected[attr] * weight
    return weighted_value.groupby(intersected["h3_index"]).sum()


def _distribute_intensive(intersected: gpd.GeoDataFrame, attr: str) -> pd.Series:
    """
    Atributo intensivo é definido como aquele cujo valor em uma região é a média
    dos valores das sub-regiões, proporcionalmente à área de interseção. A fórmula é:
    valor_hex = Σ(valor_i × área_∩i) / Σ área_∩i

    Args:
        intersected (gpd.GeoDataFrame): GeoDataFrame contendo a interseção entre
            os hexágonos H3 e as geometrias de entrada, com colunas:
              - "h3_index": índice H3 do hexágono
              - "_intersection_area": área da interseção entre o hexágono e a geometria
              - attr: coluna do atributo intensivo a ser distribuído
        attr (str): nome da coluna do atributo intensivo a ser distribuído.

    Returns:
        pd.Series: Série pandas com o valor agregado do atributo por hexágono,
            indexada pelo "h3_index".
    """
    weighted_value = intersected[attr] * intersected["_intersection_area"]
    numerator = weighted_value.groupby(intersected["h3_index"]).sum()
    denominator = intersected["_intersection_area"].groupby(intersected["h3_index"]).sum()
    return numerator / denominator


def _distribute_weighted(
    intersected: gpd.GeoDataFrame, attr: str, weight: str
) -> pd.Series:
    """
    Atributo ponderado é a razão entre dois atributos extensivos, calculada
    após repartir ambos pelos hexágonos (razão das somas). A fórmula é:
    valor_hex = Σ(valor_i × f_i) / Σ(peso_i × f_i), com f_i = área_∩i / área_poli_i

    Equivale à média de valor_i / peso_i ponderada pela quantidade de "peso"
    (ex.: população) que cai em cada hexágono.

    Args:
        intersected (gpd.GeoDataFrame): GeoDataFrame contendo a interseção entre
            os hexágonos H3 e as geometrias de entrada, com colunas:
              - "h3_index": índice H3 do hexágono
              - "_intersection_area": área da interseção entre o hexágono e a geometria
              - "_orig_area": área da geometria original
              - attr: coluna do numerador (extensivo)
              - weight: coluna do denominador (extensivo)
        attr (str): nome da coluna do numerador.
        weight (str): nome da coluna usada como denominador.

    Returns:
        pd.Series: Série pandas com a razão por hexágono, indexada pelo
            "h3_index". Hexágonos com denominador zero recebem NaN.
    """
    numerator = _distribute_extensive(intersected, attr)
    denominator = _distribute_extensive(intersected, weight)
    return (numerator / denominator).replace([np.inf, -np.inf], np.nan)


def distribute_attributes(
    intersected: gpd.GeoDataFrame,
    hex_gdf: gpd.GeoDataFrame,
    attributes: Dict[str, AttributeType],
    ratios: Optional[List[Tuple[str, str]]] = None,
) -> gpd.GeoDataFrame:
    """
    Calcula, para cada atributo configurado, o valor agregado por hexágono.

    Args:
        intersected (gpd.GeoDataFrame): GeoDataFrame contendo a interseção entre
            os hexágonos H3 e as geometrias de entrada, com colunas:
              - "h3_index": índice H3 do hexágono
              - "_intersection_area": área da interseção entre o hexágono e a geometria
              - "_orig_area": área da geometria original (necessário para atributos
                extensivos e ponderados)
              - colunas dos atributos a serem distribuídos
        hex_gdf (gpd.GeoDataFrame): GeoDataFrame contendo os hexágonos H3 gerados, com colunas:
              - "h3_index": índice H3 do hexágono
              - "geometry": polígono shapely do hexágono (EPSG:4326)
        attributes (Dict[str, AttributeType]): dicionário mapeando
            nomes de colunas para seus respectivos tipos (extensivo ou intensivo).
        ratios (Optional[List[Tuple[str, str]]]): lista de pares
            (atributo, peso) para atributos ponderados. Cada par gera a coluna
            "{atributo}_por_{peso}". Por ser uma lista separada, a mesma coluna
            pode ser usada como extensiva e ponderada, ou ponderada por pesos
            diferentes, na mesma execução.

    Returns:
        gpd.GeoDataFrame: GeoDataFrame contendo os hexágonos H3 com os valores
            agregados dos atributos, com colunas:
              - "h3_index": índice H3 do hexágono
              - "geometry": polígono shapely do hexágono (EPSG:4326)
              - colunas dos atributos agregados (atributos ponderados são
                gravados como "{atributo}_por_{peso}")
    """
    result = hex_gdf.set_index("h3_index").copy()
    output_cols = []

    for attr, attr_type in attributes.items():
        if attr not in intersected.columns:
            raise ValueError(f"Atributo '{attr}' não encontrado na camada de entrada.")

        if attr_type == AttributeType.EXTENSIVE:
            series = _distribute_extensive(intersected, attr)
        elif attr_type == AttributeType.INTENSIVE:
            series = _distribute_intensive(intersected, attr)
        elif attr_type == AttributeType.WEIGHTED:
            raise ValueError(
                f"Atributo ponderado '{attr}' deve ser informado em 'ratios' "
                "como o par (atributo, peso)."
            )
        else:
            raise ValueError(f"Tipo de atributo desconhecido: {attr_type}")

        result[attr] = series
        output_cols.append(attr)

    for attr, weight in ratios or []:
        for col in (attr, weight):
            if col not in intersected.columns:
                raise ValueError(f"Atributo '{col}' não encontrado na camada de entrada.")

        output_col = weighted_column_name(attr, weight)
        if output_col in output_cols:
            raise ValueError(f"Coluna de saída '{output_col}' gerada mais de uma vez.")

        result[output_col] = _distribute_weighted(intersected, attr, weight)
        output_cols.append(output_col)

    result = result.reset_index()

    # Remove hexágonos que não tiveram nenhuma interseção com dados válidos.
    result = result.dropna(subset=output_cols, how="all")
    return result
