export default function PhotoNavigation({ index, count, onChange }) {
  if (count < 2) return null
  return <div className="inline-photo-navigation" aria-label="Photo navigation">
    <button type="button" aria-label="Previous photo" disabled={index <= 0} onClick={() => onChange(Math.max(0, index - 1))}>‹</button>
    <span className="inline-photo-count" aria-live="polite">{index + 1} / {count}</span>
    <button type="button" aria-label="Next photo" disabled={index >= count - 1} onClick={() => onChange(Math.min(count - 1, index + 1))}>›</button>
  </div>
}
