from test_api_integration import _build_client


def test_closet_excludes_archived_before_pagination_but_retains_internal_history():
    client = _build_client()
    from app import deps
    db = deps.get_db()
    common = dict(owner_name="Member", mode="trade", category="handbag", condition="New", size="M",
                  estimated_value=500, city="New York", image=None, images=[], description="", wants="",
                  tags=[], source_item_id=None, analysis=None, title="Archive test", brand="Prada")
    for index, status in enumerate(["Active", "Review", "Traded", "Archived", "archived"]):
        db.insert_listing(listing_id=f"archive-{index}", owner_subject="api-key", status=status, **common)
        db.execute("UPDATE listings SET created_at = ? WHERE listing_id = ?", (f"2026-11-09T00:00:0{index}Z", f"archive-{index}"))
    db.commit()
    headers = {"x-api-key": "test-key"}
    for search in ({}, {"q": "Prada"}):
        first = client.get('/v1/listings', params={"mine": True, "limit": 2, **search}, headers=headers)
        assert first.status_code == 200, first.text
        page = first.json()
        assert [item['listing_id'] for item in page['items']] == ['archive-2', 'archive-1']
        assert page['has_more'] is True
        last = client.get('/v1/listings', params={"mine": True, "limit": 2, "offset": 2, **search}, headers=headers).json()
        assert [item['listing_id'] for item in last['items']] == ['archive-0']
        assert last['has_more'] is False
    assert len(db.list_owner_listings('api-key')) == 5
    assert db.get_listing_by_id('archive-3')['status'] == 'Archived'
