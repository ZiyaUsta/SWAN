# SWAN: Shadow Analysis for 3D City Models


SWAN (Shadow Analysis for 3D City Models) is an open-source Python tool designed for processing 3D city models in CityJSON format, performing shadow analysis, and storing results both in a json file and in a PostGIS database. SWAN’s modular architecture and dynamic spatial reference system (SRS) handling make it adaptable to diverse geospatial datasets


## Features

- **CityJSON Processing**: Loads and processes 3D city models using the `CityJSONLoader` module.
- **Shadow Analysis**: Computes hourly solar directions (`SunDirectionCalculator`), processes building surfaces (`GeometryProcessor`), and analyzes shadow impacts (`ShadowAnalyzer`).
- **Visualization**: Generates visualizations of shadow analysis results (`Visualizer`).
- **PostGIS Integration**: Exports CityJSON objects as `MULTIPOLYGON Z` geometries and surface points as `POINTZ` to PostGIS (`PostGISExporter`), supporting dynamic SRID extraction (e.g., `EPSG:28992`, `https://www.opengis.net/def/crs/EPSG/0/28992`).
- **Modular Design**: Extensible pipeline for easy integration into GIS workflows.
- **Open Source**: Licensed under [MIT License](#license), encouraging community contributions.

## Installation

### Prerequisites
- **Python**: 3.8 or higher
- **PostgreSQL**: With PostGIS extension enabled (`CREATE EXTENSION postgis;`)(Only required for database integration not mandatory!)
- **System Dependencies** (for `psycopg2`):
  ```bash
  # Ubuntu/Debian
  sudo apt-get install libpq-dev
  # macOS
  brew install postgresql
  ```

### Install Dependencies
Clone the repository and install Python dependencies using `requirements.txt`:

```bash
git clone https://github.com/[Your-Username]/SWAN.git
cd SWAN
pip install -r requirements.txt
```

**requirements.txt**:
```
astral=3.2
numpy=2.0.1
open3d=0.19.0
psycopg2=2.9.10
pyproj=3.7.1
shapely=2.1.1
tqdm=4.67.1
```

### Database Setup
1. Create a PostgreSQL database:
   ```sql
   CREATE DATABASE gis_database;
   ```
2. Enable PostGIS:
   ```sql
   \c gis_database
   CREATE EXTENSION postgis;
   ```

## Usage

### Example Workflow
Run the main script to process a CityJSON file, perform shadow analysis, and export results to PostGIS:

```bash
python main.py
```

**main.py** Example:
```python
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
```

### Verify Database Output
Check the `cityobjects` and `surface_points` tables in PostGIS:
```sql
SELECT id, type, ST_AsText(geometry) FROM cityobjects LIMIT 5;
SELECT bina_id, surface, ST_AsText(point), shadow, surface_type FROM surface_points LIMIT 5;
```

## Data Requirements
- **Input**: A valid CityJSON file (e.g., `Rotterdam_validity.city.json`) with `CityObjects` and `vertices`.
- **Output**: A JSON file (`all_surface_points_with_shadow.json`) with shadow analysis results, structured as:
  ```json
  [
      {
          "bina_id": "bina_1",
          "surface": "surface_1",
          "point": [123.45, 678.90, 10.0],
          "shadow": 2.5,
          "surface_type": "WallSurface"
      }
  ]
  ```

## Contributing
Contributions are welcome! To contribute:
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Commit your changes (`git commit -m "Add your feature"`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a Pull Request.


## License
SWAN is licensed under the [MIT License](LICENSE).


## Contact
For questions or support, contact Ziya Usta at [ziyausta@artvin.edu.tr] or open an issue on GitHub.