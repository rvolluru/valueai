import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { createListingAgentController, photoCoverageSummary } from '../../../../packages/app-client/src/listingAgent';
import { MANNEQUIN_DISCLAIMER } from '../../../../packages/app-client/src/mannequinDisclosure';
import { matchPhotoUrls } from '../../../../packages/app-client/src/matchPhotos';

export default function ListingAgentChat({ client, getAuth, images, onPickPhotos, styles, onClearPhotos, apiBaseUrl, initialListingId = null, initialSessionId = null, newSessionRequestId = null, onExit = null, onStartNew = null, onOpenMatch = null, onOpenPhotos = null, onContext = null, onBusyChange = null, hideComposer = false, onTranscript = null, onPhotoPanel = null }) {
  const [view, setView] = useState({ session: null, busy: false, error: '' });
  const [text, setText] = useState('');
  const transcriptCallback = useRef(onTranscript);
  transcriptCallback.current = onTranscript;
  useEffect(() => { if (view.session) {
    const question = view.session.pending?.type === 'question' ? view.session.pending : !view.session.pending ? view.session.next_step : null;
    transcriptCallback.current?.({ session_id: view.session.session_id, stage: view.session.stage, messages: view.session.messages, timeline_events: view.session.timeline_events, conditionQuestion: question?.question, conditionRequested: question?.field === 'condition' });
  } }, [view.session]);
  const busyCallback = useRef(onBusyChange);
  busyCallback.current = onBusyChange;
  useEffect(() => { busyCallback.current?.(view.busy); return () => busyCallback.current?.(false); }, [view.busy]);
  const [mannequinChoice, setMannequinChoice] = useState('');
  const [showPhotos, setShowPhotos] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showDescription, setShowDescription] = useState(false);
  const contextCallback = useRef(onContext);
  const photoCallback = useRef(onOpenPhotos);
  const openedPhotoRequest = useRef(null);
  contextCallback.current = onContext;
  photoCallback.current = onOpenPhotos;
  useEffect(() => { if (view.session?.conversation_context) contextCallback.current?.(view.session.conversation_context); }, [view.session?.conversation_context]);
  useEffect(() => {
    const photo = view.session?.photo_view;
    if (!photo?.images?.length || openedPhotoRequest.current === photo.request_id) return;
    openedPhotoRequest.current = photo.request_id;
    photoCallback.current?.({ images: matchPhotoUrls(photo, apiBaseUrl), title: photo.title, listing: photo });
  }, [view.session?.photo_view, apiBaseUrl]);
  const auth = useRef(getAuth);
  auth.current = getAuth;
  const controller = useMemo(() => createListingAgentController(client, () => auth.current(), setView), [client, initialListingId, newSessionRequestId, initialSessionId]);
  useEffect(() => { controller.activate(); controller.load(initialListingId, newSessionRequestId, initialSessionId); return () => controller.dispose(); }, [controller, initialListingId, newSessionRequestId, initialSessionId]);
  useEffect(() => {
    if (view.session?.stage !== 'analyzing') return undefined;
    const timer = setInterval(() => controller.refresh(), 4000);
    return () => clearInterval(timer);
  }, [controller, view.session?.stage]);
  const session = view.session;
  const review = session?.publication_review;
  const proposal = session?.edit_proposal || (session?.pending?.type === 'confirm_changes' ? session.pending : null);
  const canEdit = !session?.listing_id || session?.stage === 'review_ready';
  const reviewing = !!session?.listing_id;
  const displayPhotos = session?.listing && !canEdit ? (session.listing.images || []).map((url, index) => ({ image_id: `review-${index}`, url })) : session?.photos || [];
  useEffect(() => { setMannequinChoice(''); }, [review?.token]);
  const button = (label, action, disabled = false) => <TouchableOpacity accessibilityRole="button" style={styles.secondaryBtnCompact} onPress={action} disabled={view.busy || disabled}><Text style={styles.secondaryBtnText}>{label}</Text></TouchableOpacity>;
  const photoPanel = session ? <>
      {!reviewing ? <Text style={styles.helperText}>{session.photos.length}/6 saved photos</Text> : button(`${showPhotos ? 'Hide' : 'View or change'} photos (${session.photos.length})`, () => setShowPhotos(!showPhotos))}
      {session.photo_dirty ? <Text style={styles.helperText}>Photo changes are staged only. Confirm them before they are applied to the listing.</Text> : null}
      {!reviewing || showPhotos ? <View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} accessibilityLabel="Saved photos">
        {displayPhotos.map((photo, index) => <View key={photo.image_id} style={{ width: '30%' }}>
          <Image source={{ uri: new URL(photo.url, apiBaseUrl).href }} accessibilityLabel={`Saved item photo ${index + 1}`} style={{ width: '100%', aspectRatio: 1 }} />
          {review?.mannequin_assets.some(asset => asset.image_url === photo.url) ? <Text style={styles.helperText}>{MANNEQUIN_DISCLAIMER}</Text> : null}
          {canEdit ? button(`Remove photo ${index + 1}`, () => controller.removePhoto(photo.image_id)) : null}
        </View>)}
      </View>
      {canEdit ? <View>
        {button(images.length ? 'Add more photos' : 'Choose photos', onPickPhotos, session.photos.length >= 6 || images.length >= 6)}
        <Text style={styles.helperText}>{images.length} selected{images.length ? ', not uploaded yet. Press “Use these photos” before replying.' : '.'} Existing photos stay saved. Up to 6 saved photos total.</Text>
        {button('Use these photos', () => controller.upload(images, onClearPhotos), !images.length)}
        {images.length ? button('Clear selected photos', onClearPhotos) : null}
      </View> : null}
      </View> : null}
      {!onPhotoPanel && photoCoverageSummary(session).length ? <View accessibilityLabel="Photo coverage" accessibilityLiveRegion="polite">
        <Text style={styles.listingAssistantTitle}>Photo coverage</Text>
        {photoCoverageSummary(session).map((line, index) => <Text key={index} style={styles.helperText}>{line}</Text>)}
      </View> : null}
  </> : null;
  const panelCallback = useRef(onPhotoPanel);
  panelCallback.current = onPhotoPanel;
  useEffect(() => { if (session) panelCallback.current?.({ session_id: session.session_id, node: photoPanel }); }, [session, view.busy, images, showPhotos]);
  return <View style={styles.listingAssistantPanel}>
    {!hideComposer && !reviewing ? <Text style={styles.helperText}>Add photos to create a private draft. Nothing is published without your confirmation.</Text> : null}
    {onExit ? button(hideComposer ? 'Hide listing photos and review' : 'Back to conversation', onExit) : null}
    {session ? <>
      {!onPhotoPanel ? photoPanel : null}
      {!hideComposer && reviewing ? button(`${showHistory ? 'Hide' : 'View'} conversation history`, () => setShowHistory(!showHistory)) : null}
      {!hideComposer && (!reviewing || showHistory) && session.messages.map((message, index) => <View key={index} style={styles.listingChatAssistantBubble}><Text style={styles.helperText}>{message.role === 'user' ? 'You' : 'Jouft'}</Text><Text style={styles.listingAssistantMessageText}>{message.content}</Text></View>)}
      {!hideComposer && reviewing && !proposal && session.stage === 'review_ready' ? <Text style={styles.helperText}>{session.messages.filter(message => message.role === 'assistant').at(-1)?.content}</Text> : null}
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
        {button(`${showDescription ? 'Hide' : 'View'} item description`, () => setShowDescription(!showDescription))}
        {showDescription ? <Text style={styles.listingAssistantMessageText}>{session.listing.description}</Text> : null}
        {session.stage === 'review_ready' ? <View>
          <Text style={styles.helperText}>{session.listing.estimated_value > 0 ? `Estimated value: $${session.listing.estimated_value}` : 'Value needs review.'}</Text>
          {!proposal ? <Text style={styles.helperText}>Tell me what you would like to change below.</Text> : null}
          {button('Keep as draft', () => controller.send('Keep as draft'))}
          {review?.mannequin_choice_required ? <View accessibilityLabel="Choose your listing photos" style={{ padding: 16, borderWidth: 1, borderColor: '#d7cec5', backgroundColor: '#fffdf9', gap: 12, marginVertical: 16 }}>
            <Text style={[styles.listingAssistantTitle, { color: '#5b1720' }]}>Choose your listing photos</Text>
            <Text style={styles.helperText}>Include the AI styling preview, or use only your original photos.</Text>
            {review.mannequin_assets.map((asset, index) => asset.image_url ? <View key={index}><Image source={{ uri: new URL(asset.image_url, apiBaseUrl).href }} accessibilityLabel="AI-generated mannequin preview" style={{ width: '100%', height: 240, resizeMode: 'contain', backgroundColor: '#f3eee8' }} /><Text style={[styles.helperText, { fontSize: 12, lineHeight: 19, marginTop: 10, color: '#75675f' }]}>{MANNEQUIN_DISCLAIMER}</Text></View> : null)}
            {['include', 'exclude'].map(choice => <TouchableOpacity key={choice} accessibilityRole="radio" accessibilityState={{ checked: mannequinChoice === choice, disabled: view.busy }} disabled={view.busy} onPress={() => setMannequinChoice(choice)} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12, padding: 16, minHeight: 82, borderWidth: 1, borderColor: mannequinChoice === choice ? '#5b1720' : '#d7cec5', backgroundColor: mannequinChoice === choice ? '#f4eae7' : '#fffdf9', opacity: view.busy ? 0.55 : 1 }}>
              <View style={{ width: 20, height: 20, borderRadius: 10, borderWidth: 1, borderColor: '#5b1720', alignItems: 'center', justifyContent: 'center', marginTop: 2 }}>{mannequinChoice === choice ? <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: '#5b1720' }} /> : null}</View>
              <View style={{ flex: 1, gap: 6 }}><Text style={[styles.helperText, { fontWeight: '600', color: '#121a24' }]}>{choice === 'include' ? 'Include mannequin image' : 'Use original photos only'}</Text><Text style={[styles.helperText, { fontSize: 12, lineHeight: 19, color: '#75675f' }]}>{choice === 'include' ? 'Add the AI styling preview alongside your photos.' : 'Show only the photos you uploaded.'}</Text></View>
            </TouchableOpacity>)}
          </View> : null}
          {proposal ? <View style={styles.listingChatAssistantBubble}>
            <Text style={styles.listingAssistantTitle}>Save these changes?</Text>
            {Object.entries(proposal.changes || {}).map(([key, value]) => <Text key={key} style={styles.helperText}>{key}: {session.listing[key] || 'Not set'} → {value}</Text>)}
            <Text style={styles.helperText}>{session.photos.length} photos. {proposal.reanalyze ? 'Analysis will run again before publication.' : 'The existing analysis and value will be retained.'}</Text>
            <Text style={styles.helperText}>Reply “Save changes” to apply these staged changes, or “Discard changes” to cancel.</Text>
          </View> : null}
          {!proposal && review?.reasons.map(reason => <Text key={reason} style={styles.helperText}>{reason}</Text>)}
          {!proposal && review?.publishable ? button('Confirm and publish to Marketplace', () => controller.publish(mannequinChoice || null), !!images.length || !review.publishable || (review.mannequin_choice_required && !mannequinChoice)) : null}
        </View> : null}
        {session.stage === 'published' ? <View><Text style={styles.helperText}>{session.marketplace_matches && session.last_tool === 'find_marketplace_matches' ? 'Published to Marketplace.' : session.messages.filter(message => message.role === 'assistant').at(-1)?.content || 'Published to Marketplace.'}</Text>
          {button(session.marketplace_matches ? 'Refresh matches' : 'Find matching items', () => controller.send('Find marketplace matches'))}
        </View> : null}
        {session.stage === 'failed' ? <Text style={styles.error}>Analysis could not finish. Your draft is saved in My Closet.</Text> : null}
        {session.stage === 'closed' ? <View><Text style={styles.helperText}>This listing changed. Reopen review to see the current saved version.</Text>
          {session.photo_dirty ? button('Discard staged changes', () => controller.send('Discard changes')) : null}
          {button('Reopen review', () => controller.load(session.listing_id))}</View> : null}
      </View> : null}
      {session.stage === 'published' && session.marketplace_matches && !session.trade_proposal ? <View accessibilityLabel="Marketplace matches">
        <Text style={styles.listingAssistantTitle}>Marketplace matches</Text>
        <Text style={styles.helperText}>{session.marketplace_matches.count} matching items based on your item’s saved value and preferences. Selecting an item only prepares a request; confirmation is required to send.</Text>
        {session.marketplace_matches.items.map(item => <View key={item.listing_id} style={styles.listingChatAssistantBubble}>
          {matchPhotoUrls(item, apiBaseUrl).length ? <TouchableOpacity accessibilityRole="button" accessibilityLabel={`View full-size photos of ${item.title}`} disabled={view.busy} onPress={() => controller.viewPhotos(item.listing_id)}>
            <Image source={{ uri: matchPhotoUrls(item, apiBaseUrl)[0] }} accessibilityLabel={item.title} style={{ width: 100, height: 100, resizeMode: 'contain' }} />
          </TouchableOpacity> : null}
          <Text style={styles.listingAssistantTitle}>{item.title}</Text><Text style={styles.helperText}>{item.brand} · {item.size} · {item.condition} · ${item.estimated_value}</Text>
          {onOpenMatch ? button('View in Marketplace', () => onOpenMatch(item)) : null}
          {button('Request trade', () => controller.prepareTrade(item.listing_id))}
        </View>)}
        {!session.marketplace_matches.count ? <Text style={styles.helperText}>No matching items right now. Check again later.</Text> : null}
        {session.marketplace_matches.has_more ? <Text style={styles.helperText}>Showing the first {session.marketplace_matches.items.length} of {session.marketplace_matches.count} matches.</Text> : null}
      </View> : null}
      {session.trade_proposal ? <View accessibilityLabel="Confirm trade request" style={styles.listingChatAssistantBubble}>
        <Text style={styles.listingAssistantTitle}>Send this trade request?</Text>
        <Text style={styles.helperText}>You offer: {session.trade_proposal.offered.title} · {session.trade_proposal.offered.size} · {session.trade_proposal.offered.condition} · ${session.trade_proposal.offered.estimated_value}</Text>
        <Text style={styles.helperText}>You request: {session.trade_proposal.target.title} · {session.trade_proposal.target.size} · {session.trade_proposal.target.condition} · ${session.trade_proposal.target.estimated_value}</Text>
        <Text style={styles.helperText}>This offers your item to {session.trade_proposal.recipient} and notifies them. It does not complete the trade or charge a payment.</Text>
        {button('Confirm and send trade request', () => controller.confirmTrade())}
        {button('Cancel trade request', () => controller.send('Cancel trade request'))}
      </View> : null}
      {session.sent_trade ? <Text style={styles.helperText}>Trade request sent. Track it in Trade Inbox.</Text> : null}
      {!hideComposer && canEdit && session.pending?.type === 'question' && session.pending.field === 'condition' ? <View accessibilityLabel="Choose item condition" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {['New with tags', 'New', 'Like new'].map(condition => <React.Fragment key={condition}>{button(condition, () => controller.send(condition), !!images.length)}</React.Fragment>)}
      </View> : null}
      {!hideComposer && (canEdit || session.stage === 'published') ? <View><TextInput accessibilityLabel="Reply to listing agent" style={styles.input} value={text} onChangeText={setText} multiline maxLength={2000} editable={!view.busy} placeholder="Tell me about your item or ask for matches…" />
        {button('Send', () => { controller.send(text); setText(''); }, !text.trim() || !!images.length)}</View> : null}
      {!initialSessionId && button('Start another draft', async () => { onClearPhotos(); if (await controller.startNew()) onStartNew?.(); })}
    </> : null}
    {view.busy ? <ActivityIndicator /> : null}
    {view.error ? <View><Text accessibilityRole="alert" style={styles.error}>{view.error}</Text>{button('Retry', () => controller.retry())}{button('Reload saved progress', () => controller.refresh())}</View> : null}
  </View>;
}
