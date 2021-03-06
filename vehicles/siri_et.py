import xml.etree.cElementTree as ET
from io import StringIO
from datetime import timedelta
from ciso8601 import parse_datetime
from django.db.models import Q
from busstops.models import Service, DataSource
from .models import Vehicle, VehicleLocation, Call


ns = {
    'siri': 'http://www.siri.org.uk/siri'
}
operator_refs = {
    'ANE': ('ANEA', 'ANUM', 'ARDU'),
    'ANW': ('ANWE', 'AMSY', 'ACYM'),
    'AYK': ('WRAY',),
    'YTG': ('YTIG',),
    'ATS': ('ASES', 'ARBB', 'GLAR'),
    'ASC': ('ARHE', 'AKSS', 'AMTM', 'GLAR'),
    'AMD': ('AMNO', 'AMID', 'AFCL'),
}
vehicles = Vehicle.objects.select_related('latest_location__journey')
fifteen_minutes = timedelta(minutes=15)


def handle_journey(element, source, when):
    journey_element = element.find('siri:EstimatedVehicleJourney', ns)
    vehicle = journey_element.find('siri:VehicleRef', ns)
    if vehicle is None:
        return

    operator = None
    operator_ref, fleet_number = vehicle.text.split('-')
    if not fleet_number.isdigit():
        fleet_number = None
    if operator_ref in operator_refs:
        operator = operator_refs[operator_ref]
        vehicle, vehicle_created = vehicles.filter(
            Q(code=fleet_number) | Q(code=vehicle.text),
            operator__in=operator
        ).get_or_create({
            'source': source,
            'operator_id': operator[0],
            'code': vehicle.text,
            'fleet_number': fleet_number
        })
    else:
        vehicle, vehicle_created = vehicles.get_or_create({'source': source}, code=vehicle.text,
                                                          fleet_number=fleet_number)

    journey_ref = journey_element.find('siri:DatedVehicleJourneyRef', ns).text
    journey = None
    latest_location = vehicle.latest_location
    if latest_location:
        if latest_location.journey.code == journey_ref:
            journey = latest_location.journey
            journey_created = False
        elif latest_location.journey.source_id != source.id and when - latest_location.datetime < fifteen_minutes:
            return
    else:
        journey = None

    calls_to_create = []
    calls_to_update = []

    calls_element = journey_element.find('siri:EstimatedCalls', ns)
    if calls_element is None:
        return
    for call in calls_element:
        visit_number = int(call.find('siri:VisitNumber', ns).text)
        stop_id = call.find('siri:StopPointRef', ns).text
        if not journey:
            departure_time = call.find('siri:AimedDepartureTime', ns)
            if departure_time is None:
                return
            departure_time = parse_datetime(departure_time.text)
            route_name = journey_element.find('siri:PublishedLineName', ns).text
            destination = journey_element.find('siri:DirectionName', ns).text

            service = None
            if operator:
                services = Service.objects.filter(current=True, line_name=route_name, operator__in=operator)
                try:
                    service = services.filter(stops__locality__stoppoint=stop_id).distinct().get()
                except Service.MultipleObjectsReturned:
                    pass
                except Service.DoesNotExist:
                    try:
                        service = services.distinct().get()
                    except (Service.MultipleObjectsReturned, Service.DoesNotExist):
                        pass

                if service:
                    if not service.tracking:
                        service.tracking = True
                        service.save(update_fields=['tracking'])

            journeys = vehicle.vehiclejourney_set
            journey_created = False
            journey = journeys.filter(code=journey_ref, datetime__date=departure_time.date()).first()
            if not journey:
                defaults = {
                    'code': journey_ref,
                    'datetime': departure_time,
                    'route_name': route_name,
                    'destination': destination,
                    'source': source,
                    'service': service,
                    'vehicle': vehicle
                }
                journey, journey_created = journeys.filter(datetime=departure_time).get_or_create(defaults)
        if not journey:
            return
        aimed_arrival_time = call.find('siri:AimedArrivalTime', ns)
        if aimed_arrival_time is not None:
            aimed_arrival_time = aimed_arrival_time.text
        expected_arrival_time = call.find('siri:ExpectedArrivalTime', ns)
        if expected_arrival_time is not None:
            expected_arrival_time = parse_datetime(expected_arrival_time.text)
        aimed_departure_time = call.find('siri:AimedDepartureTime', ns)
        if aimed_departure_time is not None:
            aimed_departure_time = aimed_departure_time.text
        expected_departure_time = call.find('siri:ExpectedDepartureTime', ns)
        if expected_departure_time is not None:
            expected_departure_time = parse_datetime(expected_departure_time.text)

        call = None

        if not journey_created:
            try:
                call = Call.objects.get(journey=journey, visit_number=visit_number)
            except Call.DoesNotExist:
                pass

        if not call:
            call = Call(journey=journey, visit_number=visit_number)

        call.stop_id = stop_id
        call.aimed_arrival_time = aimed_arrival_time
        call.expected_arrival_time = expected_arrival_time
        call.aimed_departure_time = aimed_departure_time
        call.expected_departure_time = expected_departure_time
        if call.id:
            calls_to_update.append(call)
        else:
            calls_to_create.append(call)

    Call.objects.bulk_create(calls_to_create)
    Call.objects.bulk_update(calls_to_update, fields=['stop_id', 'aimed_arrival_time', 'expected_arrival_time',
                             'aimed_departure_time', 'expected_departure_time'])

    previous_call = None
    for call in journey.call_set.order_by('visit_number'):
        if previous_call:
            previous_time = previous_call.expected_arrival_time or previous_call.expected_departure_time
            time = call.expected_departure_time or call.expected_arrival_time
            if previous_time and time and previous_time <= when and time >= when:
                if latest_location:
                    latest_location.journey = journey
                    latest_location.latlong = previous_call.stop.latlong
                    latest_location.heading = previous_call.stop.get_heading()
                    latest_location.datetime = previous_time
                    latest_location.save()
                else:
                    vehicle.latest_location = VehicleLocation.objects.create(
                        journey=journey,
                        latlong=previous_call.stop.latlong,
                        heading=previous_call.stop.get_heading(),
                        datetime=previous_time,
                        current=True
                    )
                    vehicle.save(update_fields=['latest_location'])
                vehicle.latest_location.channel_send(vehicle)
                return
        previous_call = call


def siri_et(request_body):
    source = DataSource.objects.get(name='Arriva')
    iterator = ET.iterparse(StringIO(request_body))
    for _, element in iterator:
        tag = element.tag[29:]
        if tag == 'RecordedAtTime':
            when = parse_datetime(element.text)
        elif tag == 'EstimatedJourneyVersionFrame':
            handle_journey(element, source, when)
            element.clear()
