"""
Import stop areas from the NPTG.

Usage:

    $ ./manage.py import_stop_areas < StopAreas.csv
"""

from django.contrib.gis.geos import Point
from ..import_from_csv import ImportFromCSVCommand
from ...models import StopArea, AdminArea


class Command(ImportFromCSVCommand):
    def handle_row(self, row):
        return StopArea.objects.update_or_create(
            id=row['StopAreaCode'],
            defaults={
                'name': row['Name'],
                'admin_area': AdminArea.objects.get(id=row['AdministrativeAreaCode']),
                'stop_area_type': row['StopAreaType'],
                'latlong': Point(int(row['Easting']), int(row['Northing']), srid=27700),
                'active': (row['Status'] == 'act'),
            }
        )[0]
