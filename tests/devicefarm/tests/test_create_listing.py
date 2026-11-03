"""Real Android UI test: sign in, select photos, save a listing to the closet."""

import base64
import json
import os
import re
from pathlib import Path
import subprocess

import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import StaleElementReferenceException


def test_create_listing():
    # Require explicit staging confirmation: this test creates a real saved listing.
    assert os.environ.get('JOUFT_TEST_TARGET') == 'staging', 'Set JOUFT_TEST_TARGET=staging'
    email = os.environ['JOUFT_TEST_EMAIL']
    password = os.environ['JOUFT_TEST_PASSWORD']
    photos = sorted(Path(os.environ['JOUFT_TEST_PHOTOS']).glob('*.jpg'))
    assert 1 <= len(photos) <= 6, 'Supply 1–6 JPG views of one item, including required coverage'
    package = os.environ.get('DEVICEFARM_APP_PACKAGE', 'com.jouft.app.dev')
    assert package == 'com.jouft.app.dev', 'Only the testing app identity is supported'
    options = UiAutomator2Options().load_capabilities({
        'platformName': 'Android', 'appium:automationName': 'UiAutomator2',
        'appium:deviceName': os.environ.get('DEVICEFARM_DEVICE_NAME', 'Android'),
        'appium:udid': os.environ.get('DEVICEFARM_DEVICE_UDID'),
        'appium:appPackage': package, 'appium:autoGrantPermissions': True,
        'appium:newCommandTimeout': 180,
    })
    if os.environ.get('DEVICEFARM_APP_PATH'):
        options.set_capability('appium:app', os.environ['DEVICEFARM_APP_PATH'])
    driver = webdriver.Remote(os.environ.get('APPIUM_SERVER_URL', 'http://127.0.0.1:4723/wd/hub'), options=options)
    artifacts = Path(os.environ.get('DEVICEFARM_LOG_DIR', 'output/devicefarm'))
    artifacts.mkdir(parents=True, exist_ok=True)

    def matching_elements(label):
        elements = []
        for value in dict.fromkeys([label, label.upper()]):
            elements.extend(driver.find_elements(AppiumBy.ACCESSIBILITY_ID, value))
            elements.extend(driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiSelector().text(' + json.dumps(value) + ')'))
        visible_elements = [e for e in elements if e.is_displayed() and e.is_enabled()]
        # A heading and action can share a label (for example Create Listing).
        # Prefer the actual accessible button over its non-clickable heading.
        return sorted(visible_elements, key=lambda e: e.get_attribute('clickable') != 'true')

    def matches(label):
        try:
            return matching_elements(label)
        except StaleElementReferenceException:
            # React Native can replace a node between lookup and inspection.
            return []

    def closet_cards():
        return driver.find_elements(AppiumBy.XPATH,
            '//*[starts-with(@content-desc,"View details for ")]')

    def text(label, timeout=30, scroll=False):
        def find(d):
            found = matches(label)
            if found:
                return found[0]
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

    stage = 'opening login'
    try:
        driver.activate_app(package)
        WebDriverWait(driver, 60).until(lambda d: visible('Log In') or d.find_elements(
            AppiumBy.CLASS_NAME, 'android.widget.EditText'))
        if visible('Log In'):
            text('Log In').click()
        # A new Device Farm device starts signed out. Only the reserved Clerk
        # test-address verification flow below supports unattended verification.
        fields = WebDriverWait(driver, 60).until(
            lambda d: d.find_elements(AppiumBy.CLASS_NAME, 'android.widget.EditText') or False)
        assert len(fields) >= 2, 'Expected the email/password sign-in screen'
        stage = 'submitting credentials'
        fields[0].send_keys(email)
        fields[1].send_keys(password)
        if driver.is_keyboard_shown():
            driver.hide_keyboard()
        buttons = driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches("(?i)Sign In")')
        assert buttons, 'Sign In button missing'
        buttons[-1].click()
        WebDriverWait(driver, 90).until(lambda d: visible('Create') or visible('Verify Email'))
        if visible('Verify Email'):
            stage = 'verifying test email'
            # Clerk reserves this fixed OTP for test-mode email aliases only.
            # Never use it against a real email address or a production target.
            assert '+clerk_test@' in email.lower(), 'Email verification requires a Clerk test-mode alias'
            code_fields = [e for e in driver.find_elements(AppiumBy.CLASS_NAME, 'android.widget.EditText')
                           if e.is_enabled() and e.is_displayed()]
            assert len(code_fields) == 1, 'Expected one verification-code input'
            code_fields[0].send_keys('424242')
            if driver.is_keyboard_shown():
                driver.hide_keyboard()
            text('Verify Email').click()
        stage = 'reading existing closet'
        text('Closet', timeout=90).click()
        text('My Closet')
        WebDriverWait(driver, 30).until(lambda d: not d.find_elements(
            AppiumBy.CLASS_NAME, 'android.widget.ProgressBar'))
        existing_card_count = len(closet_cards())
        stage = 'opening create listing'
        text('Create', timeout=90).click()
        text('Add Photos')

        # Seed only these fixture images into the Android gallery. Use a clean
        # managed device: the picker selection below assumes no other photos.
        stage = 'seeding fixture photos'
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
        thumbnails = WebDriverWait(driver, 30).until(lambda d: d.find_elements(
            AppiumBy.XPATH, '//*[contains(@resource-id,"icon_thumbnail")]') or False)
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
        # Assert the persistent destination and an additional saved listing card.
        text('My Closet', timeout=180)
        WebDriverWait(driver, 30).until(lambda d: len(closet_cards()) > existing_card_count)
        driver.save_screenshot(str(artifacts / 'create-listing-success.png'))
    except Exception as exc:
        # Never record the authentication screen/password in failure artifacts.
        if driver.find_elements(AppiumBy.XPATH, '//*[@password="true"]'):
            pytest.fail(f'Test stopped while {stage}; sensitive screen capture suppressed ({type(exc).__name__})', pytrace=False)
        driver.save_screenshot(str(artifacts / 'create-listing-failure.png'))
        (artifacts / 'create-listing-failure.xml').write_text(driver.page_source)
        pytest.fail(f'Test stopped while {stage} ({type(exc).__name__}); see failure artifacts', pytrace=False)
    finally:
        driver.quit()
