from cityjson_loader import CityJSONLoader
from geometry_processor import GeometryProcessor
from sun_direction_calculator import SunDirectionCalculator
from shadow_analyzer import ShadowAnalyzer
from visualizer import Visualizer
from postgis_exporter import PostGISExporter
from astral import LocationInfo
import time

def main():
    input_file = "Rotterdam.city.json"
    spacing = 2.0
    points_output_file = "all_surface_points_with_shadow.json"
    start_date = "2025-01-15"
    end_date = "2025-01-20"
    hour_step = 1
    db_params = {
        "dbname": "your_db_name",
        "user": "your username",
        "password": "your password",
        "host": "localhost",
        "port": "5432"
    }

    start_time = time.time()
    try:
        # Load CityJSON
        cm, x_mid, y_mid, source_crs = CityJSONLoader.load_cityjson(input_file)
        location_info = LocationInfo("Rotterdam", "Netherlands", "Europe/Amsterdam", 0, 0)

        # Calculate solar directions
        sun_directions, total_days = SunDirectionCalculator.get_hourly_sun_directions(
            start_date, end_date, location_info, hour_step=hour_step, x_mid=x_mid, y_mid=y_mid, source_crs=source_crs
        )

        # Process building surfaces
        all_surfaces_dict, all_points_info = GeometryProcessor.process_all_buildings_surfaces(
            cm, sun_directions, spacing=spacing
        )

        if all_points_info:
            # Perform shadow analysis
            points_info = ShadowAnalyzer.check_all_intersections(cm, all_points_info, sun_directions, total_days)
            print(f"Total runtime: {time.time() - start_time:.2f} seconds.")
            # Save and visualize results
            Visualizer.save_points_info_with_shadow(points_info, points_output_file)
            Visualizer.visualize_all_buildings(cm, points_info)

            # Export to PostGIS Please ensure that PostGIS is properly set up and the database parameters are correct. If you do not wish to export to PostGIS, you can comment out the following lines.
            exporter = PostGISExporter(db_params)
            try:
                success_count = exporter.export_cityobjects(cm, source_crs)
                print(f"{success_count} obje impoted into cityobjects table")
                exporter.export_surface_points(points_output_file, source_crs=source_crs)
                print(f"Surface_points table created")
            finally:
                exporter.close_connection()

    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()