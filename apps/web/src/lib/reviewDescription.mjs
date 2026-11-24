// Remove only standalone facts already displayed in the review summary.
// Keep sentences containing additional details, especially wear or damage.
export function reviewDescription(description, { title, brand, condition, size, price, model } = {}) {
  const normalize = value => String(value ?? '').toLowerCase().replace(/[’']/g, '').replace(/[^a-z0-9]+/g, ' ').trim()
  const facts = new Set([title, brand, condition, size, price, model, brand && model ? `${brand} ${model}` : ''].map(normalize).filter(Boolean))
  const conditionFact = normalize(condition)
  if (conditionFact === 'new with tags') facts.add('its new with tags')
  if (conditionFact === 'new') facts.add('its new')
  if (conditionFact === 'like new') { facts.add('its in like new condition'); facts.add('like new condition') }
  const seen = new Set()
  return String(description || '').split(/\n+|(?<=[.!?])\s+/).map(part => part.trim()).filter(part => {
    const bare = part.replace(/^\s*(?:brand|product title|title|product|price|estimated value|condition|size|user name|seller)\s*:\s*/i, '')
    const key = normalize(bare)
    if (!key || facts.has(key) || seen.has(key)) return false
    seen.add(key)
    return true
  }).join('\n\n')
}
