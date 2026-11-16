"""Staging Android regression checks. Unseeded workflows are explicitly Blocked."""
import json
import os
import time
from pathlib import Path

import pytest
from android_ui import AndroidUI
from appium.webdriver.common.appiumby import AppiumBy


@pytest.fixture
def ui():
    app = AndroidUI()
    try:
        app.login(os.environ['JOUFT_TEST_EMAIL'], os.environ['JOUFT_TEST_PASSWORD'])
        yield app
    finally:
        app.driver.quit()


@pytest.fixture
def fixtures():
    path = Path(os.environ.get('JOUFT_TEST_FIXTURES', 'android-fixtures.json'))
    return json.loads(path.read_text()) if path.exists() else {}


def require(fixtures, key):
    value = fixtures.get(key)
    if not value:
        pytest.skip('Blocked: missing Android fixture ' + key)
    return value


@pytest.mark.parametrize('tab,heading', [('Market', 'Marketplace'), ('Closet', 'My Closet'),
                                        ('Inbox', 'Trade Inbox'), ('Profile', 'SETTINGS')])
def test_navigation(ui, tab, heading):
    ui.tab(tab, heading)
    ui.wait(heading)


@pytest.mark.parametrize('area', ['closet', 'marketplace'])
def test_empty_search_and_recovery(ui, area):
    ui.search(area, 'QA-NONEXISTENT-' + str(time.time_ns()))
    if area == 'closet':
        ui.wait('No matching closet listings. Try another title, brand, or category.', 60)
    else:
        ui.wait('No matching search results', 60)
        assert not ui.card_titles()
    ui.tap('Clear closet search' if area == 'closet' else 'Clear marketplace search')
    ui.wait('My Closet' if area == 'closet' else 'Marketplace')


@pytest.mark.parametrize('area', ['closet', 'marketplace'])
def test_search_known_title(ui, fixtures, area):
    item = require(fixtures, area + '_listing')
    ui.search(area, item['title'])
    ui.wait('View details for ' + item['title'], 60)
    assert item['title'] in ui.card_titles()


@pytest.mark.parametrize('key', ['brand', 'category'])
def test_closet_search_metadata(ui, fixtures, key):
    item = require(fixtures, 'closet_listing')
    ui.search('closet', item[key])
    ui.wait('View details for ' + item['title'], 60)


def test_search_review_navigation(ui, fixtures):
    item = require(fixtures, 'review_listing')
    ui.open_listing('closet', item['title'])
    assert not ui.has('No listing selected')
    ui.tap('Edit')
    ui.wait('UPDATE • REVIEW • SAVE')
    ui.tap('Cancel Edit')
    ui.tab('Closet', 'My Closet')
    ui.search('closet', item['title'])
    ui.wait('View details for ' + item['title'], 60)


def test_marketplace_detail_gallery(ui, fixtures):
    item = require(fixtures, 'marketplace_listing')
    ui.open_listing('marketplace', item['title'])
    ui.show_gallery()
    assert not ui.has('Image unavailable')
    if item.get('minimum_images', 1) > 1:
        ui.tap('Next photo')
        assert not ui.has('Image unavailable')


@pytest.mark.parametrize('section,expected', [('Account', 'First Name'), ('Security', 'Verified Sign-in Email'),
    ('Style', 'Style Preferences'), ('Shipping', 'Shipping Addresses'), ('Subscription', 'Payment Methods')])
def test_profile_sections(ui, section, expected):
    ui.tab('Profile', 'SETTINGS')
    ui.tap(section)
    # Account/Style headings also appear as selectors; extra content checks below.
    if section in {'Account', 'Security', 'Style', 'Shipping', 'Subscription'}:
        ui.tap(expected, scroll=True)
    else:
        ui.wait(expected)
    assert not ui.has('Something went wrong')


def test_notification_history(ui):
    ui.tab('Profile', 'SETTINGS')
    ui.tap('Notifications — View all activity')
    ui.wait('Notifications')


def test_resume_session(ui):
    ui.tab('Closet', 'My Closet')
    ui.driver.terminate_app(ui.package)
    ui.driver.activate_app(ui.package)
    ui.tab('Closet', 'My Closet')
    assert not ui.has('Log In')


def test_signout(ui):
    ui.logout()
    assert not ui.has('My Closet')


def test_create_without_photos(ui):
    ui.tab('Create', 'Add Photos')
    assert ui.has('0/6')
    # Disabled Continue must not advance to Item Basics.
    buttons = ui.driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches("(?i)Continue")')
    assert buttons
    if buttons[-1].is_enabled():
        buttons[-1].click()
    assert not ui.has('Item Basics')


def test_assistant_open_close(ui):
    ui.tab('Market', 'Marketplace')
    ui.tap('Open Jouft assistant')
    ui.wait('Close assistant')
    ui.tap('Close assistant')
    ui.wait('Open Jouft assistant')


def has_manual_pricing_notice(values):
    # The native preflight and API boundary use different, both valid messages.
    return any('manual pricing review' in value.lower() or
               'manual review before publishing' in value.lower() for value in values)


def test_pricing_review_blocks_publication(ui, fixtures):
    item = require(fixtures, 'pricing_review_listing')
    ui.open_listing('closet', item['title'])
    ui.wait("We couldn't determine this item's value. It needs manual review before publishing. You do not need to set a value.")
    label = 'Publish without mannequin image' if ui.has('Publish without mannequin image') else 'Publish'
    ui.tap(label)
    # Must remain in review with an explicit pricing-related error, not a successful notice.
    from selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(ui.driver, 30).until(lambda _: has_manual_pricing_notice(ui.values()))
    assert not ui.has('Listing published to Marketplace.')
    ui.tap('Back'); ui.wait('My Closet'); ui.tap('Refresh')
    ui.search('closet', item['title']); ui.wait('View details for ' + item['title'], 60)
    ui.wait('Review and publish listing')
    ui.open_listing('closet', item['title'])
    assert has_manual_pricing_notice(ui.values())
    assert ui.has('Publish') or ui.has('Publish without mannequin image')


def test_second_account_private_isolation(ui, fixtures):
    private = require(fixtures, 'private_listing')
    email = os.environ.get('JOUFT_TEST_SECOND_EMAIL')
    password = os.environ.get('JOUFT_TEST_SECOND_PASSWORD')
    if not email or not password:
        pytest.skip('Blocked: second dedicated staging account secret not configured')
    # Establish that fixture exists for A before testing that B cannot see it.
    ui.search('closet', private['title']); ui.wait('View details for ' + private['title'], 60)
    ui.logout(); ui.login(email, password)
    ui.tab('Profile', 'SETTINGS'); ui.tap('Security', scroll=True)
    ui.wait(email); ui.wait('VERIFIED')
    # The security panel contains blank password-change fields. Never capture
    # it if any such field has a value, even in a dedicated QA account.
    sensitive = ui.driver.find_elements(AppiumBy.XPATH, '//*[@password="true"]')
    if sensitive and all(not field.get_attribute('text') for field in sensitive):
        folder = Path(os.environ.get('DEVICEFARM_LOG_DIR', 'output/devicefarm'))
        folder.mkdir(parents=True, exist_ok=True)
        ui.driver.save_screenshot(str(folder / 'second-account-verified-identity.png'))
    ui.search('closet', private['title'])
    ui.wait('No matching closet listings. Try another title, brand, or category.', 60)
    ui.search('marketplace', private['title'])
    ui.wait('No matching search results', 60)
    assert not ui.card_titles()


@pytest.mark.parametrize('decision', ['include', 'exclude'])
def test_second_account_published_gallery(ui, fixtures, decision):
    item = require(fixtures, 'published_' + decision)
    email = os.environ.get('JOUFT_TEST_SECOND_EMAIL')
    password = os.environ.get('JOUFT_TEST_SECOND_PASSWORD')
    if not email or not password:
        pytest.skip('Blocked: second dedicated staging account secret not configured')
    ui.logout(); ui.login(email, password)
    ui.open_listing('marketplace', item['title'])
    ui.show_gallery()
    seen = False
    for _ in range(item.get('image_count', 1)):
        assert not ui.has('Image unavailable')
        seen |= any(value.startswith('AI-generated styling preview.') for value in ui.values())
        if ui.elements('Next photo'):
            ui.tap('Next photo')
        else:
            break
    assert seen == (decision == 'include'), 'Public gallery disagrees with owner image decision'


@pytest.mark.parametrize('filter_label', ['Active', 'Closed'])
def test_trade_inbox_filters(ui, filter_label):
    ui.tab('Inbox', 'Trade Inbox')
    ui.tap(filter_label)
    ui.wait('Trade Inbox')
    assert not ui.has('Something went wrong')


def test_invalid_signin(ui):
    ui.logout(); ui.tap('Log In')
    fields = ui.wait_editable_fields()
    assert len(fields) >= 2
    fields[0].send_keys('jouft-invalid-' + str(time.time_ns()) + '@example.invalid')
    fields[1].send_keys('Invalid-Test-Password-123')
    ui.keyboard_down(); ui.elements('Sign In')[-1].click()
    from selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(ui.driver, 30).until(lambda _: any(
        word in value.lower() for value in ui.values()
        for word in ['not found', 'incorrect', 'invalid', 'failed', 'couldn’t find', "couldn't find"]))
    assert not ui.has('My Closet')


@pytest.mark.parametrize('identifier', ['', 'not-an-email'])
def test_required_signin_fields(ui, identifier):
    ui.logout(); ui.tap('Log In')
    fields = ui.wait_editable_fields()
    assert len(fields) >= 2
    fields[0].clear(); fields[1].clear()
    if identifier:
        fields[0].send_keys(identifier)
    ui.keyboard_down()
    before = ui.values()
    ui.elements('Sign In')[-1].click()
    from selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(ui.driver, 30).until(lambda _: any(
        word in value.lower() for value in ui.values() - before
        for word in ['required', 'missing', 'invalid', 'valid email', 'identifier', 'provide', 'not found', "couldn't find", 'you have to use email address']))
    assert not ui.has('My Closet')
