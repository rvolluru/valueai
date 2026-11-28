// Clerk can report an existing session before React's auth hooks synchronize.
export function isAlreadySignedInError(error) {
  return (error?.errors || [error]).some(entry =>
    entry?.code === 'session_exists'
    || /^you(?:'|’)re already signed in\.?$/i.test(String(entry?.longMessage || entry?.message || '').trim())
  )
}
