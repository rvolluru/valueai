// Shared web/mobile orchestration adapter: workflow decisions live on the server.
function id() {
  return globalThis.crypto?.randomUUID?.() || `agent-${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

export function createListingAgentController(client, getAuth, onChange) {
  let state = { session: null, busy: false, error: '' };
  let retryOperation = null;
  let disposed = false;
  const emit = (patch) => {
    state = { ...state, ...patch };
    if (!disposed) onChange(state);
  };
  async function perform(operation) {
    if (state.busy || disposed) return;
    emit({ busy: true, error: '' });
    retryOperation = operation;
    try {
      const session = await operation();
      retryOperation = null;
      emit({ session, error: '' });
      return session;
    } catch (error) {
      emit({ error: error.message || 'Unable to finish. Your saved progress is safe.' });
      // A stale revision must be reviewed, not silently rebased over another device.
      if (error.status === 409 || error.statusCode === 409) {
        retryOperation = null;
        if (state.session) {
          try { emit({ session: await client.getListingAgentSession(state.session.session_id, await getAuth()) }); } catch { /* retain visible error */ }
        }
      }
    } finally { emit({ busy: false }); }
  }
  function turnOperation(session, message, confirmationToken = null) {
    const payload = { request_id: id(), expected_revision: session.revision, message, confirmation_token: confirmationToken };
    return async () => client.turnWithListingAgent(session.session_id, payload, await getAuth());
  }
  return {
    load(listingId = null, newSessionRequestId = null) {
      const requestId = newSessionRequestId || id();
      return perform(async () => {
        if (listingId) return client.openListingAgentReview({ request_id: requestId, listing_id: listingId }, await getAuth());
        if (newSessionRequestId) return client.startListingAgentSession({ request_id: requestId }, await getAuth());
        const existing = await client.getActiveListingAgentSession(await getAuth());
        return existing.session || client.startListingAgentSession({ request_id: requestId }, await getAuth());
      });
    },
    startNew() {
      const requestId = id();
      return perform(async () => client.startListingAgentSession({ request_id: requestId }, await getAuth()));
    },
    send(message) {
      if (!state.session || !message.trim()) return;
      return perform(turnOperation(state.session, message.trim()));
    },
    confirm() {
      const pending = state.session?.pending;
      if (pending?.type !== 'confirm_analysis') return;
      return perform(turnOperation(state.session, 'I confirm this summary. Create a private draft and start analysis; do not publish.', pending.token));
    },
    publish(mannequinChoice = null) {
      const session = state.session;
      const review = session?.publication_review;
      if (!review?.publishable || (review.mannequin_choice_required && !mannequinChoice)) return;
      const payload = { request_id: id(), expected_revision: session.revision,
        message: 'I reviewed the listing details, photos and value. Publish this listing to Marketplace.',
        publication_token: review.token, mannequin_choice: mannequinChoice };
      return perform(async () => client.turnWithListingAgent(session.session_id, payload, await getAuth()));
    },
    proposeEdits(fields) {
      if (!state.session) return;
      const session = state.session;
      const payload = { request_id: id(), expected_revision: session.revision,
        message: 'Please propose these corrections: ' + JSON.stringify(fields), edit_fields: fields };
      return perform(async () => client.turnWithListingAgent(session.session_id, payload, await getAuth()));
    },
    confirmEdits() {
      const session = state.session;
      const proposal = session?.edit_proposal || (session?.pending?.type === 'confirm_changes' ? session.pending : null);
      if (!proposal?.token) return;
      const payload = { request_id: id(), expected_revision: session.revision,
        message: 'I confirm these proposed changes. Save them, but do not publish.', edit_token: proposal.token };
      return perform(async () => client.turnWithListingAgent(session.session_id, payload, await getAuth()));
    },
    upload(images, onUploaded = () => {}) {
      if (!state.session || !images.length) return;
      const session = state.session;
      const requestId = id();
      const turnId = id();
      return perform(async () => {
        const uploaded = await client.uploadListingAgentPhotos({ sessionId: session.session_id, requestId, expectedRevision: session.revision, images }, await getAuth());
        emit({ session: uploaded });
        onUploaded();
        return client.turnWithListingAgent(session.session_id, {
          request_id: turnId, expected_revision: uploaded.revision,
          message: 'I uploaded these original photos. Please check the evidence and guide me through creating a private listing draft.',
        }, await getAuth());
      });
    },
    refresh() {
      if (!state.session) return;
      return perform(async () => client.getListingAgentSession(state.session.session_id, await getAuth()));
    },
    removePhoto(imageId) {
      if (!state.session || (state.session.listing_id && state.session.stage !== 'review_ready')) return;
      const session = state.session;
      const requestId = id();
      const turnId = id();
      return perform(async () => {
        const updated = await client.removeListingAgentPhoto(session.session_id, {
          request_id: requestId, expected_revision: session.revision, image_id: imageId,
        }, await getAuth());
        emit({ session: updated });
        return client.turnWithListingAgent(session.session_id, {
          request_id: turnId, expected_revision: updated.revision,
          message: 'I removed a saved photo. Please check the remaining evidence and guide me to the next required step.',
        }, await getAuth());
      });
    },
    retry() { if (retryOperation) return perform(retryOperation); },
    activate() { disposed = false; },
    dispose() { disposed = true; },
  };
}
