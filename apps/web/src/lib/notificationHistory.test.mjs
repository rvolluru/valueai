import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeNotificationHistory } from './notificationHistory.mjs';

test('View All includes browser alerts when server history is empty', () => {
  const result = mergeNotificationHistory([], [{ id: 'legacy', title: 'Shipping label created', body: 'Ready', createdAt: '2026-10-14T01:00:00Z', actionTab: 'inbox', read: false }]);
  assert.equal(result.length, 1);
  assert.equal(result[0].local_only, true);
  assert.equal(result[0].action_tab, 'inbox');
  assert.equal(result[0].read_at, null);
});
test('server-backed bell alerts are not duplicated', () => {
  assert.equal(mergeNotificationHistory([{ notification_id: 'server' }], [{ id: 'server', serverId: 'server' }]).length, 1);
});
test('legacy and server copies of the same event are not duplicated', () => {
  const server = { notification_id: 'server', type: 'shipping', title: 'Ready', body: 'Label', entity_id: 'offer' };
  const local = { id: 'legacy', type: 'shipping', title: 'Ready', body: 'Label', entityId: 'offer' };
  assert.equal(mergeNotificationHistory([server], [local]).length, 1);
});
