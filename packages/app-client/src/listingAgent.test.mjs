import test from 'node:test';
import assert from 'node:assert/strict';
import { createListingAgentController } from './listingAgent.js';

function setup(overrides = {}) {
  const session = { session_id: 'one', revision: 4, stage: 'collecting', messages: [], photos: [] };
  let view;
  const client = {
    getActiveListingAgentSession: async () => ({ session }),
    getListingAgentSession: async () => session,
    turnWithListingAgent: async () => session,
    ...overrides,
  };
  return { controller: createListingAgentController(client, async () => ({ bearerToken: 'token' }), next => { view = next; }),
    get view() { return view; }, session };
}

test('network retry reuses exact message ID, revision and payload', async () => {
  const calls = [];
  const fixture = setup({ turnWithListingAgent: async (id, payload) => {
    calls.push({ id, payload });
    if (calls.length === 1) throw new Error('Connection lost after server commit');
    return { session_id: 'one', revision: 9 };
  } });
  await fixture.controller.load();
  await fixture.controller.send('New, size M');
  assert.match(fixture.view.error, /Connection lost/);
  await fixture.controller.retry();
  assert.deepEqual(calls[0], calls[1]);
  assert.equal(fixture.view.session.revision, 9);
});

test('confirmation sends only the server-issued version token', async () => {
  const calls = [];
  const fixture = setup({ turnWithListingAgent: async (id, payload) => { calls.push(payload); return fixture.session; } });
  fixture.session.pending = { type: 'confirm_analysis', token: 'exact-photo-facts-version' };
  await fixture.controller.load();
  await fixture.controller.confirm();
  assert.equal(calls[0].confirmation_token, 'exact-photo-facts-version');
  assert.equal(calls[0].expected_revision, 4);
  assert.equal('workflow_stage' in calls[0], false);
});

test('revision conflict reloads saved state and never silently rebases a mutation', async () => {
  let mutations = 0;
  const fixture = setup({
    turnWithListingAgent: async () => { mutations++; throw Object.assign(new Error('Changed on another device'), { status: 409 }); },
    getListingAgentSession: async () => ({ session_id: 'one', revision: 10 }),
  });
  await fixture.controller.load();
  await fixture.controller.send('M');
  assert.equal(fixture.view.session.revision, 10);
  await fixture.controller.retry();
  assert.equal(mutations, 1);
});

test('StrictMode remount can resume the same controller', async () => {
  const fixture = setup();
  fixture.controller.dispose();
  fixture.controller.activate();
  await fixture.controller.load();
  assert.equal(fixture.view.session.session_id, 'one');
});

test('upload retry preserves photo and follow-up turn idempotency keys', async () => {
  const uploads = [];
  const turns = [];
  const fixture = setup({
    uploadListingAgentPhotos: async payload => { uploads.push(payload); return { revision: 5 }; },
    turnWithListingAgent: async (id, payload) => {
      turns.push(payload);
      if (turns.length === 1) throw new Error('Lost response');
      return fixture.session;
    },
  });
  await fixture.controller.load();
  await fixture.controller.upload([{ file: 'original' }]);
  await fixture.controller.retry();
  assert.deepEqual(uploads[0], uploads[1]);
  assert.deepEqual(turns[0], turns[1]);
});

test('saved uploads clear selection even if the follow-up model turn fails', async () => {
  let cleared = 0;
  const saved = { session_id: 'one', revision: 5, photos: [{ image_id: 'saved' }] };
  const fixture = setup({
    uploadListingAgentPhotos: async () => saved,
    turnWithListingAgent: async () => { throw new Error('Provider unavailable'); },
  });
  await fixture.controller.load();
  await fixture.controller.upload([{ file: 'original' }], () => cleared++);
  assert.equal(cleared, 1);
  assert.deepEqual(fixture.view.session, saved);
  assert.match(fixture.view.error, /Provider unavailable/);
  await fixture.controller.retry();
  assert.equal(cleared, 2);
  assert.deepEqual(fixture.view.session, saved);
});
