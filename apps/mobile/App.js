import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Linking,
  Share,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import Constants from 'expo-constants';
import { StatusBar } from 'expo-status-bar';
import { ClerkProvider, useAuth, useClerk, useSignIn, useSignUp, useUser } from '@clerk/clerk-expo';
import { tokenCache } from '@clerk/clerk-expo/token-cache';
import { createMobileApiClient } from './src/lib/apiClient';

const API_DEFAULT = Constants.expoConfig?.extra?.apiBaseUrl || 'http://127.0.0.1:8000';
const CLERK_PUBLISHABLE_KEY = Constants.expoConfig?.extra?.clerkPublishableKey || process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY || '';
const TABS = ['marketplace', 'closet', 'create', 'inbox', 'profile'];
const TAB_LABELS = {
  marketplace: 'Market',
  closet: 'Closet',
  create: 'Create',
  inbox: 'Inbox',
  profile: 'Profile',
};
const OFFER_FILTERS = ['pending', 'accepted', 'declined', 'all'];
const SUBSCRIPTION_PLANS = [
  { key: 'free', label: 'Free', monthly: 0, annual: 0, limit: '3 listings / month' },
  { key: 'starter_15', label: '$15 Plan', monthly: 15, annual: 162, limit: '25 listings / month' },
  { key: 'pro_25', label: '$25 Plan', monthly: 25, annual: 270, limit: 'Unlimited listings' },
];
const FEMALE_APPAREL_SIZE_OPTIONS = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL'];
const MALE_APPAREL_SIZE_OPTIONS = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'];
const FEMALE_SHOE_SIZE_OPTIONS = ['US 5', 'US 5.5', 'US 6', 'US 6.5', 'US 7', 'US 7.5', 'US 8', 'US 8.5', 'US 9', 'US 9.5', 'US 10', 'US 10.5', 'US 11', 'US 12'];
const MALE_SHOE_SIZE_OPTIONS = ['US 6', 'US 6.5', 'US 7', 'US 7.5', 'US 8', 'US 8.5', 'US 9', 'US 9.5', 'US 10', 'US 10.5', 'US 11', 'US 11.5', 'US 12', 'US 13', 'US 14'];
const PROFILE_CATEGORY_OPTIONS = ['Dresses', 'Jackets', 'Shoes', 'Handbags', 'Skirts', 'Accessories'];
const OFFER_POLL_INTERVAL_MS = 45000;

let DeviceModule = null;
let NotificationsModule = null;
try {
  DeviceModule = require('expo-device');
} catch (e) {
  DeviceModule = null;
}
try {
  NotificationsModule = require('expo-notifications');
  NotificationsModule.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: false,
      shouldSetBadge: false,
    }),
  });
} catch (e) {
  NotificationsModule = null;
}

const theme = {
  bg: '#f7f3ee',
  surface: '#fffdf9',
  text: '#18181b',
  muted: '#6d6760',
  line: '#e3dbd0',
  brand: '#4a161b',
  brandSoft: '#f1e8e1',
  success: '#155e4a',
  error: '#a82222',
};

function titleCase(input) {
  return String(input || '')
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(' ');
}

function buildSuggestedDescriptionFromProfile(profile) {
  const modelName = profile?.model_identification?.name?.trim?.() || '';
  const attrs = Array.isArray(profile?.model_identification?.attributes)
    ? profile.model_identification.attributes.filter((a) => typeof a === 'string' && a.trim()).slice(0, 6)
    : [];
  if (!modelName && attrs.length === 0) return '';
  if (modelName && attrs.length === 0) return `Pre-owned ${modelName}.`;
  if (!modelName && attrs.length > 0) return `Key details: ${attrs.join(', ')}.`;
  return `${modelName}. Key details: ${attrs.join(', ')}.`;
}

function normalizeImageUrl(url, apiBaseUrl) {
  if (!url || typeof url !== 'string') return null;
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  if (url.startsWith('/')) return `${String(apiBaseUrl || '').replace(/\/$/, '')}${url}`;
  return url;
}

function getMatchPreviewImages(item, apiBaseUrl) {
  const matches = Array.isArray(item?.matches) ? item.matches : [];
  return matches
    .map((match) => {
      const raw = Array.isArray(match?.images) && match.images.length > 0 ? match.images[0] : match?.image;
      return normalizeImageUrl(raw, apiBaseUrl);
    })
    .filter(Boolean)
    .slice(0, 3);
}

function listingGallery(listing, apiBaseUrl) {
  if (!listing || typeof listing !== 'object') return [];
  const raw = Array.isArray(listing.images) && listing.images.length > 0
    ? listing.images
    : [listing.image].filter(Boolean);
  return raw.map((url) => normalizeImageUrl(url, apiBaseUrl)).filter(Boolean);
}

function money(value) {
  const amount = Number(value || 0);
  return `$${Number.isFinite(amount) ? amount.toFixed(0) : '0'}`;
}

function makeId(prefix) {
  const cryptoApi = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined;
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return `${prefix}-${cryptoApi.randomUUID()}`;
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function listingDescription(listing) {
  const candidates = [
    listing?.description,
    listing?.wants,
    listing?.notes,
    listing?.trade_notes,
  ];
  const first = candidates.find((value) => typeof value === 'string' && value.trim());
  return first ? first.trim() : '';
}

function offerOfferedListings(offer) {
  return Array.isArray(offer?.offered_listings) && offer.offered_listings.length > 0
    ? offer.offered_listings
    : (offer?.offered_listing ? [offer.offered_listing] : []);
}

function normalizeShippingAddresses(addresses, fallbackProfile = null) {
  const normalized = Array.isArray(addresses)
    ? addresses
      .filter((entry) => entry && typeof entry === 'object')
      .map((entry, idx) => ({
        id: typeof entry.id === 'string' && entry.id.trim() ? entry.id : `addr-${idx + 1}`,
        label: typeof entry.label === 'string' && entry.label.trim() ? entry.label.trim() : `Address ${idx + 1}`,
        full_name: typeof entry.full_name === 'string' ? entry.full_name : '',
        address_line1: typeof entry.address_line1 === 'string' ? entry.address_line1 : '',
        address_line2: typeof entry.address_line2 === 'string' ? entry.address_line2 : '',
        city: typeof entry.city === 'string' ? entry.city : '',
        state: typeof entry.state === 'string' ? entry.state : '',
        postal_code: typeof entry.postal_code === 'string' ? entry.postal_code : '',
        country: typeof entry.country === 'string' && entry.country.trim() ? entry.country : 'US',
      }))
      .filter((entry) => entry.address_line1 && entry.city && entry.state && entry.postal_code)
    : [];
  if (normalized.length > 0) return normalized;
  const legacy = fallbackProfile && typeof fallbackProfile === 'object'
    ? {
      id: 'primary',
      label: 'Primary',
      full_name: fallbackProfile.shipping_full_name || '',
      address_line1: fallbackProfile.shipping_address_line1 || '',
      address_line2: fallbackProfile.shipping_address_line2 || '',
      city: fallbackProfile.shipping_city || '',
      state: fallbackProfile.shipping_state || '',
      postal_code: fallbackProfile.shipping_postal_code || '',
      country: fallbackProfile.shipping_country || 'US',
    }
    : null;
  if (legacy && legacy.address_line1 && legacy.city && legacy.state && legacy.postal_code) return [legacy];
  return [];
}

function normalizeProfileShippingAddresses(addresses, fallbackProfile = null) {
  const normalized = Array.isArray(addresses)
    ? addresses
      .filter((entry) => entry && typeof entry === 'object')
      .map((entry) => ({
        id: typeof entry.id === 'string' && entry.id.trim() ? entry.id : makeId('ship'),
        label: typeof entry.label === 'string' ? entry.label : '',
        full_name: typeof entry.full_name === 'string' ? entry.full_name : '',
        address_line1: typeof entry.address_line1 === 'string' ? entry.address_line1 : '',
        address_line2: typeof entry.address_line2 === 'string' ? entry.address_line2 : '',
        city: typeof entry.city === 'string' ? entry.city : '',
        state: typeof entry.state === 'string' ? entry.state : '',
        postal_code: typeof entry.postal_code === 'string' ? entry.postal_code : '',
        country: typeof entry.country === 'string' && entry.country.trim() ? entry.country : 'US',
        is_default: Boolean(entry.is_default),
      }))
    : [];
  if (normalized.length > 0) return normalized;
  const fallback = normalizeShippingAddresses([], fallbackProfile);
  if (fallback.length > 0) return fallback.map((entry) => ({ ...entry, id: entry.id || makeId('ship') }));
  return [{
    id: makeId('ship'),
    label: 'Primary',
    full_name: '',
    address_line1: '',
    address_line2: '',
    city: '',
    state: '',
    postal_code: '',
    country: 'US',
    is_default: true,
  }];
}

function normalizeMultiSizeValue(value) {
  if (Array.isArray(value)) {
    return value
      .map((entry) => (typeof entry === 'string' ? entry.trim() : ''))
      .filter(Boolean);
  }
  if (typeof value !== 'string') return [];
  return value
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function serializeMultiSizeValue(values) {
  const normalized = normalizeMultiSizeValue(values);
  if (normalized.length === 0) return null;
  return normalized.join(', ');
}

function SectionHeader({ title, subtitle, rightText, onRightPress }) {
  return (
    <View style={styles.sectionHeader}>
      <View style={{ flex: 1 }}>
        <Text style={styles.sectionEyebrow}>{subtitle}</Text>
        <Text style={styles.sectionTitle}>{title}</Text>
      </View>
      {rightText ? (
        <TouchableOpacity style={styles.headerAction} onPress={onRightPress}>
          <Text style={styles.headerActionText}>{rightText}</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

function AppTabButton({ tab, activeTab, onPress }) {
  const active = tab === activeTab;
  const label = TAB_LABELS[tab] || titleCase(tab);
  return (
    <TouchableOpacity style={[styles.tabButton, active && styles.tabButtonActive]} onPress={() => onPress(tab)}>
      <Text style={[styles.tabButtonText, active && styles.tabButtonTextActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

function ListingCard({
  item,
  apiBaseUrl,
  showMatches = false,
  onStartTrade = null,
  startTradeDisabled = false,
  onOpenDetails = null,
  onShareListing = null,
  onShareToInstagram = null,
  onShareToFacebook = null,
}) {
  const imageUrl = normalizeImageUrl(item?.image || item?.images?.[0], apiBaseUrl);
  const matchPreviewImages = showMatches ? getMatchPreviewImages(item, apiBaseUrl) : [];
  const hasMatches = Array.isArray(item?.matches) && item.matches.length > 0;
  return (
    <View style={styles.listingCard}>
      {imageUrl ? (
        <Image source={{ uri: imageUrl }} style={styles.listingImage} />
      ) : (
        <View style={[styles.listingImage, styles.listingImageFallback]}>
          <Text style={styles.emptyText}>No image</Text>
        </View>
      )}
      <View style={styles.listingBody}>
        <Text style={styles.listingEyebrow}>{titleCase(item?.category || 'listing')}</Text>
        <Text numberOfLines={2} style={styles.listingTitle}>{item?.title || 'Untitled listing'}</Text>
        <Text numberOfLines={2} style={styles.listingMeta}>
          {item?.brand || 'Unknown'} • {titleCase(item?.condition || 'unknown')}
        </Text>
        <View style={styles.valueChip}>
          <Text style={styles.valueChipText}>${Number(item?.estimated_value || 0).toFixed(0)}</Text>
        </View>
        {showMatches ? (
          <View style={styles.matchesRow}>
            <Text style={styles.matchesLabel}>Matches</Text>
            {matchPreviewImages.length > 0 ? (
              <View style={styles.matchThumbStrip}>
                {matchPreviewImages.map((src, idx) => (
                  <Image
                    key={`${item?.listing_id || item?.id || 'item'}-match-${idx}`}
                    source={{ uri: src }}
                    style={styles.matchThumb}
                  />
                ))}
              </View>
            ) : (
              <Text style={styles.matchThumbEmpty}>No matches</Text>
            )}
          </View>
        ) : null}
        {showMatches && hasMatches && onStartTrade ? (
          <TouchableOpacity
            style={[styles.primaryBtnCompact, startTradeDisabled && styles.primaryBtnDisabled]}
            onPress={() => onStartTrade(item)}
            disabled={startTradeDisabled}
          >
            <Text style={styles.primaryBtnText}>{startTradeDisabled ? 'Unavailable' : 'Start Trade'}</Text>
          </TouchableOpacity>
        ) : null}
        {onOpenDetails ? (
          <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => onOpenDetails(item)}>
            <Text style={styles.secondaryBtnText}>View Details</Text>
          </TouchableOpacity>
        ) : null}
        {onShareListing || onShareToInstagram || onShareToFacebook ? (
          <View style={styles.listingActionRow}>
            {onShareListing ? (
              <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => onShareListing(item)}>
                <Text style={styles.secondaryBtnText}>Share</Text>
              </TouchableOpacity>
            ) : null}
            {onShareToInstagram ? (
              <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => onShareToInstagram(item)}>
                <Text style={styles.secondaryBtnText}>Instagram</Text>
              </TouchableOpacity>
            ) : null}
            {onShareToFacebook ? (
              <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => onShareToFacebook(item)}>
                <Text style={styles.secondaryBtnText}>Facebook</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        ) : null}
      </View>
    </View>
  );
}

function OfferCard({ offer, apiBaseUrl }) {
  const targetListing = offer?.target_listing || null;
  const offeredListings = offerOfferedListings(offer);
  const targetHero = listingGallery(targetListing, apiBaseUrl)[0] || null;
  return (
    <View style={styles.offerCard}>
      <Text style={styles.offerTitle}>Offer #{String(offer?.offer_id || '').slice(0, 8)}</Text>
      <Text style={styles.offerMeta}>Status: {titleCase(offer?.status || 'pending')}</Text>
      <Text style={styles.offerMeta}>From: {offer?.from_subject || 'n/a'}</Text>
      <View style={styles.offerMediaRow}>
        <View style={styles.offerTargetPanel}>
          <Text style={styles.offerLaneLabel}>Target Listing</Text>
          {targetHero ? (
            <Image source={{ uri: targetHero }} style={styles.offerTargetImage} />
          ) : (
            <View style={[styles.offerTargetImage, styles.offerImageFallback]}>
              <Text style={styles.emptyText}>No image</Text>
            </View>
          )}
          <Text style={styles.offerItemTitle} numberOfLines={2}>{targetListing?.title || 'Target listing'}</Text>
          <Text style={styles.offerItemMeta} numberOfLines={1}>
            {targetListing?.brand || 'Unknown'} • {titleCase(targetListing?.condition || 'unknown')}
          </Text>
        </View>
        <View style={styles.offerOfferedPanel}>
          <Text style={styles.offerLaneLabel}>Offered Items</Text>
          <View style={styles.offerThumbGrid}>
            {offeredListings.length === 0 ? (
              <View style={styles.offerThumbEmpty}><Text style={styles.offerThumbEmptyText}>No items</Text></View>
            ) : (
              offeredListings.slice(0, 4).map((listing, idx) => {
                const thumb = listingGallery(listing, apiBaseUrl)[0] || null;
                return thumb ? (
                  <Image key={`${offer?.offer_id || 'offer'}-offered-${idx}`} source={{ uri: thumb }} style={styles.offerThumb} />
                ) : (
                  <View key={`${offer?.offer_id || 'offer'}-offered-empty-${idx}`} style={[styles.offerThumb, styles.offerImageFallback]}>
                    <Text style={styles.offerThumbEmptyText}>No image</Text>
                  </View>
                );
              })
            )}
          </View>
          {offeredListings.slice(0, 2).map((listing, idx) => (
            <Text key={`${offer?.offer_id || 'offer'}-offered-title-${idx}`} style={styles.offerItemMeta} numberOfLines={1}>
              {listing?.title || 'Offered listing'}
            </Text>
          ))}
        </View>
      </View>
    </View>
  );
}

function TopBrandHeader() {
  return (
    <View style={styles.brandWrap}>
      <View style={styles.brandStrip}>
        <Text style={styles.brandStripText}>INVITE ONLY COMMUNITY • CURATED MEMBERSHIP ACCESS</Text>
      </View>
      <View style={styles.brandMainRow}>
        <Text style={styles.brandWordmark}>JOUFT</Text>
        <Text style={styles.brandSubWordmark}>AI LUXURY EXCHANGE</Text>
      </View>
    </View>
  );
}

function MarketplaceMobileApp({ clerkEnabled = false, getBearerToken = null, clerkUserLabel = '', onSignOut = null }) {
  const [apiBaseUrl, setApiBaseUrl] = useState(API_DEFAULT);
  const [authMode, setAuthMode] = useState('api_key');
  const [apiKey, setApiKey] = useState('local-dev-key');
  const [bearerToken, setBearerToken] = useState('');

  const [activeTab, setActiveTab] = useState('marketplace');
  const [offerFilter, setOfferFilter] = useState('pending');

  const [marketplaceListings, setMarketplaceListings] = useState([]);
  const [marketplaceActorSubject, setMarketplaceActorSubject] = useState('');
  const [myListings, setMyListings] = useState([]);
  const [incomingOffers, setIncomingOffers] = useState([]);
  const [selectedOfferId, setSelectedOfferId] = useState(null);
  const [selectedListing, setSelectedListing] = useState(null);
  const [isListingDetailOpen, setIsListingDetailOpen] = useState(false);
  const [selectedListingSource, setSelectedListingSource] = useState(null);
  const [selectedListingIndex, setSelectedListingIndex] = useState(-1);
  const [tradeComposerTarget, setTradeComposerTarget] = useState(null);
  const [tradeOfferCandidates, setTradeOfferCandidates] = useState([]);
  const [tradeOfferListingIds, setTradeOfferListingIds] = useState([]);
  const [tradeOfferMessage, setTradeOfferMessage] = useState('');
  const [tradeOfferBusy, setTradeOfferBusy] = useState(false);
  const [tradeOfferError, setTradeOfferError] = useState('');
  const [shippingAddresses, setShippingAddresses] = useState([]);
  const [profileShippingAddresses, setProfileShippingAddresses] = useState([]);
  const [profileQuiz, setProfileQuiz] = useState(null);
  const [profileSaveBusy, setProfileSaveBusy] = useState(false);
  const [profileSaveMsg, setProfileSaveMsg] = useState('');
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const [paymentMsg, setPaymentMsg] = useState('');
  const [subscriptionPlan, setSubscriptionPlan] = useState('free');
  const [subscriptionCycle, setSubscriptionCycle] = useState('monthly');
  const [selectedAddressByOffer, setSelectedAddressByOffer] = useState({});
  const [shippingLabelsByOffer, setShippingLabelsByOffer] = useState({});
  const [pushEnabled, setPushEnabled] = useState(true);
  const [notificationPermission, setNotificationPermission] = useState('unknown');
  const [pushToken, setPushToken] = useState('');

  const [wizardStep, setWizardStep] = useState(1);
  const [images, setImages] = useState([]);
  const [category, setCategory] = useState('');
  const [itemTitle, setItemTitle] = useState('');
  const [itemDescription, setItemDescription] = useState('');
  const [userCondition, setUserCondition] = useState('');
  const [askingValue, setAskingValue] = useState('');
  const [tradeNotes, setTradeNotes] = useState('');
  const [analysisResult, setAnalysisResult] = useState(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const apiClient = useMemo(() => createMobileApiClient({ apiBaseUrl }), [apiBaseUrl]);
  const selectedOffer = useMemo(
    () => incomingOffers.find((offer) => offer?.offer_id === selectedOfferId) || null,
    [incomingOffers, selectedOfferId],
  );
  const initializedOfferStateRef = useRef(false);
  const offerStatusMapRef = useRef(new Map());
  const normalizedProfileGender = profileQuiz?.gender === 'male' || profileQuiz?.gender === 'female' || profileQuiz?.gender === 'other'
    ? profileQuiz.gender
    : '';
  const profileApparelSizeOptions = normalizedProfileGender === 'male' ? MALE_APPAREL_SIZE_OPTIONS : FEMALE_APPAREL_SIZE_OPTIONS;
  const profileShoeSizeOptions = normalizedProfileGender === 'male' ? MALE_SHOE_SIZE_OPTIONS : FEMALE_SHOE_SIZE_OPTIONS;
  const profileCategoryOptions = normalizedProfileGender === 'male'
    ? PROFILE_CATEGORY_OPTIONS.filter((item) => item !== 'Dresses')
    : PROFILE_CATEGORY_OPTIONS;

  function openListingDetails(listing, source) {
    if (!listing) return;
    const list = source === 'closet' ? myListings : marketplaceListings;
    const idx = list.findIndex((entry) => String(entry?.listing_id || '') === String(listing?.listing_id || ''));
    setIsListingDetailOpen(true);
    setSelectedListing(listing);
    setSelectedListingSource(source || 'marketplace');
    setSelectedListingIndex(idx);
  }

  function closeListingDetails() {
    setIsListingDetailOpen(false);
    setSelectedListing(null);
    setSelectedListingSource(null);
    setSelectedListingIndex(-1);
  }

  function flipMarketplaceListing(direction) {
    if (selectedListingSource !== 'marketplace') return;
    if (!Array.isArray(marketplaceListings) || marketplaceListings.length <= 1) return;
    const total = marketplaceListings.length;
    const current = selectedListingIndex >= 0 ? selectedListingIndex : 0;
    const next = (current + direction + total) % total;
    setSelectedListingIndex(next);
    setSelectedListing(marketplaceListings[next] || null);
  }

  function authReady() {
    if (clerkEnabled) return true;
    if (authMode === 'bearer') return Boolean(bearerToken.trim());
    return Boolean(apiKey.trim());
  }

  async function authContext() {
    if (clerkEnabled && typeof getBearerToken === 'function') {
      const token = await getBearerToken();
      if (token && String(token).trim()) return { bearerToken: String(token).trim() };
      return {};
    }
    if (authMode === 'bearer' && bearerToken.trim()) return { bearerToken: bearerToken.trim() };
    return { apiKey: apiKey.trim() };
  }

  async function loadMarketplace() {
    setLoading(true);
    setError('');
    try {
      const payload = await apiClient.listMarketplace(50, await authContext());
      setMarketplaceListings(Array.isArray(payload?.items) ? payload.items : []);
      setMarketplaceActorSubject(String(payload?.actor?.subject || ''));
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadCloset() {
    setLoading(true);
    setError('');
    try {
      const payload = await apiClient.listMyListings(100, await authContext());
      setMyListings(Array.isArray(payload?.items) ? payload.items : []);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadInbox(status = offerFilter) {
    setLoading(true);
    setError('');
    try {
      const payload = await apiClient.incomingOffers(status, 50, await authContext());
      setIncomingOffers(Array.isArray(payload?.items) ? payload.items : []);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadProfileAddresses() {
    try {
      const profile = await apiClient.fetchProfileQuiz(await authContext());
      setProfileQuiz(profile ? {
        ...profile,
        gender: profile?.gender || '',
        tops_size: normalizeMultiSizeValue(profile?.tops_size),
        dresses_size: normalizeMultiSizeValue(profile?.dresses_size),
        bottoms_size: normalizeMultiSizeValue(profile?.bottoms_size),
        shoes_size: normalizeMultiSizeValue(profile?.shoes_size),
        category_preferences: Array.isArray(profile?.category_preferences) ? profile.category_preferences : [],
      } : null);
      setSubscriptionPlan(String(profile?.subscription_plan || 'free'));
      setSubscriptionCycle(String(profile?.subscription_billing_cycle || 'monthly'));
      const normalized = normalizeShippingAddresses(profile?.shipping_addresses, profile);
      const editable = normalizeProfileShippingAddresses(profile?.shipping_addresses, profile);
      setShippingAddresses(normalized);
      setProfileShippingAddresses(editable);
      return normalized;
    } catch (e) {
      return [];
    }
  }

  async function loadPaymentMethods() {
    try {
      const payload = await apiClient.paymentMethods(await authContext());
      setPaymentMethods(Array.isArray(payload?.items) ? payload.items : []);
    } catch (e) {
      setPaymentMethods([]);
    }
  }

  async function loadShippingLabelsForOffer(offerId) {
    const payload = await apiClient.fetchShippingLabels(offerId, await authContext());
    const shipments = Array.isArray(payload?.shipments) ? payload.shipments : [];
    setShippingLabelsByOffer((prev) => ({ ...prev, [offerId]: shipments }));
    return shipments;
  }

  async function registerForPushNotifications() {
    if (!NotificationsModule) {
      setNotificationPermission('unavailable');
      return;
    }
    try {
      const current = await NotificationsModule.getPermissionsAsync();
      let finalStatus = current.status;
      if (finalStatus !== 'granted') {
        const requested = await NotificationsModule.requestPermissionsAsync();
        finalStatus = requested.status;
      }
      setNotificationPermission(finalStatus);
      if (finalStatus !== 'granted') return;
      if (!DeviceModule?.isDevice) return;
      const projectId = Constants.expoConfig?.extra?.eas?.projectId || Constants.easConfig?.projectId;
      const tokenResp = await NotificationsModule.getExpoPushTokenAsync(projectId ? { projectId } : undefined);
      setPushToken(String(tokenResp?.data || ''));
    } catch (e) {
      setNotificationPermission('denied');
    }
  }

  async function sendLocalNotification(title, body) {
    if (!NotificationsModule) return;
    try {
      await NotificationsModule.scheduleNotificationAsync({
        content: { title, body },
        trigger: null,
      });
    } catch (e) {
      // best effort only
    }
  }

  function addProfileShippingAddress() {
    setProfileSaveMsg('');
    setProfileShippingAddresses((prev) => ([
      ...prev,
      {
        id: makeId('ship'),
        label: `Address ${prev.length + 1}`,
        full_name: '',
        address_line1: '',
        address_line2: '',
        city: '',
        state: '',
        postal_code: '',
        country: 'US',
        is_default: prev.length === 0,
      },
    ]));
  }

  function updateProfileShippingAddress(addressId, field, value) {
    setProfileSaveMsg('');
    setProfileShippingAddresses((prev) => prev.map((entry) => (
      entry.id === addressId ? { ...entry, [field]: value } : entry
    )));
  }

  function removeProfileShippingAddress(addressId) {
    setProfileSaveMsg('');
    setProfileShippingAddresses((prev) => {
      const next = prev.filter((entry) => entry.id !== addressId);
      if (next.length === 0) return [];
      if (!next.some((entry) => entry.is_default)) next[0] = { ...next[0], is_default: true };
      return next;
    });
  }

  function setProfileShippingDefault(addressId) {
    setProfileSaveMsg('');
    setProfileShippingAddresses((prev) => prev.map((entry) => ({
      ...entry,
      is_default: entry.id === addressId,
    })));
  }

  function updateProfileStyleField(field, value) {
    setProfileSaveMsg('');
    setProfileQuiz((prev) => ({ ...(prev || {}), [field]: value }));
  }

  function toggleProfileStyleMulti(field, value) {
    setProfileSaveMsg('');
    setProfileQuiz((prev) => {
      const current = normalizeMultiSizeValue(prev?.[field]);
      const next = current.includes(value)
        ? current.filter((entry) => entry !== value)
        : [...current, value];
      return { ...(prev || {}), [field]: next };
    });
  }

  function toggleProfileCategory(value) {
    setProfileSaveMsg('');
    setProfileQuiz((prev) => {
      const current = Array.isArray(prev?.category_preferences) ? prev.category_preferences : [];
      const next = current.includes(value)
        ? current.filter((entry) => entry !== value)
        : [...current, value];
      return { ...(prev || {}), category_preferences: next };
    });
  }

  function buildProfileQuizPayload({ shippingAddressesOverride = null, subscriptionPlanOverride = null, subscriptionCycleOverride = null } = {}) {
    const workingAddresses = Array.isArray(shippingAddressesOverride) ? shippingAddressesOverride : profileShippingAddresses;
    const nextAddresses = workingAddresses
      .map((entry, idx) => ({
        id: entry.id || makeId('ship'),
        label: String(entry.label || '').trim() || `Address ${idx + 1}`,
        full_name: String(entry.full_name || '').trim(),
        address_line1: String(entry.address_line1 || '').trim(),
        address_line2: String(entry.address_line2 || '').trim(),
        city: String(entry.city || '').trim(),
        state: String(entry.state || '').trim(),
        postal_code: String(entry.postal_code || '').trim(),
        country: String(entry.country || 'US').trim() || 'US',
        is_default: Boolean(entry.is_default),
      }))
      .filter((entry) => entry.full_name && entry.address_line1 && entry.city && entry.state && entry.postal_code);
    const ensuredDefault = nextAddresses.map((entry, idx) => ({
      ...entry,
      is_default: nextAddresses.length > 0 ? (nextAddresses.some((x) => x.is_default) ? entry.is_default : idx === 0) : false,
    }));
    const primary = ensuredDefault[0] || {};
    return {
      gender: profileQuiz?.gender ? profileQuiz.gender : null,
      tops_size: serializeMultiSizeValue(profileQuiz?.tops_size),
      dresses_size: serializeMultiSizeValue(profileQuiz?.dresses_size),
      bottoms_size: serializeMultiSizeValue(profileQuiz?.bottoms_size),
      shoes_size: serializeMultiSizeValue(profileQuiz?.shoes_size),
      category_preferences: Array.isArray(profileQuiz?.category_preferences) ? profileQuiz.category_preferences : [],
      shipping_full_name: primary.full_name || null,
      shipping_address_line1: primary.address_line1 || null,
      shipping_address_line2: primary.address_line2 || null,
      shipping_city: primary.city || null,
      shipping_state: primary.state || null,
      shipping_postal_code: primary.postal_code || null,
      shipping_country: primary.country || null,
      shipping_addresses: ensuredDefault,
      subscription_plan: subscriptionPlanOverride ?? profileQuiz?.subscription_plan ?? subscriptionPlan ?? 'free',
      subscription_billing_cycle: subscriptionCycleOverride ?? profileQuiz?.subscription_billing_cycle ?? subscriptionCycle ?? 'monthly',
      subscription_status: profileQuiz?.subscription_status ?? null,
      subscription_renewal_date: profileQuiz?.subscription_renewal_date ?? null,
      payment_methods: Array.isArray(profileQuiz?.payment_methods) ? profileQuiz.payment_methods : [],
    };
  }

  async function saveProfileShippingAddresses() {
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    setProfileSaveBusy(true);
    setProfileSaveMsg('');
    setError('');
    try {
      const payload = buildProfileQuizPayload();
      const saved = await apiClient.saveProfileQuiz(payload, await authContext());
      setProfileQuiz(saved ? {
        ...saved,
        gender: saved?.gender || '',
        tops_size: normalizeMultiSizeValue(saved?.tops_size),
        dresses_size: normalizeMultiSizeValue(saved?.dresses_size),
        bottoms_size: normalizeMultiSizeValue(saved?.bottoms_size),
        shoes_size: normalizeMultiSizeValue(saved?.shoes_size),
        category_preferences: Array.isArray(saved?.category_preferences) ? saved.category_preferences : [],
      } : null);
      setSubscriptionPlan(String(saved?.subscription_plan || 'free'));
      setSubscriptionCycle(String(saved?.subscription_billing_cycle || 'monthly'));
      const normalized = normalizeShippingAddresses(saved?.shipping_addresses, saved);
      const editable = normalizeProfileShippingAddresses(saved?.shipping_addresses, saved);
      setShippingAddresses(normalized);
      setProfileShippingAddresses(editable);
      setProfileSaveMsg('Shipping addresses saved.');
    } catch (e) {
      setError(e.message || 'Failed to save shipping addresses.');
    } finally {
      setProfileSaveBusy(false);
    }
  }

  async function saveStylePreferences() {
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    setProfileSaveBusy(true);
    setProfileSaveMsg('');
    setError('');
    try {
      const payload = buildProfileQuizPayload({
        shippingAddressesOverride: shippingAddresses,
      });
      const saved = await apiClient.saveProfileQuiz(payload, await authContext());
      setProfileQuiz(saved ? {
        ...saved,
        gender: saved?.gender || '',
        tops_size: normalizeMultiSizeValue(saved?.tops_size),
        dresses_size: normalizeMultiSizeValue(saved?.dresses_size),
        bottoms_size: normalizeMultiSizeValue(saved?.bottoms_size),
        shoes_size: normalizeMultiSizeValue(saved?.shoes_size),
        category_preferences: Array.isArray(saved?.category_preferences) ? saved.category_preferences : [],
      } : null);
      setProfileSaveMsg('Style preferences saved.');
    } catch (e) {
      setError(e.message || 'Failed to save style preferences.');
    } finally {
      setProfileSaveBusy(false);
    }
  }

  async function saveSubscriptionSettings(plan, cycle) {
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    setProfileSaveBusy(true);
    setProfileSaveMsg('');
    setError('');
    try {
      const payload = buildProfileQuizPayload({
        subscriptionPlanOverride: plan,
        subscriptionCycleOverride: cycle,
      });
      const saved = await apiClient.saveProfileQuiz(payload, await authContext());
      setProfileQuiz(saved ? {
        ...saved,
        gender: saved?.gender || '',
        tops_size: normalizeMultiSizeValue(saved?.tops_size),
        dresses_size: normalizeMultiSizeValue(saved?.dresses_size),
        bottoms_size: normalizeMultiSizeValue(saved?.bottoms_size),
        shoes_size: normalizeMultiSizeValue(saved?.shoes_size),
        category_preferences: Array.isArray(saved?.category_preferences) ? saved.category_preferences : [],
      } : null);
      setSubscriptionPlan(String(saved?.subscription_plan || plan || 'free'));
      setSubscriptionCycle(String(saved?.subscription_billing_cycle || cycle || 'monthly'));
      setProfileSaveMsg('Subscription preferences saved.');
    } catch (e) {
      setError(e.message || 'Failed to save subscription preferences.');
    } finally {
      setProfileSaveBusy(false);
    }
  }

  async function handleAddPaymentMethod() {
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    setPaymentBusy(true);
    setPaymentMsg('');
    setError('');
    try {
      const session = await apiClient.createSetupCheckoutSession(
        {
          success_url: 'https://jouft.com/account/payment-success',
          cancel_url: 'https://jouft.com/account/payment-cancel',
        },
        await authContext(),
      );
      if (session?.status === 'disabled') {
        setPaymentMsg(session?.message || 'Stripe is not configured on server.');
      } else if (session?.checkout_url) {
        await Linking.openURL(session.checkout_url);
        setPaymentMsg('Complete setup in Stripe, then tap Sync from Stripe.');
      } else {
        setPaymentMsg('Unable to open Stripe setup right now.');
      }
    } catch (e) {
      setError(e.message || 'Failed to start payment method setup.');
    } finally {
      setPaymentBusy(false);
    }
  }

  async function handleSyncPaymentMethods() {
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    setPaymentBusy(true);
    setPaymentMsg('');
    setError('');
    try {
      const payload = await apiClient.syncStripePaymentMethods(await authContext());
      setPaymentMethods(Array.isArray(payload?.items) ? payload.items : []);
      setPaymentMsg('Payment methods synced from Stripe.');
    } catch (e) {
      setError(e.message || 'Failed to sync payment methods.');
    } finally {
      setPaymentBusy(false);
    }
  }

  async function handleRemovePaymentMethod(paymentMethodId) {
    if (!paymentMethodId) return;
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    setPaymentBusy(true);
    setPaymentMsg('');
    setError('');
    try {
      await apiClient.deletePaymentMethod(paymentMethodId, await authContext());
      await loadPaymentMethods();
      setPaymentMsg('Payment method removed.');
    } catch (e) {
      setError(e.message || 'Failed to remove payment method.');
    } finally {
      setPaymentBusy(false);
    }
  }

  async function handleSetDefaultPaymentMethod(paymentMethodId) {
    if (!paymentMethodId) return;
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    setPaymentBusy(true);
    setPaymentMsg('');
    setError('');
    try {
      await apiClient.setDefaultPaymentMethod(paymentMethodId, await authContext());
      await loadPaymentMethods();
      setPaymentMsg('Default payment method updated.');
    } catch (e) {
      setError(e.message || 'Failed to set default payment method.');
    } finally {
      setPaymentBusy(false);
    }
  }

  async function openTradeComposer(targetListing) {
    if (!targetListing?.listing_id) return;
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    setLoading(true);
    setError('');
    setTradeOfferError('');
    setTradeComposerTarget(targetListing);
    setTradeOfferCandidates([]);
    setTradeOfferListingIds([]);
    setTradeOfferMessage('');
    try {
      const payload = await apiClient.listOfferCandidates(targetListing.listing_id, 100, await authContext());
      const candidates = Array.isArray(payload?.items) ? payload.items : [];
      setTradeOfferCandidates(candidates);
      setTradeOfferListingIds(candidates[0]?.listing_id ? [candidates[0].listing_id] : []);
    } catch (e) {
      setTradeOfferError(e.message || 'Unable to load eligible listings.');
    } finally {
      setLoading(false);
    }
  }

  function closeTradeComposer() {
    setTradeComposerTarget(null);
    setTradeOfferCandidates([]);
    setTradeOfferListingIds([]);
    setTradeOfferMessage('');
    setTradeOfferError('');
  }

  function toggleTradeListing(listingId) {
    if (!listingId) return;
    setTradeOfferListingIds((prev) => (
      prev.includes(listingId)
        ? prev.filter((id) => id !== listingId)
        : [...prev, listingId]
    ));
  }

  async function submitTradeOffer() {
    if (!tradeComposerTarget?.listing_id) return;
    if (!tradeOfferListingIds.length) {
      setTradeOfferError('Select at least one listing to offer.');
      return;
    }
    setTradeOfferBusy(true);
    setTradeOfferError('');
    try {
      await apiClient.createOffer(
        {
          target_listing_id: tradeComposerTarget.listing_id,
          offered_listing_ids: tradeOfferListingIds,
          message: tradeOfferMessage.trim(),
        },
        await authContext(),
      );
      closeTradeComposer();
      setNotice('Trade offer sent.');
      setActiveTab('inbox');
      await loadInbox('pending');
    } catch (e) {
      setTradeOfferError(e.message || 'Failed to send trade offer.');
    } finally {
      setTradeOfferBusy(false);
    }
  }

  async function respondToOffer(offerId, status) {
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    setLoading(true);
    setError('');
    try {
      let receiveAddress = null;
      if (status === 'accepted') {
        const currentAddresses = shippingAddresses.length > 0 ? shippingAddresses : await loadProfileAddresses();
        if (currentAddresses.length === 0) {
          throw new Error('Add a shipping address in Profile before accepting trade.');
        }
        const selectedId = selectedAddressByOffer[offerId] || currentAddresses[0]?.id;
        const selected = currentAddresses.find((entry) => entry.id === selectedId) || currentAddresses[0];
        if (!selected) throw new Error('Select receive address before accepting trade.');
        receiveAddress = {
          label: selected.label || null,
          full_name: selected.full_name || null,
          address_line1: selected.address_line1 || null,
          address_line2: selected.address_line2 || null,
          city: selected.city || null,
          state: selected.state || null,
          postal_code: selected.postal_code || null,
          country: selected.country || null,
          is_default: false,
        };
      }

      const updated = await apiClient.actionOffer(offerId, status, receiveAddress, await authContext());
      setIncomingOffers((prev) => prev.map((offer) => (offer.offer_id === offerId ? { ...offer, ...updated } : offer)));
      if (String(updated?.status || '').toLowerCase() === 'accepted') {
        await loadShippingLabelsForOffer(offerId);
        setNotice('Trade accepted. Shipping labels are available below when ready.');
      } else if (status === 'accepted') {
        setNotice('Offer accepted. Waiting for finalization.');
      } else {
        setNotice('Offer updated.');
      }
      await loadInbox(offerFilter);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function openShippingLabel(shipment) {
    try {
      const payload = await apiClient.fetchShippingLabelDocument(shipment?.shipment_id, await authContext());
      const labelUrl = String(payload?.label_url || shipment?.label_url || '').trim();
      if (!labelUrl) {
        Alert.alert('Label unavailable', 'Carrier label URL is not available yet. Please try refresh labels.');
        return;
      }
      const canOpen = await Linking.canOpenURL(labelUrl);
      if (!canOpen) throw new Error('Cannot open label URL on this device.');
      await Linking.openURL(labelUrl);
    } catch (e) {
      setError(e.message || 'Unable to open shipping label.');
    }
  }

  async function shareListing(item) {
    try {
      const { imageUrl, title, caption } = buildSharePayload(item);
      const payload = imageUrl
        ? { message: `${caption}\n${imageUrl}`, url: imageUrl, title: title || 'Jouft Listing' }
        : { message: caption, title: title || 'Jouft Listing' };
      await Share.share(payload);
    } catch (e) {
      setError(e.message || 'Unable to open share sheet.');
    }
  }

  function buildSharePayload(item) {
    const gallery = listingGallery(item, apiBaseUrl);
    const imageUrl = gallery[0] || '';
    const title = String(item?.title || 'Luxury listing').trim();
    const brand = String(item?.brand || 'Jouft').trim();
    const value = Number(item?.estimated_value || 0);
    const description = listingDescription(item);
    const caption = [
      `${title}`,
      `${brand}${Number.isFinite(value) && value > 0 ? ` • ${money(value)}` : ''}`,
      description || 'Shared from Jouft.',
    ]
      .filter(Boolean)
      .join('\n');
    return { imageUrl, title, caption };
  }

  async function shareListingInstagram(item) {
    try {
      const { imageUrl, title, caption } = buildSharePayload(item);
      const instagramUrl = 'instagram://app';
      const canOpenInstagram = await Linking.canOpenURL(instagramUrl);
      if (canOpenInstagram) {
        await Share.share(
          imageUrl ? { message: `${caption}\n${imageUrl}`, url: imageUrl, title } : { message: caption, title },
          { dialogTitle: 'Share to Instagram' },
        );
        return;
      }
      Alert.alert('Instagram unavailable', 'Instagram app is not installed. Using standard share instead.');
      await Share.share(
        imageUrl ? { message: `${caption}\n${imageUrl}`, url: imageUrl, title } : { message: caption, title },
      );
    } catch (e) {
      setError(e.message || 'Unable to share to Instagram.');
    }
  }

  async function shareListingFacebook(item) {
    try {
      const { imageUrl, caption } = buildSharePayload(item);
      if (imageUrl) {
        const sharerUrl = `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(imageUrl)}&quote=${encodeURIComponent(caption)}`;
        const canOpenSharer = await Linking.canOpenURL(sharerUrl);
        if (canOpenSharer) {
          await Linking.openURL(sharerUrl);
          return;
        }
      }
      await Share.share({ message: imageUrl ? `${caption}\n${imageUrl}` : caption }, { dialogTitle: 'Share to Facebook' });
    } catch (e) {
      setError(e.message || 'Unable to share to Facebook.');
    }
  }

  async function refreshActiveTab() {
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    if (activeTab === 'marketplace') return loadMarketplace();
    if (activeTab === 'closet') return loadCloset();
    if (activeTab === 'inbox') return loadInbox();
  }

  useEffect(() => {
    if (!authReady()) return;
    if (activeTab === 'marketplace' && marketplaceListings.length === 0) {
      loadMarketplace();
      return;
    }
    if (activeTab === 'closet' && myListings.length === 0) {
      loadCloset();
      return;
    }
    if (activeTab === 'inbox' && incomingOffers.length === 0) {
      loadInbox(offerFilter);
    }
  }, [activeTab]);

  useEffect(() => {
    if (!authReady() || !pushEnabled) return;
    registerForPushNotifications().catch(() => {});
  }, [clerkEnabled, authMode, bearerToken, apiKey, pushEnabled]);

  useEffect(() => {
    if (!authReady()) return;
    if (activeTab !== 'inbox' && activeTab !== 'profile') return;
    loadProfileAddresses();
    if (activeTab === 'profile') loadPaymentMethods();
  }, [activeTab]);

  useEffect(() => {
    if (!authReady()) return;
    if (activeTab !== 'inbox') return;
    const acceptedOffers = incomingOffers.filter((offer) => String(offer?.status || '').toLowerCase() === 'accepted');
    acceptedOffers.forEach((offer) => {
      if (!shippingLabelsByOffer[offer.offer_id]) {
        loadShippingLabelsForOffer(offer.offer_id).catch(() => {});
      }
    });
  }, [activeTab, incomingOffers, shippingLabelsByOffer]);

  useEffect(() => {
    if (!isListingDetailOpen) return;
    if (!selectedListing) return;
    if (selectedListingSource !== 'marketplace') return;
    if (!Array.isArray(marketplaceListings) || marketplaceListings.length === 0) return;
    if (selectedListingIndex >= 0 && selectedListingIndex < marketplaceListings.length) {
      setSelectedListing(marketplaceListings[selectedListingIndex]);
      return;
    }
    const idx = marketplaceListings.findIndex((entry) => String(entry?.listing_id || '') === String(selectedListing?.listing_id || ''));
    if (idx >= 0) {
      setSelectedListingIndex(idx);
      setSelectedListing(marketplaceListings[idx]);
    }
  }, [isListingDetailOpen, marketplaceListings, selectedListing, selectedListingIndex, selectedListingSource]);

  useEffect(() => {
    if (!authReady() || !pushEnabled || notificationPermission !== 'granted') return;
    let cancelled = false;
    let timer = null;
    async function pollOffersAndNotify() {
      try {
        const payload = await apiClient.incomingOffers('all', 50, await authContext());
        if (cancelled) return;
        const offers = Array.isArray(payload?.items) ? payload.items : [];
        const nextMap = new Map();
        offers.forEach((offer) => {
          const offerId = String(offer?.offer_id || '');
          if (!offerId) return;
          nextMap.set(offerId, String(offer?.status || 'pending').toLowerCase());
        });
        if (!initializedOfferStateRef.current) {
          offerStatusMapRef.current = nextMap;
          initializedOfferStateRef.current = true;
          return;
        }
        const prevMap = offerStatusMapRef.current;
        for (const [offerId, status] of nextMap.entries()) {
          const prev = prevMap.get(offerId);
          if (!prev) {
            const incoming = offers.find((entry) => String(entry?.offer_id || '') === offerId);
            const title = incoming?.target_listing?.title || incoming?.target_listing_id || 'your listing';
            sendLocalNotification('New Trade Offer', `You received a new offer for ${title}.`);
          } else if (prev !== 'accepted' && status === 'accepted') {
            const incoming = offers.find((entry) => String(entry?.offer_id || '') === offerId);
            const title = incoming?.target_listing?.title || incoming?.target_listing_id || 'your listing';
            sendLocalNotification('Trade Accepted', `A trade was accepted for ${title}.`);
          }
        }
        offerStatusMapRef.current = nextMap;
      } catch (e) {
        // silent polling failure
      }
    }
    pollOffersAndNotify();
    timer = setInterval(pollOffersAndNotify, OFFER_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [apiClient, pushEnabled, notificationPermission, clerkEnabled, authMode, bearerToken, apiKey]);

  async function pickImages() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      setError('Photo permission is required.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsMultipleSelection: true,
      quality: 0.9,
      selectionLimit: 4,
    });
    if (!result.canceled) {
      setImages(result.assets.slice(0, 4));
      setError('');
    }
  }

  async function nextStep() {
    const canNext = wizardStep === 1 ? images.length >= 1 && images.length <= 4 : wizardStep === 2 ? Boolean(userCondition) : true;
    if (!canNext) {
      setError(wizardStep === 1 ? 'Upload 1 to 4 images before continuing.' : 'Condition is required.');
      return;
    }
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }

    if (wizardStep === 1 || wizardStep === 2) {
      setLoading(true);
      setError('');
      try {
        const payload = await apiClient.analyzeItem(
          {
            images,
            category,
            userCondition: wizardStep === 1 ? '' : userCondition,
            itemDescription: itemDescription.trim(),
            debug: true,
          },
          await authContext(),
        );
        setAnalysisResult(payload);
        if (!category && payload?.category) setCategory(payload.category);
        const gptTitle = payload?.item_profile?.model_identification?.name?.trim?.() || '';
        const suggestedDesc = buildSuggestedDescriptionFromProfile(payload?.item_profile);
        if (!itemTitle.trim() && gptTitle) setItemTitle(gptTitle);
        if (!itemDescription.trim() && suggestedDesc) setItemDescription(suggestedDesc);
        if (wizardStep === 2 && payload?.valuation?.estimated_value != null) {
          setAskingValue(String(Math.round(payload.valuation.estimated_value)));
        }
        setWizardStep((s) => Math.min(3, s + 1));
      } catch (e) {
        setError(e.message || String(e));
      } finally {
        setLoading(false);
      }
      return;
    }
    setWizardStep((s) => Math.min(3, s + 1));
  }

  function prevStep() {
    setError('');
    setWizardStep((s) => Math.max(1, s - 1));
  }

  async function publishListing() {
    if (!analysisResult) {
      setNotice('Run analysis through Step 2 first.');
      return;
    }
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }

    setLoading(true);
    setError('');
    setNotice('');
    try {
      const payload = {
        title: itemTitle.trim() || itemDescription.trim() || `${analysisResult.brand?.name || 'Item'} ${analysisResult.category || ''}`.trim(),
        mode: 'sell_trade',
        category: analysisResult.category,
        brand: analysisResult.brand?.name || 'unknown',
        condition: userCondition || analysisResult.condition?.grade || 'Good',
        estimated_value: Number(askingValue || analysisResult.valuation?.estimated_value || 0),
        city: 'Your area',
        image: images[0]?.uri || null,
        wants: tradeNotes.trim() || 'Open to similar-value offers',
        tags: [userCondition || analysisResult.condition?.grade || 'Good', analysisResult.brand?.name || 'unknown'],
        source_item_id: analysisResult.item_id,
        analysis: analysisResult,
      };

      const created = await apiClient.createListing(payload, await authContext());
      setNotice(`Listing published (${created.listing_id.slice(0, 8)}...)`);
      await loadCloset();
      setActiveTab('closet');
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.root}>
      <StatusBar style="dark" />
      <ScrollView style={styles.mainScroll} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <TopBrandHeader />

        {!!error && <Text style={styles.error}>{error}</Text>}
        {!!notice && <Text style={styles.notice}>{notice}</Text>}
        {loading && <ActivityIndicator style={{ marginTop: 8 }} color={theme.brand} />}

        {activeTab === 'marketplace' && (
          <View style={styles.section}>
            <SectionHeader title="Marketplace" subtitle="CURATED MATCHES" rightText="Refresh" onRightPress={refreshActiveTab} />
            {marketplaceListings.length === 0 ? (
              <Text style={styles.emptyText}>No listings loaded yet.</Text>
            ) : (
              marketplaceListings.map((item) => {
                const ownerSubject = String(item?.owner_subject || '');
                const canStartTrade = !ownerSubject || !marketplaceActorSubject || ownerSubject !== marketplaceActorSubject;
                return (
                  <ListingCard
                    key={item.listing_id}
                    item={item}
                    apiBaseUrl={apiBaseUrl}
                    showMatches
                    onStartTrade={openTradeComposer}
                    startTradeDisabled={!canStartTrade}
                    onOpenDetails={(listing) => openListingDetails(listing, 'marketplace')}
                  />
                );
              })
            )}
          </View>
        )}

        {activeTab === 'closet' && (
          <View style={styles.section}>
            <SectionHeader title="My Closet" subtitle="YOUR LISTINGS" rightText="Refresh" onRightPress={refreshActiveTab} />
            {myListings.length === 0 ? (
              <Text style={styles.emptyText}>No closet listings yet.</Text>
            ) : (
              myListings.map((item) => (
                <ListingCard
                  key={item.listing_id}
                  item={item}
                  apiBaseUrl={apiBaseUrl}
                  onOpenDetails={(listing) => openListingDetails(listing, 'closet')}
                  onShareListing={shareListing}
                  onShareToInstagram={shareListingInstagram}
                  onShareToFacebook={shareListingFacebook}
                />
              ))
            )}
          </View>
        )}

        {activeTab === 'create' && (
          <View style={styles.section}>
            <SectionHeader title="Create Listing" subtitle="ANALYZE • LIST • MATCH" />
            <View style={styles.stepRow}>
              {[1, 2, 3].map((step) => (
                <View key={step} style={[styles.stepPill, wizardStep === step && styles.stepPillActive]}>
                  <Text style={[styles.stepPillText, wizardStep === step && styles.stepPillTextActive]}>{step}</Text>
                </View>
              ))}
            </View>

            {wizardStep === 1 && (
              <>
                <TouchableOpacity style={styles.primaryBtn} onPress={pickImages}><Text style={styles.primaryBtnText}>Choose Photos (1-4)</Text></TouchableOpacity>
                <Text style={styles.helperText}>Selected: {images.length}</Text>
              </>
            )}

            {wizardStep === 2 && (
              <>
                <Text style={styles.label}>Category</Text>
                <TextInput value={category} onChangeText={setCategory} style={styles.input} placeholder="clothes / shoes / handbag" />
                <Text style={styles.label}>Title</Text>
                <TextInput value={itemTitle} onChangeText={setItemTitle} style={[styles.input, styles.multiInput]} multiline />
                <Text style={styles.label}>Description</Text>
                <TextInput value={itemDescription} onChangeText={setItemDescription} style={[styles.input, styles.multiInput]} multiline />
                <Text style={styles.label}>Condition</Text>
                <TextInput value={userCondition} onChangeText={setUserCondition} style={styles.input} placeholder="New / LikeNew / Good / Fair / Poor" />
              </>
            )}

            {wizardStep === 3 && (
              <>
                <Text style={styles.label}>Target asking value (USD)</Text>
                <TextInput value={askingValue} onChangeText={setAskingValue} style={styles.input} keyboardType="numeric" />
                <Text style={styles.label}>Trade notes</Text>
                <TextInput value={tradeNotes} onChangeText={setTradeNotes} style={styles.input} />
              </>
            )}

            <View style={styles.actionRow}>
              {wizardStep > 1 && (
                <TouchableOpacity style={styles.secondaryBtn} onPress={prevStep}>
                  <Text style={styles.secondaryBtnText}>Back</Text>
                </TouchableOpacity>
              )}
              {wizardStep < 3 && (
                <TouchableOpacity style={styles.primaryBtn} onPress={nextStep}>
                  <Text style={styles.primaryBtnText}>Next</Text>
                </TouchableOpacity>
              )}
              {wizardStep === 3 && (
                <TouchableOpacity style={styles.primaryBtn} onPress={publishListing}>
                  <Text style={styles.primaryBtnText}>Publish</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        )}

        {activeTab === 'inbox' && (
          <View style={styles.section}>
            <SectionHeader title="Trade Inbox" subtitle="OFFERS" rightText="Refresh" onRightPress={refreshActiveTab} />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
              {OFFER_FILTERS.map((filter) => {
                const active = filter === offerFilter;
                return (
                  <TouchableOpacity
                    key={filter}
                    style={[styles.filterButton, active && styles.filterButtonActive]}
                    onPress={async () => {
                      setOfferFilter(filter);
                      await loadInbox(filter);
                    }}
                  >
                    <Text style={[styles.filterButtonText, active && styles.filterButtonTextActive]}>{titleCase(filter)}</Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
            {incomingOffers.length === 0 ? (
              <Text style={styles.emptyText}>No offers available.</Text>
            ) : (
              incomingOffers.map((offer) => {
                const offerId = offer.offer_id;
                const isPending = String(offer?.status || '').toLowerCase() === 'pending';
                const isAccepted = String(offer?.status || '').toLowerCase() === 'accepted';
                const selectedAddressId = selectedAddressByOffer[offerId] || shippingAddresses[0]?.id || '';
                const labels = Array.isArray(shippingLabelsByOffer[offerId]) ? shippingLabelsByOffer[offerId] : [];
                return (
                  <View key={offerId} style={styles.offerCardWrap}>
                    <OfferCard offer={offer} apiBaseUrl={apiBaseUrl} />
                    <View style={styles.offerDetailCtaRow}>
                      <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => setSelectedOfferId(offerId)}>
                        <Text style={styles.secondaryBtnText}>View Offer Details</Text>
                      </TouchableOpacity>
                    </View>
                    {isPending ? (
                      <View style={styles.offerActions}>
                        <Text style={styles.label}>Receive address</Text>
                        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.addressRow}>
                          {shippingAddresses.length === 0 ? (
                            <Text style={styles.helperText}>No saved addresses. Add one in Profile.</Text>
                          ) : (
                            shippingAddresses.map((address) => {
                              const active = address.id === selectedAddressId;
                              return (
                                <TouchableOpacity
                                  key={`${offerId}-${address.id}`}
                                  style={[styles.addressChip, active && styles.addressChipActive]}
                                  onPress={() => setSelectedAddressByOffer((prev) => ({ ...prev, [offerId]: address.id }))}
                                >
                                  <Text style={[styles.addressChipText, active && styles.addressChipTextActive]}>
                                    {(address.label || 'Address').toUpperCase()}
                                  </Text>
                                  <Text style={[styles.addressChipSubText, active && styles.addressChipSubTextActive]}>
                                    {address.city}, {address.state}
                                  </Text>
                                </TouchableOpacity>
                              );
                            })
                          )}
                        </ScrollView>
                        <View style={styles.actionRow}>
                          <TouchableOpacity style={styles.primaryBtn} onPress={() => respondToOffer(offerId, 'accepted')}>
                            <Text style={styles.primaryBtnText}>Accept Trade</Text>
                          </TouchableOpacity>
                          <TouchableOpacity style={styles.secondaryBtn} onPress={() => respondToOffer(offerId, 'declined')}>
                            <Text style={styles.secondaryBtnText}>Decline</Text>
                          </TouchableOpacity>
                        </View>
                      </View>
                    ) : null}
                    {isAccepted ? (
                      <View style={styles.labelBlock}>
                        <View style={styles.labelBlockHeader}>
                          <Text style={styles.label}>Shipping labels</Text>
                          <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => loadShippingLabelsForOffer(offerId)}>
                            <Text style={styles.secondaryBtnText}>Refresh Labels</Text>
                          </TouchableOpacity>
                        </View>
                        {labels.length === 0 ? (
                          <Text style={styles.helperText}>No labels yet. Tap Refresh Labels.</Text>
                        ) : (
                          labels.map((shipment) => (
                            <View key={shipment.shipment_id} style={styles.shipmentCard}>
                              <Text style={styles.shipmentTitle}>{shipment.carrier} • {shipment.service_level}</Text>
                              <Text style={styles.shipmentMeta}>Tracking: {shipment.tracking_number || 'pending'}</Text>
                              <Text style={styles.shipmentMeta}>From: {shipment.from_city || ''} {shipment.from_state || ''}</Text>
                              <Text style={styles.shipmentMeta}>To: {shipment.to_city || ''} {shipment.to_state || ''}</Text>
                              <TouchableOpacity style={styles.primaryBtnCompact} onPress={() => openShippingLabel(shipment)}>
                                <Text style={styles.primaryBtnText}>Download Label</Text>
                              </TouchableOpacity>
                            </View>
                          ))
                        )}
                      </View>
                    ) : null}
                  </View>
                );
              })
            )}
          </View>
        )}

        {activeTab === 'profile' && (
          <View style={styles.section}>
            <SectionHeader title="Profile" subtitle="SETTINGS" />
            <Text style={styles.label}>API Base URL</Text>
            <TextInput value={apiBaseUrl} onChangeText={setApiBaseUrl} style={styles.input} autoCapitalize="none" />

            {clerkEnabled ? (
              <>
                <Text style={styles.label}>Signed In As</Text>
                <Text style={styles.helperText}>{clerkUserLabel || 'Authenticated user'}</Text>
                {onSignOut ? (
                  <TouchableOpacity style={styles.secondaryBtn} onPress={onSignOut}>
                    <Text style={styles.secondaryBtnText}>Sign Out</Text>
                  </TouchableOpacity>
                ) : null}
              </>
            ) : (
              <>
                <View style={styles.modeRow}>
                  <TouchableOpacity style={[styles.modeBtn, authMode === 'api_key' && styles.modeBtnActive]} onPress={() => setAuthMode('api_key')}>
                    <Text style={[styles.modeBtnText, authMode === 'api_key' && styles.modeBtnTextActive]}>API Key</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.modeBtn, authMode === 'bearer' && styles.modeBtnActive]} onPress={() => setAuthMode('bearer')}>
                    <Text style={[styles.modeBtnText, authMode === 'bearer' && styles.modeBtnTextActive]}>Bearer</Text>
                  </TouchableOpacity>
                </View>

                {authMode === 'api_key' ? (
                  <>
                    <Text style={styles.label}>API Key</Text>
                    <TextInput value={apiKey} onChangeText={setApiKey} style={styles.input} autoCapitalize="none" />
                  </>
                ) : (
                  <>
                    <Text style={styles.label}>Clerk Bearer Token</Text>
                    <TextInput
                      value={bearerToken}
                      onChangeText={setBearerToken}
                      style={[styles.input, styles.multiInput]}
                      multiline
                      autoCapitalize="none"
                      placeholder="Paste a valid Clerk JWT"
                    />
                  </>
                )}
              </>
            )}

            <View style={styles.profileDivider} />
            <Text style={styles.label}>Notifications</Text>
            <View style={styles.modeRow}>
              <TouchableOpacity
                style={[styles.modeBtn, pushEnabled && styles.modeBtnActive]}
                onPress={() => setPushEnabled(true)}
              >
                <Text style={[styles.modeBtnText, pushEnabled && styles.modeBtnTextActive]}>Enabled</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modeBtn, !pushEnabled && styles.modeBtnActive]}
                onPress={() => setPushEnabled(false)}
              >
                <Text style={[styles.modeBtnText, !pushEnabled && styles.modeBtnTextActive]}>Disabled</Text>
              </TouchableOpacity>
            </View>
            <Text style={styles.helperText}>
              Permission: {titleCase(notificationPermission)}{pushToken ? ' • Push token ready' : ''}
            </Text>
            <TouchableOpacity
              style={styles.secondaryBtn}
              onPress={() => sendLocalNotification('Jouft Notifications', 'Push alerts are active on this device.')}
            >
              <Text style={styles.secondaryBtnText}>Test Notification</Text>
            </TouchableOpacity>
            <View style={styles.profileDivider} />
            <Text style={styles.label}>Style Preferences</Text>
            <Text style={styles.label}>Gender</Text>
            <View style={styles.modeRow}>
              {[
                { key: 'female', label: 'Female' },
                { key: 'male', label: 'Male' },
                { key: 'other', label: 'Other' },
              ].map((option) => (
                <TouchableOpacity
                  key={option.key}
                  style={[styles.modeBtn, normalizedProfileGender === option.key && styles.modeBtnActive]}
                  onPress={() => {
                    const nextGender = option.key;
                    updateProfileStyleField('gender', nextGender);
                    if (nextGender === 'male') {
                      updateProfileStyleField('dresses_size', []);
                      updateProfileStyleField(
                        'category_preferences',
                        (Array.isArray(profileQuiz?.category_preferences) ? profileQuiz.category_preferences : []).filter((entry) => entry !== 'Dresses'),
                      );
                    }
                  }}
                >
                  <Text style={[styles.modeBtnText, normalizedProfileGender === option.key && styles.modeBtnTextActive]}>{option.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.label}>Tops Size</Text>
            <View style={styles.tagChipRow}>
              {profileApparelSizeOptions.map((size) => {
                const selected = normalizeMultiSizeValue(profileQuiz?.tops_size).includes(size);
                return (
                  <TouchableOpacity
                    key={`tops-${size}`}
                    style={[styles.tagChip, selected && styles.tagChipActive]}
                    onPress={() => toggleProfileStyleMulti('tops_size', size)}
                  >
                    <Text style={[styles.tagChipText, selected && styles.tagChipTextActive]}>{size}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {normalizedProfileGender !== 'male' ? (
              <>
                <Text style={styles.label}>Dresses Size</Text>
                <View style={styles.tagChipRow}>
                  {profileApparelSizeOptions.map((size) => {
                    const selected = normalizeMultiSizeValue(profileQuiz?.dresses_size).includes(size);
                    return (
                      <TouchableOpacity
                        key={`dresses-${size}`}
                        style={[styles.tagChip, selected && styles.tagChipActive]}
                        onPress={() => toggleProfileStyleMulti('dresses_size', size)}
                      >
                        <Text style={[styles.tagChipText, selected && styles.tagChipTextActive]}>{size}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </>
            ) : null}

            <Text style={styles.label}>Bottoms Size</Text>
            <View style={styles.tagChipRow}>
              {profileApparelSizeOptions.map((size) => {
                const selected = normalizeMultiSizeValue(profileQuiz?.bottoms_size).includes(size);
                return (
                  <TouchableOpacity
                    key={`bottoms-${size}`}
                    style={[styles.tagChip, selected && styles.tagChipActive]}
                    onPress={() => toggleProfileStyleMulti('bottoms_size', size)}
                  >
                    <Text style={[styles.tagChipText, selected && styles.tagChipTextActive]}>{size}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            <Text style={styles.label}>Shoes Size</Text>
            <View style={styles.tagChipRow}>
              {profileShoeSizeOptions.map((size) => {
                const selected = normalizeMultiSizeValue(profileQuiz?.shoes_size).includes(size);
                return (
                  <TouchableOpacity
                    key={`shoes-${size}`}
                    style={[styles.tagChip, selected && styles.tagChipActive]}
                    onPress={() => toggleProfileStyleMulti('shoes_size', size)}
                  >
                    <Text style={[styles.tagChipText, selected && styles.tagChipTextActive]}>{size}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            <Text style={styles.label}>Category Preferences</Text>
            <View style={styles.tagChipRow}>
              {profileCategoryOptions.map((categoryOption) => {
                const selected = Array.isArray(profileQuiz?.category_preferences) && profileQuiz.category_preferences.includes(categoryOption);
                return (
                  <TouchableOpacity
                    key={`cat-${categoryOption}`}
                    style={[styles.tagChip, selected && styles.tagChipActive]}
                    onPress={() => toggleProfileCategory(categoryOption)}
                  >
                    <Text style={[styles.tagChipText, selected && styles.tagChipTextActive]}>{categoryOption}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <TouchableOpacity
              style={[styles.primaryBtn, profileSaveBusy && styles.primaryBtnDisabled]}
              onPress={saveStylePreferences}
              disabled={profileSaveBusy}
            >
              <Text style={styles.primaryBtnText}>{profileSaveBusy ? 'Saving...' : 'Save Style Preferences'}</Text>
            </TouchableOpacity>

            <View style={styles.profileDivider} />
            <View style={styles.labelBlockHeader}>
              <Text style={styles.label}>Shipping Addresses</Text>
              <TouchableOpacity style={styles.secondaryBtnCompact} onPress={addProfileShippingAddress}>
                <Text style={styles.secondaryBtnText}>Add Address</Text>
              </TouchableOpacity>
            </View>
            {profileShippingAddresses.length === 0 ? (
              <Text style={styles.helperText}>No shipping addresses yet. Add one.</Text>
            ) : (
              profileShippingAddresses.map((entry) => (
                <View key={entry.id} style={styles.profileAddressCard}>
                  <View style={styles.labelBlockHeader}>
                    <Text style={styles.offerLaneLabel}>{entry.label || 'Address'}</Text>
                    <View style={styles.addressActionRow}>
                      <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => setProfileShippingDefault(entry.id)}>
                        <Text style={styles.secondaryBtnText}>{entry.is_default ? 'Default' : 'Set Default'}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => removeProfileShippingAddress(entry.id)}>
                        <Text style={styles.secondaryBtnText}>Remove</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                  <Text style={styles.label}>Label</Text>
                  <TextInput value={entry.label} onChangeText={(value) => updateProfileShippingAddress(entry.id, 'label', value)} style={styles.input} />
                  <Text style={styles.label}>Full Name</Text>
                  <TextInput value={entry.full_name} onChangeText={(value) => updateProfileShippingAddress(entry.id, 'full_name', value)} style={styles.input} />
                  <Text style={styles.label}>Address Line 1</Text>
                  <TextInput value={entry.address_line1} onChangeText={(value) => updateProfileShippingAddress(entry.id, 'address_line1', value)} style={styles.input} />
                  <Text style={styles.label}>Address Line 2</Text>
                  <TextInput value={entry.address_line2} onChangeText={(value) => updateProfileShippingAddress(entry.id, 'address_line2', value)} style={styles.input} />
                  <View style={styles.profileAddressRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.label}>City</Text>
                      <TextInput value={entry.city} onChangeText={(value) => updateProfileShippingAddress(entry.id, 'city', value)} style={styles.input} />
                    </View>
                    <View style={{ width: 96 }}>
                      <Text style={styles.label}>State</Text>
                      <TextInput value={entry.state} onChangeText={(value) => updateProfileShippingAddress(entry.id, 'state', value)} style={styles.input} autoCapitalize="characters" />
                    </View>
                  </View>
                  <View style={styles.profileAddressRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.label}>Postal Code</Text>
                      <TextInput value={entry.postal_code} onChangeText={(value) => updateProfileShippingAddress(entry.id, 'postal_code', value)} style={styles.input} />
                    </View>
                    <View style={{ width: 120 }}>
                      <Text style={styles.label}>Country</Text>
                      <TextInput value={entry.country} onChangeText={(value) => updateProfileShippingAddress(entry.id, 'country', value)} style={styles.input} autoCapitalize="characters" />
                    </View>
                  </View>
                </View>
              ))
            )}
            {!!profileSaveMsg && <Text style={styles.notice}>{profileSaveMsg}</Text>}
            <TouchableOpacity
              style={[styles.primaryBtn, profileSaveBusy && styles.primaryBtnDisabled]}
              onPress={saveProfileShippingAddresses}
              disabled={profileSaveBusy}
            >
              <Text style={styles.primaryBtnText}>{profileSaveBusy ? 'Saving...' : 'Save Shipping Addresses'}</Text>
            </TouchableOpacity>

            <View style={styles.profileDivider} />
            <Text style={styles.label}>Subscription</Text>
            <View style={styles.profilePlanList}>
              {SUBSCRIPTION_PLANS.map((plan) => {
                const selected = subscriptionPlan === plan.key;
                const amount = subscriptionCycle === 'annual' ? plan.annual : plan.monthly;
                return (
                  <TouchableOpacity
                    key={plan.key}
                    style={[styles.profilePlanCard, selected && styles.profilePlanCardActive]}
                    onPress={() => setSubscriptionPlan(plan.key)}
                  >
                    <Text style={styles.profilePlanTitle}>{plan.label}</Text>
                    <Text style={styles.profilePlanPrice}>
                      {amount === 0 ? 'Free' : `$${amount}`} {subscriptionCycle === 'annual' ? '/ year' : '/ month'}
                    </Text>
                    <Text style={styles.profilePlanLimit}>{plan.limit}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <View style={styles.modeRow}>
              <TouchableOpacity
                style={[styles.modeBtn, subscriptionCycle === 'monthly' && styles.modeBtnActive]}
                onPress={() => setSubscriptionCycle('monthly')}
              >
                <Text style={[styles.modeBtnText, subscriptionCycle === 'monthly' && styles.modeBtnTextActive]}>Monthly</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modeBtn, subscriptionCycle === 'annual' && styles.modeBtnActive]}
                onPress={() => setSubscriptionCycle('annual')}
              >
                <Text style={[styles.modeBtnText, subscriptionCycle === 'annual' && styles.modeBtnTextActive]}>Annual (10% Off)</Text>
              </TouchableOpacity>
            </View>
            <TouchableOpacity
              style={[styles.primaryBtn, profileSaveBusy && styles.primaryBtnDisabled]}
              onPress={() => saveSubscriptionSettings(subscriptionPlan, subscriptionCycle)}
              disabled={profileSaveBusy}
            >
              <Text style={styles.primaryBtnText}>{profileSaveBusy ? 'Saving...' : 'Save Subscription'}</Text>
            </TouchableOpacity>

            <View style={styles.profileDivider} />
            <View style={styles.labelBlockHeader}>
              <Text style={styles.label}>Payment Methods</Text>
              <View style={styles.addressActionRow}>
                <TouchableOpacity style={styles.secondaryBtnCompact} onPress={handleAddPaymentMethod} disabled={paymentBusy}>
                  <Text style={styles.secondaryBtnText}>Add</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.secondaryBtnCompact} onPress={handleSyncPaymentMethods} disabled={paymentBusy}>
                  <Text style={styles.secondaryBtnText}>Sync from Stripe</Text>
                </TouchableOpacity>
              </View>
            </View>
            {!!paymentMsg && <Text style={styles.helperText}>{paymentMsg}</Text>}
            {paymentMethods.length === 0 ? (
              <Text style={styles.helperText}>No payment methods added yet.</Text>
            ) : (
              paymentMethods.map((method) => (
                <View key={method.payment_method_id} style={styles.profilePaymentCard}>
                  <Text style={styles.offerItemTitle}>
                    {method.label || method.brand || method.method_type || 'Payment Method'}
                    {method.is_default ? ' • Default' : ''}
                  </Text>
                  <Text style={styles.offerItemMeta}>
                    {String(method.provider || 'stripe').toUpperCase()} • {String(method.method_type || 'card').toUpperCase()}
                  </Text>
                  <View style={styles.addressActionRow}>
                    {!method.is_default ? (
                      <TouchableOpacity
                        style={styles.secondaryBtnCompact}
                        onPress={() => handleSetDefaultPaymentMethod(method.payment_method_id)}
                        disabled={paymentBusy}
                      >
                        <Text style={styles.secondaryBtnText}>Set Default</Text>
                      </TouchableOpacity>
                    ) : null}
                    <TouchableOpacity
                      style={styles.secondaryBtnCompact}
                      onPress={() => handleRemovePaymentMethod(method.payment_method_id)}
                      disabled={paymentBusy}
                    >
                      <Text style={styles.secondaryBtnText}>Remove</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))
            )}
          </View>
        )}

        {selectedOffer ? (() => {
          const offerId = selectedOffer.offer_id;
          const targetListing = selectedOffer?.target_listing || null;
          const offeredListings = offerOfferedListings(selectedOffer);
          const targetGallery = listingGallery(targetListing, apiBaseUrl);
          const selectedAddressId = selectedAddressByOffer[offerId] || shippingAddresses[0]?.id || '';
          const labels = Array.isArray(shippingLabelsByOffer[offerId]) ? shippingLabelsByOffer[offerId] : [];
          const isPending = String(selectedOffer?.status || '').toLowerCase() === 'pending';
          const isAccepted = String(selectedOffer?.status || '').toLowerCase() === 'accepted';
          return (
            <SafeAreaView style={styles.offerDetailOverlay}>
              <View style={styles.offerDetailShell}>
                <View style={styles.offerDetailHead}>
                  <View>
                    <Text style={styles.sectionEyebrow}>Offer Details</Text>
                    <Text style={styles.offerDetailTitle}>#{String(offerId || '').slice(0, 8)}</Text>
                  </View>
                  <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => setSelectedOfferId(null)}>
                    <Text style={styles.secondaryBtnText}>Close</Text>
                  </TouchableOpacity>
                </View>
                <ScrollView contentContainerStyle={styles.offerDetailBody} keyboardShouldPersistTaps="handled">
                  <View style={styles.offerDetailPanel}>
                    <Text style={styles.offerLaneLabel}>Target Listing</Text>
                    {targetGallery.length > 0 ? (
                      <Image source={{ uri: targetGallery[0] }} style={styles.offerDetailHero} />
                    ) : (
                      <View style={[styles.offerDetailHero, styles.offerImageFallback]}>
                        <Text style={styles.emptyText}>No image</Text>
                      </View>
                    )}
                    {targetGallery.length > 1 ? (
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.offerDetailThumbRow}>
                        {targetGallery.slice(1).map((src, idx) => (
                          <Image key={`${offerId}-target-extra-${idx}`} source={{ uri: src }} style={styles.offerDetailThumb} />
                        ))}
                      </ScrollView>
                    ) : null}
                    <Text style={styles.offerDetailItemTitle}>{targetListing?.title || 'Target listing'}</Text>
                    <Text style={styles.offerDetailItemMeta}>
                      {targetListing?.brand || 'Unknown'} • {titleCase(targetListing?.condition || 'unknown')} • {titleCase(targetListing?.category || 'listing')}
                    </Text>
                  </View>

                  <View style={styles.offerDetailPanel}>
                    <Text style={styles.offerLaneLabel}>Offered Items</Text>
                    {offeredListings.length === 0 ? (
                      <Text style={styles.emptyText}>No offered listings found.</Text>
                    ) : (
                      offeredListings.map((listing, idx) => {
                        const gallery = listingGallery(listing, apiBaseUrl);
                        return (
                          <View key={`${offerId}-offered-${idx}`} style={styles.offerDetailListingCard}>
                            {gallery[0] ? (
                              <Image source={{ uri: gallery[0] }} style={styles.offerDetailListingImage} />
                            ) : (
                              <View style={[styles.offerDetailListingImage, styles.offerImageFallback]}>
                                <Text style={styles.emptyText}>No image</Text>
                              </View>
                            )}
                            <Text style={styles.offerDetailItemTitle}>{listing?.title || 'Offered listing'}</Text>
                            <Text style={styles.offerDetailItemMeta}>
                              {listing?.brand || 'Unknown'} • {titleCase(listing?.condition || 'unknown')} • ${Number(listing?.estimated_value || 0).toFixed(0)}
                            </Text>
                          </View>
                        );
                      })
                    )}
                  </View>

                  {selectedOffer?.message ? (
                    <View style={styles.offerDetailPanel}>
                      <Text style={styles.offerLaneLabel}>Message</Text>
                      <Text style={styles.offerDetailMessage}>{selectedOffer.message}</Text>
                    </View>
                  ) : null}

                  {isPending ? (
                    <View style={styles.offerDetailPanel}>
                      <Text style={styles.offerLaneLabel}>Actions</Text>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.addressRow}>
                        {shippingAddresses.length === 0 ? (
                          <Text style={styles.helperText}>No saved addresses. Add one in Profile.</Text>
                        ) : (
                          shippingAddresses.map((address) => {
                            const active = address.id === selectedAddressId;
                            return (
                              <TouchableOpacity
                                key={`${offerId}-detail-${address.id}`}
                                style={[styles.addressChip, active && styles.addressChipActive]}
                                onPress={() => setSelectedAddressByOffer((prev) => ({ ...prev, [offerId]: address.id }))}
                              >
                                <Text style={[styles.addressChipText, active && styles.addressChipTextActive]}>
                                  {(address.label || 'Address').toUpperCase()}
                                </Text>
                                <Text style={[styles.addressChipSubText, active && styles.addressChipSubTextActive]}>
                                  {address.city}, {address.state}
                                </Text>
                              </TouchableOpacity>
                            );
                          })
                        )}
                      </ScrollView>
                      <View style={styles.actionRow}>
                        <TouchableOpacity style={styles.primaryBtn} onPress={() => respondToOffer(offerId, 'accepted')}>
                          <Text style={styles.primaryBtnText}>Accept Trade</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.secondaryBtn} onPress={() => respondToOffer(offerId, 'declined')}>
                          <Text style={styles.secondaryBtnText}>Decline</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  ) : null}

                  {isAccepted ? (
                    <View style={styles.offerDetailPanel}>
                      <View style={styles.labelBlockHeader}>
                        <Text style={styles.offerLaneLabel}>Shipping Labels</Text>
                        <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => loadShippingLabelsForOffer(offerId)}>
                          <Text style={styles.secondaryBtnText}>Refresh</Text>
                        </TouchableOpacity>
                      </View>
                      {labels.length === 0 ? (
                        <Text style={styles.helperText}>No labels yet. Tap Refresh.</Text>
                      ) : (
                        labels.map((shipment) => (
                          <View key={`${offerId}-${shipment.shipment_id}`} style={styles.shipmentCard}>
                            <Text style={styles.shipmentTitle}>{shipment.carrier} • {shipment.service_level}</Text>
                            <Text style={styles.shipmentMeta}>Tracking: {shipment.tracking_number || 'pending'}</Text>
                            <TouchableOpacity style={styles.primaryBtnCompact} onPress={() => openShippingLabel(shipment)}>
                              <Text style={styles.primaryBtnText}>Download Label</Text>
                            </TouchableOpacity>
                          </View>
                        ))
                      )}
                    </View>
                  ) : null}
                </ScrollView>
              </View>
            </SafeAreaView>
          );
        })() : null}

        {isListingDetailOpen && selectedListing ? (() => {
          const gallery = listingGallery(selectedListing, apiBaseUrl);
          const hasMatches = Array.isArray(selectedListing?.matches) && selectedListing.matches.length > 0;
          const ownerSubject = String(selectedListing?.owner_subject || '');
          const canStartTrade = !ownerSubject || !marketplaceActorSubject || ownerSubject !== marketplaceActorSubject;
          const description = listingDescription(selectedListing);
          return (
            <SafeAreaView style={styles.offerDetailOverlay}>
              <View style={styles.offerDetailShell}>
                <View style={styles.offerDetailHead}>
                  <View>
                    <Text style={styles.sectionEyebrow}>Listing Details</Text>
                    <Text style={styles.offerDetailTitle}>{selectedListing?.title || 'Listing'}</Text>
                  </View>
                  <TouchableOpacity style={styles.secondaryBtnCompact} onPress={closeListingDetails} hitSlop={{ top: 10, right: 10, bottom: 10, left: 10 }}>
                    <Text style={styles.secondaryBtnText}>Close</Text>
                  </TouchableOpacity>
                </View>
                {selectedListingSource === 'marketplace' && marketplaceListings.length > 1 ? (
                  <View style={styles.marketFlipRow}>
                    <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => flipMarketplaceListing(-1)}>
                      <Text style={styles.secondaryBtnText}>Prev</Text>
                    </TouchableOpacity>
                    <Text style={styles.marketFlipText}>
                      Page {Math.max(1, selectedListingIndex + 1)} / {marketplaceListings.length}
                    </Text>
                    <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => flipMarketplaceListing(1)}>
                      <Text style={styles.secondaryBtnText}>Next</Text>
                    </TouchableOpacity>
                  </View>
                ) : null}
                <ScrollView contentContainerStyle={styles.offerDetailBody} keyboardShouldPersistTaps="handled">
                  <View style={styles.offerDetailPanel}>
                    <Text style={styles.offerLaneLabel}>Gallery</Text>
                    {gallery.length > 0 ? (
                      <>
                        <Image source={{ uri: gallery[0] }} style={styles.offerDetailHero} />
                        {gallery.length > 1 ? (
                          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.offerDetailThumbRow}>
                            {gallery.slice(1).map((src, idx) => (
                              <Image key={`${selectedListing?.listing_id || 'listing'}-extra-${idx}`} source={{ uri: src }} style={styles.offerDetailThumb} />
                            ))}
                          </ScrollView>
                        ) : null}
                      </>
                    ) : (
                      <View style={[styles.offerDetailHero, styles.offerImageFallback]}>
                        <Text style={styles.emptyText}>No image</Text>
                      </View>
                    )}
                    <Text style={styles.offerDetailItemMeta}>
                      {selectedListing?.brand || 'Unknown'} • {titleCase(selectedListing?.condition || 'unknown')} • {titleCase(selectedListing?.category || 'listing')}
                    </Text>
                    <Text style={styles.offerDetailItemMeta}>
                      {money(selectedListing?.estimated_value)}
                    </Text>
                  </View>

                  <View style={styles.offerDetailPanel}>
                    <Text style={styles.offerLaneLabel}>Description</Text>
                    <Text style={styles.offerDetailMessage}>{description || 'No description provided.'}</Text>
                  </View>

                  {hasMatches ? (
                    <View style={styles.offerDetailPanel}>
                      <Text style={styles.offerLaneLabel}>Matched Items</Text>
                      <View style={styles.matchThumbStrip}>
                        {getMatchPreviewImages(selectedListing, apiBaseUrl).map((src, idx) => (
                          <Image
                            key={`${selectedListing?.listing_id || 'listing'}-matched-${idx}`}
                            source={{ uri: src }}
                            style={styles.matchThumb}
                          />
                        ))}
                      </View>
                    </View>
                  ) : null}

                  {canStartTrade && hasMatches ? (
                    <View style={styles.offerDetailPanel}>
                      <TouchableOpacity
                        style={styles.primaryBtn}
                        onPress={() => {
                          closeListingDetails();
                          openTradeComposer(selectedListing);
                        }}
                      >
                        <Text style={styles.primaryBtnText}>Start Trade</Text>
                      </TouchableOpacity>
                    </View>
                  ) : null}
                </ScrollView>
              </View>
            </SafeAreaView>
          );
        })() : null}

        {tradeComposerTarget ? (() => {
          const targetGallery = listingGallery(tradeComposerTarget, apiBaseUrl);
          return (
            <SafeAreaView style={styles.offerDetailOverlay}>
              <View style={styles.offerDetailShell}>
                <View style={styles.offerDetailHead}>
                  <View>
                    <Text style={styles.sectionEyebrow}>Trade Composer</Text>
                    <Text style={styles.offerDetailTitle}>Build Offer</Text>
                  </View>
                  <TouchableOpacity style={styles.secondaryBtnCompact} onPress={closeTradeComposer} hitSlop={{ top: 10, right: 10, bottom: 10, left: 10 }}>
                    <Text style={styles.secondaryBtnText}>Close</Text>
                  </TouchableOpacity>
                </View>
                <ScrollView contentContainerStyle={styles.offerDetailBody} keyboardShouldPersistTaps="handled">
                  <View style={styles.offerDetailPanel}>
                    <Text style={styles.offerLaneLabel}>Target Listing</Text>
                    {targetGallery[0] ? (
                      <Image source={{ uri: targetGallery[0] }} style={styles.offerDetailHero} />
                    ) : (
                      <View style={[styles.offerDetailHero, styles.offerImageFallback]}>
                        <Text style={styles.emptyText}>No image</Text>
                      </View>
                    )}
                    <Text style={styles.offerDetailItemTitle}>{tradeComposerTarget?.title || 'Target listing'}</Text>
                    <Text style={styles.offerDetailItemMeta}>
                      {tradeComposerTarget?.brand || 'Unknown'} • {titleCase(tradeComposerTarget?.condition || 'unknown')} • {money(tradeComposerTarget?.estimated_value)}
                    </Text>
                  </View>

                  <View style={styles.offerDetailPanel}>
                    <Text style={styles.offerLaneLabel}>Your Listings to Offer</Text>
                    {tradeOfferCandidates.length === 0 ? (
                      <Text style={styles.helperText}>No eligible listings found. Offer candidates must match brand and be within price band.</Text>
                    ) : (
                      tradeOfferCandidates.map((listing) => {
                        const checked = tradeOfferListingIds.includes(listing?.listing_id);
                        const gallery = listingGallery(listing, apiBaseUrl);
                        return (
                          <TouchableOpacity
                            key={listing?.listing_id}
                            style={[styles.tradeCandidateRow, checked && styles.tradeCandidateRowActive]}
                            onPress={() => toggleTradeListing(listing?.listing_id)}
                          >
                            {gallery[0] ? (
                              <Image source={{ uri: gallery[0] }} style={styles.tradeCandidateThumb} />
                            ) : (
                              <View style={[styles.tradeCandidateThumb, styles.offerImageFallback]}>
                                <Text style={styles.offerThumbEmptyText}>No image</Text>
                              </View>
                            )}
                            <View style={{ flex: 1 }}>
                              <Text style={styles.offerItemTitle} numberOfLines={1}>{listing?.title || 'Listing'}</Text>
                              <Text style={styles.offerItemMeta} numberOfLines={1}>
                                {listing?.brand || 'Unknown'} • {money(listing?.estimated_value)}
                              </Text>
                            </View>
                            <View style={[styles.tradeCheck, checked && styles.tradeCheckActive]}>
                              <Text style={[styles.tradeCheckText, checked && styles.tradeCheckTextActive]}>{checked ? '✓' : ''}</Text>
                            </View>
                          </TouchableOpacity>
                        );
                      })
                    )}
                  </View>

                  <View style={styles.offerDetailPanel}>
                    <Text style={styles.label}>Message (optional)</Text>
                    <TextInput
                      value={tradeOfferMessage}
                      onChangeText={setTradeOfferMessage}
                      style={[styles.input, styles.multiInput]}
                      placeholder="I’d like to trade with this item. Let me know what you think."
                      multiline
                    />
                    {tradeOfferError ? <Text style={styles.error}>{tradeOfferError}</Text> : null}
                    <View style={styles.actionRow}>
                      <TouchableOpacity style={styles.secondaryBtn} onPress={closeTradeComposer}>
                        <Text style={styles.secondaryBtnText}>Cancel</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={[styles.primaryBtn, tradeOfferBusy && styles.primaryBtnDisabled]}
                        onPress={submitTradeOffer}
                        disabled={tradeOfferBusy}
                      >
                        <Text style={styles.primaryBtnText}>{tradeOfferBusy ? 'Sending...' : 'Send Trade Offer'}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                </ScrollView>
              </View>
            </SafeAreaView>
          );
        })() : null}
      </ScrollView>
      <View style={styles.tabContainer}>
        {TABS.map((tab) => (
          <AppTabButton key={tab} tab={tab} activeTab={activeTab} onPress={setActiveTab} />
        ))}
      </View>
    </View>
  );
}

function ClerkAuthScreen() {
  const [mode, setMode] = useState('sign_in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const { isLoaded: signInLoaded, signIn, setActive: setSignInActive } = useSignIn();
  const { isLoaded: signUpLoaded, signUp, setActive: setSignUpActive } = useSignUp();

  async function submitSignIn() {
    if (!signInLoaded) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await signIn.create({
        identifier: email.trim(),
        password,
      });
      if (result?.status === 'complete' && result?.createdSessionId) {
        await setSignInActive({ session: result.createdSessionId });
        return;
      }
      setError('Additional sign-in steps are required for this account.');
    } catch (e) {
      setError(e?.errors?.[0]?.longMessage || e?.errors?.[0]?.message || e.message || 'Sign in failed.');
    } finally {
      setBusy(false);
    }
  }

  async function submitSignUp() {
    if (!signUpLoaded) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await signUp.create({
        emailAddress: email.trim(),
        password,
      });
      if (result?.status === 'complete' && result?.createdSessionId) {
        await setSignUpActive({ session: result.createdSessionId });
        return;
      }
      setNotice('Sign-up started. Complete any required verification to finish.');
    } catch (e) {
      setError(e?.errors?.[0]?.longMessage || e?.errors?.[0]?.message || e.message || 'Sign up failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.authRoot}>
      <StatusBar style="dark" />
      <View style={styles.authCard}>
        <Text style={styles.sectionEyebrow}>Jouft Access</Text>
        <Text style={styles.authTitle}>{mode === 'sign_in' ? 'Sign In' : 'Create Account'}</Text>
        <Text style={styles.helperText}>Use your Clerk account to access marketplace, closet, and trade inbox.</Text>

        <View style={styles.modeRow}>
          <TouchableOpacity style={[styles.modeBtn, mode === 'sign_in' && styles.modeBtnActive]} onPress={() => setMode('sign_in')}>
            <Text style={[styles.modeBtnText, mode === 'sign_in' && styles.modeBtnTextActive]}>Sign In</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.modeBtn, mode === 'sign_up' && styles.modeBtnActive]} onPress={() => setMode('sign_up')}>
            <Text style={[styles.modeBtnText, mode === 'sign_up' && styles.modeBtnTextActive]}>Create Account</Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.label}>Email</Text>
        <TextInput value={email} onChangeText={setEmail} style={styles.input} autoCapitalize="none" keyboardType="email-address" />
        <Text style={styles.label}>Password</Text>
        <TextInput value={password} onChangeText={setPassword} style={styles.input} secureTextEntry autoCapitalize="none" />

        {!!error && <Text style={styles.error}>{error}</Text>}
        {!!notice && <Text style={styles.notice}>{notice}</Text>}

        <TouchableOpacity
          style={[styles.primaryBtn, busy && styles.primaryBtnDisabled]}
          onPress={mode === 'sign_in' ? submitSignIn : submitSignUp}
          disabled={busy}
        >
          <Text style={styles.primaryBtnText}>{busy ? 'Please wait...' : (mode === 'sign_in' ? 'Sign In' : 'Create Account')}</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

function ClerkMobileApp() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const { signOut } = useClerk();

  if (!isLoaded) {
    return (
      <SafeAreaView style={styles.authRoot}>
        <ActivityIndicator color={theme.brand} />
      </SafeAreaView>
    );
  }

  if (!isSignedIn) return <ClerkAuthScreen />;

  const label = user?.primaryEmailAddress?.emailAddress || user?.username || user?.id || 'Authenticated user';

  return (
    <MarketplaceMobileApp
      clerkEnabled
      getBearerToken={getToken}
      clerkUserLabel={label}
      onSignOut={() => signOut()}
    />
  );
}

export default function App() {
  if (!CLERK_PUBLISHABLE_KEY) {
    return <MarketplaceMobileApp />;
  }
  return (
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY} tokenCache={tokenCache}>
      <ClerkMobileApp />
    </ClerkProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.bg },
  mainScroll: { flex: 1 },
  content: { paddingBottom: 18 },
  authRoot: {
    flex: 1,
    backgroundColor: theme.bg,
    paddingHorizontal: 16,
    justifyContent: 'center',
  },
  authCard: {
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: theme.surface,
    padding: 14,
    gap: 8,
    borderRadius: 12,
  },
  authTitle: {
    color: theme.text,
    fontSize: 30,
    lineHeight: 34,
    fontFamily: 'Didot',
  },

  brandWrap: {
    backgroundColor: theme.surface,
    borderBottomWidth: 1,
    borderColor: theme.line,
    marginBottom: 10,
  },
  brandStrip: {
    backgroundColor: theme.brand,
    paddingVertical: 8,
    paddingHorizontal: 14,
  },
  brandStripText: {
    color: '#f9f4ef',
    textAlign: 'center',
    fontSize: 10,
    letterSpacing: 1.4,
    fontWeight: '500',
  },
  brandMainRow: {
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 10,
  },
  brandWordmark: {
    color: theme.brand,
    fontSize: 40,
    letterSpacing: 2.4,
    fontFamily: 'Didot',
  },
  brandSubWordmark: {
    color: theme.muted,
    marginTop: -2,
    letterSpacing: 2,
    fontSize: 11,
    textTransform: 'uppercase',
    fontWeight: '500',
  },
  tabContainer: {
    flexDirection: 'row',
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: theme.line,
    backgroundColor: theme.surface,
    paddingHorizontal: 10,
    paddingTop: 10,
    paddingBottom: 12,
  },
  tabButton: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#d4c8b6',
    borderRadius: 12,
    paddingHorizontal: 6,
    paddingVertical: 9,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabButtonActive: { backgroundColor: theme.brand, borderColor: theme.brand },
  tabButtonText: { color: '#4a4139', fontSize: 10, letterSpacing: 0.8, fontWeight: '700', textTransform: 'uppercase' },
  tabButtonTextActive: { color: '#fff' },

  section: {
    marginHorizontal: 16,
    marginBottom: 12,
    backgroundColor: theme.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: theme.line,
    padding: 12,
    gap: 10,
  },
  profileDivider: {
    borderTopWidth: 1,
    borderTopColor: theme.line,
    marginTop: 6,
    paddingTop: 8,
  },
  profilePlanList: {
    gap: 8,
  },
  profilePlanCard: {
    borderWidth: 1,
    borderColor: theme.line,
    borderRadius: 10,
    padding: 10,
    backgroundColor: '#fff',
    gap: 3,
  },
  profilePlanCardActive: {
    borderColor: theme.brand,
    backgroundColor: theme.brandSoft,
  },
  profilePlanTitle: {
    color: '#231c16',
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: 0.4,
  },
  profilePlanPrice: {
    color: theme.brand,
    fontSize: 13,
    fontWeight: '700',
  },
  profilePlanLimit: {
    color: '#645b51',
    fontSize: 11,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: theme.line,
  },
  sectionEyebrow: {
    color: '#7f7468',
    fontSize: 10,
    letterSpacing: 1.6,
    fontWeight: '600',
    textTransform: 'uppercase',
  },
  sectionTitle: {
    color: theme.text,
    fontSize: 31,
    lineHeight: 35,
    fontFamily: 'Didot',
  },
  headerAction: {
    borderWidth: 1,
    borderColor: '#d8c8b8',
    borderRadius: 8,
    backgroundColor: '#fff',
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  headerActionText: { color: theme.brand, fontSize: 11, fontWeight: '700', letterSpacing: 1.1, textTransform: 'uppercase' },

  listingCard: {
    borderWidth: 1,
    borderColor: theme.line,
    borderRadius: 0,
    overflow: 'hidden',
    backgroundColor: '#fff',
  },
  listingImage: { width: '100%', height: 220, backgroundColor: '#ddd4ca' },
  listingImageFallback: { alignItems: 'center', justifyContent: 'center' },
  listingBody: { padding: 12, gap: 6 },
  listingEyebrow: { color: '#766d64', fontSize: 11, fontWeight: '600', letterSpacing: 1.3, textTransform: 'uppercase' },
  listingTitle: {
    color: '#171511',
    fontSize: 16,
    lineHeight: 17.3,
    minHeight: 34.6,
    fontWeight: '500',
    letterSpacing: -0.1,
  },
  listingMeta: {
    color: '#55606f',
    fontSize: 11,
    lineHeight: 16,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    minHeight: 32,
  },
  valueChip: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: theme.line,
    borderRadius: 0,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#fff',
  },
  valueChipText: {
    color: '#1f2937',
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  matchesRow: {
    marginTop: 4,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  matchesLabel: {
    fontSize: 11,
    color: '#111',
    fontWeight: '600',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  matchThumbStrip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  matchThumb: {
    width: 72,
    height: 72,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: 'rgba(18,26,36,0.18)',
    backgroundColor: '#efe8df',
  },
  matchThumbEmpty: {
    color: '#7a7167',
    fontSize: 11,
  },

  offerCard: {
    backgroundColor: '#fff',
    padding: 12,
    gap: 8,
  },
  offerTitle: { color: '#171511', fontSize: 23, lineHeight: 27, fontFamily: 'Didot' },
  offerMeta: { color: '#574f46', fontSize: 12 },
  offerMediaRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 2,
  },
  offerTargetPanel: {
    flex: 1,
    borderWidth: 1,
    borderColor: theme.line,
    padding: 6,
    gap: 5,
    backgroundColor: '#fff',
  },
  offerOfferedPanel: {
    width: 136,
    borderWidth: 1,
    borderColor: theme.line,
    padding: 6,
    gap: 5,
    backgroundColor: '#fff',
  },
  offerLaneLabel: {
    color: '#6c6359',
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  offerTargetImage: {
    width: '100%',
    height: 136,
    backgroundColor: '#ece7df',
  },
  offerImageFallback: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  offerThumbGrid: {
    display: 'flex',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  offerThumb: {
    width: 56,
    height: 56,
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: '#ece7df',
  },
  offerThumbEmpty: {
    width: '100%',
    height: 56,
    borderWidth: 1,
    borderColor: theme.line,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f5f1ea',
  },
  offerThumbEmptyText: {
    color: '#7f7468',
    fontSize: 10,
  },
  offerItemTitle: {
    color: '#201c17',
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 15,
  },
  offerItemMeta: {
    color: '#6f665d',
    fontSize: 10,
    lineHeight: 13,
  },
  offerCardWrap: {
    borderWidth: 1,
    borderColor: theme.line,
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: '#fff',
  },
  offerDetailCtaRow: {
    borderTopWidth: 1,
    borderTopColor: theme.line,
    paddingHorizontal: 10,
    paddingVertical: 8,
    alignItems: 'flex-end',
    backgroundColor: '#fff',
  },
  offerDetailOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(18, 12, 8, 0.56)',
    paddingHorizontal: 14,
    paddingVertical: 16,
    zIndex: 40,
  },
  offerDetailShell: {
    flex: 1,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: theme.surface,
    overflow: 'hidden',
  },
  offerDetailHead: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: theme.line,
    backgroundColor: '#f7f1e8',
  },
  marketFlipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: theme.line,
    backgroundColor: '#fdf8f1',
  },
  marketFlipText: {
    color: '#6a6055',
    fontSize: 11,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    fontWeight: '600',
  },
  offerDetailTitle: {
    color: '#1c1713',
    fontSize: 20,
    lineHeight: 23,
    fontFamily: 'Didot',
  },
  offerDetailBody: {
    padding: 12,
    gap: 10,
  },
  offerDetailPanel: {
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: '#fff',
    padding: 10,
    gap: 8,
  },
  offerDetailHero: {
    width: '100%',
    height: 240,
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: '#ece7df',
  },
  offerDetailThumbRow: {
    gap: 8,
  },
  offerDetailThumb: {
    width: 70,
    height: 70,
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: '#ece7df',
  },
  offerDetailListingCard: {
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: '#fff',
    padding: 8,
    gap: 7,
  },
  offerDetailListingImage: {
    width: '100%',
    height: 182,
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: '#ece7df',
  },
  offerDetailItemTitle: {
    color: '#191510',
    fontSize: 16,
    lineHeight: 20,
    fontFamily: 'Didot',
  },
  offerDetailItemMeta: {
    color: '#5c5349',
    fontSize: 11,
    lineHeight: 14,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  offerDetailMessage: {
    color: '#3f382f',
    fontSize: 14,
    lineHeight: 20,
  },
  offerActions: {
    borderTopWidth: 1,
    borderTopColor: theme.line,
    padding: 10,
    gap: 8,
  },
  profileAddressCard: {
    borderWidth: 1,
    borderColor: theme.line,
    borderRadius: 10,
    padding: 9,
    gap: 6,
    backgroundColor: '#fff',
  },
  profilePaymentCard: {
    borderWidth: 1,
    borderColor: theme.line,
    borderRadius: 10,
    padding: 10,
    gap: 7,
    backgroundColor: '#fff',
  },
  profileAddressRow: {
    flexDirection: 'row',
    gap: 8,
  },
  addressActionRow: {
    flexDirection: 'row',
    gap: 6,
  },
  addressRow: {
    gap: 8,
    paddingVertical: 2,
  },
  addressChip: {
    borderWidth: 1,
    borderColor: '#d8cab8',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 7,
    backgroundColor: '#fff',
    minWidth: 126,
  },
  addressChipActive: {
    borderColor: theme.brand,
    backgroundColor: theme.brandSoft,
  },
  addressChipText: {
    color: '#4d4339',
    fontWeight: '700',
    fontSize: 10,
    letterSpacing: 1.1,
  },
  addressChipTextActive: { color: theme.brand },
  addressChipSubText: {
    color: '#6f665d',
    fontSize: 11,
    marginTop: 2,
  },
  addressChipSubTextActive: { color: theme.brand },
  labelBlock: {
    borderTopWidth: 1,
    borderTopColor: theme.line,
    padding: 10,
    gap: 8,
  },
  labelBlockHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  shipmentCard: {
    borderWidth: 1,
    borderColor: theme.line,
    borderRadius: 10,
    padding: 9,
    gap: 3,
    backgroundColor: '#fff',
  },
  shipmentTitle: {
    color: '#2a2119',
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.4,
  },
  shipmentMeta: {
    color: '#6f665d',
    fontSize: 11,
  },

  stepRow: { flexDirection: 'row', gap: 8 },
  stepPill: {
    width: 34,
    height: 34,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#d8cbbd',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
  },
  stepPillActive: { backgroundColor: theme.brand, borderColor: theme.brand },
  stepPillText: { color: '#524941', fontWeight: '600' },
  stepPillTextActive: { color: '#fff' },

  label: { fontSize: 11, color: '#6c6359', fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase' },
  input: {
    borderWidth: 1,
    borderColor: '#d9cec0',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 9,
    backgroundColor: '#fff',
    color: '#1c1917',
  },
  multiInput: { minHeight: 74, textAlignVertical: 'top' },

  modeRow: { flexDirection: 'row', gap: 8, marginVertical: 2 },
  modeBtn: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#d9cec0',
    borderRadius: 9,
    paddingVertical: 8,
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  modeBtnActive: { borderColor: theme.brand, backgroundColor: theme.brandSoft },
  modeBtnText: { color: '#4a4138', fontWeight: '700', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 },
  modeBtnTextActive: { color: theme.brand },

  primaryBtn: {
    backgroundColor: theme.brand,
    borderRadius: 10,
    paddingVertical: 11,
    paddingHorizontal: 14,
    alignItems: 'center',
  },
  primaryBtnText: { color: '#fff', fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase', fontSize: 12 },
  secondaryBtn: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#d8cab8',
    paddingVertical: 11,
    paddingHorizontal: 14,
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  primaryBtnCompact: {
    alignSelf: 'flex-start',
    marginTop: 6,
    backgroundColor: theme.brand,
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 10,
    alignItems: 'center',
  },
  primaryBtnDisabled: {
    opacity: 0.5,
  },
  secondaryBtnCompact: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#d8cab8',
    paddingVertical: 7,
    paddingHorizontal: 9,
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  listingActionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 6,
  },
  secondaryBtnText: { color: '#4b433a', fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase', fontSize: 12 },
  actionRow: { flexDirection: 'row', gap: 8, marginTop: 4 },
  tradeCandidateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderColor: theme.line,
    padding: 8,
    backgroundColor: '#fff',
  },
  tradeCandidateRowActive: {
    borderColor: theme.brand,
    backgroundColor: theme.brandSoft,
  },
  tradeCandidateThumb: {
    width: 56,
    height: 56,
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: '#ece7df',
  },
  tradeCheck: {
    width: 24,
    height: 24,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#c7b8a6',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
  },
  tradeCheckActive: {
    borderColor: theme.brand,
    backgroundColor: theme.brand,
  },
  tradeCheckText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 12,
  },
  tradeCheckTextActive: {
    color: '#fff',
  },

  filterRow: { gap: 8 },
  filterButton: {
    borderWidth: 1,
    borderColor: '#d8cab8',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#fff',
  },
  filterButtonActive: { backgroundColor: theme.brand, borderColor: theme.brand },
  filterButtonText: { color: '#4d4339', fontWeight: '700', fontSize: 11, textTransform: 'uppercase', letterSpacing: 1.2 },
  filterButtonTextActive: { color: '#fff' },
  tagChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  tagChip: {
    borderWidth: 1,
    borderColor: '#d8cab8',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#fff',
  },
  tagChipActive: {
    borderColor: theme.brand,
    backgroundColor: theme.brandSoft,
  },
  tagChipText: {
    color: '#4d4339',
    fontWeight: '700',
    fontSize: 11,
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  tagChipTextActive: {
    color: theme.brand,
  },

  helperText: { color: '#756b61' },
  emptyText: { color: '#7a7167', textAlign: 'center', paddingVertical: 10 },
  error: { color: theme.error, fontWeight: '700', marginHorizontal: 16, marginBottom: 6 },
  notice: { color: theme.success, fontWeight: '700', marginHorizontal: 16, marginBottom: 6 },
});
