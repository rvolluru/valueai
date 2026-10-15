export function mergeNotificationHistory(serverItems = [], localItems = []) {
  const ids = new Set(serverItems.map(item => item.notification_id));
  const signature = item => JSON.stringify([item.type, item.title, item.body, item.entity_id || '']);
  const signatures = new Set(serverItems.map(signature));
  const legacy = localItems.map(item => ({
    notification_id: item.serverId || `local:${item.id}`, local_id: item.id,
    local_only: !item.serverId, type: item.type, title: item.title, body: item.body,
    entity_id: item.entityId, action_tab: item.actionTab, created_at: item.createdAt,
    read_at: item.read ? item.createdAt : null,
  })).filter(item => !ids.has(item.notification_id) && !(item.local_only && signatures.has(signature(item))));
  return [...serverItems, ...legacy].sort((a, b) => (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0));
}
