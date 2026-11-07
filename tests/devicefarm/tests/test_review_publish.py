"""Android staging: create a fresh draft, review its results and publish it."""
from test_create_listing import run_listing_flow


def test_review_and_publish():
    run_listing_flow(publish=True)
