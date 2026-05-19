import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import {
  SignIn,
  SignUp,
  UserButton,
  useAuth,
  useUser,
} from '@clerk/clerk-react'

const API_DEFAULT =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000')
const CLERK_ENABLED = Boolean(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY)
const IS_PROD = Boolean(import.meta.env.PROD)

const seedListings = [
  {
    id: 'seed-1', owner: 'Mara', title: 'Louis Vuitton Neverfull MM Monogram Tote', mode: 'trade', category: 'handbag', brand: 'Louis Vuitton', condition: 'Good', estimatedValue: 960, city: 'New York, NY', image: 'https://images.unsplash.com/photo-1584917865442-de89df76afd3?auto=format&fit=crop&w=800&q=80', wants: 'Designer tote or shoulder bag in the $850-$1,100 range', tags: ['authenticated', 'monogram', 'trade-only'],
  },
  {
    id: 'seed-2', owner: 'Eli', title: 'Nike Dunk Low Panda (US 10)', mode: 'sell', category: 'shoes', brand: 'Nike', condition: 'LikeNew', estimatedValue: 110, city: 'Austin, TX', image: 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=80', wants: 'Open to trades around sneakers / streetwear', tags: ['sneakers', 'size-10', 'verified-receipt'],
  },
  {
    id: 'seed-3', owner: 'Nina', title: 'Burberry Nova Check Wool Scarf', mode: 'trade', category: 'clothes', brand: 'Burberry', condition: 'Good', estimatedValue: 170, city: 'Seattle, WA', image: 'https://images.unsplash.com/photo-1520903920243-00d872a2d1c9?auto=format&fit=crop&w=800&q=80', wants: 'Trade for premium sneakers or a small leather good', tags: ['accessory', 'winter', 'trade'],
  },
  {
    id: 'seed-4', owner: 'Jordan', title: 'Coach Tabby Shoulder Bag 26', mode: 'sell_trade', category: 'handbag', brand: 'Coach', condition: 'LikeNew', estimatedValue: 280, city: 'Chicago, IL', image: 'https://images.unsplash.com/photo-1594223274512-ad4803739b7c?auto=format&fit=crop&w=800&q=80', wants: 'Cash preferred, open to equal-value trade', tags: ['shoulder-bag', 'neutral', 'modern'],
  },
]

function money(value) {
  if (value == null || Number.isNaN(Number(value))) return 'N/A'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(Number(value))
}

function normalizeMode(mode) {
  if (mode === 'sell_trade') return 'Sell / Trade'
  if (mode === 'trade') return 'Trade'
  return 'Sell'
}

function confidenceLabel(value) {
  if (value == null) return 'n/a'
  return `${Math.round(value * 100)}%`
}

function makeId(prefix) {
  const cryptoApi = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return `${prefix}-${cryptoApi.randomUUID()}`
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function buildSuggestedDescriptionFromProfile(profile) {
  const modelName = profile?.model_identification?.name?.trim?.() || ''
  const attrs = Array.isArray(profile?.model_identification?.attributes)
    ? profile.model_identification.attributes.filter((a) => typeof a === 'string' && a.trim()).slice(0, 6)
    : []
  if (!modelName && attrs.length === 0) return ''
  if (modelName && attrs.length === 0) return `Pre-owned ${modelName}.`
  if (!modelName && attrs.length > 0) return `Key details: ${attrs.join(', ')}.`
  return `${modelName}. Key details: ${attrs.join(', ')}.`
}

function getListingDescription(item) {
  if (!item) return ''
  const profile = item.analysis?.item_profile
  const suggested = buildSuggestedDescriptionFromProfile(profile)
  if (suggested) return suggested
  if (typeof item.description === 'string' && item.description.trim()) return item.description.trim()
  if (typeof item.wants === 'string' && item.wants.trim()) return item.wants.trim()
  return ''
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '')
    reader.onerror = () => reject(reader.error || new Error('Failed reading file'))
    reader.readAsDataURL(file)
  })
}

async function analyzeItem({ apiBaseUrl, apiKey, bearerToken, images, category, userCondition, itemDescription, debug }) {
  const fd = new FormData()
  for (const file of images) fd.append('images', file, file.name)
  if (category) fd.append('category', category)
  if (userCondition) fd.append('user_condition', userCondition)
  if (itemDescription) fd.append('item_description', itemDescription)
  fd.append('debug', String(debug))

  const headers = {}
  if (bearerToken) headers.Authorization = `Bearer ${bearerToken}`
  else if (apiKey) headers['x-api-key'] = apiKey

  const resp = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/analyze`, {
    method: 'POST',
    headers,
    body: fd,
  })

  let payload = null
  try { payload = await resp.json() } catch {}
  if (!resp.ok) {
    const detail = Array.isArray(payload?.detail) ? payload.detail[0]?.msg : payload?.detail
    throw new Error(detail || `API error (${resp.status})`)
  }
  return payload
}

async function fetchAdminAnalyses({ apiBaseUrl, apiKey, bearerToken, limit = 50 }) {
  const headers = {}
  if (bearerToken) headers.Authorization = `Bearer ${bearerToken}`
  else if (apiKey) headers['x-api-key'] = apiKey

  const resp = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/admin/analyses?limit=${limit}`, {
    method: 'GET',
    headers,
  })

  let payload = null
  try { payload = await resp.json() } catch {}
  if (!resp.ok) {
    const detail = Array.isArray(payload?.detail) ? payload.detail[0]?.msg : payload?.detail
    throw new Error(detail || `API error (${resp.status})`)
  }
  return payload
}

async function fetchMyListings({ apiBaseUrl, apiKey, bearerToken, limit = 100 }) {
  const headers = {}
  if (bearerToken) headers.Authorization = `Bearer ${bearerToken}`
  else if (apiKey) headers['x-api-key'] = apiKey
  const resp = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/listings?mine=true&limit=${limit}`, {
    method: 'GET',
    headers,
  })
  let payload = null
  try { payload = await resp.json() } catch {}
  if (!resp.ok) {
    const detail = Array.isArray(payload?.detail) ? payload.detail[0]?.msg : payload?.detail
    throw new Error(detail || `API error (${resp.status})`)
  }
  return payload?.items || []
}

async function createListingRemote({ apiBaseUrl, apiKey, bearerToken, payload }) {
  const headers = { 'Content-Type': 'application/json' }
  if (bearerToken) headers.Authorization = `Bearer ${bearerToken}`
  else if (apiKey) headers['x-api-key'] = apiKey
  const resp = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/listings`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  })
  let data = null
  try { data = await resp.json() } catch {}
  if (!resp.ok) throw new Error(data?.detail || `API error (${resp.status})`)
  return data
}

async function updateListingRemote({ apiBaseUrl, apiKey, bearerToken, listingId, payload }) {
  const headers = { 'Content-Type': 'application/json' }
  if (bearerToken) headers.Authorization = `Bearer ${bearerToken}`
  else if (apiKey) headers['x-api-key'] = apiKey
  const resp = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/listings/${listingId}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(payload),
  })
  let data = null
  try { data = await resp.json() } catch {}
  if (!resp.ok) throw new Error(data?.detail || `API error (${resp.status})`)
  return data
}

export default function App() {
  if (CLERK_ENABLED) return <ClerkMarketplaceApp />
  return <LocalMarketplaceApp />
}

function ClerkMarketplaceApp() {
  const { isLoaded, isSignedIn, getToken } = useAuth()
  const { user } = useUser()
  const [authMode, setAuthMode] = useState('login')

  if (!isLoaded) return <LoadingShell message="Loading authentication..." />

  if (!isSignedIn || !user) {
    return (
      <AuthShell>
        <section className="auth-panel">
          <div className="tab-strip">
            <button className={authMode === 'login' ? 'active' : ''} onClick={() => setAuthMode('login')}>Log In</button>
            <button className={authMode === 'signup' ? 'active' : ''} onClick={() => setAuthMode('signup')}>Sign Up</button>
          </div>
          <div style={{ marginTop: 14 }}>
            {authMode === 'login' ? (
              <SignIn routing="virtual" signUpUrl="#" />
            ) : (
              <SignUp routing="virtual" signInUrl="#" />
            )}
          </div>
          <p className="tiny-note">Clerk is enabled. The app will call the backend using your Clerk bearer token.</p>
        </section>
      </AuthShell>
    )
  }

  const session = {
    id: user.id,
    name: [user.firstName, user.lastName].filter(Boolean).join(' ') || user.username || user.primaryEmailAddress?.emailAddress || 'User',
    email: user.primaryEmailAddress?.emailAddress || '',
  }

  return (
    <MarketplaceWorkspace
      session={session}
      clerkEnabled
      getBearerToken={() => getToken()}
      userMenu={<UserButton afterSignOutUrl="/" />}
    />
  )
}

function LocalMarketplaceApp() {
  const [authMode, setAuthMode] = useState('login')
  const [session, setSession] = useState(null)
  const [users, setUsers] = useState([])
  const [authEmail, setAuthEmail] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authName, setAuthName] = useState('')
  const [authError, setAuthError] = useState('')

  function handleAuthSubmit(e) {
    e.preventDefault()
    setAuthError('')
    const email = authEmail.trim().toLowerCase()
    if (!email || !authPassword.trim()) return setAuthError('Email and password are required.')
    if (authMode === 'signup') {
      if (!authName.trim()) return setAuthError('Display name is required for sign up.')
      if (users.some((u) => u.email === email)) return setAuthError('Account already exists. Log in instead.')
      const nextUser = { id: makeId('user'), email, password: authPassword, name: authName.trim() }
      setUsers((prev) => [...prev, nextUser])
      setSession({ id: nextUser.id, email: nextUser.email, name: nextUser.name })
      setAuthPassword('')
      return
    }
    const found = users.find((u) => u.email === email && u.password === authPassword)
    if (!found) return setAuthError('Invalid credentials. Use demo signup first or correct your password.')
    setSession({ id: found.id, email: found.email, name: found.name })
    setAuthPassword('')
  }

  if (!session) {
    return (
      <AuthShell>
        <section className="auth-panel">
          <div className="tab-strip">
            <button className={authMode === 'login' ? 'active' : ''} onClick={() => setAuthMode('login')}>Log In</button>
            <button className={authMode === 'signup' ? 'active' : ''} onClick={() => setAuthMode('signup')}>Sign Up</button>
          </div>
          <form className="auth-form" onSubmit={handleAuthSubmit}>
            {authMode === 'signup' && (
              <label>
                <span>Display name</span>
                <input value={authName} onChange={(e) => setAuthName(e.target.value)} placeholder="Avery" />
              </label>
            )}
            <label>
              <span>Email</span>
              <input type="email" value={authEmail} onChange={(e) => setAuthEmail(e.target.value)} placeholder="you@example.com" />
            </label>
            <label>
              <span>Password</span>
              <input type="password" value={authPassword} onChange={(e) => setAuthPassword(e.target.value)} placeholder="••••••••" />
            </label>
            {authError && <p className="error-text">{authError}</p>}
            <button className="primary" type="submit">{authMode === 'signup' ? 'Create account' : 'Continue'}</button>
          </form>
          <p className="tiny-note">MVP auth is local-browser demo storage. Add `VITE_CLERK_PUBLISHABLE_KEY` to use Clerk.</p>
        </section>
      </AuthShell>
    )
  }

  return <MarketplaceWorkspace session={session} onLogout={() => setSession(null)} />
}

function AuthShell({ children }) {
  return (
    <div className="shell auth-shell">
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />
      <section className="auth-hero">
        <p className="eyebrow">ValueAI Exchange</p>
        <h1>
          Sell or trade pre-owned fashion with <em>AI valuation confidence</em>
        </h1>
        <p className="lede">
          Upload item photos, infer brand and condition, estimate current market value, and match with buyers or traders in a similar value band.
        </p>
        <div className="hero-cards">
          <div className="hero-card"><span>1</span><h3>Analyze</h3><p>Brand + condition + valuation from your uploaded photos.</p></div>
          <div className="hero-card"><span>2</span><h3>List</h3><p>Create a sell or trade listing with confidence and evidence.</p></div>
          <div className="hero-card"><span>3</span><h3>Match</h3><p>Discover items in your target value range for swaps.</p></div>
        </div>
      </section>
      {children}
    </div>
  )
}

function LoadingShell({ message }) {
  return (
    <div className="shell auth-shell">
      <section className="auth-hero"><h1>ValueAI Exchange</h1><p className="lede">{message}</p></section>
      <section className="auth-panel"><p className="tiny-note">Please wait...</p></section>
    </div>
  )
}

function MarketplaceWorkspace({ session, onLogout, clerkEnabled = false, getBearerToken, userMenu = null }) {
  const [apiBaseUrl] = useState(API_DEFAULT)
  const [apiKey, setApiKey] = useState('local-dev-key')
  const [myListings, setMyListings] = useState([])
  const [activeTab, setActiveTab] = useState('upload')
  const [marketSearch, setMarketSearch] = useState('')
  const [tradeOnly, setTradeOnly] = useState(false)
  const [listingMode, setListingMode] = useState('sell_trade')
  const [itemTitle, setItemTitle] = useState('')
  const [category, setCategory] = useState('')
  const [userCondition, setUserCondition] = useState('')
  const [itemDescription, setItemDescription] = useState('')
  const [askingValue, setAskingValue] = useState('')
  const [tradeNotes, setTradeNotes] = useState('')
  const [images, setImages] = useState([])
  const [previewUrls, setPreviewUrls] = useState([])
  const [editPreviewUrls, setEditPreviewUrls] = useState([])
  const [editImageCount, setEditImageCount] = useState(0)
  const [debugMode, setDebugMode] = useState(true)
  const [adminAnalyses, setAdminAnalyses] = useState([])
  const [adminLoading, setAdminLoading] = useState(false)
  const [adminError, setAdminError] = useState('')
  const [adminSearch, setAdminSearch] = useState('')
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [analysisResult, setAnalysisResult] = useState(null)
  const [receiptPromptPending, setReceiptPromptPending] = useState(false)
  const [receiptPromptDismissed, setReceiptPromptDismissed] = useState(false)
  const [editingListingId, setEditingListingId] = useState(null)
  const [showCreateListingModal, setShowCreateListingModal] = useState(false)
  const [listingModalMode, setListingModalMode] = useState('create')
  const [modalEditingListing, setModalEditingListing] = useState(null)
  const [savedListingNotice, setSavedListingNotice] = useState('')
  const [wizardStep, setWizardStep] = useState(1)

  function fromRemoteListing(item) {
    if (!item) return null
    const resolveUrl = (url) => {
      if (!url || typeof url !== 'string') return null
      if (url.startsWith('blob:')) return null
      if (url.startsWith('/')) return `${apiBaseUrl.replace(/\/$/, '')}${url}`
      return url
    }
    const listedImages = Array.isArray(item.images)
      ? item.images.map(resolveUrl).filter(Boolean)
      : []
    const listedCover = resolveUrl(item.image)
    const fromAnalysisUploads = Array.isArray(item.analysis?.uploaded_images)
      ? item.analysis.uploaded_images.map((u) => resolveUrl(u?.image_url)).filter(Boolean)
      : []
    const targetCount = fromAnalysisUploads.length > 0 ? fromAnalysisUploads.length : null
    let normalizedImages = listedImages.length > 0
      ? listedImages
      : (listedCover ? [listedCover] : [])
    if (targetCount && normalizedImages.length > targetCount) {
      normalizedImages = normalizedImages.slice(0, targetCount)
    }
    if (normalizedImages.length === 0 && fromAnalysisUploads.length > 0) {
      normalizedImages = fromAnalysisUploads
    }
    return {
      id: item.listing_id || item.id,
      owner: item.owner_name || session.name || 'You',
      title: item.title || 'Untitled listing',
      mode: item.mode || 'sell_trade',
      category: item.category || 'unknown',
      brand: item.brand || 'unknown',
      condition: item.condition || 'n/a',
      estimatedValue: Number(item.estimated_value ?? item.estimatedValue ?? 0),
      city: item.city || 'Your area',
      image: normalizedImages[0] || 'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=800&q=80',
      images: normalizedImages,
      description: typeof item.description === 'string' ? item.description : '',
      wants: item.wants || 'Open to similar-value offers',
      tags: Array.isArray(item.tags) ? item.tags : [],
      sourceItemId: item.source_item_id || item.sourceItemId || null,
      analysis: item.analysis || null,
      status: item.status || 'Review',
      createdAt: item.created_at || item.createdAt || null,
    }
  }

  function toRemoteListingPayload(listing) {
    const allowedCategories = ['clothes', 'shoes', 'handbag']
    const allowedConditions = ['New', 'LikeNew', 'Good', 'Fair', 'Poor']
    const normalizedCategory = allowedCategories.includes(listing.category)
      ? listing.category
      : (allowedCategories.includes(listing.analysis?.category) ? listing.analysis.category : 'handbag')
    const normalizedCondition = allowedConditions.includes(listing.condition)
      ? listing.condition
      : 'Good'
    return {
      title: listing.title || 'Untitled listing',
      mode: listing.mode || 'sell_trade',
      category: normalizedCategory,
      brand: listing.brand || 'unknown',
      condition: normalizedCondition,
      estimated_value: Number(listing.estimatedValue || 0),
      city: listing.city || 'Your area',
      image: listing.image || null,
      images: Array.isArray(listing.images) ? listing.images : [],
      wants: listing.wants || 'Open to similar-value offers',
      tags: Array.isArray(listing.tags) ? listing.tags : [],
      source_item_id: listing.sourceItemId || null,
      analysis: listing.analysis || null,
      status: listing.status || 'Review',
      description: listing.description || '',
    }
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const items = await fetchMyListings({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          limit: 100,
        })
        if (!cancelled) setMyListings(items.map(fromRemoteListing).filter(Boolean))
      } catch {
        // Keep local state fallback if API fetch fails.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!images.length) {
        setPreviewUrls([])
        return
      }
      try {
        const urls = await Promise.all(images.map((f) => fileToDataUrl(f)))
        if (!cancelled) setPreviewUrls(urls.filter(Boolean))
      } catch {
        if (!cancelled) setPreviewUrls([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [images])

  const displayedPreviewUrls = images.length > 0
    ? previewUrls
    : (editingListingId ? editPreviewUrls : previewUrls)
  const modalPreviewUrls = listingModalMode === 'edit'
    ? [...editPreviewUrls, ...previewUrls].slice(0, 4)
    : previewUrls.slice(0, 4)

  function shouldPromptForReceipt(payload) {
    const expected = payload?.item_profile?.expected_auth_docs?.usually_provided
    const expectedNorm = typeof expected === 'string' ? expected.toLowerCase() : ''
    const receiptPresent = typeof payload?.item_profile?.receipt_present === 'string'
      ? payload.item_profile.receipt_present.toLowerCase()
      : 'unclear'
    const requested = Array.isArray(payload?.requested_photos) ? payload.requested_photos : []
    const askedByBackend = requested.includes('authenticity_receipt')
    const expectsReceipt = expectedNorm === 'yes' || expectedNorm === 'mixed' || askedByBackend
    return expectsReceipt && receiptPresent !== 'yes'
  }

  const allListings = [...myListings, ...seedListings]
  const deferredMarketSearch = useDeferredValue(marketSearch)

  const filteredListings = useMemo(() => {
    const q = deferredMarketSearch.trim().toLowerCase()
    return allListings.filter((item) => {
      if (tradeOnly && item.mode === 'sell') return false
      if (!q) return true
      return `${item.title} ${item.brand} ${item.category} ${item.city} ${item.wants}`.toLowerCase().includes(q)
    })
  }, [allListings, deferredMarketSearch, tradeOnly])

  const suggestedTrades = useMemo(() => {
    const target = Number(askingValue || analysisResult?.valuation?.estimated_value || 0)
    if (!target) return []
    return allListings
      .filter((item) => item.mode !== 'sell')
      .map((item) => ({ ...item, valueGap: Math.abs(item.estimatedValue - target) }))
      .sort((a, b) => a.valueGap - b.valueGap)
      .slice(0, 6)
  }, [allListings, askingValue, analysisResult])

  const adminFiltered = useMemo(() => {
    const q = adminSearch.trim().toLowerCase()
    if (!q) return adminAnalyses
    return adminAnalyses.filter((entry) => {
      const response = entry.response || {}
      return JSON.stringify({
        item_id: entry.item_id,
        created_at: entry.created_at,
        brand: response.brand?.name,
        category: response.category,
        valuation: response.valuation?.estimated_value,
        user_condition: response.user_condition,
      }).toLowerCase().includes(q)
    })
  }, [adminAnalyses, adminSearch])

  async function loadAdminAnalyses() {
    if (!clerkEnabled && !apiKey.trim()) {
      setAdminError('API key is required.')
      return
    }
    setAdminError('')
    setAdminLoading(true)
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      const payload = await fetchAdminAnalyses({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        limit: 50,
      })
      setAdminAnalyses(payload.items || [])
    } catch (err) {
      setAdminError(err.message || String(err))
    } finally {
      setAdminLoading(false)
    }
  }

  async function analyzeUploadedPhotosForWizard() {
    if (!clerkEnabled && !apiKey.trim()) {
      setAnalysisError('API key is required.')
      return { ok: false, needsReceiptPrompt: false, payload: null }
    }
    setSavedListingNotice('')
    setAnalysisError('')
    setAnalysisLoading(true)
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      const payload = await analyzeItem({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        images,
        category,
        userCondition,
        itemDescription: itemDescription.trim(),
        debug: debugMode,
      })
      setAnalysisResult(payload)
      const needsReceiptPrompt = shouldPromptForReceipt(payload)
      setReceiptPromptPending(needsReceiptPrompt)
      if (!category && payload?.category) setCategory(payload.category)
      const gptTitle = payload?.item_profile?.model_identification?.name?.trim?.() || ''
      const suggestedDesc = buildSuggestedDescriptionFromProfile(payload?.item_profile)
      if (!itemTitle.trim() && gptTitle) setItemTitle(gptTitle)
      if (!itemDescription.trim() && suggestedDesc) setItemDescription(suggestedDesc)
      return { ok: true, needsReceiptPrompt, payload }
    } catch (err) {
      setAnalysisError(err.message || String(err))
      return { ok: false, needsReceiptPrompt: false, payload: null }
    } finally {
      setAnalysisLoading(false)
    }
  }

  async function goToNextWizardStep() {
    if (wizardStep === 1 && (images.length < 1 || images.length > 4)) {
      setAnalysisError('Upload 1 to 4 images before continuing.')
      return
    }
    if (wizardStep === 1 && !userCondition) {
      setAnalysisError('Select item condition before continuing.')
      return
    }
    if (wizardStep === 1) {
      const result = await analyzeUploadedPhotosForWizard()
      if (!result.ok) return
      if (result.needsReceiptPrompt && !receiptPromptDismissed) {
        setAnalysisError('This brand/model is often sold with authenticity receipt or proof of purchase. Upload it if available for better valuation.')
        setWizardStep(1)
        return
      }
    }
    setAnalysisError('')
    setWizardStep((prev) => Math.min(prev + 1, 2))
  }

  function goToPrevWizardStep() {
    setAnalysisError('')
    setWizardStep((prev) => Math.max(prev - 1, 1))
  }

  async function saveListingDraft() {
    if (!analysisResult) return setSavedListingNotice('Run analysis first before publishing your listing.')
    const value = Number(askingValue || analysisResult?.valuation?.estimated_value || 0)
    const listing = {
      id: editingListingId || makeId('listing'),
      owner: session.name || 'You',
      title: itemTitle.trim() || itemDescription.trim() || `${analysisResult.brand.name} ${analysisResult.category}`,
      mode: listingMode,
      category: analysisResult.category,
      brand: analysisResult.brand.name,
      condition: analysisResult.user_condition || analysisResult.condition.grade,
      estimatedValue: value || 0,
      city: 'Your area',
      image: previewUrls[0] || 'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=800&q=80',
      images: previewUrls.length > 0 ? [...previewUrls] : ['https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=800&q=80'],
      description: itemDescription.trim(),
      wants: itemDescription.trim() || 'No description provided.',
      tags: [(analysisResult.user_condition || analysisResult.condition.grade), analysisResult.brand.name, listingMode.replace('_', '/')],
      sourceItemId: analysisResult.item_id,
      analysis: analysisResult,
      status: 'Review',
    }
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      if (editingListingId) {
        const updated = await updateListingRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          listingId: editingListingId,
          payload: toRemoteListingPayload(listing),
        })
        setMyListings((prev) => prev.map((item) => (item.id === editingListingId ? fromRemoteListing(updated) : item)))
      } else {
        const created = await createListingRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          payload: toRemoteListingPayload(listing),
        })
        setMyListings((prev) => [fromRemoteListing(created), ...prev])
      }
    } catch (err) {
      setAnalysisError(err.message || String(err))
      return
    }
    setActiveTab('portfolio')
    setSavedListingNotice(editingListingId ? 'Listing updated.' : 'Listing published to your portfolio. Browse trade matches below.')
    setEditingListingId(null)
  }

  function openEditListing(listing) {
    setActiveTab('upload')
    setWizardStep(2)
    setEditingListingId(listing.id)
    setItemTitle(listing.title || '')
    setCategory(listing.category && listing.category !== 'unknown' ? listing.category : '')
    setUserCondition(listing.condition && listing.condition !== 'n/a' ? listing.condition : '')
    setAskingValue(Number.isFinite(Number(listing.estimatedValue)) ? String(Math.round(Number(listing.estimatedValue))) : '')
    setTradeNotes(listing.wants || '')
    setItemDescription(listing.analysis?.item_profile ? buildSuggestedDescriptionFromProfile(listing.analysis.item_profile) : '')
    setAnalysisResult(listing.analysis || null)
    const existingImages = Array.isArray(listing.images) && listing.images.length > 0
      ? listing.images
      : [listing.image].filter(Boolean)
    setEditImageCount(existingImages.length)
    setEditPreviewUrls(existingImages)
    setImages([])
    setAnalysisError('')
    setSavedListingNotice('Editing listing draft.')
    setReceiptPromptPending(false)
    setReceiptPromptDismissed(false)
  }

  function resetDraft() {
    setWizardStep(1)
    setItemTitle('')
    setCategory('')
    setUserCondition('')
    setItemDescription('')
    setAskingValue('')
    setTradeNotes('')
    setImages([])
    setEditPreviewUrls([])
    setEditImageCount(0)
    setAnalysisResult(null)
    setEditingListingId(null)
    setReceiptPromptPending(false)
    setReceiptPromptDismissed(false)
    setAnalysisError('')
    setSavedListingNotice('')
  }

  async function createListingAndRunAsyncAnalysis() {
    const draftListing = {
      id: makeId('listing'),
      owner: session.name || 'You',
      title: itemTitle.trim() || itemDescription.trim() || 'New listing',
      mode: listingMode,
      category: category || 'unknown',
      brand: 'Analyzing...',
      condition: userCondition || 'n/a',
      estimatedValue: 0,
      city: 'Your area',
      image: previewUrls[0] || 'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=800&q=80',
      images: previewUrls.length > 0 ? [...previewUrls] : ['https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=800&q=80'],
      description: itemDescription.trim(),
      wants: itemDescription.trim() || 'No description provided.',
      tags: ['Analyzing'],
      sourceItemId: null,
      analysis: null,
      status: 'Analyzing',
    }
    let persistedListing = null
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      persistedListing = await createListingRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        payload: toRemoteListingPayload(draftListing),
      })
    } catch (err) {
      setAnalysisError(err.message || String(err))
      return
    }
    const listingId = persistedListing.listing_id
    setMyListings((prev) => [fromRemoteListing(persistedListing), ...prev])
    setActiveTab('portfolio')
    setAnalysisError('')
    setSavedListingNotice('Listing created. AI analysis is running in the background.')

    ;(async () => {
      const result = await analyzeUploadedPhotosForWizard()
      if (!result.ok) {
        try {
          const current = myListings.find((x) => x.id === listingId) || draftListing
          const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
          const failed = await updateListingRemote({
            apiBaseUrl,
            apiKey: clerkEnabled ? '' : apiKey.trim(),
            bearerToken,
            listingId,
            payload: toRemoteListingPayload({ ...current, status: 'AnalysisFailed', tags: ['Analysis failed'] }),
          })
          setMyListings((prev) => prev.map((item) => (item.id === listingId ? fromRemoteListing(failed) : item)))
        } catch {}
        return
      }
      const payload = result.payload || null
      try {
        const current = (myListings.find((x) => x.id === listingId) || fromRemoteListing(persistedListing) || draftListing)
        const resolved = payload || current.analysis
        const resolvedCondition = resolved?.user_condition || resolved?.condition?.grade || current.condition
        const resolvedBrand = resolved?.brand?.name || current.brand
        const resolvedCategory = resolved?.category || current.category
        const resolvedValue = Number(askingValue || resolved?.valuation?.estimated_value || current.estimatedValue || 0)
        const updatedPayload = {
          ...current,
          title: itemTitle.trim() || itemDescription.trim() || resolved?.item_profile?.model_identification?.name || current.title,
          description: (itemDescription || '').trim() || current.description || '',
          brand: resolvedBrand,
          category: resolvedCategory,
          condition: resolvedCondition,
          estimatedValue: resolvedValue,
          sourceItemId: resolved?.item_id || current.sourceItemId,
          analysis: resolved || current.analysis,
          tags: [resolvedCondition, resolvedBrand, listingMode.replace('_', '/')].filter(Boolean),
          status: 'Review',
        }
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const updated = await updateListingRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          listingId,
          payload: toRemoteListingPayload(updatedPayload),
        })
        setMyListings((prev) => prev.map((item) => (item.id === listingId ? fromRemoteListing(updated) : item)))
      } catch {}
      if (result.needsReceiptPrompt && !receiptPromptDismissed) {
        setMyListings((prev) => prev.map((item) => item.id === listingId ? { ...item, tags: [...(item.tags || []), 'Receipt requested'] } : item))
      }
    })()
  }

  async function updateListingAndRunAsyncAnalysis(listing) {
    if (!listing) return
    const existingImages = Array.isArray(listing.images) && listing.images.length > 0
      ? listing.images
      : [listing.image].filter(Boolean)
    const chosenImages = previewUrls.length > 0 ? [...previewUrls] : existingImages
    const coverImage = chosenImages[0] || 'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=800&q=80'

    const pending = {
      ...listing,
      image: coverImage,
      images: chosenImages.length > 0 ? chosenImages : [coverImage],
      condition: userCondition || listing.condition || 'n/a',
      category: category || listing.category || 'unknown',
      description: (itemDescription || '').trim() || listing.description || '',
      status: 'Analyzing',
      tags: ['Analyzing'],
    }
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      const updated = await updateListingRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        listingId: listing.id,
        payload: toRemoteListingPayload(pending),
      })
      setMyListings((prev) => prev.map((item) => item.id === listing.id ? fromRemoteListing(updated) : item))
    } catch (err) {
      setAnalysisError(err.message || String(err))
      return
    }
    setActiveTab('portfolio')
    setAnalysisError('')
    setSavedListingNotice('Listing updated. AI analysis is running in the background.')

    ;(async () => {
      const result = await analyzeUploadedPhotosForWizard()
      if (!result.ok) {
        try {
          const failed = await updateListingRemote({
            apiBaseUrl,
            apiKey: clerkEnabled ? '' : apiKey.trim(),
            bearerToken: clerkEnabled && getBearerToken ? await getBearerToken() : null,
            listingId: listing.id,
            payload: toRemoteListingPayload({ ...pending, status: 'AnalysisFailed', tags: ['Analysis failed'] }),
          })
          setMyListings((prev) => prev.map((item) => item.id === listing.id ? fromRemoteListing(failed) : item))
        } catch {}
        return
      }
      const payload = result.payload || null
      try {
        const current = myListings.find((x) => x.id === listing.id) || pending
        const resolved = payload || current.analysis
        const resolvedCondition = resolved?.user_condition || resolved?.condition?.grade || userCondition || current.condition
        const resolvedBrand = resolved?.brand?.name || current.brand
        const resolvedCategory = resolved?.category || category || current.category
        const resolvedValue = Number(askingValue || resolved?.valuation?.estimated_value || current.estimatedValue || 0)
        const updatedPayload = {
          ...current,
          title: (itemTitle || '').trim() || (itemDescription || '').trim() || resolved?.item_profile?.model_identification?.name || current.title,
          description: (itemDescription || '').trim() || current.description || '',
          brand: resolvedBrand,
          category: resolvedCategory,
          condition: resolvedCondition,
          estimatedValue: resolvedValue,
          sourceItemId: resolved?.item_id || current.sourceItemId,
          analysis: resolved || current.analysis,
          tags: [resolvedCondition, resolvedBrand, (current.mode || listingMode).replace('_', '/')].filter(Boolean),
          status: 'Review',
        }
        const updated = await updateListingRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken: clerkEnabled && getBearerToken ? await getBearerToken() : null,
          listingId: listing.id,
          payload: toRemoteListingPayload(updatedPayload),
        })
        setMyListings((prev) => prev.map((item) => item.id === listing.id ? fromRemoteListing(updated) : item))
      } catch {}
    })()
  }

  async function publishListingActive(listing) {
    if (!listing) return
    const next = {
      ...listing,
      title: (itemTitle || '').trim() || listing.title,
      description: (itemDescription || '').trim() || listing.description || '',
      category: category || listing.category || 'unknown',
      condition: userCondition || listing.condition || 'n/a',
      status: 'Active',
      tags: [
        userCondition || listing.condition || 'n/a',
        listing.brand || 'unknown',
        (listing.mode || listingMode).replace('_', '/'),
      ].filter(Boolean),
    }
    try {
      const updated = await updateListingRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken: clerkEnabled && getBearerToken ? await getBearerToken() : null,
        listingId: listing.id,
        payload: toRemoteListingPayload(next),
      })
      setMyListings((prev) => prev.map((item) => item.id === listing.id ? fromRemoteListing(updated) : item))
    } catch (err) {
      setAnalysisError(err.message || String(err))
      return
    }
    setActiveTab('portfolio')
    setSavedListingNotice('Listing published and set to Active.')
  }

  function openCreateListingModal() {
    resetDraft()
    setListingModalMode('create')
    setModalEditingListing(null)
    setShowCreateListingModal(true)
  }

  function openEditListingModal(listing) {
    const existingImages = Array.isArray(listing.images) && listing.images.length > 0
      ? listing.images
      : [listing.image].filter(Boolean)
    setListingModalMode('edit')
    setModalEditingListing(listing)
    setEditingListingId(listing.id)
    setItemTitle(listing.title || '')
    setCategory(listing.category && listing.category !== 'unknown' ? listing.category : '')
    setUserCondition(listing.condition && listing.condition !== 'n/a' ? listing.condition : '')
    setAskingValue(Number.isFinite(Number(listing.estimatedValue)) ? String(Math.round(Number(listing.estimatedValue))) : '')
    setTradeNotes(listing.wants || '')
    setItemDescription(listing.analysis?.item_profile ? buildSuggestedDescriptionFromProfile(listing.analysis.item_profile) : '')
    setAnalysisResult(listing.analysis || null)
    setImages([])
    setEditImageCount(existingImages.length)
    setEditPreviewUrls(existingImages)
    setReceiptPromptPending(false)
    setReceiptPromptDismissed(false)
    setAnalysisError('')
    setSavedListingNotice('')
    setShowCreateListingModal(true)
  }

  return (
    <div className="shell app-shell">
      <div className="topbar">
        <div className="topbar-copy">
          <p className="eyebrow">ValueAI Exchange</p>
          <h1 className="app-title">Welcome back, {session.name}</h1>
          <p className="topbar-subtitle">
            Analyze inventory, publish listings, and surface trade matches by valuation range.
          </p>
        </div>
        <div className="topbar-actions">
          {!clerkEnabled && <label className="inline-field"><span>API Key</span><input value={apiKey} onChange={(e) => setApiKey(e.target.value)} /></label>}
          {clerkEnabled ? userMenu : <button className="ghost" onClick={onLogout}>Log out</button>}
        </div>
      </div>

      <section className="stats-strip" aria-label="Workspace summary">
        <div className="stat-card">
          <span className="stat-label">My Listings</span>
          <strong>{myListings.length}</strong>
          <small>{myListings.length ? 'Active portfolio items' : 'Create your first listing'}</small>
        </div>
        <div className="stat-card">
          <span className="stat-label">Marketplace Listings</span>
          <strong>{allListings.length}</strong>
          <small>{tradeOnly ? 'Trade-filter enabled' : 'Sell + trade inventory'}</small>
        </div>
      </section>

      <div className="app-grid">
        <aside className="sidebar">
          <p className="sidebar-section-title">Workspace</p>
          <button className={activeTab === 'portfolio' ? 'nav-item active' : 'nav-item'} onClick={() => setActiveTab('portfolio')}>My Listings</button>
          <button className={activeTab === 'market' ? 'nav-item active' : 'nav-item'} onClick={() => setActiveTab('market')}>Marketplace</button>
          <button className={activeTab === 'admin' ? 'nav-item active' : 'nav-item'} onClick={() => setActiveTab('admin')}>Admin</button>
          <div className="sidebar-card"><h3>Trade Targeting</h3><p>Use the AI valuation as your anchor, then tune your target value to discover comparable listings.</p></div>
          <div className="sidebar-card sidebar-card-dark">
            <h3>Capture Tips</h3>
            <p>Lead with a clean full-item shot, then add tag/logo close-ups for more reliable brand confidence and pricing comps.</p>
          </div>
        </aside>

        <main className="content">
          {activeTab === 'upload' && (
            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Analyze + Publish</p>
                  <h2>{editingListingId ? 'Edit listing' : 'Create a sell/trade listing'}</h2>
                </div>
                <div className="header-actions">
                  <button className="ghost" onClick={resetDraft}>Reset draft</button>
                  <label className="toggle"><input type="checkbox" checked={debugMode} onChange={(e) => setDebugMode(e.target.checked)} /><span>Debug</span></label>
                </div>
              </div>

              <div className="upload-layout">
                <form className="upload-form" onSubmit={(e) => e.preventDefault()}>
                  <div className="wizard-steps" aria-label="Listing wizard steps">
                    {['Upload Images', 'Item Details & Review'].map((label, idx) => {
                      const stepNum = idx + 1
                      const state = wizardStep === stepNum ? 'active' : wizardStep > stepNum ? 'done' : ''
                      return (
                        <div key={label} className={`wizard-step ${state}`.trim()}>
                          <span>{stepNum}</span>
                          <strong>{label}</strong>
                        </div>
                      )
                    })}
                  </div>

                  {wizardStep === 1 && (
                    <div className="wizard-pane">
                      <p className="wizard-title">Step 1: Upload images + condition</p>
                      <label>
                        <span>Photos (1-4)</span>
                        <input
                          type="file"
                          accept="image/*"
                          multiple
                          onChange={(e) => {
                            const next = Array.from(e.target.files || []).slice(0, 4)
                            setImages(next)
                            setEditImageCount(next.length)
                            setEditPreviewUrls([])
                            setReceiptPromptPending(false)
                            setReceiptPromptDismissed(false)
                          }}
                        />
                      </label>
                      <label>
                        <span>Your condition assessment</span>
                        <select value={userCondition} onChange={(e) => setUserCondition(e.target.value)} required>
                          <option value="">Select condition</option>
                          <option value="New">New</option>
                          <option value="LikeNew">Like New</option>
                          <option value="Good">Good</option>
                          <option value="Fair">Fair</option>
                          <option value="Poor">Poor</option>
                        </select>
                      </label>
                      {receiptPromptPending && (
                        <div className="warning-list">
                          <p>This brand/model is often sold with authenticity receipt or proof of purchase. Upload a receipt image if available to improve valuation confidence.</p>
                          <button
                            className="ghost"
                            type="button"
                            onClick={() => {
                              setReceiptPromptDismissed(true)
                              setAnalysisError('')
                              setWizardStep(2)
                            }}
                          >
                            Continue without receipt
                          </button>
                        </div>
                      )}
                      <p className="tiny-note">When you click Next, images are analyzed to infer brand and item profile before continuing.</p>
                    </div>
                  )}

                  {wizardStep === 2 && (
                    <div className="wizard-pane">
                      <p className="wizard-title">Step 2: Item details + review</p>
                      <div className="field-grid">
                        <label>
                          <span>Category (optional)</span>
                          <select value={category} onChange={(e) => { setCategory(e.target.value) }}>
                            <option value="">Auto detect</option><option value="clothes">Clothes</option><option value="shoes">Shoes</option><option value="handbag">Handbag</option>
                          </select>
                        </label>
                      </div>

                      <label>
                        <span>Title</span>
                        <textarea
                          value={itemTitle}
                          onChange={(e) => setItemTitle(e.target.value)}
                          rows={2}
                          placeholder="e.g. Jimmy Choo Rosalia 50 Slingback Pump"
                        />
                      </label>

                      <label>
                        <span>Item description</span>
                        <textarea
                          value={itemDescription}
                          onChange={(e) => setItemDescription(e.target.value)}
                          rows={4}
                          placeholder="Describe materials, color, hardware, wear, and notable details."
                        />
                      </label>

                      <div className="gpt-profile-block">
                        <p className="gpt-profile-title">GPT Item Profile Details</p>
                        {analysisResult?.item_profile ? (
                          <pre>{JSON.stringify(analysisResult.item_profile, null, 2)}</pre>
                        ) : (
                          <p className="tiny-note">No GPT item profile was returned from Step 1 image analysis.</p>
                        )}
                      </div>
                      <div className="wizard-review">
                        <span><strong>Title:</strong> {itemTitle || 'n/a'}</span>
                        <span><strong>Images:</strong> {images.length || editImageCount}</span>
                        <span><strong>Category:</strong> {category || 'Auto detect'}</span>
                        <span><strong>Condition:</strong> {userCondition || 'n/a'}</span>
                      </div>
                    </div>
                  )}

                  {analysisError && <p className="error-text">{analysisError}</p>}
                  {savedListingNotice && <p className="ok-text">{savedListingNotice}</p>}
                  <div className="button-row">
                    {wizardStep > 1 && <button className="ghost" type="button" onClick={goToPrevWizardStep}>Back</button>}
                    {wizardStep < 2 && (
                      <button className="primary" type="button" onClick={goToNextWizardStep} disabled={analysisLoading}>
                        {wizardStep === 1 && analysisLoading ? 'Analyzing photos...' : 'Next'}
                      </button>
                    )}
                    {wizardStep === 2 && (
                      <>
                        <button className="primary" type="button" onClick={saveListingDraft}>{editingListingId ? 'Update Listing' : 'Publish Listing'}</button>
                      </>
                    )}
                  </div>
                </form>

                <div className="preview-column">
                  <div className="preview-grid">
                    {displayedPreviewUrls.length === 0 && <div className="empty-preview">Upload 1-4 photos. Recommended: tag/logo close-up + defect close-up.</div>}
                    {displayedPreviewUrls.map((url, idx) => (
                      <figure key={url} className="preview-card"><img src={url} alt={`Upload ${idx + 1}`} /><figcaption>{idx === 0 ? 'Full item' : `Close-up ${idx}`}</figcaption></figure>
                    ))}
                  </div>
                </div>
              </div>

              {analysisResult && wizardStep === 2 && (
                <div className="analysis-panels">
                  <article className="result-card feature">
                    <p className="eyebrow">AI Analysis</p>
                    <h3>{analysisResult.brand.name === 'unknown' ? 'Brand unknown' : analysisResult.brand.name}</h3>
                    <div className="metric-grid">
                      <div><span>Category</span><strong>{analysisResult.category}</strong></div>
                      <div><span>Brand confidence</span><strong>{confidenceLabel(analysisResult.brand.confidence)}</strong></div>
                      <div><span>Condition</span><strong>{analysisResult.condition.grade}</strong></div>
                      <div><span>Condition confidence</span><strong>{confidenceLabel(analysisResult.condition.confidence)}</strong></div>
                    </div>
                    {analysisResult.user_condition && (
                      <div className="request-list">
                        <span>User condition:</span>
                        <code>{analysisResult.user_condition}</code>
                      </div>
                    )}
                    {analysisResult.warnings?.length > 0 && (
                      <div className="warning-list">
                        {analysisResult.warnings.map((warning) => (
                          <p key={warning}>{warning}</p>
                        ))}
                      </div>
                    )}
                    {analysisResult.item_profile?.model_identification?.name && !(IS_PROD && wizardStep === 1) && (
                      <div className="request-list">
                        <span>GPT item profile:</span>
                        <code>{analysisResult.item_profile.model_identification.name}</code>
                      </div>
                    )}
                    {analysisResult.valuation ? (
                      <div className="valuation-band">
                        <div><span>Estimated value</span><strong>{money(analysisResult.valuation.estimated_value)}</strong></div>
                        <div><span>Range</span><strong>{money(analysisResult.valuation.range_low)} - {money(analysisResult.valuation.range_high)}</strong></div>
                        <div><span>Valuation confidence</span><strong>{confidenceLabel(analysisResult.valuation.confidence)}</strong></div>
                      </div>
                    ) : <p className="muted-text">No valuation returned yet (unknown brand or no comps).</p>}
                    {analysisResult.requested_photos?.length > 0 && (
                      <div className="request-list"><span>Requested photos:</span>{analysisResult.requested_photos.map((r) => <code key={r}>{r}</code>)}</div>
                    )}
                  </article>

                  <article className="result-card">
                    <p className="eyebrow">Suggested Trades</p>
                    <h3>Similar-value matches</h3>
                    {suggestedTrades.length === 0 && <p className="muted-text">Set a target asking value or run valuation to generate matches.</p>}
                    <div className="trade-list">
                      {suggestedTrades.map((item) => (
                        <div key={item.id} className="trade-row">
                          <img src={item.image} alt={item.title} />
                          <div><strong>{item.title}</strong><p>{item.brand} • {item.condition} • {item.city}</p><small>{normalizeMode(item.mode)} • Gap {money(item.valueGap)}</small></div>
                          <div className="pill">{money(item.estimatedValue)}</div>
                        </div>
                      ))}
                    </div>
                  </article>
                </div>
              )}
            </section>
          )}

          {activeTab === 'portfolio' && (
            <section className="panel">
              <div className="panel-header">
                <div><p className="eyebrow">Portfolio</p><h2>Your active listings</h2></div>
                <div className="header-actions">
                  <button className="primary" onClick={openCreateListingModal}>Create Listing</button>
                </div>
              </div>
              {myListings.length === 0 ? (
                <div className="empty-state"><h3>No listings yet</h3><p>Analyze an item and publish your first listing to start selling or trading.</p><button className="primary" onClick={() => setActiveTab('upload')}>Create first listing</button></div>
              ) : <div className="listing-grid">{myListings.map((item) => <ListingCard key={item.id} item={item} own onEditDraft={openEditListingModal} />)}</div>}
            </section>
          )}

          {activeTab === 'market' && (
            <section className="panel">
              <div className="panel-header">
                <div><p className="eyebrow">Marketplace</p><h2>Find trade opportunities near your value target</h2></div>
                <div className="market-controls"><input value={marketSearch} onChange={(e) => setMarketSearch(e.target.value)} placeholder="Search brand, category, city, style..." /><label className="toggle"><input type="checkbox" checked={tradeOnly} onChange={(e) => setTradeOnly(e.target.checked)} /><span>Trade only</span></label></div>
              </div>
              <div className="listing-grid">
                {filteredListings.map((item) => {
                  const baseValue = Number(item.estimatedValue || 0)
                  const tolerance = Math.max(50, baseValue * 0.2)
                  const similarItems = allListings
                    .filter((candidate) => candidate.id !== item.id)
                    .filter((candidate) => (candidate.owner || '') !== (item.owner || ''))
                    .filter((candidate) => Math.abs(Number(candidate.estimatedValue || 0) - baseValue) <= tolerance)
                    .slice(0, 5)
                  return <ListingCard key={item.id} item={item} similarItems={similarItems} marketplaceCompact />
                })}
              </div>
            </section>
          )}

          {activeTab === 'admin' && (
            <section className="panel">
              <div className="panel-header">
                <div><p className="eyebrow">Admin</p><h2>All analyzed listings with debug</h2></div>
                <div className="market-controls">
                  <input value={adminSearch} onChange={(e) => setAdminSearch(e.target.value)} placeholder="Search item, brand, category..." />
                  <button className="primary" onClick={loadAdminAnalyses} disabled={adminLoading}>{adminLoading ? 'Loading...' : 'Refresh'}</button>
                </div>
              </div>
              {adminError && <p className="error-text">{adminError}</p>}
              {adminFiltered.length === 0 ? (
                <div className="empty-state">
                  <h3>No admin data loaded</h3>
                  <p>Fetch recent analyses to inspect listings, valuations, and debug payloads.</p>
                </div>
              ) : (
                <div className="admin-grid">
                  {adminFiltered.map((entry) => (
                    <AdminAnalysisCard key={entry.analysis_id} entry={entry} />
                  ))}
                </div>
              )}
            </section>
          )}
        </main>
      </div>

      {showCreateListingModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'grid', placeItems: 'center', zIndex: 1000 }}>
          <div style={{ width: 'min(620px, 92vw)', maxHeight: '88vh', overflowY: 'auto', background: '#fff', borderRadius: 14, padding: 18, boxShadow: '0 24px 80px rgba(0,0,0,.25)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <h3 style={{ margin: 0 }}>{listingModalMode === 'edit' ? 'Edit Draft' : 'Create Listing'}</h3>
              <button className="ghost small" type="button" onClick={() => setShowCreateListingModal(false)}>Close</button>
            </div>
            <p className="tiny-note" style={{ marginTop: 0 }}>
              {listingModalMode === 'edit'
                ? 'Edit mode: update images/condition, then continue to listing details.'
                : 'Step 1: Upload images and select condition.'}
            </p>
            {listingModalMode === 'edit' ? (
              <>
                <p style={{ margin: '4px 0 8px' }}><strong>Images (1-4)</strong></p>
                <input
                  id="edit-draft-image-input"
                  type="file"
                  accept="image/*"
                  multiple
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    const selected = Array.from(e.target.files || [])
                    const maxNew = Math.max(0, 4 - editPreviewUrls.length)
                    setImages((prev) => {
                      const room = Math.max(0, maxNew - prev.length)
                      return room > 0 ? [...prev, ...selected.slice(0, room)] : prev
                    })
                    setReceiptPromptPending(false)
                    setReceiptPromptDismissed(false)
                  }}
                />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8, marginTop: 4, marginBottom: 12 }}>
                  {modalPreviewUrls.map((url, idx) => (
                    <div key={url} style={{ border: '1px solid #ddd', borderRadius: 8, overflow: 'hidden', background: '#f7f7f7' }}>
                      <img src={url} alt={`Upload ${idx + 1}`} style={{ width: '100%', height: 80, objectFit: 'cover', display: 'block' }} />
                    </div>
                  ))}
                  {modalPreviewUrls.length < 4 && (
                    <label
                      htmlFor="edit-draft-image-input"
                      style={{
                        height: 80,
                        border: '1px dashed #9ca3af',
                        borderRadius: 8,
                        display: 'grid',
                        placeItems: 'center',
                        background: '#f9fafb',
                        fontSize: 28,
                        color: '#6b7280',
                        cursor: 'pointer',
                        userSelect: 'none',
                      }}
                      title="Add image"
                    >
                      +
                    </label>
                  )}
                </div>
                <label>
                  <span>Category</span>
                  <select value={category} onChange={(e) => setCategory(e.target.value)}>
                    <option value="">Auto detect</option>
                    <option value="clothes">Clothes</option>
                    <option value="shoes">Shoes</option>
                    <option value="handbag">Handbag</option>
                  </select>
                </label>
                <label>
                  <span>Title</span>
                  <textarea
                    value={itemTitle}
                    onChange={(e) => setItemTitle(e.target.value)}
                    rows={2}
                    placeholder="e.g. Jimmy Choo Rosalia 50 Slingback Pump"
                  />
                </label>
                <label>
                  <span>Item description</span>
                  <textarea
                    value={itemDescription}
                    onChange={(e) => setItemDescription(e.target.value)}
                    rows={4}
                    placeholder="Describe materials, color, hardware, wear, and notable details."
                  />
                </label>
              </>
            ) : (
              <label>
                <span>Photos (1-4)</span>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={(e) => {
                    const next = Array.from(e.target.files || []).slice(0, 4)
                    setImages(next)
                    setEditImageCount(next.length)
                    setEditPreviewUrls([])
                    setReceiptPromptPending(false)
                    setReceiptPromptDismissed(false)
                  }}
                />
              </label>
            )}
            <label>
              <span>Your condition assessment</span>
              <select value={userCondition} onChange={(e) => setUserCondition(e.target.value)} required>
                <option value="">Select condition</option>
                <option value="New">New</option>
                <option value="LikeNew">Like New</option>
                <option value="Good">Good</option>
                <option value="Fair">Fair</option>
                <option value="Poor">Poor</option>
              </select>
            </label>
            {listingModalMode === 'edit' && (
              <div className="warning-list" style={{ marginTop: 10 }}>
                <p>
                  This brand/model is often sold with authenticity receipt or proof of purchase.
                  Uploading receipt can improve valuation confidence.
                </p>
                <input
                  id="edit-draft-receipt-input"
                  type="file"
                  accept="image/*"
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    if (!modalEditingListing) return
                    const file = Array.from(e.target.files || [])[0]
                    if (!file) return
                    setImages((prev) => {
                      const maxNew = Math.max(0, 4 - editPreviewUrls.length)
                      if (maxNew <= 0) return prev
                      return [...prev.slice(0, Math.max(0, maxNew - 1)), file]
                    })
                    setShowCreateListingModal(false)
                    setReceiptPromptPending(false)
                    setReceiptPromptDismissed(false)
                    setTimeout(() => {
                      updateListingAndRunAsyncAnalysis(modalEditingListing)
                    }, 0)
                  }}
                />
                <div className="button-row">
                  <label htmlFor="edit-draft-receipt-input" className="primary" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', textDecoration: 'none' }}>
                    Upload authenticity receipt
                  </label>
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => {
                      if (!modalEditingListing) return
                      setShowCreateListingModal(false)
                      publishListingActive(modalEditingListing)
                    }}
                  >
                    Publish Listing
                  </button>
                </div>
              </div>
            )}
            {listingModalMode === 'edit' && modalEditingListing?.analysis && (
              <div className="analysis-panels" style={{ marginTop: 12 }}>
                <article className="result-card feature">
                  <p className="eyebrow">AI Analysis</p>
                  <h3>{modalEditingListing.analysis.brand?.name === 'unknown' ? 'Brand unknown' : (modalEditingListing.analysis.brand?.name || 'Unknown')}</h3>
                  <div className="metric-grid">
                    <div><span>Category</span><strong>{modalEditingListing.analysis.category || 'unknown'}</strong></div>
                    <div><span>Brand confidence</span><strong>{confidenceLabel(modalEditingListing.analysis.brand?.confidence)}</strong></div>
                    <div><span>Condition</span><strong>{modalEditingListing.analysis.condition?.grade || modalEditingListing.condition || 'n/a'}</strong></div>
                    <div><span>Condition confidence</span><strong>{confidenceLabel(modalEditingListing.analysis.condition?.confidence)}</strong></div>
                  </div>
                  {modalEditingListing.analysis.user_condition && (
                    <div className="request-list">
                      <span>User condition:</span>
                      <code>{modalEditingListing.analysis.user_condition}</code>
                    </div>
                  )}
                  {modalEditingListing.analysis.warnings?.length > 0 && (
                    <div className="warning-list">
                      {modalEditingListing.analysis.warnings.map((warning) => (
                        <p key={warning}>{warning}</p>
                      ))}
                    </div>
                  )}
                  {modalEditingListing.analysis.item_profile?.model_identification?.name && (
                    <div className="request-list">
                      <span>GPT item profile:</span>
                      <code>{modalEditingListing.analysis.item_profile.model_identification.name}</code>
                    </div>
                  )}
                  {modalEditingListing.analysis.valuation ? (
                    <div className="valuation-band">
                      <div><span>Estimated value</span><strong>{money(modalEditingListing.analysis.valuation.estimated_value)}</strong></div>
                      <div><span>Range</span><strong>{money(modalEditingListing.analysis.valuation.range_low)} - {money(modalEditingListing.analysis.valuation.range_high)}</strong></div>
                      <div><span>Valuation confidence</span><strong>{confidenceLabel(modalEditingListing.analysis.valuation.confidence)}</strong></div>
                    </div>
                  ) : <p className="muted-text">No valuation returned yet (unknown brand or no comps).</p>}
                  {modalEditingListing.analysis.requested_photos?.length > 0 && (
                    <div className="request-list"><span>Requested photos:</span>{modalEditingListing.analysis.requested_photos.map((r) => <code key={r}>{r}</code>)}</div>
                  )}
                </article>
              </div>
            )}
            {listingModalMode !== 'edit' && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8, marginTop: 12 }}>
                {modalPreviewUrls.map((url, idx) => (
                  <div key={url} style={{ border: '1px solid #ddd', borderRadius: 8, overflow: 'hidden', background: '#f7f7f7' }}>
                    <img src={url} alt={`Upload ${idx + 1}`} style={{ width: '100%', height: 80, objectFit: 'cover', display: 'block' }} />
                  </div>
                ))}
              </div>
            )}
            <div className="button-row" style={{ marginTop: 14 }}>
              <button className="ghost" type="button" onClick={() => setShowCreateListingModal(false)}>Cancel</button>
              {listingModalMode !== 'edit' && (
                <button
                  className="primary"
                  type="button"
                  onClick={() => {
                    const currentImageCount = modalPreviewUrls.length
                    if (currentImageCount < 1 || currentImageCount > 4) {
                      setAnalysisError('Upload 1 to 4 images before continuing.')
                      return
                    }
                    if (!userCondition) {
                      setAnalysisError('Select item condition before continuing.')
                      return
                    }
                    setShowCreateListingModal(false)
                    createListingAndRunAsyncAnalysis()
                  }}
                >
                  Continue
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ListingCard({ item, own = false, onEditDraft = null, similarItems = [], marketplaceCompact = false }) {
  const gallery = Array.isArray(item.images) && item.images.length > 0
    ? item.images
    : [item.image].filter(Boolean)
  const [activeImageIdx, setActiveImageIdx] = useState(0)
  const safeIndex = Math.min(activeImageIdx, Math.max(gallery.length - 1, 0))
  const imageSrc = gallery[safeIndex] || 'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=800&q=80'

  function showPrev() {
    if (gallery.length <= 1) return
    setActiveImageIdx((prev) => (prev - 1 + gallery.length) % gallery.length)
  }

  function showNext() {
    if (gallery.length <= 1) return
    setActiveImageIdx((prev) => (prev + 1) % gallery.length)
  }

  const statusLabel = item.status || 'Review'
  const statusClass = `status-${String(statusLabel).toLowerCase().replace(/\s+/g, '')}`
  const editDisabled = own && String(statusLabel).toLowerCase() === 'analyzing'
  const badgeLabel = item.status || 'Active'
  const badgeClass = `status-${String(badgeLabel).toLowerCase().replace(/\s+/g, '')}`
  const [selectedMatch, setSelectedMatch] = useState(null)
  const anchorValue = Number(item.estimatedValue || 0)

  function matchLabel(sim) {
    const simValue = Number(sim?.estimatedValue || 0)
    if (!(anchorValue > 0) || !(simValue > 0)) return 'Match'
    const pctGap = Math.abs(simValue - anchorValue) / anchorValue
    if (pctGap <= 0.08) return 'Best Match'
    if (pctGap <= 0.18) return 'Close'
    return 'Stretch'
  }

  return (
    <>
      <article className="listing-card">
        <div className="image-wrap">
        <img src={imageSrc} alt={item.title} />
        <span className={`mode-badge ${badgeClass}`}>{badgeLabel}</span>
        {gallery.length > 1 && (
          <div style={{ position: 'absolute', left: 8, right: 8, bottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <button className="ghost small" type="button" onClick={showPrev}>‹</button>
            <span style={{ fontSize: 12, color: '#fff', background: 'rgba(0,0,0,.55)', borderRadius: 999, padding: '2px 8px' }}>{safeIndex + 1}/{gallery.length}</span>
            <button className="ghost small" type="button" onClick={showNext}>›</button>
          </div>
        )}
      </div>
      <div className="listing-body">
        <div className="listing-head">
          <h3>{item.title}</h3>
          {!marketplaceCompact && <div className="value-chip">{money(item.estimatedValue)}</div>}
        </div>
        <p className="listing-notes">{getListingDescription(item) || 'No description provided.'}</p>
        {!own && similarItems.length > 0 && (
          <div className="similar-section">
            <div className="similar-head">
              <small>Similar Price Matches</small>
              <span>{similarItems.length} items</span>
            </div>
            <div className="similar-rail">
              {similarItems.slice(0, 6).map((sim) => (
                <button
                  key={sim.id}
                  type="button"
                  className="similar-card"
                  onClick={() => setSelectedMatch(sim)}
                  title={`${sim.title} • ${money(sim.estimatedValue)}`}
                >
                  <img
                    src={(Array.isArray(sim.images) && sim.images.length > 0 ? sim.images[0] : sim.image) || 'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=800&q=80'}
                    alt={sim.title}
                  />
                  <div className="similar-card-body">
                    <span className="similar-score">{matchLabel(sim)}</span>
                    <strong>{money(sim.estimatedValue)}</strong>
                    <small>{sim.title || 'Untitled item'}</small>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
        {!marketplaceCompact && <div className="tag-row">{(item.tags || []).slice(0, 4).map((tag) => <span key={tag}>{tag}</span>)}</div>}
        {!marketplaceCompact && (
          <div className="listing-footer">
            <small>{own ? 'Your listing' : `Listed by ${item.owner}`}</small>
            <button
              className="ghost small"
              type="button"
              disabled={editDisabled}
              title={editDisabled ? 'Cannot edit while analysis is running' : undefined}
              onClick={() => (own && !editDisabled ? onEditDraft?.(item) : null)}
            >
              {own ? 'Edit draft' : 'Open offer'}
            </button>
          </div>
        )}
      </div>
      </article>
      {selectedMatch && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'grid', alignItems: 'start', justifyItems: 'center', zIndex: 1100, overflowY: 'auto', padding: '24px 12px' }}>
          <div style={{ width: 'min(640px, 92vw)', maxHeight: 'calc(100vh - 48px)', overflowY: 'auto', background: '#fff', borderRadius: 14, padding: 16, boxShadow: '0 24px 80px rgba(0,0,0,.25)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Matched Item Details</h3>
              <button className="ghost small" type="button" onClick={() => setSelectedMatch(null)}>Close</button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8, marginBottom: 12 }}>
              {(Array.isArray(selectedMatch.images) && selectedMatch.images.length > 0
                ? selectedMatch.images
                : [selectedMatch.image].filter(Boolean)
              ).map((url) => (
                <img
                  key={url}
                  src={url}
                  alt={selectedMatch.title}
                  style={{ width: '100%', height: 110, objectFit: 'cover', borderRadius: 10, border: '1px solid rgba(18,26,36,0.12)' }}
                />
              ))}
            </div>
            <div className="metric-grid">
              <div><span>Title</span><strong>{selectedMatch.title || 'n/a'}</strong></div>
              <div><span>Estimated value</span><strong>{money(selectedMatch.estimatedValue)}</strong></div>
              <div><span>Brand</span><strong>{selectedMatch.brand || 'n/a'}</strong></div>
              <div><span>Category</span><strong>{selectedMatch.category || 'n/a'}</strong></div>
              <div><span>Condition</span><strong>{selectedMatch.condition || 'n/a'}</strong></div>
              <div><span>City</span><strong>{selectedMatch.city || 'n/a'}</strong></div>
              <div><span>Owner</span><strong>{selectedMatch.owner || 'n/a'}</strong></div>
            </div>
            <p className="listing-notes" style={{ marginTop: 12 }}>{selectedMatch.wants || 'No additional notes.'}</p>
            <div className="button-row" style={{ marginTop: 12 }}>
              <button
                className="primary"
                type="button"
                onClick={() => {
                  setSelectedMatch(null)
                  if (typeof window !== 'undefined') {
                    window.alert('Trade request flow will be wired next.')
                  }
                }}
              >
                Trade
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function AdminAnalysisCard({ entry }) {
  const response = entry.response || {}
  const debug = response.debug || {}
  return (
    <article className="admin-card">
      <div className="admin-card-head">
        <div>
          <p className="eyebrow">Analysis</p>
          <h3>{response.brand?.name || 'unknown'} • {response.category || 'unknown'}</h3>
          <p className="listing-meta">{entry.item_id} • {new Date(entry.created_at).toLocaleString()}</p>
        </div>
        <div className="value-chip">{money(response.valuation?.estimated_value)}</div>
      </div>
      <div className="admin-metrics">
        <div><span>Condition</span><strong>{response.condition?.grade || 'n/a'}</strong></div>
        <div><span>User condition</span><strong>{response.user_condition || 'n/a'}</strong></div>
        <div><span>Brand confidence</span><strong>{confidenceLabel(response.brand?.confidence)}</strong></div>
        <div><span>Valuation basis</span><strong>{response.valuation?.basis || 'n/a'}</strong></div>
      </div>
      <div className="tag-row">
        {(response.requested_photos || []).map((tag) => <span key={tag}>{tag}</span>)}
        {(response.warnings || []).map((tag) => <span key={tag}>{tag}</span>)}
      </div>
      <details className="debug-block" open={false}>
        <summary>Debug payload</summary>
        <pre>{JSON.stringify(debug, null, 2)}</pre>
      </details>
      <details className="debug-block">
        <summary>Full response</summary>
        <pre>{JSON.stringify(response, null, 2)}</pre>
      </details>
    </article>
  )
}
