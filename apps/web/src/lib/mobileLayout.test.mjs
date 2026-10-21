import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8');
test('trade and shipment rows without images use the full text column', () => {
  const source = readFileSync(new URL('../components/AssistantConversation.jsx', import.meta.url), 'utf8');
  assert.match(source, /className=\{item.image \? 'has-image' : 'is-text-only'\}/);
  assert.match(css, /\.app-assistant-results article\.is-text-only\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(css, /\.app-assistant-results article\s*\{[^}]*grid-template-columns: 58px minmax\(0, 1fr\)/);
});
test('listing photo choices use Jouft cards with compact accessible radio controls', () => {
  const web = readFileSync(new URL('../components/ListingAgentChat.jsx', import.meta.url), 'utf8');
  const mobile = readFileSync(new URL('../../../mobile/src/components/ListingAgentChat.jsx', import.meta.url), 'utf8');
  assert.match(web, /fieldset className="listing-mannequin-choice" disabled=\{view.busy\}/);
  assert.match(web, /listing-choice-card.*is-selected/);
  assert.match(web, /type="radio".*checked=\{mannequinChoice === choice\}/);
  assert.match(css, /\.listing-choice-card input\[type="radio"\][^{]*\{[^}]*flex: 0 0 18px;[^}]*width: 18px;[^}]*height: 18px/);
  assert.match(css, /\.listing-mannequin-layout\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\);/);
  assert.match(mobile, /accessibilityRole="radio" accessibilityState=\{\{ checked: mannequinChoice === choice/);
});
test('threaded listing messages use the main transcript and inline condition choices on both clients', () => {
  for (const client of ['web', 'mobile']) {
    const parent = readFileSync(new URL(`../../../${client}/src/components/AssistantConversation.jsx`, import.meta.url), 'utf8');
    const child = readFileSync(new URL(`../../../${client}/src/components/ListingAgentChat.jsx`, import.meta.url), 'utf8');
    assert.match(parent, /chronologicalChat/);
    assert.match(parent, /setWorkflowBusy, setListingTranscript/);
    assert.match(parent, /setListingTranscript, setPhotoPanel/);
    assert.match(parent, /index === panelIndex.*inlinePhotos/);
    assert.doesNotMatch(parent, /index === panelIndex.*listingPanel/);
    assert.match(parent, /renderResults\(message.result_sets\)/);
    assert.match(parent, /timeline_kind === 'actions' && message.isCurrent/);
    assert.match(parent, /linkedTranscript\?\.conditionRequested/);
    assert.doesNotMatch(parent, /guided workflow|Continue listing workflow/);
    assert.match(child, /transcriptCallback\.current\?\./);
    assert.match(child, /!hideComposer.*(?:listing-agent-history|showHistory)/);
  }
});
test('short user replies have a full-width row and do not shrink to single-character bubbles', () => {
  assert.match(css, /\.assistant-conversation-main \.app-assistant-turn\s*\{[^}]*width: 100%/);
  assert.match(css, /\.app-assistant-turn\.user \.assistant-message-body\s*\{[^}]*flex: 0 0 auto;[^}]*min-width: 3\.5em/);
});
test('agent content stays in the assistant transcript scroll area without card clipping', () => {
  const transcript = css.match(/\.app-assistant-transcript\s*\{([^}]+)\}/)[1];
  assert.match(transcript, /grid-auto-rows: max-content/);
  assert.match(transcript, /min-height: 0/);
  assert.match(transcript, /overflow-y: auto/);
  assert.match(css, /\.listing-agent-chat\.panel\s*\{[^}]*overflow: visible/);
  assert.match(css, /\.listing-agent-chat \.listing-assistant-messages\s*\{[^}]*max-height: none; overflow: visible/);
});
test('agent distinguishes selected photos from uploaded photos before accepting text replies', () => {
  const web = readFileSync(new URL('../components/ListingAgentChat.jsx', import.meta.url), 'utf8');
  const mobile = readFileSync(new URL('../../../mobile/src/components/ListingAgentChat.jsx', import.meta.url), 'utf8');
  assert.match(web, /selected, not uploaded yet/);
  assert.match(web, /if \(!text.trim\(\) \|\| files.length\) return/);
  assert.match(web, /controller.upload\(files, \(\) => \{ setFiles\(\[\]\)/);
  assert.match(mobile, /not uploaded yet/);
  assert.match(mobile, /controller.upload\(images, onClearPhotos\)/);
  assert.match(mobile, /!text.trim\(\) \|\| !!images.length/);
  assert.match(web, /aria-label="Saved photos"/);
  assert.match(web, /controller.removePhoto\(photo.image_id\)/);
  assert.match(mobile, /controller.removePhoto\(photo.image_id\)/);
  assert.doesNotMatch(web + mobile, /replaces the complete saved/);
});
test('agent review uses current gallery and a separate explicit publication control', () => {
  for (const path of ['../components/ListingAgentChat.jsx', '../../../mobile/src/components/ListingAgentChat.jsx']) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8');
    assert.match(source, /session.listing.images/);
    assert.match(source, /Confirm and publish to Marketplace/);
    assert.match(source, /controller.publish\(mannequinChoice \|\| null\)/);
    assert.match(source, /review.mannequin_choice_required && !mannequinChoice/);
    assert.match(source, /MANNEQUIN_DISCLAIMER/);
    assert.match(source, /\[review\?\.token\]/);
    assert.doesNotMatch(source, /setEditFields|proposeEdits\(editFields\)/);
    assert.match(source, /Keep as draft/);
    assert.match(source, /Reply “Save changes”/);
    assert.match(source, /controller.load\(initialListingId, newSessionRequestId, initialSessionId\)/);
  }
});

test('review keeps current actions compact and separates saving from publication', () => {
  const web = readFileSync(new URL('../components/ListingAgentChat.jsx', import.meta.url), 'utf8');
  const mobile = readFileSync(new URL('../../../mobile/src/components/ListingAgentChat.jsx', import.meta.url), 'utf8');
  assert.match(web, /Conversation history/);
  assert.match(web, /open=\{!reviewing \|\| undefined\}/);
  assert.match(mobile, /showHistory/);
  for (const source of [web, mobile]) {
    assert.match(source, /Save these changes\?/);
    assert.match(source, /Save changes/);
    assert.match(source, /Discard changes/);
    assert.match(source, /!proposal && review\?\.publishable/);
    assert.doesNotMatch(source, /<h3>Jouft Listing Agent/);
  }
});

test('web and mobile create handoffs explicitly request a fresh session', () => {
  for (const path of ['../App.jsx', '../../../mobile/App.js']) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8');
    assert.match(source, /setAppAssistantNewSessionRequestId\(`create-/);
    assert.match(source, /newSessionRequestId=\{appAssistantNewSessionRequestId\}/);
  }
});

test('condition quick replies are message-based and scoped to the active question', () => {
  for (const path of ['../components/ListingAgentChat.jsx', '../../../mobile/src/components/ListingAgentChat.jsx']) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8');
    assert.match(source, /field === 'condition'/);
    assert.match(source, /\['New with tags', 'New', 'Like new'\]/);
    assert.match(source, /controller.send\(condition\)/);
    assert.match(source, /Choose item condition/);
  }
});

test('published listing chat offers read-only Marketplace matching on both clients', () => {
  for (const path of ['../components/ListingAgentChat.jsx', '../../../mobile/src/components/ListingAgentChat.jsx']) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8');
    assert.match(source, /controller.send\('Find marketplace matches'\)/);
    assert.match(source, /session.marketplace_matches.items.map/);
    assert.match(source, /View in Marketplace/);
    assert.match(source, /confirmation is required to send/);
    assert.match(source, /No matching items right now/);
  }
});

test('match photos open existing full-screen viewers without navigating away from chat', () => {
  const web = readFileSync(new URL('../components/ListingAgentChat.jsx', import.meta.url), 'utf8');
  const mobile = readFileSync(new URL('../../../mobile/src/components/ListingAgentChat.jsx', import.meta.url), 'utf8');
  for (const source of [web, mobile]) {
    assert.match(source, /View full-size photos of/);
    assert.match(source, /photoCallback.current\?\.\(/);
    assert.match(source, /controller.viewPhotos\(item.listing_id\)/);
    assert.match(source, /matchPhotoUrls\(item,/);
  }
  const app = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8');
  const mobileApp = readFileSync(new URL('../../../mobile/App.js', import.meta.url), 'utf8');
  assert.match(app, /onOpenPhotos=.*openZoomedListingImage/);
  assert.match(mobileApp, /onOpenPhotos=.*openExpandedGallery\(images, 0\)/);
});

test('listing chat exports context without transferring mutation approvals', () => {
  for (const path of ['../components/ListingAgentChat.jsx', '../../../mobile/src/components/ListingAgentChat.jsx']) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8');
    assert.match(source, /conversation_context/);
    assert.match(source, /openedPhotoRequest/);
  }
  for (const path of ['../App.jsx', '../../../mobile/App.js']) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8');
    assert.match(source, /onContext=.*pending_action: null/);
    assert.match(source, /result\??\.photo_view/);
    assert.match(source, /openAssistantListingPhotos/);
  }
});

test('matched-item trade requests show both items and require a separate send control', () => {
  for (const path of ['../components/ListingAgentChat.jsx', '../../../mobile/src/components/ListingAgentChat.jsx']) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8');
    assert.match(source, /controller.prepareTrade\(item.listing_id\)/);
    assert.match(source, /session.trade_proposal.offered.title/);
    assert.match(source, /session.trade_proposal.target.title/);
    assert.match(source, /Confirm and send trade request/);
    assert.match(source, /controller.confirmTrade\(\)/);
    assert.match(source, /Cancel trade request/);
    assert.match(source, /Track it in/);
  }
});
test('photo role labels take their own row instead of covering Set Hero', () => {
  const badge = css.match(/\.listing-image-role-badge\s*\{([^}]+)\}/)[1];
  assert.match(badge, /position: static/);
  assert.match(badge, /display: block/);
  assert.doesNotMatch(badge, /bottom:/);
});
test('mobile landing header replaces desktop grid columns instead of flex direction', () => {
  const responsive = css.slice(css.indexOf('@media (max-width: 1100px)'));
  const header = responsive.match(/\.auth-hero-topbar\s*\{([^}]+)\}/)[1];
  assert.match(header, /grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.doesNotMatch(header, /flex-direction/);
});

test('chat confirmations offer Yes and No only on the latest pending action', () => {
  for (const path of ['../App.jsx', '../../../mobile/App.js']) {
    const app = readFileSync(new URL(path, import.meta.url), 'utf8');
    assert.match(app, /message.requires_confirmation && index === appAssistantMessages.length - 1 && appAssistantContext.pending_action/);
    assert.match(app, /sendAppAssistantMessage\('Yes'\)/);
    assert.match(app, /sendAppAssistantMessage\('No'\)/);
  }
});

test('profile layout can respond to mobile widths instead of an inline desktop grid', () => {
  const app = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8');
  assert.match(app, /className="profile-settings-layout"/);
  assert.doesNotMatch(app, /gridTemplateColumns: '220px 1fr'/);
  const mobile = css.slice(css.lastIndexOf('@media (max-width: 760px)'));
  assert.match(mobile, /\.profile-settings-layout[^{}]*\{[^}]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(mobile, /\.inbox-editorial-actions\s*\{[^}]*flex-direction: column/);
  assert.match(mobile, /\.listing-review-layout/);
});
