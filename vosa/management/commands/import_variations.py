from titlecase import titlecase
from datetime import datetime
from busstops.management.import_from_csv import ImportFromCSVCommand
from ...models import Licence, Registration, Variation


def parse_date(date_string):
    if date_string:
        return datetime.strptime(date_string, '%d/%m/%y').date()


class Command(ImportFromCSVCommand):
    licence = None
    registration = None

    def handle_row(self, row):
        if len(row['Reg_No']) > 20 and row['Reg_No'].count('/'):
            parts = row['Reg_No'].split('/')
            if parts[0] == parts[1]:
                row['Reg_No'] = '/'.join(parts[1:])

        for key in ('start_point', 'finish_point', 'via'):
            if row[key].isupper() or row[key].islower():
                row[key] = titlecase(row[key])

        if not self.licence or self.licence.licence_number != row['Lic_No']:
            self.licence, _ = Licence.objects.update_or_create(
                {
                    'name': row['Op_Name'][:48],
                    'trading_name': row['trading_name'],
                    'traffic_area': row['Current Traffic Area'],
                    'discs': row['Discs in Possession'] or 0,
                    'authorised_discs': row['AUTHDISCS'] or 0,
                },
                licence_number=row['Lic_No']
            )

        if not self.registration or self.registration.registration_number != row['Lic_No']:
            self.registration, _ = Registration.objects.update_or_create(
                {
                    'licence': self.licence,
                    'description': row['Description'],
                    'start_point': row['start_point'],
                    'finish_point': row['finish_point'],
                    'via': row['via'],
                    'licence_status': row['Licence Status'],
                    'registration_status': row['Registration Status'],
                    'subsidies_description': row['Subsidies_Description'],
                    'subsidies_details': row['Subsidies_Details'],
                    'traffic_area_office_covered_by_area': row['TAO Covered BY Area'],
                    'service_number': row['Service Number'],
                },
                registration_number=row['Reg_No'],
            )

        Variation.objects.update_or_create(
            {
                'granted_date': parse_date(row['Granted_Date']),
                'expiry_date': parse_date(row['Exp_Date']),
                'effective_date': parse_date(row['effective_date']),
                'date_received': parse_date(row['received_date']),
                'end_date': parse_date(row['end_date']),
                'service_type_other_details': row['Service_Type_Other_Details'],
                'registration_status': row['Registration Status'],
                'publication_text': row['Pub_Text'],
                'service_type_description': row['Service_Type_Description'],
                'short_notice': row['Short Notice'],
                'authority_description': row['Auth_Description'],
            },
            registration=self.registration,
            variation_number=row['Variation Number'],
        )