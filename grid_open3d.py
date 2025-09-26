import json
import numpy as np
import os
from astral import LocationInfo
from astral.sun import sun, elevation, azimuth
from datetime import datetime, timedelta
import pytz
import open3d as o3d
from tqdm import tqdm
import time
import pickle
from shapely.geometry import Polygon
from multiprocessing import Pool, cpu_count


def load_cityjson(file_path):
    """CityJSON dosyasını json.load ile yükler."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dosya bulunamadı: {file_path}")
    with open(file_path, 'r') as f:
        cm = json.load(f)
    print(f"CityJSON dosyası yüklendi: {file_path}")
    print(f"Toplam obje sayısı: {len(cm.get('CityObjects', {}))}")
    crs = cm.get('metadata', {}).get('referenceSystem', 'Bilinmeyen')
    print(f"Koordinat sistemi (CRS): {crs}")
    return cm


def get_plane_equation(points):
    """3B noktalar listesinden düzlem denklemini hesaplar."""
    if len(points) < 3:
        raise ValueError("Düzlem denklemi için en az 3 nokta gerekli.")
    p1, p2, p3 = points[:3]
    v1 = np.array(p2) - np.array(p1)
    v2 = np.array(p3) - np.array(p1)
    normal = np.cross(v1, v2)
    if np.linalg.norm(normal) < 1e-6:
        raise ValueError("Noktalar düzlemsel değil veya aynı doğruda.")
    normal = normal / np.linalg.norm(normal)
    a, b, c = normal
    d = np.dot(normal, p1)
    return a, b, c, d


def project_points_to_2d(points, normal):
    """3B noktaları düzleme projekte ederek 2B koordinatlara dönüştürür."""
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
        print("Hata: 2B koordinatlarda NaN tespit edildi.")
        return np.array([]), u, v
    
    return points_2d, u, v


def get_3d_surface_points(polygon_2d, u, v, normal, p0, spacing=4.0, sun_directions=None):
    """2B poligon üzerinde ızgara oluşturur ve 3B'ye geri dönüştürür."""
    poly = Polygon(polygon_2d)
    minx, miny, maxx, maxy = poly.bounds
    
    area = poly.area
    if area > 1e8:
        print(f"Uyarı: Poligon alanı çok büyük ({area:.2e} m²), üretim sınırlandırılıyor.")
        return []
    
    if (maxx - minx < spacing) or (maxy - miny < spacing):
        print(f"Uyarı: Yüzey çok küçük, spacing={spacing} m. Nokta üretilmeyebilir.")
        return []
    
    x = np.arange(np.floor(minx), np.ceil(maxx), spacing)
    y = np.arange(np.floor(miny), np.ceil(maxy), spacing)
    xx, yy = np.meshgrid(x, y)
    points_2d = np.column_stack([xx.ravel(), yy.ravel()])
    
    from shapely import vectorized
    inside_mask = vectorized.contains(poly, points_2d[:, 0], points_2d[:, 1])
    points_2d_inside = points_2d[inside_mask]
    
    filtered_sun_directions = {
        hour: direction if direction is not None and np.dot(normal, np.array(direction)) >= 0 else None
        for hour, direction in sun_directions.items()
    }
    
    points_3d = []
    points_3d_coords = p0 + points_2d_inside[:, 0][:, None] * u + points_2d_inside[:, 1][:, None] * v
    for coord in points_3d_coords:
        point_data = {
            "coordinates": coord.tolist(),
            "normal": normal.tolist(),
            "sun_directions": filtered_sun_directions
        }
        points_3d.append(point_data)
    
    print(f"{len(points_3d)} nokta üretildi.")
    return points_3d


def get_hourly_sun_directions(date, location_info, hour_step=2):
    """Güneşin saatlik konumuna göre doğrultu vektörlerini hesaplar."""
    sun_directions = {}
    timezone = pytz.timezone(location_info.timezone)
    date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone)
    
    s = sun(location_info.observer, date=date, tzinfo=timezone)
    sunrise = s["sunrise"]
    sunset = s["sunset"]
    
    sunrise_hour = sunrise.hour if sunrise.minute < 30 else sunrise.hour + 1
    sunset_hour = sunset.hour if sunset.minute < 30 else sunset.hour + 1
    sunrise_hour = (sunrise_hour // hour_step) * hour_step
    
    hours = np.arange(sunrise_hour, sunset_hour + 1, hour_step)
    for hour in hours:
        time = date.replace(hour=int(hour), minute=0, second=0)
        alt = elevation(location_info.observer, time)
        az = azimuth(location_info.observer, time)
        if alt > 0:
            alt_rad = np.deg2rad(alt)
            az_rad = np.deg2rad(az)
            dx = np.cos(alt_rad) * np.sin(az_rad)
            dy = np.cos(alt_rad) * np.cos(az_rad)
            dz = np.sin(alt_rad)
            sun_directions[hour] = [dx, dy, dz]
        else:
            sun_directions[hour] = None
    return sun_directions


def cache_sun_directions(date, location_info, cache_file="sun_directions_one_day.pkl", hour_step=2):
    """Güneş doğrultularını hesaplar ve önbelleğe kaydeder."""
    if os.path.exists(cache_file):
        with open(cache_file, 'rb') as f:
            sun_directions = pickle.load(f)
        print(f"Güneş doğrultuları {cache_file} dosyasından yüklendi.")
    else:
        sun_directions = get_hourly_sun_directions(date, location_info, hour_step)
        with open(cache_file, 'wb') as f:
            pickle.dump(sun_directions, f)
        print(f"Güneş doğrultuları {cache_file} dosyasına kaydedildi.")
    return sun_directions


def process_all_buildings_surfaces(cm, spacing=4.0, date="2025-06-15", location_info=None, hour_step=2):
    """Tüm binaların tüm yüzeylerini ve noktalarını işler."""
    if location_info is None:
        raise ValueError("Konum bilgisi sağlanmalı.")
    
    buildings = [id for id, co in cm.get('CityObjects', {}).items() if co.get('type') == 'Building']
    if not buildings:
        raise ValueError("Dosyada bina bulunamadı.")
    
    all_surfaces_dict = {}
    all_points_info = {}
    sun_directions = cache_sun_directions(date, location_info, hour_step=hour_step)
    
    for bina_id in tqdm(buildings, desc="Binalar işleniyor"):
        co = cm['CityObjects'][bina_id]
        bina_name = co.get('attributes', {}).get('name', 'Bilinmeyen')
        print(f"İşlenen bina: {bina_id} ({bina_name})")
        
        vertices = cm['vertices']
        surfaces_dict = {}
        points_info = {}
        
        for geom_idx, geom in enumerate(co.get('geometry', [])):
            semantics = geom.get('semantics', {})
            surfaces = semantics.get('surfaces', [])
            values = semantics.get('values', [])
            
            boundaries = geom.get('boundaries', [])
            for srf_idx, boundary in enumerate(boundaries):
                yuzey_turu = 'Bilinmeyen'
                if values and srf_idx < len(values) and values[srf_idx] is not None:
                    srf = surfaces[values[srf_idx]]
                    yuzey_turu = srf.get('type', 'Bilinmeyen')
                
                if not boundary:
                    continue
                
                outer_ring_idx = boundary[0]
                outer_ring_3d = [vertices[idx] for idx in outer_ring_idx]
                surface_key = f"{bina_id}_geom_{geom_idx}_surface_{srf_idx}"
                surfaces_dict[surface_key] = outer_ring_3d
                
                try:
                    a, b, c, d = get_plane_equation(outer_ring_3d)
                    normal = np.array([a, b, c])
                    outer_ring_2d, u, v = project_points_to_2d(outer_ring_3d, normal)
                    if not outer_ring_2d.size:
                        continue
                    
                    holes_2d = []
                    for ring in boundary[1:]:
                        ring_3d = [vertices[idx] for idx in ring]
                        holes_2d.append(project_points_to_2d(ring_3d, normal)[0])
                    holes_2d = [h for h in holes_2d if h]
                    
                    points_3d = get_3d_surface_points(outer_ring_2d, u, v, normal, outer_ring_3d[0], spacing, sun_directions)
                    points_info[surface_key] = {
                        "bina_id": bina_id,
                        "yuzey_turu": yuzey_turu,
                        "noktalar": points_3d
                    }
                except Exception as e:
                    print(f"{surface_key} işlenirken hata: {str(e)}")
        
        if surfaces_dict and points_info:
            all_surfaces_dict[bina_id] = surfaces_dict
            all_points_info[bina_id] = points_info
    
    return all_surfaces_dict, all_points_info


def save_points_info(points_info, output_file):
    """Nokta bilgilerini JSON dosyasına kaydeder."""
    json_data = {}
    for bina_id, bina_points_info in points_info.items():
        json_data[bina_id] = {}
        for surface, info in bina_points_info.items():
            json_data[bina_id][surface] = {
                "bina_id": info["bina_id"],
                "yuzey_turu": info["yuzey_turu"],
                "noktalar": [
                    {
                        "coordinates": p["coordinates"],
                        "normal": p["normal"],
                        "sun_directions": {
                            hour: dir if dir is not None else [0, 0, 0]
                            for hour, dir in p["sun_directions"].items()
                        }
                    }
                    for p in info["noktalar"]
                ]
            }
    
    with open(output_file, 'w') as f:
        json.dump(json_data, f, indent=2)
    print(f"Nokta bilgileri {output_file} dosyasına kaydedildi.")


def generate_sun_direction_lines(points_info, sun_directions, length=1000.0):
    """Bina yüzeyindeki noktalar için çizgi segmentleri üretir."""
    lines = []
    for bina_id, bina_points_info in points_info.items():
        for surface, info in bina_points_info.items():
            points = info["noktalar"]
            if not points:
                continue
            coords = np.array([p["coordinates"] for p in points])
            for hour, direction in sun_directions.items():
                if direction is not None:
                    direction = np.array(direction)
                    end_points = coords + direction * length
                    for i, (start, end) in enumerate(zip(coords, end_points)):
                        lines.append({
                            "bina_id": bina_id,
                            "surface": surface,
                            "start_point": start.tolist(),
                            "end_point": end.tolist(),
                            "hour": hour
                        })
    print(f"Toplam {len(lines)} çizgi segmenti üretildi.")
    return lines


def create_open3d_scene(cm, source_surface_keys):
    """CityJSON'dan Open3D RaycastingScene oluşturur."""
    scene = o3d.t.geometry.RaycastingScene()
    vertices = np.array(cm['vertices'], dtype=np.float32)
    all_vertices = []
    all_faces = []
    vertex_offset = 0
    
    for bina_id, co in cm.get('CityObjects', {}).items():
        if co.get('type') == 'Building':
            for geom_idx, geom in enumerate(co.get('geometry', [])):
                boundaries = geom.get('boundaries', [])
                for srf_idx, boundary in enumerate(boundaries):
                    surface_key = f"{bina_id}_geom_{geom_idx}_surface_{srf_idx}"
                    if surface_key in source_surface_keys:
                        continue
                    for ring in boundary:
                        ring_3d = vertices[ring]
                        for i in range(1, len(ring_3d) - 1):
                            all_vertices.append(ring_3d[[0, i, i+1]])
                            all_faces.append([vertex_offset, vertex_offset + 1, vertex_offset + 2])
                            vertex_offset += 3
    
    if not all_faces:
        print("Uyarı: Hiçbir yüzey bulunamadı.")
        return scene
    
    vertices_np = np.concatenate(all_vertices, axis=0).astype(np.float32)
    faces_np = np.array(all_faces, dtype=np.uint32)
    mesh = o3d.t.geometry.TriangleMesh(
        vertex_positions=o3d.core.Tensor(vertices_np),
        triangle_indices=o3d.core.Tensor(faces_np)
    )
    scene.add_triangles(mesh)
    print(f"Open3D sahnesi oluşturuldu: {len(all_faces)} üçgen.")
    return scene


def ray_intersects_other_surfaces(scene, source_points, directions):
    """Open3D sahnesi ile ışın kesişim kontrolü."""
    rays = np.array([np.concatenate([p, d]) for p, d in zip(source_points, directions)], dtype=np.float32)
    rays = o3d.core.Tensor(rays)
    ans = scene.cast_rays(rays)
    t_hit = ans['t_hit'].numpy()
    return t_hit < np.inf


def process_bina_intersections(args):
    """Bir bina için kesişim kontrolleri."""
    cm, bina_id, bina_points_info, sun_directions = args
    intersections = []
    source_surface_keys = set(bina_points_info.keys())
    
    scene = create_open3d_scene(cm, source_surface_keys)
    
    for surface, info in bina_points_info.items():
        points = info["noktalar"]
        if not points:
            continue
        coords = np.array([p["coordinates"] for p in points])
        
        for hour, direction in sun_directions.items():
            if direction is not None:
                directions = np.tile(direction, (len(coords), 1))
                has_intersections = ray_intersects_other_surfaces(scene, coords, directions)
                for i, (point_data, has_intersection) in enumerate(zip(points, has_intersections)):
                    if point_data["sun_directions"].get(hour) is not None:
                        intersections.append({
                            "bina_id": bina_id,
                            "surface": surface,
                            "point": point_data["coordinates"],
                            "hour": hour,
                            "has_intersection": bool(has_intersection)
                        })
                    else:
                        intersections.append({
                            "bina_id": bina_id,
                            "surface": surface,
                            "point": point_data["coordinates"],
                            "hour": hour,
                            "has_intersection": False
                        })
    return intersections


def check_all_intersections(cm, points_info, sun_directions):
    """Tüm noktalar için kesişim kontrolü."""
    intersections = []
    pool = Pool(processes=min(8, cpu_count()))
    args = [(cm, bina_id, bina_points_info, sun_directions) for bina_id, bina_points_info in points_info.items()]
    
    for bina_intersections in tqdm(pool.imap_unordered(process_bina_intersections, args), total=len(args), desc="Binalar için kesişim kontrolü"):
        intersections.extend(bina_intersections)
    
    pool.close()
    pool.join()
    print(f"Toplam {len(intersections)} nokta-saat çifti için kesişim kontrolü yapıldı.")
    return intersections


def save_intersections(intersections, output_file):
    """Kesişim sonuçlarını JSON dosyasına kaydeder."""
    json_data = [
        {
            "bina_id": inter["bina_id"],
            "surface": inter["surface"],
            "point": inter["point"],
            "hour": inter["hour"],
            "has_intersection": inter["has_intersection"]
        }
        for inter in intersections
    ]
    
    with open(output_file, 'w') as f:
        json.dump(json_data, f, indent=2)
    print(f"Kesişim sonuçları {output_file} dosyasına kaydedildi.")


def visualize_building(cm, points_info, bina_id, sun_hour=None, line_length=10.0):
    """Belirtilen binayı, üzerindeki noktaları ve güneş doğrultularını görselleştirir."""
    # Bina geometrisini oluştur
    vertices = np.array(cm['vertices'], dtype=np.float64)
    triangles = []
    vertex_offset = 0
    all_vertices = []
    
    co = cm['CityObjects'].get(bina_id)
    if not co or co.get('type') != 'Building':
        print(f"Hata: {bina_id} bir bina değil veya bulunamadı.")
        return
    
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
        print(f"Uyarı: {bina_id} için yüzey bulunamadı.")
        return
    
    vertices_np = np.concatenate(all_vertices, axis=0)
    triangles_np = np.array(triangles, dtype=np.int32)
    
    # Bina mesh'i
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(vertices_np)
    mesh.triangles = o3d.utility.Vector3iVector(triangles_np)
    mesh.paint_uniform_color([0.7, 0.7, 0.7])  # Gri renk
    mesh.compute_vertex_normals()
    
    # Noktaları oluştur
    point_cloud = o3d.geometry.PointCloud()
    all_points = []
    for surface, info in points_info.get(bina_id, {}).items():
        for point_data in info["noktalar"]:
            all_points.append(point_data["coordinates"])
    
    if not all_points:
        print(f"Uyarı: {bina_id} için nokta bulunamadı.")
        return
    
    point_cloud.points = o3d.utility.Vector3dVector(np.array(all_points))
    point_cloud.paint_uniform_color([1, 0, 0])  # Kırmızı noktalar
    
    # Güneş doğrultusu çizgileri
    line_sets = []
    if sun_hour is not None:
        lines = []
        line_points = []
        line_idx = 0
        for surface, info in points_info.get(bina_id, {}).items():
            for point_data in info["noktalar"]:
                sun_direction = point_data["sun_directions"].get(sun_hour)
                if sun_direction is not None and not np.allclose(sun_direction, [0, 0, 0]):
                    start = np.array(point_data["coordinates"])
                    end = start + np.array(sun_direction) * line_length
                    line_points.append(start)
                    line_points.append(end)
                    lines.append([line_idx, line_idx + 1])
                    line_idx += 2
        
        if lines:
            line_set = o3d.geometry.LineSet()
            line_set.points = o3d.utility.Vector3dVector(np.array(line_points))
            line_set.lines = o3d.utility.Vector2iVector(np.array(lines))
            line_set.paint_uniform_color([0, 0, 1])  # Mavi çizgiler
            line_sets.append(line_set)
    
    # Görselleştirme
    geometries = [mesh, point_cloud] + line_sets
    o3d.visualization.draw_geometries(geometries, window_name=f"Bina: {bina_id}, Saat: {sun_hour if sun_hour is not None else 'Tümü'}")
    print(f"{bina_id} binası görselleştirildi.")


if __name__ == "__main__":
    input_file = "Rotterdam_validity.city.json"
    spacing = 2.0
    output_file = "all_surface_points_info.json"
    intersections_file = "intersections_one_day.json"
    date = "2025-06-15"
    hour_step = 1
    
    start_time = time.time()
    try:
        cm = load_cityjson(input_file)
        
        location_info = LocationInfo("Rotterdam", "Netherlands", "Europe/Amsterdam", 51.9225, 4.47917)
        
        all_surfaces_dict, all_points_info = process_all_buildings_surfaces(
            cm, spacing=spacing, date=date, location_info=location_info, hour_step=hour_step
        )
        
        if all_points_info:
            save_points_info(all_points_info, output_file)
            sun_directions = cache_sun_directions(date, location_info, hour_step=hour_step)
            lines = generate_sun_direction_lines(all_points_info, sun_directions, length=1000.0)
            intersections = check_all_intersections(cm, all_points_info, sun_directions)
            save_intersections(intersections, intersections_file)
            
            print("\nKesişim Kontrol Sonuçları (Örnek):")
            for result in intersections[:10]:
                print(f"Bina: {result['bina_id']}, Yüzey: {result['surface']}, Nokta: {result['point']}, Saat: {result['hour']}:00, Kesişim: {result['has_intersection']}")
            
            if all_points_info:
                sample_bina = list(all_points_info.keys())[0]
                sample_surface = list(all_points_info[sample_bina].keys())[0]
                sample_point = all_points_info[sample_bina][sample_surface]["noktalar"][0]
                sun_directions = sample_point["sun_directions"]
                print("\nSaatlik Filtrelenmiş Güneş Doğrultuları (doğu, kuzey, yukarı):")
                for hour, direction in sorted(sun_directions.items()):
                    if direction is not None:
                        print(f"Saat {hour:02d}: {direction}")
                    else:
                        print(f"Saat {hour:02d}: Güneş ufuk altında veya yüzey güneşe bakmıyor.")
                
                # Görselleştirme: İlk bina için, örnek olarak saat 12:00
                visualize_building(cm, all_points_info, sample_bina, sun_hour=12, line_length=10.0)
        else:
            print("Hata: Hiçbir nokta üretilmedi.")
    except Exception as e:
        print(f"Hata: {str(e)}")
    finish_time = time.time()
    print(f"\nToplam çalışma süresi: {finish_time - start_time:.2f} saniye.")