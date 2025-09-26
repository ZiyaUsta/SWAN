import json
import numpy as np
import open3d as o3d
from tqdm import tqdm

class Visualizer:
    """Visualization and JSON output serialization."""
    
    @staticmethod
    def save_points_info_with_shadow(points_info, output_file):
        """saves the point information and shadow values into a JSON file"""
        json_data = []
        try:
            for bina_id, bina_points_info in points_info.items():
                for surface, info in bina_points_info.items():
                    for point_data in info["points"]:
                        json_data.append({
                            "bina_id": bina_id,
                            "surface": surface,
                            "point": point_data["coordinates"],
                            "shadow": point_data["shadow"],
                            "surface_type": info["surface_type"]
                        })
            with open(output_file, 'w') as f:
                json.dump(json_data, f, indent=2)
        except Exception as e:
            raise Exception(f"JSON writing error: {str(e)}")
    
    @staticmethod
    def get_color_for_shadow(shadow, max_shadow):
        """Determines the color based on the shadow value (0: green, max_shadow: red)."""
        if max_shadow == 0:
            return [0, 1, 0]
        normalized = shadow / max_shadow
        if normalized <= 0.33:
            return [0, 1, normalized * 3]
        elif normalized <= 0.66:
            return [normalized * 3 - 1, 1, 0]
        else:
            return [1, 1 - (normalized - 0.66) * 3, 0]
    
    @staticmethod
    def visualize_all_buildings(cm, points_info):
        """Visualizes all buildings and points."""
        vertices = np.array(cm['vertices'], dtype=np.float64)
        geometries = []
        
        max_shadow = 0
        for bina_points_info in points_info.values():
            for info in bina_points_info.values():
                for point_data in info["points"]:
                    max_shadow = max(max_shadow, point_data["shadow"])
        
        for bina_id, co in tqdm(cm.get('CityObjects', {}).items(), desc="Visualizing buildings"):
            if co.get('type') != 'Building':
                continue
            triangles = []
            vertex_offset = 0
            all_vertices = []
            
            for geom_idx, geom in enumerate(co.get('geometry', [])):
                boundaries = geom.get('boundaries', [])
                for boundary in boundaries:
                    for ring in boundary:
                        ring_3d = vertices[ring]
                        for i in range(1, len(ring_3d) - 1):
                            all_vertices.append(ring_3d[[0, i, i+1]])
                            triangles.append([vertex_offset, vertex_offset + 1, vertex_offset + 2])
                            vertex_offset += 3
            
            if not triangles:
                continue
            
            vertices_np = np.concatenate(all_vertices, axis=0)
            triangles_np = np.array(triangles, dtype=np.int32)
            
            mesh = o3d.geometry.TriangleMesh()
            mesh.vertices = o3d.utility.Vector3dVector(vertices_np)
            mesh.triangles = o3d.utility.Vector3iVector(triangles_np)
            mesh.paint_uniform_color([0.7, 0.7, 0.7])
            mesh.compute_vertex_normals()
            geometries.append(mesh)
        
        all_points = []
        all_colors = []
        for bina_id, bina_points_info in points_info.items():
            for surface, info in bina_points_info.items():
                for point_data in info["points"]:
                    all_points.append(point_data["coordinates"])
                    color = Visualizer.get_color_for_shadow(point_data["shadow"], max_shadow)
                    all_colors.append(color)
        
        if not all_points:
            return
        
        point_cloud = o3d.geometry.PointCloud()
        point_cloud.points = o3d.utility.Vector3dVector(np.array(all_points))
        point_cloud.colors = o3d.utility.Vector3dVector(np.array(all_colors))
        geometries.append(point_cloud)
        
        o3d.visualization.draw_geometries(geometries, window_name="All Buildings and Points")