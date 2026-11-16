"""Android UI helpers; no credentials or raw auth payloads in artifacts."""
import json
import os
import re

import pytest
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait


def verification_code(email, requested_at):
    if '+clerk_test@' in email.lower():
        return '424242'
    # A real second-account email must use its actual freshly delivered code.
    # An inbox bridge or QA operator can update this narrow host secret. Never
    # reuse Clerk's test code for the real email selected by the release owner.
    secret = os.environ.get('JOUFT_TEST_SECOND_OTP_SECRET' if email.casefold() ==
        os.environ.get('JOUFT_TEST_SECOND_EMAIL', '').casefold() else 'JOUFT_TEST_OTP_SECRET')
    if not secret:
        pytest.skip('Blocked: real-email sign-in needs a configured OTP inbox bridge')
    import boto3
    client = boto3.client('secretsmanager', region_name='us-west-2')
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            code = json.loads(client.get_secret_value(SecretId=secret)['SecretString'])
            fresh = float(code.get('issued_at', 0)) >= requested_at
            if fresh and code.get('email', '').casefold() == email.casefold() and re.fullmatch(r'\d{6}', str(code.get('code', ''))):
                return str(code['code'])
        except Exception:
            pytest.skip('Blocked: OTP inbox bridge is unavailable')
        time.sleep(3)
    pytest.skip('Blocked: fresh account-specific email verification code was not delivered')


def unique_listing_card(elements):
    # Marketplace cards expose both an outer pressable and its nested image
    # with the same label. They are one listing; separate card rectangles are
    # still ambiguous and must not be selected silently.
    by_rect = {}
    for element in elements:
        r = element.rect
        if r['width'] > 0 and r['height'] > 0:
            by_rect[(r['x'], r['y'], r['width'], r['height'])] = element
    def contains(outer, inner):
        x, y, w, h = outer; a, b, c, d = inner
        return x <= a and y <= b and x+w >= a+c and y+h >= b+d
    outermost = [r for r in by_rect if not any(o != r and contains(o, r) for o in by_rect)]
    assert len(outermost) == 1, 'Listing fixture title must identify one visible card'
    return by_rect[min(by_rect, key=lambda r: r[2]*r[3])]


class AndroidUI:
    def __init__(self):
        assert os.environ.get('JOUFT_TEST_TARGET') == 'staging'
        assert os.environ.get('JOUFT_TEST_PLATFORM', 'Android').lower() == 'android'
        self.package = os.environ.get('DEVICEFARM_APP_PACKAGE', 'com.jouft.app.dev')
        assert self.package == 'com.jouft.app.dev'
        caps = {'platformName': 'Android', 'appium:automationName': 'UiAutomator2',
                'appium:udid': os.environ.get('DEVICEFARM_DEVICE_UDID'),
                'appium:appPackage': self.package, 'appium:autoGrantPermissions': True,
                'appium:newCommandTimeout': 180}
        if os.environ.get('DEVICEFARM_APP_PATH'):
            caps['appium:app'] = os.environ['DEVICEFARM_APP_PATH']
        self.driver = webdriver.Remote(os.environ.get('APPIUM_SERVER_URL',
            'http://127.0.0.1:4723/wd/hub'), options=UiAutomator2Options().load_capabilities(caps))
        # UiAutomator2's XPath 2 engine crashes on following-axis queries on
        # this pinned Android 15 host. XPath 1 supports our field associations.
        self.driver.update_settings({'enforceXPath1': True})
        self.driver.activate_app(self.package)

    def nodes(self):
        return list(ET.fromstring(self.driver.page_source).iter())

    def values(self):
        return {n.attrib.get(k, '') for n in self.nodes() for k in ['text', 'content-desc']}

    def elements(self, label):
        result = self.driver.find_elements(AppiumBy.ACCESSIBILITY_ID, label)
        for value in dict.fromkeys([label, label.upper()]):
            result += self.driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiSelector().text(' + json.dumps(value, ensure_ascii=False) + ')')
        return [x for x in result if x.is_displayed() and x.is_enabled()]

    def has(self, label):
        return label in self.values() or label.upper() in self.values()

    def wait(self, label, timeout=30):
        WebDriverWait(self.driver, timeout).until(lambda _: self.has(label))

    def tap(self, label, scroll=False):
        if scroll and not self.elements(label):
            selector = ('new UiScrollable(new UiSelector().scrollable(true)).setMaxSearchSwipes(15)'
                        '.scrollIntoView(new UiSelector().textMatches(' +
                        json.dumps('(?i)' + re.escape(label).replace(r'\ ', ' '), ensure_ascii=False) + '))')
            self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, selector)
        element = WebDriverWait(self.driver, 30).until(lambda _: next(iter(self.elements(label)), False))
        element.click()

    def keyboard_down(self):
        if self.driver.is_keyboard_shown():
            self.driver.hide_keyboard()

    def input(self, label, value):
        field = WebDriverWait(self.driver, 30).until(lambda _: next(iter(self.elements(label)), False))
        field.clear()
        field.send_keys(value)
        self.keyboard_down()

    def tab(self, name, destination):
        # Create is a modal without the footer; navigating to its current
        # destination must not require a tab that is hidden by that modal.
        if self.has(destination):
            return
        # Tap the visible text near the tab's bottom. On staging Android 4 the
        # assistant overlaps Profile's upper portion (tracked separately); do
        # not mistake that product defect for failure of every Profile check.
        self.keyboard_down()
        if name.casefold() == 'profile' and self.driver.find_elements(
                AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().scrollable(true)'):
            # Onboarding can keep the Profile route and its old scroll position
            # when a tab press is redirected to the next required section.
            self.driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiScrollable(new UiSelector().scrollable(true)).scrollToBeginning(10)')
            if self.has(destination):
                return
        for _ in range(8):
            nodes = [n for n in self.nodes() if n.attrib.get('content-desc', '').upper().endswith(', ' + name.upper())]
            if nodes:
                c = list(map(int, re.findall(r'\d+', nodes[-1].attrib['bounds'])))
                self.driver.execute_script('mobile: clickGesture', {'x': (c[0]+c[2])//2, 'y': c[3] - max(1, (c[3]-c[1])//5)})
                try:
                    self.wait(destination, 5)
                    return
                except Exception:
                    pass
            time.sleep(1)
        raise AssertionError('Tab navigation failed: ' + name)

    def show_gallery(self):
        self.tap('Gallery', scroll=True)
        # Revealing the heading alone leaves the image footer/disclosure clipped.
        size = self.driver.get_window_size()
        self.driver.swipe(size['width']//2, int(size['height']*.75),
                          size['width']//2, int(size['height']*.38), 500)

    def editable_fields(self):
        # The verification screen retains a disabled email EditText above its
        # code input. Counting it as an editable field breaks every login.
        return [field for field in self.driver.find_elements(AppiumBy.CLASS_NAME, 'android.widget.EditText')
                if field.is_enabled() and field.is_displayed()]

    def wait_editable_fields(self, minimum=2):
        def ready(_):
            fields = self.editable_fields()
            return fields if len(fields) >= minimum else False
        return WebDriverWait(self.driver, 30).until(ready)

    def login(self, email, password):
        WebDriverWait(self.driver, 60).until(lambda _: self.has('Log In') or self.driver.find_elements(
            AppiumBy.CLASS_NAME, 'android.widget.EditText') or any(
                n.attrib.get('content-desc', '').endswith(', PROFILE') for n in self.nodes()))
        if any(n.attrib.get('content-desc', '').endswith(', PROFILE') for n in self.nodes()):
            self.logout()
        if self.has('Log In'):
            self.tap('Log In')
        fields = self.wait_editable_fields()
        assert len(fields) >= 2
        fields[0].clear(); fields[0].send_keys(email)
        fields[1].send_keys(password)
        self.keyboard_down()
        requested_at = time.time()
        self.elements('Sign In')[-1].click()
        WebDriverWait(self.driver, 90).until(lambda _: self.has('Verify Email') or any(
            n.attrib.get('content-desc', '').endswith(', PROFILE') for n in self.nodes()))
        if self.has('Verify Email'):
            code = verification_code(email, requested_at)
            fields = self.wait_editable_fields(1)
            assert len(fields) == 1, 'Expected one enabled verification-code field'
            fields[0].send_keys(code); self.keyboard_down(); self.tap('Verify Email')
        self.tab('Closet', 'My Closet')

    def logout(self):
        self.tab('Profile', 'SETTINGS')
        self.tap('Sign Out', scroll=True)
        self.wait('Log In', 60)

    def search(self, area, query):
        tab, heading, field = {'closet': ('Closet', 'My Closet', 'Search my closet'),
                              'marketplace': ('Market', 'Marketplace', 'Search marketplace')}[area]
        self.tab(tab, heading)
        self.input(field, query)

    def card_titles(self):
        return [n.attrib['content-desc'].removeprefix('View details for ') for n in self.nodes()
                if n.attrib.get('content-desc', '').startswith('View details for ')]

    def open_listing(self, area, title):
        self.search(area, title)
        label = 'View details for ' + title
        self.wait(label, 60)
        unique_listing_card(self.elements(label)).click()
        self.wait('Listing Details')
        self.wait(title)

    def capture(self, destination):
        # Do not retain auth, Stripe or other credential-entry screens.
        sensitive = self.driver.find_elements(AppiumBy.XPATH, '//*[@password="true"]')
        if sensitive or not any(n.attrib.get('content-desc', '').endswith(', PROFILE') for n in self.nodes()):
            return False
        self.driver.save_screenshot(str(destination))
        return True


def android_photo_thumbnails(driver):
    """Legacy Views and Android's Compose Photo Picker expose different nodes."""
    legacy = driver.find_elements(AppiumBy.XPATH, '//*[contains(@resource-id,"icon_thumbnail")]')
    if legacy:
        return legacy
    # Scope to the system photo picker; never select arbitrary app images.
    if driver.current_package not in {'com.google.android.providers.media.module',
                                      'com.android.providers.media.module',
                                      'com.google.android.photopicker', 'com.android.photopicker'}:
        return []
    return driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().descriptionStartsWith("Photo taken on ")')
