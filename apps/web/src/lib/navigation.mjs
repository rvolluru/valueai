// Keep ordinary tab navigation inside React so temporary user-view sessions survive.
export function navigateTabLink(event, tab, navigate) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  navigate(tab)
}

const HISTORY_KEY = 'jouftNavigation'

// Track only app-created entries: history.length also includes external sites.
export function initializeAppHistory(browser) {
  if (browser.history.state?.[HISTORY_KEY]) return
  browser.history.replaceState({ ...browser.history.state, [HISTORY_KEY]: { depth: 0 } }, '', browser.location.href)
}

export function writeAppHistory(browser, href, { replace = false } = {}) {
  initializeAppHistory(browser)
  const current = browser.history.state[HISTORY_KEY]
  const destination = new URL(href, browser.location.href).href
  if (destination === browser.location.href) return false
  const state = { ...browser.history.state, [HISTORY_KEY]: { depth: current.depth + (replace ? 0 : 1) } }
  browser.history[replace ? 'replaceState' : 'pushState'](state, '', destination)
  return true
}

export function backInApp(browser, fallbackHref, onFallback) {
  initializeAppHistory(browser)
  if (browser.history.state[HISTORY_KEY].depth > 0) {
    browser.history.back()
  } else {
    writeAppHistory(browser, fallbackHref, { replace: true })
    onFallback()
  }
}
