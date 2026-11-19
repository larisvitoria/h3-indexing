# -*- coding: utf-8 -*-
import os
from collections import defaultdict

import h3
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsSpatialIndex,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

# ============================== PARÂMETROS ============================== #
INPUT_PATH = "/home/larissa/Downloads/censos_2010-2022/CE_2022.gpkg"
OUTPUT_PATH = "/home/larissa/Downloads/censos_2010-2022/CE_2022_h3_4.gpkg"
RESOLUTION = 4
EXTENSIVE_FIELDS = ["Total de Domicílios"]
INTENSIVE_FIELDS = ["Rendimento médio (responsáveis com renda positiva)"]
# ========================================================================= #

CRS_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
CRS_EQUAL_AREA = QgsCoordinateReferenceSystem("EPSG:6933")


def build_h3_grid(extent_wgs84, resolution):
    """Gera hexágonos H3 cobrindo o retângulo (extent) da camada de entrada."""
    exterior_latlng = [
        (extent_wgs84.yMinimum(), extent_wgs84.xMinimum()),
        (extent_wgs84.yMinimum(), extent_wgs84.xMaximum()),
        (extent_wgs84.yMaximum(), extent_wgs84.xMaximum()),
        (extent_wgs84.yMaximum(), extent_wgs84.xMinimum()),
    ]
    
    # Compatibilidade com H3 v4 e v3
    if hasattr(h3, 'Polygon'):
        # H3 versão 4.x
        poly = h3.Polygon(exterior_latlng)
        cells = h3.polygon_to_cells(poly, resolution)
    else:
        # H3 versão 3.x
        geo_json = {
            'type': 'Polygon',
            'coordinates': [[[lng, lat] for lat, lng in exterior_latlng] + [[exterior_latlng[0][1], exterior_latlng[0][0]]]]
        }
        cells = h3.polyfill(geo_json, resolution, geo_json_conformant=True)

    grid = {}
    for cell in cells:
        # Compatibilidade com H3 v4 e v3
        if hasattr(h3, 'cell_to_boundary'):
            boundary = h3.cell_to_boundary(cell)
        else:
            boundary = h3.h3_to_geo_boundary(cell)
            
        points = [QgsPointXY(lon, lat) for lat, lon in boundary]
        grid[cell] = QgsGeometry.fromPolygonXY([points])
        
    return grid


def run():
    print("[1/6] Lendo camada de entrada...")
    layer = QgsVectorLayer(INPUT_PATH, "entrada", "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Não foi possível abrir a camada: {INPUT_PATH}")

    field_names = [f.name() for f in layer.fields()]
    for fname in EXTENSIVE_FIELDS + INTENSIVE_FIELDS:
        if fname not in field_names:
            raise RuntimeError(f"Atributo '{fname}' não encontrado.")
            
    field_index = {name: field_names.index(name) for name in field_names}

    # Correção: Passar o transformContext do projeto
    context = QgsProject.instance().transformContext()
    to_wgs84 = QgsCoordinateTransform(layer.crs(), CRS_4326, context)
    to_equal_area = QgsCoordinateTransform(layer.crs(), CRS_EQUAL_AREA, context)

    print("[2/6] Validando geometria e reprojetando para EPSG:4326...")
    features = []
    extent_wgs84 = None
    for feat in layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            continue
        if not geom.isGeosValid():
            geom = geom.makeValid()
            if geom is None or geom.isEmpty():
                continue

        geom_wgs84 = QgsGeometry(geom)
        geom_wgs84.transform(to_wgs84)

        geom_ea = QgsGeometry(geom)
        geom_ea.transform(to_equal_area)
        orig_area = geom_ea.area()
        
        if orig_area <= 0:
            continue

        features.append({"attrs": feat.attributes(), "geom": geom_wgs84, "orig_area": orig_area})
        bbox = geom_wgs84.boundingBox()
        extent_wgs84 = bbox if extent_wgs84 is None else extent_wgs84.combineExtentWith(bbox)

    if not features:
        raise RuntimeError("Nenhuma geometria válida encontrada.")

    print(f"[3/6] Gerando grade hexagonal H3 (resolução {RESOLUTION})...")
    hex_grid = build_h3_grid(extent_wgs84, RESOLUTION)
    print(f"        {len(hex_grid)} hexágonos gerados.")

    hex_ids = list(hex_grid.keys())
    hex_index = QgsSpatialIndex()
    hex_feature_by_id = {}
    
    for i, hid in enumerate(hex_ids):
        hf = QgsFeature(i)
        hf.setGeometry(hex_grid[hid])
        hex_index.addFeature(hf)
        hex_feature_by_id[i] = hid

    print("[4/6] Executando sobreposição espacial (overlay)...")
    extensive_sums = defaultdict(lambda: defaultdict(float))
    intensive_num = defaultdict(lambda: defaultdict(float))
    intensive_den = defaultdict(lambda: defaultdict(float))

    for feat_data in features:
        geom = feat_data["geom"]
        orig_area = feat_data["orig_area"]
        attrs = feat_data["attrs"]

        for int_id in hex_index.intersects(geom.boundingBox()):
            hid = hex_feature_by_id[int_id]
            hex_geom = hex_grid[hid]
            if not geom.intersects(hex_geom):
                continue
                
            inter_geom = geom.intersection(hex_geom)
            if inter_geom is None or inter_geom.isEmpty():
                continue

            inter_geom_ea = QgsGeometry(inter_geom)
            inter_geom_ea.transform(to_equal_area)
            inter_area = inter_geom_ea.area()
            
            if inter_area <= 0:
                continue

            for fname in EXTENSIVE_FIELDS:
                value = attrs[field_index[fname]]
                if value is not None:
                    extensive_sums[hid][fname] += float(value) * (inter_area / orig_area)

            for fname in INTENSIVE_FIELDS:
                value = attrs[field_index[fname]]
                if value is not None:
                    intensive_num[hid][fname] += float(value) * inter_area
                    intensive_den[hid][fname] += inter_area

    print("[5/6] Montar camada de saída...")
    result_hex_ids = sorted(set(extensive_sums.keys()) | set(intensive_num.keys()))
    if not result_hex_ids:
        raise RuntimeError("Interseção vazia.")

    out_fields = QgsFields()
    out_fields.append(QgsField("h3_index", QVariant.String))
    for fname in EXTENSIVE_FIELDS + INTENSIVE_FIELDS:
        out_fields.append(QgsField(fname, QVariant.Double))

    out_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "grade_h3", "memory")
    out_layer.dataProvider().addAttributes(out_fields)
    out_layer.updateFields()

    out_feats = []
    for hid in result_hex_ids:
        f = QgsFeature(out_fields)
        f.setGeometry(hex_grid[hid])
        row = [str(hid)]
        for fname in EXTENSIVE_FIELDS:
            row.append(extensive_sums[hid].get(fname))
        for fname in INTENSIVE_FIELDS:
            num = intensive_num[hid].get(fname)
            den = intensive_den[hid].get(fname)
            row.append((num / den) if (num is not None and den) else None)
        f.setAttributes(row)
        out_feats.append(f)

    out_layer.dataProvider().addFeatures(out_feats)
    out_layer.updateExtents()

    print(f"[6/6] Exportando resultado: {OUTPUT_PATH}")
    
    # Correção: API Moderna do QGIS 3 para salvar vetores
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.fileEncoding = "UTF-8"
    
    error, msg = QgsVectorFileWriter.writeAsVectorFormatV3(
        out_layer, 
        OUTPUT_PATH, 
        QgsProject.instance().transformContext(), 
        options
    )
    
    if error == QgsVectorFileWriter.NoError:
        QgsProject.instance().addMapLayer(out_layer)
        print(f"Concluído: {len(result_hex_ids)} hexágonos com atributos calculados.")
    else:
        print(f"Erro ao salvar arquivo: {msg}")

run()