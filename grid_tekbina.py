import json
import numpy as np
from shapely.geometry import Polygon, Point
from cjio import cityjson
'''''
# CityJSON dosyasını yükle
cm = cityjson.load('Rotterdam_validity.city.json')
cityObjIds = list(cm.cityobjects.keys())

# İlk objeyi al (örneğin, 5. obje)
obj_id = cityObjIds[5]

# Objenin geometrisini al
geom = cm.get_cityobjects()[obj_id].geometry[0]

first_surface = geom.boundaries[2][0]  # İlk yüzeyin köşe noktaları

# first_surface’ı kontrol et
print("first_surface koordinatları:", first_surface)

#first_surface’ın yapısını kontrol et
print("first_surface (ham veri):", first_surface)
'''
import json
import numpy as np
from shapely.geometry import Polygon, Point
from cjio import cityjson
import os
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import matplotlib.pyplot as plt

def load_cityjson(file_path):
    """CityJSON dosyasını yükler."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dosya bulunamadı: {file_path}")
    try:
        cm = cityjson.load(file_path)
        print(f"CityJSON dosyası yüklendi: {file_path}")
        print(f"Toplam obje sayısı: {len(cm.j.get('CityObjects', {}))}")
        return cm
    except Exception as e:
        raise ValueError(f"CityJSON dosyası yüklenemedi: {str(e)}")

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
    if abs(normal[2]) > 1e-6:
        u = np.cross(normal, [0, 0, 1])
    else:
        u = np.cross(normal, [0, 1, 0])
    u = u / np.linalg.norm(u)
    v = np.cross(normal, u)
    v = v / np.linalg.norm(v)
    points_2d = []
    for p in points:
        p = np.array(p)
        x = np.dot(p - points[0], u)
        y = np.dot(p - points[0], v)
        points_2d.append((x, y))
    print(f"2B projeksiyon vektörleri: u={u}, v={v}")
    return points_2d, u, v

def get_3d_surface_points(polygon_2d, u, v, normal, p0, spacing=1.0):
    """2B poligon üzerinde ızgara oluşturur ve 3B'ye geri dönüştürür."""
    if not polygon_2d.is_valid:
        print("Hata: 2B poligon geçersiz.")
        return []
    minx, miny, maxx, maxy = polygon_2d.bounds
    print(f"Poligon sınırları: minx={minx:.2f}, miny={miny:.2f}, maxx={maxx:.2f}, maxy={maxy:.2f}")
    if (maxx - minx < spacing) or (maxy - miny < spacing):
        print(f"Uyarı: Yüzey çok küçük, spacing={spacing} m. Nokta üretilmeyebilir.")
        return []
    x = np.arange(np.floor(minx), np.ceil(maxx), spacing)
    y = np.arange(np.floor(miny), np.ceil(maxy), spacing)
    points_3d = []
    for xi in x:
        for yi in y:
            point_2d = Point(xi, yi)
            if polygon_2d.contains(point_2d):
                point_3d = np.array(p0) + xi * u + yi * v
                points_3d.append(point_3d.tolist())
    print(f"{len(points_3d)} nokta üretildi.")
    return points_3d

def process_single_building_surfaces(city_model, building_id=None, spacing=1.0):
    """Tek bir binanın tüm yüzeylerini ve noktalarını işler."""
    buildings = [co for co in city_model.j['CityObjects'].values() if co['type'] == 'Building']
    if not buildings:
        raise ValueError("Dosyada bina bulunamadı.")
    target_building = buildings[3] if not building_id else city_model.j['CityObjects'].get(building_id)
    if not target_building:
        raise ValueError(f"Building ID {building_id} bulunamadı.")
    building_name = target_building.get('attributes', {}).get('name', 'Bilinmeyen')
    print(f"İşlenen bina: {building_name}")
    
    vertices = city_model.j['vertices']
    surfaces_dict = {}
    points_dict = {}
    
    for geom_idx, geom in enumerate(target_building['geometry']):
        print(f"Geometri {geom_idx} işleniyor: Tür = {geom['type']}")
        if geom['type'] == 'Solid':
            for shell_idx, shell in enumerate(geom['boundaries']):
                for surface_idx, surface in enumerate(shell):
                    surface_key = f"geom_{geom_idx}_shell_{shell_idx}_surface_{surface_idx}"
                    print(f"Yüzey işleniyor: {surface_key}")
                    coords_3d = []
                    for ring in surface:
                        ring_coords = [vertices[idx] for idx in ring]
                        coords_3d.append(ring_coords)
                        print(f"Yüzey {surface_idx} köşe noktaları: {ring_coords}")
                    outer_ring_3d = coords_3d[0]
                    surfaces_dict[surface_key] = outer_ring_3d
                    try:
                        a, b, c, d = get_plane_equation(outer_ring_3d)
                        normal = np.array([a, b, c])
                        print(f"Normal vektör: {normal}")
                        outer_ring_2d, u, v = project_points_to_2d(outer_ring_3d, normal)
                        print(f"2B koordinatlar: {outer_ring_2d}")
                        holes_2d = [project_points_to_2d(ring, normal)[0] for ring in coords_3d[1:]]
                        polygon_2d = Polygon(outer_ring_2d, holes_2d if holes_2d else None)
                        if not polygon_2d.is_valid:
                            print(f"{surface_key}: Geçersiz 2B poligon, atlanıyor.")
                            continue
                        points_3d = get_3d_surface_points(polygon_2d, u, v, normal, outer_ring_3d[0], spacing)
                        points_dict[surface_key] = points_3d
                    except Exception as e:
                        print(f"{surface_key} işlenirken hata: {str(e)}")
        elif geom['type'] == 'MultiSurface':
            for surface_idx, surface in enumerate(geom['boundaries']):
                surface_key = f"geom_{geom_idx}_surface_{surface_idx}"
                print(f"Yüzey işleniyor: {surface_key}")
                coords_3d = []
                for ring in surface:
                    ring_coords = [vertices[idx] for idx in ring]
                    coords_3d.append(ring_coords)
                    print(f"Yüzey {surface_idx} köşe noktaları: {ring_coords}")
                outer_ring_3d = coords_3d[0]
                surfaces_dict[surface_key] = outer_ring_3d
                try:
                    a, b, c, d = get_plane_equation(outer_ring_3d)
                    normal = np.array([a, b, c])
                    print(f"Normal vektör: {normal}")
                    outer_ring_2d, u, v = project_points_to_2d(outer_ring_3d, normal)
                    print(f"2B koordinatlar: {outer_ring_2d}")
                    holes_2d = [project_points_to_2d(ring, normal)[0] for ring in coords_3d[1:]]
                    polygon_2d = Polygon(outer_ring_2d, holes_2d if holes_2d else None)
                    if not polygon_2d.is_valid:
                        print(f"{surface_key}: Geçersiz 2B poligon, atlanıyor.")
                        continue
                    points_3d = get_3d_surface_points(polygon_2d, u, v, normal, outer_ring_3d[0], spacing)
                    points_dict[surface_key] = points_3d
                except Exception as e:
                    print(f"{surface_key} işlenirken hata: {str(e)}")
        else:
            print(f"Geometri {geom_idx}: Bilinmeyen tür ({geom['type']}), atlanıyor.")
    
    if not surfaces_dict and not points_dict:
        print("Uyarı: Hiçbir yüzey veya nokta üretilmedi.")
    return surfaces_dict, points_dict

def visualize_surface_and_points(surfaces_dict, points_dict, title="3B Yüzeyler ve Noktalar", point_size=50):
    """Tüm yüzeyleri ve noktaları farklı renklerde görselleştirir."""
    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection='3d')
    
    has_data = False
    
    # Yüzeyleri çiz (mavi)
    for surface, vertices in surfaces_dict.items():
        try:
            vertices = np.array(vertices)
            if vertices.shape[1] != 3:
                print(f"{surface}: Geçersiz yüzey formatı, atlanıyor (beklenen: 3B koordinatlar).")
                continue
            if np.any(np.isnan(vertices)):
                print(f"{surface}: Yüzey koordinatlarında NaN tespit edildi, atlanıyor.")
                continue
            poly = Poly3DCollection([vertices], alpha=0.5, facecolors='b', edgecolors='black')
            ax.add_collection3d(poly)
            print(f"{surface}: Yüzey görselleştirildi (mavi).")
            has_data = True
        except Exception as e:
            print(f"{surface}: Yüzey çizilirken hata: {str(e)}")
    
    # Noktaları çiz (kırmızı)
    for surface, points in points_dict.items():
        if not points:
            print(f"{surface}: Boş nokta listesi, atlanıyor.")
            continue
        try:
            points = np.array(points)
            if points.shape[1] != 3:
                print(f"{surface}: Geçersiz nokta formatı, atlanıyor (beklenen: 3B koordinatlar).")
                continue
            if np.any(np.isnan(points)):
                print(f"{surface}: Nokta koordinatlarında NaN tespit edildi, atlanıyor.")
                continue
            x, y, z = points[:, 0], points[:, 1], points[:, 2]
            ax.scatter(x, y, z, c='r', label=surface + " noktalar", s=point_size)
            print(f"{surface}: {len(points)} nokta görselleştirildi (kırmızı).")
            has_data = True
        except Exception as e:
            print(f"{surface}: Noktalar çizilirken hata: {str(e)}")
    
    if not has_data:
        print("Hata: Görselleştirilecek hiçbir veri bulunamadı.")
        plt.close(fig)
        return
    
    # Eksen sınırlarını sadece yüzey koordinatlarına göre ayarla
    all_vertices = []
    for vertices in surfaces_dict.values():
        all_vertices.extend(vertices)
    all_vertices = np.array(all_vertices)
    margin = 10.0  # Daha geniş bir boşluk
    ax.set_xlim(np.min(all_vertices[:, 0]) - margin, np.max(all_vertices[:, 0]) + margin)
    ax.set_ylim(np.min(all_vertices[:, 1]) - margin, np.max(all_vertices[:, 1]) + margin)
    ax.set_zlim(np.min(all_vertices[:, 2]) - margin, np.max(all_vertices[:, 2]) + margin)
    print(f"Eksen sınırları: xlim={ax.get_xlim()}, ylim={ax.get_ylim()}, zlim={ax.get_zlim()}")
    
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_zlabel('Z (m)')
    ax.set_title(title)
    ax.legend()
    plt.show()
    print("3B yüzeyler ve noktalar görselleştirildi.")

if __name__ == "__main__":
    input_file = "kasustucity.json"  # CityJSON dosya yolu
    spacing = 1.0  # Nokta aralığı (metre cinsinden)
    
    try:
        cm = load_cityjson(input_file)
        surfaces_dict, points_dict = process_single_building_surfaces(cm, spacing=spacing)
        if surfaces_dict or points_dict:
            visualize_surface_and_points(surfaces_dict, points_dict, title="Tek Bina Yüzeyleri ve Noktalar")
            print(f"Toplam {len(surfaces_dict)} yüzey işlendi.")
            for surface, vertices in surfaces_dict.items():
                print(f"{surface}: {len(vertices)} köşe noktası ile yüzey.")
            for surface, points in points_dict.items():
                print(f"{surface}: {len(points)} nokta oluşturuldu.")
        else:
            print("Hata: Hiçbir yüzey veya nokta üretilmedi.")
    except Exception as e:
        print(f"Hata: {str(e)}")