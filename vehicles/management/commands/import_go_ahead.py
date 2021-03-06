from time import sleep
from random import shuffle
from datetime import timedelta
from ciso8601 import parse_datetime_as_naive
from requests.exceptions import RequestException
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.db.models import Extent
from django.utils import timezone
from busstops.models import Service, Locality
from bustimes.models import get_calendars, Trip
from ...models import VehicleLocation, VehicleJourney
from ..import_live_vehicles import ImportLiveVehiclesCommand


def get_latlong(item):
    return Point(item['geo']['longitude'], item['geo']['latitude'])


class Command(ImportLiveVehiclesCommand):
    url = 'https://apiv2.otrl-bus.io/api/bus/nearby'
    source_name = 'Go-Ahead'
    operators = {
        'GOEA': ['KCTB', 'CHAM', 'HEDO'],
        'CSLB': ['OXBC', 'CSLB', 'THTR'],
        'PC': ['PLYC', 'TFCN'],
        'GONW': ['GONW'],
    }

    opcos = {
        'eastangliabuses': ['KCTB', 'CHAM', 'HEDO'],
        'oxford': ['OXBC', 'CSLB', 'THTR'],
        'plymouth': ['PLYC'],
        'cornwall': ['TFCN'],
        'gonorthwest': ['GONW'],
    }

    @staticmethod
    def get_datetime(item):
        return timezone.make_aware(parse_datetime_as_naive(item['recordedTime']))

    def get_vehicle(self, item):
        vehicle = item['vehicleRef']
        operator, fleet_number = vehicle.split('-', 1)
        operators = self.operators.get(operator)
        if not operators:
            print(operator)
        defaults = {
            'source': self.source
        }
        if fleet_number.isdigit():
            defaults['fleet_number'] = fleet_number

        if operator == 'PC':
            defaults['operator_id'] = 'PLYC'
            return self.vehicles.get_or_create(defaults, code=fleet_number, operator__parent='Go South West')
        return self.vehicles.get_or_create(defaults, code=vehicle)

    def get_points(self):
        now = self.source.datetime
        time_since_midnight = timedelta(hours=now.hour, minutes=now.minute, seconds=now.second,
                                        microseconds=now.microsecond)
        trips = Trip.objects.filter(calendar__in=get_calendars(now),
                                    start__lte=time_since_midnight,
                                    end__gte=time_since_midnight)
        services = Service.objects.filter(current=True, route__trip__in=trips)
        boxes = []

        for opco in self.opcos:
            for operator in self.opcos[opco]:
                operator_services = services.filter(operator=operator)
                extent = operator_services.aggregate(Extent('geometry'))['geometry__extent']
                if not extent:
                    continue
                lng = extent[0]
                while lng <= extent[2]:
                    lat = extent[1]
                    while lat <= extent[3]:
                        boxes.append((opco, operator_services, lng, lat))
                        lat += 0.2
                    lng += 0.2
        shuffle(boxes)
        return boxes

    def get_items(self):
        for opco, services, lng, lat in self.get_points():
            bbox = Polygon.from_bbox(
                (lng - 0.05, lat - 0.05, lng + 0.05, lat + 0.05)
            )
            if services.filter(geometry__bboverlaps=bbox).exists():
                params = {'lat': lat, 'lng': lng}
                headers = {'opco': opco}
                try:
                    response = self.session.get(self.url, params=params, timeout=30, headers=headers)
                    for item in response.json()['data']:
                        yield item
                except (RequestException, KeyError):
                    continue
                sleep(1)

    def get_old_locations(self):
        return super().get_old_locations().filter(datetime__lt=self.source.datetime - timedelta(minutes=10))

    def get_journey(self, item, vehicle):
        journey = VehicleJourney(
            code=str(item['datedVehicleJourney']),
            data=item
        )

        try:
            journey.destination = str(Locality.objects.get(stoppoint=item['destination']['ref']))
        except Locality.DoesNotExist:
            journey.destination = item['destination']['name']
        journey.route_name = item['lineRef']

        operator, fleet_number = item['vehicleRef'].split('-', 1)
        operators = self.operators.get(operator)
        if not operators:
            print(operator)

        if operators:
            latest_location = vehicle.latest_location
            if (
                latest_location and latest_location.current and latest_location.journey.code == journey.code and
                latest_location.journey.route_name == journey.route_name and latest_location.journey.service
            ):
                journey.service = latest_location.journey.service
            else:
                services = Service.objects.filter(operator__in=operators, line_name__iexact=item['lineRef'],
                                                  current=True)
                try:
                    try:
                        journey.service = services.get()
                    except Service.MultipleObjectsReturned:
                        destination = item['destination']['ref']
                        services = services.filter(stops__locality__stoppoint=destination).distinct()
                        journey.service = self.get_service(services, get_latlong(item))
                        if not journey.service:
                            print(operators, item['lineRef'])
                except Service.DoesNotExist as e:
                    print(e, operators, item['lineRef'])

                if journey.service and not latest_location:
                    try:
                        operator = journey.service.operator.get()
                        if operator.id != vehicle.operator_id:
                            vehicle.operator_id = operator.id
                            vehicle.save()
                    except journey.service.operator.model.MultipleObjectsReturned:
                        pass

        return journey

    def create_vehicle_location(self, item):
        bearing = item['geo']['bearing']
        return VehicleLocation(
            latlong=get_latlong(item),
            heading=bearing
        )
