import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { createListingAgentController } from '../../../../packages/app-client/src/listingAgent';
import { MANNEQUIN_DISCLAIMER } from '../../../../packages/app-client/src/mannequinDisclosure';
import { matchPhotoUrls } from '../../../../packages/app-client/src/matchPhotos';

export default function ListingAgentChat({ client, getAuth, images, onPickPhotos, styles, onClearPhotos, apiBaseUrl, initialListingId = null, newSessionRequestId = null, onExit = null, onStartNew = null, onOpenMatch = null, onOpenPhotos = null }) {
  const [view, setView] = useState({ session: null, busy: false, error: '' });
  const [text, setText] = useState('');
  const [mannequinChoice, setMannequinChoice] = useState('');
  const [showPhotos, setShowPhotos] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showDescription, setShowDescription] = useState(false);
  const auth = useRef(getAuth);
  auth.current = getAuth;
  const controller = useMemo(() => createListingAgentController(client, () => auth.current(), setView), [client, initialListingId, newSessionRequestId]);
  useEffect(() => { controller.activate(); controller.load(initialListingId, newSessionRequestId); return () => controller.dispose(); }, [controller, initialListingId, newSessionRequestId]);
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
  return <View style={styles.listingAssistantPanel}>
    {!reviewing ? <Text style={styles.helperText}>Add photos to create a private draft. Nothing is published without your confirmation.</Text> : null}
    {onExit ? button('Back to conversation', onExit) : null}
    {session ? <>
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
      {reviewing ? button(`${showHistory ? 'Hide' : 'View'} conversation history`, () => setShowHistory(!showHistory)) : null}
      {(!reviewing || showHistory) && session.messages.map((message, index) => <View key={index} style={styles.listingChatAssistantBubble}><Text style={styles.helperText}>{message.role === 'user' ? 'You' : 'Jouft'}</Text><Text style={styles.listingAssistantMessageText}>{message.content}</Text></View>)}
      {reviewing && !proposal && session.stage === 'review_ready' ? <Text style={styles.helperText}>{session.messages.filter(message => message.role === 'assistant').at(-1)?.content}</Text> : null}
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
          {!proposal ? <Text style={styles.helperText}>Tell me any correction below—for example, “Change size to US 10.5.”</Text> : null}
          {button('Keep as draft', () => controller.send('Keep as draft'))}
          {review?.mannequin_choice_required ? <View>
            <Text style={styles.helperText}>Include the AI-generated mannequin image?</Text>
            {review.mannequin_assets.map((asset, index) => asset.image_url ? <View key={index}><Image source={{ uri: new URL(asset.image_url, apiBaseUrl).href }} style={{ width: '100%', height: 240, resizeMode: 'contain' }} /><Text style={styles.helperText}>{MANNEQUIN_DISCLAIMER}</Text></View> : null)}
            {button(`${mannequinChoice === 'include' ? '✓ ' : ''}Include mannequin image`, () => setMannequinChoice('include'))}
            {button(`${mannequinChoice === 'exclude' ? '✓ ' : ''}Use original photos only`, () => setMannequinChoice('exclude'))}
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
        {session.stage === 'published' ? <View><Text style={styles.helperText}>{session.marketplace_matches ? 'Published to Marketplace.' : session.messages.filter(message => message.role === 'assistant').at(-1)?.content || 'Published to Marketplace.'}</Text>
          {button(session.marketplace_matches ? 'Refresh matches' : 'Find matching items', () => controller.send('Find marketplace matches'))}
        </View> : null}
        {session.stage === 'failed' ? <Text style={styles.error}>Analysis could not finish. Your draft is saved in My Closet.</Text> : null}
        {session.stage === 'closed' ? <View><Text style={styles.helperText}>This listing changed. Reopen review to see the current saved version.</Text>
          {session.photo_dirty ? button('Discard staged changes', () => controller.send('Discard changes')) : null}
          {button('Reopen review', () => controller.load(session.listing_id))}</View> : null}
      </View> : null}
      {session.stage === 'published' && session.marketplace_matches ? <View accessibilityLabel="Marketplace matches">
        <Text style={styles.listingAssistantTitle}>Marketplace matches</Text>
        <Text style={styles.helperText}>{session.marketplace_matches.count} matching items based on your item’s saved value and preferences. No offer has been sent.</Text>
        {session.marketplace_matches.items.map(item => <View key={item.listing_id} style={styles.listingChatAssistantBubble}>
          {matchPhotoUrls(item, apiBaseUrl).length ? <TouchableOpacity accessibilityRole="button" accessibilityLabel={`View full-size photos of ${item.title}`} onPress={() => onOpenPhotos?.({ images: matchPhotoUrls(item, apiBaseUrl), title: item.title, listing: item })}>
            <Image source={{ uri: matchPhotoUrls(item, apiBaseUrl)[0] }} accessibilityLabel={item.title} style={{ width: 100, height: 100, resizeMode: 'contain' }} />
          </TouchableOpacity> : null}
          <Text style={styles.listingAssistantTitle}>{item.title}</Text><Text style={styles.helperText}>{item.brand} · {item.size} · {item.condition} · ${item.estimated_value}</Text>
          {onOpenMatch ? button('View in Marketplace', () => onOpenMatch(item)) : null}
        </View>)}
        {!session.marketplace_matches.count ? <Text style={styles.helperText}>No matching items right now. Check again later.</Text> : null}
        {session.marketplace_matches.has_more ? <Text style={styles.helperText}>Showing the first {session.marketplace_matches.items.length} of {session.marketplace_matches.count} matches.</Text> : null}
      </View> : null}
      {canEdit && session.pending?.type === 'question' && session.pending.field === 'condition' ? <View accessibilityLabel="Choose item condition" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {['New with tags', 'New', 'Like new'].map(condition => <React.Fragment key={condition}>{button(condition, () => controller.send(condition), !!images.length)}</React.Fragment>)}
      </View> : null}
      {canEdit || session.stage === 'published' ? <View><TextInput accessibilityLabel="Reply to listing agent" style={styles.input} value={text} onChangeText={setText} multiline maxLength={2000} editable={!view.busy} placeholder="Tell me about your item or ask for matches…" />
        {button('Send', () => { controller.send(text); setText(''); }, !text.trim() || !!images.length)}</View> : null}
      {button('Start another draft', async () => { onClearPhotos(); if (await controller.startNew()) onStartNew?.(); })}
    </> : null}
    {view.busy ? <ActivityIndicator /> : null}
    {view.error ? <View><Text accessibilityRole="alert" style={styles.error}>{view.error}</Text>{button('Retry', () => controller.retry())}{button('Reload saved progress', () => controller.refresh())}</View> : null}
  </View>;
}
