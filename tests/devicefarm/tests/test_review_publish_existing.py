"""Publish an available review draft or explicitly designated existing Android staging draft."""
from test_create_listing import run_listing_flow


def test_review_and_publish_existing():
    run_listing_flow(publish=True, existing=True)
