import { useEffect, useState } from 'react'
export default function AdminAccessRequests({ apiBaseUrl, getToken }) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [offset, setOffset] = useState(0)
  const [downloading, setDownloading] = useState(false)
  async function downloadCsv() {
    setDownloading(true); setError('')
    try {
      const token = await getToken?.()
      const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/admin/access-requests/export.csv`, { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw Error('Unable to download access requests.')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a'); link.href = url; link.download = 'jouft-access-requests.csv'
      document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) { setError(error.message) } finally { setDownloading(false) }
  }
  useEffect(() => { let current = true; setData(null); setError(''); (async () => {
    try {
      const token = await getToken?.()
      const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/admin/access-requests?limit=50&offset=${offset}`, { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) throw Error('Unable to load access requests.')
      const result = await response.json(); if (current) setData(result)
    } catch (error) { if (current) setError(error.message) }
  })(); return () => { current = false } }, [apiBaseUrl, getToken, offset])
  return <section><h3>Access requests</h3><button type="button" className="ghost" disabled={downloading} onClick={downloadCsv}>{downloading ? 'Downloading…' : 'Download CSV'}</button>{error && <p role="alert">{error}</p>}{!data && !error && <p role="status">Loading requests…</p>}
    {data && <><p>{data.total} requests</p>{data.items.map(item => <article className="admin-card" key={item.request_id}><h4>{item.first_name} · {item.email}</h4><p>{item.city}, {item.state} · Clothing {[].concat(item.clothing_size || []).join(', ')} · US shoe {[].concat(item.shoe_size || []).join(', ')}</p><p>Owns: {item.owned_brands.join(', ')}</p><p>Wants: {item.wanted_brands.join(', ')}</p><p>{item.listing_quantity} pieces · {item.typical_value}</p><p>Submitted {new Date(item.created_at).toLocaleString()} · Last submitted {new Date(item.updated_at).toLocaleString()}</p><p>Email consent recorded {new Date(item.consent_at).toLocaleString()}</p></article>)}
      <button disabled={!offset} onClick={() => setOffset(value => Math.max(0, value - 50))}>Previous</button><button disabled={offset + 50 >= data.total} onClick={() => setOffset(value => value + 50)}>Next</button></>}
  </section>
}
