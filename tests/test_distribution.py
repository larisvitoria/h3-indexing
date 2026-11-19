import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from distribution import AttributeType, distribute_attributes


def test_extensive_conserves_total_value():
    """Um polígono dividido igualmente em 2 hexágonos deve conservar a soma."""
    intersected = gpd.GeoDataFrame(
        {
            "h3_index": ["hexA", "hexB"],
            "populacao": [1000, 1000],
            "_orig_area": [100.0, 100.0],
            "_intersection_area": [50.0, 50.0],
            "geometry": [Polygon(), Polygon()],
        }
    )
    hex_gdf = gpd.GeoDataFrame(
        {"h3_index": ["hexA", "hexB"], "geometry": [Polygon(), Polygon()]}
    )

    result = distribute_attributes(
        intersected, hex_gdf, {"populacao": AttributeType.EXTENSIVE}
    )

    assert result.set_index("h3_index").loc["hexA", "populacao"] == pytest.approx(500)
    assert result.set_index("h3_index").loc["hexB", "populacao"] == pytest.approx(500)
    assert result["populacao"].sum() == pytest.approx(1000)


def test_intensive_is_area_weighted_average():
    """Renda média deve ser ponderada pela área, não somada."""
    intersected = gpd.GeoDataFrame(
        {
            "h3_index": ["hexA", "hexA"],
            "renda_media": [1000.0, 2000.0],
            "_orig_area": [100.0, 100.0],
            "_intersection_area": [30.0, 70.0],
            "geometry": [Polygon(), Polygon()],
        }
    )
    hex_gdf = gpd.GeoDataFrame({"h3_index": ["hexA"], "geometry": [Polygon()]})

    result = distribute_attributes(
        intersected, hex_gdf, {"renda_media": AttributeType.INTENSIVE}
    )

    expected = (1000.0 * 30.0 + 2000.0 * 70.0) / (30.0 + 70.0)
    assert result.set_index("h3_index").loc["hexA", "renda_media"] == pytest.approx(
        expected
    )


def test_unknown_attribute_raises():
    intersected = gpd.GeoDataFrame(
        {
            "h3_index": ["hexA"],
            "_orig_area": [100.0],
            "_intersection_area": [100.0],
            "geometry": [Polygon()],
        }
    )
    hex_gdf = gpd.GeoDataFrame({"h3_index": ["hexA"], "geometry": [Polygon()]})

    with pytest.raises(ValueError):
        distribute_attributes(
            intersected, hex_gdf, {"inexistente": AttributeType.EXTENSIVE}
        )


def test_weighted_is_ratio_of_extensive_sums():
    """Renda total / população deve ser a razão das somas repartidas no hexágono."""
    intersected = gpd.GeoDataFrame(
        {
            "h3_index": ["hexA", "hexA", "hexB"],
            "renda_total": [10000.0, 50000.0, 50000.0],
            "populacao": [10.0, 100.0, 100.0],
            "_orig_area": [100.0, 200.0, 200.0],
            "_intersection_area": [100.0, 50.0, 150.0],
            "geometry": [Polygon(), Polygon(), Polygon()],
        }
    )
    hex_gdf = gpd.GeoDataFrame(
        {"h3_index": ["hexA", "hexB"], "geometry": [Polygon(), Polygon()]}
    )

    result = distribute_attributes(
        intersected,
        hex_gdf,
        {},
        [("renda_total", "populacao")],
    ).set_index("h3_index")

    expected_a = (10000.0 * 1.0 + 50000.0 * 0.25) / (10.0 * 1.0 + 100.0 * 0.25)
    assert "renda_total" not in result.columns
    assert result.loc["hexA", "renda_total_por_populacao"] == pytest.approx(expected_a)
    assert result.loc["hexB", "renda_total_por_populacao"] == pytest.approx(500.0)


def test_weighted_zero_denominator_is_dropped():
    """Hexágono sem população não deve gerar razão infinita."""
    intersected = gpd.GeoDataFrame(
        {
            "h3_index": ["hexA", "hexB"],
            "renda_total": [1000.0, 0.0],
            "populacao": [10.0, 0.0],
            "_orig_area": [100.0, 100.0],
            "_intersection_area": [100.0, 100.0],
            "geometry": [Polygon(), Polygon()],
        }
    )
    hex_gdf = gpd.GeoDataFrame(
        {"h3_index": ["hexA", "hexB"], "geometry": [Polygon(), Polygon()]}
    )

    result = distribute_attributes(
        intersected,
        hex_gdf,
        {},
        [("renda_total", "populacao")],
    )

    assert list(result["h3_index"]) == ["hexA"]
    assert result["renda_total_por_populacao"].iloc[0] == pytest.approx(100.0)


def test_weighted_can_coexist_with_extensive_on_same_column():
    """renda_total pode ser extensiva e numerador de razões na mesma execução."""
    intersected = gpd.GeoDataFrame(
        {
            "h3_index": ["hexA"],
            "renda_total": [1000.0],
            "populacao": [10.0],
            "domicilios": [4.0],
            "_orig_area": [100.0],
            "_intersection_area": [50.0],
            "geometry": [Polygon()],
        }
    )
    hex_gdf = gpd.GeoDataFrame({"h3_index": ["hexA"], "geometry": [Polygon()]})

    result = distribute_attributes(
        intersected,
        hex_gdf,
        {"renda_total": AttributeType.EXTENSIVE},
        [("renda_total", "populacao"), ("renda_total", "domicilios")],
    ).set_index("h3_index")

    assert result.loc["hexA", "renda_total"] == pytest.approx(500.0)
    assert result.loc["hexA", "renda_total_por_populacao"] == pytest.approx(100.0)
    assert result.loc["hexA", "renda_total_por_domicilios"] == pytest.approx(250.0)


def test_weighted_missing_weight_column_raises():
    intersected = gpd.GeoDataFrame(
        {
            "h3_index": ["hexA"],
            "renda_total": [1000.0],
            "_orig_area": [100.0],
            "_intersection_area": [100.0],
            "geometry": [Polygon()],
        }
    )
    hex_gdf = gpd.GeoDataFrame({"h3_index": ["hexA"], "geometry": [Polygon()]})

    with pytest.raises(ValueError):
        distribute_attributes(
            intersected, hex_gdf, {}, [("renda_total", "inexistente")]
        )
