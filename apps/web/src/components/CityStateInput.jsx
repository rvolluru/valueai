import { useEffect, useState } from 'react'

export default function CityStateInput({ apiBaseUrl, onChange }) {
  const [text, setText] = useState('')
  const [selected, setSelected] = useState(false)
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [active, setActive] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    setItems([]); setError(''); setLoading(false)
    if (selected || text.trim().length < 3) return
    const controller = new AbortController()
    setLoading(true)
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/google/places/city-suggest?q=${encodeURIComponent(text.trim())}`, { signal: controller.signal })
        const data = await response.json()
        if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'City search is unavailable. Please try again.')
        if (!controller.signal.aborted) { setItems(data.suggestions || []); setActive(0) }
      } catch (error) { if (!controller.signal.aborted) setError(error.message) }
      finally { if (!controller.signal.aborted) setLoading(false) }
    }, 300)
    return () => { clearTimeout(timer); controller.abort() }
  }, [text, selected, apiBaseUrl])
  function choose(item) { setText(item.label); setSelected(true); setOpen(false); onChange(item.city, item.state) }
  const expanded = open && !selected && text.trim().length >= 3
  return <div className="access-city-field" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
    <label htmlFor="access-city-state"><span>City / State *</span></label>
    <div className="access-brand-combobox">
      <input id="access-city-state" required role="combobox" autoComplete="off" maxLength={120} placeholder="Start typing your city" value={text} aria-autocomplete="list" aria-expanded={expanded} aria-controls="access-city-options" aria-describedby="access-city-help" aria-activedescendant={expanded && items[active] ? `access-city-${active}` : undefined}
        onFocus={() => setOpen(true)} onChange={event => { setText(event.target.value); setSelected(false); setOpen(true); onChange('', '') }}
        onKeyDown={event => {
          if (event.key === 'Escape') setOpen(false)
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setOpen(true); setActive(value => Math.max(0, Math.min(items.length - 1, value + (event.key === 'ArrowDown' ? 1 : -1)))) }
          if (event.key === 'Enter' && expanded) { event.preventDefault(); if (items[active]) choose(items[active]) }
        }} />
      {expanded && <div className="access-brand-dropdown" id="access-city-options" role="listbox" aria-label="City and state suggestions">
        {loading ? <p role="status">Searching cities…</p> : error ? <p role="alert">{error}</p> : items.length ? items.map((item, index) => <button type="button" role="option" aria-selected={false} id={`access-city-${index}`} key={item.label} tabIndex={-1} className={active === index ? 'highlighted' : ''} onMouseDown={event => event.preventDefault()} onClick={() => choose(item)}>{item.label}</button>) : <p>No cities found. Try adding the state name.</p>}
        <div className="access-places-attribution"><img src="https://maps.gstatic.com/mapfiles/api-3/images/powered-by-google-on-white3.png" alt="Powered by Google" /></div>
      </div>}
    </div>
    <p className="access-help" id="access-city-help">{selected ? 'City and state selected.' : 'Type at least 3 characters, then choose a US city from the suggestions.'}</p>
  </div>
}
