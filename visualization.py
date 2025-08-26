import json
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from cjio import cityjson
import os

def load_points(file_path):
    """JSON dosyasından 3B noktaları yükler ve formatı düzeltir."""
    try:
        with open(file_path, 'r') as f:
            points_dict = json.load(f)
        print(f"JSON dosyası yüklendi: {file_path}")
        print(f"Yüzey sayısı: {len(points_dict)}")
        # Noktaların formatını kontrol et ve düzelt
        corrected_points_dict = {}
        for surface, points in points_dict.items():
            if not points:
                print(f"Yüzey {surface}: Boş nokta listesi.")
                corrected_points_dict[surface] = []
                continue
            # Tuple'ları listeye çevir ve formatı doğrula
            corrected_points = []
            for p in points:
                try:
                    # Tuple veya liste kontrolü
                    if isinstance(p, (tuple, list)):
                        p = list(p)  # Tuple'ı listeye çevir
                        if len(p) == 3 and all(isinstance(x, (int, float)) for x in p):
                            corrected_points.append(p)
                        else:
                            print(f"Yüzey {surface}: Geçersiz nokta formatı: {p}")
                    else:
                        print(f"Yüzey {surface}: Geçersiz veri tipi: {p}")
                except Exception as e:
                    print(f"Yüzey {surface}: Nokta işlenirken hata: {p}, {str(e)}")
            corrected_points_dict[surface] = corrected_points
            print(f"Yüzey {surface}: {len(corrected_points)} nokta")
        return corrected_points_dict
    except FileNotFoundError:
        raise FileNotFoundError(f"Dosya bulunamadı: {file_path}")
    except Exception as e:
        raise ValueError(f"JSON dosyası yüklenemedi: {str(e)}")

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

def normalize_coordinates(points, center):
    """Koordinatları merkez noktaya göre normalize eder."""
    return [[p[0] - center[0], p[1] - center[1], p[2] - center[2]] for p in points]

def validate_surface(points_3d):
    """Yüzeyin geçerli olup olmadığını kontrol eder."""
    if len(points_3d) < 3:
        print(f"Hata: Yüzeyde {len(points_3d)} nokta var, en az 3 gerekli.")
        return False
    points_array = np.array(points_3d, dtype=float)
    bounds = points_array.max(axis=0) - points_array.min(axis=0)
    print(f"Yüzey boyutları: X={bounds[0]:.2f}, Y={bounds[1]:.2f}, Z={bounds[2]:.2f}")
    if np.any(bounds < 1e-6):
        print("Uyarı: Yüzey çok küçük, çizim başarısız olabilir.")
    if np.abs(bounds[2]) < 1e-6:
        print("Uyarı: Yüzey tamamen düzlemsel (z koordinatları aynı).")
        return True, True  # Geçerli, ancak düzlemsel
    return True, False

def visualize_points_and_surfaces(cityjson_path, points_json_path, building_id=None, title="3B Yüzeyler ve Noktalar", point_size=20, surface_alpha=0.7):
    """
    CityJSON dosyasındaki yüzeyleri ve JSON dosyasındaki 3B noktaları görselleştirir.
    
    Parametreler:
        cityjson_path (str): CityJSON dosyasının yolu
        points_json_path (str): Noktaların JSON dosyasının yolu
        building_id (str, optional): İşlenecek bina ID'si
        title (str): Grafik başlığı
        point_size (float): Noktaların boyutu
        surface_alpha (float): Yüzeylerin şeffaflığı (0-1 arası)
    """
    # CityJSON ve noktaları yükle
    cm = load_cityjson(cityjson_path)
    points_dict = load_points(points_json_path)
    
    # Bina seçimi
    buildings = [co for co in cm.j['CityObjects'].values() if co['type'] == 'Building']
    if not buildings:
        raise ValueError("Dosyada bina bulunamadı.")
    
    target_building = buildings[0] if not building_id else cm.j['CityObjects'].get(building_id)
    if not target_building:
        raise ValueError(f"Building ID {building_id} bulunamadı.")
    
    print(f"İşlenen bina: {target_building.get('attributes', {}).get('name', 'Bilinmeyen')}")
    
    # 3B figür oluştur
    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection='3d')
    
    # Renk paleti
    colors = ['b', 'r', 'g', 'c', 'm', 'y', 'k', 'orange', 'purple', 'brown']
    
    # Koordinat sınırlarını ve merkezi hesapla
    all_vertices = []
    
    # Yüzeyleri çiz
    vertices = cm.j['vertices']
    has_surfaces = False
    for geom_idx, geom in enumerate(target_building['geometry']):
        print(f"Geometri {geom_idx} işleniyor: Tür = {geom['type']}")
        if geom['type'] not in ['Solid', 'MultiSurface']:
            print(f"Geometri {geom_idx}: Bilinmeyen tür ({geom['type']}), atlanıyor.")
            continue
        
        if geom['type'] == 'Solid':
            for shell_idx, shell in enumerate(geom['boundaries']):
                for surface_idx, surface in enumerate(shell):
                    try:
                        coords_3d = []
                        for ring in surface:
                            ring_coords = [vertices[idx] for idx in ring]
                            coords_3d.append(ring_coords)
                            all_vertices.extend(ring_coords)
                        
                        # Dış sınır (ilk ring)
                        outer_ring_3d = coords_3d[0]
                        is_valid, is_planar = validate_surface(outer_ring_3d)
                        if not is_valid:
                            print(f"Yüzey {surface_idx}: Geçersiz yüzey, atlanıyor.")
                            continue
                        # Normalize koordinatlar
                        center = np.mean(outer_ring_3d, axis=0)
                        outer_ring_3d = normalize_coordinates(outer_ring_3d, center)
                        print(f"Yüzey {surface_idx} koordinatları: {outer_ring_3d}")
                        # Yüzeyi çiz
                        poly3d = [outer_ring_3d]
                        facecolor = 'gray' if is_planar else colors[(geom_idx + shell_idx + surface_idx) % len(colors)]
                        ax.add_collection3d(Poly3DCollection(poly3d, facecolors=facecolor, alpha=surface_alpha, label=f"Yüzey {surface_idx}"))
                        print(f"Yüzey çizildi: Geometri {geom_idx}, Shell {shell_idx}, Yüzey {surface_idx}, Vertex sayısı: {len(outer_ring_3d)}")
                        has_surfaces = True
                    except Exception as e:
                        print(f"Yüzey {surface_idx} çizilirken hata: {str(e)}")
        
        elif geom['type'] == 'MultiSurface':
            for surface_idx, surface in enumerate(geom['boundaries']):
                try:
                    coords_3d = []
                    for ring in surface:
                        ring_coords = [vertices[idx] for idx in ring]
                        coords_3d.append(ring_coords)
                        all_vertices.extend(ring_coords)
                    
                    # Dış sınır (ilk ring)
                    outer_ring_3d = coords_3d[0]
                    is_valid, is_planar = validate_surface(outer_ring_3d)
                    if not is_valid:
                        print(f"Yüzey {surface_idx}: Geçersiz yüzey, atlanıyor.")
                        continue
                    # Normalize koordinatlar
                    center = np.mean(outer_ring_3d, axis=0)
                    outer_ring_3d = normalize_coordinates(outer_ring_3d, center)
                    print(f"Yüzey {surface_idx} koordinatları: {outer_ring_3d}")
                    # Yüzeyi çiz
                    poly3d = [outer_ring_3d]
                    facecolor = 'gray' if is_planar else colors[(geom_idx + surface_idx) % len(colors)]
                    ax.add_collection3d(Poly3DCollection(poly3d, facecolors=facecolor, alpha=surface_alpha, label=f"Yüzey {surface_idx}"))
                    print(f"Yüzey çizildi: Geometri {geom_idx}, Yüzey {surface_idx}, Vertex sayısı: {len(outer_ring_3d)}")
                    has_surfaces = True
                except Exception as e:
                    print(f"Yüzey {surface_idx} çizilirken hata: {str(e)}")
    
    # Noktaları çiz
    has_points = False
    for idx, (surface, points) in enumerate(points_dict.items()):
        if not points:
            print(f"{surface}: Boş nokta listesi, atlanıyor.")
            continue
        try:
            points = np.array(points, dtype=float)
            if points.shape[1] != 3:
                print(f"{surface}: Geçersiz nokta formatı, atlanıyor (beklenen: 3B koordinatlar).")
                continue
            # Normalize noktalar
            center = np.mean(points, axis=0)
            points = normalize_coordinates(points, center)
            x, y, z = points[:, 0], points[:, 1], points[:, 2]
            ax.scatter(x, y, z, c=colors[idx % len(colors)], label=f"Noktalar {surface}", s=point_size)
            print(f"{surface}: {len(points)} nokta görselleştirildi.")
            all_vertices.extend(points)
            has_points = True
        except Exception as e:
            print(f"{surface}: Noktalar çizilirken hata: {str(e)}")
    
    # Eğer hiç yüzey veya nokta çizilmediyse grafiği gösterme
    if not (has_points or has_surfaces):
        print("Hata: Görselleştirilecek hiçbir yüzey veya nokta bulunamadı.")
        plt.close(fig)
        return
    
    # Eksen sınırlarını otomatik ayarla
    if all_vertices:
        all_vertices = np.array(all_vertices, dtype=float)
        min_bounds = all_vertices.min(axis=0)
        max_bounds = all_vertices.max(axis=0)
        ax.set_xlim(min_bounds[0], max_bounds[0])
        ax.set_ylim(min_bounds[1], max_bounds[1])
        ax.set_zlim(min_bounds[2], max_bounds[2])
        print(f"Normalize edilmiş eksen sınırları: X=({min_bounds[0]:.2f}, {max_bounds[0]:.2f}), Y=({min_bounds[1]:.2f}, {max_bounds[1]:.2f}), Z=({min_bounds[2]:.2f}, {max_bounds[2]:.2f})")
    
    # Eksen etiketleri
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_zlabel('Z (m)')
    
    # Başlık ve lejant
    ax.set_title(title)
    if has_points or has_surfaces:
        ax.legend()
    
    # Görselleştirmeyi göster
    plt.show()
    print("3B yüzeyler ve noktalar görselleştirildi.")

if __name__ == "__main__":
    cityjson_path = "kasustucity.json"  # CityJSON dosya yolu
    points_json_path = "surface_3d_points.json"  # Noktaların JSON dosya yolu
    
    try:
        visualize_points_and_surfaces(cityjson_path, points_json_path, title="Rotterdam Bina Yüzeyleri ve Noktalar", point_size=20, surface_alpha=0.7)
    except Exception as e:
        print(f"Hata: {str(e)}")