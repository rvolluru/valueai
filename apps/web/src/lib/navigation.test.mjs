import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { navigateTabLink, initializeAppHistory, writeAppHistory, backInApp } from './navigation.mjs'

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

function fakeBrowser(initial = '/?tab=market') {
  let index = 0
  const entries = [{ href: new URL(initial, 'https://jouft.com').href, state: { unrelated: 'preserved' } }]
  const browser = {
    location: { href: entries[0].href },
    history: {
      get state() { return entries[index].state },
      // Deliberately includes entries outside the app.
      get length() { return entries.length + 10 },
      replaceState(state, _, href) { entries[index] = { state, href }; browser.location.href = href },
      pushState(state, _, href) { entries.splice(index + 1); entries.push({ state, href }); index++; browser.location.href = href },
      back() { assert.ok(index > 0, 'must not leave the app'); index--; browser.location.href = entries[index].href },
      forward() { if (index + 1 < entries.length) { index++; browser.location.href = entries[index].href } },
    },
  }
  return browser
}

test('application Back and browser Back reach identical routes across detail screens', () => {
  for (const [parent, detail] of [
    ['/?tab=market', '/?tab=market&listing=coat'],
    ['/?tab=portfolio', '/?tab=edit_listing&listing=coat'],
    ['/?tab=portfolio', '/?tab=review_listing&listing=coat'],
    ['/?tab=portfolio', '/?tab=closet_matches&listing=coat'],
    ['/?tab=inbox', '/?tab=sender_items&offer=offer-1'],
    ['/?tab=market&listing=coat', '/?tab=trade&listing=coat'],
    ['/?tab=inbox', '/?tab=inbox&detail=coat'],
    ['/?tab=market', '/?tab=market&matches=coat'],
  ]) {
    const app = fakeBrowser(parent)
    const native = fakeBrowser(parent)
    writeAppHistory(app, detail)
    writeAppHistory(native, detail)
    backInApp(app, parent, () => assert.fail('should use history'))
    native.history.back()
    assert.equal(app.location.href, native.location.href)
    app.history.forward()
    assert.equal(app.location.href, new URL(detail, 'https://jouft.com').href)
  }
})

test('deep-linked Back replaces with a safe parent instead of leaving the app', () => {
  const browser = fakeBrowser('/?tab=edit_listing&listing=coat')
  let synced = false
  backInApp(browser, '/?tab=portfolio', () => { synced = true })
  assert.equal(browser.location.href, 'https://jouft.com/?tab=portfolio')
  assert.equal(synced, true)
  assert.equal(browser.history.state.unrelated, 'preserved')
})

test('reselecting a tab does not add duplicate history entries', () => {
  const browser = fakeBrowser()
  initializeAppHistory(browser)
  assert.equal(writeAppHistory(browser, '/?tab=market'), false)
  writeAppHistory(browser, '/?tab=portfolio')
  assert.equal(writeAppHistory(browser, '/?tab=portfolio'), false)
  backInApp(browser, '/?tab=market', () => assert.fail('should have a parent'))
  assert.equal(browser.location.href, 'https://jouft.com/?tab=market')
})

test('replacement redirects preserve history depth and new navigation replaces forward branch', () => {
  const browser = fakeBrowser()
  writeAppHistory(browser, '/?tab=review_listing&listing=coat')
  writeAppHistory(browser, '/?tab=portfolio', { replace: true })
  backInApp(browser, '/?tab=market', () => assert.fail('replacement should retain parent'))
  writeAppHistory(browser, '/?tab=inbox')
  browser.history.forward()
  assert.equal(browser.location.href, 'https://jouft.com/?tab=inbox')
})

test('screen changes are centralized and application Back never uses external history length', () => {
  const source = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8')
  assert.ok(!source.includes('window.history.length'))
  assert.ok(!source.includes('window.history.pushState'))
  assert.ok(!source.includes("setActiveTab('"))
  for (const parent of ['portfolio', 'market', 'inbox']) assert.ok(source.includes(`navigateBack('${parent}')`))
  assert.ok(source.includes("activeTab === 'market' && marketMatchesTarget"))
})
