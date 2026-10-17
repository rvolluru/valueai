import copy
import json

import pytest

from app.gpt_item_profile import GptItemProfiler


URL = "https://poshmark.com/listing/louis-vuitton-fleece-jacket-123"
BAD = "https://poshmark.com/listing/louis-vuitton-fleece-jacket-456"


@pytest.mark.parametrize("mode", ["valid", "changed_price", "bad_reference", "timeout", "no_accepted"])
def test_reprices_once_using_only_accepted_evidence(monkeypatch, mode):
    profiler = GptItemProfiler(enabled=True, provider_order="openai", openai_api_key="test",
        openai_model="gpt-5", gemini_api_key=None, gemini_model="unused", timeout_s=30,
        max_images=6, image_detail="auto", reasoning_effort="low", vertex_search_enabled=False)
    row = dict(url=URL, brand="Louis Vuitton", model="Fleece Jacket", variant_match="confirmed",
        match_type="exact", condition="New", price_type="asking", currency="USD", price=1000,
        match_evidence="Same fleece jacket")
    bad = dict(row, url=BAD, currency="GBP", price=900)
    first = dict(pricing_comparables=[row, bad], grounding_sources=[],
        resale_price_estimate=dict(estimated_price=950, references=[dict(url=URL), dict(url=BAD)]),
        retail_price_estimate=dict(estimated_price=None), resale_price_breakdown=[])
    if mode == "no_accepted":
        first["pricing_comparables"] = [bad]
    second = copy.deepcopy(first)
    second.update(pricing_comparables=[copy.deepcopy(row)],
        resale_price_estimate=dict(estimated_price=850, references=[dict(url=URL)]))
    if mode == "changed_price":
        second["pricing_comparables"][0]["price"] = 1
    if mode == "bad_reference":
        second["resale_price_estimate"]["references"] = [dict(url=BAD)]
    requests = []

    class Response:
        status_code = 200
        def __init__(self, data):
            self.data = data
        def raise_for_status(self):
            pass
        def json(self):
            return {"output": [dict(type="web_search_call", action=dict(sources=[
                dict(url=URL, title="Louis Vuitton Fleece Jacket"),
                dict(url=BAD, title="Louis Vuitton Fleece Jacket")])),
                dict(type="message", content=[dict(type="output_text", text=json.dumps(self.data))])]}

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            requests.append(kwargs["json"])
            if len(requests) == 2 and mode == "timeout":
                raise TimeoutError()
            return Response(first if len(requests) == 1 else second)

    monkeypatch.setattr("app.gpt_item_profile.httpx.Client", Client)
    result = profiler._call_openai_valuation(content=[], gemini_profile=dict(
        candidate_brand="Louis Vuitton", candidate_model="Fleece Jacket"), condition_grade="New")
    assert len(requests) == (1 if mode == "no_accepted" else 2)
    assert result["pricing_evidence_policy"]["status"] == ("qualified" if mode == "valid" else "needs_review")
    assert result["resale_price_estimate"]["estimated_price"] == (850 if mode == "valid" else None)
    if len(requests) == 2:
        assert "tools" not in requests[1]
        assert BAD not in json.dumps(requests[1])
