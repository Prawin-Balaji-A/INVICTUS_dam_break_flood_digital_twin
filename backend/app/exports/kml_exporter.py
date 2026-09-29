import json
from pathlib import Path
from typing import Dict, Any, List

class KMLExporter:
    """
    Exports geospatial GeoJSON layers to OGC standard Keyhole Markup Language (.kml)
    for Google Earth, QGIS, ArcGIS, and emergency response operations.
    """

    @classmethod
    def geojson_to_kml(cls, geojson_path: str, output_kml_path: str, layer_name: str = "Flood Inundation Layer") -> str:
        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        
        # Determine theme color based on layer_name
        is_buildings = "building" in layer_name.lower()
        is_roads = "road" in layer_name.lower()
        
        if is_buildings:
            poly_color = "7f00a5ff"  # Semi-transparent amber/orange in aabbggrr
            line_color = "ff0055ff"
            style_id = "buildingStyle"
        elif is_roads:
            poly_color = "7f0000ff"
            line_color = "ff0000e6"  # Solid red
            style_id = "roadStyle"
        else:
            poly_color = "80f07814"  # Semi-transparent ocean blue (alpha=80, b=f0, g=78, r=14)
            line_color = "fff0a020"  # Bright cyan boundary
            style_id = "floodStyle"

        kml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<kml xmlns="http://www.opengis.net/kml/2.2">',
            '  <Document>',
            f'    <name>{layer_name}</name>',
            f'    <description>Dam Break &amp; Flash Flood Inundation Modelling Deliverable — OGC KML 2.2 Export</description>',
            f'    <Style id="{style_id}">',
            '      <LineStyle>',
            f'        <color>{line_color}</color>',
            '        <width>2.5</width>',
            '      </LineStyle>',
            '      <PolyStyle>',
            f'        <color>{poly_color}</color>',
            '        <fill>1</fill>',
            '        <outline>1</outline>',
            '      </PolyStyle>',
            '    </Style>'
        ]

        def coords_to_kml_str(coords: List) -> str:
            # coords is list of [lon, lat] or [lon, lat, alt]
            return " ".join(f"{c[0]},{c[1]},{c[2] if len(c) > 2 else 0}" for c in coords)

        for idx, feat in enumerate(features):
            geom = feat.get("geometry", {})
            props = feat.get("properties", {}) or {}
            geom_type = geom.get("type", "")
            geom_coords = geom.get("coordinates", [])

            name_val = props.get("name") or props.get("id") or f"Feature_{idx + 1}"
            
            # Format extended data table
            ext_data_items = []
            for k, v in props.items():
                if v is not None and k not in ["geometry", "coordinates"]:
                    ext_data_items.append(f'        <Data name="{k}"><value>{v}</value></Data>')
            ext_data_block = "\n".join(ext_data_items)

            kml_parts.append('    <Placemark>')
            kml_parts.append(f'      <name>{name_val}</name>')
            kml_parts.append(f'      <styleUrl>#{style_id}</styleUrl>')
            if ext_data_block:
                kml_parts.append('      <ExtendedData>')
                kml_parts.append(ext_data_block)
                kml_parts.append('      </ExtendedData>')

            if geom_type == "Polygon":
                kml_parts.append('      <Polygon>')
                kml_parts.append('        <extrude>1</extrude>')
                kml_parts.append('        <altitudeMode>clampToGround</altitudeMode>')
                if geom_coords:
                    outer_ring = geom_coords[0]
                    kml_parts.append('        <outerBoundaryIs>')
                    kml_parts.append('          <LinearRing>')
                    kml_parts.append(f'            <coordinates>{coords_to_kml_str(outer_ring)}</coordinates>')
                    kml_parts.append('          </LinearRing>')
                    kml_parts.append('        </outerBoundaryIs>')
                kml_parts.append('      </Polygon>')

            elif geom_type == "MultiPolygon":
                kml_parts.append('      <MultiGeometry>')
                for poly_rings in geom_coords:
                    if poly_rings:
                        outer_ring = poly_rings[0]
                        kml_parts.append('        <Polygon>')
                        kml_parts.append('          <outerBoundaryIs>')
                        kml_parts.append('            <LinearRing>')
                        kml_parts.append(f'              <coordinates>{coords_to_kml_str(outer_ring)}</coordinates>')
                        kml_parts.append('            </LinearRing>')
                        kml_parts.append('          </outerBoundaryIs>')
                        kml_parts.append('        </Polygon>')
                kml_parts.append('      </MultiGeometry>')

            elif geom_type == "LineString":
                kml_parts.append('      <LineString>')
                kml_parts.append('        <tessellate>1</tessellate>')
                kml_parts.append(f'        <coordinates>{coords_to_kml_str(geom_coords)}</coordinates>')
                kml_parts.append('      </LineString>')

            elif geom_type == "MultiLineString":
                kml_parts.append('      <MultiGeometry>')
                for line in geom_coords:
                    kml_parts.append('        <LineString>')
                    kml_parts.append('          <tessellate>1</tessellate>')
                    kml_parts.append(f'          <coordinates>{coords_to_kml_str(line)}</coordinates>')
                    kml_parts.append('        </LineString>')
                kml_parts.append('      </MultiGeometry>')

            elif geom_type == "Point":
                kml_parts.append('      <Point>')
                kml_parts.append(f'        <coordinates>{geom_coords[0]},{geom_coords[1]},0</coordinates>')
                kml_parts.append('      </Point>')

            kml_parts.append('    </Placemark>')

        kml_parts.append('  </Document>')
        kml_parts.append('</kml>')

        out_path = Path(output_kml_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(out_path), "w", encoding="utf-8") as f:
            f.write("\n".join(kml_parts))

        return str(out_path)
