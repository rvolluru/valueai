"""Bounded Android/HTTP operations for staging workflow acceptance tests.

HTTP is used for independent persistence/side-effect assertions, controlled race
injection, and restoration. The business actions under test use the native UI.
No request bodies, bearer tokens, page sources or credential screens are retained.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

PROFILE_FIELDS = set('first_name last_name email gender birthday tops_size dresses_size bottoms_size shoes_size category_preferences style_descriptors jouft_goals shipping_full_name shipping_address_line1 shipping_address_line2 shipping_city shipping_state shipping_postal_code shipping_country shipping_email shipping_phone shipping_addresses subscription_plan subscription_billing_cycle subscription_status subscription_renewal_date payment_methods'.split())


def blocked(message):
    pytest.skip('Blocked: ' + message)


def need(mapping, *keys):
    for key in keys:
        if key not in mapping or mapping[key] is None or mapping[key] == '':
            blocked('missing workflow fixture field ' + key)
    return mapping


def verify_staging_apk(manifest, apk_path):
    """The .dev identifier alone is insufficient: it can point at production."""
    need(manifest, 'environment', 'reviewed_by', 'verified_build', 'apk_sha256', 'api_origin')
    assert manifest['environment'] == 'staging'
    origin = urllib.parse.urlsplit(manifest['api_origin'])
    assert origin.scheme == 'https' and origin.hostname == 'staging.jouft.com'
    assert not origin.username and not origin.password and not origin.query and not origin.fragment
    assert origin.path in {'', '/'}
    if not apk_path or not Path(apk_path).is_file():
        blocked('verified staging APK is required on the test host')
    path = Path(apk_path)
    exact_apk = hashlib.sha256(path.read_bytes()).hexdigest() == manifest['apk_sha256']
    with zipfile.ZipFile(path) as archive:
        config_bytes = archive.read('assets/app.config')
        if not exact_apk:
            # Public Device Farm devices re-sign APKs. Permit that container
            # change only on a Device Farm host with the reviewed original JS
            # bundle AND embedded Expo configuration still byte-for-byte equal.
            assert os.environ.get('DEVICEFARM_RUN_ARN', '').startswith('arn:aws:devicefarm:'), 'APK digest mismatch'
            need(manifest, 'config_sha256', 'js_bundle_sha256')
            assert hashlib.sha256(config_bytes).hexdigest() == manifest['config_sha256'], 'APK config digest mismatch'
            assert hashlib.sha256(archive.read('assets/index.android.bundle')).hexdigest() == manifest['js_bundle_sha256'], 'APK code digest mismatch'
        config = json.loads(config_bytes)
    assert config['extra']['appEnvironment'] == 'staging', 'Workflow mutations require a staging APK'
    assert config['extra']['apiBaseUrl'].rstrip('/') == manifest['api_origin'].rstrip('/')
    assert config['android']['package'] == 'com.jouft.app.dev'


class API:
    def __init__(self, origin, account='A', subject=None):
        self.origin = origin.rstrip('/')
        assert self.origin == 'https://staging.jouft.com'
        self.account, self.subject = account, subject
        self._cached = None

    def token(self):
        if self._cached and self._cached[1] > time.time() + 15:
            return self._cached[0]
        token = os.environ.get('JOUFT_TEST_API_TOKEN_' + self.account)
        session = os.environ.get('JOUFT_TEST_CLERK_SESSION_' + self.account)
        secret = os.environ.get('JOUFT_TEST_CLERK_SECRET')
        if session and secret:
            assert secret.startswith('sk_test_'), 'Observer renewal only accepts a Clerk test instance'
            assert re.fullmatch(r'sess_[A-Za-z0-9]+', session) and self.subject
            def clerk(method, suffix):
                request = urllib.request.Request('https://api.clerk.com/v1/sessions/' + session + suffix,
                    data=b'{}' if method == 'POST' else None,
                    headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'}, method=method)
                class NoRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, req, fp, code, msg, headers, newurl):
                        return None
                try:
                    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
                        return json.load(response)
                except Exception:
                    raise AssertionError('Clerk observer renewal failed; no response body retained') from None
            record = clerk('GET', '')
            assert record['user_id'] == self.subject and record['status'] == 'active', 'Observer session account mismatch'
            token = clerk('POST', '/tokens')['jwt']
        if not token:
            blocked('missing staging observer authentication for account ' + self.account)
        try:
            payload = token.split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        except Exception:
            raise AssertionError('Observer token is not a session JWT') from None
        assert self.subject and claims.get('sub') == self.subject, 'Observer token account mismatch'
        if claims.get('exp', 0) <= time.time() + 5:
            blocked('observer token expired; configure renewable Clerk test sessions')
        self._cached = (token, claims['exp'])
        return token

    def call(self, method, path, data=None, allowed=(200,)):
        assert path.startswith('/v1/') and not path.startswith('//')
        token = self.token()
        request = urllib.request.Request(self.origin + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, method=method)
        try:
            # Refuse redirects so Authorization can never be forwarded elsewhere.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None
            with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        except Exception:
            raise AssertionError('Staging observer connection failed') from None
        if status in {401, 403}:
            blocked('staging observer token expired or lacks account access')
        assert status in allowed, 'Staging observer HTTP status ' + str(status)
        return json.loads(raw) if raw else {}

    def get(self, path):
        return self.call('GET', path)

    def assert_identity(self, expected_email):
        identity = self.get('/v1/auth/me')
        assert identity['user_id'] == self.subject
        if identity.get('email'):
            assert identity['email'].casefold() == expected_email.casefold(), 'Observer and UI accounts differ'
            return
        # Profile email is editable and cannot prove the Clerk login identity.
        secret = os.environ.get('JOUFT_TEST_CLERK_SECRET', '')
        if not secret:
            blocked('observer JWT needs an email claim or Clerk test-instance identity lookup')
        assert secret.startswith('sk_test_') and re.fullmatch(r'user_[A-Za-z0-9]+', self.subject)
        request = urllib.request.Request('https://api.clerk.com/v1/users/' + self.subject,
            headers={'Authorization': 'Bearer ' + secret})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
                user = json.load(response)
        except Exception:
            raise AssertionError('Observer login identity lookup failed') from None
        emails = {entry['email_address'].casefold() for entry in user['email_addresses']
                  if (entry.get('verification') or {}).get('status') == 'verified'}
        assert user['id'] == self.subject and expected_email.casefold() in emails, 'Observer and UI accounts differ'

    def profile(self):
        return self.get('/v1/me/profile-quiz')

    def listing(self, title, mine=True):
        rows = self.get('/v1/listings?limit=100&mine=' + str(mine).lower() + '&q=' + urllib.parse.quote(title))['items']
        found = [row for row in rows if row['title'] == title]
        assert len(found) <= 1, 'Fixture titles must be unique'
        return found[0] if found else None

    def offers(self):
        return self.get('/v1/offers/incoming?status=all&limit=100')['items']

    def offer(self, offer_id):
        rows = [row for row in self.offers() if row['offer_id'] == offer_id]
        assert len(rows) == 1, 'Controlled offer missing'
        return rows[0]


def eventually(check, timeout=60):
    end = time.monotonic() + timeout
    while True:
        value = check()
        if value:
            return value
        assert time.monotonic() < end, 'Expected persisted state was not observed'
        time.sleep(1)


class Controls:
    """Resolve visible field labels and card actions without positional indexes."""
    def __init__(self, app):
        self.app, self.driver = app, app.driver

    def scroll_to(self, label):
        if not self.app.elements(label):
            self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiScrollable(new UiSelector().scrollable(true)).setMaxSearchSwipes(18)'
                '.scrollIntoView(new UiSelector().textMatches(' + json.dumps('(?i)' + re.escape(label), ensure_ascii=False) + '))')

    def field(self, label):
        # Android element-scoped XPath does not reliably expose ancestors.
        # Resolve RN sibling labels from the complete hierarchy instead.
        aliases = {'Expiration date': ['MM / YY', 'MM/YY'], 'CVC': ['Security code', 'CVV'],
                   'ZIP': ['ZIP Code', 'Postal code']}.get(label, [])
        upper = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        lower = 'abcdefghijklmnopqrstuvwxyz'
        def find(_):
            candidates = []
            for value in [label, *aliases]:
                literal = json.dumps(value, ensure_ascii=False)
                candidates += self.driver.find_elements(AppiumBy.XPATH,
                    '//android.widget.EditText[@hint=' + literal + ' or @content-desc=' + literal + ']')
            literal = json.dumps(label.upper(), ensure_ascii=False)
            candidates += self.driver.find_elements(AppiumBy.XPATH,
                '//*[@class="android.widget.TextView" and (translate(@text,"' + lower + '","' + upper + '")=' + literal +
                ' or translate(@content-desc,"' + lower + '","' + upper + '")=' + literal +
                ')]/following::android.widget.EditText[1]')
            visible = {f.id: f for f in candidates if f.is_displayed() and f.is_enabled()}
            assert len(visible) <= 1, 'Ambiguous editable field associated with ' + label
            return next(iter(visible.values()), False)
        try:
            return WebDriverWait(self.driver, 5).until(find)
        except TimeoutException:
            self.scroll_to(label)
            return WebDriverWait(self.driver, 30).until(find)

    def input(self, label, value):
        field = self.field(label)
        field.clear(); field.send_keys(value); self.app.keyboard_down()

    def read(self, label):
        return self.field(label).text

    def scoped(self, title, button):
        self.scroll_to(title)
        anchors = [e for e in self.app.elements(title) if e.get_attribute('className') != 'android.widget.EditText']
        assert len(anchors) == 1, 'Fixture anchor must be unique'
        parent = anchors[0]
        for _ in range(7):
            parent = parent.find_element(AppiumBy.XPATH, '..')
            matches = parent.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiSelector().textMatches(' + json.dumps('(?i)' + re.escape(button), ensure_ascii=False) + ')')
            matches = [e for e in matches if e.is_displayed() and e.is_enabled()]
            if len(matches) == 1:
                matches[0].click(); return
            assert len(matches) <= 1, 'Ambiguous fixture card action'
        raise AssertionError('No scoped card action ' + button)

    def section_button(self, heading, label):
        self.scroll_to(heading)
        anchors = self.app.elements(heading)
        assert len(anchors) == 1
        # Size groups are RN sibling label/row views, not card containers.
        row = anchors[0].find_element(AppiumBy.XPATH, 'following-sibling::*[1]')
        options = row.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
            'new UiSelector().text(' + json.dumps(label, ensure_ascii=False) + ')')
        options = [e for e in options if e.is_displayed() and e.is_enabled()]
        assert len(options) == 1, 'No unique option in the requested preference section'
        options[0].click()

    def click_parent(self, label):
        self.scroll_to(label)
        elements = self.app.elements(label)
        assert len(elements) == 1, 'Fixture label must be unique'
        parent = elements[0]
        for _ in range(8):
            if parent.get_attribute('clickable') == 'true':
                parent.click(); return
            parent = parent.find_element(AppiumBy.XPATH, '..')
        raise AssertionError('No actionable parent for fixture')

    def alert(self, title, action):
        self.app.wait(title)
        # Native dialogs are isolated from identically labelled background controls.
        buttons = self.driver.find_elements(AppiumBy.ID, 'android:id/button1') + self.driver.find_elements(AppiumBy.ID, 'android:id/button2') + self.driver.find_elements(AppiumBy.ID, 'android:id/button3')
        matches = [b for b in buttons if b.text.casefold() == action.casefold()]
        assert len(matches) == 1, 'Expected native confirmation action'
        matches[0].click()

    def relaunch(self):
        self.driver.terminate_app(self.app.package); self.driver.activate_app(self.app.package)

    def profile(self, section):
        self.app.tab('Profile', 'SETTINGS'); self.app.tap(section, scroll=True)

    def offer(self, target_title, lane='Active'):
        self.app.tab('Inbox', 'Trade Inbox'); self.app.tap(lane)
        self.app.tap('Refresh')
        self.click_parent(target_title)
        self.app.wait('Requested Item')


def adb(*args):
    serial = os.environ.get('DEVICEFARM_DEVICE_UDID')
    assert serial, 'Device serial is required'
    result = subprocess.run(['adb', '-s', serial, *args], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, 'Device control operation failed'
    return result.stdout.strip()


@contextmanager
def offline():
    # Save both radios independently; never enable a radio that was disabled.
    states = {key: adb('shell', 'settings', 'get', 'global', setting)
              for key, setting in [('wifi', 'wifi_on'), ('data', 'mobile_data')]}
    if any(v not in {'0', '1'} for v in states.values()):
        blocked('cannot determine original network radio settings')
    try:
        adb('shell', 'svc', 'wifi', 'disable'); adb('shell', 'svc', 'data', 'disable')
        yield
    finally:
        for key, state in states.items():
            adb('shell', 'svc', key, 'enable' if state == '1' else 'disable')


@contextmanager
def permission(app, name):
    assert name in {'android.permission.CAMERA', 'android.permission.READ_MEDIA_IMAGES',
                    'android.permission.READ_EXTERNAL_STORAGE', 'android.permission.POST_NOTIFICATIONS',
                    'android.permission.READ_MEDIA_VISUAL_USER_SELECTED'}
    state = adb('shell', 'dumpsys', 'package', app.package)
    found = re.search(re.escape(name) + r': granted=(true|false)', state)
    if not found:
        blocked('permission is not requested/supported by this APK: ' + name)
    granted = found.group(1) == 'true'
    try:
        yield
    finally:
        adb('shell', 'pm', 'grant' if granted else 'revoke', app.package, name)


def restore_profile(api, original):
    payload = {k: v for k, v in original.items() if k in PROFILE_FIELDS}
    api.call('PUT', '/v1/me/profile-quiz', payload)
    current = api.profile()
    assert all(current.get(k) == v for k, v in payload.items()), 'Profile restoration did not persist'
