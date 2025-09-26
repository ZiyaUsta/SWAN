from datetime import datetime, timedelta
import pytz
from astral import LocationInfo
from astral.sun import sun, elevation, azimuth
import pyproj
import numpy as np

class SunDirectionCalculator:
    """Güneş doğrultularını ve toplam gün sayısını hesaplar."""
    
    @staticmethod
    def get_hourly_sun_directions(start_date, end_date, location_info, hour_step=2, x_mid=None, y_mid=None, source_crs=None):
        """Verilen tarih aralığı için güneşin saatlik konumuna göre doğrultu vektörlerini ve toplam gün sayısını hesaplar."""
        if x_mid is None or y_mid is None or source_crs is None:
            raise ValueError("x_mid, y_mid ve source_crs sağlanmalı.")
        
        # Koordinat dönüşümü
        try:
            transformer = pyproj.Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
            lon, lat = transformer.transform(x_mid, y_mid)
            location_info = LocationInfo("CityModel", "Unknown", location_info.timezone, lat, lon)
        except Exception as e:
            raise ValueError(f"Koordinat dönüşümü başarısız: {str(e)}")
        
        sun_directions = {}
        # Toplam gün sayısını hesapla
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (end_dt - start_dt).days + 1
        
        timezone = pytz.timezone(location_info.timezone)
        try:
            current_date = start_dt
            while current_date <= end_dt:
                date_str = current_date.strftime("%Y-%m-%d")
                sun_directions[date_str] = {}
                date_dt = current_date.replace(tzinfo=timezone)
                s = sun(location_info.observer, date=date_dt, tzinfo=timezone)
                sunrise = s["sunrise"]
                sunset = s["sunset"]
                sunrise_hour = sunrise.hour if sunrise.minute < 30 else sunrise.hour + 1
                sunset_hour = sunset.hour if sunset.minute < 30 else sunset.hour + 1
                sunrise_hour = (sunrise_hour // hour_step) * hour_step
                hours = np.arange(sunrise_hour, sunset_hour + 1, hour_step).astype(int)
                for hour in hours:
                    time = date_dt.replace(hour=int(hour), minute=0, second=0)
                    alt = elevation(location_info.observer, time)
                    az = azimuth(location_info.observer, time)
                    if alt > 0:
                        alt_rad = np.deg2rad(alt)
                        az_rad = np.deg2rad(az)
                        dx = np.cos(alt_rad) * np.sin(az_rad)
                        dy = np.cos(alt_rad) * np.cos(az_rad)
                        dz = np.sin(alt_rad)
                        sun_directions[date_str][int(hour)] = [dx, dy, dz]
                    else:
                        sun_directions[date_str][int(hour)] = None
                current_date += timedelta(days=1)
            return sun_directions, total_days
        except Exception as e:
            raise Exception(f"Güneş doğrultuları hesaplanırken hata: {str(e)}")