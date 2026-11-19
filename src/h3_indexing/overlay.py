"""
overlay.py - sobreposição espacial entre a camada original e a grade hexagonal.
"""

import geopandas as gpd

# CRS de área equivalente (cilíndrica, global), usado apenas para cálculo de áreas em m²
EQUAL_AREA_CRS = "EPSG:6933"


def compute_intersection(
    original_gdf: gpd.GeoDataFrame,
    hex_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """
    Intersecta a camada original com a grade hexagonal e calcula áreas.

    Args:
        original_gdf (gpd.GeoDataFrame): Camada de entrada (polígonos).
        hex_gdf (gpd.GeoDataFrame): Grade hexagonal H3.

    Returns:
        gpd.GeoDataFrame: GeoDataFrame com uma linha por par
        (polígono original x hexágono) que se sobrepõem, contendo:
          - "_intersection_area": área da interseção (m²)
          - "_orig_area": área total do polígono original (m²)
    """
    original_gdf = original_gdf.copy()
    original_gdf["_orig_id"] = range(len(original_gdf))
    original_gdf["_orig_area"] = original_gdf.to_crs(EQUAL_AREA_CRS).geometry.area

    intersected = gpd.overlay(original_gdf, hex_gdf, how="intersection")

    if intersected.empty:
        raise ValueError(
            "A interseção entre a camada de entrada e a grade H3 está vazia. "
            "Verifique se as camadas se sobrepõem geograficamente."
        )

    intersected["_intersection_area"] = intersected.to_crs(EQUAL_AREA_CRS).geometry.area
    return intersected