"""
Bulk registration engine.
- Flexible CSV column matching (like the waybill parser)
- Optional geocoding via Nominatim
- Preview mode (validate without committing)
- Commit mode (create users, link to campaign, geocode)
"""
import csv
import io
import json
import urllib.request
import urllib.parse
from datetime import datetime

from werkzeug.security import generate_password_hash

from models import db, DBUser as User, Campaign


class CampaignBulkRegistration:
    NOMINATIM_BASE = 'https://nominatim.openstreetmap.org'
    USER_AGENT = 'TFA-Shuttles-BulkRegister/1.0'

    def __init__(self, load_data=None, save_data=None):
        # kept for backwards compatibility with the old signature
        self.load_data = load_data
        self.save_data = save_data

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def preview(self, csv_text, campaign_id=None, geocode=False):
        """
        Parse CSV, validate each row, return a report.
        Does NOT write anything to the DB.
        """
        rows = self._parse_csv(csv_text)
        results = []
        seen_usernames = set()
        campaign = Campaign.query.get(campaign_id) if campaign_id else None

        for i, row in enumerate(rows, start=2):  # header is line 1
            entry = self._validate_row(row, seen_usernames, campaign)
            entry['line'] = i
            results.append(entry)
            if entry['status'] == 'ok' and entry.get('username'):
                seen_usernames.add(entry['username'].lower())

        summary = {
            'total': len(results),
            'ok': sum(1 for r in results if r['status'] == 'ok'),
            'duplicate': sum(1 for r in results if r['status'] == 'duplicate'),
            'error': sum(1 for r in results if r['status'] == 'error'),
        }
        return {
            'rows': results,
            'summary': summary,
            'campaign': campaign.to_dict() if campaign else None,
            'geocoded': geocode,
        }

    def commit(self, csv_text, campaign_id=None, geocode=True,
               default_password=None, created_by=''):
        """
        Validate then create users. Only 'ok' rows are created.
        Returns a summary dict.
        """
        report = self.preview(csv_text, campaign_id=campaign_id, geocode=geocode)
        created = []
        skipped = []
        failed = []

        for row in report['rows']:
            if row['status'] != 'ok':
                (skipped if row['status'] == 'duplicate' else failed).append(row)
                continue

            password = row.get('password') or default_password or 'changeme123'
            if len(password) < 8:
                password = 'changeme123'

            # Geocode if needed
            lat = row.get('lat')
            lng = row.get('lng')
            if geocode and (lat is None or lng is None) and row.get('address'):
                coords = self._geocode(row['address'])
                if coords:
                    lat, lng = coords

            try:
                user = User(
                    username=row['username'],
                    name=row.get('name') or row['username'],
                    password=generate_password_hash(password),
                    is_admin=False,
                    is_driver=(row.get('role') or '').lower() == 'driver',
                    registered_address=row.get('address', '') or '',
                    registered_lat=lat,
                    registered_lng=lng,
                    travel_allowance=float(row.get('allowance') or 0),
                    campaign_id=campaign_id,
                )
                db.session.add(user)
                db.session.flush()
                created.append({'username': row['username'], 'line': row['line']})
            except Exception as e:
                failed.append({'username': row.get('username'), 'line': row['line'],
                               'message': str(e)})

        db.session.commit()

        return {
            'created': len(created),
            'skipped': len(skipped),
            'failed': len(failed),
            'created_users': created,
            'skipped_rows': skipped,
            'failed_rows': failed,
        }

    # ------------------------------------------------------------------
    # INTERNALS
    # ------------------------------------------------------------------

    def _norm(self, s):
        return (s or '').strip().lower().replace('_', ' ').replace('-', ' ')

    def _pick(self, row_norm, *candidates):
        for c in candidates:
            key = self._norm(c)
            if key in row_norm and row_norm[key] not in (None, ''):
                return row_norm[key]
        return ''

    def _parse_csv(self, csv_text):
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = []
        for raw in reader:
            row_norm = {self._norm(k): v for k, v in raw.items()}
            rows.append({
                'raw': row_norm,
                'username': self._pick(row_norm, 'username', 'user', 'id', 'employee id', 'employee_id').strip(),
                'name': self._pick(row_norm, 'name', 'full name', 'fullname').strip(),
                'password': self._pick(row_norm, 'password', 'pass', 'pw').strip(),
                'email': self._pick(row_norm, 'email', 'e mail', 'mail').strip(),
                'phone': self._pick(row_norm, 'phone', 'mobile', 'cell', 'telephone').strip(),
                'address': self._pick(row_norm, 'address', 'registered address', 'home address', 'location', 'home').strip(),
                'lat': self._to_float(self._pick(row_norm, 'lat', 'latitude')),
                'lng': self._to_float(self._pick(row_norm, 'lng', 'lon', 'longitude', 'long')),
                'allowance': self._to_float(self._pick(row_norm, 'allowance', 'travel allowance', 'travel_allowance')),
                'role': self._pick(row_norm, 'role', 'type', 'user type').strip().lower(),
            })
        return rows

    @staticmethod
    def _to_float(v):
        if v in (None, ''):
            return None
        try:
            return float(str(v).replace(',', '').strip())
        except ValueError:
            return None

    def _validate_row(self, row, seen_usernames, campaign):
        username = row.get('username', '')
        if not username:
            return {'status': 'error', 'message': 'Missing username', **row}
        if len(username) < 3:
            return {'status': 'error', 'message': 'Username too short (min 3)', **row}
        if username.lower() in seen_usernames:
            return {'status': 'duplicate', 'message': 'Duplicate in file', **row}
        if User.query.get(username):
            return {'status': 'duplicate', 'message': 'Already exists', **row}

        # Auto-fill address from campaign default if row has none
        if not (row.get('address') or '').strip() and campaign and campaign.default_pickup:
            row = {**row, 'address': campaign.default_pickup}
            row['_address_from_campaign'] = True

        return {'status': 'ok', 'message': '', **row}

    def _geocode(self, address):
        try:
            q = urllib.parse.urlencode({'q': address, 'format': 'json', 'limit': 1})
            url = f'{self.NOMINATIM_BASE}/search?{q}'
            req = urllib.request.Request(url, headers={'User-Agent': self.USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            if data:
                return (float(data[0]['lat']), float(data[0]['lon']))
        except Exception as e:
            print(f"Geocode failed for '{address}': {e}")
        return None
