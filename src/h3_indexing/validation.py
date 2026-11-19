"""
validation.py - validação de geometria e CRS.

O H3 opera sobre coordenadas geográficas (latitude/longitude), portanto toda
camada precisa estar em um CRS geográfico compatível (EPSG:4326) antes da
geração da grade hexagonal.
"""

import geopandas as gpd

GEOGRAPHIC_CRS = "EPSG:4326"


def validate_and_fix_geometry(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Remove geometrias nulas e corrige geometrias inválidas com buffer(0).
    
    Args:
        gdf (gpd.GeoDataFrame): Camada de entrada.
        
    Returns:
        gpd.GeoDataFrame: Camada com geometrias válidas.
    """
    gdf = gdf.copy()
    gdf = gdf[gdf.geometry.notna()]
    if gdf.empty:
        raise ValueError("Nenhuma geometria válida encontrada após remoção de nulos.")

    invalid_mask = ~gdf.geometry.is_valid
    n_invalid = int(invalid_mask.sum())
    if n_invalid > 0:
        print(
            f"[validation] {n_invalid} geometria(s) inválida(s) encontrada(s); "
            "aplicando buffer(0) para correção."
        )
        gdf.loc[invalid_mask, "geometry"] = gdf.loc[invalid_mask, "geometry"].buffer(0)

    still_invalid = ~gdf.geometry.is_valid
    if still_invalid.any():
        raise ValueError(
            f"{int(still_invalid.sum())} geometria(s) permanecem inválidas "
            "mesmo após a correção automática."
        )

    return gdf


def validate_and_reproject_crs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Garante que a camada esteja em um CRS geográfico compatível com H3.
    
    Args:
        gdf (gpd.GeoDataFrame): Camada de entrada.
        
    Returns:
        gpd.GeoDataFrame: Camada re-projetada para EPSG:4326.
    """
    if gdf.crs is None:
        raise ValueError(
            "A camada de entrada não possui CRS definido. "
            "Defina um CRS antes de continuar."
        )

    if gdf.crs.to_string() != GEOGRAPHIC_CRS:
        print(
            f"[validation] Reprojetando de {gdf.crs} para {GEOGRAPHIC_CRS} "
            "(compatível com H3)."
        )
        gdf = gdf.to_crs(GEOGRAPHIC_CRS)

    return gdf


def validate_layer(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Pipeline completo de validação: geometria + CRS.
    
    Args:
        gdf (gpd.GeoDataFrame): Camada de entrada.
        
    Returns:
        gpd.GeoDataFrame: Camada validada e re-projetada.
    """
    gdf = validate_and_fix_geometry(gdf)
    gdf = validate_and_reproject_crs(gdf)
    return gdf
