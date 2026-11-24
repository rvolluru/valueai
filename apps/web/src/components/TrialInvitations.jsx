import { useCallback, useEffect, useState } from 'react'

const initialOffer = { name: '', code: '', plan: 'starter_15', duration_days: 30, listing_limit: 25, require_card: false, end_behavior: 'expire', billing_cycle: 'monthly', max_redemptions: 100, starts_at: '', expires_at: '', allowed_emails: '', allowed_domains: '', first_trial_only: true, new_subscribers_only: true }

export default function TrialInvitations({ admin = false, apiBaseUrl = '', apiKey = '', getToken, onChanged }) {
  const [offers, setOffers] = useState([])
  const [form, setForm] = useState(initialOffer)
  const [code, setCode] = useState(() => new URLSearchParams(window.location.search).get('invitation') || '')
  const [offer, setOffer] = useState(null)
  const [trial, setTrial] = useState(null)
  const [consent, setConsent] = useState(false)
  const [issued, setIssued] = useState(null)
  const [editing, setEditing] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const request = useCallback(async (path, body, method = body ? 'POST' : 'GET') => {
    const token = getToken ? await getToken() : null
    const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}${path}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : apiKey ? { 'x-api-key': apiKey } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the invitation settings and try again.')
    return data
  }, [apiBaseUrl, apiKey, getToken])
  async function refresh() {
    const data = await request(admin ? '/v1/admin/trial-invitations' : '/v1/me/trial-invitations')
    if (admin) setOffers(data.offers)
    else setTrial(data.trial)
  }
  async function action(fn) {
    setBusy(true); setError(''); setMessage('')
    try { await fn() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  useEffect(() => {
    let mounted = true
    const load = async () => {
      try {
        const params = new URLSearchParams(window.location.search)
        const session = params.get('trial_session_id')
        if (!admin && session) await request('/v1/me/trial-invitations/sync', { session_id: session })
        const data = await request(admin ? '/v1/admin/trial-invitations' : '/v1/me/trial-invitations')
        if (mounted) { if (admin) setOffers(data.offers); else setTrial(data.trial) }
      } catch (e) { if (mounted) setError(e.message) }
    }
    load(); return () => { mounted = false }
  }, [admin, request])
  async function create(event) {
    event.preventDefault()
    await action(async () => {
      const body = { ...form, duration_days: Number(form.duration_days), listing_limit: form.listing_limit === null ? null : Number(form.listing_limit), max_redemptions: Number(form.max_redemptions), starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null, expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null, allowed_emails: form.allowed_emails.split(/[\n,]+/).map(v => v.trim()).filter(Boolean), allowed_domains: form.allowed_domains.split(/[\n,]+/).map(v => v.trim()).filter(Boolean) }
      if (!body.code || editing) delete body.code
      const result = await request(editing ? `/v1/admin/trial-invitations/${editing}` : '/v1/admin/trial-invitations', body, editing ? 'PUT' : 'POST')
      if (!editing) setIssued(result)
      else setMessage('Settings updated for future redemptions. Existing trials keep their original terms.')
      await refresh(); setForm(initialOffer); setEditing(null)
    })
  }
  const field = (key, value) => setForm(old => ({ ...old, [key]: value }))
  return <section className="trial-invitations" aria-label={admin ? 'Manage trial invitations' : 'Invitation trial'}>
    <h3>{admin ? 'Trial invitations' : 'Have a trial invitation?'}</h3>
    {error && <p role="alert" className="error-text">{error}</p>}
    {message && <p role="status">{message}</p>}
    {admin ? <>
      <form onSubmit={create} className="trial-invitation-form">
        <fieldset className="trial-form-section"><legend>Offer details</legend><div className="trial-form-grid">
        <label>Offer name<input required maxLength={100} value={form.name} onChange={e => field('name', e.target.value)} /></label>
        {!editing && <label>Code (blank generates one)<input minLength={6} maxLength={64} pattern="[A-Za-z0-9-]+" value={form.code} onChange={e => field('code', e.target.value)} /></label>}
        <label>Membership plan<select value={form.plan} onChange={e => field('plan', e.target.value)}><option value="starter_15">Starter</option><option value="pro_25">Pro</option></select></label>
        <label>Trial days<input required type="number" min={1} max={365} value={form.duration_days} onChange={e => field('duration_days', e.target.value)} /></label>
        </div></fieldset>
        <fieldset className="trial-form-section"><legend>Listing allowance</legend><div className="trial-listing-limit">
        <label className="trial-checkbox"><input type="checkbox" checked={form.listing_limit === null} onChange={e => field('listing_limit', e.target.checked ? null : 1)} /> Unlimited new listings during trial</label>
        {form.listing_limit !== null && <label>New listings allowed (total for the trial)<input required type="number" min={1} max={2147483647} step={1} value={form.listing_limit} onChange={e => field('listing_limit', e.target.value)} /></label>}
        </div></fieldset>
        <fieldset className="trial-form-section"><legend>Card and renewal</legend><div className="trial-form-grid">
        <label>After the trial<select value={form.end_behavior} onChange={e => setForm(old => ({ ...old, end_behavior: e.target.value, require_card: e.target.value === 'renew' || old.require_card }))}><option value="expire">Expire without charging</option><option value="renew">Renew through Stripe with user consent</option></select></label>
        <label>Renewal cycle<select disabled={form.end_behavior !== 'renew'} value={form.billing_cycle} onChange={e => field('billing_cycle', e.target.value)}><option value="monthly">Monthly</option><option value="annual">Annual</option></select></label>
        <label className="trial-checkbox"><input type="checkbox" checked={form.require_card} disabled={form.end_behavior === 'renew'} onChange={e => field('require_card', e.target.checked)} /> Require a card before access starts</label>
        </div></fieldset>
        <fieldset className="trial-form-section"><legend>Redemption availability</legend><div className="trial-form-grid">
        <label>Total redemptions<input required type="number" min={1} max={100000} value={form.max_redemptions} onChange={e => field('max_redemptions', e.target.value)} /></label>
        <label>Redemption opens (your local time)<input type="datetime-local" value={form.starts_at} onChange={e => field('starts_at', e.target.value)} /></label>
        <label>Redemption expires (your local time)<input type="datetime-local" value={form.expires_at} onChange={e => field('expires_at', e.target.value)} /></label>
        </div></fieldset>
        <fieldset className="trial-form-section"><legend>Who can redeem</legend><p className="trial-field-help">Leave both email lists blank to allow any verified email. Separate entries with commas.</p><div className="trial-form-grid">
        <label>Allowed verified emails<textarea value={form.allowed_emails} onChange={e => field('allowed_emails', e.target.value)} /></label>
        <label>Allowed email domains<textarea value={form.allowed_domains} onChange={e => field('allowed_domains', e.target.value)} /></label>
        </div><div className="trial-form-options">
        <label className="trial-checkbox"><input type="checkbox" checked={form.first_trial_only} onChange={e => field('first_trial_only', e.target.checked)} /> First invitation trial only</label>
        <label className="trial-checkbox"><input type="checkbox" checked={form.new_subscribers_only} onChange={e => field('new_subscribers_only', e.target.checked)} /> New subscribers only</label>
        </div></fieldset>
        <div className="trial-form-footer"><p>Trial benefits apply to membership only. Shipping and trade charges are separate. Existing paid subscriptions cannot be replaced by a trial.</p>
        <button className="primary" disabled={busy}>{editing ? 'Save invitation settings' : 'Create invitation'}</button>
        {editing && <button type="button" className="ghost" onClick={() => { setEditing(null); setForm(initialOffer) }}>Cancel editing</button>}
        </div>
      </form>
      {issued && <div role="status"><strong>Save this code—it is shown only once:</strong><p><code>{issued.code}</code></p><input aria-label="Invitation link to copy" readOnly value={`${window.location.origin}/?tab=profile&invitation=${encodeURIComponent(issued.code)}`} /></div>}
      {offers.map(entry => <article className="admin-card" key={entry.offer_id}>
        <h4>{entry.config.name} · …{entry.code_hint}</h4>
        <button className="ghost" disabled={busy} onClick={() => { const localDate = value => { if (!value) return ''; const date = new Date(value); return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16) }; setEditing(entry.offer_id); setForm({ ...entry.config, listing_limit: entry.config.listing_limit ?? null, code: '', starts_at: localDate(entry.config.starts_at), expires_at: localDate(entry.config.expires_at), allowed_emails: entry.config.allowed_emails.join(', '), allowed_domains: entry.config.allowed_domains.join(', ') }); setIssued(null) }}>Edit settings</button>
        <p>{entry.config.plan} · {entry.config.duration_days} days · {entry.config.listing_limit == null ? 'Unlimited listings' : `${entry.config.listing_limit} new listings total`} · {entry.config.require_card ? 'Card required' : 'No card'} · {entry.config.end_behavior === 'renew' ? 'Renews' : 'Expires without charge'}</p>
        <p>{entry.redemptions.filter(r => ['active','converted','pending','revoked'].includes(r.state)).length} / {entry.config.max_redemptions} places used or reserved · {entry.active ? 'Enabled' : 'Disabled'}</p>
        <button className="ghost" disabled={busy} onClick={() => action(async () => { await request(`/v1/admin/trial-invitations/${entry.offer_id}`, { active: !entry.active }, 'PATCH'); await refresh() })}>{entry.active ? 'Disable new redemptions' : 'Enable new redemptions'}</button>
        <details><summary>Redemption history</summary><ul>{entry.redemptions.map(r => <li key={r.redemption_id}>{r.email} · {r.access_status || r.state} · {r.ends_at ? new Date(r.ends_at).toLocaleString() : 'Awaiting checkout'}{r.end_behavior === 'expire' && r.access_status === 'active' && <button className="ghost small" disabled={busy} onClick={() => action(async () => { await request(`/v1/admin/trial-invitations/redemptions/${r.redemption_id}/revoke`, {}); await refresh() })}>End trial now</button>}</li>)}</ul></details>
        <details><summary>Admin activity</summary><ul>{(entry.audit || []).map(event => <li key={event.audit_id}>{event.action} · {event.actor_subject} · {new Date(event.created_at).toLocaleString()}</li>)}</ul></details>
      </article>)}
    </> : <>
      {trial && <p role="status">{trial.plan} trial active until {new Date(trial.ends_at).toLocaleString()}. {trial.end_behavior === 'expire' ? 'No automatic charge.' : ''} {trial.listing_limit == null ? 'Unlimited new listings during the trial.' : `${trial.listings_used} of ${trial.listing_limit} new listings used; ${trial.listings_remaining} remaining.`}</p>}
      <form onSubmit={e => { e.preventDefault(); action(async () => { setOffer(await request('/v1/me/trial-invitations/preview', { code })); setConsent(false) }) }}>
        <label>Invitation code<input value={code} required minLength={6} maxLength={64} autoCapitalize="characters" onChange={e => { setCode(e.target.value); setOffer(null); setConsent(false) }} /></label>
        <button className="ghost" disabled={busy}>Check invitation</button>
      </form>
      {offer && <div><p>{offer.summary}</p><label><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /> I have reviewed and agree to these trial terms{offer.end_behavior === 'renew' ? ' and recurring charges after the trial until canceled' : ''}.</label>
        <button className="primary" disabled={busy || !consent} onClick={() => action(async () => {
          const result = await request('/v1/me/trial-invitations/redeem', { code, consent, offer_version: offer.offer_version })
          if (result.checkout_url) { window.location.assign(result.checkout_url); return }
          setMessage(result.status === 'already_redeemed' ? 'This invitation has already been redeemed.' : 'Your membership trial is active.'); setOffer(null); await refresh(); await onChanged?.()
        })}>{offer.require_card ? 'Continue to secure card setup' : 'Start trial'}</button>
      </div>}
      <button type="button" className="ghost small" disabled={busy} onClick={() => action(async () => { const session = new URLSearchParams(window.location.search).get('trial_session_id'); if (session) await request('/v1/me/trial-invitations/sync', { session_id: session }); await refresh(); await onChanged?.(); setMessage('Trial status refreshed.') })}>Refresh trial status</button>
    </>}
  </section>
}
