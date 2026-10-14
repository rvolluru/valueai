import { useEffect, useRef, useState } from 'react'
import { cropPixels } from '../../../../packages/app-client/src/photoEdits'

const full = { x: 0, y: 0, width: 100, height: 100 }
export default function ListingPhotoEditor({ src, onCancel, onApply }) {
  const image = useRef(null)
  const [angle, setAngle] = useState(0)
  const [crop, setCrop] = useState(full)
  const [zoom, setZoom] = useState(1)
  const [preview, setPreview] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  function rotatedCanvas(original, rotation) {
    const canvas = document.createElement('canvas')
    const sideways = rotation % 180 !== 0
    canvas.width = sideways ? original.naturalHeight : original.naturalWidth
    canvas.height = sideways ? original.naturalWidth : original.naturalHeight
    const ctx = canvas.getContext('2d')
    ctx.translate(canvas.width / 2, canvas.height / 2); ctx.rotate(rotation * Math.PI / 180)
    ctx.drawImage(original, -original.naturalWidth / 2, -original.naturalHeight / 2)
    return canvas
  }
  useEffect(() => {
    let active = true
    let objectUrl
    const controller = new AbortController()
    setPreview(''); setError(''); image.current = null
    async function load() {
      try {
        // Do not reuse the gallery's opaque/non-CORS image cache entry (notably Safari).
        // Decode a freshly fetched blob so the canvas remains origin-clean.
        const response = await fetch(src, { mode: 'cors', cache: 'no-store', signal: controller.signal })
        if (!response.ok) throw new Error('Photo request failed')
        const blob = await response.blob()
        if (!blob.type.startsWith('image/')) throw new Error('Response is not an image')
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        const original = new Image()
        original.onload = () => {
          if (!active) return
          image.current = original
          try { setPreview(rotatedCanvas(original, 0).toDataURL('image/jpeg', .95)) }
          catch { setError('Unable to decode this photo. Your original is unchanged.') }
        }
        original.onerror = () => { if (active) setError('Unable to decode this photo. Your original is unchanged.') }
        original.src = objectUrl
      } catch (error) {
        if (active && error.name !== 'AbortError') setError('Unable to load this photo for editing. Your original is unchanged. Please retry.')
      }
    }
    load()
    return () => { active = false; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [src])
  useEffect(() => {
    if (image.current) setPreview(rotatedCanvas(image.current, angle).toDataURL('image/jpeg', .95))
  }, [angle])
  async function save() {
    setBusy(true); setError('')
    try {
      const source = rotatedCanvas(image.current, angle)
      const box = cropPixels(source.width, source.height, crop)
      const canvas = document.createElement('canvas'); canvas.width = box.width; canvas.height = box.height
      canvas.getContext('2d').drawImage(source, box.originX, box.originY, box.width, box.height, 0, 0, box.width, box.height)
      const blob = await new Promise((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('Unable to encode photo')), 'image/jpeg', .95))
      await onApply(new File([blob], `edited-${Date.now()}.jpg`, { type: 'image/jpeg' }))
    } catch { setError('Unable to save photo edits. Your original is unchanged. Please retry.') }
    finally { setBusy(false) }
  }
  return <div className="photo-editor-backdrop"><section className="photo-editor" role="dialog" aria-modal="true" aria-label="Edit listing photo" onKeyDown={e => { if (e.key === 'Escape' && !busy) onCancel() }}>
    <header><h2>Edit photo</h2><button autoFocus disabled={busy} onClick={onCancel}>Cancel</button></header>
    <p>Zoom to inspect. Adjust the crop box, then use the photo. Save the listing to apply your edits.</p>
    <div className="photo-editor-preview"><div style={{ position: 'relative', width: `${zoom * 100}%`, minWidth: '100%' }}>
      {preview && <img src={preview} alt="Photo crop preview" style={{ width: '100%', display: 'block' }} />}
      <div style={{ position: 'absolute', border: '2px solid white', boxShadow: '0 0 0 1px #64141f', left: `${crop.x}%`, top: `${crop.y}%`, width: `${crop.width}%`, height: `${crop.height}%`, pointerEvents: 'none', boxSizing: 'border-box' }} />
    </div></div>
    <div className="photo-editor-tools"><button disabled={busy || !preview} onClick={() => setZoom(z => Math.max(1, z - .5))}>Zoom −</button><button disabled={busy || !preview} onClick={() => setZoom(z => Math.min(3, z + .5))}>Zoom +</button><button disabled={busy || !preview} onClick={() => { setAngle(a => (a + 90) % 360); setCrop(full) }}>Rotate 90°</button><button disabled={busy || !preview} onClick={() => { setAngle(0); setCrop(full); setZoom(1) }}>Reset</button></div>
    {Object.keys(full).map(key => <label className="photo-editor-crop" key={key}>{({x:'Left', y:'Top',width:'Width',height:'Height'})[key]} {crop[key]}%
      <input type="range" disabled={busy} min={key === 'x' || key === 'y' ? 0 : 1} max={key === 'x' ? 100 - crop.width : key === 'y' ? 100 - crop.height : key === 'width' ? 100 - crop.x : 100 - crop.y} value={crop[key]} onChange={e => setCrop(c => ({ ...c, [key]: Number(e.target.value) }))} />
    </label>)}
    {error && <p role="alert">{error}</p>}<button className="primary" disabled={busy || !preview} onClick={save}>{busy ? 'Saving…' : 'Use photo'}</button>
  </section></div>
}
