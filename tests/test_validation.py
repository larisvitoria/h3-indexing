import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from validation import (
    GEOGRAPHIC_CRS,
    validate_and_fix_geometry,
    validate_and_reproject_crs,
    validate_layer,
)


def _square(x0=0, y0=0, size=1):
    return Polygon([(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)])


def test_fix_invalid_geometry_with_buffer():
    # Polígono em "gravata" (self-intersecting) é inválido.
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    gdf = gpd.GeoDataFrame({"geometry": [bowtie]}, crs=GEOGRAPHIC_CRS)
    fixed = validate_and_fix_geometry(gdf)
    assert fixed.geometry.is_valid.all()


def test_reproject_to_geographic_crs():
    gdf = gpd.GeoDataFrame({"geometry": [_square()]}, crs="EPSG:3857")
    reprojected = validate_and_reproject_crs(gdf)
    assert reprojected.crs.to_string() == GEOGRAPHIC_CRS


def test_missing_crs_raises():
    gdf = gpd.GeoDataFrame({"geometry": [_square()]})
    with pytest.raises(ValueError):
        validate_and_reproject_crs(gdf)


def test_validate_layer_pipeline():
    gdf = gpd.GeoDataFrame({"geometry": [_square()]}, crs="EPSG:3857")
    result = validate_layer(gdf)
    assert result.crs.to_string() == GEOGRAPHIC_CRS
    assert result.geometry.is_valid.all()
