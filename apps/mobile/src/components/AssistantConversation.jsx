import React, { useEffect, useRef, useState } from 'react';
import { View, Text, TextInput, ScrollView, TouchableOpacity, Image } from 'react-native';
import { createConversationController, conversationBlocks, conversationSpans, assistantOutcomeLabel, resultSetHeading, chronologicalChat, listingPanelPosition, conversationText } from '../../../../packages/app-client/src/assistantConversation';

export default function AssistantConversation({ client, getAuth, onPhotos, styles, apiBaseUrl, renderWorkflow = null }) {
  const [view, setView] = useState({ busy: true });
  const [input, setInput] = useState('');
  const [workflowOpen, setWorkflowOpen] = useState(false);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [listingTranscript, setListingTranscript] = useState(null);
  const [photoPanel, setPhotoPanel] = useState(null);
  const linkedTranscript = listingTranscript?.session_id === view.session?.workflow_id ? listingTranscript : null;
  const messages = chronologicalChat(view.session?.messages, linkedTranscript, view.session?.result_sets);
  const hasPhotoEvents = messages.some(m => m.timeline_kind === 'photos');
  const hasActionEvents = messages.some(m => m.timeline_kind === 'actions');
  useEffect(() => { setWorkflowOpen(!!view.session?.workflow_id); }, [view.session?.conversation_id, view.session?.workflow_id]);
  const auth = useRef(getAuth);
  auth.current = getAuth;
  const controller = useRef(null);
  const scroll = useRef(null);
  const openedGallery = useRef(null);
  const photos = useRef(onPhotos);
  photos.current = onPhotos;
  useEffect(() => {
    const event = view.session?.gallery;
    if (event && event.request_id !== openedGallery.current) {
      openedGallery.current = event.request_id;
      photos.current(event.listing);
    }
  }, [view.session]);
  useEffect(() => {
    const current = createConversationController(client, () => auth.current(), setView);
    controller.current = current;
    current.start();
    return () => current.dispose();
  }, [client]);
  const panelIndex = listingPanelPosition(messages, linkedTranscript?.stage);
  const questionIndex = linkedTranscript?.conditionRequested ? messages.findLastIndex(m => m.role === 'assistant' && linkedTranscript.conditionQuestion && conversationText(m).endsWith(linkedTranscript.conditionQuestion)) : -1;
  const conditionButtons = <View accessibilityLabel="Choose item condition" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{['New with tags', 'New', 'Like new'].map(condition => <TouchableOpacity key={condition} accessibilityRole="button" disabled={view.busy || workflowBusy || view.retryable} onPress={() => controller.current.send(condition)} style={styles.secondaryBtnCompact}><Text style={styles.secondaryBtnText}>{condition}</Text></TouchableOpacity>)}</View>;
  const listingPanel = view.session?.workflow_id && renderWorkflow ? workflowOpen
    ? <View key={view.session.revision} pointerEvents={view.busy || view.retryable ? 'none' : 'auto'}>{renderWorkflow(view.session.workflow_id, () => setWorkflowOpen(false), setWorkflowBusy, setListingTranscript, setPhotoPanel)}</View>
    : <TouchableOpacity onPress={() => setWorkflowOpen(true)}><Text>Show listing photos and review</Text></TouchableOpacity> : null;
  const inlinePhotos = workflowOpen && photoPanel?.session_id === view.session?.workflow_id ? <View pointerEvents={view.busy || workflowBusy || view.retryable ? 'none' : 'auto'}>{photoPanel.node}</View> : null;
  const renderResults = groups => (groups || []).map(group => <View key={group.id}><Text style={styles.listingAssistantTitle}>{resultSetHeading(group)}</Text>
    {group.items.map((item, index) => <View key={item.listing_id || `${item.offer_id}-${index}`} style={styles.appAssistantResultRow}>
      {item.image ? <TouchableOpacity disabled={view.busy || view.retryable} accessibilityRole="button" accessibilityLabel={`View photos of ${item.title}`} onPress={() => controller.current.viewPhotos(item)}><Image source={{ uri: item.image }} style={styles.appAssistantResultImage} /></TouchableOpacity> : null}
      <View style={styles.tradeTargetCopy}><Text style={styles.listingAssistantTitle}>{(group.offset || 0) + index + 1} · {item.title}</Text><Text style={styles.helperText}>{group.domain === 'trades' || group.domain === 'shipping' ? `${item.carrier ? item.carrier + ' · ' : ''}${item.status}${item.eta ? ' · Estimated arrival: ' + item.eta : ''}` : `${item.brand} · ${item.size} · ${item.condition}`}</Text></View>
    </View>)}
  </View>);
  return <>
    <View style={{ padding: 12 }}><TouchableOpacity accessibilityRole="button" disabled={view.busy || workflowBusy || view.retryable} onPress={() => { setInput(''); controller.current.newThread(); }}><Text style={styles.listingAssistantTitle}>＋ New chat</Text></TouchableOpacity>
      <ScrollView horizontal keyboardShouldPersistTaps="handled" accessibilityLabel="Chat threads">{(view.threads || []).map(thread => <TouchableOpacity key={thread.conversation_id} accessibilityRole="button" accessibilityState={{ selected: view.session?.conversation_id === thread.conversation_id }} disabled={view.busy || workflowBusy || view.retryable} onPress={() => { setInput(''); controller.current.openThread(thread.conversation_id); }} style={{ padding: 10, maxWidth: 220 }}><Text numberOfLines={1} style={styles.helperText}>{thread.title}</Text></TouchableOpacity>)}</ScrollView>
    </View>
    <ScrollView ref={scroll} style={styles.appAssistantTranscript} contentContainerStyle={styles.appAssistantTranscriptContent} keyboardShouldPersistTaps="handled" onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: true })}>
      <Text style={styles.helperText}>Ask me to create a listing, update an existing one, or find Marketplace matches.</Text>
      {messages.map((message, index) => <React.Fragment key={message.id || `${message.request_id || 'legacy'}-${index}`}>
        {!hasPhotoEvents && index === panelIndex ? inlinePhotos : null}
        {message.timeline_kind === 'photos' && message.isCurrent ? inlinePhotos : message.timeline_kind === 'actions' && message.isCurrent ? listingPanel : <View style={styles.appAssistantTurn}><View style={{ flex: 1 }}>
          {conversationBlocks(message).map((block, n) => <Text key={n} style={[styles.listingAssistantMessageText, { marginBottom: 10 }, block.kind === 'heading' && { fontWeight: '700' }]}>{block.kind === 'bullet' ? '• ' : ''}{conversationSpans(block.text).map((span, i) => <Text key={i} style={span.bold ? { fontWeight: '700' } : undefined}>{span.text}</Text>)}</Text>)}
          {message.timeline_kind === 'photos' ? <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{(message.snapshot.photos || []).map(photo => <Image key={photo.image_id} source={{ uri: new URL(photo.url, apiBaseUrl).href }} accessibilityLabel="Previously uploaded item photo" style={{ width: 120, height: 140, resizeMode: 'contain' }} />)}</View> : null}
          {index === questionIndex ? conditionButtons : null}
        </View></View>}
        {renderResults(message.result_sets)}
      </React.Fragment>)}
      {!hasPhotoEvents && panelIndex === messages.length ? inlinePhotos : null}
      {!hasActionEvents ? listingPanel : null}
      {view.busy ? <Text>Thinking…</Text> : null}
      {(view.session?.outcome?.next_actions || []).map((choice, index) => <TouchableOpacity accessibilityRole="button" key={index} style={styles.secondaryBtnCompact} disabled={view.busy || view.retryable} onPress={() => controller.current.nextAction(index)}><Text style={styles.secondaryBtnText}>{choice.label}</Text></TouchableOpacity>)}
      {assistantOutcomeLabel(view.error ? view.errorCategory : view.session?.outcome?.category) ? <Text style={styles.listingAssistantTitle}>{assistantOutcomeLabel(view.error ? view.errorCategory : view.session?.outcome?.category)}</Text> : null}
      {view.error ? <Text accessibilityRole="alert" style={styles.error}>{view.error}</Text> : null}
      {view.retryable ? <TouchableOpacity disabled={view.busy} onPress={() => controller.current.retry()}><Text>Retry saved request</Text></TouchableOpacity> : null}
    </ScrollView>
    {<View style={styles.appAssistantComposer}><TextInput accessibilityLabel="Message Jouft" style={[styles.input, styles.appAssistantInput]} multiline value={input} onChangeText={setInput} editable={!view.busy && !workflowBusy && !view.retryable && !!view.session} />
      <TouchableOpacity style={styles.primaryBtnCompact} disabled={!input.trim() || view.busy || workflowBusy || view.retryable || !view.session} onPress={() => { const message = input.trim(); controller.current.send(message); setInput(''); }}><Text style={styles.primaryBtnText}>Send</Text></TouchableOpacity>
    </View>}
  </>;
}
