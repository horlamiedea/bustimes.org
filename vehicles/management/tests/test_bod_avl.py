import os
from vcr import use_cassette
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from busstops.models import Region, DataSource
from ...models import VehicleLocation


class BusOpenDataVehicleLocationsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Region.objects.create(id='EA')

        DataSource.objects.create(name='Bus Open Data',
                                  url='https://data.bus-data.dft.gov.uk/avl/download/bulk_archive')

    @use_cassette(os.path.join(settings.DATA_DIR, 'vcr', 'bod_avl.yaml'))
    def test_handle(self):
        call_command('import_bod_avl')

        self.assertEqual(125, VehicleLocation.objects.count())
