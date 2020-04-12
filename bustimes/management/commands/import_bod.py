"""Import timetable data "fresh from the cow"
"""
import os
from requests import Session
from ciso8601 import parse_datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from busstops.models import DataSource, Service
from .import_gtfs import download_if_modified
from .import_transxchange import Command as TransXChangeCommand
from .import_passenger import handle_file
from ...models import Route, Calendar


def clean_up(operators, sources):
    Route.objects.filter(service__operator__in=operators).exclude(source__in=sources).delete()
    Service.objects.filter(operator__in=operators, current=True, route=None).update(current=False)
    Calendar.objects.filter(trip=None).delete()


def get_command():
    command = TransXChangeCommand()
    command.undefined_holidays = set()
    command.notes = {}
    command.corrections = {}

    return command


def bus_open_data(api_key):
    session = Session()
    command = get_command()

    for operator_id, region_id, operators in settings.BOD_OPERATORS:
        command.operators = operators
        command.region_id = region_id
        command.service_descriptions = {}
        command.service_codes = set()
        command.calendar_cache = {}

        response = session.get('https://data.bus-data.dft.gov.uk/api/v1/dataset/', params={
            'api_key': api_key,
            'noc': operator_id,
            'status': ['published', 'expiring']
        })

        sources = []

        for result in response.json()['results']:
            filename = result['name']
            url = result['url']
            path = os.path.join(settings.DATA_DIR, filename)

            modified = parse_datetime(result['modified'])

            command.source, created = DataSource.objects.get_or_create({'name': filename}, url=url)

            if command.source.datetime != modified:
                print(response.url)
                print(result)
                command.source.datetime = modified
                download_if_modified(path, url)
                handle_file(command, filename)

                if not created:
                    command.source.name = filename
                command.source.save(update_fields=['name', 'datetime'])

            sources.append(command.source)

        clean_up(operators.values(), sources)


def first():
    command = get_command()

    for operator, region_id, operators in settings.FIRST_OPERATORS:
        filename = operator + '.zip'
        url = 'http://travelinedatahosting.basemap.co.uk/data/first/' + filename
        modified = download_if_modified(os.path.join(settings.DATA_DIR, filename), url)

        if modified:
            command.operators = operators
            command.region_id = region_id
            command.service_descriptions = {}
            command.service_codes = set()
            command.calendar_cache = {}

            command.source, created = DataSource.objects.get_or_create({'name': operator}, url=url)
            command.source.datetime = timezone.now()

            handle_file(command, filename)

            clean_up(operators.values(), [command.source])


class Command(BaseCommand):
    @staticmethod
    def add_arguments(parser):
        parser.add_argument('api_key', nargs=1, type=str)

    def handle(self, api_key, **options):

        bus_open_data(api_key)

        first()