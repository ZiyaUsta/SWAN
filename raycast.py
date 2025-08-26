#from numba import njit, prange, jit
import numpy as np

#@jit(nopython=True)
def ray_sphere_intersection_GPU(ray_origin, ray_dirs, sphere_centers, sphere_radius):

    n = ray_dirs.shape[0]
    m = sphere_centers.shape[0]
    results_per_ray = np.zeros(n, dtype=np.bool_)
    for r in range(n):
        for v in range(m):
            d = ray_dirs[r]
            A = np.dot(d, d)
            B = 2 * np.dot(d, ray_origin - sphere_centers[v])
            C_ = np.dot(ray_origin - sphere_centers[v], ray_origin - sphere_centers[v]) - sphere_radius**2
            discriminant = B**2 - 4 * A * C_
            
            if discriminant >= 0:
                results_per_ray[r] = True  # Intersection detected
                break  # No need to check other spheres for this ray
    return results_per_ray
'''''
def visualize_points(points):
    """
    Visualize 3D points using Open3D.
    
    :param points: A numpy array of shape (N, 3) representing the 3D points.
    """
    # Create a PointCloud object
    pcd = o3d.geometry.PointCloud()

    # Convert numpy points to Open3D format and assign to PointCloud
    pcd.points = o3d.utility.Vector3dVector(points)

    # Visualize the point cloud
    o3d.visualization.draw_geometries([pcd])
'''''