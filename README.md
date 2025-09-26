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
- **PostgreSQL**: With PostGIS extension enabled (`CREATE EXTENSION postgis;`)
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
psycopg2-binary==2.9.9
shapely==2.0.6
numpy==2.1.2
astral==3.2
matplotlib==3.9.2
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

def main():
    input_file = "Rotterdam_validity.city.json"
    points_output_file = "all_surface_points_with_shadow.json"
    db_params = {
        "dbname": "gis_database",
        "user": "postgres",
        "password": "your_password",
        "host": "localhost",
        "port": "5432"
    }

    # Load CityJSON
    cm, x_mid, y_mid, source_crs = CityJSONLoader.load_cityjson(input_file)
    location_info = LocationInfo("Rotterdam", "Netherlands", "Europe/Amsterdam", 0, 0)

    # Perform shadow analysis
    sun_directions, total_days = SunDirectionCalculator.get_hourly_sun_directions(
        "2025-01-15", "2025-01-20", location_info, hour_step=1, x_mid=x_mid, y_mid=y_mid, source_crs=source_crs
    )
    all_surfaces_dict, all_points_info = GeometryProcessor.process_all_buildings_surfaces(cm, sun_directions, spacing=2.0)
    points_info = ShadowAnalyzer.check_all_intersections(cm, all_points_info, sun_directions, total_days)
    Visualizer.save_points_info_with_shadow(points_info, points_output_file)
    Visualizer.visualize_all_buildings(cm, points_info)

    # Export to PostGIS
    exporter = PostGISExporter(db_params)
    try:
        exporter.export_cityobjects(cm, source_crs)
        exporter.export_surface_points(points_output_file, source_crs)
    finally:
        exporter.close_connection()

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

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md) and include tests for new features.

## License
SWAN is licensed under the [MIT License](LICENSE).

## Citation
If you use SWAN in your research, please cite our *SoftwareX* article:
> [Insert Authors], "[Insert Article Title]," *SoftwareX*, vol. [Insert Volume], [Insert Year], DOI: [Insert DOI].

## Contact
For questions or support, contact [Your Name] at [your.email@example.com] or open an issue on GitHub.