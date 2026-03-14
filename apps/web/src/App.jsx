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
const STORAGE_KEY = 'valueai_exchange_state_v2'
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

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveState(state) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

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
  const persisted = loadState()
  const [authMode, setAuthMode] = useState('login')
  const [session, setSession] = useState(persisted?.session ?? null)
  const [users, setUsers] = useState(persisted?.users ?? [])
  const [authEmail, setAuthEmail] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authName, setAuthName] = useState('')
  const [authError, setAuthError] = useState('')

  useEffect(() => {
    saveState({ ...(loadState() || {}), session, users })
  }, [session, users])

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
  const persisted = loadState()
  const [apiBaseUrl] = useState(persisted?.apiBaseUrl ?? API_DEFAULT)
  const [apiKey, setApiKey] = useState(persisted?.apiKey ?? 'local-dev-key')
  const [myListings, setMyListings] = useState(persisted?.myListings ?? [])
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
  const [debugMode, setDebugMode] = useState(true)
  const [adminAnalyses, setAdminAnalyses] = useState([])
  const [adminLoading, setAdminLoading] = useState(false)
  const [adminError, setAdminError] = useState('')
  const [adminSearch, setAdminSearch] = useState('')
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [analysisResult, setAnalysisResult] = useState(null)
  const [savedListingNotice, setSavedListingNotice] = useState('')
  const [wizardStep, setWizardStep] = useState(1)

  useEffect(() => {
    const base = loadState() || {}
    saveState({ ...base, apiBaseUrl, apiKey, myListings, ...(base.users ? { users: base.users } : {}), ...(base.session ? { session: base.session } : {}) })
  }, [apiBaseUrl, apiKey, myListings])

  useEffect(() => {
    const urls = images.map((f) => URL.createObjectURL(f))
    setPreviewUrls(urls)
    return () => urls.forEach((u) => URL.revokeObjectURL(u))
  }, [images])

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
      return false
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
        userCondition: '',
        itemDescription: itemDescription.trim(),
        debug: debugMode,
      })
      setAnalysisResult(payload)
      if (!category && payload?.category) setCategory(payload.category)
      const gptTitle = payload?.item_profile?.model_identification?.name?.trim?.() || ''
      const suggestedDesc = buildSuggestedDescriptionFromProfile(payload?.item_profile)
      if (!itemTitle.trim() && gptTitle) setItemTitle(gptTitle)
      if (!itemDescription.trim() && suggestedDesc) setItemDescription(suggestedDesc)
      return true
    } catch (err) {
      setAnalysisError(err.message || String(err))
      return false
    } finally {
      setAnalysisLoading(false)
    }
  }

  async function analyzePricingForWizardStep2() {
    if (!clerkEnabled && !apiKey.trim()) {
      setAnalysisError('API key is required.')
      return false
    }
    if (!userCondition) {
      setAnalysisError('Condition assessment is required.')
      return false
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
      if (payload?.valuation?.estimated_value != null) {
        setAskingValue(String(Math.round(payload.valuation.estimated_value)))
      } else {
        setAskingValue('')
      }
      return true
    } catch (err) {
      setAnalysisError(err.message || String(err))
      return false
    } finally {
      setAnalysisLoading(false)
    }
  }

  async function goToNextWizardStep() {
    if (wizardStep === 1 && (images.length < 1 || images.length > 4)) {
      setAnalysisError('Upload 1 to 4 images before continuing.')
      return
    }
    if (wizardStep === 1) {
      const ok = await analyzeUploadedPhotosForWizard()
      if (!ok) return
    }
    if (wizardStep === 2) {
      const ok = await analyzePricingForWizardStep2()
      if (!ok) return
    }
    setAnalysisError('')
    setWizardStep((prev) => Math.min(prev + 1, 3))
  }

  function goToPrevWizardStep() {
    setAnalysisError('')
    setWizardStep((prev) => Math.max(prev - 1, 1))
  }

  function saveListingDraft() {
    if (!analysisResult) return setSavedListingNotice('Run analysis first before publishing your listing.')
    const value = Number(askingValue || analysisResult?.valuation?.estimated_value || 0)
    const listing = {
      id: makeId('listing'),
      owner: session.name || 'You',
      title: itemTitle.trim() || itemDescription.trim() || `${analysisResult.brand.name} ${analysisResult.category}`,
      mode: listingMode,
      category: analysisResult.category,
      brand: analysisResult.brand.name,
      condition: analysisResult.user_condition || analysisResult.condition.grade,
      estimatedValue: value || 0,
      city: 'Your area',
      image: previewUrls[0] || 'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=800&q=80',
      wants: tradeNotes.trim() || 'Open to similar-value offers',
      tags: [(analysisResult.user_condition || analysisResult.condition.grade), analysisResult.brand.name, listingMode.replace('_', '/')],
      sourceItemId: analysisResult.item_id,
      analysis: analysisResult,
    }
    setMyListings((prev) => [listing, ...prev])
    setActiveTab('portfolio')
    setSavedListingNotice('Listing published to your portfolio. Browse trade matches below.')
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
    setAnalysisResult(null)
    setAnalysisError('')
    setSavedListingNotice('')
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
          <button className={activeTab === 'upload' ? 'nav-item active' : 'nav-item'} onClick={() => setActiveTab('upload')}>Create Listing</button>
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
                <div><p className="eyebrow">Analyze + Publish</p><h2>Create a sell/trade listing</h2></div>
                <div className="header-actions">
                  <button className="ghost" onClick={resetDraft}>Reset draft</button>
                  <label className="toggle"><input type="checkbox" checked={debugMode} onChange={(e) => setDebugMode(e.target.checked)} /><span>Debug</span></label>
                </div>
              </div>

              <div className="upload-layout">
                <form className="upload-form" onSubmit={(e) => e.preventDefault()}>
                  <div className="wizard-steps" aria-label="Listing wizard steps">
                    {['Upload Images', 'Item Details', 'Review & Analyze'].map((label, idx) => {
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
                      <p className="wizard-title">Step 1: Upload images + run GPT photo analysis</p>
                      <label>
                        <span>Photos (1-4)</span>
                        <input type="file" accept="image/*" multiple onChange={(e) => setImages(Array.from(e.target.files || []).slice(0, 4))} />
                      </label>
                      <p className="tiny-note">When you click Next, images are analyzed to infer brand and item profile before continuing.</p>
                    </div>
                  )}

                  {wizardStep === 2 && (
                    <div className="wizard-pane">
                      <p className="wizard-title">Step 2: Item details</p>
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

                      <div className="gpt-profile-block">
                        <p className="gpt-profile-title">GPT Item Profile Details</p>
                        {analysisResult?.item_profile ? (
                          <pre>{JSON.stringify(analysisResult.item_profile, null, 2)}</pre>
                        ) : (
                          <p className="tiny-note">No GPT item profile was returned from Step 1 image analysis.</p>
                        )}
                      </div>
                    </div>
                  )}

                  {wizardStep === 3 && (
                    <div className="wizard-pane">
                      <p className="wizard-title">Step 3: Review + analyze</p>
                      <div className="field-grid two">
                        <label>
                          <span>Listing mode</span>
                          <select value={listingMode} onChange={(e) => setListingMode(e.target.value)}>
                            <option value="sell">Sell only</option><option value="trade">Trade only</option><option value="sell_trade">Sell or trade</option>
                          </select>
                        </label>
                        <label><span>Target asking value (USD)</span><input type="number" min="0" value={askingValue} onChange={(e) => setAskingValue(e.target.value)} placeholder="Auto from valuation" /></label>
                      </div>
                      <label><span>Trade preferences / notes</span><input value={tradeNotes} onChange={(e) => setTradeNotes(e.target.value)} placeholder="What kinds of items would you trade for?" /></label>
                      <div className="wizard-review">
                        <span><strong>Title:</strong> {itemTitle || 'n/a'}</span>
                        <span><strong>Images:</strong> {images.length}</span>
                        <span><strong>Mode:</strong> {listingMode.replace('_', ' / ')}</span>
                        <span><strong>Category:</strong> {category || 'Auto detect'}</span>
                        <span><strong>Condition:</strong> {userCondition || 'n/a'}</span>
                      </div>
                    </div>
                  )}

                  {analysisError && <p className="error-text">{analysisError}</p>}
                  {savedListingNotice && <p className="ok-text">{savedListingNotice}</p>}
                  <div className="button-row">
                    {wizardStep > 1 && <button className="ghost" type="button" onClick={goToPrevWizardStep}>Back</button>}
                    {wizardStep < 3 && (
                      <button className="primary" type="button" onClick={goToNextWizardStep} disabled={analysisLoading}>
                        {wizardStep === 1 && analysisLoading ? 'Analyzing photos...' : wizardStep === 2 && analysisLoading ? 'Analyzing pricing...' : 'Next'}
                      </button>
                    )}
                    {wizardStep === 3 && (
                      <>
                        <button className="primary" type="button" onClick={saveListingDraft}>Publish Listing</button>
                      </>
                    )}
                  </div>
                </form>

                <div className="preview-column">
                  <div className="preview-grid">
                    {previewUrls.length === 0 && <div className="empty-preview">Upload 1-4 photos. Recommended: tag/logo close-up + defect close-up.</div>}
                    {previewUrls.map((url, idx) => (
                      <figure key={url} className="preview-card"><img src={url} alt={`Upload ${idx + 1}`} /><figcaption>{idx === 0 ? 'Full item' : `Close-up ${idx}`}</figcaption></figure>
                    ))}
                  </div>
                </div>
              </div>

              {analysisResult && wizardStep !== 2 && (
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
              <div className="panel-header"><div><p className="eyebrow">Portfolio</p><h2>Your active listings</h2></div></div>
              {myListings.length === 0 ? (
                <div className="empty-state"><h3>No listings yet</h3><p>Analyze an item and publish your first listing to start selling or trading.</p><button className="primary" onClick={() => setActiveTab('upload')}>Create first listing</button></div>
              ) : <div className="listing-grid">{myListings.map((item) => <ListingCard key={item.id} item={item} own />)}</div>}
            </section>
          )}

          {activeTab === 'market' && (
            <section className="panel">
              <div className="panel-header">
                <div><p className="eyebrow">Marketplace</p><h2>Find trade opportunities near your value target</h2></div>
                <div className="market-controls"><input value={marketSearch} onChange={(e) => setMarketSearch(e.target.value)} placeholder="Search brand, category, city, style..." /><label className="toggle"><input type="checkbox" checked={tradeOnly} onChange={(e) => setTradeOnly(e.target.checked)} /><span>Trade only</span></label></div>
              </div>
              <div className="listing-grid">{filteredListings.map((item) => <ListingCard key={item.id} item={item} />)}</div>
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
    </div>
  )
}

function ListingCard({ item, own = false }) {
  return (
    <article className="listing-card">
      <div className="image-wrap">
        <img src={item.image} alt={item.title} />
        <span className={`mode-badge mode-${item.mode}`}>{normalizeMode(item.mode)}</span>
      </div>
      <div className="listing-body">
        <div className="listing-head">
          <h3>{item.title}</h3>
          <div className="value-chip">{money(item.estimatedValue)}</div>
        </div>
        <p className="listing-meta">{item.brand} • {item.category} • {item.condition} • {item.city}</p>
        <p className="listing-notes">{item.wants}</p>
        <div className="tag-row">{(item.tags || []).slice(0, 4).map((tag) => <span key={tag}>{tag}</span>)}</div>
        <div className="listing-footer"><small>{own ? 'Your listing' : `Listed by ${item.owner}`}</small><button className="ghost small">{own ? 'Edit draft' : 'Open offer'}</button></div>
      </div>
    </article>
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
