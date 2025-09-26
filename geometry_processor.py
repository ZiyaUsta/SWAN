import numpy as np
from shapely.geometry import Polygon
from shapely import contains_xy
from tqdm import tqdm

class GeometryProcessor:
    "Geometric operations and processing of building surfaces."
    
    @staticmethod
    def get_plane_equation(points):
        "Calculates the plane equation from a list of 3D points."
        if len(points) < 3:
            raise ValueError("At least 3 points are required for the plane equation.")
        p1, p2, p3 = points[:3]
        v1 = np.array(p2) - np.array(p1)
        v2 = np.array(p3) - np.array(p1)
        normal = np.cross(v1, v2)
        if np.linalg.norm(normal) < 1e-6:
            raise ValueError("The points are not coplanar or are collinear.")
        normal = normal / np.linalg.norm(normal)
        a, b, c = normal
        d = np.dot(normal, p1)
        return a, b, c, d
    
    @staticmethod
    def project_points_to_2d(points, normal):
        "Projects 3D points onto the plane and converts them into 2D coordinates."
        normal = np.array(normal) / np.linalg.norm(normal)
        points = np.array(points)
        p0 = points[0]
        
        if np.allclose(normal, [0, 0, 1], atol=1e-6) or np.allclose(normal, [0, 0, -1], atol=1e-6):
            points_2d = points[:, :2] - p0[:2]
            u = np.array([1, 0, 0])
            v = np.array([0, 1, 0])
        else:
            if abs(normal[2]) > 1e-6:
                u = np.cross(normal, [0, 0, 1])
            else:
                u = np.cross(normal, [0, 1, 0])
            if np.linalg.norm(u) < 1e-6:
                u = np.cross(normal, [1, 0, 0])
            u = u / np.linalg.norm(u)
            v = np.cross(normal, u)
            v = v / np.linalg.norm(v)
            points_centered = points - p0
            points_2d = np.column_stack([np.dot(points_centered, u), np.dot(points_centered, v)])
        
        if np.any(np.isnan(points_2d)):
            return np.array([]), u, v
        
        return points_2d, u, v
    
    @staticmethod
    def get_3d_surface_points(polygon_2d, u, v, normal, p0, spacing=4.0, sun_directions=None):
        "Creates a grid on the 2D polygon and converts it back to 3D."
        poly = Polygon(polygon_2d)
        minx, miny, maxx, maxy = poly.bounds
        
        area = poly.area
        if area > 1e8:
            return []
        
        if (maxx - minx < spacing) or (maxy - miny < spacing):
            return []
        
        x = np.arange(np.floor(minx), np.ceil(maxx), spacing)
        y = np.arange(np.floor(miny), np.ceil(maxy), spacing)
        xx, yy = np.meshgrid(x, y)
        points_2d = np.column_stack([xx.ravel(), yy.ravel()])
        
        inside_mask = contains_xy(poly, points_2d[:, 0], points_2d[:, 1])
        points_2d_inside = points_2d[inside_mask]
        
        filtered_sun_directions = {}
        for day, daily_directions in sun_directions.items():
            filtered_sun_directions[day] = {
                int(hour): direction if direction is not None else None
                for hour, direction in daily_directions.items()
            }
        
        points_3d = []
        points_3d_coords = p0 + points_2d_inside[:, 0][:, None] * u + points_2d_inside[:, 1][:, None] * v
        for coord in points_3d_coords:
            point_data = {
                "coordinates": coord.tolist(),
                "normal": normal.tolist(),
                "sun_directions": filtered_sun_directions,
                "shadow": 0.0
            }
            points_3d.append(point_data)
        
        return points_3d
    
    @staticmethod
    def process_all_buildings_surfaces(cm, sun_directions, spacing=4.0):
        "Processes all surfaces and points of all buildings."
        buildings = [id for id, co in cm.get('CityObjects', {}).items() if co.get('type') == 'Building']
        if not buildings:
            raise ValueError("No buildings found in the file.")
        
        all_surfaces_dict = {}
        all_points_info = {}
        
        for bina_id in tqdm(buildings, desc="Processing buildings"):
            co = cm['CityObjects'][bina_id]
            surfaces_dict = {}
            points_info = {}
            
            for geom_idx, geom in enumerate(co.get('geometry', [])):
                semantics = geom.get('semantics', {})
                surfaces = semantics.get('surfaces', [])
                values = semantics.get('values', [])
                
                boundaries = geom.get('boundaries', [])
                for srf_idx, boundary in enumerate(boundaries):
                    surface_type = 'unknown'
                    if values and srf_idx < len(values) and values[srf_idx] is not None:
                        srf = surfaces[values[srf_idx]]
                        surface_type = srf.get('type', 'unknown')
                    
                    if not boundary or surface_type == "GroundSurface":
                        continue
                    
                    outer_ring_idx = boundary[0]
                    outer_ring_3d = [cm['vertices'][idx] for idx in outer_ring_idx]
                    surface_key = f"{bina_id}_geom_{geom_idx}_surface_{srf_idx}"
                    surfaces_dict[surface_key] = outer_ring_3d
                    
                    try:
                        a, b, c, d = GeometryProcessor.get_plane_equation(outer_ring_3d)
                        normal = np.array([a, b, c])
                        outer_ring_2d, u, v = GeometryProcessor.project_points_to_2d(outer_ring_3d, normal)
                        if not outer_ring_2d.size:
                            continue
                        
                        holes_2d = []
                        for ring in boundary[1:]:
                            ring_3d = [cm['vertices'][idx] for idx in ring]
                            holes_2d.append(GeometryProcessor.project_points_to_2d(ring_3d, normal)[0])
                        holes_2d = [h for h in holes_2d if h]
                        
                        points_3d = GeometryProcessor.get_3d_surface_points(outer_ring_2d, u, v, normal, outer_ring_3d[0], spacing, sun_directions)
                        points_info[surface_key] = {
                            "bina_id": bina_id,
                            "surface_type": surface_type,
                            "points": points_3d
                        }
                    except Exception:
                        pass
            
            if surfaces_dict and points_info:
                all_surfaces_dict[bina_id] = surfaces_dict
                all_points_info[bina_id] = points_info
        
        return all_surfaces_dict, all_points_info