from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
import json

import pytest
from fastapi import HTTPException
from test_api_integration import _build_client
from app.auth import AuthPrincipal, require_clerk_user, get_request_principal
from app import invitation_trials as trials


@pytest.fixture
def suite(monkeypatch):
    client = _build_client()
    from app.main import app
    from app.deps import get_db, get_settings
    actor = {'subject':'admin', 'admin':True}
    def principal():
        return AuthPrincipal('clerk',actor['subject'], {'role':'admin' if actor['admin'] else 'member'})
    app.dependency_overrides[require_clerk_user] = principal
    app.dependency_overrides[get_request_principal] = principal
    monkeypatch.setattr(trials, 'verified_email', lambda p,s:p.subject+'@example.com')
    yield SimpleNamespace(client=client,db=get_db(),actor=actor,settings=get_settings())
    app.dependency_overrides.clear()


def create(s, **options):
    body={'name':'Early members','code':'WELCOME30', **options}
    response=s.client.post('/v1/admin/trial-invitations',json=body)
    assert response.status_code==200,response.text
    s.actor.update(subject='member',admin=False)
    return response.json()


def redeem(s, code='WELCOME30', **values):
    config=s.db.fetchone('SELECT config_json FROM invitation_trial_offers WHERE code_hash=?',(trials.code_hash(code),))
    version=trials.offer_version(json.loads(config[0])) if config else 'missing'
    return s.client.post('/v1/me/trial-invitations/redeem',json={'code':code,'consent':True,'offer_version':version,**values})


def test_admin_authorization_and_code_secrecy(suite):
    created=create(suite)
    assert created['code']=='WELCOME30'
    assert suite.client.get('/v1/admin/trial-invitations').status_code==403
    assert suite.client.post('/v1/admin/trial-invitations',json={'name':'Unauthorized'}).status_code==403
    suite.actor['admin']=True
    listed=suite.client.get('/v1/admin/trial-invitations').json()['offers'][0]
    assert 'code_hash' not in listed and 'code' not in listed
    assert listed['code_hint']=='ME30'
    assert 'WELCOME30' not in suite.db.fetchone('SELECT config_json FROM invitation_trial_offers')[0]


@pytest.mark.parametrize('changes',[{'duration_days':0},{'duration_days':366},{'max_redemptions':0},
    {'end_behavior':'renew','require_card':False},{'plan':'free'}, {'allowed_emails':['broken']},
    {'expires_at':'2020-01-01T00:00:00Z'},{'starts_at':'2030-01-01T00:00:00'}, {'extra_field':True}])
def test_invalid_configuration(suite,changes):
    r=suite.client.post('/v1/admin/trial-invitations',json={'name':'Offer',**changes})
    assert r.status_code==422,r.text


def test_no_card_grant_idempotency_and_expiry(suite,monkeypatch):
    create(suite,plan='pro_25',duration_days=5)
    monkeypatch.setattr(trials,'stripe_request',lambda *a,**k:pytest.fail('No-card trials must not call Stripe'))
    r=redeem(suite,code=' welcome30 ')
    assert r.status_code==200,r.text
    grant=r.json()['trial']
    assert grant['plan']=='pro_25' and grant['end_behavior']=='expire'
    assert trials.active_grant(suite.db,'member')
    assert redeem(suite).json()['status']=='already_redeemed'
    assert suite.db.fetchone('SELECT COUNT(*) FROM invitation_trial_redemptions')[0]==1
    future=trials.now()+timedelta(days=6)
    monkeypatch.setattr(trials,'now',lambda:future)
    assert trials.active_grant(suite.db,'member') is None
    assert redeem(suite).json()['status']=='already_redeemed'
    assert trials.active_grant(suite.db,'member') is None


def test_email_domain_restriction_and_consent(suite):
    create(suite,allowed_emails=['vip@EXAMPLE.com'],allowed_domains=['partner.com'])
    assert redeem(suite).status_code==403
    suite.actor['subject']='vip'
    assert redeem(suite,consent=False).status_code==400
    assert redeem(suite).status_code==200


def test_disabled_future_and_capacity(suite):
    offer=create(suite,max_redemptions=1)
    assert redeem(suite).status_code==200
    suite.actor['subject']='other'
    assert redeem(suite).status_code==409
    suite.actor['admin']=True
    assert suite.client.patch('/v1/admin/trial-invitations/'+offer['offer_id'],json={'active':False}).status_code==200
    suite.actor['admin']=False
    assert redeem(suite).status_code==400


def test_future_offer_and_first_trial_guard(suite):
    future=(trials.now()+timedelta(days=1)).isoformat()
    create(suite,starts_at=future)
    assert redeem(suite).status_code==400
    suite.actor.update(subject='admin',admin=True)
    create(suite,code='SECOND30')
    assert redeem(suite,'SECOND30').status_code==200
    suite.actor.update(subject='admin',admin=True)
    create(suite,code='THIRD30')
    suite.db.execute("UPDATE invitation_trial_redemptions SET ends_at='2000-01-01T00:00:00+00:00'")
    suite.db.commit()
    assert redeem(suite,'THIRD30').status_code==409


def test_existing_paid_subscription_is_not_replaced(suite):
    create(suite,new_subscribers_only=False)
    suite.db.set_billing_subscription('member',stripe_subscription_id='sub_existing',subscription_plan='pro_25',subscription_billing_cycle='monthly',subscription_status='active',subscription_renewal_date=None)
    assert redeem(suite).status_code==409
    assert suite.db.get_billing_profile('member')['stripe_subscription_id']=='sub_existing'


def test_profile_trial_fields_cannot_be_persisted(suite):
    create(suite)
    saved=suite.client.put('/v1/me/profile-quiz',json={'birthday':'1990-01-01','first_name':'Test','last_name':'Member','email':'member@example.com','subscription_plan':'pro_25','subscription_status':'active'})
    assert saved.status_code==200,saved.text
    assert suite.db.get_user_profile_quiz('member')['subscription_status'] is None
    assert redeem(suite).status_code==200
    profile=suite.client.get('/v1/me/profile-quiz').json()
    assert profile['subscription_plan']=='starter_15' and profile['subscription_status']=='trialing'
    profile['first_name']='Updated'
    assert suite.client.put('/v1/me/profile-quiz',json=profile).status_code==200
    assert suite.db.get_user_profile_quiz('member')['subscription_status'] is None


def test_concurrent_last_slot_is_atomic(suite):
    create(suite,max_redemptions=1)
    def attempt(subject):
        p=AuthPrincipal('clerk',subject,{})
        try:return trials.redeem_offer(trials.RedeemInput(code='WELCOME30',consent=True,offer_version=trials.offer_version(json.loads(suite.db.fetchone('SELECT config_json FROM invitation_trial_offers')[0]))),p,suite.db,suite.settings)['status']
        except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes=list(executor.map(attempt,['member-a','member-b']))
    assert sorted(outcomes,key=str)==sorted(['active',409],key=str)
    assert suite.db.fetchone('SELECT COUNT(*) FROM invitation_trial_redemptions')[0]==1


def test_card_requirement_fail_closed_without_provider(suite):
    create(suite,require_card=True)
    assert redeem(suite).status_code==503
    assert suite.db.fetchone('SELECT COUNT(*) FROM invitation_trial_redemptions')[0]==0


@pytest.mark.parametrize('renew',[False,True])
def test_card_checkout_server_confirmation_recovery_and_replay(suite,monkeypatch,renew):
    create(suite,require_card=True,end_behavior='renew' if renew else 'expire',billing_cycle='annual')
    suite.settings.stripe_secret_key='sk_test_fake'
    calls=[]
    session={'id':'cs_test_123','url':'https://checkout.stripe.com/test','status':'open','subscription':'sub_trial','setup_intent':'seti_123'}
    def provider(settings,method,path,**kwargs):
        calls.append((method,path,kwargs))
        if path=='customers':return {'id':'cus_trial'}
        if path=='checkout/sessions':
            data=kwargs['data'];session['metadata']={'trial_redemption_id':data['metadata[trial_redemption_id]'],'owner_subject':data['metadata[owner_subject]']}
            assert kwargs['key'].startswith('trial-checkout-')
            assert data['mode']==('subscription' if renew else 'setup')
            if renew:
                assert data['subscription_data[trial_period_days]']=='30'
                assert data['line_items[0][price_data][unit_amount]']=='16200'
            return dict(session)
        if path.startswith('checkout/sessions/'):return dict(session)
        if path.startswith('setup_intents/'):return {'status':'succeeded','payment_method':'pm_card'}
        if path.startswith('subscriptions/'):
            stamp=trials.now();return {'id':'sub_trial','status':'trialing','trial_start':int(stamp.timestamp()),'trial_end':int((stamp+timedelta(days=30)).timestamp()),'metadata':session['metadata']}
        pytest.fail(path)
    monkeypatch.setattr(trials,'stripe_request',provider)
    r=redeem(suite)
    assert r.status_code==200,r.text
    assert r.json()['status']=='checkout' and not trials.active_grant(suite.db,'member')
    assert redeem(suite).json()['session_id']=='cs_test_123'
    assert len([c for c in calls if c[1]=='checkout/sessions'])==1
    session['status']='complete'
    result=suite.client.post('/v1/me/trial-invitations/sync',json={'session_id':'cs_test_123'})
    assert result.status_code==200,result.text
    assert result.json()['status']==('converted' if renew else 'active')
    if renew:assert suite.db.get_billing_profile('member')['stripe_subscription_id']=='sub_trial'
    else:assert trials.active_grant(suite.db,'member')
    assert suite.client.post('/v1/me/trial-invitations/sync',json={'session_id':'cs_test_123'}).status_code==200
    suite.actor['subject']='someone-else'
    assert suite.client.post('/v1/me/trial-invitations/sync',json={'session_id':'cs_test_123'}).status_code==403


def test_redemption_rate_limit(suite):
    create(suite)
    for _ in range(10):assert redeem(suite,'INVALID1').status_code==400
    assert redeem(suite,'INVALID1').status_code==429


def test_verified_email_never_uses_profile(suite,monkeypatch):
    monkeypatch.undo()
    p=AuthPrincipal('clerk','member',{'email':'fake@restricted.com'})
    with pytest.raises(HTTPException):trials.verified_email(p,SimpleNamespace(clerk_secret_key=None))


def test_edits_preserve_existing_terms_and_invalidate_preview(suite):
    created=create(suite,max_redemptions=5)
    old_version=trials.offer_version(created['config'])
    assert redeem(suite).status_code==200
    suite.actor.update(subject='admin',admin=True)
    cfg={**created['config'],'duration_days':60,'max_redemptions':10}
    assert suite.client.put('/v1/admin/trial-invitations/'+created['offer_id'],json=cfg).status_code==200
    suite.actor.update(subject='other',admin=False)
    assert redeem(suite,offer_version=old_version).status_code==409
    assert redeem(suite).status_code==200
    configs=[json.loads(r[0]) for r in suite.db.fetchall('SELECT config_json FROM invitation_trial_redemptions ORDER BY created_at')]
    assert [c['duration_days'] for c in configs]==[30,60]
    suite.actor['admin']=True
    assert suite.client.put('/v1/admin/trial-invitations/'+created['offer_id'],json={**cfg,'max_redemptions':1}).status_code==409


def test_revoked_trial_does_not_return_access_or_free_capacity(suite):
    create(suite,max_redemptions=1)
    grant=redeem(suite).json()['trial']
    suite.actor['admin']=True
    url='/v1/admin/trial-invitations/redemptions/'+grant['redemption_id']+'/revoke'
    assert suite.client.post(url).status_code==200
    assert suite.client.post(url).status_code==200
    assert not trials.active_grant(suite.db,'member')
    suite.actor.update(subject='other',admin=False)
    assert redeem(suite).status_code==409
    assert suite.client.post(url).status_code==403


def test_disabled_offer_keeps_issued_grant(suite):
    offer=create(suite)
    assert redeem(suite).status_code==200
    suite.actor['admin']=True
    suite.client.patch('/v1/admin/trial-invitations/'+offer['offer_id'],json={'active':False})
    assert trials.active_grant(suite.db,'member')


def test_trial_profile_for_member_without_profile_row(suite):
    create(suite)
    assert redeem(suite).status_code==200
    profile=suite.client.get('/v1/me/profile-quiz').json()
    assert profile['subscription_plan']=='starter_15' and profile['subscription_trial']


def test_checkout_expiry_frees_reserved_place_without_granting_access(suite,monkeypatch):
    create(suite,require_card=True,max_redemptions=1)
    suite.settings.stripe_secret_key='sk_test_fake'
    def unavailable(*args,**kwargs):
        raise HTTPException(502,'Simulated provider failure')
    monkeypatch.setattr(trials,'checkout_for_grant',unavailable)
    assert redeem(suite).status_code==502
    record=suite.db._fetch_dicts('SELECT * FROM invitation_trial_redemptions')[0]
    assert record['state']=='pending' and not trials.active_grant(suite.db,'member')
    suite.db.execute("UPDATE invitation_trial_redemptions SET checkout_session_id='cs_expired'")
    suite.db.commit()
    result=trials.complete_checkout(suite.db,suite.settings,{'id':'cs_expired','status':'expired','metadata':{'trial_redemption_id':record['redemption_id'],'owner_subject':'member'}})
    assert result['status']=='expired'
    assert not trials.active_grant(suite.db,'member')
    # A confirmed expiry frees capacity for a new attempt.
    assert redeem(suite).status_code==502
    assert suite.db.fetchone("SELECT COUNT(*) FROM invitation_trial_redemptions WHERE state='pending'")[0]==1


def test_expired_unissued_provider_failure_can_be_retried(suite,monkeypatch):
    create(suite,require_card=True,max_redemptions=1)
    suite.settings.stripe_secret_key='sk_test_fake'
    monkeypatch.setattr(trials,'checkout_for_grant',lambda *a,**k:(_ for _ in ()).throw(HTTPException(502,'Provider failure')))
    assert redeem(suite).status_code==502
    suite.db.execute("UPDATE invitation_trial_redemptions SET reserved_until='2000-01-01T00:00:00+00:00'")
    suite.db.commit()
    assert redeem(suite).status_code==502
    assert suite.db.fetchone("SELECT COUNT(*) FROM invitation_trial_redemptions WHERE state='failed'")[0]==1
    assert suite.db.fetchone("SELECT COUNT(*) FROM invitation_trial_redemptions WHERE state='pending'")[0]==1


def test_trial_entitlement_expires_without_writing_billing_status(suite,monkeypatch):
    from app.main import _subject_has_subscription_entitlement
    create(suite)
    assert redeem(suite).status_code==200
    assert _subject_has_subscription_entitlement(suite.db,'member')
    end=trials.now()+timedelta(days=31)
    monkeypatch.setattr(trials,'now',lambda:end)
    assert not _subject_has_subscription_entitlement(suite.db,'member')
    assert suite.db.get_billing_profile('member') is None


def insert_trial_listing(db, listing_id, subject='member'):
    return db.insert_listing(listing_id=listing_id,owner_subject=subject,owner_name='Test member',title='Trial item',
        mode='trade',category='shoes',brand='Example',condition='LikeNew',size='8',estimated_value=50,city='Test',
        image=None,images=[],description='',wants='',tags=[],source_item_id=None,analysis=None,status='Draft')


@pytest.mark.parametrize('limit',[0,-1,1.5])
def test_invalid_trial_listing_allowance(suite,limit):
    response=suite.client.post('/v1/admin/trial-invitations',json={'name':'Invalid allowance','listing_limit':limit})
    assert response.status_code==422


def test_trial_listing_limit_counts_new_listings_only_and_keeps_archived_usage(suite):
    from app.db import TrialListingLimitError
    insert_trial_listing(suite.db,'before-trial')
    create(suite,listing_limit=1)
    assert redeem(suite).status_code==200
    insert_trial_listing(suite.db,'allowed')
    suite.db.execute("UPDATE listings SET status='Archived' WHERE listing_id='allowed'")
    suite.db.commit()
    with pytest.raises(TrialListingLimitError):insert_trial_listing(suite.db,'denied')
    status=suite.client.get('/v1/me/trial-invitations').json()['trial']
    assert (status['listing_limit'],status['listings_used'],status['listings_remaining'])==(1,1,0)
    assert suite.db.fetchone("SELECT COUNT(*) FROM listings WHERE listing_id='denied'")[0]==0
    suite.db.execute("DELETE FROM listings WHERE listing_id='allowed'")
    suite.db.commit()
    with pytest.raises(TrialListingLimitError):insert_trial_listing(suite.db,'still-denied')


def test_unlimited_trial_and_edit_preserve_original_allowance(suite):
    created=create(suite,listing_limit=None)
    assert redeem(suite).status_code==200
    suite.actor['admin']=True
    assert suite.client.put('/v1/admin/trial-invitations/'+created['offer_id'],json={**created['config'],'listing_limit':1}).status_code==200
    for i in range(3):insert_trial_listing(suite.db,'unlimited-'+str(i))
    status=suite.client.get('/v1/me/trial-invitations').json()['trial']
    assert status['listing_limit'] is None and status['listings_used']==3 and status['listings_remaining'] is None


def test_concurrent_trial_listing_limit_is_atomic(suite):
    from app.db import TrialListingLimitError
    create(suite,listing_limit=1)
    assert redeem(suite).status_code==200
    def attempt(number):
        try:insert_trial_listing(suite.db,'race-'+str(number));return 'created'
        except TrialListingLimitError:return 'limited'
    with ThreadPoolExecutor(max_workers=2) as executor:outcomes=list(executor.map(attempt,[1,2]))
    assert sorted(outcomes)==['created','limited']
    assert suite.db.fetchone('SELECT COUNT(*) FROM invitation_trial_listing_usage')[0]==1


def test_failed_listing_insert_does_not_consume_trial_slot(suite):
    create(suite,listing_limit=1)
    assert redeem(suite).status_code==200
    values={'listing_id':'invalid','owner_subject':'member','condition':'Poor'}
    with pytest.raises((TypeError,ValueError)):
        suite.db.insert_listing(**values)
    assert suite.db.fetchone('SELECT COUNT(*) FROM invitation_trial_listing_usage')[0]==0
    insert_trial_listing(suite.db,'valid-after-failure')


def test_paid_upgrade_uses_paid_membership_not_old_trial_cap(suite):
    create(suite,listing_limit=1)
    assert redeem(suite).status_code==200
    insert_trial_listing(suite.db,'trial-slot')
    suite.db.set_billing_subscription('member',stripe_subscription_id='sub_paid',subscription_plan='pro_25',subscription_billing_cycle='monthly',subscription_status='active',subscription_renewal_date=None)
    insert_trial_listing(suite.db,'after-upgrade')
    assert suite.db.fetchone('SELECT COUNT(*) FROM invitation_trial_listing_usage')[0]==1


def test_api_reports_trial_listing_exhaustion_as_conflict(suite):
    create(suite,listing_limit=1)
    assert redeem(suite).status_code==200
    payload={'title':'Test shoes','category':'shoes','brand':'Example','condition':'LikeNew','size':'8','estimated_value':50}
    first=suite.client.post('/v1/listings',json=payload)
    assert first.status_code==200,first.text
    second=suite.client.post('/v1/listings',json=payload)
    assert second.status_code==409,second.text
    assert 'allowance' in second.json()['detail']


def test_renewing_trial_allowance_ends_with_original_trial(suite,monkeypatch):
    from app.db import TrialListingLimitError
    create(suite,listing_limit=1)
    assert redeem(suite).status_code==200
    suite.db.execute("UPDATE invitation_trial_redemptions SET state='converted',end_behavior='renew',stripe_subscription_id='sub_trial'")
    suite.db.commit()
    suite.db.set_billing_subscription('member',stripe_subscription_id='sub_trial',subscription_plan='starter_15',subscription_billing_cycle='monthly',subscription_status='trialing',subscription_renewal_date=None)
    insert_trial_listing(suite.db,'renewing-first')
    with pytest.raises(TrialListingLimitError):insert_trial_listing(suite.db,'renewing-denied')
    future=trials.now()+timedelta(days=31)
    monkeypatch.setattr(trials,'now',lambda:future)
    insert_trial_listing(suite.db,'after-trial-ended')
    assert suite.db.fetchone('SELECT COUNT(*) FROM invitation_trial_listing_usage')[0]==1
