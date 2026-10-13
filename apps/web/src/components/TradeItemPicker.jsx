import { useState } from 'react'

export default function TradeItemPicker({ offer, items, loading, error, selectedId, onSelect, onDetails, onConfirm, onClose }) {
  const [imageIndices, setImageIndices] = useState({})
  const selected = items.find((item) => String(item.listing_id || item.id) === selectedId)
  return <section className="trade-picker-page" aria-labelledby="trade-picker-title">
      <div className="panel-header"><h2 id="trade-picker-title">Sender’s eligible items</h2><button className="ghost" onClick={onClose}>Back to inbox</button></div>
      <p>They want your <strong>{offer.target_listing?.title}</strong>. Choose one item to receive in exchange.</p>
      {error && <p role="alert">{error}</p>}
      {loading && <p role="status">Loading eligible items…</p>}
      {!loading && !error && items.length === 0 && <p>No eligible items are currently available. The sender’s listings may have changed.</p>}
      <div className="trade-picker-list">{items.map((item) => {
        const id = String(item.listing_id || item.id)
        const images = (Array.isArray(item.images) ? item.images : []).map((image) => typeof image === 'string' ? image : image?.d_img || image?.p_img).filter(Boolean)
        if (!images.length && item.image) images.push(item.image)
        const index = Math.min(imageIndices[id] || 0, Math.max(0, images.length - 1))
        return <article key={id} className={`trade-picker-item listing-review-layout ${id === selectedId ? 'selected' : ''}`}>
          <div className={`listing-review-gallery ${images.length <= 1 ? 'single-image' : ''}`}>
            {images.length > 1 && <div className="listing-review-thumbnails" aria-label={`${item.title} image thumbnails`}>
              {images.map((src, i) => <button key={`${id}-${i}`} type="button" className={i === index ? 'active' : ''} aria-label={`Show ${item.title} image ${i + 1}`} aria-current={i === index ? 'true' : undefined} onClick={() => setImageIndices((prev) => ({ ...prev, [id]: i }))}><img src={src} alt="" /></button>)}
            </div>}
            {images[index] ? <img src={images[index]} alt={`${item.title || 'Sender item'} image ${index + 1}`} /> : <div className="listing-image-fallback">Image unavailable</div>}
          </div>
          <div className="listing-review-details">
            <h2>{item.title || 'Untitled listing'}</h2>
            <p className="editorial-meta">EST. ${Number(item.estimated_value || 0).toFixed(2)} · {item.brand || 'Unknown brand'} · {item.condition || 'Not provided'} · SIZE {item.size || 'Not provided'}</p>
            <p className="listing-review-description">{item.description || 'No description provided.'}</p>
            <div className="button-row listing-review-actions">
              <button className="ghost" type="button" onClick={() => onDetails(item)}>Open full listing</button>
              <button className="primary" type="button" aria-pressed={id === selectedId} disabled={loading} onClick={() => onSelect(id)}>{id === selectedId ? 'Selected' : 'Select for exchange'}</button>
            </div>
          </div>
        </article>
      })}</div>
      {selected && <div className="trade-picker-summary"><h3>Confirm your exchange selection</h3><p>Your {offer.target_listing?.title} ↔ Their {selected.title}</p><p>The sender will review and accept your selection. This does not finalize the trade.</p><button className="primary" disabled={loading} onClick={onConfirm}>{loading ? 'Submitting…' : 'Confirm selection'}</button></div>}
  </section>
}
