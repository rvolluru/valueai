export function defaultUsername(firstName, lastName) {
  return [firstName, lastName].map(value => String(value || '').trim()).filter(Boolean).join('_')
    .normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40) || ''
}
