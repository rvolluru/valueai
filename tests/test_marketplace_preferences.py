from app.main import _listing_matches_viewer_preferences


def test_preferred_category_is_required_even_at_matching_size():
    profile = {'category_preferences': ['Handbags'], 'dresses_size': 'S'}
    assert not _listing_matches_viewer_preferences({'category': 'clothes', 'title': 'Mini Dress', 'size': 'S'}, profile)
    assert _listing_matches_viewer_preferences({'category': 'handbag', 'title': 'Tote'}, profile)


def test_dresses_use_dress_size_not_top_size():
    profile = {'category_preferences': ['Dresses', 'Jackets'], 'tops_size': 'M', 'dresses_size': 'S'}
    assert not _listing_matches_viewer_preferences({'category': 'clothes', 'title': 'Mini Dress', 'size': 'M'}, profile)
    assert _listing_matches_viewer_preferences({'category': 'clothes', 'title': 'Mini Dress', 'size': 'S'}, profile)
    assert _listing_matches_viewer_preferences({'category': 'clothes', 'title': 'Blazer', 'size': 'M'}, profile)


def test_missing_category_preferences_preserves_size_rules():
    assert _listing_matches_viewer_preferences({'category': 'handbag'}, {})
    assert not _listing_matches_viewer_preferences({'category': 'shoes', 'size': '8'}, {})


def test_skirts_and_shoes_use_their_own_sizes():
    profile = {'category_preferences': ['Skirts', 'Shoes'], 'bottoms_size': 'S', 'tops_size': 'L', 'shoes_size': '8;9'}
    assert _listing_matches_viewer_preferences({'category': 'clothes', 'title': 'Silk Skirt', 'size': 'S'}, profile)
    assert not _listing_matches_viewer_preferences({'category': 'clothes', 'title': 'Silk Skirt', 'size': 'L'}, profile)
    assert _listing_matches_viewer_preferences({'category': 'shoes', 'size': '9'}, profile)
