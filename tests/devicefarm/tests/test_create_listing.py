"""Real mobile UI test: sign in, select photos, save a listing, verify analysis and mannequin output."""

import base64
import json
import os
import re
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
import subprocess

import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from android_ui import android_photo_thumbnails
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException


def new_listing_card_visible(before, after):
    # RN prunes off-screen accessibility nodes: inserting a new first card need
    # not increase the number of visible cards. An unchanged window is not proof.
    return bool(after) and (len(after) > len(before) or not before or after[0] != before[0])


def run_listing_flow(*, publish=False, existing=False, after_save=None):
    # Require explicit staging confirmation: this test creates a real saved listing.
    assert os.environ.get('JOUFT_TEST_TARGET') == 'staging', 'Set JOUFT_TEST_TARGET=staging'
    email = os.environ['JOUFT_TEST_EMAIL']
    password = os.environ['JOUFT_TEST_PASSWORD']
    target_title = os.environ.get('JOUFT_TEST_LISTING_TITLE', '').strip()
    assert not existing or publish, 'Existing review flow requires publication mode'
    photos = [] if existing else sorted(Path(os.environ['JOUFT_TEST_PHOTOS']).glob('*.jpg'))
    assert existing or 1 <= len(photos) <= 6, 'Supply 1–6 JPG views of one item, including required coverage'
    package = os.environ.get('DEVICEFARM_APP_PACKAGE', 'com.jouft.app.dev')
    assert package == 'com.jouft.app.dev', 'Only the testing app identity is supported'
    ios = os.environ.get('JOUFT_TEST_PLATFORM', 'Android').lower() == 'ios'
    assert not publish or not ios, 'Review and Publish currently targets Android only'
    input_class = 'XCUIElementTypeTextField' if ios else 'android.widget.EditText'
    options = UiAutomator2Options().load_capabilities({
        'platformName': 'Android', 'appium:automationName': 'UiAutomator2',
        'appium:deviceName': os.environ.get('DEVICEFARM_DEVICE_NAME', 'Android'),
        'appium:udid': os.environ.get('DEVICEFARM_DEVICE_UDID'),
        'appium:appPackage': package, 'appium:autoGrantPermissions': True,
        'appium:newCommandTimeout': 180,
    })
    if ios:
        options = XCUITestOptions().load_capabilities({
            'platformName': 'iOS', 'appium:automationName': 'XCUITest',
            'appium:udid': os.environ['DEVICEFARM_DEVICE_UDID'],
            'appium:bundleId': package, 'appium:newCommandTimeout': 180,
            'appium:usePrebuiltWDA': True, 'appium:useNewWDA': False,
            'appium:autoAcceptAlerts': False,
            'appium:derivedDataPath': os.environ.get('DEVICEFARM_APPIUM_WDA_DERIVED_DATA_PATH'),
        })
    if os.environ.get('DEVICEFARM_APP_PATH'):
        options.set_capability('appium:app', os.environ['DEVICEFARM_APP_PATH'])
    driver = webdriver.Remote(os.environ.get('APPIUM_SERVER_URL', 'http://127.0.0.1:4723/wd/hub'), options=options)
    artifacts = Path(os.environ.get('DEVICEFARM_LOG_DIR', 'output/devicefarm'))
    artifacts.mkdir(parents=True, exist_ok=True)

    class SnapshotControl:
        def __init__(self, attributes):
            self.attributes = attributes

        def click(self):
            bounds = {key: float(self.attributes[key]) for key in ('x', 'y', 'width', 'height')}
            driver.execute_script('mobile: tap', {
                'x': bounds['x'] + bounds['width'] / 2,
                'y': bounds['y'] + bounds['height'] / 2,
            })

    def matching_elements(label):
        if ios:
            # Grouped RN touchables have reliable snapshot bounds, but Appium's
            # displayed/text lookup can omit them or choose an icon child.
            controls = [node.attrib for node in ET.fromstring(driver.page_source).iter()
                        if node.attrib.get('visible') == 'true'
                        and node.attrib.get('enabled') == 'true'
                        and node.attrib.get('accessible') == 'true'
                        and node.attrib.get('type') in {'XCUIElementTypeOther', 'XCUIElementTypeButton', 'XCUIElementTypeMenuItem'}
                        and node.attrib.get('name', '').split(', ')[-1].casefold() == label.casefold()
                        and float(node.attrib.get('width', 0)) > 0]
            if controls:
                return [SnapshotControl(attributes) for attributes in sorted(
                    controls, key=lambda attributes: float(attributes.get('y', 0)))]
        elements = []
        for value in dict.fromkeys([label, label.upper()]):
            elements.extend(driver.find_elements(AppiumBy.ACCESSIBILITY_ID, value))
            if ios:
                elements.extend(driver.find_elements(AppiumBy.IOS_PREDICATE,
                    'label == ' + json.dumps(value) + ' OR label ENDSWITH ' + json.dumps(', ' + value)))
            else:
                elements.extend(driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
                    'new UiSelector().text(' + json.dumps(value) + ')'))
        visible_elements = [e for e in elements if e.is_displayed() and e.is_enabled()]
        # A heading and action can share a label (for example Create Listing).
        # Prefer the actual accessible button over its non-clickable heading.
        return sorted(visible_elements, key=lambda e: (e.get_attribute('type') != 'XCUIElementTypeButton') if ios else e.get_attribute('clickable') != 'true')

    def matches(label):
        try:
            return matching_elements(label)
        except StaleElementReferenceException:
            # React Native can replace a node between lookup and inspection.
            return []

    def alert_buttons():
        try:
            return driver.execute_script('mobile: alert', {'action': 'getButtons'}) or []
        except WebDriverException:
            return []

    def accept_test_permission():
        if not ios:
            return
        buttons = alert_buttons()
        # Only known permission actions, never the app's photo-source chooser.
        allowed = {'Allow', 'Allow Full Access', 'Allow Access to All Photos', 'OK', 'Open'}
        choice = next((button for button in buttons if button in allowed), None)
        if choice:
            driver.execute_script('mobile: alert', {'action': 'accept', 'buttonLabel': choice})

    def navigate_tab(label, destination, timeout=60):
        if not ios:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                nodes = [node for node in ET.fromstring(driver.page_source).iter()
                         if node.attrib.get('content-desc', '').upper().endswith(', ' + label.upper())
                         and node.attrib.get('enabled') == 'true']
                if nodes:
                    coords = [int(value) for value in re.findall(r'\d+', nodes[-1].attrib['bounds'])]
                    driver.execute_script('mobile: clickGesture', {
                        'x': (coords[0] + coords[2]) // 2,
                        'y': coords[3] - max(1, (coords[3] - coords[1]) // 5),
                    })
                    for _ in range(5):
                        if visible(destination):
                            return
                        time.sleep(1)
                else:
                    time.sleep(1)
            raise AssertionError('Android tab navigation failed: ' + label)
        log_path = artifacts / 'ios-navigation.json'
        events = json.loads(log_path.read_text()) if log_path.exists() else []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            accept_test_permission()
            # React Native groups the icon and text into one accessible node on
            # iOS. Read the actual snapshot and tap its current bounds rather
            # than relying on the driver's text-element hit-point calculation.
            root = ET.fromstring(driver.page_source)
            candidates = [node for node in root.iter()
                          if node.attrib.get('visible') == 'true'
                          and node.attrib.get('enabled') == 'true'
                          and node.attrib.get('name', '').upper().split(', ')[-1] == label.upper()
                          and float(node.attrib.get('width', 0)) > 0]
            events.append({'event': 'lookup', 'tab': label, 'candidate_count': len(candidates)})
            log_path.write_text(json.dumps(events, indent=2))
            if not candidates:
                time.sleep(2)
                continue
            node = max(candidates, key=lambda n: float(n.attrib.get('y', 0)))
            bounds = {key: float(node.attrib[key]) for key in ('x', 'y', 'width', 'height')}
            events.append({'event': 'tap', 'tab': label, 'bounds': bounds})
            log_path.write_text(json.dumps(events, indent=2))
            driver.execute_script('mobile: tap', {
                'x': bounds['x'] + bounds['width'] / 2,
                'y': bounds['y'] + bounds['height'] / 2,
            })
            for _ in range(10):
                if visible(destination):
                    events.append({'event': 'destination_visible', 'destination': destination})
                    log_path.write_text(json.dumps(events, indent=2))
                    driver.save_screenshot(str(artifacts / ('ios-' + label.lower() + '-navigation.png')))
                    return
                time.sleep(1)
            events.append({'event': 'tap_without_destination', 'destination': destination})
            log_path.write_text(json.dumps(events, indent=2))
        raise AssertionError('iOS tab navigation failed; see ios-navigation.json')

    def closet_cards():
        if ios:
            return driver.find_elements(AppiumBy.IOS_PREDICATE, 'name BEGINSWITH "View details for "')
        return driver.find_elements(AppiumBy.XPATH,
            '//*[starts-with(@content-desc,"View details for ")]')

    def text(label, timeout=30, scroll=False):
        def find(d):
            found = matches(label)
            if found:
                return found[0]
            if scroll and ios:
                d.execute_script('mobile: swipe', {'direction': 'up'})
                return False
            if scroll:
                # Python re.escape escapes spaces; use a Java-compatible regex
                # without those escapes for Android's UiScrollable expression.
                pattern = '(?i)' + re.escape(label).replace(r'\ ', ' ')
                selector = 'new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(new UiSelector().textMatches(' + json.dumps(pattern) + '))'
                found = d.find_elements(AppiumBy.ANDROID_UIAUTOMATOR, selector)
                return next((e for e in found if e.is_displayed() and e.is_enabled()), False)
            return False
        return WebDriverWait(driver, timeout).until(find)

    def visible(label):
        return bool(matches(label))

    def screen_texts():
        attribute = 'label' if ios else 'text'
        return [node.attrib[attribute].strip() for node in ET.fromstring(driver.page_source).iter()
                if node.attrib.get(attribute, '').strip()]

    def analysis_summary():
        ready = visible('Edit') and (visible('Publish') or visible('Publish with mannequin image') or visible('Publish without mannequin image'))
        values = screen_texts()
        prices = [float(value.replace(',', '')) for label in values
                  for value in re.findall(r'\$([0-9][0-9,]*(?:\.[0-9]{2})?)', label)]
        text('Description', timeout=10, scroll=True)
        values = screen_texts()
        description = ''
        for index, value in enumerate(values[:-1]):
            if value.lower() == 'description':
                description = values[index + 1]
                break
        return {
            'positive_valuation': any(value > 0 for value in prices),
            'description_present': bool(description and description != 'No description provided.'),
            'ready_for_review': ready,
        }

    def find_mannequin():
        text('Gallery', timeout=10, scroll=True)
        # scrollIntoView only reveals the Gallery heading. The image and AI
        # disclosure underneath can still be clipped below the viewport.
        if not ios:
            size = driver.get_window_size()
            driver.swipe(size['width']//2, int(size['height']*.75),
                         size['width']//2, int(size['height']*.38), 500)
        # At most six originals plus a generated preview. Inspect every page;
        # an extra image alone is not evidence of mannequin generation.
        for _ in range(8):
            values = screen_texts()
            if any(value.startswith('AI-generated styling preview.') for value in values):
                assert 'Image unavailable' not in values, 'Generated mannequin image failed to load'
                return True
            buttons = matches('Next photo')
            if not buttons:
                return False
            buttons[0].click()
            time.sleep(1)
        return False

    def publish_with_image_decision():
        choice = os.environ.get('JOUFT_TEST_MANNEQUIN_CHOICE', 'exclude')
        assert choice in {'include', 'exclude'}, 'Mannequin choice must be include or exclude'
        direct_label = ('Publish with mannequin image' if choice == 'include'
                        else 'Publish without mannequin image')
        option_label = ('Include mannequin image' if choice == 'include'
                        else 'Use original photos only')
        decision = {'requested_choice': choice, 'control_found': False,
                    'publish_clicked': False}
        report = artifacts / 'mannequin-publication-decision.json'
        report.write_text(json.dumps(decision, indent=2))
        # Inspect the complete review screen, including controls below gallery.
        for _ in range(8):
            toggles = matches('Use mannequin image')
            if toggles:
                toggle = toggles[0]
                checked = toggle.get_attribute('checked')
                if checked not in ('true', 'false', True, False):
                    checked = toggle.get_attribute('value')
                assert str(checked).lower() in {'true', 'false', '1', '0'}, 'Cannot determine mannequin toggle state'
                enabled = str(checked).lower() in {'true', '1'}
                if enabled != (choice == 'include'):
                    toggle.click()
                decision.update(control_found=True, control='Use mannequin image')
                report.write_text(json.dumps(decision, indent=2))
                driver.save_screenshot(str(artifacts / 'mannequin-decision.png'))
                text('Publish', scroll=True).click()
                decision['publish_clicked'] = True
                report.write_text(json.dumps(decision, indent=2))
                return
            direct = matches(direct_label)
            if direct:
                decision.update(control_found=True, control=direct_label)
                report.write_text(json.dumps(decision, indent=2))
                driver.save_screenshot(str(artifacts / 'mannequin-decision.png'))
                direct[0].click()
                decision['publish_clicked'] = True
                report.write_text(json.dumps(decision, indent=2))
                return
            options = matches(option_label)
            if options:
                options[0].click()
                decision.update(control_found=True, control=option_label)
                report.write_text(json.dumps(decision, indent=2))
                driver.save_screenshot(str(artifacts / 'mannequin-decision.png'))
                # Only proceed after the explicit choice; never silently use
                # plain Publish when the decision control is absent.
                confirm = matches('Confirm and publish to Marketplace')
                (confirm[0] if confirm else text('Publish', scroll=True)).click()
                decision['publish_clicked'] = True
                report.write_text(json.dumps(decision, indent=2))
                return
            driver.swipe(500, 1500, 500, 650, 500)
            time.sleep(1)
        decision['error'] = 'Review screen has no explicit mannequin include/exclude control'
        report.write_text(json.dumps(decision, indent=2))
        raise AssertionError(decision['error'])

    stage = 'opening login'
    try:
        driver.activate_app(package)
        if ios:
            driver.update_settings({'respectSystemAlerts': True})
        WebDriverWait(driver, 60).until(lambda d: accept_test_permission() or visible('Log In') or d.find_elements(
            AppiumBy.CLASS_NAME, input_class))
        if ios and any(node.attrib.get('name', '').endswith(', PROFILE')
                       for node in ET.fromstring(driver.page_source).iter()):
            stage = 'clearing restored iOS session'
            navigate_tab('Profile', 'SETTINGS')
            text('Sign Out', timeout=60, scroll=True).click()
            text('Log In', timeout=60)
        if visible('Log In'):
            text('Log In').click()
        # iOS keychain sessions can survive app reinstall; reset above. Only the reserved Clerk
        # test-address verification flow below supports unattended verification.
        fields = WebDriverWait(driver, 60).until(
            lambda d: d.find_elements(AppiumBy.CLASS_NAME, input_class) or False)
        if ios:
            fields += driver.find_elements(AppiumBy.CLASS_NAME, 'XCUIElementTypeSecureTextField')
        assert len(fields) >= 2, 'Expected the email/password sign-in screen'
        stage = 'submitting credentials'
        fields[0].send_keys(email)
        fields[1].send_keys(password)
        if driver.is_keyboard_shown():
            text('Jouft Access').click() if ios else driver.hide_keyboard()
        buttons = matches('Sign In') if ios else driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches("(?i)Sign In")')
        assert buttons, 'Sign In button missing'
        buttons[-1].click()
        WebDriverWait(driver, 90).until(lambda d: (accept_test_permission() or visible('Create') or visible('Verify Email')))
        if visible('Verify Email'):
            stage = 'verifying test email'
            # Clerk reserves this fixed OTP for test-mode email aliases only.
            # Never use it against a real email address or a production target.
            assert '+clerk_test@' in email.lower(), 'Email verification requires a Clerk test-mode alias'
            code_fields = [e for e in driver.find_elements(AppiumBy.CLASS_NAME, input_class)
                           if e.is_enabled() and e.is_displayed()]
            assert len(code_fields) == 1, 'Expected one verification-code input'
            code_fields[0].send_keys('424242')
            if driver.is_keyboard_shown():
                text('Jouft Access').click() if ios else driver.hide_keyboard()
            text('Verify Email').click()
        stage = 'reading existing closet'
        navigate_tab('Closet', 'My Closet', timeout=90)
        WebDriverWait(driver, 30).until(lambda d: not d.find_elements(
            AppiumBy.CLASS_NAME, 'XCUIElementTypeActivityIndicator' if ios else 'android.widget.ProgressBar'))
        if existing:
            stage = 'finding existing review listing'
            if not target_title:
                # Scroll through the closet to an actionable review overlay.
                # Analyzing cards use Pending Review but cannot be published.
                selector = ('new UiScrollable(new UiSelector().scrollable(true))'
                            '.setMaxSearchSwipes(30).scrollIntoView(new UiSelector()'
                            '.description("Review and publish listing"))')
                candidates = driver.find_elements(AppiumBy.ACCESSIBILITY_ID,
                                                  'Review and publish listing')
                if not candidates:
                    driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, selector)
                review = text('Review and publish listing', timeout=30)
                # Android's element-scoped XPath does not reliably expose
                # ancestors. Pair the overlay with its underlying image by
                # their shared bounds in the full accessibility snapshot.
                root = ET.fromstring(driver.page_source)
                overlays = [node for node in root.iter()
                            if node.attrib.get('content-desc') == 'Review and publish listing'
                            and node.attrib.get('enabled') == 'true']
                assert overlays, 'Review overlay disappeared'
                bounds = overlays[0].attrib.get('bounds')
                labels = {node.attrib['content-desc'] for node in root.iter()
                          if node.attrib.get('content-desc', '').startswith('View details for ')
                          and node.attrib.get('bounds') == bounds}
                assert len(labels) == 1, 'Cannot identify the selected review card safely'
                target_title = labels.pop().removeprefix('View details for ').strip()
                assert target_title, 'Selected review card has no title'
                (artifacts / 'existing-listing-selection.json').write_text(json.dumps({
                    'selection': 'first actionable review card', 'listing_title': target_title,
                }, indent=2))
            def select_target():
                search = WebDriverWait(driver, 30).until(lambda d: d.find_elements(
                    AppiumBy.ACCESSIBILITY_ID, 'Search my closet') or False)[0]
                search.clear()
                search.send_keys(target_title)
                if driver.is_keyboard_shown():
                    driver.hide_keyboard()
                expected = 'View details for ' + target_title
                def unique_card(d):
                    cards = [card for card in closet_cards()
                             if card.get_attribute('content-desc') == expected]
                    assert len(cards) <= 1, 'Ambiguous listing title; use a unique staging title'
                    return cards[0] if len(cards) == 1 and cards[0].is_enabled() else False
                return WebDriverWait(driver, 60).until(unique_card)

            select_target().click()
            text('Listing Details', timeout=30)
            stage = 'reviewing existing listing'
            summary = analysis_summary()
            assert all(summary.values()), 'Existing listing must have completed analysis and be publishable'
            assert target_title in screen_texts(), 'Opened a different listing'
            driver.save_screenshot(str(artifacts / 'existing-listing-review.png'))
            text('Gallery', timeout=15, scroll=True)
            assert 'Image unavailable' not in screen_texts(), 'Listing gallery failed to load'
            # Reopen to bring review actions back into view after gallery inspection.
            text('Back', timeout=15, scroll=not ios).click()
            text('My Closet', timeout=30)
            select_target().click()
            text('Listing Details', timeout=30)
            assert target_title in screen_texts(), 'Listing changed before publication'
            stage = 'choosing mannequin inclusion and publishing existing listing'
            publish_with_image_decision()
            text('My Closet', timeout=60)
            text('Refresh', timeout=30).click()
            select_target().click()
            text('Marketplace Matches', timeout=60)
            assert not visible('Publish'), 'Existing listing did not persist as Active'
            driver.save_screenshot(str(artifacts / 'existing-listing-publish-success.png'))
            (artifacts / 'existing-listing-publish-checks.json').write_text(json.dumps({
                **summary, 'listing_title': target_title,
                'created_by_test': False, 'published_by_test': True,
                'persisted_active_view': True,
            }, indent=2))
            return
        card_label_attribute = 'name' if ios else 'content-desc'
        existing_card_labels = [c.get_attribute(card_label_attribute) for c in closet_cards()]
        stage = 'opening create listing'
        navigate_tab('Create', 'Add Photos', timeout=90)

        # Seed only these fixture images into the Android gallery. Use a clean
        # managed device: the picker selection below assumes no other photos.
        stage = 'seeding fixture photos'
        if ios:
            # Safari saves fixtures into Photos on a real iPhone; AFC file pushes
            # alone do not register assets in the Photos library.
            urls = json.loads(Path('ios-fixture-urls.json').read_text())
            assert len(urls) == len(photos)
            driver.update_settings({'defaultActiveApplication': 'com.apple.mobilesafari'})
            for url, photo in zip(urls, photos):
                stage = 'loading iOS fixture ' + photo.name
                driver.execute_script('mobile: deepLink', {'url': url, 'bundleId': 'com.apple.mobilesafari'})
                driver.activate_app('com.apple.mobilesafari')
                def fixture_loaded(d):
                    accept_test_permission()
                    root = ET.fromstring(d.page_source)
                    loaded = any(photo.name in node.attrib.get('name', '') for node in root.iter())
                    (artifacts / 'ios-fixture-import.json').write_text(json.dumps({
                        'expected_fixture': photo.name, 'loaded': loaded,
                        'applications': [node.attrib.get('name') for node in root.iter()
                                         if node.attrib.get('type') == 'XCUIElementTypeApplication'],
                    }, indent=2))
                    return loaded
                WebDriverWait(driver, 30).until(fixture_loaded)
                # Use Safari's share sheet: long-press can select Live Text in
                # clothing photos instead of presenting image-save actions.
                stage = 'opening Safari share sheet for ' + photo.name
                text('ShareButton', timeout=15).click()
                stage = 'saving iOS fixture ' + photo.name
                text('Save Image', timeout=30, scroll=True).click()
                time.sleep(2)
                accept_test_permission()
            driver.activate_app(package)
            driver.update_settings({'defaultActiveApplication': 'auto', 'autoAcceptAlerts': False})
            stage = 'opening iOS photo chooser'
            text('Choose Photos', scroll=True).click()
            stage = 'choosing iOS photo library'
            buttons = WebDriverWait(driver, 30).until(lambda d: alert_buttons() or False)
            (artifacts / 'ios-photo-chooser.json').write_text(json.dumps({'buttons': buttons}, indent=2))
            assert 'Photo library' in buttons, 'Expected the listing photo-source chooser'
            driver.execute_script('mobile: alert', {'action': 'accept', 'buttonLabel': 'Photo library'})
            stage = 'reading iOS fixture thumbnails'
            picker_retries = 0
            def ios_thumbnails(d):
                nonlocal picker_retries, stage
                accept_test_permission()
                if visible('Unable to Load Photos'):
                    if picker_retries >= 2:
                        stage = 'iOS system photo picker unavailable after two retries'
                        raise AssertionError('iOS system photo library failed to load')
                    text('Try Again').click()
                    picker_retries += 1
                    time.sleep(3)
                    return False
                return d.find_elements(AppiumBy.IOS_PREDICATE, 'type == "XCUIElementTypeImage" AND name BEGINSWITH "Photo"') or False
            thumbnails = WebDriverWait(driver, 60).until(ios_thumbnails)
            assert len(thumbnails) == len(photos), 'Photos picker must contain only fixture photos'
            for thumbnail in thumbnails:
                bounds = thumbnail.rect
                driver.execute_script('mobile: tap', {'x': bounds['x'] + bounds['width'] / 2, 'y': bounds['y'] + bounds['height'] / 2})
            stage = 'confirming iOS fixture selection'
            text('Add').click()
        else:
            for index, photo in enumerate(photos):
                target = f'/sdcard/Pictures/jouft-e2e-{index}.jpg'
                driver.push_file(target, base64.b64encode(photo.read_bytes()).decode())
                command = ['adb']
                if os.environ.get('DEVICEFARM_DEVICE_UDID'):
                    command += ['-s', os.environ['DEVICEFARM_DEVICE_UDID']]
                subprocess.run(command + ['shell', 'am', 'broadcast', '-a',
                               'android.intent.action.MEDIA_SCANNER_SCAN_FILE', '-d', 'file://' + target],
                               check=True, capture_output=True)
            stage = 'selecting gallery photos'
            text('Choose Photos', scroll=True).click()
            text('Photo library').click()
            thumbnails = WebDriverWait(driver, 30).until(lambda d: android_photo_thumbnails(d) or False)
            assert len(thumbnails) == len(photos), 'Gallery must contain only the supplied fixture views'
            for thumbnail in thumbnails:
                thumbnail.click()
            # Android system picker uses Add (N) or Add on different OS releases.
            WebDriverWait(driver, 15).until(lambda d: next((e for e in d.find_elements(
                AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches("(?i)Add( \\(.*\\))?")')
                if e.is_displayed()), False)).click()
        stage = 'checking photo coverage'
        text('Required photo coverage is complete.', timeout=180, scroll=True)
        text('Continue').click()
        stage = 'entering item basics'
        text('Item Basics')
        text(os.environ.get('JOUFT_TEST_CATEGORY', 'Clothes'), scroll=True).click()
        text('Like New', scroll=True).click()
        text(os.environ.get('JOUFT_TEST_SIZE', 'M'), scroll=True).click()
        stage = 'saving listing'
        text('Create Listing').click()
        # The success notice is transient and can disappear during a re-render.
        # Assert the destination and a newly inserted first card even when the
        # accessibility viewport contains the same number of cards.
        text('My Closet', timeout=180)
        WebDriverWait(driver, 60).until(lambda d: new_listing_card_visible(existing_card_labels,
            [c.get_attribute(card_label_attribute) for c in closet_cards()]))
        driver.save_screenshot(str(artifacts / 'create-listing-success.png'))
        if after_save is not None:
            after_save(driver)
        stage = 'waiting for analysis and mannequin generation'
        timeout = int(os.environ.get('JOUFT_TEST_ANALYSIS_TIMEOUT', '900'))
        assert 60 <= timeout <= 1800, 'Analysis timeout must be between 60 and 1800 seconds'
        deadline = time.monotonic() + timeout
        last_summary = {}
        generated_preview_waits = 0
        while time.monotonic() < deadline:
            # This dedicated account must have only one creating test at a time.
            # The API orders My Closet newest first, so reopen the newly saved
            # first card each poll rather than retaining a stale detail snapshot.
            cards = WebDriverWait(driver, 30).until(lambda d: closet_cards() or False)
            if not cards[0].is_enabled():
                # The row can remain an old snapshot after the creation timers
                # expire; refresh while polling the server-backed closet.
                text('Refresh', timeout=15).click()
                time.sleep(10)
                continue
            label = cards[0].get_attribute('name' if ios else 'content-desc') or ''
            if ios:
                bounds = cards[0].rect
                driver.execute_script('mobile: tap', {'x': bounds['x'] + bounds['width'] / 2, 'y': bounds['y'] + bounds['height'] / 2})
            else:
                cards[0].click()
            text('Listing Details', timeout=30)
            last_summary = analysis_summary()
            title = label.removeprefix('View details for ').strip()
            last_summary['identified_title'] = bool(title and title.lower() not in {'listing', 'new listing'})
            values = screen_texts()
            assert not any('analysis failed' in value.lower() or
                           'unable to complete' in value.lower() for value in values), 'Listing analysis failed'
            if all(last_summary.values()):
                generated_preview_ready = (visible('Use mannequin image') or
                                           (visible('Publish with mannequin image') and visible('Publish without mannequin image')))
                driver.save_screenshot(str(artifacts / 'listing-analysis-success.png'))
                if find_mannequin():
                    driver.save_screenshot(str(artifacts / 'listing-mannequin-success.png'))
                    (artifacts / 'listing-analysis-checks.json').write_text(json.dumps({
                        **last_summary, 'mannequin_visible': True,
                        'published_by_test': False, 'preview_approved_by_test': False,
                    }, indent=2))
                    if publish:
                        # Return to the closet and exercise its actual review CTA,
                        # rather than publishing directly from an already open detail.
                        stage = 'opening Review and Publish'
                        text('Back', timeout=15, scroll=not ios).click()
                        text('My Closet', timeout=30)
                        text('Review and publish listing', timeout=30).click()
                        text('Listing Details', timeout=30)
                        assert title in screen_texts(), 'Review CTA opened a different listing'
                        stage = 'choosing mannequin inclusion and publishing reviewed listing'
                        publish_with_image_decision()
                        text('My Closet', timeout=60)
                        # Re-fetch persisted server state; the notice alone is transient.
                        text('Refresh', timeout=30).click()
                        cards = WebDriverWait(driver, 30).until(lambda d: closet_cards() or False)
                        current_label = cards[0].get_attribute('content-desc') or ''
                        assert current_label == label, 'Newest listing changed during publish test'
                        cards[0].click()
                        # Active closet items open Marketplace Matches, unlike drafts.
                        text('Marketplace Matches', timeout=60)
                        assert not visible('Publish'), 'Published item still offers draft publication'
                        driver.save_screenshot(str(artifacts / 'review-publish-success.png'))
                        (artifacts / 'review-publish-checks.json').write_text(json.dumps({
                            **last_summary, 'mannequin_visible': True,
                            'review_cta_opened': True, 'published_by_test': True,
                            'persisted_active_view': True, 'listing_title': title,
                        }, indent=2))
                    break
                if generated_preview_ready:
                    generated_preview_waits += 1
                    if generated_preview_waits >= 3:
                        (artifacts / 'listing-analysis-checks.json').write_text(json.dumps({
                            **last_summary, 'mannequin_review_controls_ready': True,
                            'mannequin_visible': False, 'ready_preview_polls': generated_preview_waits,
                        }, indent=2))
                        raise AssertionError('Generated preview is ready for review but its gallery disclosure was not found')
            text('Back', timeout=15, scroll=not ios).click()
            text('My Closet', timeout=30)
            # Refresh the existing closet snapshot. Create is a modal without
            # footer tabs, so opening it merely to refresh traps navigation.
            text('Refresh', timeout=30).click()
            time.sleep(10)
        else:
            (artifacts / 'listing-analysis-checks.json').write_text(json.dumps(last_summary, indent=2))
            raise AssertionError('Analysis and visible mannequin preview did not complete before timeout')

    except Exception as exc:
        (artifacts / 'listing-flow-failure.json').write_text(json.dumps({
            'stage': stage, 'error_type': type(exc).__name__,
            'sites': [{'file': Path(e.filename).name, 'function': e.name, 'line': e.lineno}
                      for e in traceback.extract_tb(exc.__traceback__)
                      if Path(e.filename).name in {'test_create_listing.py', 'android_ui.py'}],
        }, indent=2))
        # Never record the authentication screen/password in failure artifacts.
        if driver.find_elements(AppiumBy.XPATH, '//*[@type="XCUIElementTypeSecureTextField"]' if ios else '//*[@password="true"]'):
            pytest.fail(f'Test stopped while {stage}; sensitive screen capture suppressed ({type(exc).__name__})', pytrace=False)
        driver.save_screenshot(str(artifacts / 'create-listing-failure.png'))
        (artifacts / 'create-listing-failure.xml').write_text(driver.page_source)
        pytest.fail(f'Test stopped while {stage} ({type(exc).__name__}); see failure artifacts', pytrace=False)
    finally:
        driver.quit()


def test_create_listing():
    run_listing_flow()
