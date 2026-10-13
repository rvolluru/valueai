export function tradeOfferGroup(offer) {
  const status = String(offer?.status || '').trim().toLowerCase();
  return ['declined', 'completed', 'finished'].includes(status) ? 'done' : 'active';
}
