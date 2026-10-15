from test_api_integration import _build_client


def test_listing_search_filters_before_pagination_and_preserves_owner_scope():
    client = _build_client()
    from app import deps
    db = deps.get_db()
    common = dict(owner_name="Member", mode="trade", category="handbag", condition="New", size="M",
                  estimated_value=500, city="New York", image=None, images=[], description="", wants="",
                  tags=[], source_item_id=None, analysis=None, status="Active")
    for index, (owner, title, brand) in enumerate([
        ("api-key", "100% Bag", "Prada"), ("other", "Classic Tote", "Prada"),
        ("api-key", "Jacket", "Gucci"), ("api-key", "Another Tote", "Prada"),
    ]):
        db.insert_listing(listing_id=f"search-{index}", owner_subject=owner, title=title, brand=brand, **common)
    headers = {"x-api-key": "test-key"}
    def search(**params):
        response = client.get('/v1/listings', params=params, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()
    first = search(q="pRaDa", mine=True, limit=1)
    assert len(first['items']) == 1
    assert first['has_more']
    second = search(q="pRaDa", mine=True, limit=1, offset=first['next_offset'])
    assert len(second['items']) == 1
    assert second['items'][0]['listing_id'] != first['items'][0]['listing_id']
    assert not second['has_more']
    assert all(item['owner_subject'] == 'api-key' for item in first['items'] + second['items'])
    assert len(search(q="handbag")['items']) == 4
    assert len(search(q="%")['items']) == 1
    assert search(q="not found")['items'] == []
    assert len(search(q="")['items']) == 4


def test_lightweight_marketplace_retains_ai_disclosure_metadata():
    _build_client()
    from app import deps
    db = deps.get_db()
    db.insert_listing(listing_id="ai-preview", owner_subject="other", owner_name="Member", title="Shorts",
        mode="trade", category="clothes", brand="Brand", condition="New", size="M", estimated_value=100,
        city="New York", image="/v1/images/original", images=["/v1/images/original", "/v1/images/generated"],
        description="", wants="", tags=[], source_item_id=None, status="Active",
        analysis={"private_pricing_payload": "not needed by gallery", "generated_assets": [
            {"image_url": "/v1/images/generated", "synthetic": True, "review_decision": "include"}]})
    item = db.list_recent_listings(include_analysis=False, include_media=True, active_only=True)[0]
    assert "private_pricing_payload" not in item['analysis']
    assert item['analysis']['generated_assets'][0]['synthetic'] is True
    assert next(image for image in item['listed_images'] if image['d_img'] == '/v1/images/generated')['role_hint'] == 'ai_mannequin'
