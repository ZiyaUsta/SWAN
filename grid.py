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
    """CityJSON dosyasını yükler ve CRS’yi kontrol eder."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dosya bulunamadı: {file_path}")
    try:
        cm = cityjson.load(file_path)
        print(f"CityJSON dosyası yüklendi: {file_path}")
        print(f"Toplam obje sayısı: {len(cm.j.get('CityObjects', {}))}")
        crs = cm.j.get('metadata', {}).get('referenceSystem', 'Bilinmiyor')
        print(f"Koordinat sistemi (CRS): {crs}")
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
    points = np.array(points)
    p0 = points[0]
    
    if np.allclose(normal, [0, 0, 1], atol=1e-6) or np.allclose(normal, [0, 0, -1], atol=1e-6):
        points_2d = [(p[0] - p0[0], p[1] - p0[1]) for p in points]
        u = np.array([1, 0, 0])
        v = np.array([0, 1, 0])
    else:
        if abs(normal[2]) > 1e-6:
            u = np.cross(normal, [0, 0, 1])
        else:
            u = np.cross(normal, [0, 1, 0])
        if np.linalg.norm(u) < 1e-6:
            print("Uyarı: u vektörü sıfır, alternatif vektör deneniyor.")
            u = np.cross(normal, [1, 0, 0])
        u = u / np.linalg.norm(u)
        v = np.cross(normal, u)
        v = v / np.linalg.norm(v)
        points_2d = [(np.dot(p - p0, u), np.dot(p - p0, v)) for p in points]
    
    if any(np.isnan(p).any() for p in points_2d):
        print("Hata: 2B koordinatlarda NaN tespit edildi.")
        return [], u, v
    
    print(f"2B projeksiyon vektörleri: u={u}, v={v}")
    print(f"2B koordinatlar: {points_2d}")
    return points_2d, u, v

def get_3d_surface_points(polygon_2d, u, v, normal, p0, spacing=2.0, max_points=100000):
    """2B poligon üzerinde ızgara oluşturur ve 3B'ye geri dönüştürür."""
    if not polygon_2d.is_valid:
        print("Hata: 2B poligon geçersiz.")
        return []
    minx, miny, maxx, maxy = polygon_2d.bounds
    print(f"Poligon sınırları: minx={minx:.2f}, miny={miny:.2f}, maxx={maxx:.2f}, maxy={maxy:.2f}")
    
    area = polygon_2d.area
    estimated_points = (maxx - minx) * (maxy - miny) / (spacing ** 2)
    if estimated_points > max_points:
        print(f"Uyarı: Tahmini nokta sayısı ({estimated_points:.0f}) maksimumdan fazla ({max_points}), üretim sınırlandırılıyor.")
        return []
    if area > 1e8:
        print(f"Uyarı: Poligon alanı çok büyük ({area:.2e} m²), üretim sınırlandırılıyor.")
        return []
    
    if (maxx - minx < spacing) or (maxy - miny < spacing):
        print(f"Uyarı: Yüzey çok küçük, spacing={spacing} m. Nokta üretilmeyebilir.")
        return []
    
    x = np.arange(np.floor(minx), np.ceil(maxx), spacing)
    y = np.arange(np.floor(miny), np.ceil(maxy), spacing)
    points_3d = []
    count = 0
    for xi in x:
        for yi in y:
            point_2d = Point(xi, yi)
            if polygon_2d.contains(point_2d):
                point_3d = np.array(p0) + xi * u + yi * v
                points_3d.append(point_3d.tolist())
                count += 1
                if count >= max_points:
                    print(f"Uyarı: Maksimum nokta sayısı ({max_points}) aşıldı, üretim durduruldu.")
                    break
        if count >= max_points:
            break
    print(f"{len(points_3d)} nokta üretildi.")
    return points_3d

def process_single_building_surfaces(city_model, building_id=None, spacing=2.0):
    """Tek bir binanın tüm yüzeylerini ve noktalarını işler, semantik bilgileriyle birlikte."""
    buildings = [co for co in city_model.cityobjects.values() if co.type == 'Building']
    if not buildings:
        raise ValueError("Dosyada bina bulunamadı.")
    
    if building_id:
        co = city_model.get_cityobjects(id=[building_id]).get(building_id)
        if not co:
            raise ValueError(f"Building ID {building_id} bulunamadı.")
        bina_id = building_id
    else:
        co = buildings[0]
        bina_id = co.id
        if not bina_id:
            raise ValueError("İlk binanın ID'si bulunamadı.")
    
    bina_name = co.attributes.get('name', 'Bilinmeyen') if co.attributes else 'Bilinmeyen'
    print(f"İşlenen bina: {bina_id} ({bina_name})")
    
    vertices = city_model.j['vertices']
    surfaces_dict = {}
    points_info = {}
    
    for geom_idx, geom in enumerate(co.geometry):
        print(f"Geometri {geom_idx} işleniyor: Tür = {geom.type}")
        # Semantik yüzeyleri al
        roof_surfaces = geom.get_surfaces('roofsurface')
        wall_surfaces = geom.get_surfaces('wallsurface')
        ground_surfaces = geom.get_surfaces('groundsurface')
        all_surfaces = {**roof_surfaces, **wall_surfaces, **ground_surfaces}
        print(f"Semantik yüzeyler: {all_surfaces}")
        
        # Tüm yüzey türleri için sınırları al
        for srf_idx, srf in all_surfaces.items():
            yuzey_turu = srf.get('type', 'Bilinmeyen')
            surface_indices = [idx[0] for idx in srf.get('surface_idx', [])]
            print(f"Yüzey türü: {yuzey_turu}, İndeksler: {surface_indices}")
            
            try:
                # Yüzey sınırlarını al (generator’ı listeye çevir)
                boundaries = list(geom.get_surface_boundaries(srf))
                if not boundaries:
                    print(f"{yuzey_turu} için sınırlar alınamadı, atlanıyor.")
                    continue
                
                # Her yüzey için sınırları işle
                for surface_idx, coords_3d in enumerate(boundaries):
                    surface_key = f"geom_{geom_idx}_surface_{surface_indices[surface_idx]}"
                    print(f"Yüzey işleniyor: {surface_key}")
                    if not coords_3d:
                        print(f"{surface_key}: Sınırlar boş, atlanıyor.")
                        continue
                    outer_ring_3d = coords_3d[0]  # İlk ring dış sınır
                    print(f"Yüzey {surface_indices[surface_idx]} köşe noktaları: {outer_ring_3d}")
                    surfaces_dict[surface_key] = outer_ring_3d
                    
                    # Normal vektör ve 2B projeksiyon
                    try:
                        a, b, c, d = get_plane_equation(outer_ring_3d)
                        normal = np.array([a, b, c])
                        print(f"Normal vektör: {normal}")
                        outer_ring_2d, u, v = project_points_to_2d(outer_ring_3d, normal)
                        if not outer_ring_2d:
                            print(f"{surface_key}: Geçersiz 2B koordinatlar, atlanıyor.")
                            continue
                        
                        # Delikler (holes) varsa işle
                        holes_2d = [project_points_to_2d(ring, normal)[0] for ring in coords_3d[1:]]
                        holes_2d = [h for h in holes_2d if h]
                        try:
                            polygon_2d = Polygon(outer_ring_2d, holes_2d if holes_2d else None)
                        except Exception as e:
                            print(f"{surface_key}: Poligon oluşturulamadı: {str(e)}")
                            continue
                        if not polygon_2d.is_valid:
                            print(f"{surface_key}: Geçersiz 2B poligon, atlanıyor.")
                            continue
                        
                        # 3B noktaları üret
                        points_3d = get_3d_surface_points(polygon_2d, u, v, normal, outer_ring_3d[0], spacing)
                        points_info[surface_key] = {
                            "bina_id": bina_id,
                            "yuzey_turu": yuzey_turu,
                            "noktalar": points_3d
                        }
                    except Exception as e:
                        print(f"{surface_key} işlenirken hata: {str(e)}")
            except Exception as e:
                print(f"{yuzey_turu} için sınırlar alınırken hata: {str(e)}")
    
    if not surfaces_dict and not points_info:
        print("Uyarı: Hiçbir yüzey veya nokta üretilmedi.")
    return surfaces_dict, points_info

def save_points_info(points_info, output_file):
    """Nokta bilgilerini JSON dosyasına kaydeder."""
    with open(output_file, 'w') as f:
        json.dump(points_info, f, indent=2)
    print(f"Nokta bilgileri {output_file} dosyasına kaydedildi.")

def visualize_surface_and_points(surfaces_dict, points_info, title="3B Yüzeyler ve Noktalar", point_size=50):
    """Tüm yüzeyleri ve noktaları farklı renklerde görselleştirir."""
    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection='3d')
    
    has_data = False
    
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
    
    for surface, info in points_info.items():
        points = info["noktalar"]
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
            ax.scatter(x, y, z, c='r', label=f"{surface} ({info['yuzey_turu']})", s=point_size)
            print(f"{surface}: {len(points)} nokta görselleştirildi (kırmızı).")
            has_data = True
        except Exception as e:
            print(f"{surface}: Noktalar çizilirken hata: {str(e)}")
    
    if not has_data:
        print("Hata: Görselleştirilecek hiçbir veri bulunamadı.")
        plt.close(fig)
        return
    
    all_vertices = []
    for vertices in surfaces_dict.values():
        all_vertices.extend(vertices)
    all_vertices = np.array(all_vertices)
    margin = 50.0
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
    input_file = "Rotterdam_validity.city.json"
    spacing = 2.0
    output_file = "surface_points_info.json"
    
    try:
        cm = load_cityjson(input_file)
        cityObjIds = list(cm.cityobjects.keys())
        if not cityObjIds:
            raise ValueError("Dosyada geçerli bina ID'si bulunamadı.")
        default_building_id = cityObjIds[3]
        print(f"Varsayılan bina ID: {default_building_id}")
        
        surfaces_dict, points_info = process_single_building_surfaces(cm, building_id=default_building_id, spacing=spacing)
        if points_info:
            save_points_info(points_info, output_file)
            visualize_surface_and_points(surfaces_dict, points_info, title="Tek Bina Yüzeyleri ve Noktalar")
            for surface, info in points_info.items():
                print(f"{surface}: Bina ID = {info['bina_id']}, Yüzey Türü = {info['yuzey_turu']}, Nokta Sayısı = {len(info['noktalar'])}")
        else:
            print("Hata: Hiçbir nokta üretilmedi.")
    except Exception as e:
        print(f"Hata: {str(e)}")