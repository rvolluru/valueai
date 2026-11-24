import React, { useEffect, useState } from 'react';
import { Linking, Text, TextInput, TouchableOpacity, View } from 'react-native';

export default function TrialInvitation({ apiBaseUrl, getToken, styles, onChanged }) {
  const [code, setCode] = useState('');
  const [offer, setOffer] = useState(null);
  const [trial, setTrial] = useState(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  async function request(path, body) {
    const token = await getToken();
    const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}${path}`, { method: body ? 'POST' : 'GET', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to redeem this invitation.');
    return data;
  }
  async function run(fn) { setBusy(true); setMessage(''); try { await fn(); } catch (e) { setMessage(e.message); } finally { setBusy(false); } }
  async function refresh() { const data = await request('/v1/me/trial-invitations'); setTrial(data.trial); return data; }
  useEffect(() => { let canceled = false; request('/v1/me/trial-invitations').then(data => { if (!canceled) setTrial(data.trial); }).catch(e => { if (!canceled) setMessage(e.message); }); return () => { canceled = true; }; }, [apiBaseUrl]);
  return <View style={{ gap: 10, marginVertical: 16 }}>
    <Text style={styles.label}>Invitation trial</Text>
    {trial ? <Text style={styles.helperText}>{trial.plan} membership trial until {new Date(trial.ends_at).toLocaleString()}. {trial.end_behavior === 'expire' ? 'No automatic charge.' : 'Renews through Stripe unless canceled.'} {trial.listing_limit == null ? 'Unlimited new listings during the trial.' : `${trial.listings_used} of ${trial.listing_limit} new listings used; ${trial.listings_remaining} remaining.`}</Text> : null}
    <TextInput accessibilityLabel="Trial invitation code" placeholder="Invitation code" style={styles.input} value={code} maxLength={64} autoCapitalize="characters" autoCorrect={false} onChangeText={value => { setCode(value); setOffer(null); setConsent(false); }} />
    <TouchableOpacity accessibilityRole="button" disabled={busy || code.trim().length < 6} style={styles.secondaryBtnCompact} onPress={() => run(async () => { setOffer(await request('/v1/me/trial-invitations/preview', { code })); setConsent(false); })}><Text style={styles.secondaryBtnText}>Check invitation</Text></TouchableOpacity>
    {offer ? <>
      <Text style={styles.helperText}>{offer.summary}</Text>
      <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: consent }} disabled={busy} onPress={() => setConsent(!consent)}><Text style={styles.helperText}>{consent ? '☑' : '☐'} I agree to these trial terms{offer.end_behavior === 'renew' ? ' and recurring charges after the trial until canceled' : ''}.</Text></TouchableOpacity>
      <TouchableOpacity accessibilityRole="button" disabled={busy || !consent} style={styles.primaryBtn} onPress={() => run(async () => {
        const result = await request('/v1/me/trial-invitations/redeem', { code, consent, offer_version: offer.offer_version });
        if (result.checkout_url) { await Linking.openURL(result.checkout_url); setMessage('Complete secure checkout, then return here and tap Refresh trial status.'); }
        else { await refresh(); await onChanged?.(); setOffer(null); setMessage(result.status === 'already_redeemed' ? 'Invitation already redeemed.' : 'Trial active.'); }
      })}><Text style={styles.primaryBtnText}>{offer.require_card ? 'Continue to secure card setup' : 'Start trial'}</Text></TouchableOpacity>
    </> : null}
    <TouchableOpacity accessibilityRole="button" disabled={busy} style={styles.secondaryBtnCompact} onPress={() => run(async () => { await refresh(); await onChanged?.(); setMessage('Trial status refreshed.'); })}><Text style={styles.secondaryBtnText}>Refresh trial status</Text></TouchableOpacity>
    {message ? <Text accessibilityLiveRegion="polite" style={styles.helperText}>{message}</Text> : null}
  </View>;
}
