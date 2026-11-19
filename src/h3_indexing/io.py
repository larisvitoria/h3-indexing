"""
io.py - leitura e escrita de camadas vetoriais (shapefile, geopackage, geojson).
"""

from pathlib import Path
import geopandas as gpd


def read_vector_file(path: str) -> gpd.GeoDataFrame:
    """
    Carrega um shapefile/geopackage/geojson via geopandas.read_file().
    
    Args:
        path (str): Caminho do arquivo de entrada.
        
    Returns:
        gpd.GeoDataFrame: Camada vetorial carregada.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {file_path}")

    gdf = gpd.read_file(file_path)
    if gdf.empty:
        raise ValueError(f"O arquivo de entrada não contém feições: {file_path}")

    return gdf


def write_vector_file(gdf: gpd.GeoDataFrame, path: str) -> None:
    """
    Exporta um GeoDataFrame para Shapefile, GeoPackage ou GeoJSON.
    
    A extensão do arquivo de saída determina o formato:
        - .shp: Shapefile
        - .gpkg: GeoPackage
        - .geojson ou .json: GeoJSON
        
    Args:
        gdf (gpd.GeoDataFrame): Camada vetorial a ser exportada.
        path (str): Caminho do arquivo de saída.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    driver_map = {
        ".shp": "ESRI Shapefile",
        ".gpkg": "GPKG",
        ".geojson": "GeoJSON",
        ".json": "GeoJSON",
    }
    driver = driver_map.get(file_path.suffix.lower())
    if driver is None:
        raise ValueError(
            f"Formato de saída não suportado: '{file_path.suffix}'. "
            "Use .shp, .gpkg ou .geojson."
        )

    gdf.to_file(file_path, driver=driver)
