import datetime
from django.contrib.gis.geos import Point
from ..import_live_vehicles import ImportLiveVehiclesCommand
from ...models import VehicleLocation, VehicleJourney, Service


class Command(ImportLiveVehiclesCommand):
    source_name = 'jersey'
    operator = 'libertybus'
    url = 'http://sojbuslivetimespublic.azurewebsites.net/api/Values/GetMin?secondsAgo=360'

    @staticmethod
    def get_datetime(item):
        now_datetime = datetime.datetime.now(datetime.timezone.utc)
        then_time = datetime.datetime.strptime(item['time'], '%H:%M:%S').time()

        now_time = now_datetime.time().replace(tzinfo=now_datetime.tzinfo)
        then_time = then_time.replace(tzinfo=now_datetime.tzinfo)

        if now_time < then_time:
            # yesterday
            now_datetime -= datetime.timedelta(days=1)
        return datetime.datetime.combine(now_datetime, then_time)

    def get_vehicle(self, item):
        parts = item['bus'].split('-')
        vehicle_code = parts[-1]
        defaults = {
            'operator_id': self.operator,
        }
        if vehicle_code.isdigit():
            defaults['fleet_number'] = vehicle_code
        return self.vehicles.get_or_create(
            defaults,
            source=self.source,
            code=vehicle_code
        )

    def get_items(self):
        return super().get_items()['minimumInfoUpdates']

    def get_journey(self, item, vehicle):
        journey = VehicleJourney()
        parts = item['bus'].split('-')
        journey.code = parts[-2]
        journey.route_name = item['line']

        if vehicle.latest_location and vehicle.latest_location.journey.route_name == journey.route_name:
            journey.service = vehicle.latest_location.journey.service
            return journey

        if item['cat'] != 'School Bus':
            try:
                line_name = item['line'].lower()
                journey.service = Service.objects.get(line_name=line_name, current=True, operator=self.operator)
            except (Service.MultipleObjectsReturned, Service.DoesNotExist) as e:
                print(e, line_name)

        return journey

    def create_vehicle_location(self, item):
        return VehicleLocation(
            latlong=Point(item['lon'], item['lat']),
            heading=item['bearing']
        )
