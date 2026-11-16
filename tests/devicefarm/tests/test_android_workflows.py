"""21 concrete staging business workflows; fixtures supply data, never test code.

Every case validates the APK's embedded staging origin before opening a device.
Missing account/provider/data prerequisites are Blocked and fail the complete gate.
"""
from android_ui import android_photo_thumbnails
import base64
from contextlib import ExitStack
import json
import os
import time
from pathlib import Path

import pytest
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait

from android_ui import AndroidUI
from android_workflow_support import (API, Controls, adb, blocked, eventually, need,
    offline, permission, restore_profile, verify_staging_apk)

WORKFLOWS = {
    'registration': ('QA-008', False), 'password_recovery': ('QA-005', False),
    'profile_save_restore': ('QA-050', False), 'style_matching': ('QA-040', False),
    'edit_save_restore': ('QA-036', False), 'delete_disposable': ('QA-038', False),
    'like_restore': ('QA-041', False), 'trade_send': ('QA-042', True),
    'trade_decline': ('QA-043', False), 'trade_accept': ('QA-044', True),
    'trade_stale_action': ('QA-045', True),
    'shipping_address_save_restore': ('QA-046', False),
    'shipping_quote_label': ('QA-047', True), 'payment_add_default_remove': ('QA-048', True),
    'subscription_change_cancel': ('QA-049', True), 'push_delivery': ('QA-053', False),
    'photo_permission_recovery': ('QA-017', False), 'camera_capture': ('QA-016', False),
    'offline_recovery': ('QA-059', False), 'background_analysis': ('QA-060', False),
    'assistant_listing': ('QA-058', False),
}
# All inputs below are data/expectations. Arbitrary step/action recipes are no longer accepted.
REQUIRED = {
    'registration': ('email_env', 'password_env', 'invite_policy'),
    'password_recovery': ('email_env', 'password_env', 'new_password_env'),
    'profile_save_restore': ('first_name', 'style_option'),
    'style_matching': ('source_title', 'eligible_title', 'ineligible_title', 'size_option', 'size_field', 'size_field_label'),
    'edit_save_restore': ('title', 'new_title', 'description', 'condition', 'size'),
    'delete_disposable': ('title', 'listing_id', 'sentinel_title'),
    'like_restore': ('title',),
    'trade_send': ('target_title', 'exchange_title'),
    'trade_decline': ('offer_id', 'target_title'),
    'trade_accept': ('offer_id', 'target_title', 'exchange_title', 'address_label', 'amount_label'),
    'trade_stale_action': ('offer_id', 'target_title'),
    'shipping_address_save_restore': ('address',),
    'shipping_quote_label': ('offer_id', 'target_title', 'quote_amount', 'currency', 'label_host'),
    'payment_add_default_remove': ('billing_name', 'postal_code'),
    'subscription_change_cancel': ('plan_label', 'plan_key', 'amount_label'),
    'push_delivery': ('listing_id', 'title'),
    'photo_permission_recovery': ('permission',), 'camera_capture': (),
    'offline_recovery': ('title',), 'background_analysis': (),
    'assistant_listing': ('question', 'answer_fragment', 'listing_prompt', 'listing_response_fragment', 'facts'),
}
SECOND = {'trade_send', 'trade_decline', 'trade_accept', 'trade_stale_action', 'delete_disposable', 'push_delivery'}
NO_OBSERVER = {'registration', 'password_recovery', 'photo_permission_recovery', 'camera_capture'}


def prerequisites(name, manifest):
    need(manifest, 'workflows', 'exclusive_accounts')
    assert manifest['exclusive_accounts'] is True, 'Use dedicated accounts without concurrent writers'
    cfg = manifest['workflows'].get(name)
    if not cfg:
        blocked('missing data for ' + name)
    need(cfg, *REQUIRED[name])
    if name == 'registration' and cfg.get('invite_policy') == 'invite_only':
        need(cfg, 'denied_email_env', 'denied_message')
    assert not any(k in cfg for k in ['steps', 'verify', 'cleanup']), 'Use workflow fixture data, not recipes'
    assert cfg.get('disposable') is True, 'Controlled workflows require disposable fixtures/accounts'
    expected_env = {'email_env': 'JOUFT_TEST_' + ('REGISTRATION_EMAIL' if name == 'registration' else 'RECOVERY_EMAIL'),
        'password_env': 'JOUFT_TEST_' + ('REGISTRATION_PASSWORD' if name == 'registration' else 'RECOVERY_PASSWORD'),
        'new_password_env': 'JOUFT_TEST_RECOVERY_NEW_PASSWORD', 'denied_email_env': 'JOUFT_TEST_REGISTRATION_DENIED_EMAIL'}
    for key, value in cfg.items():
        if key.endswith('_env'):
            assert value == expected_env.get(key), 'Unapproved workflow environment reference'
        if key.endswith('_env') and not os.environ.get(value):
            blocked('missing workflow environment reference ' + key)
    if name in {'registration', 'password_recovery'}:
        email = os.environ[cfg['email_env']]
        assert email.casefold() not in {os.environ.get('JOUFT_TEST_EMAIL', '').casefold(), os.environ.get('JOUFT_TEST_SECOND_EMAIL', '').casefold()}, 'Use a separate disposable auth account'
    if name not in NO_OBSERVER and not (os.environ.get('JOUFT_TEST_API_TOKEN_A') or (os.environ.get('JOUFT_TEST_CLERK_SESSION_A') and os.environ.get('JOUFT_TEST_CLERK_SECRET'))):
        blocked('staging account A observer token is required')
    if name in SECOND:
        if not all(os.environ.get('JOUFT_TEST_SECOND_' + k) for k in ['EMAIL', 'PASSWORD']):
            blocked('second dedicated staging account is required')
        if not (os.environ.get('JOUFT_TEST_API_TOKEN_B') or (os.environ.get('JOUFT_TEST_CLERK_SESSION_B') and os.environ.get('JOUFT_TEST_CLERK_SECRET'))):
            blocked('staging account B observer token is required')
    if WORKFLOWS[name][1]:
        sandbox = need(manifest.get('sandbox', {}), 'verified_by', 'verified_build', 'stripe_mode', 'shippo_mode')
        if os.environ.get('JOUFT_TEST_SANDBOX_CONFIRMED') != '1':
            blocked('sandbox provider configuration is not confirmed')
        assert sandbox['verified_build'] == manifest['verified_build'], 'Sandbox evidence must match this build'
        assert sandbox['stripe_mode'] == sandbox['shippo_mode'] == 'test', 'Both providers must be verified in test mode'
    return cfg


class Case:
    def __init__(self, app, manifest, cfg):
        self.app, self.c = app, Controls(app)
        self.api = API(manifest['api_origin'], subject=manifest.get('accounts', {}).get('A', {}).get('subject'))
        self.other = API(manifest['api_origin'], 'B', subject=manifest.get('accounts', {}).get('B', {}).get('subject'))
        self.cfg = cfg
        self.cleanups = []

    def cleanup(self, operation):
        self.cleanups.append(operation)

    def switch(self, account):
        suffix = 'SECOND_' if account == 'B' else ''
        self.c.relaunch()
        self.app.login(os.environ['JOUFT_TEST_' + suffix + 'EMAIL'], os.environ['JOUFT_TEST_' + suffix + 'PASSWORD'])

    def profile_snapshot(self):
        old = self.api.profile()
        self.cleanup(lambda: restore_profile(self.api, old))
        return old

    def labels(self, fragment, timeout=60):
        WebDriverWait(self.app.driver, timeout).until(lambda _: any(fragment.casefold() in v.casefold() for v in self.app.values()))

    def ensure_fixture(self, api, title, listing_id=None):
        row = api.listing(title)
        assert row and (not listing_id or row['listing_id'] == listing_id), 'Owned fixture identity mismatch'
        return row

    def close(self):
        errors = []
        for cleanup in reversed(self.cleanups):
            try:
                cleanup()
            except BaseException:
                errors.append('cleanup_failed')
        folder = Path(os.environ.get('DEVICEFARM_LOG_DIR', 'output/devicefarm')) / 'cases'
        folder.mkdir(parents=True, exist_ok=True)
        # No account/profile data, exception text or credentials in this record.
        (folder / (self.name + '-cleanup.json')).write_text(json.dumps({'workflow': self.name,
            'operations': len(self.cleanups), 'failures': len(errors),
            'photo_access_branch': getattr(self, 'photo_access_branch', None)}))
        assert not errors, 'Workflow cleanup failed; fixture must be inspected before retry'


def otp(cfg):
    email = os.environ[cfg['email_env']]
    if '+clerk_test@' in email.lower():
        return '424242'
    blocked('authentication mutations require a disposable Clerk test email (+clerk_test); mailbox delivery remains a separate test')


def registration(t):
    a, c, f = t.app, t.c, t.cfg
    code = otp(f)
    def leave_account():
        c.relaunch()
        if any(n.attrib.get('content-desc', '').endswith(', PROFILE') for n in a.nodes()):
            a.logout()
    t.cleanup(leave_account)
    a.tap('Log In'); a.tap('Create Account')
    assert f['invite_policy'] in {'open', 'invite_only'}
    if f['invite_policy'] == 'invite_only':
        need(f, 'denied_email_env', 'denied_message')
        c.input('Email', os.environ[f['denied_email_env']])
        c.input('Password', os.environ[f['password_env']]); c.input('Confirm Password', os.environ[f['password_env']])
        a.elements('Create Account')[-1].click(); t.labels(f['denied_message'])
        assert not a.has('Verification Code'), 'Uninvited registration unexpectedly advanced'

    c.input('Email', os.environ[f['email_env']])
    c.input('Password', os.environ[f['password_env']])
    c.input('Confirm Password', 'Mismatch-for-validation-9!')
    a.elements('Create Account')[-1].click()
    t.labels('Passwords do not match')
    c.input('Confirm Password', os.environ[f['password_env']])
    a.elements('Create Account')[-1].click()
    a.wait('Verification Code', 60)
    c.input('Verification Code', code); a.tap('Verify Email')
    a.tab('Profile', 'SETTINGS')
    if f.get('initial_profile'):
        # Optional synthetic account-bootstrap data, not credentials or an
        # arbitrary action recipe. Other preferences remain separate fixtures.
        profile = f['initial_profile']
        assert set(profile) == {'first_name', 'last_name', 'birthday'}
        c.profile('Account')
        for label, key in [('First Name', 'first_name'), ('Last Name', 'last_name'), ('Birthday', 'birthday')]:
            c.input(label, profile[key])
        c.input('Email Address', os.environ[f['email_env']])
        a.tap('Save', scroll=True); a.wait('Profile saved.')
    c.profile('Security'); t.labels(os.environ[f['email_env']])
    # The created disposable account is intentionally retained as the registration
    # fixture; never delete a shared account through a privileged auth API.


def password_recovery(t):
    a, c, f = t.app, t.c, t.cfg
    code = otp(f)
    email, original, new = [os.environ[f[k]] for k in ['email_env', 'password_env', 'new_password_env']]
    assert original != new
    def reset(value):
        if not a.has('Log In'):
            a.logout()
        a.tap('Log In'); a.tap('Forgot password?')
        c.input('Email', email); a.tap('Send Reset Code')
        a.wait('Reset Code'); c.input('Reset Code', code); c.input('New Password', value)
        a.tap('Reset Password'); a.tab('Closet', 'My Closet')
    # Register restoration before the change so a mid-request failure still retries
    # resetting the original disposable password.
    def restore():
        c.relaunch(); reset(original); a.logout(); a.login(email, original); a.logout()
    t.cleanup(restore)
    reset(new)
    a.logout(); a.login(email, new); a.wait('My Closet')


def profile_save_restore(t):
    a, c, f = t.app, t.c, t.cfg
    original = t.profile_snapshot()
    assert f['first_name'] != original.get('first_name')
    c.profile('Account'); c.input('First Name', f['first_name']); a.tap('Save')
    a.wait('Profile saved.')
    eventually(lambda: t.api.profile()['first_name'] == f['first_name'])
    c.profile('Style'); a.tap(f['style_option'], scroll=True); a.tap('Save'); a.wait('Profile saved.')
    expected = set(original.get('style_descriptors') or []) ^ {f['style_option']}
    eventually(lambda: set(t.api.profile()['style_descriptors']) == expected)
    t.switch('A'); c.profile('Account'); assert c.read('First Name') == f['first_name']
    assert set(t.api.profile()['style_descriptors']) == expected


def style_matching(t):
    a, c, f = t.app, t.c, t.cfg
    original = t.profile_snapshot()
    source = t.ensure_fixture(t.api, f['source_title'])
    old_size = original.get(f['size_field']) or ''
    assert f['size_option'] not in [s.strip() for s in old_size.split(',')], 'Use an initially unselected size'
    c.profile('Style'); c.section_button(f['size_field_label'], f['size_option']); a.tap('Save'); a.wait('Profile saved.')
    eventually(lambda: f['size_option'] in (t.api.profile().get(f['size_field']) or '').replace(', ', ',').split(','))
    # Match results must be established by controlled category/size/value pairs.
    rows = eventually(lambda: t.api.get('/v1/listings/' + source['listing_id'] + '/marketplace-matches?limit=100')['items'])
    titles = {row['title'] for row in rows}
    assert f['eligible_title'] in titles and f['ineligible_title'] not in titles
    assert all(row['owner_subject'] != source['owner_subject'] for row in rows)
    a.open_listing('marketplace', f['eligible_title'])
    assert a.has('Request Trade')
    restore_profile(t.api, original); c.relaunch()
    eventually(lambda: f['eligible_title'] not in {r['title'] for r in t.api.get('/v1/listings/' + source['listing_id'] + '/marketplace-matches?limit=100')['items']})


def edit_save_restore(t):
    a, c, f = t.app, t.c, t.cfg
    original = t.ensure_fixture(t.api, f['title'])
    assert f['new_title'] != f['title'] and not t.api.listing(f['new_title'])
    def edit(title, values):
        c.relaunch(); a.open_listing('closet', title); a.tap('Edit'); a.tap('Next')
        a.wait('Title'); c.input('Title', values['title']); c.input('Description', values['description'])
        a.tap(values['condition'], scroll=True); a.tap(values['size'], scroll=True)
        a.tap('Next'); a.tap('Save Changes'); a.wait('My Closet', 120)
    restore = {'title': original['title'], 'description': original.get('description') or '',
        'condition': {'LikeNew': 'Like New', 'NewWithTags': 'New with Tags'}.get(original['condition'], original['condition']), 'size': original['size']}
    def undo():
        current = t.api.listing(f['new_title'])
        if current:
            edit(f['new_title'], restore)
        row = t.api.listing(f['title'])
        assert row and row['listing_id'] == original['listing_id']
        assert all(row.get(k) == original.get(k) for k in ['title', 'description', 'condition', 'size'])
    t.cleanup(undo)
    edit(f['title'], dict(title=f['new_title'], **{k: f[k] for k in ['description', 'condition', 'size']}))
    row = eventually(lambda: t.api.listing(f['new_title']))
    assert row['listing_id'] == original['listing_id'] and row['description'] == f['description'] and row['size'] == f['size']
    assert row['condition'] == {'Like New': 'LikeNew', 'New with Tags': 'NewWithTags'}.get(f['condition'], f['condition'])
    c.relaunch(); a.open_listing('closet', f['new_title']); a.wait(f['description'])


def delete_disposable(t):
    a, c, f = t.app, t.c, t.cfg
    t.ensure_fixture(t.api, f['title'], f['listing_id']); sentinel = t.ensure_fixture(t.api, f['sentinel_title'])
    # Scope the overflow menu to exactly the disposable card after searching.
    a.search('closet', f['title']); a.wait('View details for ' + f['title'])
    a.tap('More listing options'); a.tap('Delete listing'); c.alert('Delete listing?', 'Cancel')
    assert t.api.listing(f['title'])['listing_id'] == f['listing_id']
    a.tap('More listing options'); a.tap('Delete listing'); c.alert('Delete listing?', 'Delete')
    a.wait('Listing removed from your closet.')
    eventually(lambda: t.api.listing(f['title']) is None)
    assert t.api.listing(f['sentinel_title'])['listing_id'] == sentinel['listing_id']
    t.switch('B'); a.search('marketplace', f['title']); a.wait('No matching search results', 60)
    assert t.other.listing(f['title'], mine=False) is None


def like_restore(t):
    a, c, f = t.app, t.c, t.cfg
    before = t.api.get('/v1/me/client-state')
    t.cleanup(lambda: t.api.call('PUT', '/v1/me/client-state', {'liked_listing_ids': before['liked_listing_ids']}))
    a.open_listing('marketplace', f['title'])
    was_liked = a.has('Unlike listing')
    a.tap('Unlike listing' if was_liked else 'Like listing')
    c.relaunch(); a.open_listing('marketplace', f['title'])
    a.wait('Like listing' if was_liked else 'Unlike listing')
    row = t.api.listing(f['title'], mine=False)
    assert row
    eventually(lambda: (row['listing_id'] in t.api.get('/v1/me/client-state')['liked_listing_ids']) != was_liked)


def controlled_offer(t, expected):
    f = t.cfg
    left, right = t.api.offer(f['offer_id']), t.other.offer(f['offer_id'])
    assert left['status'] == right['status'] == expected
    assert left['target_listing']['title'] == f['target_title']
    assert left['from_subject'] == t.api.profile()['owner_subject'], 'A must be the requester'
    assert left['to_subject'] == t.other.profile()['owner_subject'], 'B must own the target'
    return left


def offer_state(t, offer_id, status):
    eventually(lambda: t.api.offer(offer_id)['status'] == status)
    assert t.other.offer(offer_id)['status'] == status


def trade_send(t):
    a, c, f = t.app, t.c, t.cfg
    target = t.ensure_fixture(t.other, f['target_title'])
    exchange = t.ensure_fixture(t.api, f['exchange_title'])
    before = {o['offer_id'] for o in t.api.offers()}
    assert not any(o['target_listing_id'] == target['listing_id'] and o['status'] in {'requested', 'pending', 'proposed'} for o in t.api.offers())
    def cleanup():
        for offer in t.api.offers():
            if offer['offer_id'] not in before and offer['target_listing_id'] == target['listing_id']:
                assert offer['from_subject'] == exchange['owner_subject']
                if offer['status'] in {'requested', 'pending', 'proposed'}:
                    t.api.call('POST', '/v1/offers/' + offer['offer_id'] + '/action', {'status': 'declined'})
    t.cleanup(cleanup)
    a.open_listing('marketplace', f['target_title']); a.tap('Request Trade'); a.wait('Trade Request Sent'); a.tap('Close')
    offers = eventually(lambda: [o for o in t.api.offers() if o['offer_id'] not in before and o['target_listing_id'] == target['listing_id']])
    assert len(offers) == 1 and offers[0]['to_subject'] == target['owner_subject']
    offer_id = offers[0]['offer_id']
    t.switch('B'); c.offer(f['target_title']); c.scoped(f['exchange_title'], 'Select for exchange')
    a.tap('Review selection', scroll=True); c.alert('Confirm selection', 'Confirm selection')
    offer_state(t, offer_id, 'proposed')
    assert t.api.offer(offer_id)['selected_offered_listing_id'] == exchange['listing_id']
    t.switch('A'); c.offer(f['target_title']); a.wait(f['exchange_title']); a.wait('Accept Proposal')
    assert len([o for o in t.api.offers() if o['offer_id'] not in before and o['target_listing_id'] == target['listing_id']]) == 1


def trade_decline(t):
    controlled_offer(t, 'proposed')
    t.c.offer(t.cfg['target_title']); t.app.tap('Decline'); t.app.wait('Offer updated.')
    offer_state(t, t.cfg['offer_id'], 'declined')
    t.switch('B'); t.c.offer(t.cfg['target_title'], 'Closed'); t.labels('Declined')
    assert not t.app.has('Create Label')


def trade_accept(t):
    controlled_offer(t, 'proposed')
    f, a, c = t.cfg, t.app, t.c
    c.offer(f['target_title']); a.wait(f['exchange_title'])
    a.tap(f['address_label'], scroll=True)
    a.tap('Accept Proposal'); a.wait('Accept Trade?')
    t.labels(f['exchange_title']); t.labels(f['target_title'])
    # Consent amount is a fixture expectation, never a blind confirmation.
    t.labels(f['amount_label']); a.tap('Accept Trade')
    offer_state(t, f['offer_id'], 'accepted')
    t.switch('B'); c.offer(f['target_title']); t.labels('Accepted Trade')
    # Accepted trades/labels cannot be undone safely. Retain these disposable
    # entities as evidence; a fresh proposal is required for the next run.


def trade_stale_action(t):
    controlled_offer(t, 'proposed')
    f, a, c = t.cfg, t.app, t.c
    before = t.api.get('/v1/offers/' + f['offer_id'] + '/shipping-labels')
    c.offer(f['target_title']); a.wait('Accept Proposal')
    # B is an independent authenticated server session. Mutate it while A still
    # holds stale native detail state, without refreshing A first.
    t.other.call('POST', '/v1/offers/' + f['offer_id'] + '/action', {'status': 'declined'})
    button = a.elements('Decline')[-1]
    button.click()
    from selenium.common.exceptions import StaleElementReferenceException
    try:
        button.click()
    except StaleElementReferenceException:
        pass
    # Retry the exact stale action through A's independent session as well.
    t.api.call('POST', '/v1/offers/' + f['offer_id'] + '/action', {'status': 'accepted'}, allowed=(400, 409))
    offer_state(t, f['offer_id'], 'declined')
    assert t.api.get('/v1/offers/' + f['offer_id'] + '/shipping-labels') == before
    c.relaunch(); c.offer(f['target_title'], 'Closed'); t.labels('Declined')
    assert not a.has('Accept Proposal')


def shipping_address_save_restore(t):
    t.profile_snapshot()
    a, c, address = t.app, t.c, t.cfg['address']
    need(address, 'Label', 'Full Name', 'Address Line 1', 'City', 'State', 'Postal Code', 'Country')
    c.profile('Shipping'); a.tap('Add Address', scroll=True)
    c.input('Label', address['Label']); a.tap('Save Addresses')
    a.wait('Shipping addresses saved.')
    assert not any(x['label'] == address['Label'] for x in t.api.profile()['shipping_addresses']), 'Incomplete address must not become selectable'
    a.tap('Add Address', scroll=True)
    for label, value in address.items():
        c.input(label, value)
    a.tap('Save Addresses'); a.wait('Shipping addresses saved.')
    eventually(lambda: any(x['label'] == address['Label'] for x in t.api.profile()['shipping_addresses']))
    c.relaunch(); c.profile('Shipping')
    saved = next(x for x in t.api.profile()['shipping_addresses'] if x['label'] == address['Label'])
    if not saved['is_default']:
        c.scoped(address['Label'], 'Set Default')
        a.tap('Save Addresses'); a.wait('Shipping addresses saved.')
    entry = next(x for x in t.api.profile()['shipping_addresses'] if x['label'] == address['Label'])
    assert entry['is_default'] and entry['postal_code'] == address['Postal Code']


def shipping_quote_label(t):
    f, a, c = t.cfg, t.app, t.c
    offer = t.api.offer(f['offer_id'])
    assert offer['status'] == 'accepted' and offer['target_listing']['title'] == f['target_title']
    c.offer(f['target_title']); a.tap('Get Shipping Quote', scroll=True)
    t.labels(f['quote_amount']); t.labels(f['currency'])
    a.tap('Create Label', scroll=True); a.wait('Shipping label created.', 120)
    rows = t.api.get('/v1/offers/' + f['offer_id'] + '/shipping-labels')['shipments']
    own = [row for row in rows if row.get('label_url')]
    assert own and all(row['offer_id'] == f['offer_id'] for row in own)
    from urllib.parse import urlsplit
    assert all(urlsplit(row['label_url']).scheme == 'https' and urlsplit(row['label_url']).hostname == f['label_host'] for row in own)
    ids = {row['shipment_id'] for row in rows}
    a.tap('Download Label', scroll=True); a.driver.back()
    c.relaunch(); c.offer(f['target_title']); a.tap('Refresh', scroll=True)
    assert {r['shipment_id'] for r in t.api.get('/v1/offers/' + f['offer_id'] + '/shipping-labels')['shipments']} == ids


def payment_add_default_remove(t):
    a, c, f = t.app, t.c, t.cfg
    before = t.api.get('/v1/me/payment-methods')['items']
    before_ids = {r['payment_method_id'] for r in before}
    defaults = [r['payment_method_id'] for r in before if r['is_default']]
    def cleanup():
        for row in t.api.get('/v1/me/payment-methods')['items']:
            if row['payment_method_id'] not in before_ids:
                t.api.call('DELETE', '/v1/me/payment-methods/' + row['payment_method_id'])
        for identity in defaults:
            t.api.call('POST', '/v1/me/payment-methods/' + identity + '/default', {})
        assert {r['payment_method_id'] for r in t.api.get('/v1/me/payment-methods')['items']} == before_ids
    t.cleanup(cleanup)
    setup = t.api.call('POST', '/v1/me/payment-methods/stripe/setup-intent', {})
    assert setup['publishable_key'].startswith('pk_test_'), 'Refuse a live Stripe payment sheet'
    c.profile('Subscription'); a.tap('Add', scroll=True)
    # Stripe's native PaymentSheet: fixed provider test card only, no real card input.
    if a.has('Card'):
        a.tap('Card')
    c.input('Card number', '4242424242424242')
    c.input('Expiration date', '1235'); c.input('CVC', '123')
    c.input('ZIP', f['postal_code'])
    if a.has('Name on card'):
        c.input('Name on card', f['billing_name'])
    a.tap('Save payment method'); a.wait('Payment method saved.', 120)
    new = eventually(lambda: [r for r in t.api.get('/v1/me/payment-methods')['items'] if r['payment_method_id'] not in before_ids])
    assert len(new) == 1 and (new[0].get('last4') or new[0].get('label', '')[-4:]) == '4242'
    label = new[0]['label']
    if not new[0]['is_default']:
        c.scoped(label, 'Set Default')
    c.relaunch(); c.profile('Subscription')
    assert next(r for r in t.api.get('/v1/me/payment-methods')['items'] if r['payment_method_id'] == new[0]['payment_method_id'])['is_default']
    c.scoped(new[0]['label'] + ' • Default', 'Remove'); a.wait('Payment method removed.')
    eventually(lambda: all(r['payment_method_id'] != new[0]['payment_method_id'] for r in t.api.get('/v1/me/payment-methods')['items']))


def subscription_change_cancel(t):
    a, c, f = t.app, t.c, t.cfg
    profile = t.api.profile()
    assert profile.get('subscription_plan') == 'free', 'Use a disposable free-plan account'
    setup = t.api.call('POST', '/v1/me/payment-methods/stripe/setup-intent', {})
    assert setup['publishable_key'].startswith('pk_test_')
    assert t.api.get('/v1/me/payment-methods')['items'], 'Seed a sandbox payment method'
    def cancel_if_needed():
        p = t.api.profile()
        if p.get('subscription_plan') != 'free' and p.get('subscription_status') in {'active', 'trialing'}:
            t.api.call('POST', '/v1/me/subscription/cancel', {})
    t.cleanup(cancel_if_needed)
    c.profile('Subscription'); a.tap(f['plan_label'], scroll=True); a.tap('Monthly'); a.tap('Activate Plan')
    a.wait('Confirm subscription'); t.labels(f['amount_label']); c.alert('Confirm subscription', 'Authorize')
    t.labels('Subscription active.', 120)
    eventually(lambda: t.api.profile()['subscription_plan'] == f['plan_key'])
    c.relaunch(); c.profile('Subscription'); a.tap('Cancel Subscription', scroll=True)
    c.alert('Cancel subscription?', 'Cancel Subscription')
    eventually(lambda: t.api.profile()['subscription_status'] in {'canceling', 'canceled'})
    c.relaunch(); c.profile('Subscription'); t.labels('Current status: Cancel')


def push_delivery(t):
    a, c, f = t.app, t.c, t.cfg
    row = t.ensure_fixture(t.api, f['title'], f['listing_id'])
    assert t.api.get('/v1/me/client-state')['alert_preferences'].get('likes'), 'Enable like alerts on the disposable fixture account'
    event_ids = []
    def cleanup():
        for identity in event_ids:
            t.api.call('DELETE', '/v1/me/notifications/' + identity, allowed=(200, 404))
        c.relaunch()
    t.cleanup(cleanup)
    with permission(a, 'android.permission.POST_NOTIFICATIONS'):
        c.profile('Account'); a.tap('Enabled', scroll=True)
        if a.has('Allow'):
            a.tap('Allow')
        t.labels('Push token ready')
        before = {r['notification_id'] for r in t.api.get('/v1/me/notifications?include_read=true')['items']}
        a.driver.press_keycode(3)
        t.other.call('POST', '/v1/listings/' + row['listing_id'] + '/like', {})
        events = eventually(lambda: [r for r in t.api.get('/v1/me/notifications?include_read=true')['items'] if r['notification_id'] not in before and r['entity_id'] == row['listing_id']])
        event_ids.extend(r['notification_id'] for r in events)
        assert len(events) == 1
        a.driver.open_notifications()
        t.labels(f['title'], 90); c.click_parent(next(v for v in a.values() if f['title'] in v))
        a.wait('Marketplace', 60)
        # History alone cannot establish delivery. The OS notification must be
        # present and tapping it must route back into the expected app screen.
        assert len([r for r in t.api.get('/v1/me/notifications?include_read=true')['items'] if r['notification_id'] not in before and r['entity_id'] == row['listing_id']]) == 1


def discard(t):
    t.c.relaunch(); t.app.tab('Create', 'Add Photos'); t.app.tap('Close')
    if t.app.has('Leave listing?'):
        t.c.alert('Leave listing?', 'Discard')
    t.app.tab('Closet', 'My Closet')


def camera_capture(t):
    a, c = t.app, t.c
    t.cleanup(lambda: discard(t))
    with permission(a, 'android.permission.CAMERA'):
        a.tab('Create', 'Add Photos'); a.tap('Choose Photos'); a.tap('Take photos')
        for label in ['While using the app', 'Only this time', 'Allow']:
            if a.has(label):
                a.tap(label); break
        a.wait('Take listing photos'); a.tap('Take photo'); a.wait('Captured photo 1')
        a.tap('Cancel taking photos'); c.alert('Discard these photos?', 'Keep taking photos')
        a.wait('Captured photo 1')
        a.tap('Cancel taking photos'); c.alert('Discard these photos?', 'Discard')
        a.wait('Add Photos'); assert not a.has('Remove photo 1')
        a.tap('Choose Photos'); a.tap('Take photos'); a.wait('Take listing photos')
        a.tap('Take photo'); a.wait('Captured photo 1'); a.tap('Use Photos (1)')
        a.wait('Remove photo 1', 120); assert not a.has('Take listing photos')


def photo_permission_recovery(t):
    a, c, f = t.app, t.c, t.cfg
    t.cleanup(lambda: discard(t))
    package_state = adb('shell', 'dumpsys', 'package', a.package)
    if f['permission'] + ':' not in package_state and int(adb('shell', 'getprop', 'ro.build.version.sdk')) >= 33:
        # Expo uses Android's permission-free scoped photo picker on API 33+.
        # Test refusal/cancel and retry instead of inventing a full-library grant.
        t.photo_access_branch = 'scoped-picker-cancel-retry'
        a.tab('Create', 'Add Photos'); a.tap('Choose Photos'); a.tap('Photo library')
        picker_packages = {'com.google.android.providers.media.module', 'com.android.providers.media.module',
            'com.google.android.documentsui', 'com.android.documentsui', 'com.google.android.photopicker'}
        WebDriverWait(a.driver, 30).until(lambda _: a.driver.current_package in picker_packages)
        a.driver.back(); a.wait('Add Photos')
        assert a.has('0/6') and not a.has('Remove photo 1')
        select_photos(t); a.wait('Remove photo 1', 120)
        return
    t.photo_access_branch = 'runtime-permission-denial-and-grant'
    with ExitStack() as stack:
        permissions = [f['permission']]
        if 'android.permission.READ_MEDIA_VISUAL_USER_SELECTED:' in adb('shell', 'dumpsys', 'package', a.package):
            permissions.append('android.permission.READ_MEDIA_VISUAL_USER_SELECTED')
        for name in permissions:
            stack.enter_context(permission(a, name))
            adb('shell', 'pm', 'revoke', a.package, name)
        c.relaunch()
        a.tab('Create', 'Add Photos'); a.tap('Choose Photos'); a.tap('Photo library')
        for label in ["Don't allow", 'Don’t allow', 'Deny']:
            if a.has(label):
                a.tap(label); break
        t.labels('Photo-library access is required')
        adb('shell', 'pm', 'grant', a.package, f['permission']); c.relaunch()
        select_photos(t)
        a.wait('Remove photo 1', 120)


def select_photos(t, assistant=False):
    a = t.app
    paths = sorted(Path(os.environ.get('JOUFT_TEST_PHOTOS', 'fixtures')).glob('*.jpg'))
    assert 1 <= len(paths) <= 6, 'Provide complete JPG views of one item'
    for index, path in enumerate(paths):
        target = '/sdcard/Pictures/jouft-workflow-' + str(time.time_ns()) + '-' + str(index) + '.jpg'
        a.driver.push_file(target, base64.b64encode(path.read_bytes()).decode())
        t.cleanup(lambda target=target: (adb('shell', 'rm', '-f', target), adb('shell', 'am', 'broadcast', '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE', '-d', 'file://' + target)))
        adb('shell', 'am', 'broadcast', '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE', '-d', 'file://' + target)
    if not assistant:
        a.tab('Create', 'Add Photos')
    a.tap('Choose photos' if assistant else 'Choose Photos'); a.tap('Photo library')
    thumbnails = WebDriverWait(a.driver, 30).until(lambda _: android_photo_thumbnails(a.driver))
    assert len(thumbnails) == len(paths), 'Use a clean Device Farm gallery containing only supplied fixture photos'
    for thumbnail in thumbnails:
        thumbnail.click()
    WebDriverWait(a.driver, 15).until(lambda _: a.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textMatches("(?i)Add( \\(.*\\))?")')).click()


def offline_recovery(t):
    a, c, f = t.app, t.c, t.cfg
    original = t.ensure_fixture(t.api, f['title'])
    a.search('closet', f['title']); a.wait('View details for ' + f['title'])
    with offline():
        a.tap('Refresh')
        WebDriverWait(a.driver, 45).until(lambda _: any(word in value.lower() for value in a.values() for word in ['network', 'offline', 'failed to fetch', 'unable to', 'timed out']))
    a.tap('Refresh'); a.wait('View details for ' + f['title'], 120)
    row = t.api.listing(f['title'])
    assert row['listing_id'] == original['listing_id']
    assert all(row.get(k) == original.get(k) for k in ['title', 'description', 'condition', 'size', 'status'])


def background_analysis(t):
    # This uses the actual photo upload/create UI shared with the established
    # create-listing test, with a hook immediately after saving the new draft.
    from test_create_listing import run_listing_flow
    before = {r['listing_id'] for r in t.api.get('/v1/listings?mine=true&limit=100')['items']}
    created = []
    def new_rows():
        return [r for r in t.api.get('/v1/listings?mine=true&limit=100')['items'] if r['listing_id'] not in before]
    def clean():
        rows = new_rows()
        unexpected = [row for row in rows if row['listing_id'] not in created]
        for row in rows:
            if row['listing_id'] in created:
                assert row['owner_subject'] == t.api.profile()['owner_subject']
                t.api.call('DELETE', '/v1/listings/' + row['listing_id'])
        assert not unexpected, 'Unidentified new draft retained for inspection; no broad deletion permitted'
    t.cleanup(clean)
    def saved(driver):
        rows = eventually(new_rows); assert len(rows) == 1
        created.append(rows[0]['listing_id'])
        initial = eventually(lambda: (lambda j: j if j.get('job_id') else None)(t.api.get('/v1/listings/' + created[0] + '/analysis-jobs/latest')))
        assert initial['status'] in {'queued', 'running', 'retrying'}, 'Analysis completed before backgrounding; use a fresh draft'
        driver.press_keycode(3)
        # Server polling avoids an arbitrary multi-minute sleep and records the
        # same job ID before/after returning to the app.
        eventually(lambda: t.api.get('/v1/listings/' + created[0] + '/analysis-jobs/latest').get('status') in {'succeeded', 'completed', 'failed'}, 900)
        driver.activate_app('com.jouft.app.dev')
        current = t.api.get('/v1/listings/' + created[0] + '/analysis-jobs/latest')
        assert current.get('job_id') == initial.get('job_id') and current.get('status') in {'succeeded', 'completed'}
    run_listing_flow(after_save=saved)
    assert len(created) == len(new_rows()) == 1


def assistant_listing(t):
    a, c, f = t.app, t.c, t.cfg
    baseline = {r['listing_id'] for r in t.api.get('/v1/listings?mine=true&limit=100')['items']}
    a.tap('Open Jouft assistant'); a.wait('Close assistant'); a.tap('＋ New chat')
    t.cleanup(lambda: (c.relaunch(), a.tab('Closet', 'My Closet')))
    # Current conversation pilot exposes an accessible composer and Send button.
    c.input('Message Jouft', f['question']); a.tap('Send'); t.labels(f['answer_fragment'], 180)
    c.input('Message Jouft', f['listing_prompt']); a.tap('Send'); t.labels(f['listing_response_fragment'], 180)
    # Cancel before any draft is saved, then start a fresh thread and retry.
    c.input('Message Jouft', 'Cancel creating this listing'); a.tap('Send'); t.labels('cancel', 120)
    assert {r['listing_id'] for r in t.api.get('/v1/listings?mine=true&limit=100')['items']} == baseline, 'Cancellation must not save a draft'
    a.tap('＋ New chat'); c.input('Message Jouft', f['listing_prompt']); a.tap('Send')
    t.labels(f['listing_response_fragment'], 180)
    before = {r['listing_id'] for r in t.api.get('/v1/listings?mine=true&limit=100')['items']}
    def created():
        return [r for r in t.api.get('/v1/listings?mine=true&limit=100')['items'] if r['listing_id'] not in before]
    known_ids = []
    def cleanup_draft():
        rows = created()
        unexpected = [row for row in rows if row['listing_id'] not in known_ids]
        for row in rows:
            if row['listing_id'] in known_ids:
                assert row['status'] != 'Active', 'Assistant published without explicit consent'
                t.api.call('DELETE', '/v1/listings/' + row['listing_id'])
        assert not unexpected, 'Unidentified assistant draft retained for inspection'
    t.cleanup(cleanup_draft)
    select_photos(t, assistant=True)
    a.tap('Use these photos', scroll=True)
    c.input('Message Jouft', f['facts']); a.tap('Send')
    a.wait('Confirm draft details', 180)
    assert not created(), 'Assistant created a draft before confirmation'
    a.tap('Confirm and analyze private draft', scroll=True)
    rows = eventually(created, 180); assert len(rows) == 1
    identity = rows[0]['listing_id']; known_ids.append(identity)
    eventually(lambda: t.api.get('/v1/listings/' + identity + '/analysis-jobs/latest')['status'] in {'succeeded', 'failed'}, 900)
    assert t.api.get('/v1/listings/' + identity + '/analysis-jobs/latest')['status'] == 'succeeded'
    a.tap('Close assistant'); a.tab('Closet', 'My Closet'); a.tap('Refresh')
    row = created()[0]
    assert row['listing_id'] == identity and row['status'] == 'Review'
    a.open_listing('closet', row['title']); a.wait('Listing Details')


FUNCTIONS = {name: globals()[name] for name in WORKFLOWS}


def selected_workflows():
    names = os.environ.get('JOUFT_TEST_WORKFLOW_CASES', '')
    selected = names.split(',') if names else list(WORKFLOWS)
    assert selected and len(set(selected)) == len(selected) and set(selected) <= set(WORKFLOWS), 'Unknown or duplicate workflow selection'
    return selected


@pytest.mark.parametrize('workflow', selected_workflows())
def test_controlled_workflow(workflow, request):
    request.node.user_properties.append(('qa_case_id', WORKFLOWS[workflow][0]))
    path = Path(os.environ.get('JOUFT_TEST_FIXTURES', 'android-fixtures.json'))
    manifest = json.loads(path.read_text()) if path.exists() else {}
    if not manifest:
        blocked('reviewed Android fixture manifest is required')
    cfg = prerequisites(workflow, manifest)
    verify_staging_apk(manifest, os.environ.get('DEVICEFARM_APP_PATH'))
    # Bind observers to the same dedicated identities used by the UI before any
    # device action or cleanup snapshot can touch account data.
    if workflow not in NO_OBSERVER:
        for account in (['A', 'B'] if workflow in SECOND else ['A']):
            subject = need(manifest.get('accounts', {}).get(account, {}), 'subject')['subject']
            observer = API(manifest['api_origin'], account, subject=subject)
            suffix = 'SECOND_' if account == 'B' else ''
            observer.assert_identity(os.environ['JOUFT_TEST_' + suffix + 'EMAIL'])
    # Do not launch a nested Appium session for the shared creation flow.
    app = None if workflow == 'background_analysis' else AndroidUI()
    t = Case(app, manifest, cfg) if app else object.__new__(Case)
    if app is None:
        t.app = None; t.api = API(manifest['api_origin'], subject=manifest.get('accounts', {}).get('A', {}).get('subject')); t.cleanups = []
    t.name = workflow
    try:
        if app and workflow not in {'registration', 'password_recovery'}:
            app.login(os.environ['JOUFT_TEST_EMAIL'], os.environ['JOUFT_TEST_PASSWORD'])
        elif app:
            # Ensure authentication cases begin signed out on reused devices.
            if any(n.attrib.get('content-desc', '').endswith(', PROFILE') for n in app.nodes()):
                app.logout()
        if WORKFLOWS[workflow][1] and workflow not in {'payment_add_default_remove', 'subscription_change_cancel'}:
            setup = t.api.call('POST', '/v1/me/payment-methods/stripe/setup-intent', {})
            assert setup.get('publishable_key', '').startswith('pk_test_'), 'Refuse live or missing Stripe configuration'
        FUNCTIONS[workflow](t)
    finally:
        try:
            if app:
                folder = Path(os.environ.get('DEVICEFARM_LOG_DIR', 'output/devicefarm')) / 'cases'
                folder.mkdir(parents=True, exist_ok=True)
                # Financial/authentication cases suppress screenshots entirely.
                if not WORKFLOWS[workflow][1] and workflow not in {'registration', 'password_recovery'}:
                    app.capture(folder / (workflow + '.png'))
        finally:
            try:
                t.close()
            finally:
                if app:
                    app.driver.quit()
