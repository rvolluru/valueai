from datetime import datetime, timedelta, timezone
from test_api_integration import _build_client


def test_profile_requires_age_eighteen_for_supplied_birthday():
    client = _build_client()
    today = datetime.now(timezone.utc).date()
    cutoff = today.replace(year=today.year - 18, day=min(today.day, 28))
    profile = {'first_name': 'Test', 'last_name': 'Member', 'email': 'test@example.com'}
    for birthday, expected in [(cutoff.isoformat(), 200), ((cutoff + timedelta(days=1)).isoformat(), 400),
                               (today.isoformat(), 400), ((today + timedelta(days=1)).isoformat(), 400),
                               ('2000-02-30', 400), (None, 400), ('', 400)]:
        response = client.put('/v1/me/profile-quiz', headers={'x-api-key': 'test-key'},
                              json={**profile, 'birthday': birthday})
        assert response.status_code == expected, response.text
    saved = client.get('/v1/me/profile-quiz', headers={'x-api-key': 'test-key'}).json()
    assert saved['birthday'] == cutoff.isoformat()
