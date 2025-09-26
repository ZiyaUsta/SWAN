import numpy as np
import open3d as o3d
from tqdm import tqdm

class ShadowAnalyzer:
    """Ray-tracing ile gölge analizi ve günlük ortalama gölge hesaplama."""
    
    @staticmethod
    def create_open3d_scene(cm):
        """CityJSON'dan Open3D RaycastingScene oluşturur, her bina için ayrı geometri ID ile."""
        scene = o3d.t.geometry.RaycastingScene()
        vertices = np.array(cm['vertices'], dtype=np.float32)
        bina_to_geom_id = {}
        
        for bina_id, co in tqdm(cm.get('CityObjects', {}).items(), desc="Sahne oluşturuluyor"):
            if co.get('type') == 'Building':
                all_vertices = []
                all_faces = []
                vertex_offset = 0
                for geom_idx, geom in enumerate(co.get('geometry', [])):
                    boundaries = geom.get('boundaries', [])
                    for boundary in boundaries:
                        for ring in boundary:
                            ring_3d = vertices[ring]
                            for i in range(1, len(ring_3d) - 1):
                                all_vertices.append(ring_3d[[0, i, i+1]])
                                all_faces.append([vertex_offset, vertex_offset + 1, vertex_offset + 2])
                                vertex_offset += 3
                if all_faces:
                    vertices_np = np.concatenate(all_vertices, axis=0).astype(np.float32)
                    faces_np = np.array(all_faces, dtype=np.uint32)
                    mesh = o3d.t.geometry.TriangleMesh(
                        vertex_positions=o3d.core.Tensor(vertices_np),
                        triangle_indices=o3d.core.Tensor(faces_np)
                    )
                    geom_id = scene.add_triangles(mesh)
                    bina_to_geom_id[bina_id] = geom_id
        
        return scene, bina_to_geom_id
    
    @staticmethod
    def ray_intersects_other_surfaces(scene, source_points, directions, own_geom_id, epsilon=1e-6):
        """Open3D sahnesi ile ışın kesişim kontrolü, kendi bina geometrisini hariç tutarak."""
        rays = np.array([np.concatenate([p, d]) for p, d in zip(source_points, directions)], dtype=np.float32)
        rays = o3d.core.Tensor(rays)
        ans = scene.cast_rays(rays)
        t_hit = ans['t_hit'].numpy()
        geom_ids = ans['geometry_ids'].numpy()
        has_hit = (t_hit < np.inf) & (t_hit > epsilon) & (geom_ids != own_geom_id)
        return has_hit
    
    @staticmethod
    def process_bina_intersections(bina_id, bina_points_info, sun_directions, scene, bina_to_geom_id, total_days):
        """Bir bina için kesişim kontrolleri ve günlük ortalama shadow hesaplama."""
        own_geom_id = bina_to_geom_id.get(bina_id, -1)
        
        for surface, info in bina_points_info.items():
            points = info["points"]
            if not points:
                continue
            coords = np.array([p["coordinates"] for p in points])
            
            for day in sun_directions:
                for hour, direction in sun_directions[day].items():
                    if direction is None:
                        for point_data in points:
                            point_data["shadow"] += 1
                    else:
                        directions = np.tile(direction, (len(coords), 1))
                        has_intersections = ShadowAnalyzer.ray_intersects_other_surfaces(scene, coords, directions, own_geom_id)
                        for point_data, has_intersection in zip(points, has_intersections):
                            if has_intersection:
                                point_data["shadow"] += 1
            # Günlük ortalama shadow hesapla
            for point_data in points:
                point_data["shadow"] = point_data["shadow"] / total_days if total_days > 0 else 0.0
        return bina_points_info
    
    @staticmethod
    def check_all_intersections(cm, points_info, sun_directions, total_days):
        """Tüm noktalar için kesişim kontrolü ve shadow hesaplama."""
        scene, bina_to_geom_id = ShadowAnalyzer.create_open3d_scene(cm)
        
        for bina_id, bina_points_info in tqdm(points_info.items(), desc="Binalar için kesişim kontrolü"):
            updated_points_info = ShadowAnalyzer.process_bina_intersections(bina_id, bina_points_info, sun_directions, scene, bina_to_geom_id, total_days)
            points_info[bina_id] = updated_points_info
        
        return points_info