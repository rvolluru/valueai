import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

test('assistant modal has its own safe-area provider and protects all screen edges', () => {
  const source = readFileSync(new URL('../../App.js', import.meta.url), 'utf8');
  const modal = source.slice(source.indexOf('<Modal visible={appAssistantOpen}'));
  const content = modal.slice(0, modal.indexOf('</Modal>'));
  assert.match(content, /<SafeAreaProvider>\s*<SafeAreaView style=\{styles\.appAssistantRoot\} edges=\{\['top', 'right', 'bottom', 'left'\]\}/);
  assert.match(content, /<\/SafeAreaView>\s*<\/SafeAreaProvider>/);
});
