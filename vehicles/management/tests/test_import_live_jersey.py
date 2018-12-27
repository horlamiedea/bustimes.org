import os
from freezegun import freeze_time
from vcr import use_cassette
from django.test import TestCase
from busstops.models import Region, Operator, DataSource
from ..commands import import_live_jersey


class JerseyImportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Region.objects.create(id='JE')
        Operator.objects.create(id='libertybus', region_id='JE')

    @use_cassette(os.path.join('data', 'vcr', 'import_live_jersey.yaml'), decode_compressed_response=True)
    @freeze_time('2018-08-21 00:00:09')
    def test_handle(self):
        command = import_live_jersey.Command()
        items = command.get_items()

        command.source = DataSource.objects.create(datetime='2018-08-06T22:41:15+01:00')

        journey, created = command.get_journey(items[0])

        self.assertEqual('330', str(journey.vehicle))
        self.assertTrue(created)
        self.assertIsNone(journey.service)

        # test a time before midnight (yesterday)
        location = command.create_vehicle_location(items[0], journey.vehicle, journey.service)
        self.assertEqual('2018-08-20 23:59:00+00:00', str(location.datetime))
        self.assertEqual(43, location.heading)

        # test a time after midnight (today)
        journey, created = command.get_journey(items[1])

        location = command.create_vehicle_location(items[1], journey.vehicle, journey.service)
        self.assertEqual('2018-08-21 00:00:04+00:00', str(location.datetime))
        self.assertEqual(204, location.heading)