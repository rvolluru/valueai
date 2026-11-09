import pytest
from test_api_integration import _build_client


@pytest.mark.parametrize('cleared', [None, '', '   '])
def test_profile_phone_clear_persists_and_omitted_phone_is_preserved(cleared):
    client = _build_client()
    headers = {'x-api-key': 'test-key'}
    path = '/v1/me/profile-quiz'
    profile = {'first_name': 'Test', 'last_name': 'Member', 'email': 'test@example.com', 'birthday': '1990-01-01'}
    response = client.put(path, headers=headers, json={**profile, 'shipping_phone': '+19495550123'})
    assert response.status_code == 200, response.text
    assert response.json()['shipping_phone'] == '+19495550123'
    response = client.put(path, headers=headers, json=profile)
    assert response.status_code == 200, response.text
    assert response.json()['shipping_phone'] == '+19495550123'
    response = client.put(path, headers=headers, json={**profile, 'shipping_phone': cleared})
    assert response.status_code == 200, response.text
    assert response.json()['shipping_phone'] is None
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()['shipping_phone'] is None
