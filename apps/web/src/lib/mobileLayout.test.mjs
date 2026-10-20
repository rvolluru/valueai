import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8');
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
    assert.match(source, /controller.load\(initialListingId, newSessionRequestId\)/);
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

test('profile layout can respond to mobile widths instead of an inline desktop grid', () => {
  const app = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8');
  assert.match(app, /className="profile-settings-layout"/);
  assert.doesNotMatch(app, /gridTemplateColumns: '220px 1fr'/);
  const mobile = css.slice(css.lastIndexOf('@media (max-width: 760px)'));
  assert.match(mobile, /\.profile-settings-layout[^{}]*\{[^}]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(mobile, /\.inbox-editorial-actions\s*\{[^}]*flex-direction: column/);
  assert.match(mobile, /\.listing-review-layout/);
});
