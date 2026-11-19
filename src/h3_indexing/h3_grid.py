"""
h3_grid.py - geração da grade hexagonal H3 cobrindo a extensão da camada de entrada.

Usa a API do h3-py v4 (h3.h3shape_to_cells_experimental / h3.cell_to_boundary).
"""

import geopandas as gpd
import h3
from shapely.geometry import Polygon, box


def _polygon_to_h3shape(polygon: Polygon) -> "h3.LatLngPoly":
    """
    Converte um shapely Polygon (lon, lat) para h3.LatLngPoly (lat, lon).
    
    Args:
        polygon (Polygon): Polígono shapely a ser convertido.
        
    Returns:
        h3.LatLngPoly: Polígono no formato esperado pelo h3-py.
    """
    exterior = [(lat, lon) for lon, lat in polygon.exterior.coords]
    holes = [
        [(lat, lon) for lon, lat in interior.coords]
        for interior in polygon.interiors
    ]
    return h3.LatLngPoly(exterior, *holes)


def _cell_to_polygon(cell: str) -> Polygon:
    """
    Converte um índice H3 em um shapely Polygon (lon, lat).
    
    Args:
        cell (str): Índice H3 a ser convertido.
    
    Returns:
        Polygon: Polígono shapely correspondente ao hexágono H3.
    """
    boundary = h3.cell_to_boundary(cell)  # lista de (lat, lon)
    coords = [(lon, lat) for lat, lon in boundary]
    return Polygon(coords)


def generate_hex_grid(gdf: gpd.GeoDataFrame, resolution: int) -> gpd.GeoDataFrame:
    """
    Gera hexágonos H3 cobrindo a extensão (bounding box) da camada de entrada.

    Usa o bounding box (e não as geometrias individuais) para garantir
    cobertura total, evitando buracos na grade final em regiões com
    polígonos não contíguos.

    Inclui todo hexágono que toca o bounding box (modo "overlap"), e não
    apenas os de centroide interno: assim nenhuma parte de polígono na borda
    da extensão fica descoberta e os atributos extensivos são conservados.

    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame já validado, em EPSG:4326.
        resolution (int): resolução H3, de 0 a 15.
    
    Returns:
        gpd.GeoDataFrame: GeoDataFrame contendo os hexágonos H3 gerados
        com as colunas:
          - "h3_index": índice H3 do hexágono
          - "geometry": polígono shapely do hexágono (EPSG:4326)
    """
    if not (0 <= resolution <= 15):
        raise ValueError("A resolução H3 deve estar entre 0 e 15.")

    minx, miny, maxx, maxy = gdf.total_bounds
    bbox_polygon = box(minx, miny, maxx, maxy)

    h3shape = _polygon_to_h3shape(bbox_polygon)
    cells = h3.h3shape_to_cells_experimental(h3shape, resolution, contain="overlap")

    if not cells:
        raise ValueError(
            "Nenhum hexágono foi gerado para a extensão informada. "
            "Verifique a resolução escolhida (tente um valor menor)."
        )

    records = [
        {"h3_index": cell, "geometry": _cell_to_polygon(cell)} for cell in cells
    ]
    hex_gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    return hex_gdf
