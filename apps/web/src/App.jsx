import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import {
  SignIn,
  SignUp,
  UserButton,
  useAuth,
  useClerk,
  useUser,
} from '@clerk/clerk-react'
import { createWebApiClient } from './lib/apiClient'

const API_DEFAULT =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000')
const CLERK_ENABLED = Boolean(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY)
const IS_PROD = Boolean(import.meta.env.PROD)
const VALID_TABS = new Set(['market', 'portfolio', 'inbox', 'profile', 'market_new', 'admin', 'trade', 'upload'])

function tabFromLocation() {
  if (typeof window === 'undefined') return 'market'
  const params = new URLSearchParams(window.location.search)
  const tab = String(params.get('tab') || '').trim().toLowerCase()
  return VALID_TABS.has(tab) ? tab : 'market'
}

function tabHref(tab) {
  return `/?tab=${encodeURIComponent(tab)}`
}

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

function emptyShippingAddress() {
  return {
    id: makeId('ship'),
    label: '',
    full_name: '',
    address_line1: '',
    address_line2: '',
    city: '',
    state: '',
    postal_code: '',
    country: 'US',
    is_default: false,
  }
}

function normalizeShippingAddresses(addresses, fallback = null) {
  const normalized = Array.isArray(addresses)
    ? addresses
      .filter((a) => a && typeof a === 'object')
      .map((a) => ({
        id: typeof a.id === 'string' && a.id.trim() ? a.id : makeId('ship'),
        label: typeof a.label === 'string' ? a.label : '',
        full_name: typeof a.full_name === 'string' ? a.full_name : '',
        address_line1: typeof a.address_line1 === 'string' ? a.address_line1 : '',
        address_line2: typeof a.address_line2 === 'string' ? a.address_line2 : '',
        city: typeof a.city === 'string' ? a.city : '',
        state: typeof a.state === 'string' ? a.state : '',
        postal_code: typeof a.postal_code === 'string' ? a.postal_code : '',
        country: typeof a.country === 'string' && a.country.trim() ? a.country : 'US',
        is_default: Boolean(a.is_default),
      }))
    : []
  if (normalized.length > 0) return normalized
  if (fallback && typeof fallback === 'object') {
    const hasLegacy = ['shipping_full_name', 'shipping_address_line1', 'shipping_address_line2', 'shipping_city', 'shipping_state', 'shipping_postal_code', 'shipping_country']
      .some((key) => typeof fallback?.[key] === 'string' && fallback[key].trim())
    if (hasLegacy) {
      return [{
        ...emptyShippingAddress(),
        label: 'Primary',
        full_name: fallback.shipping_full_name || '',
        address_line1: fallback.shipping_address_line1 || '',
        address_line2: fallback.shipping_address_line2 || '',
        city: fallback.shipping_city || '',
        state: fallback.shipping_state || '',
        postal_code: fallback.shipping_postal_code || '',
        country: fallback.shipping_country || 'US',
        is_default: true,
      }]
    }
  }
  return [emptyShippingAddress()]
}

function normalizeMultiSizeValue(value) {
  if (Array.isArray(value)) {
    return value
      .map((entry) => (typeof entry === 'string' ? entry.trim() : ''))
      .filter(Boolean)
  }
  if (typeof value !== 'string') return []
  return value
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
}

function serializeMultiSizeValue(values) {
  const normalized = normalizeMultiSizeValue(values)
  if (normalized.length === 0) return null
  return normalized.join(', ')
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

function getListingGallery(item) {
  if (!item) return []
  if (Array.isArray(item.images) && item.images.length > 0) return item.images.filter(Boolean)
  return [item.image].filter(Boolean)
}

function getUploadedImageUrlsFromAnalysis(analysis) {
  if (!analysis || !Array.isArray(analysis.uploaded_images)) return []
  return analysis.uploaded_images
    .map((u) => (typeof u?.image_url === 'string' ? u.image_url.trim() : ''))
    .filter((u) => Boolean(u) && !u.startsWith('data:') && !u.startsWith('blob:'))
}

function buildListingShareCaption(item) {
  const title = String(item?.title || 'Listing').trim()
  const brand = String(item?.brand || 'Unknown brand').trim()
  const condition = String(item?.condition || 'Unknown condition').trim()
  const value = money(item?.estimatedValue)
  const description = getListingDescription(item)
  const imageLinks = getListingGallery(item).slice(0, 3)
  const imageLine = imageLinks.length > 0 ? ` Images: ${imageLinks.join(' ')}` : ''
  return `${title} | ${brand} | ${condition} | Est. ${value}. ${description}${imageLine} #Jouft #FashionExchange`
}

function sizeOptionsForCategory(category) {
  if (category === 'shoes') return ['US 5', 'US 5.5', 'US 6', 'US 6.5', 'US 7', 'US 7.5', 'US 8', 'US 8.5', 'US 9', 'US 9.5', 'US 10', 'US 10.5', 'US 11', 'US 12']
  if (category === 'clothes') return ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL']
  if (category === 'handbag') return ['Mini', 'Small', 'Medium', 'Large']
  return []
}

const FEMALE_APPAREL_SIZE_OPTIONS = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL']
const MALE_APPAREL_SIZE_OPTIONS = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
const FEMALE_SHOE_SIZE_OPTIONS = ['US 5', 'US 5.5', 'US 6', 'US 6.5', 'US 7', 'US 7.5', 'US 8', 'US 8.5', 'US 9', 'US 9.5', 'US 10', 'US 10.5', 'US 11', 'US 12']
const MALE_SHOE_SIZE_OPTIONS = ['US 6', 'US 6.5', 'US 7', 'US 7.5', 'US 8', 'US 8.5', 'US 9', 'US 9.5', 'US 10', 'US 10.5', 'US 11', 'US 11.5', 'US 12', 'US 13', 'US 14']
const PROFILE_CATEGORY_OPTIONS = ['Dresses', 'Jackets', 'Shoes', 'Handbags', 'Skirts', 'Accessories']
const SUBSCRIPTION_PLANS = [
  { id: 'free', name: 'Free Tier', monthlyPrice: 0, listingsPerMonth: 3, description: '3 listings per month' },
  { id: 'starter', name: 'Starter', monthlyPrice: 15, listingsPerMonth: 25, description: 'Up to 25 listings per month' },
  { id: 'pro', name: 'Pro', monthlyPrice: 25, listingsPerMonth: null, description: 'Unlimited listings' },
]
const CLERK_AUTH_APPEARANCE = {
  variables: {
    colorPrimary: '#0d1118',
    borderRadius: '0px',
    fontFamily: '"Plus Jakarta Sans", "Helvetica Neue", Arial, sans-serif',
  },
  elements: {
    rootBox: 'auth-clerk-root',
    card: 'auth-clerk-card',
    formButtonPrimary: 'auth-clerk-primary-btn',
  },
}

function normalizeSubscriptionPlanId(plan) {
  const raw = String(plan || '').trim().toLowerCase()
  if (!raw) return 'free'
  if (raw === 'starter') return 'starter'
  if (raw === 'pro') return 'pro'
  if (raw.includes('free')) return 'free'
  if (raw.includes('15') || raw.includes('starter')) return 'starter'
  if (raw.includes('25') || raw.includes('pro') || raw.includes('unlimited')) return 'pro'
  return 'free'
}

function normalizeBillingCycle(cycle) {
  return String(cycle || '').toLowerCase() === 'annual' ? 'annual' : 'monthly'
}

function brandSizeChartUrl(brand, category) {
  const name = String(brand || '').trim().toLowerCase()
  if (!name || name === 'unknown') return null
  const key = `${name}:${category || ''}`
  const byCategory = {
    'gucci:shoes': 'https://www.gucci.com/us/en/st/stories/article/women-shoes-size-guide',
    'gucci:clothes': 'https://www.gucci.com/us/en/st/stories/article/women-ready-to-wear-size-guide',
    'burberry:shoes': 'https://us.burberry.com/customer-service/size-guide/',
    'burberry:clothes': 'https://us.burberry.com/customer-service/size-guide/',
    'jimmy choo:shoes': 'https://us.jimmychoo.com/en/customer-services/size-guide/',
    'balenciaga:shoes': 'https://www.balenciaga.com/en-us/size-guide',
    'chanel:shoes': 'https://www.chanel.com/us/fashion/size-guide/',
    'coach:shoes': 'https://www.coach.com/customer-service-size-guide',
    'louis vuitton:shoes': 'https://us.louisvuitton.com/eng-us/faq/size-guide',
    'prada:shoes': 'https://www.prada.com/us/en/customer-service/size-guide.html',
  }
  if (byCategory[key]) return byCategory[key]
  const generic = {
    gucci: 'https://www.gucci.com/us/en/st/stories/article/size-guide',
    burberry: 'https://us.burberry.com/customer-service/size-guide/',
    'jimmy choo': 'https://us.jimmychoo.com/en/customer-services/size-guide/',
    balenciaga: 'https://www.balenciaga.com/en-us/size-guide',
    chanel: 'https://www.chanel.com/us/fashion/size-guide/',
    coach: 'https://www.coach.com/customer-service-size-guide',
    'louis vuitton': 'https://us.louisvuitton.com/eng-us/faq/size-guide',
    prada: 'https://www.prada.com/us/en/customer-service/size-guide.html',
  }
  return generic[name] || null
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '')
    reader.onerror = () => reject(reader.error || new Error('Failed reading file'))
    reader.readAsDataURL(file)
  })
}

let stripeJsPromise = null
function loadStripeJs() {
  if (typeof window === 'undefined') return Promise.reject(new Error('Browser context required'))
  if (window.Stripe) return Promise.resolve(window.Stripe)
  if (!stripeJsPromise) {
    stripeJsPromise = new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-stripe-js="true"]')
      if (existing) {
        existing.addEventListener('load', () => resolve(window.Stripe))
        existing.addEventListener('error', () => reject(new Error('Failed to load Stripe.js')))
        return
      }
      const script = document.createElement('script')
      script.src = 'https://js.stripe.com/v3/'
      script.async = true
      script.dataset.stripeJs = 'true'
      script.onload = () => resolve(window.Stripe)
      script.onerror = () => reject(new Error('Failed to load Stripe.js'))
      document.head.appendChild(script)
    })
  }
  return stripeJsPromise
}

async function analyzeItem({ apiBaseUrl, apiKey, bearerToken, images, category, userCondition, itemDescription, debug }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.analyzeItem(
    {
      images: (images || []).map((file) => ({ file })),
      category,
      userCondition,
      itemDescription,
      debug,
    },
    authContext(bearerToken),
  )
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
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  const payload = await client.listMyListings(limit, authContext(bearerToken))
  return payload?.items || []
}

async function fetchMarketplaceListings({ apiBaseUrl, apiKey, bearerToken, limit = 50 }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  const payload = await client.listMarketplace(limit, authContext(bearerToken))
  return payload?.items || []
}

async function fetchOfferCandidates({ apiBaseUrl, apiKey, bearerToken, targetListingId, limit = 100 }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  const payload = await client.listOfferCandidates(targetListingId, limit, authContext(bearerToken))
  return payload?.items || []
}

async function createListingRemote({ apiBaseUrl, apiKey, bearerToken, payload }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.createListing(payload, authContext(bearerToken))
}

async function updateListingRemote({ apiBaseUrl, apiKey, bearerToken, listingId, payload }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.updateListing(listingId, payload, authContext(bearerToken))
}

async function fetchProfileQuizRemote({ apiBaseUrl, apiKey, bearerToken }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.profileQuiz(authContext(bearerToken))
}

async function saveProfileQuizRemote({ apiBaseUrl, apiKey, bearerToken, payload }) {
  const normalizedPayload = {
    ...payload,
    gender: payload?.gender ? payload.gender : null,
  }
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.put('/v1/me/profile-quiz', normalizedPayload, authContext(bearerToken))
}

async function fetchUspsAddressSuggestionsRemote({ apiBaseUrl, apiKey, bearerToken, q, city, state, postalCode }) {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (city) params.set('city', city)
  if (state) params.set('state', state)
  if (postalCode) params.set('postal_code', postalCode)
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  const data = await client.get(`/v1/usps/address-suggest?${params.toString()}`, authContext(bearerToken))
  return Array.isArray(data?.suggestions) ? data.suggestions : []
}

async function fetchPaymentMethodsRemote({ apiBaseUrl, apiKey, bearerToken }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  const data = await client.paymentMethods(authContext(bearerToken))
  return Array.isArray(data?.items) ? data.items : []
}

async function createPaymentMethodRemote({ apiBaseUrl, apiKey, bearerToken, payload }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.post('/v1/me/payment-methods', payload, authContext(bearerToken))
}

async function deletePaymentMethodRemote({ apiBaseUrl, apiKey, bearerToken, paymentMethodId }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.delete(`/v1/me/payment-methods/${paymentMethodId}`, authContext(bearerToken))
}

async function setDefaultPaymentMethodRemote({ apiBaseUrl, apiKey, bearerToken, paymentMethodId }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.post(`/v1/me/payment-methods/${paymentMethodId}/default`, {}, authContext(bearerToken))
}

async function createStripeSetupCheckoutSessionRemote({ apiBaseUrl, apiKey, bearerToken, successUrl, cancelUrl }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.createSetupCheckoutSession(
    { successUrl, cancelUrl },
    authContext(bearerToken),
  )
}

async function syncStripePaymentMethodsRemote({ apiBaseUrl, apiKey, bearerToken }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  const data = await client.syncStripePaymentMethods(authContext(bearerToken))
  return Array.isArray(data?.items) ? data.items : []
}

async function createStripeSetupIntentRemote({ apiBaseUrl, apiKey, bearerToken }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.post('/v1/me/payment-methods/stripe/setup-intent', {}, authContext(bearerToken))
}

async function createOfferRemote({ apiBaseUrl, apiKey, bearerToken, payload }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.createOffer(payload, authContext(bearerToken))
}

async function fetchIncomingOffersRemote({ apiBaseUrl, apiKey, bearerToken, status = 'pending', limit = 50 }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.incomingOffers(status, limit, authContext(bearerToken))
}

async function actionOfferRemote({ apiBaseUrl, apiKey, bearerToken, offerId, status, receiveAddress = null }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.offerAction(offerId, status, receiveAddress, authContext(bearerToken))
}

async function fetchShippingQuoteRemote({ apiBaseUrl, apiKey, bearerToken, offerId }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.post(`/v1/offers/${offerId}/shipping-quote`, {}, authContext(bearerToken))
}

async function createShippingLabelsRemote({ apiBaseUrl, apiKey, bearerToken, offerId, rateId = null }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.post(
    `/v1/offers/${offerId}/shipping-labels`,
    { confirmed: true, rate_id: rateId || null },
    authContext(bearerToken),
  )
}

async function fetchShippingLabelsRemote({ apiBaseUrl, apiKey, bearerToken, offerId }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.get(`/v1/offers/${offerId}/shipping-labels`, authContext(bearerToken))
}

async function fetchShippingLabelDocumentRemote({ apiBaseUrl, apiKey, bearerToken, shipmentId }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.get(`/v1/shipments/${shipmentId}/label`, authContext(bearerToken))
}

export default function App() {
  if (CLERK_ENABLED) return <ClerkMarketplaceApp />
  return <LocalMarketplaceApp />
}

function ClerkMarketplaceApp() {
  const { isLoaded, isSignedIn, getToken } = useAuth()
  const { signOut } = useClerk()
  const { user } = useUser()
  const [authMode, setAuthMode] = useState('login')
  const [authPanelOpen, setAuthPanelOpen] = useState(false)

  if (!isLoaded) return <LoadingShell message="Loading authentication..." />

  if (!isSignedIn || !user) {
    return (
      <AuthShell
        actions={(
        <div className="auth-cta-actions auth-cta-actions-fixed">
          <button className="ghost" type="button" onClick={() => { setAuthMode('login'); setAuthPanelOpen(true) }}>Log In</button>
          <button className="primary" type="button" onClick={() => { setAuthMode('signup'); setAuthPanelOpen(true) }}>Request Access</button>
        </div>
        )}
      >
        {authPanelOpen && (
          <div className="auth-modal-shell" onClick={() => setAuthPanelOpen(false)}>
            <section className="auth-panel auth-panel-modal auth-panel-clerk" onClick={(e) => e.stopPropagation()}>
              <div className="auth-panel-head auth-panel-head-clerk">
                <p className="eyebrow">{authMode === 'login' ? 'Sign In' : 'Create Account'}</p>
                <button className="ghost small" type="button" onClick={() => setAuthPanelOpen(false)}>Close</button>
              </div>
              <div className="auth-clerk-wrap">
                {authMode === 'login' ? (
                  <SignIn routing="virtual" signUpUrl="#" appearance={CLERK_AUTH_APPEARANCE} />
                ) : (
                  <SignUp routing="virtual" signInUrl="#" appearance={CLERK_AUTH_APPEARANCE} />
                )}
              </div>
            </section>
          </div>
        )}
      </AuthShell>
    )
  }

  const session = {
    id: user.id,
    name: [user.firstName, user.lastName].filter(Boolean).join(' ') || user.username || user.primaryEmailAddress?.emailAddress || 'User',
    email: user.primaryEmailAddress?.emailAddress || '',
  }
  const profileData = {
    userId: user.id || '',
    name: [user.firstName, user.lastName].filter(Boolean).join(' ') || '',
    firstName: user.firstName || '',
    lastName: user.lastName || '',
    username: user.username || '',
    email: user.primaryEmailAddress?.emailAddress || '',
    phone: user.primaryPhoneNumber?.phoneNumber || '',
    createdAt: user.createdAt ? new Date(user.createdAt).toLocaleString() : '',
  }

  return (
    <MarketplaceWorkspace
      session={session}
      profileData={profileData}
      onLogout={() => signOut({ redirectUrl: '/' })}
      clerkEnabled
      getBearerToken={() => getToken()}
      userMenu={(
        <UserButton afterSignOutUrl="/">
          <UserButton.MenuItems>
            <UserButton.Action label="Profile" />
          </UserButton.MenuItems>
        </UserButton>
      )}
    />
  )
}

function LocalMarketplaceApp() {
  const [authMode, setAuthMode] = useState('login')
  const [authPanelOpen, setAuthPanelOpen] = useState(false)
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
      <AuthShell
        actions={(
        <div className="auth-cta-actions auth-cta-actions-fixed">
          <button className="ghost" type="button" onClick={() => { setAuthMode('login'); setAuthPanelOpen(true) }}>Log In</button>
          <button className="primary" type="button" onClick={() => { setAuthMode('signup'); setAuthPanelOpen(true) }}>Request Access</button>
        </div>
        )}
      >
        {authPanelOpen && (
          <div className="auth-modal-shell" onClick={() => setAuthPanelOpen(false)}>
            <section className="auth-panel auth-panel-modal" onClick={(e) => e.stopPropagation()}>
              <div className="auth-panel-head">
                <p className="eyebrow">{authMode === 'login' ? 'Sign In' : 'Create Account'}</p>
                <button className="ghost small" type="button" onClick={() => setAuthPanelOpen(false)}>Close</button>
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
          </div>
        )}
      </AuthShell>
    )
  }

  return <MarketplaceWorkspace session={session} onLogout={() => setSession(null)} />
}

function AuthShell({ children, actions = null }) {
  const authImages = {
    hero: 'https://images.unsplash.com/photo-1617038220319-276d3cfab638?auto=format&fit=crop&w=1800&q=80',
    bags: 'https://images.unsplash.com/photo-1594223274512-ad4803739b7c?auto=format&fit=crop&w=900&q=80',
    apparel: 'https://images.unsplash.com/photo-1487222477894-8943e31ef7b2?auto=format&fit=crop&w=900&q=80',
    shoes: 'https://images.unsplash.com/photo-1543163521-1bf539c55dd2?auto=format&fit=crop&w=900&q=80',
    accessories: 'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=900&q=80',
    jewelry: 'https://images.unsplash.com/photo-1617038220319-276d3cfab638?auto=format&fit=crop&w=900&q=80',
    designer: 'https://images.unsplash.com/photo-1511499767150-a48a237f0083?auto=format&fit=crop&w=900&q=80',
  }
  return (
    <div className="shell auth-shell">
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />
      <section className="auth-hero">
        <div className="auth-announce-bar">INVITE ONLY COMMUNITY • CURATED MEMBERSHIP ACCESS</div>
        <div className="auth-hero-topbar">
          <div className="auth-brandmark" aria-label="Jouft brand">
            <div className="auth-brand-lockup">
              <strong>JOUFT</strong>
            </div>
          </div>
          <div className="auth-marquee" aria-label="Site sections">
            <span>TRADING</span>
            <span>CLOSET</span>
            <span>DISCOVER</span>
            <span>HOW IT WORKS</span>
            <span>JOURNAL</span>
          </div>
          {actions}
        </div>
        <div className="auth-hero-feature">
          <div className="auth-hero-copy">
            <p className="auth-kicker">TRADE. ELEVATE. BELONG.</p>
            <h1 className="auth-hero-title">
              <span>The Fashion Trading Platform</span>
              <span>for Collectors</span>
            </h1>
            <p className="lede">
              Trade authentic, pre-loved and new fashion with our curated community. No listing fees. No marketplace clutter. Just the right match.
            </p>
            <div className="auth-hero-actions">
              <button className="primary" type="button">Request Access</button>
              <button className="ghost arrow" type="button">How It Works</button>
            </div>
            <p className="auth-social-proof">Join 2,800+ members shaping the future of fashion.</p>
          </div>
          <div className="auth-hero-image-wall">
            <div className="auth-hero-main-image">
              <img src={authImages.hero} alt="Jouft curated hero editorial" />
            </div>
            <div className="auth-members-card">
              <p className="auth-members-kicker">CURATED COMMUNITY</p>
              <h3>Members Only</h3>
              <p>Exclusivity. Trust. Quality.</p>
              <span>+2.8K</span>
            </div>
          </div>
        </div>
        <div className="auth-hero-meta auth-value-strip">
          <span><strong>EXCLUSIVE ACCESS</strong>Invitation-only community of verified fashion lovers.</span>
          <span><strong>CURATED QUALITY</strong>Every item is authenticated and quality-checked.</span>
          <span><strong>SMART MATCHING</strong>We match you by style, value, and preferences.</span>
          <span><strong>SUSTAINABLE IMPACT</strong>Extend item life, reduce waste, elevate style.</span>
        </div>
        <section className="auth-closet-section">
          <div className="auth-section-head">
            <h2>BROWSE THE CLOSET</h2>
            <button className="ghost arrow" type="button">View All Categories</button>
          </div>
          <div className="auth-closet-grid">
            <article className="auth-closet-card">
              <img src={authImages.bags} alt="Bags" />
              <div><h3>BAGS</h3><p>312 items</p></div>
            </article>
            <article className="auth-closet-card">
              <img src={authImages.apparel} alt="Apparel" />
              <div><h3>APPAREL</h3><p>892 items</p></div>
            </article>
            <article className="auth-closet-card">
              <img src={authImages.shoes} alt="Shoes" />
              <div><h3>SHOES</h3><p>532 items</p></div>
            </article>
            <article className="auth-closet-card">
              <img src={authImages.accessories} alt="Accessories" />
              <div><h3>ACCESSORIES</h3><p>241 items</p></div>
            </article>
            <article className="auth-closet-card">
              <img src={authImages.jewelry} alt="Jewelry" />
              <div><h3>JEWELRY</h3><p>189 items</p></div>
            </article>
            <article className="auth-closet-card">
              <img src={authImages.designer} alt="Designer collections" />
              <div><h3>DESIGNER COLLECTIONS</h3><p>126 items</p></div>
            </article>
          </div>
          <div className="auth-new-banner">
            <span>NEW TO JOUFT</span>
            <p>Not sure how it works? Watch our short walkthrough video.</p>
            <button className="ghost arrow" type="button">Watch Now</button>
          </div>
        </section>
        <section className="auth-how-section">
          <div className="auth-section-head">
            <h2>HOW JOUFT WORKS</h2>
            <button className="ghost arrow" type="button">Learn More</button>
          </div>
          <div className="hero-cards">
            <div className="hero-card">
              <div className="hero-card-content"><span>01</span><h3>Share Your Items</h3><p>Add pieces from your closet. We evaluate them for you.</p></div>
            </div>
            <div className="hero-card">
              <div className="hero-card-content"><span>02</span><h3>Get Matched</h3><p>Our algorithm finds the best matches based on style and value.</p></div>
            </div>
            <div className="hero-card">
              <div className="hero-card-content"><span>03</span><h3>Trade Securely</h3><p>Approve the trade and we handle authentication and shipping.</p></div>
            </div>
            <div className="hero-card">
              <div className="hero-card-content"><span>04</span><h3>Elevate Together</h3><p>Enjoy new pieces, build your style, and join the community.</p></div>
            </div>
          </div>
        </section>
        <footer className="auth-site-footer">
          <strong>JOUFT</strong>
          <div className="auth-footer-links">
            <span>ABOUT</span><span>JOURNAL</span><span>FAQ</span><span>TERMS</span><span>PRIVACY</span>
          </div>
          <small>© 2026 JOUFT. ALL RIGHTS RESERVED.</small>
        </footer>
      </section>
      {children}
    </div>
  )
}

function LoadingShell({ message }) {
  return (
    <div className="shell auth-shell">
      <section className="auth-hero"><h1>Jouft</h1><p className="lede">{message}</p></section>
      <section className="auth-panel"><p className="tiny-note">Please wait...</p></section>
    </div>
  )
}

function MarketplaceWorkspace({ session, profileData = null, onLogout, clerkEnabled = false, getBearerToken, userMenu = null, onOpenProfile = null }) {
  const [apiBaseUrl] = useState(API_DEFAULT)
  const [apiKey, setApiKey] = useState('local-dev-key')
  const [myListings, setMyListings] = useState([])
  const [marketListings, setMarketListings] = useState([])
  const [activeTab, setActiveTab] = useState(() => tabFromLocation())
  const [marketSearch, setMarketSearch] = useState('')
  const [tradeOnly, setTradeOnly] = useState(false)
  const [listingMode, setListingMode] = useState('sell_trade')
  const [itemTitle, setItemTitle] = useState('')
  const [category, setCategory] = useState('')
  const [userCondition, setUserCondition] = useState('')
  const [itemDescription, setItemDescription] = useState('')
  const [itemSize, setItemSize] = useState('')
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
  const [profileQuiz, setProfileQuiz] = useState({
    gender: '', tops_size: [], dresses_size: [], bottoms_size: [], shoes_size: [], category_preferences: [],
    shipping_full_name: '', shipping_address_line1: '', shipping_address_line2: '', shipping_city: '', shipping_state: '', shipping_postal_code: '', shipping_country: '',
    shipping_addresses: [emptyShippingAddress()],
    subscription_plan: 'free', subscription_billing_cycle: 'monthly', subscription_status: '', subscription_renewal_date: '', payment_methods: [],
  })
  const [activeShippingAddressIdx, setActiveShippingAddressIdx] = useState(0)
  const [addressSuggestions, setAddressSuggestions] = useState([])
  const [profileSaveMsg, setProfileSaveMsg] = useState('')
  const [paymentMethods, setPaymentMethods] = useState([])
  const [paymentBusy, setPaymentBusy] = useState(false)
  const [paymentSyncBusy, setPaymentSyncBusy] = useState(false)
  const [paymentLoadError, setPaymentLoadError] = useState('')
  const [paymentActionMsg, setPaymentActionMsg] = useState('')
  const [paymentDeleteBusyId, setPaymentDeleteBusyId] = useState('')
  const [showStripePaymentModal, setShowStripePaymentModal] = useState(false)
  const [stripeUiBusy, setStripeUiBusy] = useState(false)
  const [stripeUiError, setStripeUiError] = useState('')
  const [stripeUiReady, setStripeUiReady] = useState(false)
  const [subscriptionStripeAutoSynced, setSubscriptionStripeAutoSynced] = useState(false)
  const stripeRef = useRef(null)
  const stripeElementsRef = useRef(null)
  const stripePaymentElementRef = useRef(null)
  const [incomingOffers, setIncomingOffers] = useState([])
  const [offersActorSubject, setOffersActorSubject] = useState('')
  const [tradeComposerTarget, setTradeComposerTarget] = useState(null)
  const [marketMatchesTargetId, setMarketMatchesTargetId] = useState(null)
  const [tradeOfferCandidates, setTradeOfferCandidates] = useState([])
  const [tradeOfferListingIds, setTradeOfferListingIds] = useState([])
  const [tradeOfferMessage, setTradeOfferMessage] = useState('')
  const [tradeOfferError, setTradeOfferError] = useState('')
  const [tradeOfferBusy, setTradeOfferBusy] = useState(false)
  const [tradeDetailListing, setTradeDetailListing] = useState(null)
  const [offerStatusFilter, setOfferStatusFilter] = useState('all')
  const [closetFilter, setClosetFilter] = useState('all')
  const [profileSection, setProfileSection] = useState('general')
  const [shippingLabelsByOffer, setShippingLabelsByOffer] = useState({})
  const [offerReceiveAddressById, setOfferReceiveAddressById] = useState({})
  const [shippingQuoteByOffer, setShippingQuoteByOffer] = useState({})
  const [marketMagazineIndex, setMarketMagazineIndex] = useState(null)
  const [newMarketIndex, setNewMarketIndex] = useState(0)
  const [newMarketFlipDir, setNewMarketFlipDir] = useState('next')
  const [newMarketIsFlipping, setNewMarketIsFlipping] = useState(false)
  const forcedLogoutRef = useRef(false)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof onLogout !== 'function') return undefined
    function handleUnauthorized() {
      if (forcedLogoutRef.current) return
      forcedLogoutRef.current = true
      setSavedListingNotice('Your session expired. Please sign in again.')
      Promise.resolve(onLogout()).catch(() => {})
    }
    window.addEventListener('valueai:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('valueai:unauthorized', handleUnauthorized)
  }, [onLogout])

  function resolveOfferActorSubject(offer) {
    const participants = [String(offer?.from_subject || ''), String(offer?.to_subject || '')]
      .map((value) => value.trim())
      .filter(Boolean)
    const candidates = [String(session?.id || ''), String(offersActorSubject || '')]
      .map((value) => value.trim())
      .filter(Boolean)
      .filter((value) => value.toLowerCase() !== 'api-key')
    for (const candidate of candidates) {
      if (participants.includes(candidate)) return candidate
    }
    return candidates[0] || participants[0] || ''
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const data = await fetchProfileQuizRemote({ apiBaseUrl, apiKey: clerkEnabled ? '' : apiKey.trim(), bearerToken })
        if (!cancelled) {
          const shippingAddresses = normalizeShippingAddresses(data?.shipping_addresses, data)
          setProfileQuiz({
            gender: data?.gender || '',
            tops_size: normalizeMultiSizeValue(data?.tops_size),
            dresses_size: normalizeMultiSizeValue(data?.dresses_size),
            bottoms_size: normalizeMultiSizeValue(data?.bottoms_size),
            shoes_size: normalizeMultiSizeValue(data?.shoes_size),
            category_preferences: Array.isArray(data?.category_preferences) ? data.category_preferences : [],
            shipping_full_name: shippingAddresses[0]?.full_name || '',
            shipping_address_line1: shippingAddresses[0]?.address_line1 || '',
            shipping_address_line2: shippingAddresses[0]?.address_line2 || '',
            shipping_city: shippingAddresses[0]?.city || '',
            shipping_state: shippingAddresses[0]?.state || '',
            shipping_postal_code: shippingAddresses[0]?.postal_code || '',
            shipping_country: shippingAddresses[0]?.country || '',
            shipping_addresses: shippingAddresses,
            subscription_plan: normalizeSubscriptionPlanId(data?.subscription_plan),
            subscription_billing_cycle: normalizeBillingCycle(data?.subscription_billing_cycle),
            subscription_status: data?.subscription_status || '',
            subscription_renewal_date: data?.subscription_renewal_date || '',
            payment_methods: Array.isArray(data?.payment_methods) ? data.payment_methods : [],
          })
          setActiveShippingAddressIdx(0)
        }
      } catch {}
    })()
    return () => { cancelled = true }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (profileSection !== 'subscription') return
      if (subscriptionStripeAutoSynced) return
      if (paymentSyncBusy) return
      setPaymentSyncBusy(true)
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const methods = await syncStripePaymentMethodsRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
        })
        if (!cancelled) {
          setPaymentMethods(methods)
          setPaymentLoadError('')
          setSubscriptionStripeAutoSynced(true)
        }
      } catch (err) {
        if (!cancelled) {
          setPaymentLoadError(err?.message || 'Failed to sync payment methods.')
          setProfileSaveMsg(err.message || 'Failed to sync payment methods.')
        }
      } finally {
        if (!cancelled) setPaymentSyncBusy(false)
      }
    })()
    return () => { cancelled = true }
  }, [profileSection, subscriptionStripeAutoSynced, paymentSyncBusy, apiBaseUrl, apiKey, clerkEnabled, getBearerToken])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!showStripePaymentModal) return
      setStripeUiError('')
      setStripeUiBusy(true)
      setStripeUiReady(false)
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const setup = await createStripeSetupIntentRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
        })
        if (!setup?.client_secret || !setup?.publishable_key) {
          throw new Error(setup?.message || 'Stripe setup is not configured.')
        }
        const StripeCtor = await loadStripeJs()
        const stripe = StripeCtor(setup.publishable_key)
        const elements = stripe.elements({ clientSecret: setup.client_secret, appearance: { theme: 'stripe' } })
        const payment = elements.create('payment')
        const mountEl = document.getElementById('stripe-payment-element')
        if (!mountEl) throw new Error('Payment UI container unavailable.')
        payment.mount(mountEl)
        if (cancelled) return
        stripeRef.current = stripe
        stripeElementsRef.current = elements
        stripePaymentElementRef.current = payment
        setStripeUiReady(true)
      } catch (err) {
        if (!cancelled) setStripeUiError(err.message || 'Failed to initialize Stripe payment UI.')
      } finally {
        if (!cancelled) setStripeUiBusy(false)
      }
    })()
    return () => {
      cancelled = true
      try { stripePaymentElementRef.current?.unmount?.() } catch {}
      stripePaymentElementRef.current = null
      stripeElementsRef.current = null
      stripeRef.current = null
      setStripeUiReady(false)
    }
  }, [showStripePaymentModal, apiBaseUrl, apiKey, clerkEnabled, getBearerToken])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (typeof window === 'undefined') return
      const params = new URLSearchParams(window.location.search)
      const setup = params.get('stripe_setup')
      if (setup !== 'success') return
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const methods = await syncStripePaymentMethodsRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
        })
        if (!cancelled) setPaymentMethods(methods)
        if (!cancelled) setProfileSaveMsg('Stripe payment method added.')
      } catch (err) {
        if (!cancelled) setProfileSaveMsg(err.message || 'Stripe sync failed.')
      } finally {
        params.delete('stripe_setup')
        const next = params.toString()
        window.history.replaceState({}, '', `${window.location.pathname}${next ? `?${next}` : ''}`)
      }
    })()
    return () => { cancelled = true }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const methods = await fetchPaymentMethodsRemote({ apiBaseUrl, apiKey: clerkEnabled ? '' : apiKey.trim(), bearerToken })
        if (!cancelled) {
          setPaymentMethods(methods)
          setPaymentLoadError('')
        }
      } catch (err) {
        if (!cancelled) {
          setPaymentLoadError(err?.message || 'Failed to load payment methods.')
        }
      }
    })()
    return () => { cancelled = true }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken])

  useEffect(() => {
    let cancelled = false
    let timer = null
    async function refreshOffers() {
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const payload = await fetchIncomingOffersRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          status: offerStatusFilter,
          limit: 50,
        })
        if (!cancelled) {
          const items = Array.isArray(payload?.items) ? payload.items : []
          setIncomingOffers(items)
          setOffersActorSubject(typeof payload?.actor?.subject === 'string' ? payload.actor.subject : '')
          setOfferReceiveAddressById((prev) => {
            const next = { ...prev }
            items.forEach((offer) => {
              if (!next[offer.offer_id]) {
                next[offer.offer_id] = (shippingAddresses[0]?.id || '')
              }
            })
            return next
          })
        }
      } catch {
        if (!cancelled) {
          setIncomingOffers([])
          setOffersActorSubject('')
        }
      } finally {
        if (!cancelled) timer = setTimeout(refreshOffers, 15000)
      }
    }
    refreshOffers()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken, offerStatusFilter, profileQuiz.shipping_addresses])
  const normalizedProfileGender = profileQuiz.gender === 'male' || profileQuiz.gender === 'female' || profileQuiz.gender === 'other'
    ? profileQuiz.gender
    : ''
  const profileApparelSizeOptions = normalizedProfileGender === 'male' ? MALE_APPAREL_SIZE_OPTIONS : FEMALE_APPAREL_SIZE_OPTIONS
  const profileShoeSizeOptions = normalizedProfileGender === 'male' ? MALE_SHOE_SIZE_OPTIONS : FEMALE_SHOE_SIZE_OPTIONS
  const profileCategoryOptions = normalizedProfileGender === 'male'
    ? PROFILE_CATEGORY_OPTIONS.filter((c) => c !== 'Dresses')
    : PROFILE_CATEGORY_OPTIONS
  const selectedSubscriptionPlanId = normalizeSubscriptionPlanId(profileQuiz.subscription_plan)
  const selectedBillingCycle = normalizeBillingCycle(profileQuiz.subscription_billing_cycle)
  const shippingAddresses = normalizeShippingAddresses(profileQuiz.shipping_addresses, profileQuiz)
  const safeActiveShippingAddressIdx = Math.max(0, Math.min(activeShippingAddressIdx, shippingAddresses.length - 1))
  const activeShippingAddress = shippingAddresses[safeActiveShippingAddressIdx] || shippingAddresses[0] || emptyShippingAddress()

  function updateActiveShippingAddress(patch) {
    setProfileQuiz((prev) => {
      const nextAddresses = normalizeShippingAddresses(prev.shipping_addresses, prev)
      const idx = Math.max(0, Math.min(activeShippingAddressIdx, nextAddresses.length - 1))
      nextAddresses[idx] = { ...nextAddresses[idx], ...patch }
      return { ...prev, shipping_addresses: nextAddresses }
    })
  }

  function addShippingAddress() {
    const newAddress = { ...emptyShippingAddress(), label: `Address ${shippingAddresses.length + 1}` }
    const updated = [...shippingAddresses, newAddress]
    setProfileQuiz((prev) => ({ ...prev, shipping_addresses: updated }))
    setActiveShippingAddressIdx(updated.length - 1)
    setAddressSuggestions([])
  }

  function removeActiveShippingAddress() {
    if (shippingAddresses.length <= 1) {
      setProfileQuiz((prev) => ({ ...prev, shipping_addresses: [emptyShippingAddress()] }))
      setActiveShippingAddressIdx(0)
      setAddressSuggestions([])
      return
    }
    const idx = safeActiveShippingAddressIdx
    const updated = shippingAddresses.filter((_, i) => i !== idx)
    setProfileQuiz((prev) => ({ ...prev, shipping_addresses: updated }))
    setActiveShippingAddressIdx(Math.max(0, idx - 1))
    setAddressSuggestions([])
  }

  useEffect(() => {
    let cancelled = false
    const line1 = (activeShippingAddress?.address_line1 || '').trim()
    const state = (activeShippingAddress?.state || '').trim()
    if (line1.length < 5 || state.length !== 2) {
      setAddressSuggestions([])
      return undefined
    }
    const timer = setTimeout(async () => {
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const suggestions = await fetchUspsAddressSuggestionsRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          q: line1,
          city: activeShippingAddress?.city || '',
          state,
          postalCode: activeShippingAddress?.postal_code || '',
        })
        if (!cancelled) setAddressSuggestions(suggestions.slice(0, 5))
      } catch {
        if (!cancelled) setAddressSuggestions([])
      }
    }, 350)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [
    activeShippingAddress?.address_line1,
    activeShippingAddress?.city,
    activeShippingAddress?.state,
    activeShippingAddress?.postal_code,
    safeActiveShippingAddressIdx,
    apiBaseUrl,
    apiKey,
    clerkEnabled,
    getBearerToken,
  ])

  function fromRemoteListing(item) {
    if (!item) return null
    const ownerNameRaw = typeof item.owner_name === 'string' ? item.owner_name.trim() : ''
    const ownerSubjectRaw = typeof item.owner_subject === 'string' ? item.owner_subject.trim() : ''
    const isCurrentUserListing = ownerSubjectRaw && String(session?.id || '').trim() === ownerSubjectRaw
    const ownerNameLooksLikeSubject = ownerNameRaw && (
      ownerNameRaw === ownerSubjectRaw
      || /^user_[a-z0-9]+$/i.test(ownerNameRaw)
    )
    const displayOwnerName = !ownerNameRaw || ownerNameLooksLikeSubject
      ? (isCurrentUserListing ? (session.name || 'You') : 'Member')
      : ownerNameRaw
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
    const normalized = {
      id: item.listing_id || item.id,
      owner: displayOwnerName,
      title: item.title || 'Untitled listing',
      mode: item.mode || 'sell_trade',
      category: item.category || 'unknown',
      brand: item.brand || 'unknown',
      condition: item.condition || 'n/a',
      size: typeof item.size === 'string' ? item.size : '',
      estimatedValue: Number(item.estimated_value ?? item.estimatedValue ?? 0),
      city: item.city || 'Your area',
      image: normalizedImages[0] || null,
      images: normalizedImages,
      description: typeof item.description === 'string' ? item.description : '',
      wants: item.wants || 'Open to similar-value offers',
      tags: Array.isArray(item.tags) ? item.tags : [],
      sourceItemId: item.source_item_id || item.sourceItemId || null,
      analysis: item.analysis || null,
      status: item.status || 'Review',
      createdAt: item.created_at || item.createdAt || null,
    }
    if (Array.isArray(item.matches)) {
      normalized.matches = item.matches.map((m) => fromRemoteListing(m)).filter(Boolean)
    }
    return normalized
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
      size: listing.size || null,
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
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const items = await fetchMarketplaceListings({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          limit: 50,
        })
        if (!cancelled) setMarketListings(items.map(fromRemoteListing).filter(Boolean))
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

  const allListings = marketListings.length > 0 ? marketListings : [...myListings, ...seedListings]
  const deferredMarketSearch = useDeferredValue(marketSearch)

  const filteredListings = useMemo(() => {
    const q = deferredMarketSearch.trim().toLowerCase()
    return allListings.filter((item) => {
      const status = typeof item.status === 'string' ? item.status.toLowerCase() : ''
      if (status !== 'active') return false
      if (tradeOnly && item.mode === 'sell') return false
      if (!q) return true
      return `${item.title} ${item.brand} ${item.category} ${item.city} ${item.wants}`.toLowerCase().includes(q)
    })
  }, [allListings, deferredMarketSearch, tradeOnly])
  const marketplaceNavCount = useMemo(
    () => allListings.filter((item) => String(item?.status || '').toLowerCase() === 'active').length,
    [allListings],
  )
  const marketMatchesTarget = useMemo(
    () => allListings.find((x) => x.id === marketMatchesTargetId) || null,
    [allListings, marketMatchesTargetId]
  )
  const similarListingsForTarget = useMemo(() => {
    if (!marketMatchesTarget) return []
    return Array.isArray(marketMatchesTarget.matches) ? marketMatchesTarget.matches : []
  }, [marketMatchesTarget])
  useEffect(() => {
    if (!marketMatchesTarget) return
    function onKeyDown(e) {
      if (e.key === 'Escape') setMarketMatchesTargetId(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [marketMatchesTarget])

  const latestActiveListings = useMemo(
    () => allListings.filter((item) => String(item?.status || '').toLowerCase() === 'active').slice(0, 6),
    [allListings],
  )
  const showFreshListingsStrip = false

  useEffect(() => {
    if (filteredListings.length === 0) {
      setMarketMagazineIndex(null)
      return
    }
    if (marketMagazineIndex == null) return
    setMarketMagazineIndex((prev) => {
      if (prev == null) return null
      return Math.max(0, Math.min(prev, filteredListings.length - 1))
    })
  }, [filteredListings, marketMagazineIndex])

  useEffect(() => {
    if (filteredListings.length === 0) {
      setNewMarketIndex(0)
      return
    }
    setNewMarketIndex((prev) => Math.min(prev, filteredListings.length - 1))
  }, [filteredListings])

  function flipToNewMarketplaceIndex(nextIndex, direction) {
    if (filteredListings.length === 0) return
    setNewMarketFlipDir(direction)
    setNewMarketIsFlipping(true)
    setTimeout(() => {
      setNewMarketIndex(nextIndex)
      setNewMarketIsFlipping(false)
    }, 180)
  }

  function flipNewMarketplaceNext() {
    if (filteredListings.length <= 1) return
    const next = (newMarketIndex + 1) % filteredListings.length
    flipToNewMarketplaceIndex(next, 'next')
  }

  function flipNewMarketplacePrev() {
    if (filteredListings.length <= 1) return
    const prev = (newMarketIndex - 1 + filteredListings.length) % filteredListings.length
    flipToNewMarketplaceIndex(prev, 'prev')
  }

  function openMarketplaceMagazine(item) {
    const idx = filteredListings.findIndex((entry) => entry?.id === item?.id)
    if (idx >= 0) setMarketMagazineIndex(idx)
  }

  function flipMarketplaceMagazineNext() {
    if (filteredListings.length <= 1 || marketMagazineIndex == null) return
    setMarketMagazineIndex((marketMagazineIndex + 1) % filteredListings.length)
  }

  function flipMarketplaceMagazinePrev() {
    if (filteredListings.length <= 1 || marketMagazineIndex == null) return
    setMarketMagazineIndex((marketMagazineIndex - 1 + filteredListings.length) % filteredListings.length)
  }

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

  const closetBreakdown = useMemo(() => {
    let active = 0
    let draft = 0
    let traded = 0
    for (const item of myListings) {
      const status = String(item?.status || '').toLowerCase()
      if (status === 'active') active += 1
      else if (status === 'traded') traded += 1
      else draft += 1
    }
    return {
      active,
      draft,
      traded,
      offers: incomingOffers.filter((o) => String(o?.status || '').toLowerCase() === 'pending').length,
    }
  }, [myListings, incomingOffers])

  const filteredClosetListings = useMemo(() => {
    if (closetFilter === 'all') return myListings
    if (closetFilter === 'offers') {
      const targetIds = new Set(
        incomingOffers
          .filter((o) => String(o?.status || '').toLowerCase() === 'pending')
          .map((o) => o?.target_listing?.listing_id)
          .filter(Boolean)
      )
      return myListings.filter((x) => targetIds.has(x.id))
    }
    if (closetFilter === 'active') return myListings.filter((x) => String(x?.status || '').toLowerCase() === 'active')
    if (closetFilter === 'traded') return myListings.filter((x) => String(x?.status || '').toLowerCase() === 'traded')
    if (closetFilter === 'draft') {
      return myListings.filter((x) => {
        const s = String(x?.status || '').toLowerCase()
        return s !== 'active' && s !== 'traded'
      })
    }
    return myListings
  }, [myListings, incomingOffers, closetFilter])

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

  async function openTradeComposer(targetListing, preferredOfferedListingId = null) {
    if (!targetListing?.id) return
    setTradeComposerTarget(targetListing)
    setTradeOfferMessage('')
    setTradeOfferError('')
    setMarketMatchesTargetId(null)
    setActiveTab('trade')

    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      const items = await fetchOfferCandidates({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        targetListingId: targetListing.id,
        limit: 100,
      })
      const normalized = items.map(fromRemoteListing).filter(Boolean)
      setTradeOfferCandidates(normalized)
      const preferred = preferredOfferedListingId
        ? normalized.find((x) => x.id === preferredOfferedListingId)
        : null
      setTradeOfferListingIds(preferred?.id ? [preferred.id] : (normalized[0]?.id ? [normalized[0].id] : []))
    } catch (err) {
      setTradeOfferError(err.message || 'Failed to load offer candidates.')
      setTradeOfferCandidates([])
      setTradeOfferListingIds([])
    }
  }

  async function submitTradeOffer() {
    if (!tradeComposerTarget?.id) return
    if (!tradeOfferListingIds.length) {
      setTradeOfferError('Select one or more of your listings to offer for trade.')
      return
    }
    setTradeOfferBusy(true)
    setTradeOfferError('')
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      await createOfferRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        payload: {
          target_listing_id: tradeComposerTarget.id,
          offered_listing_ids: tradeOfferListingIds,
          message: tradeOfferMessage.trim(),
        },
      })
      setTradeComposerTarget(null)
      setTradeOfferCandidates([])
      setTradeOfferListingIds([])
      setTradeOfferMessage('')
      setSavedListingNotice('Trade offer sent. The listing owner has been notified.')
      setActiveTab('market')
    } catch (err) {
      setTradeOfferError(err.message || 'Failed to send trade offer.')
    } finally {
      setTradeOfferBusy(false)
    }
  }

  function openMarketMatches(targetListing) {
    setMarketMatchesTargetId(targetListing?.id || null)
    setActiveTab('market')
  }

  async function respondToOffer(offerId, status, receiveAddress = null) {
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      const updatedOffer = await actionOfferRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        offerId,
        status,
        receiveAddress,
      })
      setIncomingOffers((prev) => prev.map((o) => (o.offer_id === offerId ? { ...o, ...updatedOffer } : o)))
      if (status === 'accepted') {
        const actorSubject = resolveOfferActorSubject(updatedOffer)
        const actorAccepted = actorSubject
          ? (
            (actorSubject === updatedOffer.from_subject && Boolean(updatedOffer.accepted_by_from))
            || (actorSubject === updatedOffer.to_subject && Boolean(updatedOffer.accepted_by_to))
          )
          : false
        const myItems = await fetchMyListings({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          limit: 100,
        })
        const marketItems = await fetchMarketplaceListings({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          limit: 50,
        })
        setMyListings(myItems.map(fromRemoteListing).filter(Boolean))
        setMarketListings(marketItems.map(fromRemoteListing).filter(Boolean))
        if (updatedOffer?.status === 'accepted') {
          setSavedListingNotice('Trade accepted by both users. Shipping labels are being generated automatically and can be downloaded here even if email is unavailable.')
          try {
            await loadShippingLabelsForOffer(offerId)
          } catch {}
        } else if (actorAccepted) {
          setSavedListingNotice('Your acceptance is recorded. Waiting for the other user to accept.')
        }
      }
      const refreshed = await fetchIncomingOffersRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        status: offerStatusFilter,
        limit: 50,
      })
      setIncomingOffers(Array.isArray(refreshed?.items) ? refreshed.items : [])
      setOffersActorSubject(typeof refreshed?.actor?.subject === 'string' ? refreshed.actor.subject : '')
    } catch (err) {
      setSavedListingNotice(err.message || 'Failed to update trade offer.')
    }
  }

  async function loadShippingLabelsForOffer(offerId) {
    const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
    const payload = await fetchShippingLabelsRemote({
      apiBaseUrl,
      apiKey: clerkEnabled ? '' : apiKey.trim(),
      bearerToken,
      offerId,
    })
    const shipments = Array.isArray(payload?.shipments) ? payload.shipments : []
    setShippingLabelsByOffer((prev) => ({ ...prev, [offerId]: shipments }))
    return shipments
  }

  useEffect(() => {
    if (activeTab !== 'inbox') return
    const acceptedOfferIds = incomingOffers
      .filter((offer) => String(offer?.status || '').toLowerCase() === 'accepted')
      .map((offer) => offer.offer_id)
      .filter((offerId) => offerId && !Array.isArray(shippingLabelsByOffer[offerId]))
    if (!acceptedOfferIds.length) return
    let cancelled = false
    ;(async () => {
      for (const offerId of acceptedOfferIds) {
        if (cancelled) return
        try {
          await loadShippingLabelsForOffer(offerId)
        } catch {}
      }
    })()
    return () => { cancelled = true }
  }, [activeTab, incomingOffers, shippingLabelsByOffer])

  async function createShippingLabelsForOffer(offerId) {
    const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
    const quote = shippingQuoteByOffer[offerId] || null
    const payload = await createShippingLabelsRemote({
      apiBaseUrl,
      apiKey: clerkEnabled ? '' : apiKey.trim(),
      bearerToken,
      offerId,
      rateId: quote?.rate_id || null,
    })
    const shipments = Array.isArray(payload?.shipments) ? payload.shipments : []
    setShippingLabelsByOffer((prev) => ({ ...prev, [offerId]: shipments }))
    return shipments
  }

  async function loadShippingQuoteForOffer(offerId) {
    const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
    const quote = await fetchShippingQuoteRemote({
      apiBaseUrl,
      apiKey: clerkEnabled ? '' : apiKey.trim(),
      bearerToken,
      offerId,
    })
    setShippingQuoteByOffer((prev) => ({ ...prev, [offerId]: quote }))
    return quote
  }

  async function openShippingLabel(shipment) {
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      const payload = await fetchShippingLabelDocumentRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        shipmentId: shipment?.shipment_id,
      })
      const rawUrl = (payload?.label_url || shipment?.label_url || '').trim()
      const fromAddr = payload?.from || {}
      const toAddr = payload?.to || {}
      const requiredKeys = ['name', 'line1', 'city', 'state', 'postal_code', 'country']
      const missingFrom = requiredKeys.filter((k) => !String(fromAddr?.[k] || '').trim())
      const missingTo = requiredKeys.filter((k) => !String(toAddr?.[k] || '').trim())
      const hasIncompleteProfile = missingFrom.length > 0 || missingTo.length > 0
      const fmt = {
        name: 'name',
        line1: 'address line 1',
        city: 'city',
        state: 'state',
        postal_code: 'postal code',
        country: 'country',
      }
      if (!rawUrl) {
        const msg = hasIncompleteProfile
          ? `Shipping profile incomplete.${missingFrom.length > 0 ? ` Sender missing: ${missingFrom.map((k) => fmt[k]).join(', ')}.` : ''}${missingTo.length > 0 ? ` Receiver missing: ${missingTo.map((k) => fmt[k]).join(', ')}.` : ''}`
          : 'Carrier label is not available yet. Please retry in a few seconds.'
        setSavedListingNotice(msg)
        window.alert(msg)
        return
      }
      if (/^\/v1\/shipments\/[^/]+\/label$/i.test(rawUrl)) {
        const msg = hasIncompleteProfile
          ? `Shipping profile incomplete.${missingFrom.length > 0 ? ` Sender missing: ${missingFrom.map((k) => fmt[k]).join(', ')}.` : ''}${missingTo.length > 0 ? ` Receiver missing: ${missingTo.map((k) => fmt[k]).join(', ')}.` : ''}`
          : 'Carrier label is still processing. Please retry in a few seconds.'
        setSavedListingNotice(msg)
        window.alert(msg)
        return
      }
      const resolved = /^https?:\/\//i.test(rawUrl)
        ? rawUrl
        : `${apiBaseUrl.replace(/\/$/, '')}${rawUrl}`
      window.open(resolved, '_blank', 'noopener,noreferrer')
    } catch (err) {
      const msg = err.message || 'Failed to open label.'
      setSavedListingNotice(msg)
      window.alert(msg)
    }
  }

  const offeredTotalValue = tradeOfferCandidates
    .filter((x) => tradeOfferListingIds.includes(x.id))
    .reduce((sum, x) => sum + Number(x.estimatedValue || 0), 0)
  const composerTargetValue = Number(tradeComposerTarget?.estimatedValue || 0)
  const composerGapPct = composerTargetValue > 0 ? Math.abs(offeredTotalValue - composerTargetValue) / composerTargetValue : null
  const composerWithinBand = composerGapPct !== null ? composerGapPct <= 0.30 : false

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
      size: itemSize || null,
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
    setItemSize(typeof listing.size === 'string' ? listing.size : '')
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
    setItemSize('')
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
      size: itemSize || null,
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
        const profileDescription = buildSuggestedDescriptionFromProfile(resolved?.item_profile)
        const resolvedCondition = resolved?.user_condition || resolved?.condition?.grade || current.condition
        const resolvedBrand = resolved?.brand?.name || current.brand
        const resolvedCategory = resolved?.category || current.category
        const resolvedValue = Number(askingValue || resolved?.valuation?.estimated_value || current.estimatedValue || 0)
        const resolvedImageUrls = getUploadedImageUrlsFromAnalysis(resolved)
        const updatedPayload = {
          ...current,
          title: itemTitle.trim() || itemDescription.trim() || resolved?.item_profile?.model_identification?.name || current.title,
          description: (itemDescription || '').trim() || current.description || profileDescription || '',
          image: resolvedImageUrls[0] || current.image || null,
          images: resolvedImageUrls.length > 0 ? resolvedImageUrls : (Array.isArray(current.images) ? current.images : [current.image].filter(Boolean)),
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
      size: itemSize || listing.size || null,
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
        const profileDescription = buildSuggestedDescriptionFromProfile(resolved?.item_profile)
        const resolvedCondition = resolved?.user_condition || resolved?.condition?.grade || userCondition || current.condition
        const resolvedBrand = resolved?.brand?.name || current.brand
        const resolvedCategory = resolved?.category || category || current.category
        const resolvedValue = Number(askingValue || resolved?.valuation?.estimated_value || current.estimatedValue || 0)
        const resolvedImageUrls = getUploadedImageUrlsFromAnalysis(resolved)
        const updatedPayload = {
          ...current,
          title: (itemTitle || '').trim() || (itemDescription || '').trim() || resolved?.item_profile?.model_identification?.name || current.title,
          description: (itemDescription || '').trim() || current.description || profileDescription || '',
          image: resolvedImageUrls[0] || current.image || null,
          images: resolvedImageUrls.length > 0 ? resolvedImageUrls : (Array.isArray(current.images) ? current.images : [current.image].filter(Boolean)),
          brand: resolvedBrand,
          category: resolvedCategory,
          condition: resolvedCondition,
          size: itemSize || current.size || null,
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
      size: itemSize || listing.size || null,
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
    setItemSize(typeof listing.size === 'string' ? listing.size : '')
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
          <div className="app-brand-row">
            <div className="app-brandmark" aria-label="Jouft brand">
              <span className="app-brand-emblem">J</span>
              <div className="app-brand-lockup">
                <strong>JOUFT</strong>
                <small>AI LUXURY EXCHANGE</small>
              </div>
            </div>
            <div className="app-brand-links" aria-label="Primary app sections">
              <a href={tabHref('market')} className={activeTab === 'market' ? 'app-brand-link active' : 'app-brand-link'}>Marketplace</a>
              <a href={tabHref('portfolio')} className={activeTab === 'portfolio' ? 'app-brand-link active' : 'app-brand-link'}>My Closet</a>
              <a href={tabHref('inbox')} className={activeTab === 'inbox' ? 'app-brand-link active' : 'app-brand-link'}>Trade Inbox</a>
              <a href={tabHref('profile')} className={activeTab === 'profile' ? 'app-brand-link active' : 'app-brand-link'}>Profile</a>
            </div>
          </div>
        </div>
        <div className="topbar-actions">
          {!clerkEnabled && <label className="inline-field"><span>API Key</span><input value={apiKey} onChange={(e) => setApiKey(e.target.value)} /></label>}
          {clerkEnabled ? (
            <>
              <button className="ghost" type="button" onClick={() => setActiveTab('profile')}>Profile</button>
              {userMenu}
            </>
          ) : <button className="ghost" onClick={onLogout}>Log out</button>}
        </div>
      </div>

      {showFreshListingsStrip && activeTab !== 'profile' && latestActiveListings.length > 0 && (
      <section className="panel latest-hero">
        <div className="panel-header" style={{ marginBottom: 8 }}>
          <div>
            <p className="eyebrow">Latest Marketplace</p>
            <h2 style={{ marginTop: 4 }}>Fresh active listings</h2>
          </div>
          <div className="button-row">
            <button className="ghost small" type="button" onClick={() => setActiveTab('market')}>View Marketplace</button>
          </div>
        </div>
        <div className="latest-rail">
          {latestActiveListings.map((item) => {
            const thumb = (Array.isArray(item.images) && item.images.length > 0) ? item.images[0] : item.image
            return (
              <button key={`latest-${item.id}`} type="button" className="latest-card" onClick={() => setActiveTab('market')}>
                <div className="latest-thumb" aria-hidden="true">
                  {thumb ? (
                    <img src={thumb} alt="" />
                  ) : (
                    <div className="listing-image-fallback">Image unavailable</div>
                  )}
                </div>
                <div className="latest-meta">
                  <h3 className="editorial-title latest-title">{item.title || 'Untitled listing'}</h3>
                  <p className="editorial-byline">BY {String(item.owner || 'Unknown seller').toUpperCase()}</p>
                  <p className="editorial-meta">
                    EST. {money(item.estimatedValue)}
                  </p>
                </div>
              </button>
            )
          })}
        </div>
      </section>
      )}

      {activeTab === 'profile' ? (
        <main className="content" style={{ marginTop: 12 }}>
          <section className="panel">
            <div style={{ maxWidth: 980 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <h3 style={{ margin: 0 }}>Profile</h3>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 16 }}>
                <aside className="profile-nav" style={{ border: '1px solid var(--line)', borderRadius: 12, padding: 10, alignSelf: 'start' }}>
                  <button className={profileSection === 'general' ? 'nav-item active' : 'nav-item'} type="button" onClick={() => setProfileSection('general')}>General</button>
                  <button className={profileSection === 'style' ? 'nav-item active' : 'nav-item'} type="button" onClick={() => setProfileSection('style')}>Style Preferences</button>
                  <button className={profileSection === 'subscription' ? 'nav-item active' : 'nav-item'} type="button" onClick={() => setProfileSection('subscription')}>Subscription</button>
                  <button className={profileSection === 'shipping' ? 'nav-item active' : 'nav-item'} type="button" onClick={() => setProfileSection('shipping')}>Shipping</button>
                </aside>
                <div>
                  {profileSection === 'general' && (
                    <div className="metric-grid">
                      <div><span>Name</span><strong>{profileData?.name || session?.name || 'n/a'}</strong></div>
                      <div><span>First Name</span><strong>{profileData?.firstName || 'n/a'}</strong></div>
                      <div><span>Last Name</span><strong>{profileData?.lastName || 'n/a'}</strong></div>
                      <div><span>Email</span><strong>{profileData?.email || session?.email || 'n/a'}</strong></div>
                      <div><span>Phone</span><strong>{profileData?.phone || 'n/a'}</strong></div>
                    </div>
                  )}
                  {profileSection === 'style' && (
                    <div style={{ marginTop: 4 }}>
                      <p className="eyebrow" style={{ marginBottom: 8 }}>Style Preferences</p>
                      <div className="field-grid">
                        <label>
                          <span>Gender</span>
                          <select
                            value={profileQuiz.gender || ''}
                            onChange={(e) => {
                              const nextGender = e.target.value
                              setProfileQuiz((p) => ({
                                ...p,
                                gender: nextGender,
                                dresses_size: nextGender === 'male' ? [] : p.dresses_size,
                                category_preferences: nextGender === 'male'
                                  ? p.category_preferences.filter((x) => x !== 'Dresses')
                                  : p.category_preferences,
                              }))
                            }}
                          >
                            <option value="">Select gender</option>
                            <option value="female">Female</option>
                            <option value="male">Male</option>
                            <option value="other">Other</option>
                          </select>
                        </label>
                        <div>
                          <span className="tiny-note">Tops Size (multi-select)</span>
                          <div className="tag-row" style={{ marginTop: 6 }}>
                            {profileApparelSizeOptions.map((s) => {
                              const selected = Array.isArray(profileQuiz.tops_size) && profileQuiz.tops_size.includes(s)
                              return (
                                <button
                                  key={`tops-${s}`}
                                  type="button"
                                  className={selected ? 'pill' : 'ghost small'}
                                  onClick={() => setProfileQuiz((p) => ({
                                    ...p,
                                    tops_size: selected
                                      ? p.tops_size.filter((x) => x !== s)
                                      : [...p.tops_size, s],
                                  }))}
                                >
                                  {s}
                                </button>
                              )
                            })}
                          </div>
                        </div>
                        {normalizedProfileGender !== 'male' && (
                          <div>
                            <span className="tiny-note">Dresses Size (multi-select)</span>
                            <div className="tag-row" style={{ marginTop: 6 }}>
                              {profileApparelSizeOptions.map((s) => {
                                const selected = Array.isArray(profileQuiz.dresses_size) && profileQuiz.dresses_size.includes(s)
                                return (
                                  <button
                                    key={`dresses-${s}`}
                                    type="button"
                                    className={selected ? 'pill' : 'ghost small'}
                                    onClick={() => setProfileQuiz((p) => ({
                                      ...p,
                                      dresses_size: selected
                                        ? p.dresses_size.filter((x) => x !== s)
                                        : [...p.dresses_size, s],
                                    }))}
                                  >
                                    {s}
                                  </button>
                                )
                              })}
                            </div>
                          </div>
                        )}
                        <div>
                          <span className="tiny-note">Bottoms Size (multi-select)</span>
                          <div className="tag-row" style={{ marginTop: 6 }}>
                            {profileApparelSizeOptions.map((s) => {
                              const selected = Array.isArray(profileQuiz.bottoms_size) && profileQuiz.bottoms_size.includes(s)
                              return (
                                <button
                                  key={`bottoms-${s}`}
                                  type="button"
                                  className={selected ? 'pill' : 'ghost small'}
                                  onClick={() => setProfileQuiz((p) => ({
                                    ...p,
                                    bottoms_size: selected
                                      ? p.bottoms_size.filter((x) => x !== s)
                                      : [...p.bottoms_size, s],
                                  }))}
                                >
                                  {s}
                                </button>
                              )
                            })}
                          </div>
                        </div>
                        <div>
                          <span className="tiny-note">Shoes Size (multi-select)</span>
                          <div className="tag-row" style={{ marginTop: 6 }}>
                            {profileShoeSizeOptions.map((s) => {
                              const selected = Array.isArray(profileQuiz.shoes_size) && profileQuiz.shoes_size.includes(s)
                              return (
                                <button
                                  key={`shoes-${s}`}
                                  type="button"
                                  className={selected ? 'pill' : 'ghost small'}
                                  onClick={() => setProfileQuiz((p) => ({
                                    ...p,
                                    shoes_size: selected
                                      ? p.shoes_size.filter((x) => x !== s)
                                      : [...p.shoes_size, s],
                                  }))}
                                >
                                  {s}
                                </button>
                              )
                            })}
                          </div>
                        </div>
                      </div>
                      <div style={{ marginTop: 10 }}>
                        <span className="tiny-note">Category Preferences</span>
                        <div className="tag-row" style={{ marginTop: 6 }}>
                          {profileCategoryOptions.map((c) => {
                            const selected = profileQuiz.category_preferences.includes(c)
                            return (
                              <button
                                key={c}
                                type="button"
                                className={selected ? 'pill' : 'ghost small'}
                                onClick={() => setProfileQuiz((p) => ({
                                  ...p,
                                  category_preferences: selected
                                    ? p.category_preferences.filter((x) => x !== c)
                                    : [...p.category_preferences, c],
                                }))}
                              >
                                {c}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    </div>
                  )}
                  {profileSection === 'subscription' && (
                    <div style={{ marginTop: 4 }}>
                      <p className="eyebrow" style={{ marginBottom: 8 }}>Subscription</p>
                      <div className="billing-cycle-toggle">
                        <button
                          className={selectedBillingCycle === 'monthly' ? 'nav-item active' : 'nav-item'}
                          type="button"
                          onClick={() => setProfileQuiz((p) => ({ ...p, subscription_billing_cycle: 'monthly' }))}
                        >
                          Monthly Billing
                        </button>
                        <button
                          className={selectedBillingCycle === 'annual' ? 'nav-item active' : 'nav-item'}
                          type="button"
                          onClick={() => setProfileQuiz((p) => ({ ...p, subscription_billing_cycle: 'annual' }))}
                        >
                          Annual Billing (10% Off)
                        </button>
                      </div>
                      <div className="subscription-plan-grid">
                        {SUBSCRIPTION_PLANS.map((plan) => {
                          const isSelected = selectedSubscriptionPlanId === plan.id
                          const annualTotal = plan.monthlyPrice > 0 ? Math.round(plan.monthlyPrice * 12 * 0.9) : 0
                          const annualMonthlyEquivalent = plan.monthlyPrice > 0 ? (annualTotal / 12) : 0
                          const priceLabel = selectedBillingCycle === 'annual'
                            ? (plan.monthlyPrice > 0
                              ? `$${annualTotal}/year ($${annualMonthlyEquivalent.toFixed(2)}/month)`
                              : '$0/year')
                            : (plan.monthlyPrice > 0 ? `$${plan.monthlyPrice}/month` : '$0/month')
                          return (
                            <button
                              key={plan.id}
                              type="button"
                              className={isSelected ? 'subscription-plan-card active' : 'subscription-plan-card'}
                              onClick={() => setProfileQuiz((p) => ({
                                ...p,
                                subscription_plan: plan.id,
                                subscription_status: 'active',
                              }))}
                            >
                              <span className="subscription-plan-name">{plan.name}</span>
                              <strong className="subscription-plan-price">{priceLabel}</strong>
                              <span className="subscription-plan-limit">{plan.description}</span>
                            </button>
                          )
                        })}
                      </div>
                      <div className="field-grid two">
                        <label>
                          <span>Status</span>
                          <select
                            value={profileQuiz.subscription_status || ''}
                            onChange={(e) => setProfileQuiz((p) => ({ ...p, subscription_status: e.target.value }))}
                          >
                            <option value="">Select status</option>
                            <option value="active">Active</option>
                            <option value="trialing">Trialing</option>
                            <option value="paused">Paused</option>
                            <option value="canceled">Canceled</option>
                          </select>
                        </label>
                        <label>
                          <span>Renewal Date</span>
                          <input type="date" value={profileQuiz.subscription_renewal_date || ''} onChange={(e) => setProfileQuiz((p) => ({ ...p, subscription_renewal_date: e.target.value }))} />
                        </label>
                      </div>
                      <div style={{ marginTop: 14 }}>
                        <p className="eyebrow" style={{ marginBottom: 8 }}>Payment Methods ({paymentMethods.length})</p>
                        <span className="tiny-note">Payments are fully managed by Stripe. No raw card data is collected or stored by this app.</span>
                        <div className="button-row" style={{ marginBottom: 8 }}>
                          <button className="ghost small" type="button" onClick={() => setShowStripePaymentModal(true)}>
                            + Add Payment Method
                          </button>
                        </div>
                        <div style={{ display: 'grid', gap: 8 }}>
                          {paymentActionMsg && <span className="tiny-note" style={{ color: '#067647' }}>{paymentActionMsg}</span>}
                          {paymentLoadError && <span className="tiny-note" style={{ color: '#b42318' }}>{paymentLoadError}</span>}
                          {paymentMethods.length === 0 && <span className="tiny-note">No payment methods added yet.</span>}
                          {paymentMethods.map((method) => (
                            <div key={method.payment_method_id} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', border: '1px solid var(--line)', borderRadius: 10, padding: '8px 10px' }}>
                              <div>
                                <strong>{method.label || method.method_type}</strong>
                                <div className="tiny-note">{method.provider}{method.is_default ? ' • Default' : ''}</div>
                                {(method.last4 || method.email) && (
                                  <div className="tiny-note">{method.last4 ? `•••• ${method.last4}` : method.email}</div>
                                )}
                              </div>
                              <div className="button-row">
                                {!method.is_default && (
                                  <button
                                    className="ghost small"
                                    type="button"
                                    disabled={paymentBusy}
                                    onClick={async () => {
                                      setPaymentBusy(true)
                                      try {
                                        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
                                        await setDefaultPaymentMethodRemote({
                                          apiBaseUrl,
                                          apiKey: clerkEnabled ? '' : apiKey.trim(),
                                          bearerToken,
                                          paymentMethodId: method.payment_method_id,
                                        })
                                        const refreshed = await fetchPaymentMethodsRemote({
                                          apiBaseUrl,
                                          apiKey: clerkEnabled ? '' : apiKey.trim(),
                                          bearerToken,
                                        })
                                        setPaymentMethods(refreshed)
                                        setPaymentActionMsg('Default payment method updated.')
                                        setPaymentLoadError('')
                                      } catch (err) {
                                        setPaymentActionMsg('')
                                        setPaymentLoadError(err?.message || 'Failed to set default method.')
                                        setProfileSaveMsg(err.message || 'Failed to set default method.')
                                      } finally {
                                        setPaymentBusy(false)
                                      }
                                    }}
                                  >
                                    Set Default
                                  </button>
                                )}
                                <button
                                  className="ghost small"
                                  type="button"
                                  disabled={paymentDeleteBusyId === method.payment_method_id}
                                  onClick={async () => {
                                    const confirmed = window.confirm('Delete this payment method from both Jouft and Stripe?')
                                    if (!confirmed) return
                                    setPaymentActionMsg('Removing payment method...')
                                    setPaymentDeleteBusyId(method.payment_method_id)
                                    try {
                                      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
                                      await deletePaymentMethodRemote({
                                        apiBaseUrl,
                                        apiKey: clerkEnabled ? '' : apiKey.trim(),
                                        bearerToken,
                                        paymentMethodId: method.payment_method_id,
                                      })
                                      const refreshed = await fetchPaymentMethodsRemote({
                                        apiBaseUrl,
                                        apiKey: clerkEnabled ? '' : apiKey.trim(),
                                        bearerToken,
                                      })
                                      setPaymentMethods(refreshed)
                                      setPaymentActionMsg('Payment method removed.')
                                      setPaymentLoadError('')
                                    } catch (err) {
                                      setPaymentActionMsg('')
                                      setPaymentLoadError(err?.message || 'Failed to remove method.')
                                      setProfileSaveMsg(err.message || 'Failed to remove method.')
                                    } finally {
                                      setPaymentDeleteBusyId('')
                                    }
                                  }}
                                >
                                  {paymentDeleteBusyId === method.payment_method_id ? 'Removing...' : 'Remove'}
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                  {profileSection === 'shipping' && (
                    <div style={{ marginTop: 4 }}>
                      <div className="shipping-address-head">
                        <p className="eyebrow" style={{ marginBottom: 8 }}>Shipping Addresses</p>
                        <div className="button-row" style={{ marginTop: 0 }}>
                          <button className="ghost small" type="button" onClick={addShippingAddress}>Add Address</button>
                          <button className="ghost small" type="button" onClick={removeActiveShippingAddress} disabled={shippingAddresses.length <= 1}>Remove Selected</button>
                        </div>
                      </div>
                      <div className="shipping-address-tabs">
                        {shippingAddresses.map((address, idx) => (
                          <button
                            key={address.id || `shipping-address-${idx}`}
                            type="button"
                            className={safeActiveShippingAddressIdx === idx ? 'nav-item active' : 'nav-item'}
                            onClick={() => {
                              setActiveShippingAddressIdx(idx)
                              setAddressSuggestions([])
                            }}
                          >
                            {address.label?.trim() || `Address ${idx + 1}`}
                          </button>
                        ))}
                      </div>
                      <div className="field-grid">
                        <label>
                          <span>Address Label</span>
                          <input value={activeShippingAddress?.label || ''} onChange={(e) => updateActiveShippingAddress({ label: e.target.value })} placeholder="Home, Office, etc." />
                        </label>
                        <label>
                          <span>Full Name</span>
                          <input value={activeShippingAddress?.full_name || ''} onChange={(e) => updateActiveShippingAddress({ full_name: e.target.value })} />
                        </label>
                        <label>
                          <span>Address Line 1</span>
                          <input value={activeShippingAddress?.address_line1 || ''} onChange={(e) => updateActiveShippingAddress({ address_line1: e.target.value })} />
                        </label>
                        {addressSuggestions.length > 0 && (
                          <div style={{ gridColumn: '1 / -1', border: '1px solid var(--line)', borderRadius: 10, background: 'var(--panel)' }}>
                            {addressSuggestions.map((s, idx) => (
                              <button
                                key={`${s.formatted || s.street_address || 'addr'}-${idx}`}
                                type="button"
                                className="ghost small"
                                style={{ width: '100%', textAlign: 'left', borderRadius: 0, border: 'none', borderBottom: idx === addressSuggestions.length - 1 ? 'none' : '1px solid var(--line)' }}
                                onClick={() => {
                                  updateActiveShippingAddress({
                                    address_line1: s.street_address || activeShippingAddress?.address_line1 || '',
                                    city: s.city || activeShippingAddress?.city || '',
                                    state: s.state || activeShippingAddress?.state || '',
                                    postal_code: s.postal_code || activeShippingAddress?.postal_code || '',
                                    country: activeShippingAddress?.country || 'US',
                                  })
                                  setAddressSuggestions([])
                                }}
                              >
                                {s.formatted || s.street_address}
                              </button>
                            ))}
                          </div>
                        )}
                        <label>
                          <span>Address Line 2</span>
                          <input value={activeShippingAddress?.address_line2 || ''} onChange={(e) => updateActiveShippingAddress({ address_line2: e.target.value })} />
                        </label>
                        <label>
                          <span>City</span>
                          <input value={activeShippingAddress?.city || ''} onChange={(e) => updateActiveShippingAddress({ city: e.target.value })} />
                        </label>
                        <label>
                          <span>State</span>
                          <input value={activeShippingAddress?.state || ''} onChange={(e) => updateActiveShippingAddress({ state: e.target.value })} />
                        </label>
                        <label>
                          <span>Postal Code</span>
                          <input value={activeShippingAddress?.postal_code || ''} onChange={(e) => updateActiveShippingAddress({ postal_code: e.target.value })} />
                        </label>
                        <label>
                          <span>Country</span>
                          <input value={activeShippingAddress?.country || ''} onChange={(e) => updateActiveShippingAddress({ country: e.target.value })} />
                        </label>
                      </div>
                    </div>
                  )}
                </div>
              </div>
              <div className="button-row" style={{ marginTop: 12 }}>
                <button
                  className="ghost small"
                  type="button"
                  onClick={() => setActiveTab('portfolio')}
                >
                  Cancel
                </button>
                <button
                  className="primary"
                  type="button"
                  onClick={async () => {
                    try {
                      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
                      const normalizedAddresses = normalizeShippingAddresses(profileQuiz.shipping_addresses, profileQuiz)
                      const primaryAddress = normalizedAddresses[0] || emptyShippingAddress()
                      const payload = {
                        ...profileQuiz,
                        tops_size: serializeMultiSizeValue(profileQuiz.tops_size),
                        dresses_size: serializeMultiSizeValue(profileQuiz.dresses_size),
                        bottoms_size: serializeMultiSizeValue(profileQuiz.bottoms_size),
                        shoes_size: serializeMultiSizeValue(profileQuiz.shoes_size),
                        subscription_plan: selectedSubscriptionPlanId,
                        subscription_billing_cycle: selectedBillingCycle,
                        shipping_addresses: normalizedAddresses.map((address, idx) => ({
                          label: address.label || null,
                          full_name: address.full_name || null,
                          address_line1: address.address_line1 || null,
                          address_line2: address.address_line2 || null,
                          city: address.city || null,
                          state: address.state || null,
                          postal_code: address.postal_code || null,
                          country: address.country || null,
                          is_default: idx === 0,
                        })),
                        shipping_full_name: primaryAddress.full_name || null,
                        shipping_address_line1: primaryAddress.address_line1 || null,
                        shipping_address_line2: primaryAddress.address_line2 || null,
                        shipping_city: primaryAddress.city || null,
                        shipping_state: primaryAddress.state || null,
                        shipping_postal_code: primaryAddress.postal_code || null,
                        shipping_country: primaryAddress.country || null,
                        payment_methods: paymentMethods
                          .map((m) => (typeof m?.label === 'string' ? m.label.trim() : ''))
                          .filter(Boolean),
                      }
                      const saved = await saveProfileQuizRemote({
                        apiBaseUrl,
                        apiKey: clerkEnabled ? '' : apiKey.trim(),
                        bearerToken,
                        payload,
                      })
                      const savedShippingAddresses = normalizeShippingAddresses(saved?.shipping_addresses, saved)
                      setProfileQuiz({
                        gender: saved?.gender || '',
                        tops_size: normalizeMultiSizeValue(saved?.tops_size),
                        dresses_size: normalizeMultiSizeValue(saved?.dresses_size),
                        bottoms_size: normalizeMultiSizeValue(saved?.bottoms_size),
                        shoes_size: normalizeMultiSizeValue(saved?.shoes_size),
                        category_preferences: Array.isArray(saved?.category_preferences) ? saved.category_preferences : [],
                        shipping_full_name: savedShippingAddresses[0]?.full_name || '',
                        shipping_address_line1: savedShippingAddresses[0]?.address_line1 || '',
                        shipping_address_line2: savedShippingAddresses[0]?.address_line2 || '',
                        shipping_city: savedShippingAddresses[0]?.city || '',
                        shipping_state: savedShippingAddresses[0]?.state || '',
                        shipping_postal_code: savedShippingAddresses[0]?.postal_code || '',
                        shipping_country: savedShippingAddresses[0]?.country || '',
                        shipping_addresses: savedShippingAddresses,
                        subscription_plan: normalizeSubscriptionPlanId(saved?.subscription_plan),
                        subscription_billing_cycle: normalizeBillingCycle(saved?.subscription_billing_cycle),
                        subscription_status: saved?.subscription_status || '',
                        subscription_renewal_date: saved?.subscription_renewal_date || '',
                        payment_methods: Array.isArray(saved?.payment_methods) ? saved.payment_methods : [],
                      })
                      setActiveShippingAddressIdx(0)
                      setProfileSaveMsg('Profile saved.')
                    } catch (err) {
                      setProfileSaveMsg(err.message || 'Failed to save profile.')
                    }
                  }}
                >
                  Save Profile
                </button>
                {profileSaveMsg && <span className="tiny-note">{profileSaveMsg}</span>}
              </div>
            </div>
          </section>
        </main>
      ) : (
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
                      {(() => {
                        const categoryForSize = category || analysisResult?.category || ''
                        const brandForSize = analysisResult?.brand?.name || ''
                        const sizeChartUrl = brandSizeChartUrl(brandForSize, categoryForSize)
                        if (!brandForSize || brandForSize === 'unknown') return null
                        return (
                          <div className="request-list">
                            <span>Brand size chart:</span>
                            {sizeChartUrl ? (
                              <a href={sizeChartUrl} target="_blank" rel="noreferrer">
                                {brandForSize} size chart
                              </a>
                            ) : (
                              <code>No chart available for this brand</code>
                            )}
                          </div>
                        )
                      })()}
                      <label>
                        <span>Size</span>
                        <select
                          value={itemSize}
                          onChange={(e) => setItemSize(e.target.value)}
                          required
                        >
                          {(() => {
                            const categoryForSize = category || analysisResult?.category || ''
                            const options = sizeOptionsForCategory(categoryForSize)
                            return (
                              <>
                                <option value="">{options.length ? 'Select size' : 'Select category first'}</option>
                                {options.map((opt) => (
                                  <option key={opt} value={opt}>{opt}</option>
                                ))}
                              </>
                            )
                          })()}
                        </select>
                      </label>
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
                        <span><strong>Size:</strong> {itemSize || 'n/a'}</span>
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
                        <button
                          className="primary"
                          type="button"
                          onClick={() => {
                            if (!itemSize) {
                              setAnalysisError('Select item size before publishing.')
                              return
                            }
                            saveListingDraft()
                          }}
                        >
                          {editingListingId ? 'Update Listing' : 'Publish Listing'}
                        </button>
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
                <div>
                  <p className="eyebrow">Portfolio</p>
                  <h2>Your active listings</h2>
                  <div className="button-row" style={{ marginTop: 6 }}>
                    <button className={closetFilter === 'all' ? 'primary' : 'ghost small'} type="button" onClick={() => setClosetFilter('all')}>All ({myListings.length})</button>
                    <button className={closetFilter === 'active' ? 'primary' : 'ghost small'} type="button" onClick={() => setClosetFilter('active')}>Active ({closetBreakdown.active})</button>
                    <button className={closetFilter === 'draft' ? 'primary' : 'ghost small'} type="button" onClick={() => setClosetFilter('draft')}>Draft ({closetBreakdown.draft})</button>
                    <button className={closetFilter === 'offers' ? 'primary' : 'ghost small'} type="button" onClick={() => setClosetFilter('offers')}>Offers ({closetBreakdown.offers})</button>
                    <button className={closetFilter === 'traded' ? 'primary' : 'ghost small'} type="button" onClick={() => setClosetFilter('traded')}>Traded ({closetBreakdown.traded})</button>
                  </div>
                </div>
                <div className="header-actions">
                  <button className="primary" onClick={openCreateListingModal}>Create Listing</button>
                </div>
              </div>
              {filteredClosetListings.length === 0 ? (
                <div className="empty-state"><h3>No listings yet</h3><p>Analyze an item and publish your first listing to start selling or trading.</p><button className="primary" onClick={() => setActiveTab('upload')}>Create first listing</button></div>
              ) : <div className="listing-grid market-editorial-grid">{filteredClosetListings.map((item) => <ListingCard key={item.id} item={item} own onEditDraft={openEditListingModal} editorialStyle />)}</div>}
            </section>
          )}

          {activeTab === 'inbox' && (
            <section className="panel">
              <div className="panel-header">
                <div><p className="eyebrow">Trade Inbox</p><h2>Incoming offers</h2></div>
                <div className="market-controls">
                  <button className={offerStatusFilter === 'all' ? 'primary' : 'ghost small'} type="button" onClick={() => setOfferStatusFilter('all')}>All</button>
                  <button className={offerStatusFilter === 'pending' ? 'primary' : 'ghost small'} type="button" onClick={() => setOfferStatusFilter('pending')}>Pending</button>
                </div>
              </div>
              {incomingOffers.length === 0 ? (
                <div className="empty-state"><h3>No offers</h3><p>No incoming trade offers for this filter yet.</p></div>
              ) : (
                <div className="inbox-editorial-list">
                  {incomingOffers.map((offer) => {
                    const actorSubject = resolveOfferActorSubject(offer)
                    const isSender = actorSubject && actorSubject === offer.from_subject
                    const actorAccepted = isSender ? Boolean(offer.accepted_by_from) : Boolean(offer.accepted_by_to)
                    const bothAccepted = Boolean(offer.accepted_by_from) && Boolean(offer.accepted_by_to)
                    const canReceiverAccept = !isSender
                    const offerShipments = shippingLabelsByOffer[offer.offer_id]
                    const hasLoadedShipments = Array.isArray(offerShipments)
                    const hasShipments = hasLoadedShipments && offerShipments.length > 0
                    const selectedAddressId = offerReceiveAddressById[offer.offer_id] || shippingAddresses[0]?.id || ''
                    const selectedAddress = shippingAddresses.find((a) => a.id === selectedAddressId) || shippingAddresses[0] || null
                    const quote = shippingQuoteByOffer[offer.offer_id]
                    const targetThumbs = (Array.isArray(offer.target_listing?.images) && offer.target_listing.images.length > 0
                      ? offer.target_listing.images
                      : [offer.target_listing?.image].filter(Boolean)
                    ).slice(0, 4)
                    const offeredThumbs = (Array.isArray(offer.offered_listings) && offer.offered_listings.length > 0 ? offer.offered_listings : (offer.offered_listing ? [offer.offered_listing] : []))
                      .flatMap((listing) => ((Array.isArray(listing?.images) && listing.images.length > 0 ? listing.images : [listing?.image].filter(Boolean)).slice(0, 2)).map((url) => ({ url, listing })))
                      .slice(0, 8)
                    const targetHero = targetThumbs[0] || null
                    return (
                    <article key={offer.offer_id} className="inbox-editorial-card">
                      <div className="inbox-editorial-frame">
                        <div className="inbox-editorial-media">
                          <button type="button" className="inbox-target-hero" onClick={() => setTradeDetailListing(offer.target_listing || null)}>
                            {targetHero ? (
                              <img src={targetHero} alt={offer.target_listing?.title || 'Your listing'} />
                            ) : (
                              <span className="inbox-target-fallback">No image</span>
                            )}
                            <span className="inbox-target-chip">Your Item</span>
                          </button>
                          <div className="inbox-offered-column">
                            <p className="inbox-lane-label">Offered Items</p>
                            <div className="inbox-offered-grid">
                              {offeredThumbs.map(({ url, listing }) => (
                                <button key={`offered-${offer.offer_id}-${listing?.listing_id || 'listing'}-${url}`} type="button" className="inbox-thumb-btn" onClick={() => setTradeDetailListing(listing || null)}>
                                  <img src={url} alt="Offered listing" className="inbox-thumb" />
                                </button>
                              ))}
                            </div>
                          </div>
                        </div>
                        <div className="inbox-editorial-content">
                          <div className="inbox-editorial-head">
                            <p className="eyebrow">Trade Offer</p>
                            <span className={`inbox-status-pill inbox-status-${String(offer.status || '').toLowerCase() || 'pending'}`}>{offer.status || 'pending'}</span>
                          </div>
                          <h3 className="inbox-editorial-title">
                            {offer.from_subject} wants to trade {offer.offered_listing?.title || 'their listing'}
                          </h3>
                          <p className="inbox-editorial-subtitle">For your {offer.target_listing?.title || 'listing'}</p>
                        </div>
                      </div>
                      {offer.message ? <p className="inbox-offer-message">Message: {offer.message}</p> : null}
                      {offer.status === 'pending' && (
                        <div className="button-row inbox-editorial-actions">
                          {canReceiverAccept && !actorAccepted ? (
                            <>
                              <label className="inbox-address-select">
                                <span>Receive At Address</span>
                                <select
                                  value={selectedAddressId}
                                  onChange={(e) => setOfferReceiveAddressById((prev) => ({ ...prev, [offer.offer_id]: e.target.value }))}
                                >
                                  {shippingAddresses.map((addr, idx) => (
                                    <option key={addr.id} value={addr.id}>{addr.label?.trim() || `Address ${idx + 1}`} - {addr.city || 'City'} {addr.state || ''}</option>
                                  ))}
                                </select>
                              </label>
                              <button
                                className="primary"
                                type="button"
                                onClick={() => respondToOffer(
                                  offer.offer_id,
                                  'accepted',
                                  selectedAddress ? {
                                    label: selectedAddress.label || null,
                                    full_name: selectedAddress.full_name || null,
                                    address_line1: selectedAddress.address_line1 || null,
                                    address_line2: selectedAddress.address_line2 || null,
                                    city: selectedAddress.city || null,
                                    state: selectedAddress.state || null,
                                    postal_code: selectedAddress.postal_code || null,
                                    country: selectedAddress.country || null,
                                    is_default: false,
                                  } : null,
                                )}
                              >
                                Accept Trade
                              </button>
                              <button className="ghost" type="button" onClick={() => respondToOffer(offer.offer_id, 'declined')}>Decline</button>
                            </>
                          ) : isSender ? (
                            <span className="tiny-note inbox-flow-note">Offer sent. Waiting for receiver to accept.</span>
                          ) : (
                            <span className="tiny-note inbox-flow-note">You accepted this trade. Finalizing shipment labels.</span>
                          )}
                        </div>
                      )}
                      {quote?.amount ? (
                        <p className="tiny-note inbox-flow-note">
                          Quote: {quote.currency || 'USD'} {quote.amount} • {quote.carrier || 'USPS'} {quote.service_level || ''}
                        </p>
                      ) : null}
                      {(offer.status === 'accepted' || bothAccepted) && (
                        <div className="inbox-label-section">
                          {!hasLoadedShipments ? (
                            <p className="tiny-note inbox-flow-note">Loading shipping labels...</p>
                          ) : null}
                          {hasShipments && (
                            <div className="inbox-label-list">
                              {offerShipments.map((s) => (
                                <div key={s.shipment_id} className="inbox-label-card">
                                  <strong>{s.carrier} • {s.service_level}</strong>
                                  <div className="tiny-note">Tracking: {s.tracking_number || 'pending'}</div>
                                  <div className="tiny-note">From: {s.from_name || 'n/a'} • {s.from_city || ''} {s.from_state || ''}</div>
                                  <div className="tiny-note">To: {s.to_name || 'n/a'} • {s.to_city || ''} {s.to_state || ''}</div>
                                  <button type="button" className="ghost small" onClick={() => openShippingLabel(s)}>
                                    Download label
                                  </button>
                                </div>
                              ))}
                            </div>
                          )}
                          <div className="button-row inbox-editorial-actions">
                            <button
                              className="ghost small"
                              type="button"
                              onClick={async () => {
                                try {
                                  await loadShippingLabelsForOffer(offer.offer_id)
                                } catch (err) {
                                  setSavedListingNotice(err.message || 'Failed to load shipping labels.')
                                }
                              }}
                            >
                              Refresh Labels
                            </button>
                          </div>
                        </div>
                      )}
                    </article>
                  )})}
                </div>
              )}
            </section>
          )}

          {activeTab === 'market' && (
            <section className="panel">
              <div className="panel-header">
                <div><p className="eyebrow">Marketplace</p><h2>Find trade opportunities near your value target</h2></div>
                <div className="market-controls">
                  <input value={marketSearch} onChange={(e) => setMarketSearch(e.target.value)} placeholder="Search brand, category, city, style..." />
                  <label className="toggle"><input type="checkbox" checked={tradeOnly} onChange={(e) => setTradeOnly(e.target.checked)} /><span>Trade only</span></label>
                  {marketMagazineIndex !== null ? (
                    <button className="ghost small" type="button" onClick={() => setMarketMagazineIndex(null)}>Back to Regular View</button>
                  ) : null}
                </div>
              </div>
              <div className="market-layout">
                {marketMagazineIndex !== null && filteredListings[marketMagazineIndex] ? (
                  <div className="market-magazine-shell">
                    <button className="market-magazine-nav" type="button" onClick={flipMarketplaceMagazinePrev} aria-label="Previous listing page">&#8249;</button>
                    <div className="market-magazine-viewport">
                      {(() => {
                        const item = filteredListings[marketMagazineIndex]
                        const similarMatches = Array.isArray(item.matches) ? item.matches : []
                        const matchPreviewListings = similarMatches
                          .map((candidate) => ({ candidate, thumb: getListingGallery(candidate)[0] }))
                          .filter((entry) => Boolean(entry.thumb))
                        const heroGallery = getListingGallery(item)
                        const hero = heroGallery[0]
                        const own = String(item.owner || '').trim().toLowerCase() === String(session?.name || '').trim().toLowerCase()
                        return (
                          <article className="market-magazine-page" key={`market-page-${item.id}-${marketMagazineIndex}`}>
                            <div className="market-magazine-feature">
                              <div className="market-magazine-top">
                                <div className="market-magazine-copy">
                                  <p className="eyebrow">Marketplace</p>
                                  <h3 className="editorial-title">{item.title || 'Untitled listing'}</h3>
                                  <p className="editorial-meta">
                                    EST. {money(item.estimatedValue)} · {String(item.brand || 'Unknown').toUpperCase()} · {String(item.condition || 'Unknown').toUpperCase()} · {String(item.city || 'Unknown').toUpperCase()}
                                  </p>
                                </div>
                              </div>
                              <div className="market-magazine-media-row">
                                <div className="market-magazine-image-wrap">
                                  {heroGallery.length > 1 ? (
                                    <div className="market-magazine-image-grid" role="img" aria-label={`${item.title || 'Listing'} images`}>
                                      {heroGallery.map((src, idx) => (
                                        <img key={`${item.id}-hero-${idx}`} src={src} alt={`${item.title || 'Listing'} image ${idx + 1}`} />
                                      ))}
                                    </div>
                                  ) : hero ? (
                                    <img src={hero} alt={item.title || 'Listing'} />
                                  ) : (
                                    <div className="listing-image-fallback">Image unavailable</div>
                                  )}
                                </div>
                                <div className="market-magazine-matches">
                                  <button
                                    className="editorial-match-btn"
                                    type="button"
                                    onClick={() => openMarketMatches(item)}
                                    disabled={own}
                                  >
                                    {own ? 'YOUR LISTING' : 'MATCHES'}
                                  </button>
                                  <div className="market-magazine-match-strip">
                                    {!own && matchPreviewListings.length > 0 ? (
                                      matchPreviewListings.slice(0, 3).map(({ candidate, thumb }, idx) => (
                                        <button
                                        key={`${item.id}-market-match-${idx}`}
                                        type="button"
                                        className="match-thumb-btn"
                                        onClick={() => openMarketMatches(item)}
                                        title="Open matches workflow"
                                      >
                                        <img src={thumb} alt={candidate?.title || 'Matched item'} className="market-magazine-match-thumb" />
                                      </button>
                                      ))
                                    ) : (
                                      <span className="match-thumb-empty">{own ? 'N/A' : 'NO MATCHES'}</span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </article>
                        )
                      })()}
                    </div>
                    <button className="market-magazine-nav" type="button" onClick={flipMarketplaceMagazineNext} aria-label="Next listing page">&#8250;</button>
                    <div className="market-magazine-meta">
                      <span>PAGE {marketMagazineIndex + 1} / {filteredListings.length}</span>
                    </div>
                  </div>
                ) : (
                  <div className="listing-grid market-listing-grid market-editorial-grid">
                    {filteredListings.map((item) => {
                      const baseValue = Number(item.estimatedValue || 0)
                      const similarMatches = Array.isArray(item.matches) ? item.matches : []
                      const matchPreviewListings = similarMatches
                        .map((candidate) => ({ candidate, thumb: getListingGallery(candidate)[0] }))
                        .filter((entry) => Boolean(entry.thumb))
                      const myTradeCandidates = myListings
                        .filter((mine) => String(mine.status || '').toLowerCase() === 'active')
                        .filter((mine) => Math.abs(Number(mine.estimatedValue || 0) - baseValue) <= Math.max(50, baseValue * 0.3))
                      return (
                        <ListingCard
                          key={item.id}
                          item={item}
                          marketplaceCompact
                          onOpenTrade={openTradeComposer}
                          myTradeCandidates={myTradeCandidates}
                          onOpenMatches={openMarketMatches}
                          matchPreviewImages={matchPreviewListings.map((entry) => entry.thumb)}
                          onOpenMagazinePage={openMarketplaceMagazine}
                        />
                      )
                    })}
                  </div>
                )}
              </div>
            </section>
          )}

          {activeTab === 'market_new' && (
            <section className="panel">
              <div className="panel-header">
                <div><p className="eyebrow">New Marketplace</p><h2>Magazine page-flip experience for comparison</h2></div>
                <div className="market-controls"><input value={marketSearch} onChange={(e) => setMarketSearch(e.target.value)} placeholder="Search brand, category, city, style..." /><label className="toggle"><input type="checkbox" checked={tradeOnly} onChange={(e) => setTradeOnly(e.target.checked)} /><span>Trade only</span></label></div>
              </div>
              {filteredListings.length === 0 ? (
                <div className="empty-state">
                  <h3>No listings match this filter</h3>
                  <p>Try broadening your search terms or turn off trade-only mode.</p>
                </div>
              ) : (
                <div className="market-magazine-shell">
                  <button className="market-magazine-nav" type="button" onClick={flipNewMarketplacePrev} aria-label="Previous listing page">&#8249;</button>
                  <div className="market-magazine-viewport">
                    <div className="market-magazine-stack" aria-hidden="true">
                      <span />
                      <span />
                    </div>
                    {(() => {
                      const item = filteredListings[newMarketIndex]
                      const similarMatches = Array.isArray(item.matches) ? item.matches : []
                      const matchPreviewImages = similarMatches
                        .map((candidate) => getListingGallery(candidate)[0])
                        .filter(Boolean)
                      const heroGallery = getListingGallery(item)
                      const hero = heroGallery[0]
                      const own = String(item.owner || '').trim().toLowerCase() === String(session?.name || '').trim().toLowerCase()
                      return (
                        <article className={`market-magazine-page ${newMarketIsFlipping ? `is-flipping ${newMarketFlipDir}` : ''}`} key={`new-market-page-${item.id}-${newMarketIndex}`}>
                          <div className="market-magazine-feature">
                            <div className="market-magazine-top">
                              <div className="market-magazine-copy">
                                <p className="eyebrow">Marketplace</p>
                                <h3 className="editorial-title">{item.title || 'Untitled listing'}</h3>
                                <p className="editorial-meta">
                                  EST. {money(item.estimatedValue)} · {String(item.brand || 'Unknown').toUpperCase()} · {String(item.condition || 'Unknown').toUpperCase()} · {String(item.city || 'Unknown').toUpperCase()}
                                </p>
                              </div>
                            </div>
                            <div className="market-magazine-media-row">
                              <div className="market-magazine-image-wrap">
                                {heroGallery.length > 1 ? (
                                  <div className="market-magazine-image-grid" role="img" aria-label={`${item.title || 'Listing'} images`}>
                                    {heroGallery.map((src, idx) => (
                                      <img key={`${item.id}-hero-${idx}`} src={src} alt={`${item.title || 'Listing'} image ${idx + 1}`} />
                                    ))}
                                  </div>
                                ) : hero ? (
                                  <img src={hero} alt={item.title || 'Listing'} />
                                ) : (
                                  <div className="listing-image-fallback">Image unavailable</div>
                                )}
                              </div>
                              <div className="market-magazine-matches">
                                <button
                                  className="editorial-match-btn"
                                  type="button"
                                  onClick={() => openMarketMatches(item)}
                                  disabled={own}
                                >
                                  {own ? 'YOUR LISTING' : 'MATCHES'}
                                </button>
                                <div className="market-magazine-match-strip">
                                  {!own && matchPreviewListings.length > 0 ? (
                                    matchPreviewListings.slice(0, 3).map(({ candidate, thumb }, idx) => (
                                      <button
                                        key={`${item.id}-new-market-match-${idx}`}
                                        type="button"
                                        className="match-thumb-btn"
                                        onClick={() => openMarketMatches(item)}
                                        title="Open matches workflow"
                                      >
                                        <img src={thumb} alt={candidate?.title || 'Matched item'} className="market-magazine-match-thumb" />
                                      </button>
                                    ))
                                  ) : (
                                    <span className="match-thumb-empty">{own ? 'N/A' : 'NO MATCHES'}</span>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        </article>
                      )
                    })()}
                  </div>
                  <button className="market-magazine-nav" type="button" onClick={flipNewMarketplaceNext} aria-label="Next listing page">&#8250;</button>
                  <div className="market-magazine-meta">
                    <span>PAGE {newMarketIndex + 1} / {filteredListings.length}</span>
                  </div>
                </div>
              )}
            </section>
          )}

          {activeTab === 'trade' && (
            <section className="panel trade-page trade-editorial">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Trade Offer</p>
                  <h2>{tradeComposerTarget ? 'Build and send your offer' : 'Select a target listing first'}</h2>
                </div>
                <div className="header-actions">
                  <button className="ghost" type="button" onClick={() => setActiveTab('market')}>Back to Marketplace</button>
                </div>
              </div>
              {!tradeComposerTarget ? (
                <div className="empty-state">
                  <h3>No target selected</h3>
                  <p>Open Marketplace and click Start Trade on a listing to begin.</p>
                  <button className="primary" type="button" onClick={() => setActiveTab('market')}>Go to Marketplace</button>
                </div>
              ) : (
                <>
                <div className="trade-editorial-banner">
                  <div>
                    <p className="eyebrow">Curated Exchange</p>
                    <h3>Compose a value-aligned offer</h3>
                  </div>
                  <p>
                    {tradeComposerTarget.brand || 'Unknown brand'} • {tradeComposerTarget.condition || 'Unknown condition'} • {tradeComposerTarget.city || 'Unknown city'}
                  </p>
                </div>
                <div className="trade-page-grid trade-page-grid-editorial">
                  <article className="trade-page-card trade-target-card">
                    <p className="eyebrow">Target Listing</p>
                    {getListingGallery(tradeComposerTarget)[0] ? (
                      <img
                        src={getListingGallery(tradeComposerTarget)[0]}
                        alt={tradeComposerTarget.title || 'Target listing'}
                        className="trade-target-image"
                      />
                    ) : null}
                    <h3>{tradeComposerTarget.title}</h3>
                    <p className="tiny-note">{tradeComposerTarget.brand || 'Unknown brand'} • {tradeComposerTarget.condition || 'Unknown condition'} • {tradeComposerTarget.city || 'Unknown city'}</p>
                    <div className="value-chip">{money(tradeComposerTarget.estimatedValue)}</div>
                    <div className="button-row trade-target-actions">
                      <button className="ghost small" type="button" onClick={() => setTradeDetailListing(tradeComposerTarget)}>View details</button>
                    </div>
                  </article>

                  <article className="trade-page-card trade-offer-card">
                    <p className="eyebrow">Your Listings To Offer</p>
                    <div className="trade-offer-list trade-offer-list-editorial">
                      {tradeOfferCandidates.map((x) => {
                        const checked = tradeOfferListingIds.includes(x.id)
                        const thumb = getListingGallery(x)[0] || null
                        return (
                          <div key={x.id} className="trade-offer-row">
                            <input type="checkbox" className="trade-offer-checkbox" checked={checked} onChange={(e) => setTradeOfferListingIds((prev) => (e.target.checked ? [...prev, x.id] : prev.filter((id) => id !== x.id)))} />
                            {thumb ? (
                              <img src={thumb} alt={x.title || 'Listing'} className="trade-offer-thumb" />
                            ) : (
                              <div className="trade-offer-thumb trade-offer-thumb-empty">No image</div>
                            )}
                            <span className="trade-offer-row-text">
                              <strong>{x.title}</strong>
                              <small>{money(x.estimatedValue)}</small>
                            </span>
                          </div>
                        )
                      })}
                      {tradeOfferCandidates.length === 0 && (
                        <p className="tiny-note trade-empty-note">
                          No eligible listings found. Offer candidates must match brand and be within price band.
                        </p>
                      )}
                    </div>
                    <div className="trade-offer-metrics">
                      <p className="tiny-note trade-metric-line">
                        Offered total: {money(offeredTotalValue)} • Target: {money(composerTargetValue)}
                      </p>
                    <p className={composerWithinBand ? 'ok-text trade-band-line' : 'error-text trade-band-line'}>
                      {composerGapPct === null ? 'Select target listing.' : (composerWithinBand ? 'Within 30% trade band' : 'Outside 30% trade band')}
                    </p>
                    </div>
                    <label className="trade-message-field">
                      <span>Message (optional)</span>
                      <textarea value={tradeOfferMessage} onChange={(e) => setTradeOfferMessage(e.target.value)} rows={4} placeholder="I’d like to trade with this item. Let me know what you think." />
                    </label>
                    {tradeOfferError ? <p className="error-text">{tradeOfferError}</p> : null}
                    <div className="button-row trade-offer-actions">
                      <button className="ghost" type="button" onClick={() => setActiveTab('market')}>Cancel</button>
                      <button className="primary" type="button" onClick={submitTradeOffer} disabled={tradeOfferBusy || !composerWithinBand}>
                        {tradeOfferBusy ? 'Sending...' : 'Send Trade Offer'}
                      </button>
                    </div>
                  </article>
                </div>
                </>
              )}
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
      )}

      {tradeDetailListing && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'grid', alignItems: 'start', justifyItems: 'center', zIndex: 1150, overflowY: 'auto', padding: '24px 12px' }}>
          <div style={{ width: 'min(640px, 92vw)', maxHeight: 'calc(100vh - 48px)', overflowY: 'auto', background: '#fff', borderRadius: 14, padding: 16, boxShadow: '0 24px 80px rgba(0,0,0,.25)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Item Details</h3>
              <button className="ghost small" type="button" onClick={() => setTradeDetailListing(null)}>Close</button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8, marginBottom: 12 }}>
              {(Array.isArray(tradeDetailListing.images) && tradeDetailListing.images.length > 0
                ? tradeDetailListing.images
                : [tradeDetailListing.image].filter(Boolean)
              ).map((url) => (
                <img
                  key={url}
                  src={url}
                  alt={tradeDetailListing.title || 'Listing image'}
                  style={{ width: '100%', height: 110, objectFit: 'cover', borderRadius: 10, border: '1px solid rgba(18,26,36,0.12)' }}
                />
              ))}
            </div>
            <div className="metric-grid">
              <div><span>Title</span><strong>{tradeDetailListing.title || 'n/a'}</strong></div>
              <div><span>Estimated value</span><strong>{money(tradeDetailListing.estimatedValue ?? tradeDetailListing.estimated_value)}</strong></div>
              <div><span>Brand</span><strong>{tradeDetailListing.brand || 'n/a'}</strong></div>
              <div><span>Category</span><strong>{tradeDetailListing.category || 'n/a'}</strong></div>
              <div><span>Condition</span><strong>{tradeDetailListing.condition || 'n/a'}</strong></div>
              <div><span>Status</span><strong>{tradeDetailListing.status || 'n/a'}</strong></div>
            </div>
            <p className="listing-notes" style={{ marginTop: 12 }}>{getListingDescription(tradeDetailListing) || 'No additional notes.'}</p>
          </div>
        </div>
      )}

      {marketMatchesTarget && (
        <div className="market-matches-backdrop" onClick={() => setMarketMatchesTargetId(null)}>
          <aside className={`market-matches-drawer ${similarListingsForTarget.length === 1 ? 'single-match' : ''}`} onClick={(e) => e.stopPropagation()}>
            <div className="market-matches-head">
              <div>
                <p className="eyebrow">Similar Matches</p>
                <h3>Matches for {marketMatchesTarget.title}</h3>
              </div>
              <button className="ghost small" type="button" onClick={() => setMarketMatchesTargetId(null)}>Close</button>
            </div>
            {similarListingsForTarget.length === 0 ? (
              <p className="tiny-note">No close value matches found right now.</p>
            ) : (
              <div className={`market-matches-grid ${similarListingsForTarget.length === 1 ? 'single' : ''}`}>
                {similarListingsForTarget.map((sim) => (
                  <article key={sim.id} className="market-match-card">
                    {(Array.isArray(sim.images) && sim.images.length > 0 ? sim.images[0] : sim.image) ? (
                      <img
                        src={(Array.isArray(sim.images) && sim.images.length > 0 ? sim.images[0] : sim.image)}
                        alt={sim.title || 'Matched item'}
                      />
                    ) : (
                      <div className="market-match-empty">No image</div>
                    )}
                    {similarListingsForTarget.length === 1 && Array.isArray(sim.images) && sim.images.length > 1 && (
                      <div className="market-match-gallery-row">
                        {sim.images.slice(1, 5).map((url, idx) => (
                          <img key={`${sim.id}-extra-${idx}`} src={url} alt="" />
                        ))}
                      </div>
                    )}
                    <div className="market-match-body">
                      <strong>{money(sim.estimatedValue)}</strong>
                      <p>{sim.title || 'Untitled item'}</p>
                      <small>{sim.brand || 'Unknown brand'} • {sim.condition || 'Unknown condition'} • {sim.city || 'Unknown city'}</small>
                      <div className="listing-actions">
                        <button className="ghost small" type="button" onClick={() => setTradeDetailListing(sim)}>View details</button>
                        <button
                          className="ghost small"
                          type="button"
                          onClick={() => {
                            const target = marketMatchesTarget
                            setMarketMatchesTargetId(null)
                            if (target) openTradeComposer(target, sim.id)
                          }}
                        >
                          Start Trade
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </aside>
        </div>
      )}

      {showCreateListingModal && (
        <div className="listing-modal-overlay">
          <div className="listing-modal-card">
            <div className="listing-modal-head">
              <h3>{listingModalMode === 'edit' ? 'Edit Draft' : 'Create Listing'}</h3>
              <button className="ghost small" type="button" onClick={() => setShowCreateListingModal(false)}>Close</button>
            </div>
            <p className="tiny-note listing-modal-note">
              {listingModalMode === 'edit'
                ? 'Edit mode: update images/condition, then continue to listing details.'
                : 'Step 1: Upload images and select condition.'}
            </p>
            {listingModalMode === 'edit' ? (
              <>
                <p className="listing-modal-label"><strong>Images (1-4)</strong></p>
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
                <div className="listing-modal-image-grid">
                  {modalPreviewUrls.map((url, idx) => (
                    <div key={url} className="listing-modal-thumb">
                      <img src={url} alt={`Upload ${idx + 1}`} />
                    </div>
                  ))}
                  {modalPreviewUrls.length < 4 && (
                    <label
                      htmlFor="edit-draft-image-input"
                      className="listing-modal-add-image"
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
            <label className="listing-modal-field">
              <span>Your condition assessment</span>
              <select value={userCondition} onChange={(e) => setUserCondition(e.target.value)} required>
                <option value="">Select condition</option>
                <option value="New">New</option>
                <option value="LikeNew">Like New</option>
              </select>
            </label>
            {listingModalMode === 'edit' && (
              <label>
                <span>Size</span>
                <select value={itemSize} onChange={(e) => setItemSize(e.target.value)}>
                  {(() => {
                    const categoryForSize = category || modalEditingListing?.analysis?.category || modalEditingListing?.category || ''
                    const options = sizeOptionsForCategory(categoryForSize)
                    return (
                      <>
                        <option value="">{options.length ? 'Select size' : 'Select category first'}</option>
                        {options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                      </>
                    )
                  })()}
                </select>
              </label>
            )}
            {listingModalMode === 'edit' && (
              <div className="warning-list listing-modal-warning">
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
              <div className="analysis-panels listing-modal-analysis">
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
              <div className="listing-modal-image-grid listing-modal-image-grid-top">
                {modalPreviewUrls.map((url, idx) => (
                  <div key={url} className="listing-modal-thumb">
                    <img src={url} alt={`Upload ${idx + 1}`} />
                  </div>
                ))}
              </div>
            )}
            <div className="button-row listing-modal-actions">
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

      {showStripePaymentModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'grid', placeItems: 'center', zIndex: 1100 }}>
          <div style={{ width: 'min(560px, 92vw)', background: '#fff', borderRadius: 14, padding: 18, boxShadow: '0 24px 80px rgba(0,0,0,.25)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <h3 style={{ margin: 0 }}>Add Payment Method</h3>
              <button className="ghost small" type="button" onClick={() => setShowStripePaymentModal(false)}>Close</button>
            </div>
            <p className="tiny-note" style={{ marginTop: 0 }}>
              Securely processed by Stripe. Your card data is never stored on this app.
            </p>
            <div id="stripe-payment-element" style={{ border: '1px solid var(--line)', borderRadius: 10, padding: 12, minHeight: 120 }} />
            {stripeUiError && <div className="tiny-note" style={{ color: '#b42318', marginTop: 8 }}>{stripeUiError}</div>}
            <div className="button-row" style={{ marginTop: 12 }}>
              <button
                className="primary"
                type="button"
                disabled={stripeUiBusy || !stripeUiReady}
                onClick={async () => {
                  try {
                    if (!stripeRef.current || !stripeElementsRef.current || !stripeUiReady) {
                      throw new Error(stripeUiError || 'Stripe payment form is still loading. Please wait a moment and try again.')
                    }
                    setStripeUiBusy(true)
                    setStripeUiError('')
                    const result = await stripeRef.current.confirmSetup({
                      elements: stripeElementsRef.current,
                      confirmParams: { return_url: window.location.href },
                      redirect: 'if_required',
                    })
                    if (result?.error) throw new Error(result.error.message || 'Failed to save payment method.')
                    const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
                    const methods = await syncStripePaymentMethodsRemote({
                      apiBaseUrl,
                      apiKey: clerkEnabled ? '' : apiKey.trim(),
                      bearerToken,
                    })
                    setPaymentMethods(methods)
                    setPaymentLoadError('')
                    setPaymentActionMsg('Payment method added.')
                    setProfileSaveMsg('Payment method added via Stripe.')
                    setShowStripePaymentModal(false)
                  } catch (err) {
                    setPaymentActionMsg('')
                    setPaymentLoadError(err?.message || 'Failed to sync payment methods.')
                    setStripeUiError(err.message || 'Failed to save payment method.')
                  } finally {
                    setStripeUiBusy(false)
                  }
                }}
              >
                {stripeUiBusy ? 'Saving…' : 'Save Payment Method'}
              </button>
              <button className="ghost small" type="button" onClick={() => setShowStripePaymentModal(false)} disabled={stripeUiBusy}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ListingCard({ item, own = false, onEditDraft = null, marketplaceCompact = false, onOpenTrade = null, myTradeCandidates = [], onOpenMatches = null, matchPreviewImages = [], editorialStyle = false, onOpenMagazinePage = null }) {
  const gallery = Array.isArray(item.images) && item.images.length > 0
    ? item.images
    : [item.image].filter(Boolean)
  const imageSrc = gallery[0] || null

  const statusLabel = item.status || 'Review'
  const statusClass = `status-${String(statusLabel).toLowerCase().replace(/\s+/g, '')}`
  const editDisabled = own && String(statusLabel).toLowerCase() === 'analyzing'
  const badgeLabel = item.status || 'Active'
  const badgeClass = `status-${String(badgeLabel).toLowerCase().replace(/\s+/g, '')}`
  const brandLabel = String(item.brand || '').trim() || 'Unknown brand'
  const conditionLabel = String(item.condition || '').trim() || 'Unknown condition'
  const cityLabel = String(item.city || '').trim() || 'Unknown city'
  const isEditorial = editorialStyle || (marketplaceCompact && !own)
  const isMagazineClickable = typeof onOpenMagazinePage === 'function'

  function openMagazinePage() {
    if (!isMagazineClickable) return
    onOpenMagazinePage(item)
  }

  function shareToFacebook(e) {
    e?.stopPropagation?.()
    if (typeof window === 'undefined') return
    const caption = buildListingShareCaption(item)
    const listingId = String(item?.listing_id || item?.id || '').trim()
    const base = API_DEFAULT.replace(/\/$/, '')
    const fallbackUrl = typeof window.location?.href === 'string' ? window.location.href : 'https://jouft.com'
    const shareUrl = listingId
      ? `${base}/v1/share/listings/${encodeURIComponent(listingId)}`
      : fallbackUrl
    const url = `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}&quote=${encodeURIComponent(caption)}`
    window.open(url, '_blank', 'noopener,noreferrer,width=640,height=640')
  }

  async function shareToInstagram(e) {
    e?.stopPropagation?.()
    const caption = buildListingShareCaption(item)
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(caption)
      }
    } catch {}
    if (typeof window !== 'undefined') {
      window.open('https://www.instagram.com/', '_blank', 'noopener,noreferrer')
      window.alert('Listing caption copied. Paste it into your Instagram post.')
    }
  }

  return (
    <>
      <article
        className={`listing-card ${isEditorial ? 'market-editorial' : ''} ${isMagazineClickable ? 'is-clickable' : ''}`}
        onClick={isMagazineClickable ? openMagazinePage : undefined}
        role={isMagazineClickable ? 'button' : undefined}
        tabIndex={isMagazineClickable ? 0 : undefined}
        onKeyDown={isMagazineClickable ? (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            openMagazinePage()
          }
        } : undefined}
      >
        <div className={`image-wrap ${gallery.length > 1 ? 'multi-images' : ''}`}>
        {gallery.length > 1 ? (
          <div className="listing-image-grid" role="img" aria-label={`${item.title || 'Listing'} images`}>
            {gallery.map((src, idx) => (
              <img key={`${item.id}-gallery-${idx}`} src={src} alt={`${item.title || 'Listing'} image ${idx + 1}`} />
            ))}
          </div>
        ) : imageSrc ? (
          <img src={imageSrc} alt={item.title} />
        ) : (
          <div className="listing-image-fallback" aria-label="No image available">
            Image unavailable
          </div>
        )}
        {own && !isEditorial && <span className={`mode-badge ${badgeClass}`}>{badgeLabel}</span>}
      </div>
      <div className="listing-body">
        {isEditorial ? (
          <>
            <h3 className="editorial-title">{item.title || 'Untitled listing'}</h3>
            <p className="editorial-byline">BY {String(item.owner || 'Unknown seller').toUpperCase()}</p>
            <p className="editorial-meta">
              EST. {money(item.estimatedValue)} · {brandLabel.toUpperCase()} · {conditionLabel.toUpperCase()} · {cityLabel.toUpperCase()}
            </p>
            <div className="listing-footer editorial-footer">
              <div className="listing-actions">
                {!own && (
                  <button
                    className="editorial-match-btn"
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onOpenMatches?.(item)
                    }}
                    title="View matched items from your closet"
                  >
                    <span>MATCHES</span>
                    <span className="match-thumb-strip" aria-hidden="true">
                      {matchPreviewImages.length > 0 ? (
                        matchPreviewImages.slice(0, 3).map((src, idx) => (
                          <img key={`${item.id}-match-${idx}`} src={src} alt="" className="match-thumb" />
                        ))
                      ) : (
                        <span className="match-thumb-empty">NO MATCHES</span>
                      )}
                    </span>
                  </button>
                )}
                {own && (
                  <div className="editorial-own-actions">
                    <button
                      className="editorial-match-btn"
                      type="button"
                      disabled={editDisabled}
                      title={editDisabled ? 'Cannot edit while analysis is running' : undefined}
                      onClick={(e) => {
                        e.stopPropagation()
                        if (!editDisabled) onEditDraft?.(item)
                      }}
                    >
                      <span>EDIT DRAFT</span>
                    </button>
                    <button className="editorial-match-btn" type="button" onClick={shareToFacebook}>
                      <span>SHARE FACEBOOK</span>
                    </button>
                    <button className="editorial-match-btn" type="button" onClick={shareToInstagram}>
                      <span>SHARE INSTAGRAM</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="listing-head">
              <h3>{item.title}</h3>
              <div className="value-chip">{money(item.estimatedValue)}</div>
            </div>
            <div className="listing-scan-row">
              <span>{brandLabel}</span>
              <span>{conditionLabel}</span>
              <span>{cityLabel}</span>
            </div>
            <p className="listing-notes listing-notes-clamp">{getListingDescription(item) || 'No description provided.'}</p>
            {!marketplaceCompact && <div className="tag-row">{(item.tags || []).slice(0, 4).map((tag) => <span key={tag}>{tag}</span>)}</div>}
            {(!marketplaceCompact || !own) && (
              <div className="listing-footer">
                <div className="listing-footer-meta">
                  <small>{own ? 'Your listing' : `Listed by ${item.owner}`}</small>
                </div>
                <div className="listing-actions">
                  {!own && (
                    <button
                      className="ghost small"
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        onOpenMatches?.(item)
                      }}
                      title="View matched items from your closet"
                    >
                      <span>Matches</span>
                      <span className="match-thumb-strip" aria-hidden="true">
                        {matchPreviewImages.length > 0 ? (
                          matchPreviewImages.slice(0, 3).map((src, idx) => (
                            <img key={`${item.id}-match-${idx}`} src={src} alt="" className="match-thumb" />
                          ))
                        ) : (
                          <span className="match-thumb-empty">No matches</span>
                        )}
                      </span>
                    </button>
                  )}
                  {own && (
                    <>
                      <button
                        className="ghost small"
                        type="button"
                        disabled={editDisabled}
                        title={editDisabled ? 'Cannot edit while analysis is running' : undefined}
                        onClick={(e) => {
                          e.stopPropagation()
                          if (!editDisabled) onEditDraft?.(item)
                        }}
                      >
                        Edit draft
                      </button>
                      <button className="ghost small" type="button" onClick={shareToFacebook}>Share Facebook</button>
                      <button className="ghost small" type="button" onClick={shareToInstagram}>Share Instagram</button>
                    </>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
      </article>
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
