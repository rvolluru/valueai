import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import {
  SignIn,
  SignUp,
  UserButton,
  useAuth,
  useClerk,
  useUser,
} from '@clerk/clerk-react'
import { FaFacebookF, FaPinterestP } from 'react-icons/fa'
import { FiBell, FiTrash2 } from 'react-icons/fi'
import { createWebApiClient } from './lib/apiClient'

const API_DEFAULT =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000')
const CLERK_ENABLED = Boolean(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY)
const IS_PROD = Boolean(import.meta.env.PROD)
const VALID_TABS = new Set(['market', 'portfolio', 'inbox', 'profile', 'profile_setup', 'admin', 'trade', 'edit_listing', 'review_listing'])
const TEMP_SHOW_PROFILE_QUESTIONNAIRE_ON_LOGIN = false
const LISTINGS_PAGE_SIZE = 24

function tabFromLocation() {
  if (typeof window === 'undefined') return 'market'
  const params = new URLSearchParams(window.location.search)
  const tab = String(params.get('tab') || '').trim().toLowerCase()
  return VALID_TABS.has(tab) ? tab : 'market'
}

function hasExplicitTabInLocation() {
  if (typeof window === 'undefined') return false
  const params = new URLSearchParams(window.location.search)
  const tab = String(params.get('tab') || '').trim().toLowerCase()
  return VALID_TABS.has(tab)
}

function tabHref(tab) {
  return `/?tab=${encodeURIComponent(tab)}`
}

function editListingHref(listingId) {
  return `/?tab=edit_listing&listing=${encodeURIComponent(listingId || '')}`
}

function reviewListingHref(listingId) {
  return `/?tab=review_listing&listing=${encodeURIComponent(listingId || '')}`
}

function marketListingHref(listingId) {
  return `/?tab=market&listing=${encodeURIComponent(listingId || '')}`
}

function listingIdFromLocation() {
  if (typeof window === 'undefined') return ''
  const params = new URLSearchParams(window.location.search)
  return String(params.get('listing') || '').trim()
}

function ownerFirstName(name, fallback = 'Member') {
  const value = String(name || '').trim()
  if (!value) return fallback
  const first = value.split(/\s+/).find(Boolean)
  return first || fallback
}

const seedListings = [
  {
    id: 'seed-1', owner: 'Mara', title: 'Louis Vuitton Neverfull MM Monogram Tote', mode: 'trade', category: 'handbag', brand: 'Louis Vuitton', condition: 'LikeNew', estimatedValue: 960, city: 'New York, NY', image: 'https://images.unsplash.com/photo-1584917865442-de89df76afd3?auto=format&fit=crop&w=800&q=80', wants: 'Designer tote or shoulder bag in the $850-$1,100 range', tags: ['authenticated', 'monogram', 'trade-only'],
  },
  {
    id: 'seed-2', owner: 'Eli', title: 'Nike Dunk Low Panda (US 10)', mode: 'trade', category: 'shoes', brand: 'Nike', condition: 'LikeNew', estimatedValue: 110, city: 'Austin, TX', image: 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=80', wants: 'Open to sneaker or streetwear trades', tags: ['sneakers', 'size-10', 'verified-receipt'],
  },
  {
    id: 'seed-3', owner: 'Nina', title: 'Burberry Nova Check Wool Scarf', mode: 'trade', category: 'clothes', brand: 'Burberry', condition: 'LikeNew', estimatedValue: 170, city: 'Seattle, WA', image: 'https://images.unsplash.com/photo-1520903920243-00d872a2d1c9?auto=format&fit=crop&w=800&q=80', wants: 'Trade for premium sneakers or a small leather good', tags: ['accessory', 'winter', 'trade'],
  },
  {
    id: 'seed-4', owner: 'Jordan', title: 'Coach Tabby Shoulder Bag 26', mode: 'trade', category: 'handbag', brand: 'Coach', condition: 'LikeNew', estimatedValue: 280, city: 'Chicago, IL', image: 'https://images.unsplash.com/photo-1594223274512-ad4803739b7c?auto=format&fit=crop&w=800&q=80', wants: 'Open to equal-value trade', tags: ['shoulder-bag', 'neutral', 'modern'],
  },
]

function money(value) {
  if (value == null || Number.isNaN(Number(value))) return 'N/A'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(Number(value))
}

function normalizeMode() {
  return 'Trade'
}

function confidenceLabel(value) {
  if (value == null) return 'n/a'
  return `${Math.round(value * 100)}%`
}

function VisualConditionDebug({ assessment }) {
  if (!assessment || typeof assessment !== 'object') return null
  const evidence = Array.isArray(assessment.evidence)
    ? assessment.evidence.filter((entry) => typeof entry === 'string' && entry.trim())
    : []
  const fields = [
    ['Wear level', assessment.wear_level],
    ['Box included', assessment.box_included],
    ['Dust bag', assessment.dust_bag_included],
    ['New-in-box signal', assessment.new_in_box_signal],
    ['Pricing tier', assessment.pricing_tier],
    ['Confidence', assessment.confidence == null ? null : confidenceLabel(assessment.confidence)],
  ].filter(([, value]) => value != null && String(value).trim())
  if (fields.length === 0 && evidence.length === 0) return null
  return (
    <div className="visual-condition-debug">
      <p className="eyebrow">Visual Condition Assessment</p>
      {fields.length > 0 && (
        <div className="metric-grid visual-condition-grid">
          {fields.map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{String(value).includes('_') ? titleCase(String(value).replace(/_/g, ' ')) : String(value)}</strong>
            </div>
          ))}
        </div>
      )}
      {evidence.length > 0 && (
        <div className="visual-condition-evidence">
          <span>Evidence</span>
          <ul>
            {evidence.slice(0, 8).map((entry, idx) => (
              <li key={`${entry}-${idx}`}>{entry}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function makeId(prefix) {
  const cryptoApi = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return `${prefix}-${cryptoApi.randomUUID()}`
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function listingRecordId(listing) {
  return String(listing?.listing_id || listing?.id || '').trim()
}

function offerParticipantName(offer, role = 'from') {
  const direct = String(role === 'to' ? offer?.to_name || '' : offer?.from_name || '').trim()
  if (direct && !direct.toLowerCase().startsWith('user_')) return direct.split(/\s+/)[0]
  const subject = String(role === 'to' ? offer?.to_subject || '' : offer?.from_subject || '').trim()
  return subject && !subject.toLowerCase().startsWith('user_') ? subject.split(/\s+/)[0] : 'Member'
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

function isCompleteShippingAddress(address) {
  return Boolean(
    String(address?.full_name || '').trim()
    && String(address?.address_line1 || '').trim()
    && String(address?.city || '').trim()
    && String(address?.state || '').trim()
    && String(address?.postal_code || '').trim()
    && String(address?.country || '').trim()
  )
}

function completeShippingAddresses(addresses) {
  return (Array.isArray(addresses) ? addresses : []).filter(isCompleteShippingAddress)
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

function isGenericTradeNote(value) {
  const normalized = String(value || '').trim().toLowerCase().replace(/[.!\s]+$/g, '')
  return normalized === 'open to similar-value offers'
    || normalized === 'open to similar value offers'
    || normalized === 'no description provided'
}

function meaningfulDescription(value) {
  const text = String(value || '').trim()
  return text && !isGenericTradeNote(text) ? text : ''
}

function cleanupParagraphBreaks(value) {
  return String(value || '')
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => line.trim())
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function sentenceChunks(value) {
  return String(value || '')
    .match(/[^.!?]+[.!?]+(?:["')\]]+)?|[^.!?]+$/g)
    ?.map((sentence) => sentence.trim())
    .filter(Boolean) || []
}

function splitCommaDetails(value) {
  const normalized = String(value || '').replace(/\s+/g, ' ').trim()
  if (normalized.length < 140) return [normalized].filter(Boolean)
  const parts = normalized
    .split(/,\s+(?=(?:and\s+)?(?:a|an|the|small|large|stacked|single|double|gold|silver|black|white|beige|brown|red|blue|green|pink|leather|canvas|suede|wool|cotton|silk|chain|logo|hardware|strap|heel|toe|zip|pocket|closure|handle|shoulder|silhouette)\b)/i)
    .map((part) => part.trim())
    .filter(Boolean)
  if (parts.length < 3) return [normalized]
  const grouped = []
  for (let i = 0; i < parts.length; i += 2) grouped.push(parts.slice(i, i + 2).join(', '))
  return grouped
}

function organizeDescriptionParagraphs(value) {
  const existing = cleanupParagraphBreaks(value)
  if (!existing) return ''

  const normalized = existing.replace(/\s*\n\s*/g, ' ').replace(/\s+/g, ' ').trim()
  const paragraphs = []
  const labeledPattern = /\b(Key details|Condition|Wear|Flaws|Measurements|Size|Material|Materials|Color|Hardware|Authenticity|Notes|Trade notes):/gi
  const labeledMatches = [...normalized.matchAll(labeledPattern)]

  if (labeledMatches.length > 0) {
    const firstLabel = labeledMatches[0]
    const intro = normalized.slice(0, firstLabel.index).trim()
    if (intro) paragraphs.push(...sentenceChunks(intro).slice(0, 2))

    labeledMatches.forEach((match, index) => {
      const start = match.index
      const end = index + 1 < labeledMatches.length ? labeledMatches[index + 1].index : normalized.length
      const section = normalized.slice(start, end).trim()
      if (!section) return
      const [labelPart, ...bodyParts] = section.split(':')
      const label = labelPart.trim()
      const body = bodyParts.join(':').trim()
      if (!body) {
        paragraphs.push(section)
        return
      }
      const bodySentences = sentenceChunks(body)
      if (label.toLowerCase() === 'key details' && bodySentences.length <= 1) {
        const detailParagraphs = splitCommaDetails(body)
        paragraphs.push(`${label}: ${detailParagraphs.shift()}`)
        paragraphs.push(...detailParagraphs)
        return
      }
      paragraphs.push(`${label}: ${bodySentences.shift() || body}`)
      paragraphs.push(...bodySentences)
    })
  } else {
    const sentences = sentenceChunks(normalized)
    if (sentences.length <= 2) return normalized
    paragraphs.push(sentences.shift())
    while (sentences.length > 0) paragraphs.push(sentences.splice(0, 2).join(' '))
  }

  return cleanupParagraphBreaks(paragraphs.filter(Boolean).join('\n\n'))
}

function getListingDescription(item) {
  if (!item) return ''
  const profile = item.analysis?.item_profile
  const suggested = buildSuggestedDescriptionFromProfile(profile)
  if (suggested) return suggested
  const description = meaningfulDescription(item.description)
  if (description) return description
  const wants = meaningfulDescription(item.wants)
  if (wants) return wants
  return ''
}

function ListingDescriptionParagraphs({ item, fallback = 'No description provided.', className = 'listing-description-paragraphs' }) {
  const description = organizeDescriptionParagraphs(getListingDescription(item))
  if (!description) return <p className="listing-notes">{fallback}</p>
  return (
    <div className={className}>
      {description.split(/\n{2,}/).map((paragraph, idx) => (
        <p key={`${item?.id || item?.listing_id || 'listing'}-description-${idx}`} className="listing-notes">
          {paragraph}
        </p>
      ))}
    </div>
  )
}

function getListingGallery(item) {
  if (!item) return []
  const raw = Array.isArray(item.listedImages) && item.listedImages.length > 0
    ? item.listedImages.map((entry) => entry?.d_img || entry?.display_image || entry?.image)
    : Array.isArray(item.images) && item.images.length > 0 ? item.images : [item.image]
  const seen = new Set()
  return raw.filter((src) => {
    const value = typeof src === 'string' ? src.trim() : ''
    if (!value || seen.has(value)) return false
    seen.add(value)
    return true
  })
}

function missingPublishFields(listing) {
  const missing = []
  const gallery = getListingGallery(listing)
  const title = String(listing?.title || '').trim()
  const category = String(listing?.category || '').trim().toLowerCase()
  const brand = String(listing?.brand || '').trim()
  const condition = String(listing?.condition || '').trim()
  const value = Number(listing?.estimatedValue || 0)
  const size = String(listing?.size || '').trim()
  const validCategories = new Set(['clothes', 'shoes', 'handbag'])
  const validConditions = new Set(['NewWithTags', 'New', 'LikeNew'])

  if (gallery.length < 1) missing.push('photos')
  if (!title || title.toLowerCase() === 'new listing' || title.toLowerCase() === 'untitled listing') missing.push('title')
  if (!validCategories.has(category)) missing.push('category')
  if (!brand || ['unknown', 'analyzing...', 'n/a'].includes(brand.toLowerCase())) missing.push('brand')
  if (!validConditions.has(condition)) missing.push('condition')
  if (!Number.isFinite(value) || value <= 0) missing.push('AI estimated value')
  if ((category === 'clothes' || category === 'shoes') && !size) missing.push('size')
  return missing
}

function missingPublishFieldsMessage(listing) {
  const missing = missingPublishFields(listing)
  if (missing.length < 1) return ''
  return `Listing missing fields: ${missing.join(', ')}. Please edit the listing and add the missing information before publishing.`
}

function getUploadedImageUrlsFromAnalysis(analysis) {
  if (!analysis || !Array.isArray(analysis.uploaded_images)) return []
  return analysis.uploaded_images
    .map((u) => (typeof u?.image_url === 'string' ? u.image_url.trim() : ''))
    .filter(isPersistableImageUrl)
}

function isPersistableImageUrl(value) {
  if (typeof value !== 'string') return false
  const trimmed = value.trim()
  return /^https?:\/\//i.test(trimmed) || trimmed.startsWith('/')
}

function persistableImageUrls(values) {
  const list = Array.isArray(values) ? values : [values]
  return Array.from(new Set(list.map((value) => (typeof value === 'string' ? value.trim() : '')).filter(isPersistableImageUrl)))
}

function shouldRenderListingImageAsBlob(value) {
  if (typeof value !== 'string') return false
  const trimmed = value.trim()
  if (!trimmed) return false
  if (trimmed.startsWith('/v1/images/')) return true
  try {
    return new URL(trimmed, typeof window !== 'undefined' ? window.location.origin : 'http://localhost').pathname.startsWith('/v1/images/')
  } catch {
    return false
  }
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function fetchListingImageBlobUrl(src, signal) {
  let lastError = null
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    try {
      const resp = await fetch(src, { signal, cache: 'force-cache' })
      if (!resp.ok) throw new Error(`Image request failed with ${resp.status}`)
      const blob = await resp.blob()
      if (!blob || blob.size < 1) throw new Error('Image response was empty.')
      return URL.createObjectURL(blob)
    } catch (err) {
      if (err?.name === 'AbortError') throw err
      lastError = err
      await wait(250 * (attempt + 1))
    }
  }
  throw lastError || new Error('Image request failed.')
}

function sameStringList(left, right) {
  const a = Array.isArray(left) ? left.map((value) => String(value || '').trim()) : []
  const b = Array.isArray(right) ? right.map((value) => String(value || '').trim()) : []
  if (a.length !== b.length) return false
  return a.every((value, index) => value === b[index])
}

function displayConditionLabel(input) {
  const normalized = String(input || '').replace(/[-_\s]+/g, '').toLowerCase()
  if (normalized === 'newwithtags' || normalized === 'nwt') return 'New with Tags'
  if (normalized === 'likenew') return 'Like New'
  return String(input || 'Unknown condition').trim() || 'Unknown condition'
}

function shipmentTrackingLabel(shipment) {
  const raw = String(shipment?.tracking_status || shipment?.status || '').trim().toLowerCase()
  const labels = {
    label_created: 'Label created',
    pre_transit: 'Label created',
    shipped: 'In transit',
    transit: 'In transit',
    out_for_delivery: 'Out for delivery',
    delivered: 'Delivered',
    returned: 'Returned',
    exception: 'Delivery exception',
  }
  return labels[raw] || (raw ? raw.replace(/_/g, ' ') : 'Tracking pending')
}

function buildListingShareCaption(item) {
  const title = String(item?.title || 'Listing').trim()
  const brand = String(item?.brand || 'Unknown brand').trim()
  const condition = displayConditionLabel(item?.condition)
  const value = money(item?.estimatedValue)
  const description = getListingDescription(item)
  const imageLinks = getListingGallery(item).slice(0, 3)
  const imageLine = imageLinks.length > 0 ? ` Images: ${imageLinks.join(' ')}` : ''
  return `${title} | ${brand} | ${condition} | Est. ${value}. ${description}${imageLine} #Jouft #FashionExchange`
}

function sizeOptionsForCategory(category) {
  if (category === 'shoes') return ['US 5', 'US 5.5', 'US 6', 'US 6.5', 'US 7', 'US 7.5', 'US 8', 'US 8.5', 'US 9', 'US 9.5', 'US 10', 'US 10.5', 'US 11', 'US 12']
  if (category === 'clothes') return APPAREL_SIZE_OPTIONS
  if (category === 'handbag') return ['Mini', 'Small', 'Medium', 'Large']
  return []
}

const US_NUMERIC_APPAREL_SIZE_OPTIONS = ['00', '0', '2', '4', '6', '8', '10', '12', '14', '16', '18', '20', '22', '24']
const FEMALE_ALPHA_APPAREL_SIZE_OPTIONS = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL']
const MALE_ALPHA_APPAREL_SIZE_OPTIONS = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
const FEMALE_APPAREL_SIZE_OPTIONS = [...FEMALE_ALPHA_APPAREL_SIZE_OPTIONS, ...US_NUMERIC_APPAREL_SIZE_OPTIONS]
const MALE_APPAREL_SIZE_OPTIONS = [...MALE_ALPHA_APPAREL_SIZE_OPTIONS, ...US_NUMERIC_APPAREL_SIZE_OPTIONS]
const APPAREL_SIZE_OPTIONS = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', ...US_NUMERIC_APPAREL_SIZE_OPTIONS]
const FEMALE_SHOE_SIZE_OPTIONS = ['US 5', 'US 5.5', 'US 6', 'US 6.5', 'US 7', 'US 7.5', 'US 8', 'US 8.5', 'US 9', 'US 9.5', 'US 10', 'US 10.5', 'US 11', 'US 12']
const MALE_SHOE_SIZE_OPTIONS = ['US 6', 'US 6.5', 'US 7', 'US 7.5', 'US 8', 'US 8.5', 'US 9', 'US 9.5', 'US 10', 'US 10.5', 'US 11', 'US 11.5', 'US 12', 'US 13', 'US 14']
const PROFILE_CATEGORY_OPTIONS = ['Dresses', 'Jackets', 'Shoes', 'Handbags', 'Skirts', 'Accessories']
const STYLE_DESCRIPTOR_OPTIONS = [
  { value: 'Classic', className: 'classic', description: 'Tailored staples, polish, refined neutrals' },
  { value: 'Trendy', className: 'trendy', description: 'Current silhouettes, bold accents, high rotation' },
  { value: 'Unique', className: 'unique', description: 'Statement finds, unexpected texture, rare details' },
]
const JOUFT_GOAL_OPTIONS = [
  'Refresh My Closet',
  'Trade Unworn Pieces',
  'Discover Rare Finds',
  'Access Luxury Fashion',
  'Build My Collection',
  'Sustainable Fashion',
  'Connect With Fashion Enthusiasts',
  'Trade Instead of Sell',
]
const PROFILE_SETUP_TOTAL_STEPS = 5
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

function subscriptionPlanIdForApi(plan) {
  const normalized = normalizeSubscriptionPlanId(plan)
  if (normalized === 'starter') return 'starter_15'
  if (normalized === 'pro') return 'pro_25'
  return 'free'
}

function normalizeSelectableSubscriptionPlanId(plan) {
  const normalized = normalizeSubscriptionPlanId(plan)
  return SUBSCRIPTION_PLANS.some((entry) => entry.id === normalized)
    ? normalized
    : 'free'
}

function normalizeBillingCycle(cycle) {
  return String(cycle || '').toLowerCase() === 'annual' ? 'annual' : 'monthly'
}

function titleCase(input) {
  return String(input || '')
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(' ')
}

function resolveSignupFullName(session, profileData) {
  const profileParts = [profileData?.firstName, profileData?.lastName]
    .map((part) => (typeof part === 'string' ? part.trim() : ''))
    .filter(Boolean)
  if (profileParts.length > 0) return profileParts.join(' ')
  const profileName = typeof profileData?.name === 'string' ? profileData.name.trim() : ''
  if (profileName) return profileName
  return typeof session?.name === 'string' ? session.name.trim() : ''
}

function isProfileSetupRequired(profile) {
  const firstName = String(profile?.first_name || profile?.firstName || '').trim()
  const lastName = String(profile?.last_name || profile?.lastName || '').trim()
  const email = String(profile?.email || '').trim()
  const gender = String(profile?.gender || '').trim()
  const birthday = String(profile?.birthday || '').trim()
  const addresses = completeShippingAddresses(normalizeShippingAddresses(profile?.shipping_addresses, profile))
  const hasSizes = normalizeMultiSizeValue(profile?.tops_size).length > 0
    || normalizeMultiSizeValue(profile?.dresses_size).length > 0
    || normalizeMultiSizeValue(profile?.bottoms_size).length > 0
    || normalizeMultiSizeValue(profile?.shoes_size).length > 0
  const hasStyle = Array.isArray(profile?.style_descriptors) && profile.style_descriptors.length > 0
  const hasGoal = Array.isArray(profile?.jouft_goals) && profile.jouft_goals.length > 0
  const plan = normalizeSubscriptionPlanId(profile?.subscription_plan)
  const status = String(profile?.subscription_status || '').trim().toLowerCase()
  const hasSubscription = plan === 'free' || ['active', 'trialing'].includes(status)
  return !firstName || !lastName || !email || !gender || !birthday || addresses.length === 0 || !hasSizes || !hasStyle || !hasGoal || !hasSubscription
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

const UPLOAD_MAX_DIMENSION = 1600
const UPLOAD_JPEG_QUALITY = 0.82

function uploadBaseName(name, index) {
  const fallback = `upload-${index + 1}`
  const cleanName = String(name || fallback)
  const dotIndex = cleanName.lastIndexOf('.')
  return dotIndex > 0 ? cleanName.slice(0, dotIndex) : cleanName
}

async function sha256Hex(blob) {
  if (!window.crypto?.subtle) return null
  const buffer = await blob.arrayBuffer()
  const digest = await window.crypto.subtle.digest('SHA-256', buffer)
  return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

async function resizeImageForUpload(file, index) {
  const sourceType = file?.type || 'image/jpeg'
  if (!sourceType.startsWith('image/')) return file
  let bitmap
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    bitmap = await createImageBitmap(file)
  }
  const scale = Math.min(1, UPLOAD_MAX_DIMENSION / Math.max(bitmap.width, bitmap.height))
  const width = Math.max(1, Math.round(bitmap.width * scale))
  const height = Math.max(1, Math.round(bitmap.height * scale))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  context.drawImage(bitmap, 0, 0, width, height)
  if (typeof bitmap.close === 'function') bitmap.close()
  const blob = await new Promise((resolve, reject) => {
    canvas.toBlob((nextBlob) => {
      if (nextBlob) resolve(nextBlob)
      else reject(new Error('Could not prepare image for upload'))
    }, 'image/jpeg', UPLOAD_JPEG_QUALITY)
  })
  return new File([blob], `${uploadBaseName(file?.name, index)}.jpg`, {
    type: 'image/jpeg',
    lastModified: Date.now(),
  })
}

async function prepareImagesForUpload(images) {
  return Promise.all((images || []).map(async (file, index) => {
    const preparedFile = await resizeImageForUpload(file, index)
    return {
      file: preparedFile,
      filename: preparedFile.name || `upload-${index + 1}.jpg`,
      contentType: preparedFile.type || 'image/jpeg',
      contentLength: preparedFile.size,
      contentHash: await sha256Hex(preparedFile),
    }
  }))
}

async function analyzeItem({ apiBaseUrl, apiKey, bearerToken, images, category, userCondition, itemDescription, itemSize, debug }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.analyzeItem(
    {
      images: (images || []).map((file) => ({ file })),
      category,
      userCondition,
      itemDescription,
      itemSize,
      debug,
    },
    authContext(bearerToken),
  )
}

async function uploadListingImages({ apiBaseUrl, apiKey, bearerToken, images }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  let prepared
  try {
    prepared = await prepareImagesForUpload(images || [])
  } catch (err) {
    console.warn('Client image preparation failed; falling back to original upload.', err)
    prepared = (images || []).map((file, index) => ({
      file,
      filename: file?.name || `upload-${index + 1}.jpg`,
      contentType: file?.type || 'image/jpeg',
      contentLength: file?.size || null,
      contentHash: null,
    }))
  }
  const auth = authContext(bearerToken)
  try {
    const presigned = await client.createImageUploadSlots(
      {
        images: prepared.map((entry) => ({
          filename: entry.filename,
          contentType: entry.contentType,
          contentLength: entry.contentLength,
        })),
      },
      auth,
    )
    const slots = presigned?.upload_slots || []
    if (slots.length !== prepared.length) throw new Error('Upload slot count did not match selected images.')
    await Promise.all(slots.map(async (slot, index) => {
      const resp = await fetch(slot.upload_url, {
        method: slot.method || 'PUT',
        headers: slot.headers || { 'Content-Type': prepared[index].contentType },
        body: prepared[index].file,
      })
      if (!resp.ok) throw new Error(`Direct image upload failed (${resp.status})`)
    }))
    return client.confirmImageUploads(
      {
        itemId: presigned.item_id,
        uploadedImages: slots.map((slot, index) => ({
          image_id: slot.image_id,
          filename: prepared[index].filename,
          content_type: prepared[index].contentType,
          storage_uri: slot.storage_uri,
          role_hint: slot.role_hint,
          content_hash: prepared[index].contentHash,
        })),
      },
      auth,
    )
  } catch (err) {
    console.warn('Direct image upload failed; falling back to API upload.', err)
    return client.uploadImages(
      { images: prepared.map((entry) => ({ file: entry.file })) },
      auth,
    )
  }
}

async function queueListingAnalysisJob({ apiBaseUrl, apiKey, bearerToken, listingId, images, category, userCondition, itemDescription, itemSize, debug }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.queueListingAnalysis(
    {
      listingId,
      images: (images || []).map((file) => ({ file })),
      category,
      userCondition,
      itemDescription,
      itemSize,
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

async function fetchMyListings({ apiBaseUrl, apiKey, bearerToken, limit = 100, offset = 0 }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  const payload = await client.listMyListings(limit, authContext(bearerToken), { offset })
  return {
    items: payload?.items || [],
    hasMore: Boolean(payload?.has_more),
    nextOffset: Number.isFinite(Number(payload?.next_offset)) ? Number(payload.next_offset) : null,
  }
}

async function fetchMarketplaceListings({ apiBaseUrl, apiKey, bearerToken, limit = 50, offset = 0 }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  const payload = await client.listMarketplace(limit, authContext(bearerToken), { offset })
  return {
    items: payload?.items || [],
    hasMore: Boolean(payload?.has_more),
    nextOffset: Number.isFinite(Number(payload?.next_offset)) ? Number(payload.next_offset) : null,
  }
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

async function deleteListingRemote({ apiBaseUrl, apiKey, bearerToken, listingId }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.deleteListing(listingId, authContext(bearerToken))
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

async function fetchClientStateRemote({ apiBaseUrl, apiKey, bearerToken }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.clientState(authContext(bearerToken))
}

async function saveClientStateRemote({ apiBaseUrl, apiKey, bearerToken, payload }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.saveClientState(payload, authContext(bearerToken))
}

async function fetchNotificationsRemote({ apiBaseUrl, apiKey, bearerToken, limit = 50 }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.listNotifications(limit, authContext(bearerToken))
}

async function deleteNotificationRemote({ apiBaseUrl, apiKey, bearerToken, notificationId }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.deleteNotification(notificationId, authContext(bearerToken))
}

async function likeListingRemote({ apiBaseUrl, apiKey, bearerToken, listingId }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.likeListing(listingId, authContext(bearerToken))
}

async function fetchGooglePlacesAddressSuggestionsRemote({ apiBaseUrl, apiKey, bearerToken, q, city, state, postalCode }) {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (city) params.set('city', city)
  if (state) params.set('state', state)
  if (postalCode) params.set('postal_code', postalCode)
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  const data = await client.get(`/v1/google/places/address-suggest?${params.toString()}`, authContext(bearerToken))
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

async function activateSubscriptionRemote({ apiBaseUrl, apiKey, bearerToken, plan, billingCycle, paymentMethodId = '' }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.post(
    '/v1/me/subscription/activate',
    {
      plan: subscriptionPlanIdForApi(plan),
      billing_cycle: normalizeBillingCycle(billingCycle),
      payment_method_id: paymentMethodId || null,
    },
    authContext(bearerToken),
  )
}

async function createOfferRemote({ apiBaseUrl, apiKey, bearerToken, payload }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.createOffer(payload, authContext(bearerToken))
}

async function fetchIncomingOffersRemote({ apiBaseUrl, apiKey, bearerToken, status = 'pending', limit = 50 }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.incomingOffers(status, limit, authContext(bearerToken))
}

async function actionOfferRemote({ apiBaseUrl, apiKey, bearerToken, offerId, status, receiveAddress = null, selectedOfferedListingId = null }) {
  const { client, authContext } = createWebApiClient({ apiBaseUrl, apiKey })
  return client.offerAction(offerId, status, receiveAddress, selectedOfferedListingId, authContext(bearerToken))
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
  if (typeof window !== 'undefined' && window.location.pathname === '/terms') {
    return <TermsPage />
  }
  if (typeof window !== 'undefined' && window.location.pathname === '/privacy') {
    return <PrivacyPolicyPage />
  }
  if (CLERK_ENABLED) return <ClerkMarketplaceApp />
  return <LocalMarketplaceApp />
}

const TERMS_SECTIONS = [
  {
    title: '1. Overview',
    body: [
      'JOUFT is a platform that enables users to trade clothing and accessories with other users.',
      'JOUFT facilitates trades but does not own, inspect, or guarantee any listed items.',
    ],
  },
  {
    title: '2. Eligibility and Accounts',
    body: ['You are responsible for all activity under your account.'],
    items: [
      'Be at least 18 years old',
      'Provide accurate information',
      'Maintain the security of your account',
    ],
  },
  {
    title: '3. Listings',
    body: ['By listing an item, you agree that:', 'JOUFT may remove listings at its discretion.'],
    items: [
      'You own the item',
      'The item is authentic',
      'The description and images are accurate',
      'The item complies with platform rules',
    ],
  },
  {
    title: '4. Trades (Binding Agreement)',
    body: ['Trades are binding once accepted.', 'By confirming a trade, you agree to:', 'Failure to complete a trade will result in penalties.'],
    items: [
      'Ship your item',
      'Pay all applicable fees',
      'Complete the transaction in good faith',
    ],
  },
  {
    title: '5. Shipping (Required)',
    body: [
      'Shipping is required for all trades.',
      'You agree to:',
      'Shipping fees may include both carrier costs and a service fee.',
      'You may not complete trades outside the platform.',
    ],
    items: [
      'Use JOUFT-provided shipping labels',
      'Pay a shipping fee',
      'Ship within 72 hours',
    ],
  },
  {
    title: '6. Fees',
    body: ['You may be charged:', 'Fees may vary during promotional or beta periods.', 'All fees are disclosed before confirmation.'],
    items: [
      'Shipping fee (mandatory)',
      'Trade fee (may apply, including during beta periods)',
      'Membership fee (if applicable)',
      'Optional services (authentication, promotions)',
    ],
  },
  {
    title: '7. Authorization of Charges',
    body: [
      'By using JOUFT and confirming a trade, you authorize JOUFT to charge your payment method for:',
      'Failure to maintain a valid payment method may result in account suspension.',
    ],
    items: [
      'Shipping fees',
      'Trade fees',
      'Membership fees',
      'Penalty fees',
    ],
  },
  {
    title: '8. Non-Shipment Penalty',
    body: ['If you confirm a trade and fail to ship within the required timeframe:', 'Repeated violations will result in suspension or permanent removal.'],
    items: [
      'A non-shipment penalty fee will be automatically charged',
      'The trade will be canceled',
      'The penalty amount will be determined based on the value band of the item',
      'All or a portion of the penalty may be used to compensate the affected user',
    ],
  },
  {
    title: '9. Value Bands',
    body: ['Items may be grouped into value ranges ("value bands") to:', 'Value bands are estimates and do not guarantee market value.'],
    items: [
      'Facilitate trade matching',
      'Determine penalty amounts',
    ],
  },
  {
    title: '10. Authentication (Optional)',
    body: ['Authentication services may be offered:'],
    items: [
      'Additional fees apply',
      'Results are not guaranteed',
    ],
  },
  {
    title: '11. Item Misrepresentation',
    body: ['If an item is materially different from its description:', 'JOUFT determines outcomes at its discretion.'],
    items: [
      'JOUFT may cancel or reverse the trade',
      'The responsible user may be penalized',
      'The affected user may be compensated',
    ],
  },
  {
    title: '12. Counterfeit Items',
    body: ['If an item is determined to be counterfeit:'],
    items: [
      'The trade will be canceled',
      'The listing user may be permanently banned',
      'Fees may be forfeited',
    ],
  },
  {
    title: '13. Shipping Issues',
    items: [
      'Responsibility transfers once the package is scanned by the carrier',
      'JOUFT is not responsible for shipping delays, loss, or damage',
      'Users agree to cooperate with carrier claims',
    ],
  },
  {
    title: '14. Disputes Between Users',
    body: ['If a dispute arises:', 'All decisions made by JOUFT are final and binding.'],
    items: [
      'Users must provide requested evidence',
      'JOUFT may review and resolve disputes',
    ],
  },
  {
    title: '15. User Conduct',
    body: ['You may not:', 'Violations may result in suspension or removal.'],
    items: [
      'Misrepresent items',
      'List counterfeit goods',
      'Fail to complete trades',
      'Attempt to bypass the platform',
    ],
  },
  {
    title: '16. Data Use and Platform Insights',
    body: [
      'JOUFT may use aggregated and anonymized data derived from user activity to:',
      'This data does not identify individual users.',
    ],
    items: [
      'Improve the platform',
      'Develop insights and analytics',
      'Support partnerships, including with brands and advertisers',
    ],
  },
  {
    title: '17. Payments',
    body: [
      'Payments are processed through third-party providers.',
      'All fees are non-refundable unless required by law.',
    ],
  },
  {
    title: '18. Limitation of Liability',
    body: ['JOUFT is not liable for:'],
    items: [
      'Lost or damaged items',
      'Failed trades',
      'User actions',
      'Indirect damages',
    ],
  },
  {
    title: '19. Dispute Resolution (Legal)',
    body: ['All disputes shall be resolved through binding arbitration.', 'You waive:', 'Arbitration will take place in CA.'],
    items: [
      'Jury trial',
      'Class actions',
    ],
  },
  {
    title: '20. Changes to Terms',
    body: [
      'JOUFT may update these Terms at any time.',
      'Continued use constitutes acceptance.',
    ],
  },
  {
    title: '21. Contact',
    contact: 'Email: JOUFTllc@gmail.com',
  },
]

const PRIVACY_POLICY_SECTIONS = [
  {
    title: '1. Information We Collect',
    items: [
      'Account information (name, email, preferences)',
      'Transaction data (listings, trades, shipping)',
      'Device and usage data',
    ],
  },
  {
    title: '2. How We Use Information',
    body: [
      'We use information to operate the platform, process trades and payments, improve user experience, and prevent fraud.',
      'We may also use aggregated and anonymized data to generate insights and analytics, including for brand and advertising partnerships.',
    ],
  },
  {
    title: '3. Sharing of Information',
    body: [
      'We may share data with shipping providers, payment processors, and authentication partners.',
      'We may share aggregated and anonymized insights with partners.',
      'We do not sell personal data.',
    ],
  },
  {
    title: '4. Data Security',
    body: ['We take reasonable measures to protect your data but cannot guarantee absolute security.'],
  },
  {
    title: '5. Your Rights (California Residents)',
    body: ['You may request access or request deletion.'],
    contact: 'Contact: JOUFTllc@gmail.com',
  },
  {
    title: '6. Cookies',
    body: ['We use cookies to improve functionality and analyze usage.'],
  },
  {
    title: '7. Updates',
    body: ['We may update this policy at any time.'],
  },
  {
    title: '8. Contact',
    contact: 'Email: admin@jouft.com',
  },
]

const CONTACT_DETAILS = [
  {
    title: 'Company Address',
    body: [
      '120 Vantis Dr. Suite 300',
      'Aliso Viejo, CA 92656',
      'US',
    ],
  },
  {
    title: 'Contact Email',
    contact: 'admin@jouft.com',
  },
]
const CONTACT_MAP_QUERY = '120 Vantis Dr Suite 300, Aliso Viejo, CA 92656, US'
const CONTACT_MAP_EMBED_URL = `https://maps.google.com/maps?q=${encodeURIComponent(CONTACT_MAP_QUERY)}&output=embed`
const CONTACT_DIRECTIONS_URL = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(CONTACT_MAP_QUERY)}`

function PrivacyPolicyPage() {
  return (
    <main className="legal-page">
      <header className="legal-header">
        <a className="legal-wordmark" href="/">JOUFT</a>
        <a className="legal-back-link" href="/">Back to Jouft</a>
      </header>
      <section className="legal-card">
        <p className="eyebrow">Legal</p>
        <h1>Privacy Policy</h1>
        <div className="legal-divider" />
        {PRIVACY_POLICY_SECTIONS.map((section) => (
          <section className="legal-section" key={section.title}>
            <h2>{section.title}</h2>
            {section.items ? (
              <ul>
                {section.items.map((item) => <li key={item}>{item}</li>)}
              </ul>
            ) : null}
            {section.body?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
            {section.contact ? <p className="legal-contact">{section.contact}</p> : null}
          </section>
        ))}
      </section>
    </main>
  )
}

function TermsPage() {
  return (
    <main className="legal-page">
      <header className="legal-header">
        <a className="legal-wordmark" href="/">JOUFT</a>
        <a className="legal-back-link" href="/">Back to Jouft</a>
      </header>
      <section className="legal-card">
        <p className="eyebrow">Legal</p>
        <h1>Terms</h1>
        <div className="legal-divider" />
        {TERMS_SECTIONS.map((section) => (
          <section className="legal-section" key={section.title}>
            <h2>{section.title}</h2>
            {section.body?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
            {section.items ? (
              <ul>
                {section.items.map((item) => <li key={item}>{item}</li>)}
              </ul>
            ) : null}
            {section.contact ? <p className="legal-contact">{section.contact}</p> : null}
          </section>
        ))}
      </section>
    </main>
  )
}

function ClerkMarketplaceApp() {
  const { isLoaded, isSignedIn, getToken } = useAuth()
  const { signOut } = useClerk()
  const { user } = useUser()
  const [authMode, setAuthMode] = useState('login')
  const [authPanelOpen, setAuthPanelOpen] = useState(false)
  const getBearerToken = useCallback(() => getToken(), [getToken])
  const handleLogout = useCallback(() => signOut({ redirectUrl: '/' }), [signOut])

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
	      onLogout={handleLogout}
	      clerkEnabled
	      getBearerToken={getBearerToken}
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
  const handleLogout = useCallback(() => setSession(null), [])

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

  return <MarketplaceWorkspace session={session} onLogout={handleLogout} />
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
            <a href="#closet">CLOSET</a>
            <span>DISCOVER</span>
            <a href="#how-it-works">HOW IT WORKS</a>
            <a href="#contact">CONTACT US</a>
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
              <a className="ghost arrow" href="#how-it-works">How It Works</a>
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
        <section className="auth-closet-section" id="closet">
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
        <section className="auth-how-section" id="how-it-works">
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
        <section className="auth-contact-section" id="contact">
          <div className="auth-section-head">
            <h2>CONTACT US</h2>
          </div>
          <div className="auth-contact-grid">
            <div className="auth-contact-details">
              {CONTACT_DETAILS.map((section) => (
                <div className="auth-contact-block" key={section.title}>
                  <h3>{section.title}</h3>
                  {section.body?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                  {section.contact ? <a href={`mailto:${section.contact}`}>{section.contact}</a> : null}
                </div>
              ))}
              <a className="contact-directions-link" href={CONTACT_DIRECTIONS_URL} target="_blank" rel="noreferrer">
                Get Directions
              </a>
            </div>
            <div className="contact-map-frame auth-contact-map">
              <iframe
                title="JOUFT office map"
                src={CONTACT_MAP_EMBED_URL}
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
              />
            </div>
          </div>
        </section>
        <footer className="auth-site-footer">
          <strong>JOUFT</strong>
          <div className="auth-footer-links">
            <span>ABOUT</span><a href="#contact">CONTACT US</a><span>FAQ</span><a href="/terms">TERMS</a><a href="/privacy">PRIVACY</a>
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
  const signupFullName = resolveSignupFullName(session, profileData)
  const shouldAutoOpenProfileSetupRef = useRef(TEMP_SHOW_PROFILE_QUESTIONNAIRE_ON_LOGIN && !hasExplicitTabInLocation())
  const [apiBaseUrl] = useState(API_DEFAULT)
  const [apiKey, setApiKey] = useState('local-dev-key')
  const [myListings, setMyListings] = useState([])
  const [marketListings, setMarketListings] = useState([])
  const [myListingsLoading, setMyListingsLoading] = useState(false)
  const [marketListingsLoading, setMarketListingsLoading] = useState(false)
  const [myListingsHasMore, setMyListingsHasMore] = useState(false)
  const [marketListingsHasMore, setMarketListingsHasMore] = useState(false)
  const [myListingsNextOffset, setMyListingsNextOffset] = useState(0)
  const [marketListingsNextOffset, setMarketListingsNextOffset] = useState(0)
  const [myListingsPageLoading, setMyListingsPageLoading] = useState(false)
  const [marketListingsPageLoading, setMarketListingsPageLoading] = useState(false)
  const [activeTab, setActiveTab] = useState(() => (shouldAutoOpenProfileSetupRef.current ? 'profile_setup' : tabFromLocation()))
  const [marketSearch, setMarketSearch] = useState('')
  const [itemTitle, setItemTitle] = useState('')
  const [category, setCategory] = useState('')
  const [userCondition, setUserCondition] = useState('')
  const [itemDescription, setItemDescription] = useState('')
  const [itemSize, setItemSize] = useState('')
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
  const [createListingBusy, setCreateListingBusy] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [analysisResult, setAnalysisResult] = useState(null)
  const [receiptPromptPending, setReceiptPromptPending] = useState(false)
  const [receiptPromptDismissed, setReceiptPromptDismissed] = useState(false)
  const [editingListingId, setEditingListingId] = useState(null)
  const [reviewListingId, setReviewListingId] = useState(null)
  const [showCreateListingModal, setShowCreateListingModal] = useState(false)
  const [listingModalMode, setListingModalMode] = useState('create')
  const [modalEditingListing, setModalEditingListing] = useState(null)
  const [savedListingNotice, setSavedListingNotice] = useState('')
  const [appAlert, setAppAlert] = useState(null)
  const [offerActionBusyById, setOfferActionBusyById] = useState({})
  const [offerAcceptedListingById, setOfferAcceptedListingById] = useState({})
  const [selectedShippingLabel, setSelectedShippingLabel] = useState(null)
  const [profileQuiz, setProfileQuiz] = useState({
    first_name: profileData?.firstName || '', last_name: profileData?.lastName || '', email: profileData?.email || session?.email || '',
    gender: '', birthday: '', tops_size: [], dresses_size: [], bottoms_size: [], shoes_size: [], category_preferences: [],
    style_descriptors: [], jouft_goals: [],
    shipping_full_name: '', shipping_address_line1: '', shipping_address_line2: '', shipping_city: '', shipping_state: '', shipping_postal_code: '', shipping_country: '',
    shipping_email: profileData?.email || session?.email || '', shipping_phone: profileData?.phone || '',
    shipping_addresses: [emptyShippingAddress()],
    subscription_plan: 'free', subscription_billing_cycle: 'monthly', subscription_status: '', subscription_renewal_date: '', payment_methods: [],
  })
  const [profileSetupStep, setProfileSetupStep] = useState(1)
  const [profileSetupRequired, setProfileSetupRequired] = useState(false)
  const [activeShippingAddressIdx, setActiveShippingAddressIdx] = useState(0)
  const [addressSuggestions, setAddressSuggestions] = useState([])
  const [addressAutocompleteActive, setAddressAutocompleteActive] = useState(false)
  const [profileSaveMsg, setProfileSaveMsg] = useState('')
  const [profileTabReloading, setProfileTabReloading] = useState(false)
  const [profileTabReloadKey, setProfileTabReloadKey] = useState(0)
  const [profileHydrationRetry, setProfileHydrationRetry] = useState(0)
  const [paymentMethods, setPaymentMethods] = useState([])
  const [profileHydrationError, setProfileHydrationError] = useState('')
  const [paymentBusy, setPaymentBusy] = useState(false)
  const [paymentSyncBusy, setPaymentSyncBusy] = useState(false)
  const [paymentLoadError, setPaymentLoadError] = useState('')
  const [paymentActionMsg, setPaymentActionMsg] = useState('')
  const [paymentDeleteBusyId, setPaymentDeleteBusyId] = useState('')
  const [selectedSubscriptionPaymentMethodId, setSelectedSubscriptionPaymentMethodId] = useState('')
  const [subscriptionSelectionDirty, setSubscriptionSelectionDirty] = useState(false)
  const [showStripePaymentModal, setShowStripePaymentModal] = useState(false)
  const [subscriptionConfirmRequest, setSubscriptionConfirmRequest] = useState(null)
  const [stripeUiBusy, setStripeUiBusy] = useState(false)
  const [stripeUiError, setStripeUiError] = useState('')
  const [stripeUiReady, setStripeUiReady] = useState(false)
  const [subscriptionStripeAutoSynced, setSubscriptionStripeAutoSynced] = useState(false)
  const stripeRef = useRef(null)
  const stripeElementsRef = useRef(null)
  const stripePaymentElementRef = useRef(null)
  const subscriptionConfirmResolverRef = useRef(null)
  const [incomingOffers, setIncomingOffers] = useState([])
  const [offersActorSubject, setOffersActorSubject] = useState('')
  const [tradeNotification, setTradeNotification] = useState(null)
  const [notifications, setNotifications] = useState([])
  const [notificationsHydrated, setNotificationsHydrated] = useState(false)
  const [notificationPanelOpen, setNotificationPanelOpen] = useState(false)
  const [tradeComposerTarget, setTradeComposerTarget] = useState(null)
  const [marketMatchesTargetId, setMarketMatchesTargetId] = useState(null)
  const [selectedMarketImageIndex, setSelectedMarketImageIndex] = useState(0)
  const [selectedCreateImageIndex, setSelectedCreateImageIndex] = useState(0)
  const [selectedEditImageIndex, setSelectedEditImageIndex] = useState(0)
  const [selectedReviewImageIndex, setSelectedReviewImageIndex] = useState(0)
  const [selectedEditHeroImageIndex, setSelectedEditHeroImageIndex] = useState(null)
  const [tradeOfferCandidates, setTradeOfferCandidates] = useState([])
  const [tradeOfferListingIds, setTradeOfferListingIds] = useState([])
  const [tradeOfferMessage, setTradeOfferMessage] = useState('')
  const [tradeOfferError, setTradeOfferError] = useState('')
  const [tradeOfferBusy, setTradeOfferBusy] = useState(false)
  const [tradeDetailListing, setTradeDetailListing] = useState(null)
  const [tradeDetailImageIndex, setTradeDetailImageIndex] = useState(0)
  const [zoomedListingImage, setZoomedListingImage] = useState(null)
  const [zoomedListingImageScale, setZoomedListingImageScale] = useState(1)
  const [offerStatusFilter, setOfferStatusFilter] = useState('all')
  const [closetFilter, setClosetFilter] = useState('all')
  const [profileSection, setProfileSection] = useState(TEMP_SHOW_PROFILE_QUESTIONNAIRE_ON_LOGIN ? 'style' : 'general')
  const [shippingLabelsByOffer, setShippingLabelsByOffer] = useState({})
  const [offerReceiveAddressById, setOfferReceiveAddressById] = useState({})
  const [shippingQuoteByOffer, setShippingQuoteByOffer] = useState({})
  const [selectedMarketListingIndex, setSelectedMarketListingIndex] = useState(null)
  const [likedListingIds, setLikedListingIds] = useState([])
  const [clientStateHydrated, setClientStateHydrated] = useState(false)
  const forcedLogoutRef = useRef(false)
  const profileSetupAutoOpenedRef = useRef(false)
  const knownIncomingOfferIdsRef = useRef(new Set())
  const offerStatusByIdRef = useRef(new Map())
  const shippingSignatureByOfferRef = useRef(new Map())
  const incomingOfferPollInitializedRef = useRef(false)
  const seenServerNotificationIdsRef = useRef(new Set())
  const profileQuizHydrationStartedRef = useRef('')
  const lastLoadedProfileQuizRef = useRef(null)
  const profileSetupDirtyRef = useRef(false)
  const activeTabRef = useRef(activeTab)
  const notificationStorageKey = useMemo(() => {
    const subject = String(session?.id || session?.email || 'guest').trim() || 'guest'
    return `jouft.notifications.${subject}`
  }, [session?.email, session?.id])

  useEffect(() => {
    activeTabRef.current = activeTab
  }, [activeTab])

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

  function isOfferReceivedByCurrentUser(offer, actorSubject = '') {
    const actor = String(actorSubject || resolveOfferActorSubject(offer) || '').trim()
    const recipient = String(offer?.to_subject || '').trim()
    return Boolean(actor && recipient && actor === recipient)
  }

  function isOwnedByCurrentUser(listing) {
    const ownerSubject = String(listing?.ownerSubject || '').trim()
    const currentSubject = String(session?.id || '').trim()
    if (ownerSubject && currentSubject && ownerSubject === currentSubject) return true
    const ownerName = String(listing?.owner || '').trim().toLowerCase()
    const currentName = String(session?.name || '').trim().toLowerCase()
    return Boolean(ownerName && currentName && ownerName === currentName)
  }

  function navigateToTab(tab) {
    if (!VALID_TABS.has(tab)) return
    const nextTab = profileSetupRequired && tab !== 'profile_setup' ? 'profile_setup' : tab
    setActiveTab(nextTab)
    if (typeof window !== 'undefined') {
      window.history.pushState({}, '', tabHref(nextTab))
    }
  }

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    function handlePopState() {
      const requestedTab = tabFromLocation()
      const nextTab = profileSetupRequired && requestedTab !== 'profile_setup' ? 'profile_setup' : requestedTab
      if (nextTab !== 'edit_listing') {
        setEditingListingId(null)
        setModalEditingListing(null)
        setImages([])
        setEditPreviewUrls([])
        setSelectedEditHeroImageIndex(null)
        setAnalysisError('')
      }
      if (nextTab !== 'review_listing') {
        setReviewListingId(null)
      }
      if (!(nextTab === 'market' && listingIdFromLocation())) {
        setSelectedMarketListingIndex(null)
        setSelectedMarketImageIndex(0)
      }
      setActiveTab(nextTab)
      if (nextTab !== requestedTab) {
        window.history.replaceState({}, '', tabHref(nextTab))
      }
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [profileSetupRequired])

  const unreadNotificationCount = notifications.filter((entry) => !entry.read).length

  function addAppNotification({ type, title, body, actionTab = 'inbox', entityId = '' }) {
    const notification = {
      id: `${type || 'notification'}-${entityId || Date.now()}-${Date.now()}`,
      type: type || 'notification',
      title: title || 'Notification',
      body: body || '',
      actionTab,
      entityId,
      createdAt: new Date().toISOString(),
      read: false,
    }
    setNotifications((prev) => [notification, ...prev].slice(0, 50))
    return notification
  }

  function openNotificationCenter() {
    if (notificationPanelOpen) {
      setNotificationPanelOpen(false)
      setNotifications((prev) => prev.filter((entry) => !entry.read))
      return
    }
    setNotifications((prev) => prev.map((entry) => ({ ...entry, read: true })))
    setNotificationPanelOpen(true)
  }

  function openNotificationAction(notification) {
    setNotificationPanelOpen(false)
    setNotifications((prev) => prev.filter((entry) => entry.id !== notification?.id && !entry.read))
    if (notification?.actionTab) {
      navigateToTab(notification.actionTab)
      if (notification.actionTab === 'inbox') setOfferStatusFilter('all')
    }
  }

  function showShippingAddressRequiredAlert(message = 'Add a shipping address to your profile before accepting a trade.') {
    setAppAlert({
      title: 'Shipping Address Required',
      message,
      primaryLabel: 'Go to Profile',
      onPrimary: () => {
        setAppAlert(null)
        setProfileSection('shipping')
        navigateToTab('profile')
      },
      secondaryLabel: 'Cancel',
    })
  }

  function confirmTradeAcceptance(offer, quoteOverride = null, selectedOfferedListing = null) {
    const offeredTitle = selectedOfferedListing?.title || offer?.offered_listing?.title || 'the offered item'
    const targetTitle = offer?.target_listing?.title || 'your item'
    const quote = quoteOverride || shippingQuoteByOffer[offer?.offer_id]
    const shippingCost = quote?.status === 'quoted' && quote?.amount
      ? `${quote.currency || 'USD'} ${quote.amount}`
      : 'unavailable'
    return new Promise((resolve) => {
      setAppAlert({
        title: 'Accept Trade?',
        message: `Accept this trade for ${targetTitle} in exchange for ${offeredTitle}? Shipping cost charged to you: ${shippingCost}.`,
        primaryLabel: 'Accept Trade',
        onPrimary: () => {
          setAppAlert(null)
          resolve(true)
        },
        secondaryLabel: 'Cancel',
        onSecondary: () => resolve(false),
      })
    })
  }

  function confirmListingDelete(listing) {
    return new Promise((resolve) => {
      setAppAlert({
        title: 'Delete Listing?',
        message: `Delete "${listing?.title || 'this listing'}" from your closet? This cannot be undone.`,
        primaryLabel: 'Delete Listing',
        onPrimary: () => {
          setAppAlert(null)
          resolve(true)
        },
        secondaryLabel: 'Cancel',
        onSecondary: () => resolve(false),
      })
    })
  }

  function isSameListingOwner(left, right) {
    const leftSubject = String(left?.ownerSubject || left?.owner_subject || '').trim().toLowerCase()
    const rightSubject = String(right?.ownerSubject || right?.owner_subject || '').trim().toLowerCase()
    if (leftSubject && rightSubject) return leftSubject === rightSubject
    if (isOwnedByCurrentUser(left) && isOwnedByCurrentUser(right)) return true
    const leftOwner = String(left?.owner || left?.owner_name || '').trim().toLowerCase()
    const rightOwner = String(right?.owner || right?.owner_name || '').trim().toLowerCase()
    const currentName = String(session?.name || '').trim().toLowerCase()
    if (!rightSubject && currentName && isOwnedByCurrentUser(left) && rightOwner === currentName) return true
    if (!leftSubject && currentName && isOwnedByCurrentUser(right) && leftOwner === currentName) return true
    return Boolean((!leftSubject || !rightSubject) && leftOwner && rightOwner && leftOwner === rightOwner)
  }

  function getCrossOwnerMatches(listing) {
    const matches = Array.isArray(listing?.matches) ? listing.matches : []
    return matches.filter((candidate) => !isSameListingOwner(listing, candidate))
  }

  function removeSentOfferMatches(targetListingId, offeredListingIds) {
    const targetId = String(targetListingId || '').trim()
    const offeredIds = new Set((Array.isArray(offeredListingIds) ? offeredListingIds : [])
      .map((id) => String(id || '').trim())
      .filter(Boolean))
    if (!targetId || offeredIds.size === 0) return
    setMarketListings((prev) => prev.map((listing) => {
      if (String(listing?.id || '') !== targetId || !Array.isArray(listing?.matches)) return listing
      return {
        ...listing,
        matches: listing.matches.filter((match) => !offeredIds.has(String(match?.id || ''))),
      }
    }))
  }

  useEffect(() => {
    let cancelled = false
    setClientStateHydrated(false)
    ;(async () => {
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const data = await fetchClientStateRemote({ apiBaseUrl, apiKey: clerkEnabled ? '' : apiKey.trim(), bearerToken })
        if (!cancelled) {
          const likedIds = Array.isArray(data?.liked_listing_ids) ? data.liked_listing_ids : []
          setLikedListingIds(likedIds.map((id) => String(id)).filter(Boolean))
        }
      } catch {
        if (!cancelled) setLikedListingIds([])
      } finally {
        if (!cancelled) setClientStateHydrated(true)
      }
    })()
    return () => { cancelled = true }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken, session?.id])

  useEffect(() => {
    if (!clientStateHydrated) return
    let cancelled = false
    ;(async () => {
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        if (cancelled) return
        await saveClientStateRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          payload: {
            liked_listing_ids: likedListingIds,
          },
        })
      } catch {}
    })()
    return () => { cancelled = true }
  }, [apiBaseUrl, apiKey, clerkEnabled, clientStateHydrated, getBearerToken, likedListingIds])

  useEffect(() => {
    if (typeof window === 'undefined') return
    setNotificationsHydrated(false)
    try {
      const raw = window.localStorage.getItem(notificationStorageKey)
      const parsed = raw ? JSON.parse(raw) : []
      setNotifications(Array.isArray(parsed) ? parsed.slice(0, 50) : [])
    } catch {
      setNotifications([])
    } finally {
      setNotificationsHydrated(true)
    }
  }, [notificationStorageKey])

  useEffect(() => {
    if (!notificationsHydrated || typeof window === 'undefined') return
    try {
      window.localStorage.setItem(notificationStorageKey, JSON.stringify(notifications.slice(0, 50)))
    } catch {}
  }, [notificationStorageKey, notifications, notificationsHydrated])

  useEffect(() => {
    let cancelled = false

    async function pollServerNotifications() {
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const payload = await fetchNotificationsRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          limit: 50,
        })
        if (cancelled) return
        const items = Array.isArray(payload?.items) ? payload.items : []
        items.slice().reverse().forEach((item) => {
          const id = String(item?.notification_id || item?.id || '')
          if (!id || seenServerNotificationIdsRef.current.has(id)) return
          seenServerNotificationIdsRef.current.add(id)
          addAppNotification({
            type: item?.type || 'notification',
            title: item?.title || 'Notification',
            body: item?.body || '',
            actionTab: item?.action_tab === 'marketplace' ? 'market' : (item?.action_tab || 'inbox'),
            entityId: item?.entity_id || '',
          })
          deleteNotificationRemote({
            apiBaseUrl,
            apiKey: clerkEnabled ? '' : apiKey.trim(),
            bearerToken,
            notificationId: id,
          }).catch(() => {})
        })
      } catch {}
    }

    pollServerNotifications()
    const timer = window.setInterval(pollServerNotifications, 15000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken])

  async function loadProfileQuizIntoState({ force = false } = {}) {
    const hydrationKey = String(session?.id || session?.email || 'anonymous')
    if (!force && profileQuizHydrationStartedRef.current === hydrationKey) {
      return lastLoadedProfileQuizRef.current
    }
    profileQuizHydrationStartedRef.current = hydrationKey
    const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
    if (clerkEnabled && !bearerToken) throw new Error('Authentication token unavailable.')
    const data = await fetchProfileQuizRemote({ apiBaseUrl, apiKey: clerkEnabled ? '' : apiKey.trim(), bearerToken })
    lastLoadedProfileQuizRef.current = data
    const shippingAddresses = normalizeShippingAddresses(data?.shipping_addresses, data)
    const hydratedShippingAddresses = shippingAddresses.map((address, idx) => (
      idx === 0 && !address.full_name && signupFullName
        ? { ...address, full_name: signupFullName }
        : address
    ))
    const primaryShippingAddress = hydratedShippingAddresses[0] || emptyShippingAddress()
    if (!(profileSetupDirtyRef.current && activeTabRef.current === 'profile_setup')) {
      setProfileQuiz({
        first_name: data?.first_name || profileData?.firstName || '',
        last_name: data?.last_name || profileData?.lastName || '',
        email: data?.email || profileData?.email || session?.email || '',
        shipping_email: data?.shipping_email || profileData?.email || session?.email || '',
        shipping_phone: data?.shipping_phone || profileData?.phone || '',
        gender: data?.gender || '',
        birthday: data?.birthday || '',
        tops_size: normalizeMultiSizeValue(data?.tops_size),
        dresses_size: normalizeMultiSizeValue(data?.dresses_size),
        bottoms_size: normalizeMultiSizeValue(data?.bottoms_size),
        shoes_size: normalizeMultiSizeValue(data?.shoes_size),
        category_preferences: Array.isArray(data?.category_preferences) ? data.category_preferences : [],
        style_descriptors: Array.isArray(data?.style_descriptors) ? data.style_descriptors : [],
        jouft_goals: Array.isArray(data?.jouft_goals) ? data.jouft_goals : [],
        shipping_full_name: primaryShippingAddress.full_name || '',
        shipping_address_line1: primaryShippingAddress.address_line1 || '',
        shipping_address_line2: primaryShippingAddress.address_line2 || '',
        shipping_city: primaryShippingAddress.city || '',
        shipping_state: primaryShippingAddress.state || '',
        shipping_postal_code: primaryShippingAddress.postal_code || '',
        shipping_country: primaryShippingAddress.country || '',
        shipping_addresses: hydratedShippingAddresses,
        subscription_plan: normalizeSelectableSubscriptionPlanId(data?.subscription_plan),
        subscription_billing_cycle: normalizeBillingCycle(data?.subscription_billing_cycle),
        subscription_status: data?.subscription_status || '',
        subscription_renewal_date: data?.subscription_renewal_date || '',
        payment_methods: Array.isArray(data?.payment_methods) ? data.payment_methods : [],
      })
      setActiveShippingAddressIdx(0)
    }
    setProfileHydrationError('')
    return data
  }

  async function reloadProfileTabAfterSuccess(message = '', { navigateToProfileTab = false } = {}) {
    setProfileTabReloading(true)
    try {
      setActiveTab('profile')
      setProfileSection('general')
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      await loadProfileQuizIntoState({ force: true })
      const methods = await fetchPaymentMethodsRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
      })
      setPaymentMethods(methods)
      setPaymentLoadError('')
      setProfileTabReloadKey((key) => key + 1)
      if (message) setProfileSaveMsg(message)
      if (navigateToProfileTab && typeof window !== 'undefined') {
        window.location.assign(tabHref('profile'))
      }
    } finally {
      setProfileTabReloading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    let retryTimer = null
    ;(async () => {
      try {
        const data = await loadProfileQuizIntoState()
        if (!cancelled) {
          if (!data) return
          const profileSetupRequired = isProfileSetupRequired(data)
          setProfileSetupRequired(profileSetupRequired)
          const shouldOpenSetup = (
            profileSetupRequired || (!hasExplicitTabInLocation() && shouldAutoOpenProfileSetupRef.current)
          )
          if (!profileSetupRequired) {
            shouldAutoOpenProfileSetupRef.current = false
            if (activeTabRef.current === 'profile_setup' && !profileSetupDirtyRef.current) {
              navigateToTab('market')
              return
            }
          }
          if (shouldOpenSetup && !profileSetupAutoOpenedRef.current) {
            profileSetupAutoOpenedRef.current = true
            navigateToTab('profile_setup')
          }
        }
      } catch {
        profileQuizHydrationStartedRef.current = ''
        if (!cancelled) setProfileHydrationError('Profile data could not be loaded yet.')
        if (!cancelled && profileHydrationRetry < 5) {
          retryTimer = window.setTimeout(() => {
            if (!cancelled) setProfileHydrationRetry((count) => count + 1)
          }, 750)
        }
      }
    })()
    return () => {
      cancelled = true
      if (retryTimer) window.clearTimeout(retryTimer)
    }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken, session?.email, session?.id, signupFullName, profileData?.firstName, profileData?.lastName, profileData?.email, profileHydrationRetry])

  useEffect(() => {
    if (activeTab !== 'profile' && activeTab !== 'profile_setup') return undefined
    let cancelled = false
    const timer = window.setTimeout(() => {
      loadProfileQuizIntoState({ force: true }).catch((err) => {
        if (!cancelled) setProfileHydrationError(err.message || 'Profile data could not be loaded.')
      })
    }, 150)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [activeTab, apiBaseUrl, apiKey, clerkEnabled, getBearerToken, session?.email, session?.id, signupFullName, profileData?.firstName, profileData?.lastName, profileData?.email])

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
    if (paymentMethods.length === 0) {
      if (selectedSubscriptionPaymentMethodId) setSelectedSubscriptionPaymentMethodId('')
      return
    }
    const selectedStillExists = paymentMethods.some((method) => method.payment_method_id === selectedSubscriptionPaymentMethodId)
    if (selectedStillExists) return
    const fallback = paymentMethods.find((method) => method.is_default) || paymentMethods[0]
    setSelectedSubscriptionPaymentMethodId(fallback?.payment_method_id || '')
  }, [paymentMethods, selectedSubscriptionPaymentMethodId])

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

  const normalizedProfileGender = profileQuiz.gender === 'male' || profileQuiz.gender === 'female' || profileQuiz.gender === 'other'
    ? profileQuiz.gender
    : ''
  const profileApparelSizeOptions = normalizedProfileGender === 'male' ? MALE_APPAREL_SIZE_OPTIONS : FEMALE_APPAREL_SIZE_OPTIONS
  const profileShoeSizeOptions = normalizedProfileGender === 'male' ? MALE_SHOE_SIZE_OPTIONS : FEMALE_SHOE_SIZE_OPTIONS
  const profileCategoryOptions = normalizedProfileGender === 'male'
    ? PROFILE_CATEGORY_OPTIONS.filter((c) => c !== 'Dresses')
    : PROFILE_CATEGORY_OPTIONS
  const selectedSubscriptionPlanId = normalizeSelectableSubscriptionPlanId(profileQuiz.subscription_plan)
  const selectedSubscriptionPlan = SUBSCRIPTION_PLANS.find((plan) => plan.id === selectedSubscriptionPlanId) || SUBSCRIPTION_PLANS[0]
  const selectedSubscriptionPlanIsPaid = Number(selectedSubscriptionPlan?.monthlyPrice || 0) > 0
  const selectedBillingCycle = normalizeBillingCycle(profileQuiz.subscription_billing_cycle)
  const shippingAddresses = normalizeShippingAddresses(profileQuiz.shipping_addresses, profileQuiz)
  const completeProfileShippingAddresses = completeShippingAddresses(shippingAddresses)
  const primaryShippingAddressId = shippingAddresses[0]?.id || ''
  const subscriptionStatus = String(profileQuiz.subscription_status || '').trim().toLowerCase()
  const hasActiveSubscription = ['active', 'trialing'].includes(subscriptionStatus)
  const subscriptionSelectionIsCurrent = hasActiveSubscription && !subscriptionSelectionDirty

  function currentProfileSetupStepError(step = profileSetupStep) {
    const payload = profilePayloadForSave()
    const primaryAddress = normalizeShippingAddresses(payload.shipping_addresses, payload)[0] || emptyShippingAddress()
    if (step === 1) {
      if (!payload.first_name) return 'First name is required.'
      if (!payload.last_name) return 'Last name is required.'
      if (!payload.email) return 'Email address is required.'
      if (!payload.birthday) return 'Birthday is required.'
      if (!payload.gender) return 'Gender is required.'
      if (!isCompleteShippingAddress(primaryAddress)) return 'Complete shipping address is required.'
    }
    if (step === 2) {
      const hasSize = ['tops_size', 'dresses_size', 'bottoms_size', 'shoes_size']
        .some((field) => normalizeMultiSizeValue(payload[field]).length > 0)
      if (!hasSize) return 'Select at least one size.'
    }
    if (step === 3 && (!Array.isArray(payload.style_descriptors) || payload.style_descriptors.length === 0)) {
      return 'Choose at least one style.'
    }
    if (step === 4 && (!Array.isArray(payload.jouft_goals) || payload.jouft_goals.length === 0)) {
      return 'Choose at least one reason.'
    }
    if (step === 5) {
      if (!selectedSubscriptionPlan) return 'Select a subscription plan.'
      if (selectedSubscriptionPlanIsPaid && paymentMethods.length === 0) return 'Add a payment method before activating your subscription.'
      if (selectedSubscriptionPlanIsPaid && !selectedSubscriptionPaymentMethodId) return 'Select the payment method for your subscription.'
    }
    return ''
  }

  const loadIncomingOffers = useCallback(async ({ status = offerStatusFilter, updateInbox = true } = {}) => {
    const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
    const payload = await fetchIncomingOffersRemote({
      apiBaseUrl,
      apiKey: clerkEnabled ? '' : apiKey.trim(),
      bearerToken,
      status,
      limit: 50,
    })
    const items = Array.isArray(payload?.items) ? payload.items : []
    const actorSubject = typeof payload?.actor?.subject === 'string' ? payload.actor.subject : ''
    if (updateInbox) {
      setIncomingOffers(items)
      setOffersActorSubject(actorSubject)
      setOfferReceiveAddressById((prev) => {
        const next = { ...prev }
        items.forEach((offer) => {
          if (!next[offer.offer_id]) {
            next[offer.offer_id] = primaryShippingAddressId
          }
        })
        return next
      })
    }
    return { items, actorSubject }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken, offerStatusFilter, primaryShippingAddressId])

  function incomingTradeNotificationText(offers) {
    const list = Array.isArray(offers) ? offers : []
    if (list.length === 1) {
      const offer = list[0]
      const targetTitle = offer?.target_listing?.title || 'one of your listings'
      return `New trade request for ${targetTitle}.`
    }
    return `${list.length} new trade requests.`
  }

  function notificationOfferTitle(offer) {
    return offer?.target_listing?.title || offer?.offered_listing?.title || 'a listing'
  }

  function shippingLabelSignature(shipments) {
    return (Array.isArray(shipments) ? shipments : [])
      .map((shipment) => {
        const id = shipment?.shipment_id || shipment?.id || ''
        const labelReady = String(shipment?.label_url || shipment?.label_href || '').trim() ? 'label:yes' : 'label:no'
        const status = shipment?.status || ''
        return `${id}:${status}:${labelReady}`
      })
      .join('|')
  }

  useEffect(() => {
    if (activeTab !== 'inbox') return undefined
    let cancelled = false
    loadIncomingOffers({ status: offerStatusFilter, updateInbox: true }).catch(() => {
      if (!cancelled) {
        setIncomingOffers([])
        setOffersActorSubject('')
      }
    })
    return () => {
      cancelled = true
    }
  }, [activeTab, loadIncomingOffers, offerStatusFilter])

  useEffect(() => {
    let cancelled = false

    async function pollPendingOffers() {
      try {
        const inboxActive = activeTabRef.current === 'inbox'
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const { items, actorSubject } = await loadIncomingOffers({
          status: 'all',
          updateInbox: false,
        })
        if (cancelled) return
        if (inboxActive) {
          const visibleItems = offerStatusFilter === 'all'
            ? items
            : items.filter((offer) => String(offer?.status || '').toLowerCase() === offerStatusFilter)
          setIncomingOffers(visibleItems)
          setOffersActorSubject(actorSubject)
          setOfferReceiveAddressById((prev) => {
            const next = { ...prev }
            visibleItems.forEach((offer) => {
              if (!next[offer.offer_id]) {
                next[offer.offer_id] = primaryShippingAddressId
              }
            })
            return next
          })
        }
        const pendingReceived = items.filter((offer) => (
          String(offer?.status || '').toLowerCase() === 'pending'
          && isOfferReceivedByCurrentUser(offer, actorSubject)
        ))
        const currentIds = new Set(pendingReceived.map((offer) => String(offer?.offer_id || '')).filter(Boolean))
        const previousIds = knownIncomingOfferIdsRef.current
        const newOffers = pendingReceived.filter((offer) => {
          const id = String(offer?.offer_id || '')
          return id && !previousIds.has(id)
        })
        knownIncomingOfferIdsRef.current = currentIds
        const previousStatusById = offerStatusByIdRef.current
        const nextStatusById = new Map(previousStatusById)
        const acceptedOffers = []
        items.forEach((offer) => {
          const offerId = String(offer?.offer_id || '')
          if (!offerId) return
          const status = String(offer?.status || '').toLowerCase()
          const previousStatus = String(previousStatusById.get(offerId) || '').toLowerCase()
          if (status === 'accepted' && previousStatus && previousStatus !== 'accepted') {
            acceptedOffers.push(offer)
          }
          nextStatusById.set(offerId, status)
        })
        offerStatusByIdRef.current = nextStatusById
        if (!incomingOfferPollInitializedRef.current) {
          incomingOfferPollInitializedRef.current = true
          const initializedAcceptedOffers = items.filter((offer) => String(offer?.status || '').toLowerCase() === 'accepted')
          for (const offer of initializedAcceptedOffers) {
            const offerId = String(offer?.offer_id || '')
            if (!offerId) continue
            try {
              const payload = await fetchShippingLabelsRemote({
                apiBaseUrl,
                apiKey: clerkEnabled ? '' : apiKey.trim(),
                bearerToken,
                offerId,
              })
              const shipments = Array.isArray(payload?.shipments) ? payload.shipments : []
              shippingSignatureByOfferRef.current.set(offerId, shippingLabelSignature(shipments))
              if (inboxActive) setShippingLabelsByOffer((prev) => ({ ...prev, [offerId]: shipments }))
            } catch {}
          }
          return
        }
        if (newOffers.length > 0) {
          setTradeNotification({
            id: newOffers.map((offer) => offer.offer_id).join(','),
            message: incomingTradeNotificationText(newOffers),
          })
          newOffers.forEach((offer) => {
            addAppNotification({
              type: 'trade-received',
              title: 'Trade offer received',
              body: incomingTradeNotificationText([offer]),
              actionTab: 'inbox',
              entityId: offer?.offer_id || '',
            })
          })
        }
        acceptedOffers.forEach((offer) => {
          addAppNotification({
            type: 'trade-accepted',
            title: 'Trade accepted',
            body: `Trade accepted for ${notificationOfferTitle(offer)}.`,
            actionTab: 'inbox',
            entityId: offer?.offer_id || '',
          })
        })
        const acceptedForShipping = items.filter((offer) => String(offer?.status || '').toLowerCase() === 'accepted')
        for (const offer of acceptedForShipping) {
          const offerId = String(offer?.offer_id || '')
          if (!offerId) continue
          try {
            const payload = await fetchShippingLabelsRemote({
              apiBaseUrl,
              apiKey: clerkEnabled ? '' : apiKey.trim(),
              bearerToken,
              offerId,
            })
            const shipments = Array.isArray(payload?.shipments) ? payload.shipments : []
            const previousSignature = shippingSignatureByOfferRef.current.get(offerId) || ''
            const nextSignature = shippingLabelSignature(shipments)
            const hadLabel = previousSignature.includes('label:yes')
            const hasLabel = nextSignature.includes('label:yes')
            shippingSignatureByOfferRef.current.set(offerId, nextSignature)
            if (inboxActive) setShippingLabelsByOffer((prev) => ({ ...prev, [offerId]: shipments }))
            if (hasLabel && !hadLabel) {
              addAppNotification({
                type: 'shipping-label',
                title: 'Shipping label created',
                body: `Shipping label is ready for ${notificationOfferTitle(offer)}.`,
                actionTab: 'inbox',
                entityId: offerId,
              })
            }
          } catch {}
        }
      } catch {
        // Background notification polling should not interrupt the current screen.
      }
    }

    pollPendingOffers()
    const timer = window.setInterval(pollPendingOffers, 15000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken, loadIncomingOffers, offerStatusFilter, primaryShippingAddressId])
  const safeActiveShippingAddressIdx = Math.max(0, Math.min(activeShippingAddressIdx, shippingAddresses.length - 1))
  const activeShippingAddress = shippingAddresses[safeActiveShippingAddressIdx] || shippingAddresses[0] || emptyShippingAddress()
  const primaryProfileAddress = shippingAddresses[0] || emptyShippingAddress()

  function updateActiveShippingAddress(patch) {
    setProfileQuiz((prev) => {
      const nextAddresses = normalizeShippingAddresses(prev.shipping_addresses, prev)
      const idx = Math.max(0, Math.min(activeShippingAddressIdx, nextAddresses.length - 1))
      nextAddresses[idx] = { ...nextAddresses[idx], ...patch }
      return { ...prev, shipping_addresses: nextAddresses }
    })
  }

  function updatePrimaryShippingAddress(patch) {
    profileSetupDirtyRef.current = true
    setProfileQuiz((prev) => {
      const nextAddresses = normalizeShippingAddresses(prev.shipping_addresses, prev)
      nextAddresses[0] = { ...nextAddresses[0], ...patch, is_default: true }
      return {
        ...prev,
        shipping_addresses: nextAddresses,
        shipping_full_name: nextAddresses[0].full_name || '',
        shipping_address_line1: nextAddresses[0].address_line1 || '',
        shipping_address_line2: nextAddresses[0].address_line2 || '',
        shipping_city: nextAddresses[0].city || '',
        shipping_state: nextAddresses[0].state || '',
        shipping_postal_code: nextAddresses[0].postal_code || '',
        shipping_country: nextAddresses[0].country || '',
      }
    })
  }

  function toggleProfileArrayField(field, value, max = null) {
    profileSetupDirtyRef.current = true
    setProfileQuiz((prev) => {
      const current = Array.isArray(prev[field]) ? prev[field] : []
      const selected = current.includes(value)
      const next = selected
        ? current.filter((x) => x !== value)
        : (max && current.length >= max ? current : [...current, value])
      return { ...prev, [field]: next }
    })
  }

  function profilePayloadForSave() {
    const normalizedAddresses = normalizeShippingAddresses(profileQuiz.shipping_addresses, profileQuiz)
    const primaryAddress = normalizedAddresses[0] || emptyShippingAddress()
    return {
      ...profileQuiz,
      first_name: String(profileQuiz.first_name || profileData?.firstName || '').trim(),
      last_name: String(profileQuiz.last_name || profileData?.lastName || '').trim(),
      email: String(profileQuiz.email || profileData?.email || session?.email || '').trim().toLowerCase(),
      shipping_email: String(profileQuiz.shipping_email || profileQuiz.email || profileData?.email || session?.email || '').trim().toLowerCase() || null,
      shipping_phone: String(profileQuiz.shipping_phone || '').trim() || null,
      birthday: profileQuiz.birthday || null,
      tops_size: serializeMultiSizeValue(profileQuiz.tops_size),
      dresses_size: serializeMultiSizeValue(profileQuiz.dresses_size),
      bottoms_size: serializeMultiSizeValue(profileQuiz.bottoms_size),
      shoes_size: serializeMultiSizeValue(profileQuiz.shoes_size),
      category_preferences: Array.isArray(profileQuiz.category_preferences) ? profileQuiz.category_preferences : [],
      style_descriptors: Array.isArray(profileQuiz.style_descriptors) ? profileQuiz.style_descriptors : [],
      jouft_goals: Array.isArray(profileQuiz.jouft_goals) ? profileQuiz.jouft_goals : [],
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
  }

  function applySavedProfileQuiz(saved) {
    profileSetupDirtyRef.current = false
    setSubscriptionSelectionDirty(false)
    const savedShippingAddresses = normalizeShippingAddresses(saved?.shipping_addresses, saved)
    setProfileQuiz({
      first_name: saved?.first_name || profileData?.firstName || '',
      last_name: saved?.last_name || profileData?.lastName || '',
      email: saved?.email || profileData?.email || session?.email || '',
      shipping_email: saved?.shipping_email || profileData?.email || session?.email || '',
      shipping_phone: saved?.shipping_phone || profileData?.phone || '',
      gender: saved?.gender || '',
      birthday: saved?.birthday || '',
      tops_size: normalizeMultiSizeValue(saved?.tops_size),
      dresses_size: normalizeMultiSizeValue(saved?.dresses_size),
      bottoms_size: normalizeMultiSizeValue(saved?.bottoms_size),
      shoes_size: normalizeMultiSizeValue(saved?.shoes_size),
      category_preferences: Array.isArray(saved?.category_preferences) ? saved.category_preferences : [],
      style_descriptors: Array.isArray(saved?.style_descriptors) ? saved.style_descriptors : [],
      jouft_goals: Array.isArray(saved?.jouft_goals) ? saved.jouft_goals : [],
      shipping_full_name: savedShippingAddresses[0]?.full_name || '',
      shipping_address_line1: savedShippingAddresses[0]?.address_line1 || '',
      shipping_address_line2: savedShippingAddresses[0]?.address_line2 || '',
      shipping_city: savedShippingAddresses[0]?.city || '',
      shipping_state: savedShippingAddresses[0]?.state || '',
      shipping_postal_code: savedShippingAddresses[0]?.postal_code || '',
      shipping_country: savedShippingAddresses[0]?.country || '',
      shipping_addresses: savedShippingAddresses,
      subscription_plan: normalizeSelectableSubscriptionPlanId(saved?.subscription_plan),
      subscription_billing_cycle: normalizeBillingCycle(saved?.subscription_billing_cycle),
      subscription_status: saved?.subscription_status || '',
      subscription_renewal_date: saved?.subscription_renewal_date || '',
      payment_methods: Array.isArray(saved?.payment_methods) ? saved.payment_methods : [],
    })
    setActiveShippingAddressIdx(0)
    setAddressSuggestions([])
    setAddressAutocompleteActive(false)
  }

  async function saveProfileQuiz() {
    const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
    const saved = await saveProfileQuizRemote({
      apiBaseUrl,
      apiKey: clerkEnabled ? '' : apiKey.trim(),
      bearerToken,
      payload: profilePayloadForSave(),
    })
    applySavedProfileQuiz(saved)
    setProfileSaveMsg('Profile saved.')
    return saved
  }

  function requestSubscriptionConfirmation(details) {
    return new Promise((resolve) => {
      subscriptionConfirmResolverRef.current = resolve
      setSubscriptionConfirmRequest(details)
    })
  }

  function resolveSubscriptionConfirmation(confirmed) {
    const resolver = subscriptionConfirmResolverRef.current
    subscriptionConfirmResolverRef.current = null
    setSubscriptionConfirmRequest(null)
    if (resolver) resolver(Boolean(confirmed))
  }

  async function activateSelectedSubscription() {
    const selectedPlan = SUBSCRIPTION_PLANS.find((plan) => plan.id === selectedSubscriptionPlanId) || SUBSCRIPTION_PLANS[0]
    if (!selectedPlan) {
      setProfileSaveMsg('Select a subscription plan.')
      return null
    }
    const billingCycle = selectedBillingCycle
    const annualTotal = Math.round(selectedPlan.monthlyPrice * 12 * 0.9)
    const amount = billingCycle === 'annual' ? annualTotal : selectedPlan.monthlyPrice
    const selectedPaymentMethod = paymentMethods.find((method) => method.payment_method_id === selectedSubscriptionPaymentMethodId)
      || paymentMethods.find((method) => method.is_default)
      || paymentMethods[0]

    if (amount > 0 && !selectedPaymentMethod) {
      setProfileSaveMsg('Add a payment method before activating your subscription.')
      return null
    }

    const paymentLabel = selectedPaymentMethod?.label
      || [selectedPaymentMethod?.brand, selectedPaymentMethod?.last4 ? `•••• ${selectedPaymentMethod.last4}` : ''].filter(Boolean).join(' ')
      || 'Selected payment method'
    const amountLabel = `$${amount}${billingCycle === 'annual' ? ' / year' : ' / month'}`
    if (amount > 0) {
      const confirmed = await requestSubscriptionConfirmation({
        planName: selectedPlan.name,
        amountLabel,
        billingCycle,
        paymentLabel,
      })
      if (!confirmed) {
        setProfileSaveMsg('Subscription activation canceled.')
        return null
      }
    }

    const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
    const activated = await activateSubscriptionRemote({
      apiBaseUrl,
      apiKey: clerkEnabled ? '' : apiKey.trim(),
      bearerToken,
      plan: selectedSubscriptionPlanId,
      billingCycle,
      paymentMethodId: amount > 0 ? selectedPaymentMethod?.payment_method_id || '' : '',
    })
    const activatedStatus = String(activated?.status || '').trim().toLowerCase()
    if (amount > 0 && !['active', 'trialing'].includes(activatedStatus)) {
      const statusLabel = activatedStatus ? titleCase(activatedStatus) : 'not active'
      throw new Error(`Payment was not processed. Subscription status is ${statusLabel}. Please update your payment details.`)
    }
    setProfileQuiz((prev) => ({
      ...prev,
      subscription_plan: normalizeSubscriptionPlanId(activated?.plan || selectedSubscriptionPlanId),
      subscription_billing_cycle: normalizeBillingCycle(activated?.billing_cycle || billingCycle),
      subscription_status: activated?.status || prev.subscription_status || '',
      subscription_renewal_date: activated?.renewal_date || '',
    }))
    setSubscriptionSelectionDirty(false)
    setProfileSaveMsg(activated?.message || 'Subscription active.')
    return activated
  }

  function addShippingAddress() {
    const newAddress = { ...emptyShippingAddress(), label: `Address ${shippingAddresses.length + 1}` }
    const updated = [...shippingAddresses, newAddress]
    setProfileQuiz((prev) => ({ ...prev, shipping_addresses: updated }))
    setActiveShippingAddressIdx(updated.length - 1)
    setAddressSuggestions([])
    setAddressAutocompleteActive(false)
  }

  function removeActiveShippingAddress() {
    if (shippingAddresses.length <= 1) {
      setProfileQuiz((prev) => ({ ...prev, shipping_addresses: [emptyShippingAddress()] }))
      setActiveShippingAddressIdx(0)
      setAddressSuggestions([])
      setAddressAutocompleteActive(false)
      return
    }
    const idx = safeActiveShippingAddressIdx
    const updated = shippingAddresses.filter((_, i) => i !== idx)
    setProfileQuiz((prev) => ({ ...prev, shipping_addresses: updated }))
    setActiveShippingAddressIdx(Math.max(0, idx - 1))
    setAddressSuggestions([])
    setAddressAutocompleteActive(false)
  }

  useEffect(() => {
    let cancelled = false
    const line1 = (activeShippingAddress?.address_line1 || '').trim()
    if (!addressAutocompleteActive) {
      setAddressSuggestions([])
      return undefined
    }
    if (line1.length < 3) {
      setAddressSuggestions([])
      return undefined
    }
    const timer = setTimeout(async () => {
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const suggestions = await fetchGooglePlacesAddressSuggestionsRemote({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          q: line1,
          city: '',
          state: '',
          postalCode: '',
        })
        if (!cancelled) setAddressSuggestions(suggestions.slice(0, 5))
      } catch {
        if (!cancelled) setAddressSuggestions([])
      }
    }, 150)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [
    activeShippingAddress?.address_line1,
    addressAutocompleteActive,
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
      const trimmed = url.trim()
      const baseUrl = apiBaseUrl.replace(/\/$/, '')
      if (/^https?:\/\//i.test(trimmed)) {
        try {
          const parsed = new URL(trimmed)
          if (parsed.pathname.startsWith('/v1/images/') && parsed.hostname.endsWith('.elb.amazonaws.com')) {
            return `${baseUrl}${parsed.pathname}`
          }
        } catch (err) {
          return trimmed
        }
        return trimmed
      }
      if (trimmed.startsWith('/')) return `${baseUrl}${trimmed}`
      return null
    }
    const listedImages = Array.isArray(item.images)
      ? item.images.map(resolveUrl).filter(Boolean)
      : []
    const listedCover = resolveUrl(item.image)
	    const fromAnalysisUploads = Array.isArray(item.analysis?.uploaded_images)
	      ? item.analysis.uploaded_images.map((u) => resolveUrl(u?.image_url)).filter(Boolean)
	      : []
	    const normalizedListedImages = Array.isArray(item.listed_images)
	      ? item.listed_images.map((entry, idx) => {
	        if (!entry || typeof entry !== 'object') return null
	        const display = resolveUrl(entry.d_img || entry.display_image || entry.image || entry.p_img)
	        const original = resolveUrl(entry.p_img || entry.original_image || entry.source_image) || display
	        if (!display) return null
	        return { p_img: original, d_img: display, is_hero: Boolean(entry.is_hero) || display === listedCover || idx === 0 }
	      }).filter(Boolean)
	      : []
	    const targetCount = fromAnalysisUploads.length > 0 ? fromAnalysisUploads.length : null
	    let normalizedImages = normalizedListedImages.length > 0
	      ? normalizedListedImages.map((entry) => entry.d_img)
	      : listedImages.length > 0
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
      ownerSubject: ownerSubjectRaw || null,
      title: item.title || 'Untitled listing',
      mode: 'trade',
      category: item.category || 'unknown',
      brand: item.brand || 'unknown',
      condition: item.condition || 'n/a',
      size: typeof item.size === 'string' ? item.size : '',
      estimatedValue: Number(item.estimated_value ?? item.estimatedValue ?? 0),
      city: item.city || 'Your area',
	      image: normalizedImages[0] || null,
	      images: normalizedImages,
	      listedImages: normalizedListedImages.length > 0
	        ? normalizedListedImages
	        : normalizedImages.map((url, idx) => ({ p_img: url, d_img: url, is_hero: idx === 0 })),
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
    const allowedConditions = ['NewWithTags', 'New', 'LikeNew']
	    const uploadedImageUrls = getUploadedImageUrlsFromAnalysis(listing.analysis)
	    const listingImageUrls = persistableImageUrls([...(Array.isArray(listing.images) ? listing.images : []), listing.image])
	    const imageUrls = listingImageUrls.length > 0 ? listingImageUrls : uploadedImageUrls
	    const listedImages = Array.isArray(listing.listedImages)
	      ? listing.listedImages
	        .map((entry, idx) => {
	          if (!entry || typeof entry !== 'object') return null
	          const display = persistableImageUrls([entry.d_img || entry.display_image || entry.image])[0]
	          const original = persistableImageUrls([entry.p_img || entry.original_image || entry.source_image])[0] || display
	          if (!display) return null
	          return { p_img: original, d_img: display, is_hero: Boolean(entry.is_hero) || display === imageUrls[0] || idx === 0 }
	        })
	        .filter(Boolean)
	      : imageUrls.map((url, idx) => ({ p_img: uploadedImageUrls[idx] || url, d_img: url, is_hero: idx === 0 }))
    const normalizedCategory = allowedCategories.includes(listing.category)
      ? listing.category
      : (allowedCategories.includes(listing.analysis?.category) ? listing.analysis.category : 'handbag')
    const normalizedCondition = allowedConditions.includes(listing.condition)
      ? listing.condition
      : 'LikeNew'
    return {
      title: listing.title || 'Untitled listing',
      mode: 'trade',
      category: normalizedCategory,
      brand: listing.brand || 'unknown',
      condition: normalizedCondition,
      size: listing.size || null,
      estimated_value: Number(listing.estimatedValue || 0),
      city: listing.city || 'Your area',
	      image: imageUrls[0] || null,
	      images: imageUrls,
	      listed_images: listedImages,
      wants: listing.wants || 'Open to similar-value offers',
      tags: Array.isArray(listing.tags) ? listing.tags : [],
      source_item_id: listing.sourceItemId || null,
      analysis: listing.analysis || null,
      status: listing.status || 'Review',
      description: listing.description || '',
    }
  }

  const loadListings = useCallback(async ({ showLoading = true } = {}) => {
    const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
    if (showLoading) {
      setMyListingsLoading(true)
      setMarketListingsLoading(true)
    }
    try {
      const [myItems, marketItems] = await Promise.all([
        fetchMyListings({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          limit: LISTINGS_PAGE_SIZE,
          offset: 0,
        }),
        fetchMarketplaceListings({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          limit: LISTINGS_PAGE_SIZE,
          offset: 0,
        }),
      ])
      setMyListings(myItems.items.map(fromRemoteListing).filter(Boolean))
      setMyListingsHasMore(myItems.hasMore)
      setMyListingsNextOffset(myItems.nextOffset || 0)
      setMarketListings(marketItems.items.map(fromRemoteListing).filter(Boolean))
      setMarketListingsHasMore(marketItems.hasMore)
      setMarketListingsNextOffset(marketItems.nextOffset || 0)
    } catch {
      // Keep current listings visible if a background refresh fails.
    } finally {
      if (showLoading) {
        setMyListingsLoading(false)
        setMarketListingsLoading(false)
      }
    }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken])

  const loadMoreMyListings = useCallback(async () => {
    if (myListingsPageLoading || myListingsLoading || !myListingsHasMore) return
    setMyListingsPageLoading(true)
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      const page = await fetchMyListings({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        limit: LISTINGS_PAGE_SIZE,
        offset: myListingsNextOffset,
      })
      const nextItems = page.items.map(fromRemoteListing).filter(Boolean)
      setMyListings((prev) => {
        const seen = new Set(prev.map((item) => String(item?.id || '')))
        return [...prev, ...nextItems.filter((item) => {
          const id = String(item?.id || '')
          if (!id || seen.has(id)) return false
          seen.add(id)
          return true
        })]
      })
      setMyListingsHasMore(page.hasMore)
      setMyListingsNextOffset(page.nextOffset || 0)
    } catch {
      // Keep existing listings visible when lazy loading fails.
    } finally {
      setMyListingsPageLoading(false)
    }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken, myListingsHasMore, myListingsLoading, myListingsNextOffset, myListingsPageLoading])

  const loadMoreMarketListings = useCallback(async () => {
    if (marketListingsPageLoading || marketListingsLoading || !marketListingsHasMore) return
    setMarketListingsPageLoading(true)
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      const page = await fetchMarketplaceListings({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        limit: LISTINGS_PAGE_SIZE,
        offset: marketListingsNextOffset,
      })
      const nextItems = page.items.map(fromRemoteListing).filter(Boolean)
      setMarketListings((prev) => {
        const seen = new Set(prev.map((item) => String(item?.id || '')))
        return [...prev, ...nextItems.filter((item) => {
          const id = String(item?.id || '')
          if (!id || seen.has(id)) return false
          seen.add(id)
          return true
        })]
      })
      setMarketListingsHasMore(page.hasMore)
      setMarketListingsNextOffset(page.nextOffset || 0)
    } catch {
      // Keep existing listings visible when lazy loading fails.
    } finally {
      setMarketListingsPageLoading(false)
    }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken, marketListingsHasMore, marketListingsLoading, marketListingsNextOffset, marketListingsPageLoading])

  function scheduleListingRefreshes() {
    if (typeof window === 'undefined') return
    window.setTimeout(() => { void loadListings({ showLoading: false }) }, 4000)
    window.setTimeout(() => { void loadListings({ showLoading: false }) }, 10000)
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setMyListingsLoading(true)
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const items = await fetchMyListings({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          limit: LISTINGS_PAGE_SIZE,
          offset: 0,
        })
        if (!cancelled) {
          setMyListings(items.items.map(fromRemoteListing).filter(Boolean))
          setMyListingsHasMore(items.hasMore)
          setMyListingsNextOffset(items.nextOffset || 0)
        }
      } catch {
        // Keep local state fallback if API fetch fails.
      } finally {
        if (!cancelled) setMyListingsLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [apiBaseUrl, apiKey, clerkEnabled, getBearerToken])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setMarketListingsLoading(true)
      try {
        const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
        const items = await fetchMarketplaceListings({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          limit: LISTINGS_PAGE_SIZE,
          offset: 0,
        })
        if (!cancelled) {
          setMarketListings(items.items.map(fromRemoteListing).filter(Boolean))
          setMarketListingsHasMore(items.hasMore)
          setMarketListingsNextOffset(items.nextOffset || 0)
        }
      } catch {
        // Keep local state fallback if API fetch fails.
      } finally {
        if (!cancelled) setMarketListingsLoading(false)
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

  const modalPreviewUrls = listingModalMode === 'edit'
    ? [...editPreviewUrls, ...previewUrls].slice(0, 6)
    : previewUrls.slice(0, 6)

  function moveArrayItemToFront(list, index) {
    const items = Array.isArray(list) ? list.filter(Boolean) : []
    if (items.length < 2) return items
    const safeIndex = Math.max(0, Math.min(index, items.length - 1))
    if (safeIndex === 0) return items
    const next = [...items]
    const [selected] = next.splice(safeIndex, 1)
    return [selected, ...next]
  }

  function orderedCreateImagesForSave() {
    return moveArrayItemToFront(images.slice(0, 6), selectedCreateImageIndex)
  }

  function orderedEditExistingImageUrlsForSave() {
    const existingCount = editPreviewUrls.length
    if (selectedEditHeroImageIndex === null || selectedEditHeroImageIndex >= existingCount) return persistableImageUrls(editPreviewUrls)
    return persistableImageUrls(moveArrayItemToFront(editPreviewUrls, selectedEditHeroImageIndex))
  }

  function orderedEditNewImagesForSave() {
    const existingCount = editPreviewUrls.length
    if (selectedEditHeroImageIndex === null || selectedEditHeroImageIndex < existingCount) return images
    return moveArrayItemToFront(images, selectedEditHeroImageIndex - existingCount)
  }

  useEffect(() => {
    if (listingModalMode !== 'edit') return
    setSelectedEditImageIndex((idx) => {
      if (modalPreviewUrls.length <= 0) return 0
      return Math.max(0, Math.min(idx, modalPreviewUrls.length - 1))
    })
    setSelectedEditHeroImageIndex((idx) => {
      if (idx === null) return null
      if (modalPreviewUrls.length <= 0) return null
      return Math.max(0, Math.min(idx, modalPreviewUrls.length - 1))
    })
  }, [listingModalMode, modalPreviewUrls.length])

  useEffect(() => {
    setSelectedCreateImageIndex((idx) => {
      if (previewUrls.length <= 0) return 0
      return Math.max(0, Math.min(idx, previewUrls.length - 1))
    })
  }, [previewUrls.length])

  function originalListingImageUrls(listing) {
    return persistableImageUrls(Array.isArray(listing?.images) && listing.images.length > 0
      ? listing.images
      : [listing?.image].filter(Boolean))
  }

  function resolveListingImageUrl(url) {
    const raw = String(url || '').trim()
    if (!raw) return ''
    if (/^https?:\/\//i.test(raw)) return raw
    if (raw.startsWith('/')) return `${apiBaseUrl.replace(/\/$/, '')}${raw}`
    return raw
  }

  function waitForImageUrl(url) {
    const resolved = resolveListingImageUrl(url)
    if (!resolved || typeof window === 'undefined') return Promise.resolve(false)
    return new Promise((resolve) => {
      const img = new window.Image()
      const timer = window.setTimeout(() => resolve(false), 5000)
      img.onload = () => {
        window.clearTimeout(timer)
        resolve(true)
      }
      img.onerror = () => {
        window.clearTimeout(timer)
        resolve(false)
      }
      img.src = resolved
    })
  }

  async function waitForUploadedListingImages(imageUrls) {
    const urls = persistableImageUrls(imageUrls)
    if (urls.length < 1) return false
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const results = await Promise.all(urls.map((url) => waitForImageUrl(url)))
      if (results.every(Boolean)) return true
      await new Promise((resolve) => window.setTimeout(resolve, 350))
    }
    return false
  }

  async function listingImageUrlToFile(url, index) {
    const resolved = resolveListingImageUrl(url)
    const resp = await fetch(resolved)
    if (!resp.ok) throw new Error(`Could not load existing listing image ${index + 1} for analysis.`)
    const blob = await resp.blob()
    const contentType = blob.type || 'image/jpeg'
    const ext = contentType.includes('png') ? 'png' : contentType.includes('webp') ? 'webp' : 'jpg'
    return new File([blob], `listing-image-${index + 1}.${ext}`, { type: contentType })
  }

  function mergedEditImageUrlsForSave(existingImageUrls, uploadedImageUrls) {
    const existing = persistableImageUrls(existingImageUrls)
    const uploaded = persistableImageUrls(uploadedImageUrls)
    if (selectedEditHeroImageIndex !== null && selectedEditHeroImageIndex >= editPreviewUrls.length && uploaded.length > 0) {
      return persistableImageUrls([uploaded[0], ...existing, ...uploaded.slice(1)]).slice(0, 6)
    }
    return persistableImageUrls([...existing, ...uploaded]).slice(0, 6)
  }

  async function analysisFilesForEdit(existingImageUrls, newImages = images) {
    const keptFiles = await Promise.all(existingImageUrls.map((url, index) => listingImageUrlToFile(url, index)))
    if (selectedEditHeroImageIndex !== null && selectedEditHeroImageIndex >= editPreviewUrls.length && newImages.length > 0) {
      const safeNewIndex = Math.max(0, Math.min(selectedEditHeroImageIndex - editPreviewUrls.length, newImages.length - 1))
      const remainingNewImages = newImages.filter((_, idx) => idx !== safeNewIndex)
      return [newImages[safeNewIndex], ...keptFiles, ...remainingNewImages].slice(0, 6)
    }
    return [...keptFiles, ...newImages].slice(0, 6)
  }

  function editPublishRequiresAnalysis(listing) {
    if (!listing) return false
    const originalImages = originalListingImageUrls(listing)
    const keptImages = orderedEditExistingImageUrlsForSave()
    const imagesChanged = images.length > 0 || !sameStringList(keptImages, originalImages)
    const originalCondition = String(listing.condition || 'n/a').trim()
    const nextCondition = String(userCondition || listing.condition || 'n/a').trim()
    return imagesChanged || nextCondition !== originalCondition
  }

  function buildEditedListingPayload(listing, overrides = {}) {
    if (!listing) return null
    const imageUrls = persistableImageUrls(
      overrides.images || (editPreviewUrls.length > 0 || images.length > 0 ? orderedEditExistingImageUrlsForSave() : originalListingImageUrls(listing)),
    )
    const nextCondition = userCondition || listing.condition || 'n/a'
    const nextBrand = overrides.brand || listing.brand || 'unknown'
    const nextMode = 'trade'
    return {
      ...listing,
      ...overrides,
      title: (itemTitle || '').trim() || overrides.title || listing.title,
      description: (itemDescription || '').trim() || meaningfulDescription(overrides.description) || meaningfulDescription(listing.description) || '',
      wants: (tradeNotes || '').trim() || overrides.wants || listing.wants || 'Open to similar-value offers',
      category: category || overrides.category || listing.category || 'unknown',
      condition: overrides.condition || nextCondition,
      size: itemSize || overrides.size || listing.size || null,
      estimatedValue: Number(overrides.estimatedValue ?? listing.estimatedValue ?? 0),
      image: imageUrls[0] || overrides.image || listing.image || null,
      images: imageUrls.length > 0 ? imageUrls : (Array.isArray(overrides.images) ? overrides.images : listing.images || []),
      brand: nextBrand,
      mode: nextMode,
      tags: overrides.tags || [overrides.condition || nextCondition, nextBrand, String(nextMode || '').replace('_', '/')].filter(Boolean),
    }
  }

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
      if (getCrossOwnerMatches(item).length === 0) return false
      if (!q) return true
      return `${item.title} ${item.brand} ${item.category} ${item.city} ${item.wants}`.toLowerCase().includes(q)
    })
  }, [allListings, deferredMarketSearch])
  const marketplaceNavCount = useMemo(
    () => allListings.filter((item) => (
      String(item?.status || '').toLowerCase() === 'active'
      && getCrossOwnerMatches(item).length > 0
    )).length,
    [allListings],
  )
  const marketMatchesTarget = useMemo(
    () => allListings.find((x) => x.id === marketMatchesTargetId) || null,
    [allListings, marketMatchesTargetId]
  )
  const similarListingsForTarget = useMemo(() => {
    if (!marketMatchesTarget) return []
    return getCrossOwnerMatches(marketMatchesTarget)
  }, [marketMatchesTarget])
  useEffect(() => {
    if (!marketMatchesTarget) return
    function onKeyDown(e) {
      if (e.key === 'Escape') setMarketMatchesTargetId(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [marketMatchesTarget])

  useEffect(() => {
    if (!zoomedListingImage) return
    function onKeyDown(e) {
      if (e.key === 'Escape') closeZoomedListingImage()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [zoomedListingImage])

  const latestActiveListings = useMemo(
    () => allListings.filter((item) => String(item?.status || '').toLowerCase() === 'active').slice(0, 6),
    [allListings],
  )
  const showFreshListingsStrip = false

  useEffect(() => {
    if (filteredListings.length === 0) {
      setSelectedMarketListingIndex(null)
      return
    }
    if (selectedMarketListingIndex == null) return
    setSelectedMarketListingIndex((prev) => {
      if (prev == null) return null
      return Math.max(0, Math.min(prev, filteredListings.length - 1))
    })
  }, [filteredListings, selectedMarketListingIndex])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (activeTab !== 'market') return
    const requestedListingId = listingIdFromLocation()
    if (!requestedListingId) return
    const idx = filteredListings.findIndex((entry) => String(entry?.id || entry?.listing_id || '') === requestedListingId)
    if (idx >= 0 && idx !== selectedMarketListingIndex) {
      setSelectedMarketListingIndex(idx)
      setSelectedMarketImageIndex(0)
    }
  }, [activeTab, filteredListings, selectedMarketListingIndex])

  function openMarketplaceListingDetails(item) {
    const idx = filteredListings.findIndex((entry) => entry?.id === item?.id)
    if (idx >= 0) {
      setSelectedMarketListingIndex(idx)
      setSelectedMarketImageIndex(0)
      if (typeof window !== 'undefined') {
        window.history.pushState({}, '', marketListingHref(item?.id || item?.listing_id))
      }
    }
  }

  function toggleMarketplaceLike(listingId) {
    const normalizedId = String(listingId || '').trim()
    if (!normalizedId) return
    const alreadyLiked = likedListingIds.includes(normalizedId)
    setLikedListingIds((prev) => (
      prev.includes(normalizedId)
        ? prev.filter((id) => id !== normalizedId)
        : [...prev, normalizedId]
    ))
    if (!alreadyLiked) {
      ;(async () => {
        try {
          const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
          await likeListingRemote({
            apiBaseUrl,
            apiKey: clerkEnabled ? '' : apiKey.trim(),
            bearerToken,
            listingId: normalizedId,
          })
        } catch {}
      })()
    }
  }

  const suggestedTrades = useMemo(() => {
    const target = Number(analysisResult?.valuation?.estimated_value || 0)
    if (!target) return []
    return allListings
      .map((item) => ({ ...item, valueGap: Math.abs(item.estimatedValue - target) }))
      .sort((a, b) => a.valueGap - b.valueGap)
      .slice(0, 6)
  }, [allListings, analysisResult])

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

  const reviewListing = useMemo(() => {
    const requestedId = reviewListingId || (activeTab === 'review_listing' ? listingIdFromLocation() : '')
    if (!requestedId) return null
    return myListings.find((item) => String(item?.id || '') === String(requestedId)) || null
  }, [activeTab, myListings, reviewListingId])

  const reviewListingGallery = useMemo(
    () => (reviewListing ? getListingGallery(reviewListing) : []),
    [reviewListing],
  )

  useEffect(() => {
    if (activeTab !== 'review_listing') return
    const requestedId = listingIdFromLocation()
    if (requestedId && requestedId !== reviewListingId) {
      setReviewListingId(requestedId)
    }
  }, [activeTab, reviewListingId])

  useEffect(() => {
    setSelectedReviewImageIndex(0)
  }, [reviewListing?.id])

  useEffect(() => {
    setSelectedReviewImageIndex((idx) => {
      if (reviewListingGallery.length <= 0) return 0
      return Math.max(0, Math.min(idx, reviewListingGallery.length - 1))
    })
  }, [reviewListingGallery.length])

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
    if (completeProfileShippingAddresses.length === 0) {
      setTradeOfferError('Add a complete shipping address in Profile before sending a trade offer.')
      return
    }
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
      removeSentOfferMatches(tradeComposerTarget.id, tradeOfferListingIds)
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

  function openTradeDetailListing(listing) {
    setTradeDetailListing(listing || null)
    setTradeDetailImageIndex(0)
  }

  function openZoomedListingImage(image) {
    setZoomedListingImage(image || null)
    setZoomedListingImageScale(0.5)
  }

  function closeZoomedListingImage() {
    setZoomedListingImage(null)
    setZoomedListingImageScale(0.5)
  }

  function adjustZoomedListingImageScale(delta) {
    setZoomedListingImageScale((current) => {
      const next = Math.round((current + delta) * 100) / 100
      return Math.max(0.5, Math.min(3, next))
    })
  }

  async function respondToOffer(offerId, status, receiveAddress = null, selectedOfferedListingId = null) {
    const currentOffer = incomingOffers.find((offer) => offer.offer_id === offerId) || null
    try {
      if (status === 'accepted' && completeProfileShippingAddresses.length === 0) {
        showShippingAddressRequiredAlert('Add shipping address to profile.')
        return
      }
      if (status === 'accepted' && !receiveAddress) {
        showShippingAddressRequiredAlert('Select a shipping address before accepting trade.')
        return
      }
      if (status === 'accepted') {
        const offeredChoices = Array.isArray(currentOffer?.offered_listings) && currentOffer.offered_listings.length > 0
          ? currentOffer.offered_listings
          : (currentOffer?.offered_listing ? [currentOffer.offered_listing] : [])
        const selectedId = selectedOfferedListingId || (offeredChoices.length === 1 ? listingRecordId(offeredChoices[0]) : '')
        if (!selectedId || !offeredChoices.some((listing) => listingRecordId(listing) === selectedId)) {
          setSavedListingNotice('Select one offered item to accept for this trade.')
          return
        }
        selectedOfferedListingId = selectedId
      }
      if (status === 'accepted') {
        const selectedOfferedListing = (Array.isArray(currentOffer?.offered_listings) ? currentOffer.offered_listings : [])
          .find((listing) => listingRecordId(listing) === selectedOfferedListingId) || currentOffer?.offered_listing || null
        let acceptanceQuote = shippingQuoteByOffer[offerId] || null
        if (!shippingQuoteByOffer[offerId]) {
          try {
            acceptanceQuote = await loadShippingQuoteForOffer(offerId)
          } catch (err) {
            acceptanceQuote = {
              status: 'unavailable',
              debug: err.message || 'Shipping quote unavailable',
            }
            setShippingQuoteByOffer((prev) => ({
              ...prev,
              [offerId]: acceptanceQuote,
            }))
          }
        }
        const confirmed = await confirmTradeAcceptance(currentOffer, acceptanceQuote, selectedOfferedListing)
        if (!confirmed) return
      }
      setOfferActionBusyById((prev) => ({ ...prev, [offerId]: status }))
      setSavedListingNotice(status === 'accepted' ? 'Accepting trade...' : 'Updating trade offer...')
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      const updatedOffer = await actionOfferRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        offerId,
        status,
        receiveAddress,
        selectedOfferedListingId,
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
          limit: LISTINGS_PAGE_SIZE,
          offset: 0,
        })
        const marketItems = await fetchMarketplaceListings({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          limit: LISTINGS_PAGE_SIZE,
          offset: 0,
        })
        setMyListings(myItems.items.map(fromRemoteListing).filter(Boolean))
        setMyListingsHasMore(myItems.hasMore)
        setMyListingsNextOffset(myItems.nextOffset || 0)
        setMarketListings(marketItems.items.map(fromRemoteListing).filter(Boolean))
        setMarketListingsHasMore(marketItems.hasMore)
        setMarketListingsNextOffset(marketItems.nextOffset || 0)
        if (updatedOffer?.status === 'accepted') {
          setSavedListingNotice('Trade accepted successfully. This trade is now in Accepted.')
          setOfferStatusFilter('accepted')
          try {
            await loadShippingLabelsForOffer(offerId)
          } catch {}
        } else if (actorAccepted) {
          setSavedListingNotice('Your acceptance is recorded. Waiting for the other user to accept.')
          setOfferStatusFilter('accepted')
        }
      }
      if (status === 'declined') {
        setSavedListingNotice('Trade offer declined.')
      }
      const nextOfferStatusFilter = status === 'accepted' ? 'accepted' : offerStatusFilter
      const refreshed = await fetchIncomingOffersRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        status: nextOfferStatusFilter,
        limit: 50,
      })
      setIncomingOffers(Array.isArray(refreshed?.items) ? refreshed.items : [])
      setOffersActorSubject(typeof refreshed?.actor?.subject === 'string' ? refreshed.actor.subject : '')
    } catch (err) {
      setSavedListingNotice(err.message || 'Failed to update trade offer.')
    } finally {
      setOfferActionBusyById((prev) => {
        const next = { ...prev }
        delete next[offerId]
        return next
      })
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

  useEffect(() => {
    if (activeTab !== 'inbox') return
    const pendingReceivedOfferIds = incomingOffers
      .filter((offer) => String(offer?.status || '').toLowerCase() === 'pending')
      .filter((offer) => {
        const actorSubject = resolveOfferActorSubject(offer)
        return actorSubject && actorSubject === offer.to_subject
      })
      .map((offer) => offer.offer_id)
      .filter((offerId) => offerId && !shippingQuoteByOffer[offerId])
    if (!pendingReceivedOfferIds.length) return
    let cancelled = false
    ;(async () => {
      for (const offerId of pendingReceivedOfferIds) {
        if (cancelled) return
        try {
          await loadShippingQuoteForOffer(offerId)
        } catch (err) {
          if (cancelled) return
          setShippingQuoteByOffer((prev) => ({
            ...prev,
            [offerId]: {
              status: 'unavailable',
              debug: err.message || 'Shipping quote unavailable',
            },
          }))
        }
      }
    })()
    return () => { cancelled = true }
  }, [activeTab, incomingOffers, shippingQuoteByOffer])

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
    setShippingQuoteByOffer((prev) => ({ ...prev, [offerId]: prev[offerId] || { status: 'loading' } }))
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
        const status = String(payload?.status || shipment?.status || '').toLowerCase()
        const msg = status === 'awaiting_shippo_config'
          ? 'Shipping labels are not configured on the server yet.'
          : hasIncompleteProfile
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
      setSelectedShippingLabel({
        url: resolved,
        shipmentId: shipment?.shipment_id || '',
        carrier: shipment?.carrier || payload?.carrier || 'Carrier',
        serviceLevel: shipment?.service_level || payload?.service_level || '',
        trackingNumber: shipment?.tracking_number || payload?.tracking_number || '',
        trackingStatus: shipmentTrackingLabel(payload || shipment),
        trackingDetails: payload?.tracking_status_details || shipment?.tracking_status_details || '',
        trackingEta: payload?.tracking_eta || shipment?.tracking_eta || '',
      })
    } catch (err) {
      const msg = err.message || 'Failed to open label.'
      setSavedListingNotice(msg)
      window.alert(msg)
    }
  }

  const selectedTradeOfferListings = tradeOfferCandidates
    .filter((x) => tradeOfferListingIds.includes(x.id))
  const composerTargetValue = Number(tradeComposerTarget?.estimatedValue || 0)
  const composerWithinBand = composerTargetValue > 0 && selectedTradeOfferListings.length > 0
    ? selectedTradeOfferListings.every((x) => Math.abs(Number(x.estimatedValue || 0) - composerTargetValue) / composerTargetValue <= 0.30)
    : false

  async function analyzeUploadedPhotosForWizard({ analysisImages = images } = {}) {
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
        images: analysisImages,
        category,
        userCondition,
        itemDescription: itemDescription.trim(),
        itemSize,
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

  function resetDraft() {
    setItemTitle('')
    setCategory('')
    setUserCondition('')
    setItemDescription('')
    setItemSize('')
    setTradeNotes('')
    setImages([])
    setEditPreviewUrls([])
    setEditImageCount(0)
    setSelectedCreateImageIndex(0)
    setSelectedEditImageIndex(0)
    setSelectedEditHeroImageIndex(null)
    setAnalysisResult(null)
    setEditingListingId(null)
    setReceiptPromptPending(false)
    setReceiptPromptDismissed(false)
    setAnalysisError('')
    setSavedListingNotice('')
  }

  async function createListingAndRunAsyncAnalysis() {
    if (!clerkEnabled && !apiKey.trim()) {
      setAnalysisError('API key is required.')
      return false
    }
    const imagesForAnalysis = orderedCreateImagesForSave()
    if (imagesForAnalysis.length < 1 || imagesForAnalysis.length > 6) {
      setAnalysisError('Upload 1 to 6 images before continuing.')
      return false
    }
    if (!category) {
      setAnalysisError('Select item category before continuing.')
      return false
    }
    if (!userCondition) {
      setAnalysisError('Select item condition before continuing.')
      return false
    }
    setCreateListingBusy(true)
    setAnalysisError('')
    setSavedListingNotice('')
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      const uploaded = await uploadListingImages({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        images: imagesForAnalysis,
      })
      const uploadedImageUrls = persistableImageUrls((uploaded?.uploaded_images || []).map((entry) => entry?.image_url))
      if (uploadedImageUrls.length < 1) {
        throw new Error('Images were uploaded, but no image URLs were returned.')
      }
      const uploadedImagesReady = await waitForUploadedListingImages(uploadedImageUrls)
      if (!uploadedImagesReady) {
        throw new Error('Images are still processing. Please retry creating the listing in a few seconds.')
      }
      const draftDescription = (itemDescription || '').trim()
      const draftCondition = userCondition || 'LikeNew'
      const draftListing = {
        id: makeId('listing'),
        owner: session.name || 'You',
        title: itemTitle.trim() || draftDescription || 'New listing',
        mode: 'trade',
        category,
        brand: 'unknown',
        condition: draftCondition,
        size: itemSize || null,
        estimatedValue: 0,
        city: 'Your area',
        image: uploadedImageUrls[0],
        images: uploadedImageUrls,
        description: draftDescription,
        wants: draftDescription || 'Open to similar-value offers',
        tags: ['Analyzing'],
        sourceItemId: uploaded?.item_id || null,
        analysis: null,
        status: 'Analyzing',
      }
      const created = await createListingRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        payload: toRemoteListingPayload(draftListing),
      })
      const normalized = fromRemoteListing(created)
      setMyListings((prev) => [normalized, ...prev])
      setActiveTab('portfolio')
      setAnalysisError('')
      setSavedListingNotice('Listing created. AI analysis is running in the background.')
      setShowCreateListingModal(false)
      scheduleListingRefreshes()
      return true
    } catch (err) {
      setAnalysisError(err.message || String(err))
      setSavedListingNotice('Listing creation failed. Please retry creating the listing.')
      return false
    } finally {
      setCreateListingBusy(false)
    }
  }

  async function updateListingAndRunAsyncAnalysis(listing, { finalStatus = 'Review', publishAfterAnalysis = false } = {}) {
    if (!listing) return
    const existingImageUrls = persistableImageUrls(editPreviewUrls.length > 0 || images.length > 0
      ? orderedEditExistingImageUrlsForSave()
      : originalListingImageUrls(listing))
    const newImagesForUpload = orderedEditNewImagesForSave()
    if (existingImageUrls.length < 1 && images.length < 1) {
      setAnalysisError('Upload 1 to 6 images before continuing.')
      return
    }

    setAnalysisError('')
    setSavedListingNotice('')
    try {
      const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
      let uploadedImageUrls = []
      if (newImagesForUpload.length > 0) {
        const uploaded = await uploadListingImages({
          apiBaseUrl,
          apiKey: clerkEnabled ? '' : apiKey.trim(),
          bearerToken,
          images: newImagesForUpload,
        })
        uploadedImageUrls = persistableImageUrls((uploaded?.uploaded_images || []).map((entry) => entry?.image_url))
        if (uploadedImageUrls.length !== newImagesForUpload.length) {
          throw new Error('Images were uploaded, but not all image URLs were returned.')
        }
      }
      const imageUrls = mergedEditImageUrlsForSave(existingImageUrls, uploadedImageUrls)
      if (imageUrls.length < 1) throw new Error('Could not resolve listing image URLs.')
      const pending = {
        ...buildEditedListingPayload(listing, {
          image: imageUrls[0],
          images: imageUrls,
          status: 'Analyzing',
          tags: ['Analyzing'],
        }),
        status: 'Analyzing',
        tags: ['Analyzing'],
      }
      const updated = await updateListingRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken,
        listingId: listing.id,
        payload: toRemoteListingPayload(pending),
      })
      setMyListings((prev) => prev.map((item) => item.id === listing.id ? fromRemoteListing(updated) : item))
      setEditingListingId(null)
      setModalEditingListing(null)
      setShowCreateListingModal(false)
      setActiveTab('portfolio')
      setSavedListingNotice(publishAfterAnalysis
        ? 'Listing changes saved. AI analysis is running before publishing.'
        : 'Listing updated. AI analysis is running in the background.')
      scheduleListingRefreshes()
    } catch (err) {
      setAnalysisError(err.message || String(err))
      setSavedListingNotice('Listing update failed. Please retry saving the listing.')
    }
  }

  async function saveListingEdits(listing) {
    if (!listing) return
    const finalStatus = String(listing.status || 'Review')
    if (editPublishRequiresAnalysis(listing)) {
      updateListingAndRunAsyncAnalysis(listing, { finalStatus, publishAfterAnalysis: false })
      setShowCreateListingModal(false)
      return
    }
    const next = {
      ...buildEditedListingPayload(listing),
      status: finalStatus,
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
      setEditingListingId(null)
      setModalEditingListing(null)
      setShowCreateListingModal(false)
      setActiveTab('portfolio')
      setSavedListingNotice('Listing changes saved.')
    } catch (err) {
      setAnalysisError(err.message || String(err))
    }
  }

  async function publishListingToMarketplace(listing) {
    if (!listing) return
    const missingMessage = missingPublishFieldsMessage(listing)
    if (missingMessage) {
      setAnalysisError(missingMessage)
      setSavedListingNotice('')
      return
    }
    setAnalysisError('')
    const next = {
      ...listing,
      status: 'Active',
      tags: [
        listing.condition || 'LikeNew',
        listing.brand || 'unknown',
        'trade',
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
      setActiveTab('portfolio')
      setSavedListingNotice('Listing published to Marketplace.')
    } catch (err) {
      setAnalysisError(err.message || String(err))
    }
  }

  async function removeListingFromCloset(listing) {
    if (!listing?.id) return
    const confirmed = await confirmListingDelete(listing)
    if (!confirmed) return
    setAnalysisError('')
    setSavedListingNotice('')
    try {
      await deleteListingRemote({
        apiBaseUrl,
        apiKey: clerkEnabled ? '' : apiKey.trim(),
        bearerToken: clerkEnabled && getBearerToken ? await getBearerToken() : null,
        listingId: listing.id,
      })
      setMyListings((prev) => prev.filter((item) => item.id !== listing.id))
      setMarketListings((prev) => prev.filter((item) => item.id !== listing.id))
      setSavedListingNotice('Listing removed from your closet.')
    } catch (err) {
      setAnalysisError(err.message || String(err))
    }
  }

  function openCreateListingModal() {
    resetDraft()
    setListingModalMode('create')
    setModalEditingListing(null)
    setShowCreateListingModal(true)
  }

  function openCreateListingFromCloset() {
    setActiveTab('portfolio')
    openCreateListingModal()
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
    setTradeNotes(listing.wants || '')
    setItemDescription(organizeDescriptionParagraphs(
      meaningfulDescription(listing.description) || buildSuggestedDescriptionFromProfile(listing.analysis?.item_profile) || '',
    ))
    setAnalysisResult(listing.analysis || null)
    setImages([])
    setEditImageCount(existingImages.length)
    setEditPreviewUrls(existingImages)
    setSelectedEditImageIndex(0)
    setSelectedEditHeroImageIndex(null)
    setReceiptPromptPending(false)
    setReceiptPromptDismissed(false)
    setAnalysisError('')
    setSavedListingNotice('')
    setShowCreateListingModal(false)
    setActiveTab('edit_listing')
    if (typeof window !== 'undefined') {
      window.history.pushState({}, '', editListingHref(listing.id))
    }
  }

  function openReviewListing(listing) {
    if (!listing?.id) return
    setReviewListingId(listing.id)
    setAnalysisError('')
    setSavedListingNotice('')
    setActiveTab('review_listing')
    if (typeof window !== 'undefined') {
      window.history.pushState({}, '', reviewListingHref(listing.id))
    }
  }

  function removeEditListingImageAtIndex(imageIndex) {
    if (imageIndex < editPreviewUrls.length) {
      setEditPreviewUrls((prev) => {
        const next = prev.filter((_, idx) => idx !== imageIndex)
        setEditImageCount(next.length)
        return next
      })
    } else {
      const newImageIndex = imageIndex - editPreviewUrls.length
      setImages((prev) => prev.filter((_, idx) => idx !== newImageIndex))
    }
    setSelectedEditImageIndex((idx) => Math.max(0, idx - (idx >= imageIndex ? 1 : 0)))
    setSelectedEditHeroImageIndex((idx) => {
      if (idx === null) return null
      if (idx === imageIndex) return null
      return Math.max(0, idx - (idx > imageIndex ? 1 : 0))
    })
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
              <a href={tabHref('profile')} className={activeTab === 'profile' || activeTab === 'profile_setup' ? 'app-brand-link active' : 'app-brand-link'}>Profile</a>
            </div>
          </div>
        </div>
        <div className="topbar-actions">
          {!clerkEnabled && <label className="inline-field"><span>API Key</span><input value={apiKey} onChange={(e) => setApiKey(e.target.value)} /></label>}
          {clerkEnabled ? (
            <>
              <div className="notification-center">
                <button
                  className={`notification-bell${unreadNotificationCount > 0 ? ' has-unread' : ''}`}
                  type="button"
                  onClick={openNotificationCenter}
                  aria-label={`Notifications${unreadNotificationCount > 0 ? `, ${unreadNotificationCount} unread` : ''}`}
                >
                  <FiBell aria-hidden="true" />
                  {unreadNotificationCount > 0 && (
                    <span className="notification-count">{unreadNotificationCount > 99 ? '99+' : unreadNotificationCount}</span>
                  )}
                </button>
                {notificationPanelOpen && (
                  <div className="notification-panel" role="dialog" aria-label="Notifications">
                    <div className="notification-panel-head">
                      <strong>Notifications</strong>
                      {notifications.length > 0 && (
                        <button className="ghost small" type="button" onClick={() => setNotifications([])}>Clear</button>
                      )}
                    </div>
                    {notifications.length === 0 ? (
                      <p className="notification-empty">No notifications yet.</p>
                    ) : (
                      <div className="notification-list">
                        {notifications.map((notification) => (
                          <button
                            key={notification.id}
                            className={`notification-item notification-${notification.type}`}
                            type="button"
                            onClick={() => openNotificationAction(notification)}
                          >
                            <span>{notification.title}</span>
                            {notification.body && <small>{notification.body}</small>}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
              <button className="ghost" type="button" onClick={() => navigateToTab('profile')}>Profile</button>
              {userMenu}
            </>
          ) : <button className="ghost" onClick={onLogout}>Log out</button>}
        </div>
      </div>

      {tradeNotification && (
        <div className="trade-notification-banner" role="status" aria-live="polite">
          <div>
            <strong>Trade request received</strong>
            <p>{tradeNotification.message}</p>
          </div>
          <div className="trade-notification-actions">
            <button
              className="primary small"
              type="button"
              onClick={() => {
                setTradeNotification(null)
                navigateToTab('inbox')
                setOfferStatusFilter('pending')
              }}
            >
              View
            </button>
            <button className="ghost small" type="button" onClick={() => setTradeNotification(null)}>Dismiss</button>
          </div>
        </div>
      )}

      {appAlert && (
        <div className="app-alert-overlay" role="presentation" onClick={() => {
          const onSecondary = appAlert.onSecondary
          setAppAlert(null)
          if (typeof onSecondary === 'function') onSecondary()
        }}>
          <section className="app-alert-card" role="dialog" aria-modal="true" aria-labelledby="app-alert-title" onClick={(event) => event.stopPropagation()}>
            <p className="eyebrow">JOUFT</p>
            <h3 id="app-alert-title">{appAlert.title}</h3>
            <p>{appAlert.message}</p>
            <div className="button-row app-alert-actions">
              {appAlert.secondaryLabel && (
                <button className="ghost" type="button" onClick={() => {
                  const onSecondary = appAlert.onSecondary
                  setAppAlert(null)
                  if (typeof onSecondary === 'function') onSecondary()
                }}>{appAlert.secondaryLabel}</button>
              )}
              {appAlert.primaryLabel && (
                <button className="primary" type="button" onClick={() => (typeof appAlert.onPrimary === 'function' ? appAlert.onPrimary() : setAppAlert(null))}>
                  {appAlert.primaryLabel}
                </button>
              )}
            </div>
          </section>
        </div>
      )}

      {selectedShippingLabel && (
        <div className="shipping-label-overlay" role="presentation" onClick={() => setSelectedShippingLabel(null)}>
          <section className="shipping-label-card" role="dialog" aria-modal="true" aria-labelledby="shipping-label-title" onClick={(event) => event.stopPropagation()}>
            <div className="shipping-label-head">
              <div>
                <p className="eyebrow">Shipping Label</p>
                <h3 id="shipping-label-title">{selectedShippingLabel.carrier} {selectedShippingLabel.serviceLevel}</h3>
                {selectedShippingLabel.trackingNumber ? (
                  <p className="tiny-note">Tracking: {selectedShippingLabel.trackingNumber}</p>
                ) : null}
                <p className="tiny-note">Status: {selectedShippingLabel.trackingStatus || 'Tracking pending'}</p>
                {selectedShippingLabel.trackingDetails ? (
                  <p className="tiny-note">{selectedShippingLabel.trackingDetails}</p>
                ) : null}
                {selectedShippingLabel.trackingEta ? (
                  <p className="tiny-note">Estimated delivery: {selectedShippingLabel.trackingEta}</p>
                ) : null}
              </div>
              <button className="ghost small" type="button" onClick={() => setSelectedShippingLabel(null)}>Close</button>
            </div>
            <div className="shipping-label-frame">
              <iframe title="Shipping label preview" src={selectedShippingLabel.url} />
            </div>
            <div className="button-row shipping-label-actions">
              <a className="ghost small" href={selectedShippingLabel.url} target="_blank" rel="noreferrer">Open externally</a>
              <a className="primary small" href={selectedShippingLabel.url} target="_blank" rel="noreferrer">Download</a>
            </div>
          </section>
        </div>
      )}

      {showFreshListingsStrip && activeTab !== 'profile' && activeTab !== 'profile_setup' && latestActiveListings.length > 0 && (
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
                  <p className="editorial-byline">BY {ownerFirstName(item.owner, 'Member').toUpperCase()}</p>
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

      {activeTab === 'profile_setup' && (
        <main className="content profile-setup-page" style={{ marginTop: 12 }}>
          <section className="profile-setup-shell">
            <div className="profile-setup-head">
              <div>
                <p className="eyebrow">Profile setup</p>
                <h3 id="profile-setup-title">
                  {profileSetupStep === 1 && 'Step 1 - Address'}
                  {profileSetupStep === 2 && 'Your Browse Profile'}
                  {profileSetupStep === 3 && 'Describe Your Style'}
                  {profileSetupStep === 4 && 'What Brings You to JOUFT?'}
                  {profileSetupStep === 5 && 'Subscription & Payment'}
                </h3>
              </div>
              <div className="profile-setup-progress">
                {Array.from({ length: PROFILE_SETUP_TOTAL_STEPS }, (_, idx) => (
                  <span key={`profile-setup-step-${idx + 1}`} className={profileSetupStep >= idx + 1 ? 'active' : ''} />
                ))}
              </div>
            </div>

            {profileSetupStep === 1 && (
              <div className="profile-setup-body">
                <div className="profile-setup-field-group">
                  <p className="eyebrow">Account</p>
                  <div className="field-grid two">
                    <label>
                      <span>First Name</span>
                      <input
                        value={profileQuiz.first_name || ''}
                        onChange={(e) => {
                          profileSetupDirtyRef.current = true
                          setProfileQuiz((p) => ({ ...p, first_name: e.target.value }))
                        }}
                        required
                      />
                    </label>
                    <label>
                      <span>Last Name</span>
                      <input
                        value={profileQuiz.last_name || ''}
                        onChange={(e) => {
                          profileSetupDirtyRef.current = true
                          setProfileQuiz((p) => ({ ...p, last_name: e.target.value }))
                        }}
                        required
                      />
                    </label>
                    <label>
                      <span>Email Address</span>
                      <input
                        type="email"
                        value={profileQuiz.email || ''}
                        onChange={(e) => {
                          profileSetupDirtyRef.current = true
                          setProfileQuiz((p) => ({ ...p, email: e.target.value }))
                        }}
                        required
                      />
                    </label>
                    <label>
                      <span>Birthday</span>
                      <input
                        type="date"
                        value={profileQuiz.birthday || ''}
                        onChange={(e) => {
                          profileSetupDirtyRef.current = true
                          setProfileQuiz((p) => ({ ...p, birthday: e.target.value }))
                        }}
                      />
                    </label>
                    <label>
                      <span>Gender</span>
                      <select
                        value={profileQuiz.gender || ''}
                        onChange={(e) => {
                          profileSetupDirtyRef.current = true
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
                  </div>
                </div>

                <div className="profile-setup-field-group">
                  <p className="eyebrow">Shipping Address</p>
                  <div className="field-grid two">
                    <label>
                      <span>Shipping Full Name</span>
                      <input value={primaryProfileAddress.full_name || ''} onChange={(e) => updatePrimaryShippingAddress({ full_name: e.target.value })} />
                    </label>
                    <label>
                      <span>Address Line 1</span>
                      <input value={primaryProfileAddress.address_line1 || ''} onChange={(e) => updatePrimaryShippingAddress({ address_line1: e.target.value })} />
                    </label>
                    <label>
                      <span>Address Line 2</span>
                      <input value={primaryProfileAddress.address_line2 || ''} onChange={(e) => updatePrimaryShippingAddress({ address_line2: e.target.value })} />
                    </label>
                    <label>
                      <span>City</span>
                      <input value={primaryProfileAddress.city || ''} onChange={(e) => updatePrimaryShippingAddress({ city: e.target.value })} />
                    </label>
                    <label>
                      <span>State</span>
                      <input value={primaryProfileAddress.state || ''} onChange={(e) => updatePrimaryShippingAddress({ state: e.target.value })} />
                    </label>
                    <label>
                      <span>Postal Code</span>
                      <input value={primaryProfileAddress.postal_code || ''} onChange={(e) => updatePrimaryShippingAddress({ postal_code: e.target.value })} />
                    </label>
                    <label>
                      <span>Country</span>
                      <input value={primaryProfileAddress.country || ''} onChange={(e) => updatePrimaryShippingAddress({ country: e.target.value })} />
                    </label>
                  </div>
                </div>
              </div>
            )}

            {profileSetupStep === 2 && (
              <div className="profile-setup-body">
                <div className="profile-setup-size-grid">
                  <div>
                    <span className="tiny-note">Tops Size</span>
                    <div className="tag-row">
                      {profileApparelSizeOptions.map((s) => {
                        const selected = Array.isArray(profileQuiz.tops_size) && profileQuiz.tops_size.includes(s)
                        return <button key={`setup-tops-${s}`} type="button" className={selected ? 'pill' : 'ghost small'} onClick={() => toggleProfileArrayField('tops_size', s)}>{s}</button>
                      })}
                    </div>
                  </div>
                  {normalizedProfileGender !== 'male' && (
                    <div>
                      <span className="tiny-note">Dresses Size</span>
                      <div className="tag-row">
                        {profileApparelSizeOptions.map((s) => {
                          const selected = Array.isArray(profileQuiz.dresses_size) && profileQuiz.dresses_size.includes(s)
                          return <button key={`setup-dresses-${s}`} type="button" className={selected ? 'pill' : 'ghost small'} onClick={() => toggleProfileArrayField('dresses_size', s)}>{s}</button>
                        })}
                      </div>
                    </div>
                  )}
                  <div>
                    <span className="tiny-note">Bottoms Size</span>
                    <div className="tag-row">
                      {profileApparelSizeOptions.map((s) => {
                        const selected = Array.isArray(profileQuiz.bottoms_size) && profileQuiz.bottoms_size.includes(s)
                        return <button key={`setup-bottoms-${s}`} type="button" className={selected ? 'pill' : 'ghost small'} onClick={() => toggleProfileArrayField('bottoms_size', s)}>{s}</button>
                      })}
                    </div>
                  </div>
                  <div>
                    <span className="tiny-note">Shoes Size</span>
                    <div className="tag-row">
                      {profileShoeSizeOptions.map((s) => {
                        const selected = Array.isArray(profileQuiz.shoes_size) && profileQuiz.shoes_size.includes(s)
                        return <button key={`setup-shoes-${s}`} type="button" className={selected ? 'pill' : 'ghost small'} onClick={() => toggleProfileArrayField('shoes_size', s)}>{s}</button>
                      })}
                    </div>
                  </div>
                  <div>
                    <span className="tiny-note">Browse Categories</span>
                    <div className="tag-row">
                      {profileCategoryOptions.map((c) => {
                        const selected = profileQuiz.category_preferences.includes(c)
                        return <button key={`setup-category-${c}`} type="button" className={selected ? 'pill' : 'ghost small'} onClick={() => toggleProfileArrayField('category_preferences', c)}>{c}</button>
                      })}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {profileSetupStep === 3 && (
              <div className="profile-setup-body">
                <p className="tiny-note">Choose up to 3.</p>
                <div className="profile-style-card-grid">
                  {STYLE_DESCRIPTOR_OPTIONS.map((style) => {
                    const selected = profileQuiz.style_descriptors.includes(style.value)
                    return (
                      <button
                        key={style.value}
                        type="button"
                        className={selected ? 'profile-style-card active' : 'profile-style-card'}
                        onClick={() => toggleProfileArrayField('style_descriptors', style.value, 3)}
                      >
                        <span className={`profile-style-visual ${style.className}`} aria-hidden="true" />
                        <strong>{style.value}</strong>
                        <span>{style.description}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {profileSetupStep === 4 && (
              <div className="profile-setup-body">
                <p className="tiny-note">Choose up to 2.</p>
                <div className="profile-goal-grid">
                  {JOUFT_GOAL_OPTIONS.map((goal) => {
                    const selected = profileQuiz.jouft_goals.includes(goal)
                    return (
                      <button
                        key={goal}
                        type="button"
                        className={selected ? 'pill' : 'ghost small'}
                        onClick={() => toggleProfileArrayField('jouft_goals', goal, 2)}
                      >
                        {goal}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {profileSetupStep === 5 && (
              <div className="profile-setup-body">
                <p className="tiny-note">Choose a plan to start using JOUFT. Payment details are only required for paid plans.</p>
                <div className="billing-cycle-toggle">
                  <button
                    className={selectedBillingCycle === 'monthly' ? 'nav-item active' : 'nav-item'}
                    type="button"
                    onClick={() => {
                      profileSetupDirtyRef.current = true
                      setProfileQuiz((p) => ({ ...p, subscription_billing_cycle: 'monthly' }))
                    }}
                  >
                    Monthly Billing
                  </button>
                  <button
                    className={selectedBillingCycle === 'annual' ? 'nav-item active' : 'nav-item'}
                    type="button"
                    onClick={() => {
                      profileSetupDirtyRef.current = true
                      setProfileQuiz((p) => ({ ...p, subscription_billing_cycle: 'annual' }))
                    }}
                  >
                    Annual Billing (10% Off)
                  </button>
                </div>
                <div className="subscription-plan-grid">
                  {SUBSCRIPTION_PLANS.map((plan) => {
                    const isSelected = selectedSubscriptionPlanId === plan.id
                    const annualTotal = Math.round(plan.monthlyPrice * 12 * 0.9)
                    const annualMonthlyEquivalent = annualTotal / 12
                    const priceLabel = plan.monthlyPrice <= 0
                      ? 'Free'
                      : selectedBillingCycle === 'annual'
                      ? `$${annualTotal}/year ($${annualMonthlyEquivalent.toFixed(2)}/month)`
                      : `$${plan.monthlyPrice}/month`
                    return (
                      <button
                        key={`setup-plan-${plan.id}`}
                        type="button"
                        className={isSelected ? 'subscription-plan-card active' : 'subscription-plan-card'}
                        onClick={() => {
                          profileSetupDirtyRef.current = true
                          setProfileQuiz((p) => ({ ...p, subscription_plan: plan.id, subscription_status: '' }))
                        }}
                      >
                        <span className="subscription-plan-name">{plan.name}</span>
                        <strong className="subscription-plan-price">{priceLabel}</strong>
                        <span className="subscription-plan-limit">{plan.description}</span>
                      </button>
                    )
                  })}
                </div>
                <div style={{ marginTop: 16 }}>
                  {selectedSubscriptionPlanIsPaid ? (
                    <>
                      <p className="eyebrow" style={{ marginBottom: 8 }}>Payment Method</p>
                      <span className="tiny-note">Payments are managed by Stripe. JOUFT does not store raw card numbers.</span>
                      <div className="button-row" style={{ marginBottom: 8 }}>
                        <button className="ghost small" type="button" onClick={() => setShowStripePaymentModal(true)}>
                          + Add Payment Method
                        </button>
                        <button
                          className="ghost small"
                          type="button"
                          disabled={paymentSyncBusy}
                          onClick={async () => {
                            setPaymentSyncBusy(true)
                            try {
                              const bearerToken = clerkEnabled && getBearerToken ? await getBearerToken() : null
                              const synced = await syncStripePaymentMethodsRemote({
                                apiBaseUrl,
                                apiKey: clerkEnabled ? '' : apiKey.trim(),
                                bearerToken,
                              })
                              setPaymentMethods(synced)
                              setPaymentActionMsg('Payment methods synced.')
                              setPaymentLoadError('')
                            } catch (err) {
                              setPaymentLoadError(err?.message || 'Failed to sync payment methods.')
                            } finally {
                              setPaymentSyncBusy(false)
                            }
                          }}
                        >
                          {paymentSyncBusy ? 'Syncing...' : 'Sync From Stripe'}
                        </button>
                      </div>
                      {paymentActionMsg && <span className="tiny-note" style={{ color: '#067647' }}>{paymentActionMsg}</span>}
                      {paymentLoadError && <span className="tiny-note" style={{ color: '#b42318' }}>{paymentLoadError}</span>}
                      {paymentMethods.length === 0 ? (
                        <p className="tiny-note">Add a payment method before activating your subscription.</p>
                      ) : (
                        <div style={{ display: 'grid', gap: 8 }}>
                          {paymentMethods.map((method) => {
                            const selectedForSubscription = method.payment_method_id === selectedSubscriptionPaymentMethodId
                            return (
                              <button
                                key={`setup-payment-${method.payment_method_id}`}
                                type="button"
                                className={selectedForSubscription ? 'subscription-plan-card active' : 'subscription-plan-card'}
                                onClick={() => setSelectedSubscriptionPaymentMethodId(method.payment_method_id)}
                                style={{ textAlign: 'left' }}
                              >
                                <span className="subscription-plan-name">{method.label || method.method_type || 'Payment method'}</span>
                                <span className="tiny-note">
                                  {method.provider}{method.is_default ? ' • Default' : ''}{selectedForSubscription ? ' • Subscription' : ''}
                                </span>
                                {(method.last4 || method.email) && (
                                  <span className="tiny-note">{method.last4 ? `•••• ${method.last4}` : method.email}</span>
                                )}
                              </button>
                            )
                          })}
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="tiny-note">Free plan selected. No payment method is required.</p>
                  )}
                </div>
              </div>
            )}

            <div className="profile-setup-actions">
              <div className="button-row" style={{ margin: 0 }}>
                <button className="ghost small" type="button" disabled={profileSetupStep === 1} onClick={() => setProfileSetupStep((step) => Math.max(1, step - 1))}>Back</button>
                {profileSetupStep < PROFILE_SETUP_TOTAL_STEPS ? (
                  <button
                    className="primary"
                    type="button"
                    onClick={() => {
                      const error = currentProfileSetupStepError(profileSetupStep)
                      if (error) {
                        setProfileSaveMsg(error)
                        return
                      }
                      setProfileSaveMsg('')
                      setProfileSetupStep((step) => Math.min(PROFILE_SETUP_TOTAL_STEPS, step + 1))
                    }}
                  >
                    Next
                  </button>
                ) : (
                  <button
                    className="primary"
                    type="button"
                    onClick={async () => {
                      try {
                        const error = currentProfileSetupStepError(PROFILE_SETUP_TOTAL_STEPS)
                        if (error) {
                          setProfileSaveMsg(error)
                          return
                        }
                        await saveProfileQuiz()
                        const activated = await activateSelectedSubscription()
                        if (!activated) return
                        profileSetupDirtyRef.current = false
                        setProfileSetupRequired(false)
                        setAppAlert({
                          title: selectedSubscriptionPlanIsPaid ? 'Subscription Active' : 'Free Plan Active',
                          message: selectedSubscriptionPlanIsPaid
                            ? 'Payment processed successfully. Your JOUFT subscription is active.'
                            : 'Your free JOUFT plan is active.',
                          primaryLabel: 'Continue',
                        })
                        setActiveTab('market')
                        if (typeof window !== 'undefined') {
                          window.history.pushState({}, '', tabHref('market'))
                        }
                      } catch (err) {
                        setProfileSetupStep(PROFILE_SETUP_TOTAL_STEPS)
                        setProfileSaveMsg(err.message || 'Payment was not processed. Please update your payment details.')
                      }
                    }}
                  >
                    Finish
                  </button>
                )}
              </div>
            </div>
            {profileSaveMsg && <span className="tiny-note">{profileSaveMsg}</span>}
          </section>
        </main>
      )}

      {activeTab === 'profile' ? (
        <main className="content" style={{ marginTop: 12 }}>
          <section className="panel" key={`profile-tab-${profileTabReloadKey}`}>
            <div style={{ maxWidth: 980 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
		                <h3 className="profile-tab-heading">Profile</h3>
              </div>
              {profileTabReloading ? (
                <div className="loading-panel" role="status" aria-live="polite">
                  <span className="spinner" aria-hidden="true" />
                  <h3>Reloading profile...</h3>
                  <p>We are refreshing your saved profile details.</p>
                </div>
              ) : (
              <>
              <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 16 }}>
                <aside className="profile-nav" style={{ border: '1px solid var(--line)', borderRadius: 12, padding: 10, alignSelf: 'start' }}>
                  <button className={profileSection === 'general' ? 'nav-item active' : 'nav-item'} type="button" onClick={() => setProfileSection('general')}>General</button>
                  <button className={profileSection === 'style' ? 'nav-item active' : 'nav-item'} type="button" onClick={() => setProfileSection('style')}>Style Preferences</button>
                  <button className={profileSection === 'subscription' ? 'nav-item active' : 'nav-item'} type="button" onClick={() => setProfileSection('subscription')}>Subscription</button>
                  <button className={profileSection === 'shipping' ? 'nav-item active' : 'nav-item'} type="button" onClick={() => setProfileSection('shipping')}>Shipping</button>
                </aside>
	                <div>
                  {profileHydrationError && <p className="error-text">{profileHydrationError}</p>}
	                  {profileSection === 'general' && (
                    <div className="field-grid two">
                      <label>
                        <span>First Name</span>
                        <input
                          value={profileQuiz.first_name || ''}
                          onChange={(e) => setProfileQuiz((p) => ({ ...p, first_name: e.target.value }))}
                          placeholder="First name"
                        />
                      </label>
                      <label>
                        <span>Last Name</span>
                        <input
                          value={profileQuiz.last_name || ''}
                          onChange={(e) => setProfileQuiz((p) => ({ ...p, last_name: e.target.value }))}
                          placeholder="Last name"
                        />
                      </label>
                      <label>
                        <span>Email</span>
                        <input
                          type="email"
                          value={profileQuiz.email || ''}
                          onChange={(e) => setProfileQuiz((p) => ({ ...p, email: e.target.value }))}
                          placeholder="email@example.com"
                        />
                      </label>
                      <label>
                        <span>Phone</span>
                        <input
                          type="tel"
                          value={profileQuiz.shipping_phone || ''}
                          onChange={(e) => setProfileQuiz((p) => ({ ...p, shipping_phone: e.target.value }))}
                          placeholder="Phone number"
                        />
                      </label>
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
                          onClick={() => {
                            setSubscriptionSelectionDirty(true)
                            setProfileQuiz((p) => ({ ...p, subscription_billing_cycle: 'monthly' }))
                          }}
                        >
                          Monthly Billing
                        </button>
                        <button
                          className={selectedBillingCycle === 'annual' ? 'nav-item active' : 'nav-item'}
                          type="button"
                          onClick={() => {
                            setSubscriptionSelectionDirty(true)
                            setProfileQuiz((p) => ({ ...p, subscription_billing_cycle: 'annual' }))
                          }}
                        >
                          Annual Billing (10% Off)
                        </button>
                      </div>
                      <div className="subscription-plan-grid">
                        {SUBSCRIPTION_PLANS.map((plan) => {
                          const isSelected = selectedSubscriptionPlanId === plan.id
                          const annualTotal = Math.round(plan.monthlyPrice * 12 * 0.9)
                          const annualMonthlyEquivalent = annualTotal / 12
                          const priceLabel = plan.monthlyPrice <= 0
                            ? 'Free'
                            : selectedBillingCycle === 'annual'
                            ? `$${annualTotal}/year ($${annualMonthlyEquivalent.toFixed(2)}/month)`
                            : `$${plan.monthlyPrice}/month`
                          return (
                            <button
                              key={plan.id}
                              type="button"
                              className={isSelected ? 'subscription-plan-card active' : 'subscription-plan-card'}
                              onClick={() => {
                                setSubscriptionSelectionDirty(true)
                                setProfileQuiz((p) => ({
                                  ...p,
                                  subscription_plan: plan.id,
                                }))
                              }}
                            >
                              <span className="subscription-plan-name">{plan.name}</span>
                              <strong className="subscription-plan-price">{priceLabel}</strong>
                              <span className="subscription-plan-limit">{plan.description}</span>
                            </button>
                          )
                        })}
                      </div>
                      <span className="tiny-note">Current status: {profileQuiz.subscription_status ? titleCase(profileQuiz.subscription_status) : 'Not active'}</span>
                      {selectedSubscriptionPlanIsPaid ? (
                        <div className="field-grid two" style={{ marginTop: 12 }}>
                          <label>
                            <span>Payment method for this subscription</span>
                            <select
                              value={selectedSubscriptionPaymentMethodId}
                              onChange={(e) => {
                                setSubscriptionSelectionDirty(true)
                                setSelectedSubscriptionPaymentMethodId(e.target.value)
                              }}
                            >
                              {paymentMethods.length === 0 ? (
                                <option value="">Add a payment method first</option>
                              ) : (
                                paymentMethods.map((method) => (
                                  <option key={method.payment_method_id} value={method.payment_method_id}>
                                    {method.label || method.method_type || 'Payment method'}{method.is_default ? ' (default)' : ''}
                                  </option>
                                ))
                              )}
                            </select>
                          </label>
                        </div>
                      ) : (
                        <span className="tiny-note">Free plan selected. No payment method is required.</span>
                      )}
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
                          {paymentMethods.map((method) => {
                            const selectedForSubscription = method.payment_method_id === selectedSubscriptionPaymentMethodId
                            return (
                            <div key={method.payment_method_id} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', border: selectedForSubscription ? '1px solid var(--ink)' : '1px solid var(--line)', borderRadius: 10, padding: '8px 10px' }}>
                              <div>
                                <strong>{method.label || method.method_type}</strong>
                                <div className="tiny-note">
                                  {method.provider}{method.is_default ? ' • Default' : ''}{selectedForSubscription ? ' • Subscription' : ''}
                                </div>
                                {(method.last4 || method.email) && (
                                  <div className="tiny-note">{method.last4 ? `•••• ${method.last4}` : method.email}</div>
                                )}
                              </div>
                              <div className="button-row">
                                {!selectedForSubscription && (
                                  <button
                                    className="ghost small"
                                    type="button"
                                    onClick={() => {
                                      setSubscriptionSelectionDirty(true)
                                      setSelectedSubscriptionPaymentMethodId(method.payment_method_id)
                                    }}
                                  >
                                    Use for Subscription
                                  </button>
                                )}
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
                                        await reloadProfileTabAfterSuccess('Default payment method updated.')
                                        setPaymentActionMsg('Default payment method updated.')
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
                                      await reloadProfileTabAfterSuccess('Payment method removed.')
                                      setPaymentActionMsg('Payment method removed.')
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
                            )
                          })}
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
                              setAddressAutocompleteActive(false)
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
                          <input
                            value={activeShippingAddress?.address_line1 || ''}
                            onChange={(e) => {
                              setAddressAutocompleteActive(true)
                              updateActiveShippingAddress({ address_line1: e.target.value })
                            }}
                            autoComplete="off"
                          />
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
                                    country: s.country || activeShippingAddress?.country || 'US',
                                  })
                                  setAddressSuggestions([])
                                  setAddressAutocompleteActive(false)
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
                  onClick={async () => {
                    setProfileSaveMsg('')
                    setProfileHydrationError('')
                    try {
                      profileSetupDirtyRef.current = false
                      await loadProfileQuizIntoState({ force: true })
                    } catch (err) {
                      setProfileHydrationError(err.message || 'Profile data could not be loaded.')
                    }
                  }}
                >
                  Cancel
                </button>
                <button
                  className={profileSection === 'subscription' && subscriptionSelectionIsCurrent ? 'primary disabled' : 'primary'}
                  type="button"
                  disabled={profileSection === 'subscription' && subscriptionSelectionIsCurrent}
                  onClick={async () => {
                    try {
                      if (profileSection === 'subscription') {
                        const activated = await activateSelectedSubscription()
                        if (activated) {
                          await reloadProfileTabAfterSuccess('Subscription active.')
                          setAppAlert({
                            title: selectedSubscriptionPlanIsPaid ? 'Subscription Active' : 'Free Plan Active',
                            message: selectedSubscriptionPlanIsPaid
                              ? 'Payment processed successfully. Your JOUFT subscription is active.'
                              : 'Your free JOUFT plan is active.',
                            primaryLabel: 'Continue',
                          })
                        }
                      } else {
                        await saveProfileQuiz()
                        await reloadProfileTabAfterSuccess('Profile saved.', { navigateToProfileTab: true })
                      }
                    } catch (err) {
                      if (profileSection === 'subscription') {
                        setProfileSection('payments')
                        setPaymentLoadError(err.message || 'Payment was not processed. Please update your payment details.')
                      }
                      setProfileSaveMsg(err.message || 'Failed to save profile.')
                    }
                  }}
                >
                  {profileSection === 'subscription'
                    ? (subscriptionSelectionIsCurrent
                      ? 'Subscription Active'
                      : (hasActiveSubscription ? 'Update Subscription' : (selectedSubscriptionPlanIsPaid ? 'Activate Subscription' : 'Use Free Plan')))
                    : 'Save Profile'}
                </button>
                {profileSaveMsg && <span className="tiny-note">{profileSaveMsg}</span>}
              </div>
              </>
              )}
            </div>
          </section>
        </main>
      ) : (
      <main className="content">
          {activeTab === 'edit_listing' && (
            <section className="panel listing-edit-page">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Edit Listing</p>
                </div>
                <div className="header-actions">
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => {
                      if (typeof window !== 'undefined' && tabFromLocation() === 'edit_listing' && window.history.length > 1) {
                        window.history.back()
                        return
                      }
                      setActiveTab('portfolio')
                      setEditingListingId(null)
                      setModalEditingListing(null)
                      setImages([])
                      setEditPreviewUrls([])
                      setSelectedEditHeroImageIndex(null)
                      setAnalysisError('')
                    }}
                    disabled={analysisLoading || createListingBusy}
                  >
                    Back to Closet
                  </button>
                </div>
              </div>

              {!modalEditingListing ? (
                <div className="empty-state">
                  <h3>No listing selected</h3>
                  <p>Select a listing from your closet to edit it.</p>
                  <button className="primary" type="button" onClick={() => navigateToTab('portfolio')}>Go to Closet</button>
                </div>
              ) : (
                <div className="listing-edit-layout">
                  <aside className="listing-edit-gallery-panel">
                    <p className="listing-modal-label"><strong>Images (1-6)</strong></p>
                    <input
                      id="edit-listing-page-image-input"
                      type="file"
                      accept="image/*"
                      multiple
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const selected = Array.from(e.target.files || [])
                        const maxNew = Math.max(0, 6 - editPreviewUrls.length)
                        setImages((prev) => {
                          const room = Math.max(0, maxNew - prev.length)
                          return room > 0 ? [...prev, ...selected.slice(0, room)] : prev
                        })
                        setReceiptPromptPending(false)
                        setReceiptPromptDismissed(false)
                        e.target.value = ''
                      }}
                    />
                    <div className="listing-edit-gallery market-selected-gallery">
                      <div className="listing-edit-main-image market-selected-main-image">
                        {modalPreviewUrls.length > 0 ? (
                          <>
                            <img
                              src={modalPreviewUrls[Math.min(selectedEditImageIndex, modalPreviewUrls.length - 1)]}
                              alt={`Listing image ${Math.min(selectedEditImageIndex, modalPreviewUrls.length - 1) + 1}`}
                            />
                            {selectedEditHeroImageIndex === Math.min(selectedEditImageIndex, modalPreviewUrls.length - 1) && (
                              <span className="listing-hero-badge listing-edit-hero-badge">Hero</span>
                            )}
                            {Math.min(selectedEditImageIndex, modalPreviewUrls.length - 1) >= editPreviewUrls.length && (
                              <span className="listing-modal-new-badge listing-edit-main-badge">New</span>
                            )}
                            <button
                              className="listing-modal-set-hero listing-edit-main-set-hero"
                              type="button"
                              onClick={() => setSelectedEditHeroImageIndex(Math.min(selectedEditImageIndex, modalPreviewUrls.length - 1))}
                              disabled={selectedEditHeroImageIndex === Math.min(selectedEditImageIndex, modalPreviewUrls.length - 1)}
                            >
                              {selectedEditHeroImageIndex === Math.min(selectedEditImageIndex, modalPreviewUrls.length - 1) ? 'Hero Image' : 'Set Hero'}
                            </button>
                            <button
                              className="listing-modal-remove-image listing-edit-main-remove"
                              type="button"
                              onClick={() => removeEditListingImageAtIndex(Math.min(selectedEditImageIndex, modalPreviewUrls.length - 1))}
                            >
                              Remove
                            </button>
                          </>
                        ) : (
                          <label htmlFor="edit-listing-page-image-input" className="listing-edit-empty-main">
                            <span>+</span>
                            <strong>Add images</strong>
                          </label>
                        )}
                      </div>

                      <div className="market-selected-thumbnails listing-edit-thumbnails" aria-label="Listing image thumbnails">
                        {modalPreviewUrls.map((url, idx) => (
                          <button
                            key={`edit-page-thumb-${url}-${idx}`}
                            className={idx === Math.min(selectedEditImageIndex, modalPreviewUrls.length - 1) ? 'active' : ''}
                            type="button"
                            onClick={() => setSelectedEditImageIndex(idx)}
                            aria-label={`Show image ${idx + 1}`}
                          >
                            <img src={url} alt="" />
                            {idx === selectedEditHeroImageIndex && <span className="listing-edit-thumb-badge hero">Hero</span>}
                            {idx >= editPreviewUrls.length && <span className="listing-edit-thumb-badge new">New</span>}
                          </button>
                        ))}
                        {modalPreviewUrls.length < 6 && (
                          <label htmlFor="edit-listing-page-image-input" className="listing-modal-add-image listing-edit-thumb-add" title="Add image">
                            +
                          </label>
                        )}
                      </div>
                    </div>
                  </aside>

                  <div className="listing-edit-details">
                  <form className="listing-edit-form" onSubmit={(e) => e.preventDefault()}>
                    {createListingBusy && <p className="ok-text">Saving listing...</p>}
                    {analysisLoading && <p className="ok-text">Analyzing photos...</p>}
                    {analysisError && <p className="error-text">{analysisError}</p>}
                    {savedListingNotice && !analysisLoading && !createListingBusy && <p className="ok-text">{savedListingNotice}</p>}

                    <div className="field-grid">
                      <label>
                        <span>Category</span>
                        <select value={category} onChange={(e) => setCategory(e.target.value)}>
                          <option value="">Select category</option>
                          <option value="clothes">Clothes</option>
                          <option value="shoes">Shoes</option>
                          <option value="handbag">Handbag</option>
                        </select>
                      </label>
                      <label>
                        <span>Your condition assessment</span>
                        <select value={userCondition} onChange={(e) => setUserCondition(e.target.value)} required>
                          <option value="">Select condition</option>
                          <option value="NewWithTags">New with Tags</option>
                          <option value="New">New</option>
                          <option value="LikeNew">Like New</option>
                        </select>
                      </label>
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
                        onBlur={() => setItemDescription((current) => organizeDescriptionParagraphs(current))}
                        rows={8}
                        placeholder="Describe materials, color, hardware, wear, and notable details."
                      />
                    </label>

                    <label>
                      <span>Trade notes</span>
                      <textarea
                        value={tradeNotes}
                        onChange={(e) => setTradeNotes(e.target.value)}
                        rows={3}
                        placeholder="What you want in exchange"
                      />
                    </label>

                    <div className="button-row listing-modal-actions">
                      <button
                        className="ghost"
                        type="button"
                        onClick={() => {
                          setActiveTab('portfolio')
                          setEditingListingId(null)
                          setModalEditingListing(null)
                          setImages([])
                          setEditPreviewUrls([])
                          setAnalysisError('')
                        }}
                        disabled={analysisLoading || createListingBusy}
                      >
                        Cancel
                      </button>
                      <button
                        className="primary"
                        type="button"
                        disabled={analysisLoading || createListingBusy}
                        onClick={() => {
                          const currentImageCount = modalPreviewUrls.length
                          if (currentImageCount < 1 || currentImageCount > 6) {
                            setAnalysisError('Upload 1 to 6 images before continuing.')
                            return
                          }
                          if (!userCondition) {
                            setAnalysisError('Select item condition before continuing.')
                            return
                          }
                          saveListingEdits(modalEditingListing)
                        }}
                      >
                        Save Changes
                      </button>
                    </div>
                  </form>

                    {modalEditingListing?.analysis && (
                      <section className="listing-edit-analysis">
                      <article className="result-card feature">
                        <p className="eyebrow">AI Analysis</p>
                        <h3>{modalEditingListing.analysis.brand?.name === 'unknown' ? 'Brand unknown' : (modalEditingListing.analysis.brand?.name || 'Unknown')}</h3>
                        <div className="metric-grid">
                          <div><span>Category</span><strong>{modalEditingListing.analysis.category || 'unknown'}</strong></div>
                          <div><span>Brand confidence</span><strong>{confidenceLabel(modalEditingListing.analysis.brand?.confidence)}</strong></div>
                          <div><span>Condition</span><strong>{modalEditingListing.analysis.condition?.grade || modalEditingListing.condition || 'n/a'}</strong></div>
                          <div><span>Condition confidence</span><strong>{confidenceLabel(modalEditingListing.analysis.condition?.confidence)}</strong></div>
                        </div>
                        {modalEditingListing.analysis.item_profile?.model_identification?.name && (
                          <div className="request-list">
                            <span>GPT item profile:</span>
                            <code>{modalEditingListing.analysis.item_profile.model_identification.name}</code>
                          </div>
                        )}
                        <VisualConditionDebug assessment={modalEditingListing.analysis.item_profile?.visual_condition_assessment} />
                        {modalEditingListing.analysis.valuation ? (
                          <div className="valuation-band">
                            <div><span>Estimated value</span><strong>{money(modalEditingListing.analysis.valuation.estimated_value)}</strong></div>
                            <div><span>Range</span><strong>{money(modalEditingListing.analysis.valuation.range_low)} - {money(modalEditingListing.analysis.valuation.range_high)}</strong></div>
                            <div><span>Valuation confidence</span><strong>{confidenceLabel(modalEditingListing.analysis.valuation.confidence)}</strong></div>
                          </div>
                        ) : <p className="muted-text">No valuation returned yet.</p>}
                      </article>
                      </section>
                    )}
                  </div>
                </div>
              )}
            </section>
          )}

          {activeTab === 'review_listing' && (
            <section className="panel listing-review-page">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Review Listing</p>
                </div>
                <div className="header-actions">
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => {
                      if (typeof window !== 'undefined' && tabFromLocation() === 'review_listing' && window.history.length > 1) {
                        window.history.back()
                        return
                      }
                      setReviewListingId(null)
                      navigateToTab('portfolio')
                    }}
                  >
                    Back to Closet
                  </button>
                </div>
              </div>

              {!reviewListing ? (
                <div className="empty-state">
                  <h3>No listing selected</h3>
                  <p>Select a listing from your closet to review it.</p>
                  <button className="primary" type="button" onClick={() => navigateToTab('portfolio')}>Go to Closet</button>
                </div>
              ) : (
                <div className="listing-review-layout">
                  <div className={`listing-review-gallery ${reviewListingGallery.length <= 1 ? 'single-image' : ''}`}>
                    {reviewListingGallery.length > 1 && (
                      <div className="listing-review-thumbnails" aria-label="Listing image thumbnails">
                        {reviewListingGallery.map((src, idx) => (
                          <button
                            key={`${reviewListing.id}-review-thumb-${idx}`}
                            type="button"
                            className={idx === selectedReviewImageIndex ? 'active' : ''}
                            onClick={() => setSelectedReviewImageIndex(idx)}
                            aria-label={`Show image ${idx + 1}`}
                            aria-current={idx === selectedReviewImageIndex ? 'true' : undefined}
                          >
                            <img src={src} alt="" />
                          </button>
                        ))}
                      </div>
                    )}
                    {reviewListingGallery[selectedReviewImageIndex] ? (
                      <img src={reviewListingGallery[selectedReviewImageIndex]} alt={`${reviewListing.title || 'Listing'} image ${selectedReviewImageIndex + 1}`} />
                    ) : (
                      <div className="listing-image-fallback">Image unavailable</div>
                    )}
                  </div>
                  <div className="listing-review-details">
                    <h2>{reviewListing.title || 'Untitled listing'}</h2>
                    <p className="editorial-byline">BY {ownerFirstName(reviewListing.owner, 'Member').toUpperCase()}</p>
                    <p className="editorial-meta">
                      EST. {money(reviewListing.estimatedValue)} · {String(reviewListing.brand || 'Unknown').toUpperCase()} · {displayConditionLabel(reviewListing.condition).toUpperCase()} · SIZE {String(reviewListing.size || 'N/A').toUpperCase()}
                    </p>
                    <p className="listing-review-description">{getListingDescription(reviewListing) || 'No description provided.'}</p>
                    {analysisError && <p className="error-text">{analysisError}</p>}
                    {savedListingNotice && <p className="ok-text">{savedListingNotice}</p>}
                    <div className="button-row listing-review-actions">
                      <button className="ghost" type="button" onClick={() => openEditListingModal(reviewListing)}>Edit</button>
                      <button className="primary" type="button" onClick={() => publishListingToMarketplace(reviewListing)}>Publish</button>
                    </div>
                  </div>
                </div>
              )}
            </section>
          )}

          {activeTab === 'portfolio' && (
            <section className="panel">
	              <div className="panel-header">
	                <div>
	                  <p className="eyebrow">Portfolio</p>
	                  <div className="button-row" style={{ marginTop: 6 }}>
                    <button className={closetFilter === 'all' ? 'primary' : 'ghost small'} type="button" onClick={() => setClosetFilter('all')}>All ({myListings.length})</button>
                    <button className={closetFilter === 'active' ? 'primary' : 'ghost small'} type="button" onClick={() => setClosetFilter('active')}>Active ({closetBreakdown.active})</button>
                    <button className={closetFilter === 'draft' ? 'primary' : 'ghost small'} type="button" onClick={() => setClosetFilter('draft')}>Draft ({closetBreakdown.draft})</button>
                    <button className={closetFilter === 'offers' ? 'primary' : 'ghost small'} type="button" onClick={() => setClosetFilter('offers')}>Offers ({closetBreakdown.offers})</button>
                    <button className={closetFilter === 'traded' ? 'primary' : 'ghost small'} type="button" onClick={() => setClosetFilter('traded')}>Traded ({closetBreakdown.traded})</button>
                  </div>
                </div>
                <div className="header-actions">
                  <button className="primary" type="button" onClick={openCreateListingModal}>Create Listing</button>
                </div>
              </div>
              {myListingsLoading ? (
                <div className="empty-state loading-state" role="status" aria-live="polite">
                  <span className="loading-dot" aria-hidden="true" />
                  <h3>Loading your closet...</h3>
                  <p>We are getting your listings ready.</p>
                </div>
              ) : filteredClosetListings.length === 0 ? (
                <div className="empty-state"><h3>No listings yet</h3><p>Analyze an item and publish your first listing to start trading.</p><button className="primary" type="button" onClick={openCreateListingModal}>Create first listing</button></div>
              ) : (
                <>
                  {analysisError && <p className="error-text">{analysisError}</p>}
                  {savedListingNotice && <p className="ok-text">{savedListingNotice}</p>}
                  <div className="listing-grid closet-listing-grid">{filteredClosetListings.map((item) => <ListingCard key={item.id} item={item} own onEditDraft={openEditListingModal} onReviewListing={openReviewListing} onPublishListing={publishListingToMarketplace} onRemoveListing={removeListingFromCloset} editorialStyle />)}</div>
                  {closetFilter === 'all' && myListingsHasMore ? (
                    <div className="load-more-row">
                      <button className="ghost" type="button" onClick={loadMoreMyListings} disabled={myListingsPageLoading}>
                        {myListingsPageLoading ? 'Loading...' : 'Load More Listings'}
                      </button>
                    </div>
                  ) : null}
                </>
              )}
            </section>
          )}

          {activeTab === 'inbox' && (
            <section className="panel">
	              <div className="panel-header">
	                <div><p className="eyebrow">Trade Inbox</p></div>
                <div className="market-controls">
                  <button className={offerStatusFilter === 'all' ? 'primary' : 'ghost small'} type="button" onClick={() => setOfferStatusFilter('all')}>All</button>
                  <button className={offerStatusFilter === 'pending' ? 'primary' : 'ghost small'} type="button" onClick={() => setOfferStatusFilter('pending')}>Pending</button>
                  <button className={offerStatusFilter === 'accepted' ? 'primary' : 'ghost small'} type="button" onClick={() => setOfferStatusFilter('accepted')}>Accepted</button>
                  <button className={offerStatusFilter === 'declined' ? 'primary' : 'ghost small'} type="button" onClick={() => setOfferStatusFilter('declined')}>Declined</button>
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
                    const selectableAddresses = completeProfileShippingAddresses
                    const selectedAddressId = offerReceiveAddressById[offer.offer_id] || (selectableAddresses.length === 1 ? selectableAddresses[0].id : '')
                    const selectedAddress = selectableAddresses.find((a) => a.id === selectedAddressId) || null
                    const offeredChoices = Array.isArray(offer.offered_listings) && offer.offered_listings.length > 0
                      ? offer.offered_listings
                      : (offer.offered_listing ? [offer.offered_listing] : [])
                    const selectedOfferedListingId = offerAcceptedListingById[offer.offer_id]
                      || offer.selected_offered_listing_id
                      || (offeredChoices.length === 1 ? listingRecordId(offeredChoices[0]) : '')
                    const quote = shippingQuoteByOffer[offer.offer_id]
                    const offerActionBusy = offerActionBusyById[offer.offer_id] || ''
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
                          <button type="button" className="inbox-target-hero" onClick={() => openTradeDetailListing(offer.target_listing || null)}>
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
                                <button key={`offered-${offer.offer_id}-${listing?.listing_id || 'listing'}-${url}`} type="button" className="inbox-thumb-btn" onClick={() => openTradeDetailListing(listing || null)}>
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
                            {offerParticipantName(offer, 'from')} wants to trade {offer.offered_listing?.title || 'their listing'}
                          </h3>
                          <p className="inbox-editorial-subtitle">For your {offer.target_listing?.title || 'listing'}</p>
                          {offer.message ? <p className="inbox-offer-message">Message: {offer.message}</p> : null}
                          {offer.status === 'pending' && (
                            <div className="button-row inbox-editorial-actions">
                              {canReceiverAccept && !actorAccepted ? (
                                <>
                                  <p className="tiny-note inbox-flow-note">
                                    Shipping cost to send your item: {
                                      quote?.status === 'quoted' && quote?.amount
                                        ? `${quote.currency || 'USD'} ${quote.amount} • ${quote.carrier || 'USPS'} ${quote.service_level || ''}`
                                        : quote?.status === 'loading'
                                          ? 'Calculating...'
                                          : 'Unavailable until shipping addresses are complete.'
                                    }
                                  </p>
                                  <label className="inbox-address-select">
                                    <span>Receive At Address</span>
                                    <select
                                      value={selectedAddressId}
                                      onChange={(e) => setOfferReceiveAddressById((prev) => ({ ...prev, [offer.offer_id]: e.target.value }))}
                                    >
                                      <option value="">
                                        {selectableAddresses.length === 0 ? 'Add complete address in Profile' : 'Select shipping address'}
                                      </option>
                                      {selectableAddresses.map((addr, idx) => (
                                        <option key={addr.id} value={addr.id}>{addr.label?.trim() || `Address ${idx + 1}`} - {addr.city || 'City'} {addr.state || ''}</option>
                                      ))}
                                    </select>
                                  </label>
                                  <label className="inbox-address-select">
                                    <span>Accepted Offered Item</span>
                                    <select
                                      value={selectedOfferedListingId || ''}
                                      onChange={(e) => setOfferAcceptedListingById((prev) => ({ ...prev, [offer.offer_id]: e.target.value }))}
                                    >
                                      <option value="">
                                        {offeredChoices.length === 0 ? 'No offered items available' : 'Select offered item'}
                                      </option>
                                      {offeredChoices.map((listing, idx) => (
                                        <option key={`${offer.offer_id}-choice-${listingRecordId(listing) || idx}`} value={listingRecordId(listing)}>
                                          {listing?.title || `Offered item ${idx + 1}`} - {money(listing?.estimated_value)}
                                        </option>
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
                                      selectedOfferedListingId,
                                    )}
                                    disabled={Boolean(offerActionBusy) || !selectedOfferedListingId}
                                  >
                                    {offerActionBusy === 'accepted' ? 'Accepting...' : 'Accept Trade'}
                                  </button>
                                  <button className="ghost" type="button" onClick={() => respondToOffer(offer.offer_id, 'declined')} disabled={Boolean(offerActionBusy)}>
                                    {offerActionBusy === 'declined' ? 'Declining...' : 'Decline'}
                                  </button>
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
                                  {offerShipments.map((s) => {
                                    const hasLabelUrl = Boolean(String(s.label_url || '').trim())
                                    const shipmentStatus = String(s.status || '').toLowerCase()
                                    const unavailableMessage = shipmentStatus === 'awaiting_shippo_config'
                                      ? 'Shipping labels are not configured on the server yet.'
                                      : 'Carrier label is not available yet.'
                                    return (
                                      <div key={s.shipment_id} className="inbox-label-card">
                                        <strong>{s.carrier} • {s.service_level}</strong>
                                        <div className="tiny-note">Tracking: {s.tracking_number || 'pending'}</div>
                                        <div className="tiny-note">Status: {shipmentTrackingLabel(s)}</div>
                                        {s.tracking_status_details ? <div className="tiny-note">{s.tracking_status_details}</div> : null}
                                        {s.tracking_eta ? <div className="tiny-note">Estimated delivery: {s.tracking_eta}</div> : null}
                                        <div className="tiny-note">From: {s.from_name || 'n/a'} • {s.from_city || ''} {s.from_state || ''}</div>
                                        <div className="tiny-note">To: {s.to_name || 'n/a'} • {s.to_city || ''} {s.to_state || ''}</div>
                                        {!hasLabelUrl ? <div className="tiny-note">{unavailableMessage}</div> : null}
                                        <button type="button" className="ghost small" disabled={!hasLabelUrl} onClick={() => openShippingLabel(s)}>
                                          {hasLabelUrl ? 'Download label' : 'Label unavailable'}
                                        </button>
                                      </div>
                                    )
                                  })}
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
                        </div>
                      </div>
                    </article>
                  )})}
                </div>
              )}
            </section>
          )}

          {activeTab === 'market' && (
            <section className="panel">
              <div className="panel-header">
	                <div><p className="eyebrow">Marketplace</p></div>
	                <div className="market-controls">
	                  <input value={marketSearch} onChange={(e) => setMarketSearch(e.target.value)} placeholder="Search brand, category, city, style..." />
	                </div>
              </div>
              <div className="market-layout">
                {marketListingsLoading ? (
                  <div className="empty-state loading-state" role="status" aria-live="polite">
                    <span className="loading-dot" aria-hidden="true" />
                    <h3>Loading marketplace listings...</h3>
                    <p>We are finding the latest active listings.</p>
                  </div>
                ) : selectedMarketListingIndex !== null && filteredListings[selectedMarketListingIndex] ? (
                  (() => {
                    const item = filteredListings[selectedMarketListingIndex]
                    const gallery = getListingGallery(item)
                    const own = isOwnedByCurrentUser(item)
                    const isLiked = likedListingIds.includes(String(item.id))
                    const similarMatches = getCrossOwnerMatches(item)
                    const matchPreviewListings = similarMatches
                      .map((candidate) => ({ candidate, thumb: getListingGallery(candidate)[0] }))
                    const selectedImageIdx = gallery.length > 0 ? Math.min(selectedMarketImageIndex, gallery.length - 1) : 0
                    const selectedImage = gallery[selectedImageIdx]
                    return (
                      <article className="market-selected-detail" key={`market-selected-${item.id}`}>
                        <div className="market-selected-viewer">
                          <div className={`market-selected-gallery ${gallery.length <= 1 ? 'single-image' : ''}`} aria-label={`${item.title || 'Listing'} images`}>
                            <div className="market-selected-main-image">
                              {selectedImage ? (
                                <button
                                  type="button"
                                  className="listing-image-zoom-trigger"
                                  onClick={() => openZoomedListingImage({
                                    src: selectedImage,
                                    alt: `${item.title || 'Listing'} image ${selectedImageIdx + 1}`,
                                  })}
                                  aria-label={`Magnify ${item.title || 'listing'} image ${selectedImageIdx + 1}`}
                                >
                                  <img src={selectedImage} alt={`${item.title || 'Listing'} image ${selectedImageIdx + 1}`} />
                                  <span className="listing-image-zoom-label">Magnify</span>
                                </button>
                              ) : (
                                <div className="listing-image-fallback">Image unavailable</div>
                              )}
                            </div>
                            {gallery.length > 1 && (
                              <div className="market-selected-thumbnails" aria-label="Listing image thumbnails">
                                {gallery.map((src, idx) => (
                                  <button
                                    key={`${item.id}-selected-gallery-thumb-${idx}`}
                                    type="button"
                                    className={idx === selectedImageIdx ? 'active' : ''}
                                    onClick={() => setSelectedMarketImageIndex(idx)}
                                    aria-label={`Show image ${idx + 1}`}
                                    aria-current={idx === selectedImageIdx ? 'true' : undefined}
                                  >
                                    <img src={src} alt="" />
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>

                          <div className="market-selected-details">
                            <div className="market-selected-head">
                              <div>
                                <h3>{item.title || 'Untitled listing'}</h3>
                                <p className="editorial-byline">BY {ownerFirstName(item.owner, 'Member').toUpperCase()}</p>
                                <p className="editorial-meta">
                                  EST. {money(item.estimatedValue)} · {String(item.brand || 'Unknown').toUpperCase()} · {displayConditionLabel(item.condition).toUpperCase()} · SIZE {String(item.size || 'N/A').toUpperCase()}
                                </p>
                              </div>
                              <div className="market-selected-actions">
                                {!own && (
                                  <button
                                    className={`ghost small listing-like-btn ${isLiked ? 'is-liked' : ''}`}
                                    type="button"
                                    onClick={() => toggleMarketplaceLike(item.id)}
                                    title={isLiked ? 'Unlike listing' : 'Like listing'}
                                    aria-label={isLiked ? 'Unlike listing' : 'Like listing'}
                                  >
                                    <LikeIcon liked={isLiked} />
                                  </button>
                                )}
                                <button
                                  className="ghost small"
                                  type="button"
                                  onClick={() => {
                                    if (typeof window !== 'undefined' && tabFromLocation() === 'market' && listingIdFromLocation() && window.history.length > 1) {
                                      window.history.back()
                                      return
                                    }
                                    setSelectedMarketListingIndex(null)
                                    setSelectedMarketImageIndex(0)
                                    if (typeof window !== 'undefined') {
                                      window.history.replaceState({}, '', tabHref('market'))
                                    }
                                  }}
                                >
                                  Back
                                </button>
                              </div>
                            </div>

                            <ListingDescriptionParagraphs item={item} className="market-selected-description" />

                            {similarMatches.length > 0 ? (
                              <div className="market-selected-matches">
                                <span className="market-selected-matches-label">Matched Items</span>
                                <span className="match-thumb-strip market-selected-match-thumbs">
                                  {matchPreviewListings.slice(0, 3).map(({ candidate, thumb }, idx) => (
                                    thumb ? (
                                      <button
                                        key={`${item.id}-selected-match-${idx}`}
                                        type="button"
                                        className="match-thumb-button"
                                        onClick={() => {
                                          openTradeDetailListing(candidate)
                                        }}
                                        aria-label={`View matched item ${candidate?.title || idx + 1}`}
                                      >
                                        <img
                                          src={thumb}
                                          alt=""
                                          className="match-thumb"
                                        />
                                      </button>
                                    ) : (
                                      <button
                                        key={`${item.id}-selected-match-${idx}`}
                                        type="button"
                                        className="match-thumb match-thumb-button market-selected-match-placeholder"
                                        onClick={() => {
                                          openTradeDetailListing(candidate)
                                        }}
                                        aria-label={`View matched item ${candidate?.title || idx + 1}`}
                                      >
                                        Match
                                      </button>
                                    )
                                  ))}
                                </span>
                                <button className="ghost small" type="button" onClick={() => openMarketMatches(item)}>View Matches</button>
                              </div>
                            ) : null}

                            <div className="button-row">
                              {!own ? (
                                <button type="button" onClick={() => openTradeComposer(item)}>Start Trade</button>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      </article>
                    )
                  })()
                ) : filteredListings.length === 0 ? (
                  <div className="empty-state">
                    {marketListingsHasMore && !marketSearch.trim() ? (
                      <>
                        <h3>Looking for matched listings...</h3>
                        <p>More marketplace listings are available to check.</p>
                        <button className="ghost" type="button" onClick={loadMoreMarketListings} disabled={marketListingsPageLoading}>
                          {marketListingsPageLoading ? 'Loading...' : 'Load More Listings'}
                        </button>
                      </>
                    ) : (
                      <>
                        <h3>No matched marketplace listings yet</h3>
                        <p>Create or publish a closet listing to see marketplace items that match your closet.</p>
                        <button className="primary" type="button" onClick={openCreateListingFromCloset}>Create Listing</button>
                      </>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="listing-grid market-listing-grid market-editorial-grid">
                      {filteredListings.map((item) => {
                        const isOwnListing = isOwnedByCurrentUser(item)
                        const baseValue = Number(item.estimatedValue || 0)
                        const similarMatches = getCrossOwnerMatches(item)
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
                            onOpenDetails={openMarketplaceListingDetails}
                            isOwnListing={isOwnListing}
                            liked={likedListingIds.includes(String(item.id))}
                            onToggleLike={() => toggleMarketplaceLike(item.id)}
                          />
                        )
                      })}
                    </div>
                    {marketListingsHasMore && !marketSearch.trim() ? (
                      <div className="load-more-row">
                        <button className="ghost" type="button" onClick={loadMoreMarketListings} disabled={marketListingsPageLoading}>
                          {marketListingsPageLoading ? 'Loading...' : 'Load More Listings'}
                        </button>
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            </section>
          )}

          {activeTab === 'trade' && (
            <section className="panel trade-page trade-editorial">
	              <div className="panel-header">
	                <div>
	                  <p className="eyebrow">Trade Offer</p>
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
                      <button className="ghost small" type="button" onClick={() => openTradeDetailListing(tradeComposerTarget)}>View details</button>
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
                        Selected choices: {selectedTradeOfferListings.length} • Target: {money(composerTargetValue)}
                      </p>
                    <p className={composerWithinBand ? 'ok-text trade-band-line' : 'error-text trade-band-line'}>
                      {composerWithinBand ? 'Each selected item is within the 30% trade band' : 'Select at least one item within the 30% trade band'}
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
	                <div><p className="eyebrow">Admin</p></div>
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
        <div className="trade-detail-backdrop">
          <div className="trade-detail-shell">
            {(() => {
              const detailGallery = getListingGallery(tradeDetailListing)
              const activeDetailImageIndex = detailGallery.length > 0 ? Math.min(tradeDetailImageIndex, detailGallery.length - 1) : 0
              const activeDetailImage = detailGallery[activeDetailImageIndex]
              const ownerName = tradeDetailListing.owner || tradeDetailListing.owner_name || 'Member'
              const detailValue = tradeDetailListing.estimatedValue ?? tradeDetailListing.estimated_value
              return (
                <article className="market-selected-detail trade-detail-market-view">
                  <div className="market-selected-viewer">
                    <div className={`market-selected-gallery ${detailGallery.length <= 1 ? 'single-image' : ''}`} aria-label={`${tradeDetailListing.title || 'Listing'} images`}>
                      <div className="market-selected-main-image trade-detail-main-image">
                        {activeDetailImage ? (
                          <button
                            type="button"
                            className="listing-image-zoom-trigger"
                            onClick={() => openZoomedListingImage({
                              src: activeDetailImage,
                              alt: `${tradeDetailListing.title || 'Listing'} image ${activeDetailImageIndex + 1}`,
                            })}
                            aria-label={`Magnify ${tradeDetailListing.title || 'listing'} image ${activeDetailImageIndex + 1}`}
                          >
                            <img src={activeDetailImage} alt={`${tradeDetailListing.title || 'Listing'} image ${activeDetailImageIndex + 1}`} />
                            <span className="listing-image-zoom-label">Magnify</span>
                          </button>
                        ) : (
                          <div className="listing-image-fallback">Image unavailable</div>
                        )}
                      </div>
                      {detailGallery.length > 1 && (
                        <div className="market-selected-thumbnails" aria-label="Listing image thumbnails">
                          {detailGallery.map((url, idx) => (
                            <button
                              key={`${tradeDetailListing.id || tradeDetailListing.listing_id}-detail-thumb-${idx}`}
                              type="button"
                              className={idx === activeDetailImageIndex ? 'active' : ''}
                              onClick={() => setTradeDetailImageIndex(idx)}
                              aria-label={`Show image ${idx + 1}`}
                              aria-current={idx === activeDetailImageIndex ? 'true' : undefined}
                            >
                              <img src={url} alt="" />
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="market-selected-details">
                      <div className="market-selected-head">
                        <div>
                          <h3>{tradeDetailListing.title || 'Untitled listing'}</h3>
                          <p className="editorial-byline">BY {ownerFirstName(ownerName, 'Member').toUpperCase()}</p>
                          <p className="editorial-meta">
                            EST. {money(detailValue)} · {String(tradeDetailListing.brand || 'Unknown').toUpperCase()} · {displayConditionLabel(tradeDetailListing.condition).toUpperCase()} · SIZE {String(tradeDetailListing.size || 'N/A').toUpperCase()}
                          </p>
                        </div>
                        <div className="market-selected-actions">
                          <button className="ghost small" type="button" onClick={() => setTradeDetailListing(null)}>
                            Back
                          </button>
                        </div>
                      </div>

                      <ListingDescriptionParagraphs item={tradeDetailListing} className="market-selected-description" />
                    </div>
                  </div>
                </article>
              )
            })()}
          </div>
        </div>
      )}

      {zoomedListingImage && (
        <div
          className="listing-image-zoom-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Magnified listing image"
          onClick={closeZoomedListingImage}
        >
          <div className="listing-image-zoom-toolbar" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              onClick={() => adjustZoomedListingImageScale(-0.25)}
              disabled={zoomedListingImageScale <= 0.5}
              aria-label="Zoom out"
            >
              -
            </button>
            <span>{Math.round(zoomedListingImageScale * 100)}%</span>
            <button
              type="button"
              onClick={() => adjustZoomedListingImageScale(0.25)}
              disabled={zoomedListingImageScale >= 3}
              aria-label="Zoom in"
            >
              +
            </button>
            <button type="button" onClick={() => setZoomedListingImageScale(0.5)}>
              Reset
            </button>
            <button
              type="button"
              onClick={closeZoomedListingImage}
            >
              Close
            </button>
          </div>
          <div className="listing-image-zoom-stage" onClick={(e) => e.stopPropagation()}>
            <img
              src={zoomedListingImage.src}
              alt={zoomedListingImage.alt || 'Magnified listing image'}
              style={{ width: `${zoomedListingImageScale * 100}%` }}
              onClick={() => adjustZoomedListingImageScale(0.25)}
            />
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
                        <button className="ghost small" type="button" onClick={() => openTradeDetailListing(sim)}>View details</button>
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
              <h3>Create Listing</h3>
              <button className="ghost small" type="button" onClick={() => setShowCreateListingModal(false)} disabled={analysisLoading || createListingBusy}>Close</button>
            </div>
            <p className="tiny-note listing-modal-note">Step 1: Upload images and select condition.</p>
            {createListingBusy && <p className="ok-text">Uploading photos and creating listing...</p>}
            {analysisLoading && <p className="ok-text">Analyzing photos...</p>}
            {analysisError && <p className="error-text">{analysisError}</p>}
            {savedListingNotice && !analysisLoading && !createListingBusy && <p className="ok-text">{savedListingNotice}</p>}

            <label>
              <span>Photos (1-6)</span>
              <input
                type="file"
                accept="image/*"
                multiple
                onChange={(e) => {
                  const next = Array.from(e.target.files || []).slice(0, 6)
                  setImages(next)
                  setSelectedCreateImageIndex(0)
                  setEditImageCount(next.length)
                  setEditPreviewUrls([])
                  setReceiptPromptPending(false)
                  setReceiptPromptDismissed(false)
                }}
              />
            </label>
            <label>
              <span>Category</span>
              <select
                value={category}
                onChange={(e) => {
                  const nextCategory = e.target.value
                  setCategory(nextCategory)
                  if (itemSize && !sizeOptionsForCategory(nextCategory).includes(itemSize)) setItemSize('')
                }}
              >
                <option value="">Select category</option>
                <option value="clothes">Clothes</option>
                <option value="shoes">Shoes</option>
                <option value="handbag">Handbag</option>
              </select>
            </label>
            <label className="listing-modal-field">
              <span>Your condition assessment</span>
              <select value={userCondition} onChange={(e) => setUserCondition(e.target.value)} required>
                <option value="">Select condition</option>
                <option value="NewWithTags">New with Tags</option>
                <option value="New">New</option>
                <option value="LikeNew">Like New</option>
              </select>
            </label>
            <label>
              <span>Size</span>
              <select value={itemSize} onChange={(e) => setItemSize(e.target.value)}>
                {(() => {
                  const options = sizeOptionsForCategory(category)
                  return (
                    <>
                      <option value="">{options.length ? 'Select size' : 'Select category first'}</option>
                      {options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                    </>
                  )
                })()}
              </select>
            </label>

            <div className="listing-modal-image-grid listing-modal-image-grid-top">
              {modalPreviewUrls.map((url, idx) => (
                <div key={url} className={`listing-modal-thumb ${idx === selectedCreateImageIndex ? 'is-hero' : ''}`}>
                  <img src={url} alt={`Upload ${idx + 1}`} />
                  {idx === selectedCreateImageIndex && <span className="listing-hero-badge">Hero</span>}
                  <button
                    className="listing-modal-set-hero"
                    type="button"
                    onClick={() => setSelectedCreateImageIndex(idx)}
                  >
                    Set Hero
                  </button>
                </div>
              ))}
            </div>

            <div className="button-row listing-modal-actions">
              <button className="ghost" type="button" onClick={() => setShowCreateListingModal(false)} disabled={analysisLoading || createListingBusy}>Cancel</button>
              <button
                className="primary"
                type="button"
                disabled={analysisLoading || createListingBusy}
                onClick={async () => {
                  const currentImageCount = modalPreviewUrls.length
                  if (currentImageCount < 1 || currentImageCount > 6) {
                    setAnalysisError('Upload 1 to 6 images before continuing.')
                    return
                  }
                  if (!userCondition) {
                    setAnalysisError('Select item condition before continuing.')
                    return
                  }
                  await createListingAndRunAsyncAnalysis()
                }}
              >
                {createListingBusy ? 'Creating...' : 'Create Listing'}
              </button>
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
                    await syncStripePaymentMethodsRemote({
                      apiBaseUrl,
                      apiKey: clerkEnabled ? '' : apiKey.trim(),
                      bearerToken,
                    })
                    await reloadProfileTabAfterSuccess('Payment method added via Stripe.')
                    setPaymentActionMsg('Payment method added.')
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

      {subscriptionConfirmRequest && (
        <div className="app-alert-overlay" role="presentation" onClick={() => resolveSubscriptionConfirmation(false)}>
          <section
            className="app-alert-card subscription-confirm-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="subscription-confirm-title"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="eyebrow">JOUFT MEMBERSHIP</p>
            <h3 id="subscription-confirm-title">Confirm Subscription</h3>
            <p>Review your plan and payment method before we process your subscription.</p>
            <dl className="subscription-confirm-details">
              <div>
                <dt>Plan</dt>
                <dd>{subscriptionConfirmRequest.planName}</dd>
              </div>
              <div>
                <dt>Amount</dt>
                <dd>{subscriptionConfirmRequest.amountLabel}</dd>
              </div>
              <div>
                <dt>Payment</dt>
                <dd>{subscriptionConfirmRequest.paymentLabel}</dd>
              </div>
            </dl>
            <div className="button-row app-alert-actions">
              <button className="ghost" type="button" onClick={() => resolveSubscriptionConfirmation(false)}>
                Cancel
              </button>
              <button className="primary" type="button" onClick={() => resolveSubscriptionConfirmation(true)}>
                Process Payment
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

function LikeIcon({ liked = false }) {
  return (
    <svg className="listing-like-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M12 21s-6.7-4.35-9.23-7.95C.66 10.09 1.5 6.23 4.93 4.97c2.2-.81 4.2.1 5.53 1.73 1.33-1.63 3.33-2.54 5.53-1.73 3.43 1.26 4.27 5.12 2.16 8.08C18.7 16.65 12 21 12 21Z"
        fill={liked ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function SocialShareIcon({ network }) {
  const Icon = network === 'facebook' ? FaFacebookF : FaPinterestP
  return <Icon className="listing-share-icon" aria-hidden="true" focusable="false" />
}

function ListingImage({ src, alt, onFailed }) {
  const [status, setStatus] = useState('loading')
  const [blobUrl, setBlobUrl] = useState('')

  useEffect(() => {
    if (!src) {
      setStatus('failed')
      setBlobUrl('')
      return undefined
    }
    if (!shouldRenderListingImageAsBlob(src)) {
      setBlobUrl('')
      setStatus('direct')
      return undefined
    }

    const controller = new AbortController()
    let cancelled = false
    let createdBlobUrl = ''
    setStatus('loading')
    setBlobUrl('')
    fetchListingImageBlobUrl(src, controller.signal)
      .then((url) => {
        createdBlobUrl = url
        if (cancelled) {
          URL.revokeObjectURL(url)
          return
        }
        setBlobUrl(url)
        setStatus('loaded')
      })
      .catch((err) => {
        if (cancelled || err?.name === 'AbortError') return
        setBlobUrl('')
        setStatus('direct')
      })

    return () => {
      cancelled = true
      controller.abort()
      if (createdBlobUrl) URL.revokeObjectURL(createdBlobUrl)
    }
  }, [src])

  if (!src || status === 'failed') {
    return (
      <div className="listing-image-fallback" aria-label="No image available">
        Image unavailable
      </div>
    )
  }

  return (
    <>
      {status === 'loading' && (
        <div className="listing-image-fallback listing-image-loading" aria-label="Image loading">
          Loading image...
        </div>
      )}
      {status !== 'loading' && (
        <img
          src={blobUrl || src}
          alt={alt}
          onLoad={() => setStatus('loaded')}
          onError={() => {
            setStatus('failed')
            onFailed?.(src)
          }}
        />
      )}
    </>
  )
}

function ListingCard({ item, own = false, onEditDraft = null, onReviewListing = null, onPublishListing = null, onRemoveListing = null, marketplaceCompact = false, onOpenTrade = null, myTradeCandidates = [], onOpenMatches = null, matchPreviewImages = [], editorialStyle = false, onOpenDetails = null, isOwnListing = false, liked = false, onToggleLike = null }) {
  const rawGallery = Array.isArray(item.images) && item.images.length > 0
    ? item.images
    : [item.image].filter(Boolean)
  const [failedImageSrcs, setFailedImageSrcs] = useState(() => new Set())
  useEffect(() => {
    setFailedImageSrcs(new Set())
  }, [item?.id, rawGallery.join('|')])
  const gallery = rawGallery.filter((src) => !failedImageSrcs.has(src))
  const cardGallery = gallery.slice(0, 1)
  const imageSrc = gallery[0] || null

  const statusLabel = item.status || 'Review'
  const statusClass = `status-${String(statusLabel).toLowerCase().replace(/\s+/g, '')}`
  const normalizedStatus = String(statusLabel).toLowerCase()
  const analysisInProgress = normalizedStatus === 'analyzing'
  const cardDisabled = own && analysisInProgress
  const editDisabled = own && analysisInProgress
  const analysisFailed = normalizedStatus === 'analysisfailed'
  const canReviewAndPublish = own && typeof onReviewListing === 'function' && !['active', 'analyzing', 'analysisfailed'].includes(normalizedStatus)
  const badgeLabel = item.status || 'Active'
  const badgeClass = `status-${String(badgeLabel).toLowerCase().replace(/\s+/g, '')}`
  const brandLabel = String(item.brand || '').trim() || 'Unknown brand'
  const conditionLabel = displayConditionLabel(item.condition)
  const cityLabel = String(item.city || '').trim() || 'Unknown city'
  const sizeLabel = String(item.size || '').trim() || 'N/A'
  const isEditorial = editorialStyle || (marketplaceCompact && !own)
  const isDetailClickable = typeof onOpenDetails === 'function' && !cardDisabled
  const showLikeButton = !own && !isOwnListing && typeof onToggleLike === 'function'

  function openDetailPage() {
    if (!isDetailClickable) return
    onOpenDetails(item)
  }

  const markImageFailed = useCallback((src) => {
    if (!src) return
    setFailedImageSrcs((prev) => {
      if (prev.has(src)) return prev
      const next = new Set(prev)
      next.add(src)
      return next
    })
  }, [])

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

  async function shareToPinterest(e) {
    e?.stopPropagation?.()
    if (typeof window === 'undefined') return
    const caption = buildListingShareCaption(item)
    const listingId = String(item?.listing_id || item?.id || '').trim()
    const base = API_DEFAULT.replace(/\/$/, '')
    const fallbackUrl = typeof window.location?.href === 'string' ? window.location.href : 'https://jouft.com'
    const shareUrl = listingId
      ? `${base}/v1/share/listings/${encodeURIComponent(listingId)}`
      : fallbackUrl
    const mediaUrl = typeof imageSrc === 'string' && imageSrc.trim() ? imageSrc.trim() : ''
    const url = `https://www.pinterest.com/pin/create/button/?url=${encodeURIComponent(shareUrl)}&description=${encodeURIComponent(caption)}${mediaUrl ? `&media=${encodeURIComponent(mediaUrl)}` : ''}`
    window.open(url, '_blank', 'noopener,noreferrer,width=900,height=700')
  }

  return (
    <>
      <article
        className={`listing-card ${own ? 'closet-listing-card' : ''} ${isEditorial ? 'market-editorial' : ''} ${isDetailClickable ? 'is-clickable' : ''} ${cardDisabled ? 'is-disabled' : ''}`}
        onClick={isDetailClickable ? openDetailPage : undefined}
        role={isDetailClickable ? 'button' : undefined}
        tabIndex={isDetailClickable ? 0 : undefined}
        aria-disabled={cardDisabled || undefined}
        onKeyDown={isDetailClickable ? (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            openDetailPage()
          }
        } : undefined}
      >
        <div className={`image-wrap ${cardGallery.length > 1 ? 'multi-images' : ''}`}>
        {cardGallery.length > 1 ? (
          <div className="listing-image-grid" role="img" aria-label={`${item.title || 'Listing'} images`}>
            {cardGallery.map((src, idx) => (
              <ListingImage
                key={`${item.id}-gallery-${idx}`}
                src={src}
                alt={`${item.title || 'Listing'} image ${idx + 1}`}
                onFailed={markImageFailed}
              />
            ))}
          </div>
        ) : imageSrc ? (
          <ListingImage src={imageSrc} alt={item.title} onFailed={markImageFailed} />
        ) : (
          <div className="listing-image-fallback" aria-label="No image available">
            Image unavailable
          </div>
        )}
        {own && !isEditorial && <span className={`status-badge ${badgeClass}`}>{badgeLabel}</span>}
      </div>
      <div className="listing-body">
        {isEditorial ? (
          <>
            <div className="editorial-title-row">
              <h3 className="editorial-title">{item.title || 'Untitled listing'}</h3>
              {showLikeButton && (
                <button
                  className={`editorial-match-btn listing-like-btn listing-like-title ${liked ? 'is-liked' : ''}`}
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onToggleLike()
                  }}
                  title={liked ? 'Unlike listing' : 'Like listing'}
                  aria-label={liked ? 'Unlike listing' : 'Like listing'}
                >
                  <LikeIcon liked={liked} />
                </button>
              )}
            </div>
            <p className="editorial-byline">BY {ownerFirstName(item.owner, 'Member').toUpperCase()}</p>
            <p className="editorial-meta">
              EST. {money(item.estimatedValue)} · {brandLabel.toUpperCase()} · {conditionLabel.toUpperCase()} · SIZE {sizeLabel.toUpperCase()}
            </p>
            {own && analysisFailed && (
              <p className="listing-analysis-failed-message">
                Analysis failed. Please manually update the listing details.
              </p>
            )}
            <div className="listing-footer editorial-footer">
              <div className="listing-actions">
                {!own && matchPreviewImages.length > 0 && (
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
                      {matchPreviewImages.slice(0, 3).map((src, idx) => (
                        <img key={`${item.id}-match-${idx}`} src={src} alt="" className="match-thumb" />
                      ))}
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
                      <span>EDIT LISTING</span>
                    </button>
                    {typeof onRemoveListing === 'function' && (
                      <button
                        className="editorial-match-btn listing-remove-btn listing-icon-btn"
                        type="button"
                        title="Delete listing"
                        aria-label="Delete listing"
                        onClick={(e) => {
                          e.stopPropagation()
                          onRemoveListing(item)
                        }}
                      >
                        <FiTrash2 aria-hidden="true" />
                      </button>
                    )}
                    <button
                      className="editorial-match-btn listing-share-icon-btn"
                      type="button"
                      onClick={shareToFacebook}
                      title="Share on Facebook"
                      aria-label="Share on Facebook"
                    >
                      <SocialShareIcon network="facebook" />
                    </button>
                    <button
                      className="editorial-match-btn listing-share-icon-btn"
                      type="button"
                      onClick={shareToPinterest}
                      title="Share on Pinterest"
                      aria-label="Share on Pinterest"
                    >
                      <SocialShareIcon network="pinterest" />
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
            {own && analysisFailed && (
              <p className="listing-analysis-failed-message">
                Analysis failed. Please manually update the listing details.
              </p>
            )}
            {!marketplaceCompact && <div className="tag-row">{(item.tags || []).slice(0, 4).map((tag) => <span key={tag}>{tag}</span>)}</div>}
            {(!marketplaceCompact || !own) && (
              <div className="listing-footer">
                <div className="listing-footer-meta">
                  <small>{own ? 'Your listing' : `Listed by ${ownerFirstName(item.owner, 'Member')}`}</small>
                </div>
                <div className="listing-actions">
                  {!own && matchPreviewImages.length > 0 && (
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
                        {matchPreviewImages.slice(0, 3).map((src, idx) => (
                          <img key={`${item.id}-match-${idx}`} src={src} alt="" className="match-thumb" />
                        ))}
                      </span>
                    </button>
                  )}
                  {!own && !isOwnListing && !isEditorial && typeof onToggleLike === 'function' && (
                    <button
                      className={`ghost small listing-like-btn ${liked ? 'is-liked' : ''}`}
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        onToggleLike()
                      }}
                      title={liked ? 'Unlike listing' : 'Like listing'}
                      aria-label={liked ? 'Unlike listing' : 'Like listing'}
                    >
                      <LikeIcon liked={liked} />
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
                        Edit Listing
                      </button>
                      {typeof onRemoveListing === 'function' && (
                        <button
                          className="ghost small listing-remove-btn listing-icon-btn"
                          type="button"
                          title="Delete listing"
                          aria-label="Delete listing"
                          onClick={(e) => {
                            e.stopPropagation()
                            onRemoveListing(item)
                          }}
                        >
                          <FiTrash2 aria-hidden="true" />
                        </button>
                      )}
                      <button
                        className="ghost small listing-share-icon-btn"
                        type="button"
                        onClick={shareToFacebook}
                        title="Share on Facebook"
                        aria-label="Share on Facebook"
                      >
                        <SocialShareIcon network="facebook" />
                      </button>
                      <button
                        className="ghost small listing-share-icon-btn"
                        type="button"
                        onClick={shareToPinterest}
                        title="Share on Pinterest"
                        aria-label="Share on Pinterest"
                      >
                        <SocialShareIcon network="pinterest" />
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
      {cardDisabled && (
        <span className="listing-review-overlay" aria-hidden="true">Pending Review</span>
      )}
      {canReviewAndPublish && (
        <button
          className="listing-review-overlay listing-review-overlay-button"
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onReviewListing?.(item)
          }}
        >
          Review and Publish
        </button>
      )}
      </article>
    </>
  )
}

function AdminAnalysisCard({ entry }) {
  const response = entry.response || {}
  const debug = response.debug || {}
  const profile = response.item_profile || {}
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
      <VisualConditionDebug assessment={profile.visual_condition_assessment} />
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
