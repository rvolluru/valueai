import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { navigateTabLink } from './navigation.mjs'

test('ordinary tab clicks navigate without reloading the user-view session', () => {
  for (const tab of ['market', 'portfolio', 'inbox', 'profile']) {
    let prevented = false
    let destination
    navigateTabLink({ button: 0, preventDefault() { prevented = true } }, tab, (value) => { destination = value })
    assert.equal(prevented, true)
    assert.equal(destination, tab)
  }
})

test('modified clicks retain native browser link behavior', () => {
  for (const options of [{ button: 1 }, { metaKey: true }, { ctrlKey: true }, { shiftKey: true }, { altKey: true }, { defaultPrevented: true }]) {
    navigateTabLink({ button: 0, ...options, preventDefault() { assert.fail('must not intercept') } }, 'market', () => assert.fail('must not navigate'))
  }
})

test('all primary tabs use in-app navigation and profile saves avoid page reload', () => {
  const source = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8')
  for (const tab of ['market', 'portfolio', 'inbox', 'profile']) {
    assert.ok(source.includes(`onClick={(event) => navigateTabLink(event, '${tab}', navigateToTab)}`))
  }
  assert.ok(!source.includes("window.location.assign(tabHref('profile'))"))
})
