import test from 'node:test';
import assert from 'node:assert/strict';
import { SUPPORT_ARTICLES, SUPPORT_CATEGORIES, SUPPORT_CONTACT, searchSupportArticles, supportEmailUrl } from './supportContent.mjs';

test('help articles have unique stable anchors and valid topic categories', () => {
  assert.equal(new Set(SUPPORT_ARTICLES.map(article => article.id)).size, SUPPORT_ARTICLES.length);
  for (const article of SUPPORT_ARTICLES) {
    assert.match(article.id, /^[a-z][a-z-]+$/);
    assert.ok(SUPPORT_CATEGORIES.includes(article.category));
    assert.ok(article.title && article.body.length);
    assert.ok(article.body.every(paragraph => typeof paragraph === 'string' && paragraph.trim()));
    for (const link of article.links || []) assert.ok(['/privacy', '/data-deletion', '/terms'].includes(link.path));
  }
});

test('search finds user problems in titles, text and plain-language synonyms', () => {
  for (const [query, id] of [['forgot password', 'sign-in'], [' MANNEQUIN ', 'ai-preview'], ['$0', 'wrong-analysis'], ['unsubscribe', 'email-updates'], ['cancel subscription', 'billing'], ['camera permissions', 'app-problem'], ['counterfeit', 'trade-problem']]) {
    assert.ok(searchSupportArticles(query).some(article => article.id === id), query);
  }
  assert.equal(searchSupportArticles().length, SUPPORT_ARTICLES.length);
  assert.deepEqual(searchSupportArticles('unfindablexyz'), []);
});

test('topic filters combine with all search terms and do not mutate the content', () => {
  const before = JSON.stringify(SUPPORT_ARTICLES);
  const result = searchSupportArticles('photos', 'Listings & photos');
  assert.ok(result.length);
  assert.ok(result.every(article => article.category === 'Listings & photos'));
  assert.deepEqual(searchSupportArticles('unsubscribe', 'Listings & photos'), []);
  assert.equal(JSON.stringify(SUPPORT_ARTICLES), before);
});

test('contact action creates a reviewable email draft without private account data', () => {
  const url = new URL(supportEmailUrl('Listings & photos'));
  assert.equal(url.protocol, 'mailto:');
  assert.equal(url.pathname, SUPPORT_CONTACT.email);
  assert.equal(url.searchParams.get('subject'), 'Jouft support: Listings & photos');
  const body = url.searchParams.get('body');
  assert.match(body, /Steps to reproduce:\n/);
  assert.match(body, /do not include passwords, verification codes, or full payment details/);
  assert.match(SUPPORT_CONTACT.phoneUrl, /^tel:\+\d+$/);
});
