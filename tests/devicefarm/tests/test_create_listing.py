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

    def text(label, timeout=30, scroll=False):
        selector = 'new UiSelector().textMatches(' + json.dumps('(?i)' + re.escape(label)) + ')'
        if scroll:
            selector = 'new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(' + selector + ')'
        return WebDriverWait(driver, timeout).until(
            lambda d: next((e for e in (d.find_elements(AppiumBy.ACCESSIBILITY_ID, label.upper())
                            + d.find_elements(AppiumBy.ACCESSIBILITY_ID, label)
                            + d.find_elements(AppiumBy.ANDROID_UIAUTOMATOR, selector))
                            if e.is_displayed() and e.is_enabled()), False))

    def visible(label):
        return any(e.is_displayed() for e in (
            driver.find_elements(AppiumBy.ACCESSIBILITY_ID, label.upper())
            + driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiSelector().textMatches(' + json.dumps('(?i)' + re.escape(label)) + ')')))

    try:
        driver.activate_app(package)
        WebDriverWait(driver, 60).until(lambda d: visible('Log In') or d.find_elements(
            AppiumBy.CLASS_NAME, 'android.widget.EditText'))
        if visible('Log In'):
            text('Log In').click()
        # A new Device Farm device starts signed out. MFA/verification challenges
        # intentionally fail instead of bypassing authentication.
        fields = WebDriverWait(driver, 60).until(
            lambda d: d.find_elements(AppiumBy.CLASS_NAME, 'android.widget.EditText') or False)
        assert len(fields) >= 2, 'Expected the email/password sign-in screen'
        fields[0].send_keys(email)
        fields[1].send_keys(password)
        if driver.is_keyboard_shown():
            driver.hide_keyboard()
        buttons = driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches("(?i)Sign In")')
        assert buttons, 'Sign In button missing'
        buttons[-1].click()
        WebDriverWait(driver, 90).until(lambda d: visible('Create') or visible('Verify Email'))
        if visible('Verify Email'):
            pytest.fail('Staging sign-in requires an emailed verification code; unattended test-account authentication must be configured', pytrace=False)
        text('Create', timeout=90).click()
        text('Add Photos')

        # Seed only these fixture images into the Android gallery. Use a clean
        # managed device: the picker selection below assumes no other photos.
        for index, photo in enumerate(photos):
            target = f'/sdcard/Pictures/jouft-e2e-{index}.jpg'
            driver.push_file(target, base64.b64encode(photo.read_bytes()).decode())
            command = ['adb']
            if os.environ.get('DEVICEFARM_DEVICE_UDID'):
                command += ['-s', os.environ['DEVICEFARM_DEVICE_UDID']]
            subprocess.run(command + ['shell', 'am', 'broadcast', '-a',
                           'android.intent.action.MEDIA_SCANNER_SCAN_FILE', '-d', 'file://' + target],
                           check=True, capture_output=True)
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
        text('Required photo coverage is complete.', timeout=180, scroll=True)
        text('Continue').click()
        text('Item Basics')
        text(os.environ.get('JOUFT_TEST_CATEGORY', 'Clothes'), scroll=True).click()
        text('Like New', scroll=True).click()
        text(os.environ.get('JOUFT_TEST_SIZE', 'M'), scroll=True).click()
        text('Create Listing').click()
        text('Listing created. AI analysis is running in the background.', timeout=180)
        text('My Closet')
        driver.save_screenshot(str(artifacts / 'create-listing-success.png'))
    except Exception:
        # Never record the authentication screen/password in failure artifacts.
        if driver.find_elements(AppiumBy.XPATH, '//*[@password="true"]'):
            pytest.fail('Authentication did not complete; sensitive screen capture suppressed', pytrace=False)
        driver.save_screenshot(str(artifacts / 'create-listing-failure.png'))
        (artifacts / 'create-listing-failure.xml').write_text(driver.page_source)
        raise
    finally:
        driver.quit()
