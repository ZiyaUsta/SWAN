import json
import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json
from shapely.geometry import Point
from datetime import datetime
import logging
import re

# Minimal logging
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class PostGISExporter:
    def __init__(self, db_params):
        self.db_params = db_params
        self.conn = None
        self.cursor = None
        try:
            self.conn = psycopg2.connect(**db_params)
            self.cursor = self.conn.cursor()
            self.cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            self.conn.commit()
        except Exception as e:
            logger.error(f"DB bağlantı hatası: {e}")
            raise

    def extract_srid(self, source_crs):
        if not source_crs or not isinstance(source_crs, str):
            raise ValueError(f"Geçersiz source_crs: {source_crs}")

        patterns = [
            r'^EPSG:(\d+)$',
            r'^https?://www\.opengis\.net/def/crs/EPSG/\d+/(\d+)$',
            r'^\d+$'
        ]

        for pattern in patterns:
            match = re.match(pattern, source_crs)
            if match:
                return int(match.group(1) if pattern != r'^\d+$' else match.group(0))

        raise ValueError(f"Geçersiz source_crs formatı: {source_crs}")

    def create_valid_wkt(self, geom, vertices, geom_type="MULTIPOLYGON Z"):
        if not geom or not vertices:
            return None

        try:
            boundaries = geom.get('boundaries', [])
            if not boundaries or not isinstance(boundaries, list):
                return None

            surfaces = []
            for surface in boundaries:
                if isinstance(surface, list) and surface:
                    vertex_indices = surface[0]
                    if len(vertex_indices) < 3:
                        continue
                    coordinates = [vertices[i] for i in vertex_indices if i < len(vertices)]
                    if len(coordinates) < 3:
                        continue
                    if coordinates[0] != coordinates[-1]:
                        coordinates.append(coordinates[0])
                    wkt_coords = ','.join([f"{x} {y} {z}" for x, y, z in coordinates])
                    surfaces.append(f"(({wkt_coords}))")

            if not surfaces:
                return None

            return f"MULTIPOLYGON Z({','.join(surfaces)})"
        except Exception:
            return None

    def check_table_schema(self, table_name, expected_geometry_type="MULTIPOLYGONZ", srid=None):
        try:
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = %s
                );
            """, (table_name.split('.')[-1],))
            exists = self.cursor.fetchone()[0]

            if exists and srid:
                self.cursor.execute("""
                    SELECT type, srid
                    FROM geometry_columns
                    WHERE f_table_schema = 'public' AND f_table_name = %s;
                """, (table_name.split('.')[-1],))
                result = self.cursor.fetchone()
                if result:
                    current_type, current_srid = result
                    if current_type.upper() != expected_geometry_type or current_srid != srid:
                        return False
                else:
                    return False
            return exists
        except Exception as e:
            logger.error(f"Tablo şeması kontrol hatası: {e}")
            raise

    def create_cityobjects_table(self, srid):
        try:
            query = sql.SQL("""
                CREATE TABLE IF NOT EXISTS cityobjects (
                    id VARCHAR PRIMARY KEY,
                    type VARCHAR,
                    geometry GEOMETRY(MULTIPOLYGONZ, {srid}),
                    attributes JSONB,
                    metadata JSONB
                );
            """).format(srid=sql.Literal(srid))
            self.cursor.execute(query)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"cityobjects tablosu oluşturma hatası: {e}")
            raise

    def create_surface_points_table(self, srid):
        try:
            query = sql.SQL("""
                CREATE TABLE IF NOT EXISTS surface_points (
                    id SERIAL PRIMARY KEY,
                    bina_id VARCHAR(255),
                    surface VARCHAR(255),
                    point GEOMETRY(POINTZ, {srid}),
                    shadow FLOAT,
                    surface_type VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """).format(srid=sql.Literal(srid))
            self.cursor.execute(query)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"surface_points tablosu oluşturma hatası: {e}")
            raise

    def export_cityobjects(self, cm, source_crs):
        try:
            srid = self.extract_srid(source_crs)
            if not self.check_table_schema("cityobjects", "MULTIPOLYGONZ", srid):
                self.create_cityobjects_table(srid)

            city_objects = cm.get('CityObjects', {})
            vertices = cm.get('vertices', [])
            success_count = 0

            for obj_id, obj in city_objects.items():
                geometry = None
                if obj.get('geometry'):
                    geom = obj['geometry'][0]
                    if geom.get('type') in ["MultiSurface", "CompositeSurface"]:
                        geometry = self.create_valid_wkt(geom, vertices)
                    if not geometry:
                        continue
                else:
                    continue

                attributes = obj.get('attributes', {})
                obj_metadata = obj.get('metadata', {})

                try:
                    self.cursor.execute("""
                        INSERT INTO cityobjects (id, type, geometry, attributes, metadata)
                        VALUES (%s, %s, ST_GeomFromText(%s, %s), %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            type = EXCLUDED.type,
                            geometry = EXCLUDED.geometry,
                            attributes = EXCLUDED.attributes,
                            metadata = EXCLUDED.metadata;
                    """, (obj_id, obj.get('type'), geometry, srid, Json(attributes), Json(obj_metadata)))
                    self.conn.commit()
                    success_count += 1
                except psycopg2.Error:
                    self.conn.rollback()

            return success_count
        except Exception as e:
            self.conn.rollback()
            logger.error(f"CityObjects aktarma hatası: {e}")
            raise

    def export_surface_points(self, points_file, source_crs):
        try:
            srid = self.extract_srid(source_crs)
            self.create_surface_points_table(srid)
            with open(points_file, 'r') as f:
                points_data = json.load(f)

            if not points_data:
                return

            inserted_count = 0
            for point_entry in points_data:
                coords = point_entry.get("point")
                if not coords or len(coords) != 3:
                    continue

                surface_type = point_entry.get("surface_type") or "Unknown"
                geom_wkt = Point(coords).wkt

                self.cursor.execute(sql.SQL("""
                    INSERT INTO surface_points (bina_id, surface, point, shadow, surface_type, created_at)
                    VALUES (%s, %s, ST_SetSRID(ST_GeomFromText(%s), {}), %s, %s, %s);
                """).format(sql.Literal(srid)), (
                    point_entry.get("bina_id"), point_entry.get("surface"), geom_wkt,
                    point_entry.get("shadow"), surface_type, datetime.now()
                ))
                inserted_count += 1

            self.conn.commit()
            return inserted_count
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Yüzey noktaları aktarma hatası: {e}")
            raise

    def close_connection(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def __del__(self):
        self.close_connection()
