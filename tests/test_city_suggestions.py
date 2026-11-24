from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app import main


@pytest.mark.parametrize('mode,expected', [(True, 1), (False, 0)])
def test_city_mode_accepts_city_without_street_and_restricts_provider(monkeypatch, mode, expected):
    calls = []
    class Response:
        status_code = 200
        content = b'json'
        def __init__(self, data): self.data = data
        def json(self): return self.data
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            calls.append(kwargs['json'])
            return Response({'suggestions': [{'placePrediction': {'placeId': 'austin', 'text': {'text': 'Austin, TX, USA'}}}]})
        def get(self, url, **kwargs):
            return Response({'formattedAddress': 'Austin, TX, USA', 'addressComponents': [
                {'types': ['locality'], 'longText': 'Austin'},
                {'types': ['administrative_area_level_1'], 'shortText': 'TX'},
                {'types': ['country'], 'shortText': 'US'},
            ]})
    monkeypatch.setattr(main.httpx, 'Client', Client)
    settings = SimpleNamespace(google_places_api_key='test', google_places_ios_bundle_identifier='', google_places_timeout_s=2, google_places_autocomplete_url='https://test/autocomplete', google_places_details_url='https://test/{place_id}')
    result = main._google_places_address_suggest(q='Aus', city=None, state=None, postal_code=None, settings=settings, cities_only=mode)
    assert len(result['suggestions']) == expected
    if mode:
        assert calls[0]['includedPrimaryTypes'] == ['(cities)']
        assert result['suggestions'][0]['city'] == 'Austin'
        assert result['suggestions'][0]['state'] == 'TX'
    assert calls[0]['includedRegionCodes'] == ['us']


def test_city_suggestions_deduplicate(monkeypatch):
    monkeypatch.setattr(main, '_google_places_address_suggest', lambda **kwargs: {'suggestions': [{'city': 'Austin', 'state': 'TX'}] * 2})
    assert main.google_places_city_suggest(q='Austin', settings=SimpleNamespace(google_places_api_key='test')) == {'suggestions': [{'city': 'Austin', 'state': 'TX', 'label': 'Austin, TX'}]}


def test_city_suggestions_missing_configuration():
    with pytest.raises(HTTPException) as error:
        main.google_places_city_suggest(q='Austin', settings=SimpleNamespace(google_places_api_key=''))
    assert error.value.status_code == 503
