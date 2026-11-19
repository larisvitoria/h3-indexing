import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from h3_grid import generate_hex_grid


def _small_area_gdf():
    # Pequeno polígono em torno de um ponto na cidade de Fortaleza, CE.
    poly = Polygon(
        [
            (-38.55, -3.75),
            (-38.50, -3.75),
            (-38.50, -3.70),
            (-38.55, -3.70),
        ]
    )
    return gpd.GeoDataFrame({"geometry": [poly]}, crs="EPSG:4326")


def test_generate_hex_grid_returns_hexagons():
    gdf = _small_area_gdf()
    hex_gdf = generate_hex_grid(gdf, resolution=7)
    assert len(hex_gdf) > 0
    assert set(hex_gdf.columns) == {"h3_index", "geometry"}
    assert hex_gdf.crs.to_string() == "EPSG:4326"


def test_invalid_resolution_raises():
    gdf = _small_area_gdf()
    with pytest.raises(ValueError):
        generate_hex_grid(gdf, resolution=16)


def test_grid_covers_whole_extent():
    # Hexágonos com centroide fora do bounding box, mas que o tocam, também
    # devem entrar, para que a borda da camada não fique descoberta.
    gdf = _small_area_gdf()
    hex_gdf = generate_hex_grid(gdf, resolution=7)
    uncovered = gdf.geometry.iloc[0].difference(hex_gdf.geometry.union_all())
    assert uncovered.area < 1e-12


def test_extent_smaller_than_one_hexagon():
    tiny = gpd.GeoDataFrame(
        {"geometry": [Polygon([(-38.52, -3.72), (-38.519, -3.72), (-38.519, -3.719)])]},
        crs="EPSG:4326",
    )
    hex_gdf = generate_hex_grid(tiny, resolution=5)
    assert len(hex_gdf) >= 1
