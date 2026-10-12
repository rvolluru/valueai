// Keep ordinary tab navigation inside React so temporary user-view sessions survive.
export function navigateTabLink(event, tab, navigate) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  navigate(tab)
}
