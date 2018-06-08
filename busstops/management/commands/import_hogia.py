from time import sleep
import requests
import logging
from django.db import OperationalError
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.utils import timezone
from ...models import DataSource, Vehicle, VehicleLocation, Service


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def update(self):
        now = timezone.now()

        url = 'http://ncc.hogiacloud.com/map/VehicleMapService/Vehicles'

        try:
            response = self.session.get(url, timeout=5)
        except OperationalError as e:
            print(e)
            logger.error(e, exc_info=True)
            return
        except requests.exceptions.RequestException as e:
            print(e)
            logger.error(e, exc_info=True)
            sleep(120)  # wait for two minutes
            return

        source, _ = DataSource.objects.update_or_create({'url': url, 'datetime': now}, name='NCC Hogia')

        for item in response.json():
            vehicle = item['Label']
            if ': ' in vehicle:
                vehicle, service = vehicle.split(': ', 1)
                service = service.split('/', 1)[0]
                service = Service.objects.filter(servicecode__scheme=source.name, servicecode__code=service).first()
            else:
                service = None
            vehicle, _ = Vehicle.objects.update_or_create(
                source=source,
                code=item['Label'].split(': ')[0]
            )
            if item['Speed'] != item['Speed']:
                item['Speed'] = None
            location = VehicleLocation(
                datetime=now,
                vehicle=vehicle,
                source=source,
                service=service,
                latlong=Point(item['Longitude'], item['Latitude']),
                data=item
            )
            location.save()
        sleep(10)

    def handle(self, *args, **options):

        self.session = requests.Session()

        while True:
            self.update()
