import CityStateInput from './CityStateInput'
import { useEffect, useRef, useState } from 'react'

function BrandChoices({ label, value, onChange, brands, id, allowCustom = true, maxSelections = 5 }) {
  const noun = allowCustom ? 'brand' : 'size'
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const input = useRef(null)
  const query = search.trim()
  const selected = brand => value.some(item => item.toLowerCase() === brand.toLowerCase())
  const matches = brands.filter(brand => brand.toLowerCase().includes(query.toLowerCase()) && !selected(brand))
  const canAdd = allowCustom && query && !brands.some(brand => brand.toLowerCase() === query.toLowerCase()) && !selected(query)
  const options = [...matches.map(brand => ({ brand, custom: false })), ...(canAdd ? [{ brand: query, custom: true }] : [])]
  const expanded = open && (Boolean(query) || !allowCustom) && value.length < maxSelections
  function choose(brand) {
    if (value.length >= maxSelections || selected(brand)) return
    onChange([...value, brand]); setSearch(''); setActive(0); input.current?.focus()
  }
  function keyboard(event) {
    if (event.key === 'Escape') { setOpen(false); return }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); setOpen(true)
      const next = Math.max(0, Math.min(options.length - 1, active + (event.key === 'ArrowDown' ? 1 : -1)))
      setActive(next)
      document.getElementById(`${id}-option-${next}`)?.scrollIntoView({ block: 'nearest' })
    }
    if (event.key === 'Enter' && expanded) {
      event.preventDefault()
      if (options[active]) choose(options[active].brand)
    }
  }
  return <fieldset className="access-brands"><legend>{label} *</legend>
    <p className="access-help" id={`${id}-help`}>{allowCustom ? 'Type to find or add a brand, then select it.' : 'Type to filter sizes, then select one or more.'} {value.length}/{maxSelections} selected.</p>
    <div className="access-brand-combobox" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
      <div className="access-multiselect-input">
    <div className="access-selected access-input-tags" aria-live="polite">{value.map(brand => <button key={brand} type="button" onClick={() => { onChange(value.filter(item => item !== brand)); setSearch('') }} aria-label={`Remove ${brand} from ${label}`}>{brand} ×</button>)}</div>
      <input ref={input} role="combobox" aria-label={`Search ${label.toLowerCase()}`} aria-describedby={`${id}-help`} aria-autocomplete="list" aria-expanded={expanded} aria-controls={`${id}-options`} aria-activedescendant={expanded && options[active] ? `${id}-option-${active}` : undefined}
        placeholder={value.length >= maxSelections ? `${maxSelections} selected — remove one to change` : `Type a ${noun}${allowCustom ? ' name' : ''}`} maxLength={80} value={search} disabled={value.length >= maxSelections}
        onFocus={() => setOpen(true)} onKeyDown={keyboard} onChange={event => { setSearch(event.target.value); setActive(0); setOpen(true) }} autoComplete="off" />
      </div>
      {expanded && <div className="access-brand-dropdown" id={`${id}-options`} role="listbox" aria-label={label} aria-multiselectable="true">
        {options.map((option, index) => <button key={option.brand} id={`${id}-option-${index}`} role="option" aria-selected={false} className={active === index ? 'highlighted' : ''} tabIndex={-1} type="button"
          onMouseDown={event => event.preventDefault()} onMouseEnter={() => setActive(index)} onClick={() => choose(option.brand)}>{option.custom ? `Add “${option.brand}”` : option.brand}</button>)}
        {!options.length && <p>No unselected {noun}s found.</p>}
      </div>}
    </div>
  </fieldset>
}

export default function AccessRequestPage({ apiBaseUrl }) {
  const [options, setOptions] = useState(null)
  const [form, setForm] = useState({ first_name: '', email: '', city: '', state: '', clothing_size: [], shoe_size: [], owned_brands: [], wanted_brands: [], listing_quantity: '', typical_value: '', email_consent: false, website: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [success, setSuccess] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError('')
    fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/access-request-options`, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw Error('Unable to load the form. Please try again.')
      setOptions(await response.json())
    }).catch(error => { if (error.name !== 'AbortError') setError(error.message) })
    return () => controller.abort()
  }, [apiBaseUrl, retry])
  const field = (key, value) => setForm(current => ({ ...current, [key]: value }))
  async function submit(event) {
    event.preventDefault(); setError('')
    if (!form.city || !form.state) { setError('Choose your city and state from the location suggestions.'); return }
    if (!form.clothing_size.length || !form.shoe_size.length) { setError('Choose at least one clothing size and one shoe size.'); return }
    if (!form.owned_brands.length || !form.wanted_brands.length) { setError('Choose at least one brand you own and one brand you would want.'); return }
    setBusy(true)
    try {
      const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/access-requests`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) })
      const result = await response.json()
      if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : 'Please check your answers and try again.')
      setSuccess(true)
    } catch (error) { setError(error.message || 'Unable to submit. Please try again.') } finally { setBusy(false) }
  }
  const select = (key, label, choices) => <label><span>{label} *</span><select required value={form[key]} onChange={event => field(key, event.target.value)}><option value="">Select an option</option>{choices.map(value => <option key={value}>{value}</option>)}</select></label>
  return <main className="access-request-page">
    <header><a className="access-wordmark" href="/">JOUFT<sup>™</sup></a><a href="/">Back to home</a></header>
    <section className="access-request-card">
      <p className="eyebrow">JOIN THE COMMUNITY</p><h1 className="waitlist-logo-font">Join waiting list</h1>
      {success ? <div role="status"><h2>Thank you for your interest.</h2><p>We’ve received your request and will contact you about access to Jouft.</p><a className="primary" href="/">Back to home</a></div> : <>
        <p>Tell us a little about yourself and the pieces you’d love to trade.</p><p className="access-help">All fields marked * are required. Submitting a request does not create an account or guarantee an invitation.</p>
        {error && <p className="error-text" role="alert">{error}</p>}
        {!options ? <div>{error ? <button type="button" onClick={() => setRetry(value => value + 1)}>Try again</button> : <p role="status">Loading form…</p>}</div> : <form onSubmit={submit}>
          <fieldset disabled={busy} className="access-form-fields"><legend className="access-sr-only">Access request details</legend>
          <div className="field-grid two">
            <label><span>First name *</span><input required autoComplete="given-name" maxLength={100} value={form.first_name} onChange={event => field('first_name', event.target.value)} /></label>
            <label><span>Email *</span><input required type="email" autoComplete="email" maxLength={254} value={form.email} onChange={event => field('email', event.target.value)} /></label>
            <CityStateInput apiBaseUrl={apiBaseUrl} onChange={(city, state) => setForm(current => ({ ...current, city, state }))} />
            <BrandChoices id="clothing-sizes" label="Clothing sizes" value={form.clothing_size} brands={options.clothing_sizes} allowCustom={false} maxSelections={options.clothing_sizes.length} onChange={value => field('clothing_size', value)} />
            <BrandChoices id="shoe-sizes" label="Shoe sizes (US)" value={form.shoe_size} brands={options.shoe_sizes} allowCustom={false} maxSelections={options.shoe_sizes.length} onChange={value => field('shoe_size', value)} />
          </div>
          <div className="field-grid two access-brand-grid">
            <BrandChoices id="owned-brands" label="Brands you own and would trade" value={form.owned_brands} brands={options.brands} onChange={value => field('owned_brands', value)} />
            <BrandChoices id="wanted-brands" label="Brands you’d want" value={form.wanted_brands} brands={options.brands} onChange={value => field('wanted_brands', value)} />
          </div>
          <div className="field-grid two">
            {select('listing_quantity', 'Pieces you could see yourself listing', options.listing_quantities)}
            {select('typical_value', 'Typical value of pieces you’d trade', options.typical_values)}
          </div>
          <div className="access-honeypot" aria-hidden="true"><label>Website<input tabIndex={-1} autoComplete="off" value={form.website} onChange={event => field('website', event.target.value)} /></label></div>
          <label className="access-consent"><input required type="checkbox" checked={form.email_consent} onChange={event => field('email_consent', event.target.checked)} /><span>{options.consent_text} *</span></label>
          <p className="access-help">See our <a href="/privacy">Privacy Policy</a> for how we handle your information.</p>
          <button className="primary waitlist-logo-font" disabled={busy}>{busy ? 'Submitting…' : 'Join waiting list'}</button>
          </fieldset>
        </form>}
      </>}
    </section>
  </main>
}
