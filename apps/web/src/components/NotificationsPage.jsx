import { useEffect, useState } from 'react'
import { mergeNotificationHistory } from '../lib/notificationHistory.mjs'

export default function NotificationsPage({ load, markRead, onOpen, onBack, localItems = [], markLocalRead }) {
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [more, setMore] = useState(false)
  const history = mergeNotificationHistory(items, localItems)
  async function fetchPage(reset = false) {
    setBusy(true); setError('')
    try {
      const result = await load(reset ? 0 : items.length)
      setItems(previous => reset ? result.items : [...previous, ...result.items.filter(item => !previous.some(old => old.notification_id === item.notification_id))])
      setMore(Boolean(result.has_more))
    } catch { setError('Unable to load notifications. Please try again.') }
    finally { setBusy(false) }
  }
  useEffect(() => { fetchPage(true) }, [])
  async function open(item) {
    try {
      if (!item.read_at) {
        if (item.local_only) markLocalRead?.(item.local_id)
        else await markRead(item.notification_id)
      }
      setItems(previous => previous.map(old => old.notification_id === item.notification_id ? { ...old, read_at: new Date().toISOString() } : old))
      if (item.action_tab) onOpen(item)
    } catch { setError('Unable to update this notification. Please try again.') }
  }
  return <section className="panel notifications-history"><div className="panel-header"><div><p className="eyebrow">Your activity</p><h2>Notifications</h2></div><div className="header-actions"><button className="ghost" onClick={onBack}>Back</button><button className="ghost" disabled={busy} onClick={() => fetchPage(true)}>Refresh</button></div></div>
    <p>Trade updates, listing activity, and shipping notifications—all in one place.</p>
    {error && <p role="alert">{error}</p>}
    {!busy && !history.length && !error && <p>No notifications yet. Your updates will appear here.</p>}
    <div className="notification-history-list">{history.map(item => <button type="button" key={item.notification_id} className={`notification-history-item ${item.read_at ? '' : 'unread'}`} onClick={() => open(item)}>
      <div><strong>{item.title}</strong>{!item.read_at && <span className="notification-unread-label">Unread</span>}</div><p>{item.body}</p><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time>
    </button>)}</div>
    {busy && <p role="status">Loading notifications…</p>}
    {more && <button className="ghost" disabled={busy} onClick={() => fetchPage()}>Load older notifications</button>}
  </section>
}
