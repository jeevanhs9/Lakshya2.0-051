"""Configurable geocoding and driving-route integration for FarmLink."""

import json
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class RoutingServiceError(Exception):
    pass


class RoutingService:
    def __init__(self, api_key=None, provider='google', region='in'):
        self.api_key = api_key
        self.provider = provider
        self.region = region

    @property
    def configured(self):
        return bool(self.api_key)

    def _get_json(self, base_url, params):
        if not self.configured:
            return None
        auth_param = 'apiKey' if self.provider == 'geoapify' else 'key'
        request_url = f'{base_url}?{urlencode({**params, auth_param: self.api_key})}'
        request = Request(request_url, headers={'User-Agent': 'FarmLink-AI/1.0'})
        try:
            with urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RoutingServiceError('The configured routing service could not be reached.') from error
        if self.provider == 'google' and payload.get('status') not in {'OK', 'ZERO_RESULTS'}:
            raise RoutingServiceError(payload.get('error_message') or 'Google Maps could not complete this request.')
        return payload

    @lru_cache(maxsize=512)
    def geocode(self, address):
        if not self.configured:
            return None
        if self.provider == 'geoapify':
            payload = self._get_json(
                'https://api.geoapify.com/v1/geocode/search',
                {'text': address, 'filter': f'countrycode:{self.region}', 'format': 'json'},
            )
            results = payload.get('results', [])
            if not results:
                return None
            latitude = results[0].get('lat')
            longitude = results[0].get('lon')
            if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
                return None
            return float(latitude), float(longitude)
        payload = self._get_json(
            'https://maps.googleapis.com/maps/api/geocode/json',
            {'address': address, 'region': self.region},
        )
        results = payload.get('results', [])
        if not results:
            return None
        location = results[0].get('geometry', {}).get('location', {})
        latitude = location.get('lat')
        longitude = location.get('lng')
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            return None
        return float(latitude), float(longitude)

    def route(self, coordinates):
        """Return Google driving distance and duration for 2–25 coordinates."""
        if not self.configured or len(coordinates) < 2:
            return None
        if len(coordinates) > 25:
            raise RoutingServiceError('FarmLink accepts a maximum of 25 route points per request.')
        if self.provider == 'geoapify':
            payload = self._get_json(
                'https://api.geoapify.com/v1/routing',
                {
                    'waypoints': '|'.join(f'{latitude:.6f},{longitude:.6f}' for latitude, longitude in coordinates),
                    'mode': 'light_truck',
                    'format': 'json',
                },
            )
            routes = payload.get('results', [])
            if not routes:
                return None
            route = routes[0]
            distance_meters = route.get('distance', 0)
            duration_seconds = route.get('time', 0)
            if distance_meters <= 0 or duration_seconds <= 0:
                return None
            return {
                'distanceKm': round(distance_meters / 1000, 1),
                'durationHours': round(duration_seconds / 3600, 2),
                'provider': 'geoapify',
            }
        encoded = [f'{latitude:.6f},{longitude:.6f}' for latitude, longitude in coordinates]
        params = {
            'origin': encoded[0],
            'destination': encoded[-1],
            'mode': 'driving',
            'units': 'metric',
        }
        if len(encoded) > 2:
            params['waypoints'] = '|'.join(encoded[1:-1])
        payload = self._get_json('https://maps.googleapis.com/maps/api/directions/json', params)
        routes = payload.get('routes', [])
        if not routes:
            return None
        legs = routes[0].get('legs', [])
        distance_meters = sum(leg.get('distance', {}).get('value', 0) for leg in legs)
        duration_seconds = sum(leg.get('duration', {}).get('value', 0) for leg in legs)
        if distance_meters <= 0 or duration_seconds <= 0:
            return None
        return {
            'distanceKm': round(distance_meters / 1000, 1),
            'durationHours': round(duration_seconds / 3600, 2),
            'provider': 'google_directions',
        }
