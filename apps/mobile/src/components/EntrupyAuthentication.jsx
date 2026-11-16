import React, { useState } from 'react';
import { View, Text, Button, Linking } from 'react-native';
import Entrupy from '../../modules/entrupy';

export default function EntrupyAuthentication({ listingId, apiClient, authContext }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  async function run(capture) {
    setBusy(true); setError(''); setResult(null);
    try {
      const auth = await authContext();
      if (capture) {
        if (!Entrupy) throw Error('Entrupy requires a new native app build.');
        const request = await Entrupy.generateAuthorizationRequest();
        if (!request) throw Error('Unable to start Entrupy authorization.');
        const session = await apiClient.authorizeEntrupy(listingId, request, auth);
        await Entrupy.login(session.signed_authorization_request);
        await Entrupy.startCapture(session.metadata);
      } else {
        setResult(await apiClient.getEntrupyAuthentication(listingId, auth));
      }
    } catch (err) { setError(err.message || 'Authentication unavailable'); }
    finally { setBusy(false); }
  }
  return <View style={{ paddingVertical: 12, gap: 8 }}>
    <Text>Entrupy item authentication</Text>
    <Button title="Authenticate with Entrupy" disabled={busy} onPress={() => run(true)} />
    <Button title="Check authentication result" disabled={busy} onPress={() => run(false)} />
    {result && <Text>{result.display || result.result || 'Awaiting result'}{result.retake_required ? ' — photos must be retaken' : ''}</Text>}
    {result?.authenticated && result.certificate_url && <Button title="View Entrupy certificate" onPress={() => Linking.openURL(result.certificate_url)} />}
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
  </View>;
}
