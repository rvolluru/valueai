import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { createListingAgentController } from '../../../../packages/app-client/src/listingAgent';

export default function ListingAgentChat({ client, getAuth, images, onPickPhotos, styles, onClearPhotos }) {
  const [view, setView] = useState({ session: null, busy: false, error: '' });
  const [text, setText] = useState('');
  const auth = useRef(getAuth);
  auth.current = getAuth;
  const controller = useMemo(() => createListingAgentController(client, () => auth.current(), setView), [client]);
  useEffect(() => { controller.activate(); controller.load(); return () => controller.dispose(); }, [controller]);
  useEffect(() => {
    if (view.session?.stage !== 'analyzing') return undefined;
    const timer = setInterval(() => controller.refresh(), 4000);
    return () => clearInterval(timer);
  }, [controller, view.session?.stage]);
  const session = view.session;
  const button = (label, action, disabled = false) => <TouchableOpacity accessibilityRole="button" style={styles.secondaryBtnCompact} onPress={action} disabled={view.busy || disabled}><Text style={styles.secondaryBtnText}>{label}</Text></TouchableOpacity>;
  return <View style={styles.listingAssistantPanel}>
    <Text style={styles.listingAssistantTitle}>Jouft Listing Agent</Text>
    <Text style={styles.helperText}>Create a private draft. Nothing is published from this chat.</Text>
    {session ? <>
      <Text style={styles.helperText}>{session.photos.length}/6 saved photos · {session.stage.replaceAll('_', ' ')}</Text>
      {!session.listing_id ? <View>
        {button(images.length ? 'Add more photos' : 'Choose photos', onPickPhotos, images.length >= 6)}
        <Text style={styles.helperText}>{images.length} selected{images.length ? ', not uploaded yet. Press “Use these photos” before replying.' : '.'} Using photos replaces the complete saved set.</Text>
        {button('Use these photos', () => controller.upload(images, onClearPhotos), !images.length)}
        {images.length ? button('Clear selected photos', onClearPhotos) : null}
      </View> : null}
      {session.messages.map((message, index) => <View key={index} style={styles.listingChatAssistantBubble}><Text style={styles.helperText}>{message.role === 'user' ? 'You' : 'Jouft'}</Text><Text style={styles.listingAssistantMessageText}>{message.content}</Text></View>)}
      {session.pending?.type === 'confirm_analysis' ? <View style={styles.listingChatAssistantBubble}>
        <Text style={styles.listingAssistantTitle}>Confirm draft details</Text>
        {Object.entries(session.pending.facts).map(([key, value]) => <Text key={key} style={styles.listingAssistantMessageText}>{key}: {value}</Text>)}
        {session.pending.waived_views.length ? <Text style={styles.helperText}>Unavailable views: {session.pending.waived_views.join(', ')}</Text> : null}
        {button('Confirm and analyze private draft', () => controller.confirm())}
      </View> : null}
      {session.stage === 'analyzing' ? <Text style={styles.helperText}>Analysis is running. You can close this chat and resume later.</Text> : null}
      {session.listing_id && !session.job_id ? button('Continue saved draft', () => controller.send('Continue the confirmed private draft and start its analysis.')) : null}
      {session.listing ? <View style={styles.listingChatAssistantBubble}>
        <Text style={styles.listingAssistantTitle}>{session.listing.title}</Text>
        <Text style={styles.listingAssistantMessageText}>{session.listing.brand} · {session.listing.condition} · {session.listing.size}</Text>
        <Text style={styles.listingAssistantMessageText}>{session.listing.description}</Text>
        {session.stage === 'review_ready' ? <Text style={styles.helperText}>{session.listing.estimated_value > 0 ? `Estimated value: $${session.listing.estimated_value}` : 'Value needs review.'} Review and edit this private draft in My Closet.</Text> : null}
        {session.stage === 'failed' ? <Text style={styles.error}>Analysis could not finish. Your draft is saved in My Closet.</Text> : null}
        {session.stage === 'closed' ? <Text style={styles.helperText}>This listing changed outside this conversation. Continue in My Closet.</Text> : null}
      </View> : null}
      {!session.listing_id ? <View><TextInput accessibilityLabel="Reply to listing agent" style={styles.input} value={text} onChangeText={setText} multiline maxLength={2000} editable={!view.busy} placeholder="Tell me about your item…" />
        {button('Send', () => { controller.send(text); setText(''); }, !text.trim() || !!images.length)}</View> : null}
      {button('Start another draft', () => { onClearPhotos(); controller.startNew(); })}
    </> : null}
    {view.busy ? <ActivityIndicator /> : null}
    {view.error ? <View><Text accessibilityRole="alert" style={styles.error}>{view.error}</Text>{button('Retry', () => controller.retry())}{button('Reload saved progress', () => controller.refresh())}</View> : null}
  </View>;
}
