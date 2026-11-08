"""Android UI helpers; no credentials or raw auth payloads in artifacts."""
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait


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
        self.driver.activate_app(self.package)

    def nodes(self):
        return list(ET.fromstring(self.driver.page_source).iter())

    def values(self):
        return {n.attrib.get(k, '') for n in self.nodes() for k in ['text', 'content-desc']}

    def elements(self, label):
        result = self.driver.find_elements(AppiumBy.ACCESSIBILITY_ID, label)
        for value in dict.fromkeys([label, label.upper()]):
            result += self.driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiSelector().text(' + json.dumps(value) + ')')
        return [x for x in result if x.is_displayed() and x.is_enabled()]

    def has(self, label):
        return label in self.values() or label.upper() in self.values()

    def wait(self, label, timeout=30):
        WebDriverWait(self.driver, timeout).until(lambda _: self.has(label))

    def tap(self, label, scroll=False):
        if scroll and not self.elements(label):
            selector = ('new UiScrollable(new UiSelector().scrollable(true)).setMaxSearchSwipes(15)'
                        '.scrollIntoView(new UiSelector().textMatches(' +
                        json.dumps('(?i)' + re.escape(label).replace(r'\ ', ' ')) + '))')
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
        for _ in range(8):
            nodes = [n for n in self.nodes() if n.attrib.get('content-desc', '').upper().endswith(', ' + name.upper())]
            if nodes:
                c = list(map(int, re.findall(r'\d+', nodes[-1].attrib['bounds'])))
                self.driver.execute_script('mobile: clickGesture', {'x': (c[0]+c[2])//2, 'y': (c[1]+c[3])//2})
                try:
                    self.wait(destination, 5)
                    return
                except Exception:
                    pass
            time.sleep(1)
        raise AssertionError('Tab navigation failed: ' + name)

    def login(self, email, password):
        WebDriverWait(self.driver, 60).until(lambda _: self.has('Log In') or self.driver.find_elements(
            AppiumBy.CLASS_NAME, 'android.widget.EditText') or any(
                n.attrib.get('content-desc', '').endswith(', PROFILE') for n in self.nodes()))
        if any(n.attrib.get('content-desc', '').endswith(', PROFILE') for n in self.nodes()):
            self.logout()
        if self.has('Log In'):
            self.tap('Log In')
        fields = WebDriverWait(self.driver, 30).until(lambda _: self.driver.find_elements(
            AppiumBy.CLASS_NAME, 'android.widget.EditText'))
        assert len(fields) >= 2
        fields[0].clear(); fields[0].send_keys(email)
        fields[1].send_keys(password)
        self.keyboard_down()
        self.elements('Sign In')[-1].click()
        WebDriverWait(self.driver, 90).until(lambda _: self.has('Verify Email') or any(
            n.attrib.get('content-desc', '').endswith(', PROFILE') for n in self.nodes()))
        if self.has('Verify Email'):
            assert '+clerk_test@' in email.lower()
            fields = self.driver.find_elements(AppiumBy.CLASS_NAME, 'android.widget.EditText')
            assert len(fields) == 1
            fields[0].send_keys('424242'); self.keyboard_down(); self.tap('Verify Email')
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
        assert len(self.elements(label)) == 1, 'Listing fixture title must be unique'
        self.tap(label)
        self.wait('Listing Details')
        self.wait(title)

    def capture(self, destination):
        # Do not retain auth, Stripe or other credential-entry screens.
        sensitive = self.driver.find_elements(AppiumBy.XPATH, '//*[@password="true"]')
        if sensitive or not any(n.attrib.get('content-desc', '').endswith(', PROFILE') for n in self.nodes()):
            return False
        self.driver.save_screenshot(str(destination))
        return True
