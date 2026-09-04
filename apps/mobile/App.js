import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Linking,
  Modal,
  Platform,
  RefreshControl,
  Share,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import * as ImageManipulator from 'expo-image-manipulator';
import * as WebBrowser from 'expo-web-browser';
import Constants from 'expo-constants';
import { StatusBar } from 'expo-status-bar';
import { ClerkProvider, useAuth, useClerk, useOAuth, useSignIn, useSignUp, useUser } from '@clerk/clerk-expo';
import { tokenCache } from '@clerk/clerk-expo/token-cache';
import { FontAwesome, Ionicons } from '@expo/vector-icons';
import { createMobileApiClient } from './src/lib/apiClient';

WebBrowser.maybeCompleteAuthSession();

const API_DEFAULT = process.env.EXPO_PUBLIC_API_BASE_URL || Constants.expoConfig?.extra?.apiBaseUrl || 'http://127.0.0.1:8000';
const CLERK_PUBLISHABLE_KEY = Constants.expoConfig?.extra?.clerkPublishableKey || process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY || '';
const TEMP_SHOW_PROFILE_QUESTIONNAIRE_ON_LOGIN = false;
const ANALYSIS_FAILED_MESSAGE = 'Analysis failed. Please manually update the listing details.';
const PRIVACY_POLICY_URL = 'https://jouft.com/privacy';
const TERMS_URL = 'https://jouft.com/terms';
const CONTACT_EMAIL = 'admin@jouft.com';
const CONTACT_ADDRESS_LINES = ['120 Vantis Dr. Suite 300', 'Aliso Viejo, CA 92656', 'US'];
const CONTACT_MAP_QUERY = '120 Vantis Dr Suite 300, Aliso Viejo, CA 92656, US';
const CONTACT_DIRECTIONS_URL = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(CONTACT_MAP_QUERY)}`;
const UPLOAD_MAX_DIMENSION = 1600;
const UPLOAD_JPEG_QUALITY = 0.82;
const TABS = ['marketplace', 'closet', 'create', 'inbox', 'profile'];
const LISTINGS_PAGE_SIZE = 24;
const TAB_LABELS = {
  marketplace: 'Market',
  closet: 'Closet',
  create: 'Create',
  inbox: 'Inbox',
  profile: 'Profile',
};
const TAB_ICONS = {
  marketplace: 'search-outline',
  closet: 'shirt-outline',
  create: 'add-circle-outline',
  inbox: 'chatbubbles-outline',
  profile: 'person-outline',
};
const OFFER_FILTERS = ['pending', 'accepted', 'declined', 'all'];
const SUBSCRIPTION_PLANS = [
  { key: 'free', label: 'Free', monthly: 0, annual: 0, limit: '3 listings / month' },
  { key: 'starter_15', label: '$15 Plan', monthly: 15, annual: 162, limit: '25 listings / month' },
  { key: 'pro_25', label: '$25 Plan', monthly: 25, annual: 270, limit: 'Unlimited listings' },
];
const US_NUMERIC_APPAREL_SIZE_OPTIONS = ['00', '0', '2', '4', '6', '8', '10', '12', '14', '16', '18', '20', '22', '24'];
const FEMALE_ALPHA_APPAREL_SIZE_OPTIONS = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL'];
const MALE_ALPHA_APPAREL_SIZE_OPTIONS = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'];
const FEMALE_APPAREL_SIZE_OPTIONS = [...FEMALE_ALPHA_APPAREL_SIZE_OPTIONS, ...US_NUMERIC_APPAREL_SIZE_OPTIONS];
const MALE_APPAREL_SIZE_OPTIONS = [...MALE_ALPHA_APPAREL_SIZE_OPTIONS, ...US_NUMERIC_APPAREL_SIZE_OPTIONS];
const APPAREL_SIZE_OPTIONS = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', ...US_NUMERIC_APPAREL_SIZE_OPTIONS];
const ACCESSORY_SIZE_OPTIONS = ['One Size', 'Mini', 'Small', 'Medium', 'Large', 'Adjustable'];
const FEMALE_SHOE_SIZE_OPTIONS = ['US 5', 'US 5.5', 'US 6', 'US 6.5', 'US 7', 'US 7.5', 'US 8', 'US 8.5', 'US 9', 'US 9.5', 'US 10', 'US 10.5', 'US 11', 'US 12'];
const MALE_SHOE_SIZE_OPTIONS = ['US 6', 'US 6.5', 'US 7', 'US 7.5', 'US 8', 'US 8.5', 'US 9', 'US 9.5', 'US 10', 'US 10.5', 'US 11', 'US 11.5', 'US 12', 'US 13', 'US 14'];
const PROFILE_CATEGORY_OPTIONS = ['Dresses', 'Jackets', 'Shoes', 'Handbags', 'Skirts', 'Accessories'];
const STYLE_DESCRIPTOR_OPTIONS = ['Classic', 'Trendy', 'Unique'];
const JOUFT_GOAL_OPTIONS = [
  'Refresh My Closet',
  'Trade Unworn Pieces',
  'Discover Rare Finds',
  'Access Luxury Fashion',
  'Build My Collection',
  'Sustainable Fashion',
  'Connect With Fashion Enthusiasts',
  'Trade Instead of Sell',
];
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
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: false,
      shouldSetBadge: false,
    }),
  });
} catch (e) {
  NotificationsModule = null;
}

const theme = {
  bg: '#f1f1f1',
  surface: '#fbf8f2',
  text: '#18181b',
  muted: '#4f5560',
  line: 'rgba(18, 26, 36, 0.14)',
  lineStrong: 'rgba(18, 26, 36, 0.28)',
  brand: '#4a161b',
  brandSoft: '#f1e8e1',
  panel: '#f8f8f8',
  success: '#155e4a',
  error: '#a82222',
};
const ALERT_CATEGORIES = [
  { key: 'likes', label: 'Likes' },
  { key: 'trades', label: 'Trades' },
  { key: 'shipping', label: 'Shipping' },
];

const DEFAULT_ALERT_PREFS = {
  likes: true,
  trades: true,
  shipping: true,
};

function uploadBaseName(name, index) {
  const fallback = `upload-${index + 1}`;
  const cleanName = String(name || fallback);
  const dotIndex = cleanName.lastIndexOf('.');
  return dotIndex > 0 ? cleanName.slice(0, dotIndex) : cleanName;
}

async function prepareMobileImageForUpload(image, index) {
  const width = Number(image?.width || 0);
  const height = Number(image?.height || 0);
  const resizeAction = width > 0 && height > 0 && Math.max(width, height) > UPLOAD_MAX_DIMENSION
    ? [{
      resize: width >= height
        ? { width: UPLOAD_MAX_DIMENSION }
        : { height: UPLOAD_MAX_DIMENSION },
    }]
    : [];
  const result = await ImageManipulator.manipulateAsync(
    image.uri,
    resizeAction,
    { compress: UPLOAD_JPEG_QUALITY, format: ImageManipulator.SaveFormat.JPEG },
  );
  return {
    ...image,
    uri: result.uri,
    width: result.width || image.width,
    height: result.height || image.height,
    fileName: `${uploadBaseName(image.fileName || image.name, index)}.jpg`,
    mimeType: 'image/jpeg',
    fileSize: result.fileSize || image.fileSize || null,
  };
}

async function uploadImagesWithDirectFallback({ apiClient, images, auth }) {
  let prepared = [];
  try {
    prepared = await Promise.all((images || []).map((image, index) => prepareMobileImageForUpload(image, index)));
  } catch (e) {
    prepared = images || [];
  }
  try {
    const blobs = await Promise.all(prepared.map(async (image) => {
      const resp = await fetch(image.uri);
      if (!resp.ok) throw new Error('Could not read prepared image for upload.');
      return resp.blob();
    }));
    const presigned = await apiClient.createImageUploadSlots({
      images: prepared.map((image, index) => ({
        fileName: image.fileName || `upload-${index + 1}.jpg`,
        mimeType: image.mimeType || 'image/jpeg',
        contentLength: blobs[index]?.size || image.fileSize || null,
      })),
    }, auth);
    const slots = presigned?.upload_slots || [];
    if (slots.length !== prepared.length) throw new Error('Upload slot count did not match selected images.');
    await Promise.all(slots.map(async (slot, index) => {
      const resp = await fetch(slot.upload_url, {
        method: slot.method || 'PUT',
        headers: slot.headers || { 'Content-Type': prepared[index]?.mimeType || 'image/jpeg' },
        body: blobs[index],
      });
      if (!resp.ok) throw new Error(`Direct image upload failed (${resp.status})`);
    }));
    return apiClient.confirmImageUploads({
      itemId: presigned.item_id,
      uploadedImages: slots.map((slot, index) => ({
        image_id: slot.image_id,
        filename: prepared[index]?.fileName || `upload-${index + 1}.jpg`,
        content_type: prepared[index]?.mimeType || 'image/jpeg',
        storage_uri: slot.storage_uri,
        role_hint: slot.role_hint,
      })),
    }, auth);
  } catch (e) {
    return apiClient.uploadImages({ images: prepared }, auth);
  }
}

function titleCase(input) {
  return String(input || '')
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(' ');
}

function displayConditionLabel(input) {
  const normalized = String(input || '').replace(/[-_\s]+/g, '').toLowerCase();
  if (normalized === 'newwithtags' || normalized === 'nwt') return 'New with Tags';
  if (normalized === 'likenew') return 'Like New';
  return titleCase(input || 'unknown');
}

function shipmentTrackingLabel(shipment) {
  const raw = String(shipment?.tracking_status || shipment?.status || '').trim().toLowerCase();
  const labels = {
    label_created: 'Label created',
    pre_transit: 'Label created',
    shipped: 'In transit',
    transit: 'In transit',
    out_for_delivery: 'Out for delivery',
    delivered: 'Delivered',
    returned: 'Returned',
    exception: 'Delivery exception',
  };
  return labels[raw] || (raw ? titleCase(raw) : 'Tracking pending');
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
  const trimmed = url.trim();
  const baseUrl = String(apiBaseUrl || '').replace(/\/$/, '');
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    try {
      const parsed = new URL(trimmed);
      if (parsed.pathname.startsWith('/v1/images/') && parsed.hostname.endsWith('.elb.amazonaws.com')) {
        return `${baseUrl}${parsed.pathname}`;
      }
    } catch (e) {
      return trimmed;
    }
    return trimmed;
  }
  if (trimmed.startsWith('/')) return `${baseUrl}${trimmed}`;
  return null;
}

function listingOwnerSubject(item) {
  return String(item?.owner_subject || item?.ownerSubject || '').trim().toLowerCase();
}

function listingOwnerName(item) {
  return String(item?.owner_name || item?.owner || '').trim().toLowerCase();
}

function listingOwnerDisplayName(item, fallback = 'Unknown member') {
  const ownerNameRaw = String(item?.owner_name || item?.owner || '').trim();
  const ownerSubjectRaw = String(item?.owner_subject || item?.ownerSubject || '').trim();
  const ownerNameLooksLikeSubject = ownerNameRaw && (
    ownerNameRaw === ownerSubjectRaw
    || /^user_[a-z0-9]+$/i.test(ownerNameRaw)
  );
  if (!ownerNameRaw || ownerNameLooksLikeSubject) return fallback;
  return ownerNameRaw;
}

function ownerFirstName(name, fallback = 'Member') {
  const value = String(name || '').trim();
  if (!value) return fallback;
  const first = value.split(/\s+/).find(Boolean);
  return first || fallback;
}

function isSameListingOwner(left, right, currentSubject = '') {
  const normalizedCurrentSubject = String(currentSubject || '').trim().toLowerCase();
  const leftSubject = String(left?.owner_subject || left?.ownerSubject || '').trim().toLowerCase();
  const rightSubject = String(right?.owner_subject || right?.ownerSubject || '').trim().toLowerCase();
  if (leftSubject && rightSubject) return leftSubject === rightSubject;
  if (normalizedCurrentSubject && leftSubject === normalizedCurrentSubject && rightSubject === normalizedCurrentSubject) return true;
  const leftOwner = listingOwnerName(left);
  const rightOwner = listingOwnerName(right);
  return Boolean((!leftSubject || !rightSubject) && leftOwner && rightOwner && leftOwner === rightOwner);
}

function getCrossOwnerMatches(item, currentSubject = '') {
  const normalizedCurrentSubject = String(currentSubject || '').trim().toLowerCase();
  const itemOwnerSubject = listingOwnerSubject(item);
  const matches = Array.isArray(item?.matches) ? item.matches : [];
  return matches.filter((match) => {
    if (isSameListingOwner(item, match, normalizedCurrentSubject)) return false;
    if (normalizedCurrentSubject && itemOwnerSubject === normalizedCurrentSubject && listingOwnerSubject(match) === normalizedCurrentSubject) return false;
    return true;
  });
}

function removeSentOfferMatchesFromListings(listings, targetListingId, offeredListingIds) {
  const targetId = String(targetListingId || '').trim();
  const offeredIds = new Set((Array.isArray(offeredListingIds) ? offeredListingIds : [])
    .map((id) => String(id || '').trim())
    .filter(Boolean));
  if (!targetId || offeredIds.size === 0) return listings;
  return (Array.isArray(listings) ? listings : []).map((listing) => {
    if (String(listing?.listing_id || listing?.id || '') !== targetId || !Array.isArray(listing?.matches)) return listing;
    return {
      ...listing,
      matches: listing.matches.filter((match) => !offeredIds.has(String(match?.listing_id || match?.id || ''))),
    };
  });
}

function getMatchPreviewImages(item, apiBaseUrl, currentSubject = '') {
  const matches = getCrossOwnerMatches(item, currentSubject);
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
  const listedImages = Array.isArray(listing.listed_images)
    ? listing.listed_images
    : (Array.isArray(listing.listedImages) ? listing.listedImages : []);
  const raw = listedImages.length > 0
    ? listedImages.map((entry) => entry?.d_img || entry?.display_image || entry?.image)
    : Array.isArray(listing.images) && listing.images.length > 0
    ? listing.images
    : [listing.image].filter(Boolean);
  const seen = new Set();
  return raw
    .map((url) => normalizeImageUrl(url, apiBaseUrl))
    .filter((url) => {
      if (!url || seen.has(url)) return false;
      seen.add(url);
      return true;
    });
}

function missingPublishFields(listing) {
  const missing = [];
  const gallery = Array.isArray(listing?.images) && listing.images.length > 0
    ? listing.images.filter(Boolean)
    : [listing?.image].filter(Boolean);
  const title = String(listing?.title || '').trim();
  const category = String(listing?.category || '').trim().toLowerCase();
  const brand = String(listing?.brand || '').trim();
  const condition = String(listing?.condition || '').trim();
  const value = Number(listing?.estimated_value ?? listing?.estimatedValue ?? 0);
  const size = String(listing?.size || '').trim();
  const validCategories = new Set(['clothes', 'shoes', 'handbag', 'accessories']);
  const validConditions = new Set(['NewWithTags', 'New', 'LikeNew']);

  if (gallery.length < 1) missing.push('photos');
  if (!title || title.toLowerCase() === 'new listing' || title.toLowerCase() === 'untitled listing') missing.push('title');
  if (!validCategories.has(category)) missing.push('category');
  if (!brand || ['unknown', 'analyzing...', 'n/a'].includes(brand.toLowerCase())) missing.push('brand');
  if (!validConditions.has(condition)) missing.push('condition');
  if (!Number.isFinite(value) || value <= 0) missing.push('AI estimated value');
  if ((category === 'clothes' || category === 'shoes') && !size) missing.push('size');
  return missing;
}

function missingPublishFieldsMessage(listing) {
  const missing = missingPublishFields(listing);
  return missing.length > 0
    ? `Listing missing fields: ${missing.join(', ')}. Please edit the listing and add the missing information before publishing.`
    : '';
}

function persistableImageUrl(url) {
  if (!url || typeof url !== 'string') return '';
  const trimmed = url.trim();
  if (!trimmed) return '';
  try {
    const parsed = new URL(trimmed);
    return parsed.pathname.startsWith('/v1/images/') ? parsed.pathname : trimmed;
  } catch {
    return trimmed;
  }
}

function persistableImageUrls(values) {
  const seen = new Set();
  return (Array.isArray(values) ? values : [])
    .map(persistableImageUrl)
    .filter((url) => {
      if (!url || seen.has(url)) return false;
      seen.add(url);
      return Boolean(normalizeImageUrl(url, ''));
    });
}

function uploadedImageUrlsFromPayload(payload) {
  const uploaded = Array.isArray(payload?.uploaded_images) ? payload.uploaded_images : [];
  return uploaded
    .map((entry) => (typeof entry?.image_url === 'string' ? entry.image_url.trim() : ''))
    .filter(Boolean);
}

function sameStringList(left, right) {
  const a = (Array.isArray(left) ? left : []).map((value) => String(value || '').trim()).filter(Boolean);
  const b = (Array.isArray(right) ? right : []).map((value) => String(value || '').trim()).filter(Boolean);
  if (a.length !== b.length) return false;
  return a.every((value, index) => value === b[index]);
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

function isGenericTradeNote(value) {
  const normalized = String(value || '').trim().toLowerCase().replace(/[.!\s]+$/g, '');
  return normalized === 'open to similar-value offers'
    || normalized === 'open to similar value offers'
    || normalized === 'no description provided';
}

function listingDescription(listing) {
  const candidates = [
    listing?.description,
    listing?.wants,
    listing?.notes,
    listing?.trade_notes,
  ];
  const first = candidates.find((value) => typeof value === 'string' && value.trim() && !isGenericTradeNote(value));
  return first ? first.trim() : '';
}

function offerOfferedListings(offer) {
  return Array.isArray(offer?.offered_listings) && offer.offered_listings.length > 0
    ? offer.offered_listings
    : (offer?.offered_listing ? [offer.offered_listing] : []);
}

function offerParticipantName(offer, role = 'from') {
  const direct = String(role === 'to' ? offer?.to_name || '' : offer?.from_name || '').trim();
  if (direct && !direct.toLowerCase().startsWith('user_')) return direct.split(/\s+/)[0];
  const subject = String(role === 'to' ? offer?.to_subject || '' : offer?.from_subject || '').trim();
  return subject && !subject.toLowerCase().startsWith('user_') ? subject.split(/\s+/)[0] : 'Member';
}

function offerActorSubject(offer, fallbackSubject = '') {
  const fallback = String(fallbackSubject || '').trim();
  const actor = String(offer?.actor_subject || offer?.actorSubject || '').trim();
  if (actor) return actor;
  if (fallback) return fallback;
  return '';
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

function isCompleteShippingAddress(address) {
  return Boolean(
    String(address?.full_name || '').trim()
    && String(address?.address_line1 || '').trim()
    && String(address?.city || '').trim()
    && String(address?.state || '').trim()
    && String(address?.postal_code || '').trim()
    && String(address?.country || '').trim()
  );
}

function completeShippingAddresses(addresses) {
  return (Array.isArray(addresses) ? addresses : []).filter(isCompleteShippingAddress);
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

function normalizeProfileQuiz(profile) {
  if (!profile) return null;
  return {
    ...profile,
    first_name: profile?.first_name || '',
    last_name: profile?.last_name || '',
    email: profile?.email || '',
    shipping_email: profile?.shipping_email || profile?.email || '',
    shipping_phone: profile?.shipping_phone || '',
    birthday: profile?.birthday || '',
    gender: profile?.gender || '',
    tops_size: normalizeMultiSizeValue(profile?.tops_size),
    dresses_size: normalizeMultiSizeValue(profile?.dresses_size),
    bottoms_size: normalizeMultiSizeValue(profile?.bottoms_size),
    shoes_size: normalizeMultiSizeValue(profile?.shoes_size),
    category_preferences: Array.isArray(profile?.category_preferences) ? profile.category_preferences : [],
    style_descriptors: Array.isArray(profile?.style_descriptors) ? profile.style_descriptors : [],
    jouft_goals: Array.isArray(profile?.jouft_goals) ? profile.jouft_goals : [],
  };
}

function isProfileSetupRequired(profile) {
  const firstName = String(profile?.first_name || profile?.firstName || '').trim();
  const lastName = String(profile?.last_name || profile?.lastName || '').trim();
  const email = String(profile?.email || '').trim();
  const gender = String(profile?.gender || '').trim();
  const birthday = String(profile?.birthday || '').trim();
  const addresses = completeShippingAddresses(normalizeProfileShippingAddresses(profile?.shipping_addresses, profile));
  const hasSizes = normalizeMultiSizeValue(profile?.tops_size).length > 0
    || normalizeMultiSizeValue(profile?.dresses_size).length > 0
    || normalizeMultiSizeValue(profile?.bottoms_size).length > 0
    || normalizeMultiSizeValue(profile?.shoes_size).length > 0;
  const hasStyle = Array.isArray(profile?.style_descriptors) && profile.style_descriptors.length > 0;
  const hasGoal = Array.isArray(profile?.jouft_goals) && profile.jouft_goals.length > 0;
  const plan = String(profile?.subscription_plan || '').trim().toLowerCase();
  const status = String(profile?.subscription_status || '').trim().toLowerCase();
  const hasSubscription = plan === 'free' || ['active', 'trialing'].includes(status);
  return !firstName || !lastName || !email || !gender || !birthday || addresses.length === 0 || !hasSizes || !hasStyle || !hasGoal || !hasSubscription;
}

function normalizeSelectableSubscriptionPlan(plan) {
  const raw = String(plan || '').trim();
  return SUBSCRIPTION_PLANS.some((entry) => entry.key === raw) ? raw : 'free';
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

function sizeOptionsForCategory(category) {
  const normalized = String(category || '').trim().toLowerCase();
  if (normalized === 'shoes') return ['US 5', 'US 5.5', 'US 6', 'US 6.5', 'US 7', 'US 7.5', 'US 8', 'US 8.5', 'US 9', 'US 9.5', 'US 10', 'US 10.5', 'US 11', 'US 12'];
  if (normalized === 'clothes') return APPAREL_SIZE_OPTIONS;
  if (normalized === 'handbag') return ['Mini', 'Small', 'Medium', 'Large'];
  if (normalized === 'accessories') return ACCESSORY_SIZE_OPTIONS;
  return [];
}

function brandSizeChartUrl(brand, category) {
  const name = String(brand || '').trim().toLowerCase();
  if (!name || name === 'unknown') return null;
  const key = `${name}:${String(category || '').trim().toLowerCase()}`;
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
  };
  if (byCategory[key]) return byCategory[key];
  const generic = {
    gucci: 'https://www.gucci.com/us/en/st/stories/article/size-guide',
    burberry: 'https://us.burberry.com/customer-service/size-guide/',
    'jimmy choo': 'https://us.jimmychoo.com/en/customer-services/size-guide/',
    balenciaga: 'https://www.balenciaga.com/en-us/size-guide',
    chanel: 'https://www.chanel.com/us/fashion/size-guide/',
    coach: 'https://www.coach.com/customer-service-size-guide',
    'louis vuitton': 'https://us.louisvuitton.com/eng-us/faq/size-guide',
    prada: 'https://www.prada.com/us/en/customer-service/size-guide.html',
  };
  return generic[name] || null;
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
  const icon = TAB_ICONS[tab] || 'ellipse-outline';
  return (
    <TouchableOpacity style={[styles.tabButton, active && styles.tabButtonActive]} onPress={() => onPress(tab)}>
      <Ionicons
        name={icon}
        size={22}
        color={active ? '#fff' : '#4a4139'}
        style={styles.tabButtonIcon}
      />
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
  onEditDraft = null,
  onReviewListing = null,
  onPublishListing = null,
  onRemoveListing = null,
  onShareListing = null,
  onShareToPinterest = null,
  onShareToFacebook = null,
  liked = false,
  onToggleLike = null,
  currentOwnerSubject = '',
  currentUserDisplayName = '',
  showStatus = true,
}) {
  const rawImageUrl = item?.image || item?.images?.[0];
  const [imageFailed, setImageFailed] = useState(false);
  const imageUrl = imageFailed ? null : normalizeImageUrl(rawImageUrl, apiBaseUrl);
  useEffect(() => {
    setImageFailed(false);
  }, [rawImageUrl, apiBaseUrl]);
  const matchPreviewImages = showMatches ? getMatchPreviewImages(item, apiBaseUrl, currentOwnerSubject) : [];
  const hasMatches = getCrossOwnerMatches(item, currentOwnerSubject).length > 0;
  const statusLabel = String(item?.status || '').trim();
  const analysisFailed = statusLabel.toLowerCase() === 'analysisfailed';
  const analyzing = statusLabel.toLowerCase() === 'analyzing';
  const closetCardDisabled = analyzing && Boolean(onEditDraft || onPublishListing || onRemoveListing);
  const canReviewAndPublish = typeof onReviewListing === 'function' && !['active', 'analyzing', 'analysisfailed'].includes(statusLabel.toLowerCase());
  const isCurrentUserListing = Boolean(
    currentOwnerSubject
    && listingOwnerSubject(item)
    && listingOwnerSubject(item) === String(currentOwnerSubject || '').trim().toLowerCase()
  );
  const ownerName = ownerFirstName(
    listingOwnerDisplayName(item, isCurrentUserListing ? (currentUserDisplayName || 'You') : 'Member'),
    isCurrentUserListing ? 'You' : 'Member',
  );
  const brandLabel = item?.brand || 'Unknown';
  const conditionLabel = displayConditionLabel(item?.condition || 'unknown');
  const sizeLabel = item?.size || 'N/A';
  const CardContainer = onOpenDetails ? TouchableOpacity : View;
  const cardContainerProps = onOpenDetails ? {
    onPress: () => onOpenDetails(item),
    disabled: closetCardDisabled,
    activeOpacity: 0.88,
    accessibilityRole: 'button',
    accessibilityLabel: `View details for ${item?.title || 'listing'}`,
  } : {};
  return (
    <CardContainer
      style={[styles.listingCard, closetCardDisabled && styles.listingCardDisabled]}
      {...cardContainerProps}
    >
      {imageUrl ? (
        <Image
          source={{ uri: imageUrl }}
          style={[styles.listingImage, closetCardDisabled && styles.listingCardContentDisabled]}
          onError={() => setImageFailed(true)}
        />
      ) : (
        <View style={[styles.listingImage, styles.listingImageFallback, closetCardDisabled && styles.listingCardContentDisabled]}>
          <Text style={styles.emptyText}>Image unavailable</Text>
        </View>
      )}
      <View style={[styles.listingBody, closetCardDisabled && styles.listingCardContentDisabled]}>
        <View style={styles.listingTitleRow}>
          <View style={{ flex: 1 }}>
            <Text numberOfLines={2} style={styles.listingTitle}>{item?.title || 'Untitled listing'}</Text>
          </View>
          {onToggleLike ? (
            <TouchableOpacity
              style={[styles.likeButton, liked && styles.likeButtonActive]}
              onPress={() => onToggleLike(item)}
              accessibilityRole="button"
              accessibilityLabel={liked ? 'Unlike listing' : 'Like listing'}
            >
              <Text style={[styles.likeButtonText, liked && styles.likeButtonTextActive]}>{liked ? '♥' : '♡'}</Text>
            </TouchableOpacity>
          ) : null}
        </View>
        <Text numberOfLines={1} style={styles.listingByline}>
          BY {ownerName.toUpperCase()}
        </Text>
        <Text numberOfLines={2} style={styles.listingMeta}>
          EST. {money(item?.estimated_value)} · {String(brandLabel).toUpperCase()} · {String(conditionLabel).toUpperCase()} · SIZE {String(sizeLabel).toUpperCase()}
        </Text>
        {analysisFailed ? (
          <Text style={styles.analysisFailedText}>{ANALYSIS_FAILED_MESSAGE}</Text>
        ) : null}
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
        {showStatus && statusLabel || onEditDraft || onRemoveListing || onShareListing || onShareToPinterest || onShareToFacebook ? (
          <View style={styles.listingActionRow}>
            {showStatus && statusLabel ? (
              <View style={[styles.statusBadge, analysisFailed && styles.statusBadgeFailed]}>
                <Text style={[styles.statusBadgeText, analysisFailed && styles.statusBadgeTextFailed]}>
                  {titleCase(statusLabel)}
                </Text>
              </View>
            ) : null}
            {onEditDraft ? (
              <TouchableOpacity
                style={[styles.secondaryBtnCompact, styles.listingIconButton, analyzing && styles.primaryBtnDisabled]}
                onPress={() => onEditDraft(item)}
                disabled={analyzing}
                accessibilityRole="button"
                accessibilityLabel="Edit listing"
              >
                <FontAwesome name="pencil-square-o" size={19} color="#4b433a" />
              </TouchableOpacity>
            ) : null}
            {onRemoveListing ? (
              <TouchableOpacity
                style={[styles.secondaryBtnCompact, styles.listingIconButton, styles.dangerBtnCompact, closetCardDisabled && styles.primaryBtnDisabled]}
                onPress={() => onRemoveListing(item)}
                disabled={closetCardDisabled}
                accessibilityRole="button"
                accessibilityLabel="Delete listing"
              >
                <FontAwesome name="trash-o" size={20} color="#b42318" />
              </TouchableOpacity>
            ) : null}
            {onShareListing ? (
              <TouchableOpacity
                style={[styles.secondaryBtnCompact, styles.listingTextButton, closetCardDisabled && styles.primaryBtnDisabled]}
                onPress={() => onShareListing(item)}
                disabled={closetCardDisabled}
              >
                <Text style={styles.secondaryBtnText}>Share</Text>
              </TouchableOpacity>
            ) : null}
            {onShareToPinterest ? (
              <TouchableOpacity
                style={[styles.secondaryBtnCompact, styles.shareIconButton, closetCardDisabled && styles.primaryBtnDisabled]}
                onPress={() => onShareToPinterest(item)}
                disabled={closetCardDisabled}
                accessibilityRole="button"
                accessibilityLabel="Share on Pinterest"
              >
                <FontAwesome name="pinterest-p" size={18} color="#4b433a" />
              </TouchableOpacity>
            ) : null}
            {onShareToFacebook ? (
              <TouchableOpacity
                style={[styles.secondaryBtnCompact, styles.shareIconButton, closetCardDisabled && styles.primaryBtnDisabled]}
                onPress={() => onShareToFacebook(item)}
                disabled={closetCardDisabled}
                accessibilityRole="button"
                accessibilityLabel="Share on Facebook"
              >
                <FontAwesome name="facebook" size={18} color="#4b433a" />
              </TouchableOpacity>
            ) : null}
          </View>
        ) : null}
      </View>
      {closetCardDisabled ? (
        <View pointerEvents="none" style={styles.pendingReviewOverlay}>
          <Text style={styles.pendingReviewText}>Pending Review</Text>
        </View>
      ) : null}
      {canReviewAndPublish ? (
        <TouchableOpacity
          style={styles.pendingReviewOverlay}
          onPress={() => onReviewListing(item)}
          accessibilityRole="button"
          accessibilityLabel="Review and publish listing"
        >
          <Text style={styles.pendingReviewText}>Review and Publish</Text>
        </TouchableOpacity>
      ) : null}
    </CardContainer>
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
      <Text style={styles.offerMeta}>From: {offerParticipantName(offer, 'from')}</Text>
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
            {targetListing?.brand || 'Unknown'} • {displayConditionLabel(targetListing?.condition || 'unknown')}
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
      <View style={styles.brandMainRow}>
        <Text style={styles.brandWordmark}>JOUFT</Text>
        <Text style={styles.brandSubWordmark}>AI LUXURY EXCHANGE</Text>
      </View>
    </View>
  );
}

function MarketplaceMobileApp({ clerkEnabled = false, getBearerToken = null, clerkUserLabel = '', clerkUserProfile = {}, onSignOut = null }) {
  const [apiBaseUrl, setApiBaseUrl] = useState(API_DEFAULT);
  const [authMode, setAuthMode] = useState('api_key');
  const [apiKey, setApiKey] = useState('local-dev-key');
  const [bearerToken, setBearerToken] = useState('');

  const [activeTab, setActiveTab] = useState(TEMP_SHOW_PROFILE_QUESTIONNAIRE_ON_LOGIN ? 'profile' : 'marketplace');
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
  const [selectedGalleryImage, setSelectedGalleryImage] = useState(null);
  const [failedDetailImages, setFailedDetailImages] = useState({});
  const [tradeComposerTarget, setTradeComposerTarget] = useState(null);
  const [tradeOfferCandidates, setTradeOfferCandidates] = useState([]);
  const [tradeOfferListingIds, setTradeOfferListingIds] = useState([]);
  const [tradeOfferMessage, setTradeOfferMessage] = useState('');
  const [tradeOfferBusy, setTradeOfferBusy] = useState(false);
  const [tradeOfferError, setTradeOfferError] = useState('');
  const [appAlert, setAppAlert] = useState(null);
  const [offerActionBusyById, setOfferActionBusyById] = useState({});
  const [offerAcceptedListingById, setOfferAcceptedListingById] = useState({});
  const [shippingAddresses, setShippingAddresses] = useState([]);
  const [profileShippingAddresses, setProfileShippingAddresses] = useState([]);
  const [profileQuiz, setProfileQuiz] = useState(null);
  const [profileSaveBusy, setProfileSaveBusy] = useState(false);
  const [profileSaveMsg, setProfileSaveMsg] = useState('');
  const [profileHydrationRetry, setProfileHydrationRetry] = useState(0);
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const [paymentMsg, setPaymentMsg] = useState('');
  const [selectedSubscriptionPaymentMethodId, setSelectedSubscriptionPaymentMethodId] = useState('');
  const [subscriptionPlan, setSubscriptionPlan] = useState('free');
  const [subscriptionCycle, setSubscriptionCycle] = useState('monthly');
  const [selectedAddressByOffer, setSelectedAddressByOffer] = useState({});
  const [shippingLabelsByOffer, setShippingLabelsByOffer] = useState({});
  const [shippingQuoteByOffer, setShippingQuoteByOffer] = useState({});
  const [shippingBusyByOffer, setShippingBusyByOffer] = useState({});
  const [addressSuggestionsById, setAddressSuggestionsById] = useState({});
  const [addressSuggestBusyById, setAddressSuggestBusyById] = useState({});
  const [pushEnabled, setPushEnabled] = useState(true);
  const [alertPrefs, setAlertPrefs] = useState(DEFAULT_ALERT_PREFS);
  const [alertStateHydrated, setAlertStateHydrated] = useState(false);
  const [notificationPermission, setNotificationPermission] = useState('unknown');
  const [pushToken, setPushToken] = useState('');
  const [likedListingIds, setLikedListingIds] = useState([]);

  const [wizardStep, setWizardStep] = useState(1);
  const [editingListingId, setEditingListingId] = useState('');
  const [editingListing, setEditingListing] = useState(null);
  const [selectedHeroImageIndex, setSelectedHeroImageIndex] = useState(0);
  const [selectedEditHeroImageIndex, setSelectedEditHeroImageIndex] = useState(null);
  const [profileSection, setProfileSection] = useState('account');
  const [images, setImages] = useState([]);
  const [editImageUrls, setEditImageUrls] = useState([]);
  const [category, setCategory] = useState('');
  const [itemTitle, setItemTitle] = useState('');
  const [itemDescription, setItemDescription] = useState('');
  const [userCondition, setUserCondition] = useState('');
  const [itemSize, setItemSize] = useState('');
  const [tradeNotes, setTradeNotes] = useState('');
  const [analysisResult, setAnalysisResult] = useState(null);

  const [loading, setLoading] = useState(false);
  const [marketplaceLoading, setMarketplaceLoading] = useState(false);
  const [closetLoading, setClosetLoading] = useState(false);
  const [marketplaceHasMore, setMarketplaceHasMore] = useState(false);
  const [closetHasMore, setClosetHasMore] = useState(false);
  const [marketplaceNextOffset, setMarketplaceNextOffset] = useState(0);
  const [closetNextOffset, setClosetNextOffset] = useState(0);
  const [marketplacePageLoading, setMarketplacePageLoading] = useState(false);
  const [closetPageLoading, setClosetPageLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const apiClient = useMemo(() => createMobileApiClient({ apiBaseUrl }), [apiBaseUrl]);
  useEffect(() => {
    const count = editImageUrls.length + images.length;
    if (editingListingId) {
      setSelectedEditHeroImageIndex((idx) => {
        if (idx === null) return null;
        return count > 0 ? Math.max(0, Math.min(idx, count - 1)) : null;
      });
    } else {
      setSelectedHeroImageIndex((idx) => (count > 0 ? Math.max(0, Math.min(idx, count - 1)) : 0));
    }
  }, [editingListingId, editImageUrls.length, images.length]);

  const selectedOffer = useMemo(
    () => incomingOffers.find((offer) => offer?.offer_id === selectedOfferId) || null,
    [incomingOffers, selectedOfferId],
  );
  const initializedOfferStateRef = useRef(false);
  const offerStatusMapRef = useRef(new Map());
	  const initializedShippingStateRef = useRef(false);
	  const shippingStatusMapRef = useRef(new Map());
	  const seenServerNotificationIdsRef = useRef(new Set());
	  const registeredPushTokenRef = useRef('');
	  const profileSetupCheckedRef = useRef('');
	  const mainScrollRef = useRef(null);
  const normalizedProfileGender = profileQuiz?.gender === 'male' || profileQuiz?.gender === 'female' || profileQuiz?.gender === 'other'
    ? profileQuiz.gender
    : '';
  const profileApparelSizeOptions = normalizedProfileGender === 'male' ? MALE_APPAREL_SIZE_OPTIONS : FEMALE_APPAREL_SIZE_OPTIONS;
  const profileShoeSizeOptions = normalizedProfileGender === 'male' ? MALE_SHOE_SIZE_OPTIONS : FEMALE_SHOE_SIZE_OPTIONS;
	  const profileCategoryOptions = normalizedProfileGender === 'male'
	    ? PROFILE_CATEGORY_OPTIONS.filter((item) => item !== 'Dresses')
	    : PROFILE_CATEGORY_OPTIONS;
	
	  useEffect(() => {
	    if (!isListingDetailOpen) return;
	    requestAnimationFrame(() => {
	      mainScrollRef.current?.scrollTo?.({ y: 0, animated: false });
	    });
	  }, [isListingDetailOpen, selectedListingSource, selectedListing?.listing_id]);
	
	  useEffect(() => {
	    if (paymentMethods.length === 0) {
	      if (selectedSubscriptionPaymentMethodId) setSelectedSubscriptionPaymentMethodId('');
      return;
    }
    const selectedStillExists = paymentMethods.some((method) => method?.payment_method_id === selectedSubscriptionPaymentMethodId);
    if (selectedStillExists) return;
    const fallback = paymentMethods.find((method) => method?.is_default) || paymentMethods[0];
    setSelectedSubscriptionPaymentMethodId(fallback?.payment_method_id || '');
  }, [paymentMethods, selectedSubscriptionPaymentMethodId]);

	  function openListingDetails(listing, source) {
	    if (!listing) return;
	    const list = source === 'closet' ? myListings : marketplaceListings;
	    const idx = list.findIndex((entry) => String(entry?.listing_id || '') === String(listing?.listing_id || ''));
    setIsListingDetailOpen(true);
    setSelectedListing(listing);
    setSelectedListingSource(source || 'marketplace');
	    setSelectedListingIndex(idx);
	    setFailedDetailImages({});
	    requestAnimationFrame(() => {
	      mainScrollRef.current?.scrollTo?.({ y: 0, animated: false });
	    });
	  }

  function closeListingDetails() {
    setIsListingDetailOpen(false);
    setSelectedListing(null);
    setSelectedListingSource(null);
    setSelectedListingIndex(-1);
    setSelectedGalleryImage(null);
    setFailedDetailImages({});
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

  function profileSetupSectionFor(profile = profileQuiz, availablePaymentMethods = paymentMethods) {
    const firstName = String(profile?.first_name || profile?.firstName || '').trim();
    const lastName = String(profile?.last_name || profile?.lastName || '').trim();
    const email = String(profile?.email || '').trim();
    const birthday = String(profile?.birthday || '').trim();
    const gender = String(profile?.gender || '').trim();
    const completeAddresses = completeShippingAddresses(normalizeProfileShippingAddresses(profile?.shipping_addresses, profile));
    const hasSizes = normalizeMultiSizeValue(profile?.tops_size).length > 0
      || normalizeMultiSizeValue(profile?.dresses_size).length > 0
      || normalizeMultiSizeValue(profile?.bottoms_size).length > 0
      || normalizeMultiSizeValue(profile?.shoes_size).length > 0;
    const hasStyle = Array.isArray(profile?.style_descriptors) && profile.style_descriptors.length > 0;
    const hasGoal = Array.isArray(profile?.jouft_goals) && profile.jouft_goals.length > 0;
    const plan = String(profile?.subscription_plan || '').trim().toLowerCase();
    const status = String(profile?.subscription_status || '').trim().toLowerCase();
    const hasSubscription = plan === 'free' || ['active', 'trialing'].includes(status);

    if (!firstName || !lastName || !email || !birthday) return 'account';
    if (!gender || !hasSizes || !hasStyle || !hasGoal) return 'style';
    if (completeAddresses.length === 0) return 'shipping';
    if (!hasSubscription && availablePaymentMethods.length === 0) return 'payments';
    if (!hasSubscription) return 'subscription';
    return '';
  }

  async function loadMarketplace() {
    setLoading(true);
    setMarketplaceLoading(true);
    setError('');
    try {
      const payload = await apiClient.listMarketplace(LISTINGS_PAGE_SIZE, await authContext(), { offset: 0 });
      setMarketplaceListings(Array.isArray(payload?.items) ? payload.items : []);
      setMarketplaceActorSubject(String(payload?.actor?.subject || ''));
      setMarketplaceHasMore(Boolean(payload?.has_more));
      setMarketplaceNextOffset(Number.isFinite(Number(payload?.next_offset)) ? Number(payload.next_offset) : 0);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
      setMarketplaceLoading(false);
    }
  }

  function isOwnMarketplaceListing(item) {
    const ownerSubject = String(item?.owner_subject || '');
    return Boolean(ownerSubject && marketplaceActorSubject && ownerSubject === marketplaceActorSubject);
  }

  async function loadCloset() {
    setLoading(true);
    setClosetLoading(true);
    setError('');
    try {
      const payload = await apiClient.listMyListings(LISTINGS_PAGE_SIZE, await authContext(), { offset: 0 });
      setMyListings(Array.isArray(payload?.items) ? payload.items : []);
      setClosetHasMore(Boolean(payload?.has_more));
      setClosetNextOffset(Number.isFinite(Number(payload?.next_offset)) ? Number(payload.next_offset) : 0);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
      setClosetLoading(false);
    }
  }

  async function loadMoreMarketplace() {
    if (marketplaceLoading || marketplacePageLoading || !marketplaceHasMore) return;
    setMarketplacePageLoading(true);
    try {
      const payload = await apiClient.listMarketplace(LISTINGS_PAGE_SIZE, await authContext(), { offset: marketplaceNextOffset });
      const nextItems = Array.isArray(payload?.items) ? payload.items : [];
      setMarketplaceListings((prev) => {
        const seen = new Set(prev.map((item) => String(item?.listing_id || item?.id || '')));
        return [...prev, ...nextItems.filter((item) => {
          const id = String(item?.listing_id || item?.id || '');
          if (!id || seen.has(id)) return false;
          seen.add(id);
          return true;
        })];
      });
      setMarketplaceHasMore(Boolean(payload?.has_more));
      setMarketplaceNextOffset(Number.isFinite(Number(payload?.next_offset)) ? Number(payload.next_offset) : 0);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setMarketplacePageLoading(false);
    }
  }

  async function loadMoreCloset() {
    if (closetLoading || closetPageLoading || !closetHasMore) return;
    setClosetPageLoading(true);
    try {
      const payload = await apiClient.listMyListings(LISTINGS_PAGE_SIZE, await authContext(), { offset: closetNextOffset });
      const nextItems = Array.isArray(payload?.items) ? payload.items : [];
      setMyListings((prev) => {
        const seen = new Set(prev.map((item) => String(item?.listing_id || item?.id || '')));
        return [...prev, ...nextItems.filter((item) => {
          const id = String(item?.listing_id || item?.id || '');
          if (!id || seen.has(id)) return false;
          seen.add(id);
          return true;
        })];
      });
      setClosetHasMore(Boolean(payload?.has_more));
      setClosetNextOffset(Number.isFinite(Number(payload?.next_offset)) ? Number(payload.next_offset) : 0);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setClosetPageLoading(false);
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
      const auth = await authContext();
      if (clerkEnabled && !auth?.bearerToken) throw new Error('Authentication token unavailable.');
      const profile = await apiClient.fetchProfileQuiz(auth);
      setProfileQuiz(normalizeProfileQuiz({
        ...(profile || {}),
        first_name: profile?.first_name || clerkUserProfile?.firstName || '',
        last_name: profile?.last_name || clerkUserProfile?.lastName || '',
        email: profile?.email || clerkUserProfile?.email || '',
        shipping_email: profile?.shipping_email || profile?.email || clerkUserProfile?.email || '',
        shipping_phone: profile?.shipping_phone || '',
      }));
      setSubscriptionPlan(normalizeSelectableSubscriptionPlan(profile?.subscription_plan));
      setSubscriptionCycle(String(profile?.subscription_billing_cycle || 'monthly'));
      const normalized = normalizeShippingAddresses(profile?.shipping_addresses, profile);
      const editable = normalizeProfileShippingAddresses(profile?.shipping_addresses, profile);
      setShippingAddresses(normalized);
      setProfileShippingAddresses(editable);
      return normalized;
    } catch (e) {
      if (profileHydrationRetry < 5) {
        setTimeout(() => setProfileHydrationRetry((count) => count + 1), 750);
      }
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

  async function reloadProfileTabAfterSave(message = '') {
    setActiveTab('profile');
    requestAnimationFrame(() => {
      mainScrollRef.current?.scrollTo?.({ y: 0, animated: false });
    });
    await loadProfileAddresses();
    await loadPaymentMethods();
    if (message) setProfileSaveMsg(message);
  }

  useEffect(() => {
    if (!authReady()) return;
    const profileKey = String(clerkUserProfile?.id || clerkUserProfile?.email || bearerToken || apiKey || 'anonymous');
    if (profileSetupCheckedRef.current === profileKey) return;
    profileSetupCheckedRef.current = profileKey;
    let cancelled = false;
    (async () => {
      const auth = await authContext();
      if (cancelled) return;
      const profile = await apiClient.fetchProfileQuiz(auth);
      if (cancelled) return;
      const normalized = normalizeProfileQuiz({
        ...(profile || {}),
        first_name: profile?.first_name || clerkUserProfile?.firstName || '',
        last_name: profile?.last_name || clerkUserProfile?.lastName || '',
        email: profile?.email || clerkUserProfile?.email || '',
        shipping_email: profile?.shipping_email || profile?.email || clerkUserProfile?.email || '',
        shipping_phone: profile?.shipping_phone || '',
      });
      setProfileQuiz(normalized);
      let loadedPaymentMethods = paymentMethods;
      try {
        const paymentPayload = await apiClient.paymentMethods(auth);
        if (cancelled) return;
        loadedPaymentMethods = Array.isArray(paymentPayload?.items) ? paymentPayload.items : [];
        setPaymentMethods(loadedPaymentMethods);
      } catch (e) {
        loadedPaymentMethods = [];
        setPaymentMethods([]);
      }
      const requiredProfileSection = profileSetupSectionFor(normalized, loadedPaymentMethods);
      if (requiredProfileSection) {
        setProfileSection(requiredProfileSection);
        setActiveTab('profile');
      }
    })().catch(() => {
      profileSetupCheckedRef.current = '';
    });
    return () => {
      cancelled = true;
    };
  }, [
    apiClient,
    clerkEnabled,
    authMode,
    bearerToken,
    apiKey,
    clerkUserProfile?.id,
    clerkUserProfile?.firstName,
    clerkUserProfile?.lastName,
    clerkUserProfile?.email,
  ]);

  async function loadShippingLabelsForOffer(offerId) {
    const payload = await apiClient.fetchShippingLabels(offerId, await authContext());
    const shipments = Array.isArray(payload?.shipments) ? payload.shipments : [];
    setShippingLabelsByOffer((prev) => ({ ...prev, [offerId]: shipments }));
    return shipments;
  }

  async function loadShippingQuoteForOffer(offerId) {
    if (!offerId) return null;
    setShippingBusyByOffer((prev) => ({ ...prev, [offerId]: true }));
    setShippingQuoteByOffer((prev) => ({ ...prev, [offerId]: prev[offerId] || { status: 'loading' } }));
    setError('');
    try {
      const quote = await apiClient.fetchShippingQuote(offerId, await authContext());
      setShippingQuoteByOffer((prev) => ({ ...prev, [offerId]: quote }));
      return quote;
    } catch (e) {
      setError(e.message || 'Failed to load shipping quote.');
      return null;
    } finally {
      setShippingBusyByOffer((prev) => ({ ...prev, [offerId]: false }));
    }
  }

  async function createShippingLabelsForOffer(offerId) {
    if (!offerId) return [];
    setShippingBusyByOffer((prev) => ({ ...prev, [offerId]: true }));
    setError('');
    try {
      const quote = shippingQuoteByOffer[offerId] || await apiClient.fetchShippingQuote(offerId, await authContext());
      if (quote) setShippingQuoteByOffer((prev) => ({ ...prev, [offerId]: quote }));
      const payload = await apiClient.createShippingLabels(offerId, quote?.rate_id || null, await authContext());
      const shipments = Array.isArray(payload?.shipments) ? payload.shipments : [];
      setShippingLabelsByOffer((prev) => ({ ...prev, [offerId]: shipments }));
      setNotice('Shipping label created.');
      return shipments;
    } catch (e) {
      setError(e.message || 'Failed to create shipping label.');
      return [];
    } finally {
      setShippingBusyByOffer((prev) => ({ ...prev, [offerId]: false }));
    }
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
      const token = String(tokenResp?.data || '').trim();
      setPushToken(token);
      if (token && registeredPushTokenRef.current !== token && authReady()) {
        try {
          await apiClient.registerPushToken({
            token,
            platform: Platform.OS,
            device_id: Constants.sessionId || DeviceModule?.modelId || DeviceModule?.modelName || null,
          }, await authContext());
          registeredPushTokenRef.current = token;
        } catch (e) {
          // Keep local notification permission state even if backend registration is temporarily unavailable.
        }
      }
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

  function canSendAlert(category) {
    return Boolean(alertPrefs?.[category]);
  }

  function canSendLocalNotification() {
    return Boolean(pushEnabled && notificationPermission === 'granted');
  }

  async function sendCategoryAlert(category, title, body) {
    if (!canSendAlert(category)) return;
    if (category === 'trades') {
      setAppAlert({
        title,
        message: body,
        primaryLabel: 'View Inbox',
        secondaryLabel: 'Dismiss',
        onPrimary: () => {
          setAppAlert(null);
          setActiveTab('inbox');
        },
      });
    } else {
      setNotice(body || title);
    }
    if (canSendLocalNotification()) await sendLocalNotification(title, body);
  }

  function toggleAlertPreference(category) {
    if (!category) return;
    setAlertPrefs((prev) => ({
      ...prev,
      [category]: !prev?.[category],
    }));
  }

  async function toggleLikedListing(item) {
    const listingId = String(item?.listing_id || item?.id || '');
    if (!listingId) return;
    const isLiked = likedListingIds.includes(listingId);
    setLikedListingIds((prev) => (
      prev.includes(listingId) ? prev.filter((id) => id !== listingId) : [...prev, listingId]
    ));
    if (!isLiked) {
      try {
        await apiClient.likeListing(listingId, await authContext());
      } catch (e) {
        // Liked state is still saved locally; notification delivery is best effort.
      }
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

  function toggleProfileLimitedArray(field, value, max) {
    setProfileSaveMsg('');
    setProfileQuiz((prev) => {
      const current = Array.isArray(prev?.[field]) ? prev[field] : [];
      const next = current.includes(value)
        ? current.filter((entry) => entry !== value)
        : [...current, value].slice(0, max);
      return { ...(prev || {}), [field]: next };
    });
  }

  async function loadAddressSuggestionsFor(entry) {
    if (!entry?.id) return;
    const query = String(entry.address_line1 || '').trim();
    if (!query) {
      setProfileSaveMsg('Enter address line 1 before finding suggestions.');
      return;
    }
    setAddressSuggestBusyById((prev) => ({ ...prev, [entry.id]: true }));
    setProfileSaveMsg('');
    try {
      const payload = await apiClient.addressSuggestions(
        {
          q: query,
          city: entry.city || '',
          state: entry.state || '',
          postalCode: entry.postal_code || '',
        },
        await authContext(),
      );
      const suggestions = Array.isArray(payload?.suggestions) ? payload.suggestions.slice(0, 5) : [];
      setAddressSuggestionsById((prev) => ({ ...prev, [entry.id]: suggestions }));
      if (suggestions.length === 0) setProfileSaveMsg('No address suggestions found.');
    } catch (e) {
      setProfileSaveMsg(e.message || 'Failed to load address suggestions.');
    } finally {
      setAddressSuggestBusyById((prev) => ({ ...prev, [entry.id]: false }));
    }
  }

  function applyAddressSuggestion(addressId, suggestion) {
    if (!addressId || !suggestion) return;
    setProfileSaveMsg('');
    setProfileShippingAddresses((prev) => prev.map((entry) => (
      entry.id === addressId
        ? {
          ...entry,
          address_line1: suggestion.street_address || suggestion.address_line1 || entry.address_line1,
          address_line2: suggestion.address_line2 || entry.address_line2,
          city: suggestion.city || entry.city,
          state: suggestion.state || entry.state,
          postal_code: suggestion.postal_code || entry.postal_code,
          country: suggestion.country || entry.country || 'US',
        }
        : entry
    )));
    setAddressSuggestionsById((prev) => ({ ...prev, [addressId]: [] }));
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
    const firstName = String(profileQuiz?.first_name || clerkUserProfile?.firstName || '').trim();
    const lastName = String(profileQuiz?.last_name || clerkUserProfile?.lastName || '').trim();
    const email = String(profileQuiz?.email || clerkUserProfile?.email || '').trim().toLowerCase();
    return {
      first_name: firstName,
      last_name: lastName,
      email,
      shipping_email: String(profileQuiz?.shipping_email || email).trim().toLowerCase() || null,
      shipping_phone: String(profileQuiz?.shipping_phone || '').trim() || null,
      birthday: profileQuiz?.birthday || null,
      gender: profileQuiz?.gender ? profileQuiz.gender : null,
      tops_size: serializeMultiSizeValue(profileQuiz?.tops_size),
      dresses_size: serializeMultiSizeValue(profileQuiz?.dresses_size),
      bottoms_size: serializeMultiSizeValue(profileQuiz?.bottoms_size),
      shoes_size: serializeMultiSizeValue(profileQuiz?.shoes_size),
      category_preferences: Array.isArray(profileQuiz?.category_preferences) ? profileQuiz.category_preferences : [],
      style_descriptors: Array.isArray(profileQuiz?.style_descriptors) ? profileQuiz.style_descriptors : [],
      jouft_goals: Array.isArray(profileQuiz?.jouft_goals) ? profileQuiz.jouft_goals : [],
      shipping_full_name: primary.full_name || null,
      shipping_address_line1: primary.address_line1 || null,
      shipping_address_line2: primary.address_line2 || null,
      shipping_city: primary.city || null,
      shipping_state: primary.state || null,
      shipping_postal_code: primary.postal_code || null,
      shipping_country: primary.country || null,
      shipping_addresses: ensuredDefault,
      subscription_plan: normalizeSelectableSubscriptionPlan(subscriptionPlanOverride ?? profileQuiz?.subscription_plan ?? subscriptionPlan),
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
      setProfileQuiz(normalizeProfileQuiz(saved));
      setSubscriptionPlan(normalizeSelectableSubscriptionPlan(saved?.subscription_plan));
      setSubscriptionCycle(String(saved?.subscription_billing_cycle || 'monthly'));
      const normalized = normalizeShippingAddresses(saved?.shipping_addresses, saved);
      const editable = normalizeProfileShippingAddresses(saved?.shipping_addresses, saved);
      setShippingAddresses(normalized);
      setProfileShippingAddresses(editable);
      await reloadProfileTabAfterSave('Shipping addresses saved.');
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
      setProfileQuiz(normalizeProfileQuiz(saved));
      await reloadProfileTabAfterSave('Profile saved.');
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
    const selectedPlan = SUBSCRIPTION_PLANS.find((entry) => entry.key === plan);
    if (!selectedPlan) {
      setProfileSaveMsg('Select a subscription plan to start.');
      setSubscriptionPlan('free');
      return;
    }
    const amount = cycle === 'annual' ? Number(selectedPlan?.annual || 0) : Number(selectedPlan?.monthly || 0);
    const selectedPaymentMethod = paymentMethods.find((method) => method?.payment_method_id === selectedSubscriptionPaymentMethodId)
      || paymentMethods.find((method) => method?.is_default)
      || paymentMethods[0]
      || null;
    if (amount > 0 && paymentMethods.length === 0) {
      setProfileSaveMsg('Add a payment method before activating a paid plan.');
      setProfileSection('payments');
      setPaymentMsg('Add a payment method before activating a paid plan.');
      return;
    }
    if (amount > 0) {
      const confirmed = await confirmSubscriptionActivation({
        planLabel: selectedPlan?.label || titleCase(plan),
        amount,
        cycle,
        paymentMethod: selectedPaymentMethod,
      });
      if (!confirmed) {
        setProfileSaveMsg('Subscription activation canceled.');
        return;
      }
    }
    setProfileSaveBusy(true);
    setProfileSaveMsg('');
    setError('');
    try {
      const activated = await apiClient.activateSubscription({
        plan,
        billing_cycle: cycle,
        payment_method_id: amount > 0 ? selectedPaymentMethod?.payment_method_id : null,
      }, await authContext());
      setProfileQuiz((prev) => normalizeProfileQuiz({
        ...(prev || {}),
        owner_subject: activated?.owner_subject || prev?.owner_subject || '',
        subscription_plan: activated?.plan || plan || 'free',
        subscription_billing_cycle: activated?.billing_cycle || cycle || 'monthly',
        subscription_status: activated?.status || null,
        subscription_renewal_date: activated?.renewal_date || null,
      }));
      setSubscriptionPlan(normalizeSelectableSubscriptionPlan(activated?.plan || plan));
      setSubscriptionCycle(String(activated?.billing_cycle || cycle || 'monthly'));
      setProfileSaveMsg(activated?.message || 'Subscription active.');
    } catch (e) {
      const message = e.message || 'Failed to activate subscription.';
      if (message.toLowerCase().includes('payment method')) {
        setProfileSection('payments');
        setPaymentMsg(message);
      } else {
        setError(message);
      }
    } finally {
      setProfileSaveBusy(false);
    }
  }

  function confirmSubscriptionActivation({ planLabel, amount, cycle, paymentMethod }) {
    const paymentLabel = paymentMethod?.label
      || [paymentMethod?.brand, paymentMethod?.last4 ? `•••• ${paymentMethod.last4}` : ''].filter(Boolean).join(' ')
      || 'Default payment method';
    const amountLabel = `$${amount}${cycle === 'annual' ? ' / year' : ' / month'}`;
    return new Promise((resolve) => {
      Alert.alert(
        'Confirm subscription',
        `Plan: ${planLabel}\nAmount: ${amountLabel}\nPayment: ${paymentLabel}`,
        [
          { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
          { text: 'Activate', style: 'default', onPress: () => resolve(true) },
        ],
      );
    });
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
      const setup = await apiClient.createSetupIntent(await authContext());
      if (setup?.status === 'disabled') {
        setPaymentMsg(setup?.message || 'Stripe is not configured on server.');
        return;
      }
      const publishableKey = String(setup?.publishable_key || '').trim();
      const setupIntentClientSecret = String(setup?.client_secret || '').trim();
      if (!publishableKey || !setupIntentClientSecret) {
        setPaymentMsg('Unable to start Stripe setup right now.');
        return;
      }
      let stripeNative;
      try {
        stripeNative = require('@stripe/stripe-react-native');
      } catch (stripeLoadError) {
        throw new Error('Stripe native module is not available in this build. Rebuild the mobile app before adding payment methods in-app.');
      }
      const { initStripe, initPaymentSheet, presentPaymentSheet } = stripeNative;
      await initStripe({
        publishableKey,
        merchantIdentifier: 'merchant.com.jouft.app',
        urlScheme: Constants.expoConfig?.scheme || 'com.jouft.app.dev',
      });
      const initResult = await initPaymentSheet({
        merchantDisplayName: 'JOUFT',
        setupIntentClientSecret,
        returnURL: `${Constants.expoConfig?.scheme || 'com.jouft.app.dev'}://stripe-redirect`,
        allowsDelayedPaymentMethods: false,
        primaryButtonLabel: 'Save payment method',
      });
      if (initResult.error) {
        throw new Error(initResult.error.message || 'Failed to initialize Stripe payment sheet.');
      }
      const presentResult = await presentPaymentSheet();
      if (presentResult.error) {
        if (String(presentResult.error.code || '').toLowerCase() === 'canceled') {
          setPaymentMsg('Payment method setup canceled.');
          return;
        }
        throw new Error(presentResult.error.message || 'Payment method setup failed.');
      }
      await handleSyncPaymentMethods();
      setPaymentMsg('Payment method saved.');
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
    const currentAddresses = completeShippingAddresses(shippingAddresses.length > 0 ? shippingAddresses : await loadProfileAddresses());
    if (currentAddresses.length === 0) {
      setTradeOfferError('Add a complete shipping address in Profile before sending a trade offer.');
      return;
    }
    if (!tradeOfferListingIds.length) {
      setTradeOfferError('Select at least one listing to offer.');
      return;
    }
    const selectedOfferListings = tradeOfferCandidates
      .filter((listing) => tradeOfferListingIds.includes(listing?.listing_id));
    const targetValue = Number(tradeComposerTarget?.estimated_value || 0);
    const allWithinBand = targetValue > 0 && selectedOfferListings.every((listing) => Math.abs(Number(listing?.estimated_value || 0) - targetValue) / targetValue <= 0.30);
    if (!allWithinBand) {
      setTradeOfferError(targetValue > 0 ? 'Each offered listing must be within the 30% trade band.' : 'Target listing needs a value before sending an offer.');
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
      setMarketplaceListings((prev) => removeSentOfferMatchesFromListings(prev, tradeComposerTarget.listing_id, tradeOfferListingIds));
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

  function showShippingAddressRequiredAlert(message = 'Add a shipping address to your profile before accepting a trade.') {
    setAppAlert({
      title: 'Shipping Address Required',
      message,
      primaryLabel: 'Go to Profile',
      onPrimary: () => {
        setAppAlert(null);
        setProfileSection('shipping');
        setActiveTab('profile');
      },
      secondaryLabel: 'Cancel',
    });
  }

  function confirmTradeAcceptance(offer, quoteOverride = null, selectedOfferedListing = null) {
    const offeredTitle = selectedOfferedListing?.title || offer?.offered_listing?.title || 'the offered item';
    const targetTitle = offer?.target_listing?.title || 'your item';
    const quote = quoteOverride || shippingQuoteByOffer[offer?.offer_id];
    const shippingCost = quote?.status === 'quoted' && quote?.amount
      ? `${quote.currency || 'USD'} ${quote.amount}`
      : 'unavailable';
    return new Promise((resolve) => {
      setAppAlert({
        title: 'Accept Trade?',
        message: `Accept this trade for ${targetTitle} in exchange for ${offeredTitle}? Shipping cost charged to you: ${shippingCost}.`,
        primaryLabel: 'Accept Trade',
        onPrimary: () => {
          setAppAlert(null);
          resolve(true);
        },
        secondaryLabel: 'Cancel',
        onSecondary: () => resolve(false),
      });
    });
  }

  async function respondToOffer(offerId, status) {
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    const currentOffer = incomingOffers.find((offer) => offer.offer_id === offerId) || null;
    setError('');
    try {
      let receiveAddress = null;
      let selectedOfferedListingId = null;
      if (status === 'accepted') {
        const offeredChoices = Array.isArray(currentOffer?.offered_listings) && currentOffer.offered_listings.length > 0
          ? currentOffer.offered_listings
          : (currentOffer?.offered_listing ? [currentOffer.offered_listing] : []);
        selectedOfferedListingId = offerAcceptedListingById[offerId] || currentOffer?.selected_offered_listing_id || (offeredChoices.length === 1 ? listingIdOf(offeredChoices[0]) : '');
        if (!selectedOfferedListingId || !offeredChoices.some((listing) => listingIdOf(listing) === selectedOfferedListingId)) {
          setError('Select one offered item to accept for this trade.');
          return;
        }
        const currentAddresses = completeShippingAddresses(shippingAddresses.length > 0 ? shippingAddresses : await loadProfileAddresses());
        if (currentAddresses.length === 0) {
          showShippingAddressRequiredAlert('Add shipping address to profile.');
          return;
        }
        const selectedId = selectedAddressByOffer[offerId] || (currentAddresses.length === 1 ? currentAddresses[0].id : '');
        const selected = currentAddresses.find((entry) => entry.id === selectedId) || null;
        if (!selected) {
          showShippingAddressRequiredAlert('Select a shipping address before accepting trade.');
          return;
        }
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
        let acceptanceQuote = shippingQuoteByOffer[offerId] || null;
        if (!acceptanceQuote) {
          acceptanceQuote = await loadShippingQuoteForOffer(offerId);
        }
        const selectedOfferedListing = offeredChoices.find((listing) => listingIdOf(listing) === selectedOfferedListingId) || currentOffer?.offered_listing || null;
        const confirmed = await confirmTradeAcceptance(currentOffer, acceptanceQuote, selectedOfferedListing);
        if (!confirmed) return;
      }

      setOfferActionBusyById((prev) => ({ ...prev, [offerId]: status }));
      setNotice(status === 'accepted' ? 'Accepting trade...' : 'Updating trade offer...');
      const updated = await apiClient.actionOffer(offerId, status, receiveAddress, selectedOfferedListingId, await authContext());
      setIncomingOffers((prev) => prev.map((offer) => (offer.offer_id === offerId ? { ...offer, ...updated } : offer)));
      if (String(updated?.status || '').toLowerCase() === 'accepted') {
        await loadShippingLabelsForOffer(offerId);
        setOfferFilter('accepted');
        setNotice('Trade accepted successfully. This trade is now in Accepted.');
      } else if (status === 'accepted') {
        setOfferFilter('accepted');
        setNotice('Offer accepted. Waiting for finalization.');
      } else {
        setNotice('Offer updated.');
      }
      await loadInbox(status === 'accepted' ? 'accepted' : offerFilter);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setOfferActionBusyById((prev) => {
        const next = { ...prev };
        delete next[offerId];
        return next;
      });
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
      await WebBrowser.openBrowserAsync(labelUrl, {
        presentationStyle: WebBrowser.WebBrowserPresentationStyle.PAGE_SHEET,
      });
    } catch (e) {
      setError(e.message || 'Unable to open shipping label.');
    }
  }

  async function shareListing(item) {
    try {
      const { shareUrl, imageUrl, title, caption } = buildSharePayload(item);
      const payload = shareUrl
        ? { message: `${caption}\n${shareUrl}`, url: shareUrl, title: title || 'Jouft Listing' }
        : imageUrl
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
    const listingId = String(item?.listing_id || item?.id || '').trim();
    const base = String(apiBaseUrl || API_DEFAULT || '').replace(/\/$/, '');
    const shareUrl = listingId && base ? `${base}/v1/share/listings/${encodeURIComponent(listingId)}` : '';
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
    return { shareUrl, imageUrl, title, caption };
  }

  async function shareListingPinterest(item) {
    try {
      const { shareUrl, imageUrl, caption } = buildSharePayload(item);
      if (shareUrl || imageUrl) {
        const targetUrl = shareUrl || imageUrl;
        const pinterestUrl = `https://www.pinterest.com/pin/create/button/?url=${encodeURIComponent(targetUrl)}${imageUrl ? `&media=${encodeURIComponent(imageUrl)}` : ''}&description=${encodeURIComponent(caption)}`;
        await WebBrowser.openBrowserAsync(pinterestUrl, {
          presentationStyle: WebBrowser.WebBrowserPresentationStyle.PAGE_SHEET,
        });
        return;
      }
      await Share.share(
        { message: shareUrl ? `${caption}\n${shareUrl}` : imageUrl ? `${caption}\n${imageUrl}` : caption },
        { dialogTitle: 'Share to Pinterest' },
      );
    } catch (e) {
      setError(e.message || 'Unable to share to Pinterest.');
    }
  }

  async function shareListingFacebook(item) {
    try {
      const { shareUrl, imageUrl, caption } = buildSharePayload(item);
      if (shareUrl || imageUrl) {
        const targetUrl = shareUrl || imageUrl;
        const sharerUrl = `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(targetUrl)}&quote=${encodeURIComponent(caption)}`;
        await WebBrowser.openBrowserAsync(sharerUrl, {
          presentationStyle: WebBrowser.WebBrowserPresentationStyle.PAGE_SHEET,
        });
        return;
      }
      await Share.share({ message: shareUrl ? `${caption}\n${shareUrl}` : imageUrl ? `${caption}\n${imageUrl}` : caption }, { dialogTitle: 'Share to Facebook' });
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
  }, [
    activeTab,
    marketplaceListings.length,
    myListings.length,
    incomingOffers.length,
    offerFilter,
    clerkEnabled,
    clerkUserProfile?.id,
    authMode,
    bearerToken,
    apiKey,
    apiBaseUrl,
  ]);

  useEffect(() => {
    if (!authReady()) return;
    let cancelled = false;
    setAlertStateHydrated(false);
    async function hydrateClientState() {
      try {
        const state = await apiClient.fetchClientState(await authContext());
        if (cancelled) return;
        setAlertPrefs({ ...DEFAULT_ALERT_PREFS, ...(state?.alert_preferences || {}) });
        const likedIds = Array.isArray(state?.liked_listing_ids) ? state.liked_listing_ids : [];
        setLikedListingIds(likedIds.map((id) => String(id)).filter(Boolean));
      } catch (e) {
        if (cancelled) return;
        setAlertPrefs(DEFAULT_ALERT_PREFS);
        setLikedListingIds([]);
      } finally {
        if (!cancelled) setAlertStateHydrated(true);
      }
    }
    hydrateClientState();
    return () => {
      cancelled = true;
    };
  }, [apiClient, clerkEnabled, authMode, bearerToken, apiKey]);

  useEffect(() => {
    if (!alertStateHydrated) return;
    if (!authReady()) return;
    let cancelled = false;
    async function saveClientState() {
      try {
        const auth = await authContext();
        if (cancelled) return;
        await apiClient.saveClientState(
          {
            alert_preferences: alertPrefs,
            liked_listing_ids: likedListingIds,
          },
          auth,
        );
      } catch (e) {
        // best effort only
      }
    }
    saveClientState();
    return () => {
      cancelled = true;
    };
  }, [apiClient, alertPrefs, likedListingIds, alertStateHydrated]);

  useEffect(() => {
    if (!authReady()) return;
    if (pushEnabled) {
      registerForPushNotifications().catch(() => {});
      return;
    }
    const token = registeredPushTokenRef.current || pushToken;
    if (token) {
      (async () => {
        apiClient.unregisterPushToken(token, await authContext()).catch(() => {});
      })();
      registeredPushTokenRef.current = '';
    }
  }, [clerkEnabled, authMode, bearerToken, apiKey, pushEnabled, pushToken]);

  useEffect(() => {
    if (!authReady()) return;
    if (activeTab !== 'inbox' && activeTab !== 'profile') return;
    loadProfileAddresses();
    if (activeTab === 'profile') loadPaymentMethods();
  }, [
    activeTab,
    profileHydrationRetry,
    clerkEnabled,
    authMode,
    bearerToken,
    apiKey,
    clerkUserProfile?.firstName,
    clerkUserProfile?.lastName,
    clerkUserProfile?.email,
  ]);

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
    if (!authReady()) return;
    if (activeTab !== 'inbox') return;
    const pendingReceivedOfferIds = incomingOffers
      .filter((offer) => String(offer?.status || '').toLowerCase() === 'pending')
      .filter((offer) => {
        const actorSubject = offerActorSubject(offer, marketplaceActorSubject || clerkUserProfile?.id);
        return actorSubject && actorSubject === String(offer?.to_subject || '').trim();
      })
      .map((offer) => offer.offer_id)
      .filter((offerId) => offerId && !shippingQuoteByOffer[offerId]);
    if (pendingReceivedOfferIds.length === 0) return;
    let cancelled = false;
    (async () => {
      for (const offerId of pendingReceivedOfferIds) {
        if (cancelled) return;
        await loadShippingQuoteForOffer(offerId);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeTab, incomingOffers, shippingQuoteByOffer, marketplaceActorSubject, clerkUserProfile?.id]);

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
    if (!authReady()) return;
    let cancelled = false;
    let timer = null;
    async function pollOffersAndNotify() {
      try {
        const payload = await apiClient.incomingOffers('all', 50, await authContext());
        if (cancelled) return;
        const offers = Array.isArray(payload?.items) ? payload.items : [];
        const actorSubject = String(payload?.actor?.subject || marketplaceActorSubject || clerkUserProfile?.id || '').trim();
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
            const isReceivedOffer = Boolean(
              incoming
              && actorSubject
              && String(incoming?.to_subject || '').trim() === actorSubject,
            );
            if (isReceivedOffer) {
              const title = incoming?.target_listing?.title || incoming?.target_listing_id || 'your listing';
              sendCategoryAlert('trades', 'New Trade Offer', `You received a new offer for ${title}.`);
            }
          } else if (prev !== 'accepted' && status === 'accepted') {
            const incoming = offers.find((entry) => String(entry?.offer_id || '') === offerId);
            const title = incoming?.target_listing?.title || incoming?.target_listing_id || 'your listing';
            sendCategoryAlert('trades', 'Trade Accepted', `A trade was accepted for ${title}.`);
          }
        }
        offerStatusMapRef.current = nextMap;

        const nextShippingMap = new Map();
        const acceptedOffers = offers.filter((offer) => String(offer?.status || '').toLowerCase() === 'accepted');
        for (const offer of acceptedOffers) {
          const offerId = String(offer?.offer_id || '');
          if (!offerId) continue;
          try {
            const labelPayload = await apiClient.fetchShippingLabels(offerId, await authContext());
            if (cancelled) return;
            const shipments = Array.isArray(labelPayload?.shipments) ? labelPayload.shipments : [];
            if (shipments.length > 0) {
              setShippingLabelsByOffer((prev) => ({ ...prev, [offerId]: shipments }));
            }
            shipments.forEach((shipment) => {
              const shipmentId = String(shipment?.shipment_id || '');
              if (!shipmentId) return;
              const status = String(shipment?.status || 'pending').toLowerCase();
              const hasLabel = Boolean(String(shipment?.label_url || '').trim());
              const signature = `${status}:${hasLabel ? 'label' : 'no-label'}:${shipment?.tracking_number || ''}`;
              const key = `${offerId}:${shipmentId}`;
              nextShippingMap.set(key, signature);
              if (!initializedShippingStateRef.current) return;
              const prevSignature = shippingStatusMapRef.current.get(key);
              if (!prevSignature) {
                sendCategoryAlert('shipping', 'Shipping Label Ready', 'A shipping label is available for your accepted trade.');
                return;
              }
              if (prevSignature !== signature) {
                const alertTitle = hasLabel ? 'Shipping Updated' : 'Shipment Updated';
                sendCategoryAlert('shipping', alertTitle, `Shipment status is now ${titleCase(status)}.`);
              }
            });
          } catch (e) {
            // silent polling failure for a single offer
          }
        }
        shippingStatusMapRef.current = nextShippingMap;
        initializedShippingStateRef.current = true;
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
  }, [
    apiClient,
    pushEnabled,
    alertPrefs,
    notificationPermission,
    clerkEnabled,
    authMode,
    bearerToken,
    apiKey,
    marketplaceActorSubject,
    clerkUserProfile?.id,
  ]);

  useEffect(() => {
    if (!authReady()) return;
    let cancelled = false;
    let timer = null;
    async function pollServerNotifications() {
      try {
        const payload = await apiClient.listNotifications(50, await authContext());
        if (cancelled) return;
        const items = Array.isArray(payload?.items) ? payload.items : [];
        for (const notification of items.reverse()) {
          const notificationId = String(notification?.notification_id || notification?.id || '');
          if (!notificationId || seenServerNotificationIdsRef.current.has(notificationId)) continue;
          seenServerNotificationIdsRef.current.add(notificationId);
          const type = String(notification?.type || '');
          const category = type === 'listing-liked' ? 'likes' : type.includes('shipping') ? 'shipping' : 'trades';
          await sendCategoryAlert(
            category,
            notification?.title || 'Jouft notification',
            notification?.body || '',
          );
          apiClient.deleteNotification(notificationId, await authContext()).catch(() => {});
        }
      } catch (e) {
        // Background notification polling should not interrupt the current screen.
      }
    }
    pollServerNotifications();
    timer = setInterval(pollServerNotifications, OFFER_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [
    apiClient,
    pushEnabled,
    alertPrefs,
    notificationPermission,
    clerkEnabled,
    authMode,
    bearerToken,
    apiKey,
  ]);

  async function pickImages() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      setError('Photo permission is required.');
      return;
    }
    const existingEditImageCount = editingListingId ? editImageUrls.length + images.length : 0;
    if (editingListingId && existingEditImageCount >= 6) {
      setError('Remove an image before adding another. Listings support up to 6 images.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsMultipleSelection: true,
      quality: 0.9,
      selectionLimit: editingListingId ? Math.max(1, 6 - existingEditImageCount) : 6,
    });
    if (!result.canceled) {
      const selectedAssets = Array.isArray(result.assets) ? result.assets : [];
      if (editingListingId) {
        setImages((prev) => {
          const remaining = Math.max(0, 6 - editImageUrls.length - prev.length);
          return [...prev, ...selectedAssets.slice(0, remaining)];
        });
        setAnalysisResult(null);
        setWizardStep((step) => Math.min(step, 2));
      } else {
        setImages(selectedAssets.slice(0, 6));
        setSelectedHeroImageIndex(0);
      }
      setError('');
    }
  }

  async function nextStep() {
    const isEditing = Boolean(editingListingId);
    const canNext = wizardStep === 1
      ? (isEditing ? true : images.length >= 1 && images.length <= 6)
      : wizardStep === 2 ? Boolean(userCondition) : true;
    if (!canNext) {
      setError(wizardStep === 1 ? 'Upload 1 to 6 images before continuing.' : 'Condition is required.');
      return;
    }
    if (!authReady()) {
      setError(clerkEnabled ? 'Sign in is required.' : (authMode === 'bearer' ? 'Bearer token required.' : 'API key required.'));
      return;
    }
    setWizardStep((s) => Math.min(3, s + 1));
  }

  function prevStep() {
    setError('');
    setWizardStep((s) => Math.max(1, s - 1));
  }

  function listingIdOf(item) {
    return String(item?.listing_id || item?.id || '').trim();
  }

  function resetListingForm() {
    setWizardStep(1);
    setEditingListingId('');
    setEditingListing(null);
    setSelectedHeroImageIndex(0);
    setSelectedEditHeroImageIndex(null);
    setImages([]);
    setEditImageUrls([]);
    setCategory('');
    setItemTitle('');
    setItemDescription('');
    setUserCondition('');
    setItemSize('');
    setTradeNotes('');
    setAnalysisResult(null);
  }

  function moveArrayItemToFront(list, index) {
    const items = Array.isArray(list) ? list.filter(Boolean) : [];
    if (items.length < 2) return items;
    const safeIndex = Math.max(0, Math.min(index, items.length - 1));
    if (safeIndex === 0) return items;
    const next = [...items];
    const [selected] = next.splice(safeIndex, 1);
    return [selected, ...next];
  }

  function orderedCreateImagesForSave() {
    return moveArrayItemToFront(images.slice(0, 6), selectedHeroImageIndex);
  }

  function orderedEditExistingImagesForSave() {
    if (selectedEditHeroImageIndex === null || selectedEditHeroImageIndex >= editImageUrls.length) return persistableImageUrls(editImageUrls);
    return persistableImageUrls(moveArrayItemToFront(editImageUrls, selectedEditHeroImageIndex));
  }

  function orderedEditPendingImagesForSave() {
    if (selectedEditHeroImageIndex === null || selectedEditHeroImageIndex < editImageUrls.length) return images;
    return moveArrayItemToFront(images, selectedEditHeroImageIndex - editImageUrls.length);
  }

  function cancelEditListing() {
    resetListingForm();
    setActiveTab('closet');
    setNotice('');
    setError('');
  }

  function removeEditImageAt(index) {
    setEditImageUrls((prev) => prev.filter((_, entryIndex) => entryIndex !== index));
    setSelectedEditHeroImageIndex((idx) => {
      if (idx === null) return null;
      if (idx === index) return null;
      return Math.max(0, idx - (idx > index ? 1 : 0));
    });
  }

  function removePendingImageAt(index) {
    setImages((prev) => prev.filter((_, entryIndex) => entryIndex !== index));
    if (editingListingId) {
      setSelectedEditHeroImageIndex((idx) => {
        const absoluteIndex = editImageUrls.length + index;
        if (idx === null) return null;
        if (idx === absoluteIndex) return null;
        return Math.max(0, idx - (idx > absoluteIndex ? 1 : 0));
      });
    } else {
      setSelectedHeroImageIndex((idx) => Math.max(0, idx - (idx >= index ? 1 : 0)));
    }
    setAnalysisResult(null);
    if (editingListingId) setWizardStep((step) => Math.min(step, 2));
  }

  function openEditListingDraft(item) {
    const listingId = listingIdOf(item);
    if (!listingId || String(item?.status || '').toLowerCase() === 'analyzing') return;
    const existingImageUrls = listingGallery(item, apiBaseUrl).slice(0, 6);
    setEditingListingId(listingId);
    setEditingListing(item);
    setSelectedEditHeroImageIndex(null);
    setImages([]);
    setEditImageUrls(existingImageUrls);
    setCategory(item?.category || '');
    setItemTitle(item?.title || '');
    setItemDescription(listingDescription(item) || '');
    setUserCondition(item?.condition || '');
    setItemSize(item?.size || '');
    setTradeNotes(item?.wants || '');
    setAnalysisResult(null);
    setWizardStep(2);
    setError('');
    setNotice('Editing listing draft.');
    setActiveTab('editListing');
  }

  function handleTabPress(tab) {
    const requiredProfileSection = profileSetupSectionFor();
    if (requiredProfileSection) {
      setProfileSection(requiredProfileSection);
      setActiveTab('profile');
      if (tab !== 'profile') {
        setNotice('Complete your profile setup and subscription to start.');
      }
      return;
    }
	    if (tab === 'create') {
	      resetListingForm();
	      setNotice('');
	      setError('');
	    }
	    setActiveTab(tab);
	    requestAnimationFrame(() => {
	      mainScrollRef.current?.scrollTo?.({ y: 0, animated: false });
	    });
	  }

  function editSaveRequiresAnalysis() {
    if (!editingListing) return false;
    const originalImages = persistableImageUrls(listingGallery(editingListing, apiBaseUrl));
    const keptImages = orderedEditExistingImagesForSave();
    const imagesChanged = images.length > 0 || !sameStringList(keptImages, originalImages);
    const originalCondition = String(editingListing?.condition || 'n/a').trim();
    const nextCondition = String(userCondition || editingListing?.condition || 'n/a').trim();
    return imagesChanged || nextCondition !== originalCondition;
  }

  async function waitForUploadedListingImages(imageUrls) {
    const urls = persistableImageUrls(imageUrls)
      .map((url) => normalizeImageUrl(url, apiBaseUrl))
      .filter(Boolean);
    if (urls.length < 1) return false;
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const results = await Promise.all(urls.map((url) => Image.prefetch(url).catch(() => false)));
      if (results.every(Boolean)) return true;
      await new Promise((resolve) => setTimeout(resolve, 350));
    }
    return false;
  }

	  function buildListingPayloadForSave({ imageUrls, sourceItemId = null, analysis = null, status = null } = {}) {
	    const resolvedImageUrls = persistableImageUrls(imageUrls || []);
    if (resolvedImageUrls.length < 1) {
      throw new Error(editingListingId ? 'Keep existing images or upload new photos before saving.' : 'Upload 1 to 6 images before creating the listing.');
    }
	    const resolvedAnalysis = analysis || analysisResult || editingListing?.analysis || null;
	    const originalImageUrls = persistableImageUrls(uploadedImageUrlsFromPayload({ uploaded_images: resolvedAnalysis?.uploaded_images || [] }));
	    const existingListedImages = Array.isArray(editingListing?.listed_images)
	      ? editingListing.listed_images
	      : (Array.isArray(editingListing?.listedImages) ? editingListing.listedImages : []);
	    const listedImages = resolvedImageUrls.map((url, idx) => {
	      const existing = existingListedImages.find((entry) => {
	        const display = persistableImageUrls([entry?.d_img || entry?.display_image || entry?.image])[0];
	        return display === url;
	      });
	      if (existing) {
	        const display = persistableImageUrls([existing.d_img || existing.display_image || existing.image])[0] || url;
	        const original = persistableImageUrls([existing.p_img || existing.original_image || existing.source_image])[0] || display;
	        return { p_img: original, d_img: display, is_hero: idx === 0 };
	      }
	      return { p_img: originalImageUrls[idx] || url, d_img: url, is_hero: idx === 0 };
	    });
	    const analysisCategory = resolvedAnalysis?.category || editingListing?.category || category || '';
    const analysisBrand = resolvedAnalysis?.brand?.name || editingListing?.brand || 'unknown';
    const analysisCondition = userCondition || resolvedAnalysis?.user_condition || editingListing?.condition || 'LikeNew';
    const value = Number(resolvedAnalysis?.valuation?.estimated_value ?? editingListing?.estimated_value ?? 0);
    const description = itemDescription.trim();
    return {
      title: itemTitle.trim() || description || (status === 'Analyzing' ? 'New listing' : `${analysisBrand} ${analysisCategory}`.trim()),
      mode: 'trade',
      category: category || analysisCategory,
      brand: analysisBrand,
      condition: analysisCondition,
      size: itemSize || editingListing?.size || null,
      estimated_value: value,
      city: editingListing?.city || 'Your area',
	      image: resolvedImageUrls[0] || null,
	      images: resolvedImageUrls,
	      listed_images: listedImages,
      description,
      wants: tradeNotes.trim() || editingListing?.wants || 'Open to similar-value offers',
      tags: [analysisCondition, analysisBrand].filter(Boolean),
      source_item_id: sourceItemId || resolvedAnalysis?.item_id || editingListing?.source_item_id || null,
      analysis: resolvedAnalysis,
      status: status || editingListing?.status || 'Review',
    };
  }

  async function publishListingToMarketplace(item) {
    const listingId = listingIdOf(item);
    if (!listingId) return;
    const missingMessage = missingPublishFieldsMessage(item);
    if (missingMessage) {
      setError(missingMessage);
      setNotice('');
      return;
    }
    if (String(item?.status || '').toLowerCase() === 'analyzing') {
      setError('Cannot publish while analysis is running.');
      setNotice('');
      return;
    }
    setLoading(true);
    setError('');
    setNotice('');
    try {
      const condition = item?.condition || 'LikeNew';
      const brand = item?.brand || 'unknown';
      await apiClient.updateListing(
        listingId,
        {
          ...item,
          status: 'Active',
          tags: [condition, brand, 'trade'].filter(Boolean),
        },
        await authContext(),
      );
      await loadCloset();
      if (selectedListing && listingIdOf(selectedListing) === listingId) {
        closeListingDetails();
      }
      setNotice('Listing published to Marketplace.');
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  function removeListingFromCloset(item) {
    const listingId = listingIdOf(item);
    if (!listingId) return;
    Alert.alert(
      'Delete listing?',
      `Delete "${item?.title || 'this listing'}" from your closet? This cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            setLoading(true);
            setError('');
            setNotice('');
            try {
              await apiClient.deleteListing(listingId, await authContext());
              setMyListings((prev) => prev.filter((listing) => listingIdOf(listing) !== listingId));
              setMarketplaceListings((prev) => prev.filter((listing) => listingIdOf(listing) !== listingId));
              setNotice('Listing removed from your closet.');
            } catch (e) {
              setError(e.message || String(e));
            } finally {
              setLoading(false);
            }
          },
        },
      ],
    );
  }

  async function publishListing() {
    const isEditing = Boolean(editingListingId);
    const imagesForAnalysis = isEditing
      ? orderedEditPendingImagesForSave().slice(0, Math.max(0, 6 - editImageUrls.length))
      : orderedCreateImagesForSave();
    const existingImages = isEditing ? orderedEditExistingImagesForSave() : [];
    if (!isEditing && (imagesForAnalysis.length < 1 || imagesForAnalysis.length > 6)) {
      setError('Upload 1 to 6 images before creating the listing.');
      return;
    }
    if (!category) {
      setError('Category is required.');
      return;
    }
    if (!userCondition) {
      setError('Condition is required.');
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
      const auth = await authContext();
      const uploaded = imagesForAnalysis.length > 0
        ? await uploadImagesWithDirectFallback({ apiClient, images: imagesForAnalysis, auth })
        : null;
      const uploadedImageUrls = persistableImageUrls(uploadedImageUrlsFromPayload(uploaded));
      if (imagesForAnalysis.length > 0 && uploadedImageUrls.length < 1) {
        throw new Error('Images were uploaded, but no image URLs were returned.');
      }
      if (uploadedImageUrls.length > 0) {
        const uploadedImagesReady = await waitForUploadedListingImages(uploadedImageUrls);
        if (!uploadedImagesReady) {
          throw new Error('Images are still processing. Please retry creating the listing in a few seconds.');
        }
      }
      const imageUrls = isEditing
        ? [...existingImages, ...uploadedImageUrls].slice(0, 6)
        : uploadedImageUrls;
      const orderedImageUrls = isEditing && selectedEditHeroImageIndex !== null && selectedEditHeroImageIndex >= editImageUrls.length && uploadedImageUrls.length > 0
        ? [uploadedImageUrls[0], ...existingImages, ...uploadedImageUrls.slice(1)].slice(0, 6)
        : imageUrls;
      if (imageUrls.length < 1) {
        throw new Error(isEditing ? 'Keep existing images or upload new photos before saving.' : 'Upload 1 to 6 images before creating the listing.');
      }
      const shouldRunAnalysis = isEditing ? editSaveRequiresAnalysis() : true;
      const payload = buildListingPayloadForSave({
        imageUrls: orderedImageUrls,
        sourceItemId: uploaded?.item_id || null,
        analysis: shouldRunAnalysis ? null : undefined,
        status: shouldRunAnalysis ? 'Analyzing' : undefined,
      });
      if (isEditing) {
        const updated = await apiClient.updateListing(editingListingId, payload, await authContext());
        setNotice(shouldRunAnalysis ? 'Listing updated. AI analysis is running in the background.' : `Listing updated (${String(updated.listing_id || editingListingId).slice(0, 8)}...)`);
        if (shouldRunAnalysis) {
          setTimeout(loadCloset, 4000);
          setTimeout(loadCloset, 10000);
        }
      } else {
        const created = await apiClient.createListing(payload, auth);
        setNotice('Listing created. AI analysis is running in the background.');
        setTimeout(loadCloset, 4000);
        setTimeout(loadCloset, 10000);
      }
      await loadCloset();
      resetListingForm();
      setActiveTab('closet');
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  function renderListingDetailContent({ asScreen = false } = {}) {
    if (!selectedListing) return null;
    const gallery = listingGallery(selectedListing, apiBaseUrl);
    const hasMatches = getCrossOwnerMatches(selectedListing, marketplaceActorSubject).length > 0;
    const matchPreviewImages = hasMatches ? getMatchPreviewImages(selectedListing, apiBaseUrl, marketplaceActorSubject) : [];
    const isOwnListing = selectedListingSource === 'marketplace' && isOwnMarketplaceListing(selectedListing);
    const canStartTrade = selectedListingSource !== 'marketplace' || !isOwnListing;
    const description = listingDescription(selectedListing);
    const selectedListingLiked = likedListingIds.includes(String(selectedListing?.listing_id || selectedListing?.id || ''));
    const selectedListingAnalysisFailed = String(selectedListing?.status || '').toLowerCase() === 'analysisfailed';
    const selectedListingStatus = String(selectedListing?.status || '').trim().toLowerCase();
    const canReviewClosetListing = selectedListingSource === 'closet' && !['active', 'analyzing', 'analysisfailed'].includes(selectedListingStatus);
    const body = (
      <>
        <View style={styles.offerDetailPanel}>
          <Text style={styles.offerLaneLabel}>Details</Text>
          <Text style={styles.offerDetailItemMeta}>
            {selectedListing?.brand || 'Unknown'} • {displayConditionLabel(selectedListing?.condition || 'unknown')} • {titleCase(selectedListing?.category || 'listing')}
          </Text>
          <Text style={styles.offerDetailItemMeta}>
            {money(selectedListing?.estimated_value)}
          </Text>
          {selectedListingAnalysisFailed ? (
            <Text style={styles.analysisFailedText}>{ANALYSIS_FAILED_MESSAGE}</Text>
          ) : null}
          {selectedListingSource === 'marketplace' && !isOwnListing ? (
            <TouchableOpacity
              style={[styles.secondaryBtnCompact, styles.likeDetailIconButton, selectedListingLiked && styles.likeDetailButtonActive]}
              onPress={() => toggleLikedListing(selectedListing)}
              accessibilityRole="button"
              accessibilityLabel={selectedListingLiked ? 'Unlike listing' : 'Like listing'}
            >
              <FontAwesome
                name={selectedListingLiked ? 'heart' : 'heart-o'}
                size={22}
                color={selectedListingLiked ? theme.brand : '#4b433a'}
              />
            </TouchableOpacity>
          ) : null}
          {canReviewClosetListing ? (
            <View style={styles.listingDetailActionRow}>
              <TouchableOpacity
                style={styles.secondaryBtnCompact}
                onPress={() => {
                  const listing = selectedListing;
                  closeListingDetails();
                  openEditListingDraft(listing);
                }}
              >
                <Text style={styles.secondaryBtnText}>Edit</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.primaryBtnCompact}
                onPress={() => publishListingToMarketplace(selectedListing)}
              >
                <Text style={styles.primaryBtnText}>Publish</Text>
              </TouchableOpacity>
            </View>
          ) : null}
        </View>

        <View style={styles.offerDetailPanel}>
          <Text style={styles.offerLaneLabel}>Description</Text>
          <Text style={styles.offerDetailMessage}>{description || 'No description provided.'}</Text>
        </View>

        {hasMatches ? (
          <View style={styles.offerDetailPanel}>
            <View style={styles.listingDetailMatchRow}>
              <Text style={styles.offerLaneLabel}>Matched Items</Text>
              {matchPreviewImages.length > 0 ? (
                <View style={styles.matchThumbStrip}>
                  {matchPreviewImages.map((src, idx) => (
                    <Image
                      key={`${selectedListing?.listing_id || 'listing'}-matched-${idx}`}
                      source={{ uri: src }}
                      style={styles.matchThumb}
                    />
                  ))}
                </View>
              ) : (
                <Text style={styles.matchThumbEmpty}>No match images</Text>
              )}
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

        <View style={styles.offerDetailPanel}>
          <Text style={styles.offerLaneLabel}>Gallery</Text>
          {gallery.length > 0 ? (
            <View style={styles.listingDetailGalleryStack}>
              {gallery.map((src, idx) => {
                const failed = Boolean(failedDetailImages[src]);
                return (
                  <TouchableOpacity
                    key={`${selectedListing?.listing_id || 'listing'}-image-${idx}`}
                    activeOpacity={0.88}
                    onPress={() => setSelectedGalleryImage(src)}
                    disabled={failed}
                  >
                    {failed ? (
                      <View style={[styles.listingDetailGalleryImageFull, styles.offerImageFallback]}>
                        <Text style={styles.emptyText}>Image unavailable</Text>
                      </View>
                    ) : (
                      <Image
                        source={{ uri: src }}
                        style={styles.listingDetailGalleryImageFull}
                        onError={() => setFailedDetailImages((prev) => ({ ...prev, [src]: true }))}
                      />
                    )}
                  </TouchableOpacity>
                );
              })}
            </View>
          ) : (
            <View style={[styles.offerDetailHero, styles.offerImageFallback]}>
              <Text style={styles.emptyText}>No image</Text>
            </View>
          )}
        </View>
      </>
    );

    return (
      <View style={asScreen ? styles.listingDetailScreen : styles.offerDetailShell}>
        <View style={styles.offerDetailHead}>
          <View style={styles.offerDetailTitleWrap}>
            <Text style={styles.sectionEyebrow}>Listing Details</Text>
            <Text style={styles.offerDetailTitle} numberOfLines={3}>{selectedListing?.title || 'Listing'}</Text>
          </View>
          <TouchableOpacity style={[styles.secondaryBtnCompact, styles.offerDetailBackButton]} onPress={closeListingDetails} hitSlop={{ top: 10, right: 10, bottom: 10, left: 10 }}>
            <Text style={styles.secondaryBtnText}>{asScreen ? 'Back' : 'Close'}</Text>
          </TouchableOpacity>
        </View>
        {asScreen ? (
          <View style={styles.offerDetailBody}>{body}</View>
        ) : (
          <ScrollView contentContainerStyle={styles.offerDetailBody} keyboardShouldPersistTaps="handled">
            {body}
          </ScrollView>
        )}
      </View>
    );
  }

  const matchedMarketplaceListings = marketplaceListings.filter((item) => (
    String(item?.status || '').trim().toLowerCase() === 'active'
    && getCrossOwnerMatches(item, marketplaceActorSubject).length > 0
  ));

  return (
    <SafeAreaView style={styles.root} edges={['top', 'right', 'bottom', 'left']}>
      <StatusBar style="dark" />
	      <ScrollView
	        ref={mainScrollRef}
	        style={styles.mainScroll}
	        contentContainerStyle={styles.content}
	        keyboardShouldPersistTaps="handled"
	        scrollEventThrottle={250}
	        onScroll={({ nativeEvent }) => {
	          if (activeTab !== 'marketplace' && activeTab !== 'closet') return;
	          const { layoutMeasurement, contentOffset, contentSize } = nativeEvent;
	          const distanceFromBottom = contentSize.height - (layoutMeasurement.height + contentOffset.y);
	          if (distanceFromBottom > 900) return;
	          if (activeTab === 'marketplace') {
	            loadMoreMarketplace();
	          } else if (activeTab === 'closet') {
	            loadMoreCloset();
	          }
	        }}
	        refreshControl={
	          activeTab === 'marketplace' || activeTab === 'closet' ? (
	            <RefreshControl
	              refreshing={activeTab === 'marketplace' ? marketplaceLoading : closetLoading}
	              onRefresh={refreshActiveTab}
	              tintColor={theme.brand}
	              colors={[theme.brand]}
	            />
	          ) : null
	        }
	      >
        <TopBrandHeader />

        {!!error && <Text style={styles.error}>{error}</Text>}
        {!!notice && <Text style={styles.notice}>{notice}</Text>}
        {loading && !marketplaceLoading && !closetLoading && <ActivityIndicator style={{ marginTop: 8 }} color={theme.brand} />}

        {activeTab === 'marketplace' && (
          <View style={styles.section}>
            {isListingDetailOpen && selectedListingSource === 'marketplace' && selectedListing ? (
              renderListingDetailContent({ asScreen: true })
            ) : (
              <>
                <SectionHeader title="Marketplace" subtitle="CURATED MATCHES" rightText="Refresh" onRightPress={refreshActiveTab} />
	                {marketplaceLoading && matchedMarketplaceListings.length === 0 ? (
                  <View style={styles.loadingState}>
                    <ActivityIndicator color={theme.brand} />
                    <Text style={styles.loadingText}>Loading marketplace listings...</Text>
                  </View>
                ) : matchedMarketplaceListings.length === 0 && !marketplaceHasMore ? (
                  <View style={styles.emptyState}>
                    <Text style={styles.emptyTitle}>No matched marketplace listings yet</Text>
                    <Text style={styles.emptyText}>Create or publish a closet listing to see marketplace items that match your closet.</Text>
                    <TouchableOpacity
                      style={styles.primaryBtn}
                      onPress={() => {
                        resetListingForm();
                        setActiveTab('create');
                      }}
                    >
                      <Text style={styles.primaryBtnText}>Create Listing</Text>
                    </TouchableOpacity>
                  </View>
                ) : matchedMarketplaceListings.length === 0 ? (
                  <View style={styles.emptyState}>
                    <Text style={styles.emptyTitle}>Looking for matched listings...</Text>
                    <Text style={styles.emptyText}>More marketplace listings are available to check.</Text>
                    <TouchableOpacity
                      style={[styles.secondaryBtnCompact, styles.loadMoreButton, marketplacePageLoading && styles.primaryBtnDisabled]}
                      onPress={loadMoreMarketplace}
                      disabled={marketplacePageLoading}
                    >
                      {marketplacePageLoading ? <ActivityIndicator color={theme.brand} /> : <Text style={styles.secondaryBtnText}>Load More Listings</Text>}
                    </TouchableOpacity>
                  </View>
                ) : (
                  matchedMarketplaceListings.map((item) => {
                    const isOwnListing = isOwnMarketplaceListing(item);
                    return (
                      <ListingCard
                        key={item.listing_id}
                        item={item}
                        apiBaseUrl={apiBaseUrl}
                        showMatches
                        showStatus={false}
                        currentOwnerSubject={marketplaceActorSubject}
                        currentUserDisplayName={clerkUserLabel}
                        onStartTrade={openTradeComposer}
                        startTradeDisabled={isOwnListing}
                        onOpenDetails={(listing) => openListingDetails(listing, 'marketplace')}
                        liked={likedListingIds.includes(String(item?.listing_id || item?.id || ''))}
                        onToggleLike={isOwnListing ? null : toggleLikedListing}
                      />
                    );
                  }).concat(marketplaceHasMore ? [
                    <TouchableOpacity
                      key="marketplace-load-more"
                      style={[styles.secondaryBtnCompact, styles.loadMoreButton, marketplacePageLoading && styles.primaryBtnDisabled]}
                      onPress={loadMoreMarketplace}
                      disabled={marketplacePageLoading}
                    >
                      {marketplacePageLoading ? <ActivityIndicator color={theme.brand} /> : <Text style={styles.secondaryBtnText}>Load More Listings</Text>}
                    </TouchableOpacity>,
                  ] : [])
                )}
              </>
            )}
          </View>
        )}

        {activeTab === 'closet' && (
          <View style={styles.section}>
            {isListingDetailOpen && selectedListingSource === 'closet' && selectedListing ? (
              renderListingDetailContent({ asScreen: true })
            ) : (
              <>
                <SectionHeader title="My Closet" subtitle="YOUR LISTINGS" rightText="Refresh" onRightPress={refreshActiveTab} />
	                {closetLoading && myListings.length === 0 ? (
                  <View style={styles.loadingState}>
                    <ActivityIndicator color={theme.brand} />
                    <Text style={styles.loadingText}>Loading your closet...</Text>
                  </View>
                ) : myListings.length === 0 ? (
                  <Text style={styles.emptyText}>No closet listings yet.</Text>
                ) : (
                  myListings.map((item) => (
                    <ListingCard
                      key={item.listing_id}
                      item={item}
                      apiBaseUrl={apiBaseUrl}
                      onOpenDetails={(listing) => openListingDetails(listing, 'closet')}
                      onEditDraft={openEditListingDraft}
                      onReviewListing={(listing) => openListingDetails(listing, 'closet')}
                      onPublishListing={publishListingToMarketplace}
                      onRemoveListing={removeListingFromCloset}
                      onShareListing={shareListing}
                      onShareToPinterest={shareListingPinterest}
                      onShareToFacebook={shareListingFacebook}
                      currentOwnerSubject={marketplaceActorSubject}
                      currentUserDisplayName={clerkUserLabel}
                    />
                  )).concat(closetHasMore ? [
                    <TouchableOpacity
                      key="closet-load-more"
                      style={[styles.secondaryBtnCompact, styles.loadMoreButton, closetPageLoading && styles.primaryBtnDisabled]}
                      onPress={loadMoreCloset}
                      disabled={closetPageLoading}
                    >
                      {closetPageLoading ? <ActivityIndicator color={theme.brand} /> : <Text style={styles.secondaryBtnText}>Load More Listings</Text>}
                    </TouchableOpacity>,
                  ] : [])
                )}
              </>
            )}
          </View>
        )}

        {(activeTab === 'create' || activeTab === 'editListing') && (
          <View style={styles.section}>
            <SectionHeader
              title={editingListingId ? 'Edit Listing' : 'Create Listing'}
              subtitle={editingListingId ? 'UPDATE • REVIEW • SAVE' : 'UPLOAD • CONDITION • CREATE'}
              rightText={editingListingId ? 'Cancel Edit' : null}
              onRightPress={editingListingId ? cancelEditListing : null}
            />
            {editingListingId ? (
              <View style={styles.stepRow}>
                {[1, 2, 3].map((step) => (
                  <View key={step} style={[styles.stepPill, wizardStep === step && styles.stepPillActive]}>
                    <Text style={[styles.stepPillText, wizardStep === step && styles.stepPillTextActive]}>{step}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {editingListingId ? (
              <View style={styles.editImagePanel}>
                <Text style={styles.label}>Listing Images ({editImageUrls.length + images.length}/6)</Text>
                <View style={styles.editImageGrid}>
                  {editImageUrls.map((imageUrl, index) => (
                    <View key={`${imageUrl}-${index}`} style={[styles.editImageTile, selectedEditHeroImageIndex === index && styles.editImageTileHero]}>
                      <Image source={{ uri: imageUrl }} style={styles.editImageThumb} resizeMode="cover" />
                      {selectedEditHeroImageIndex === index ? <Text style={styles.editImageHeroBadge}>Hero</Text> : null}
                      <TouchableOpacity style={styles.editImageHeroButton} onPress={() => setSelectedEditHeroImageIndex(index)}>
                        <Text style={styles.editImageHeroButtonText}>{selectedEditHeroImageIndex === index ? 'Hero Image' : 'Set Hero'}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={styles.editImageRemove} onPress={() => removeEditImageAt(index)}>
                        <Text style={styles.editImageRemoveText}>Remove</Text>
                      </TouchableOpacity>
                    </View>
                  ))}
                  {images.map((asset, index) => (
                    <View key={`${asset?.uri || 'pending'}-${index}`} style={[styles.editImageTile, selectedEditHeroImageIndex === editImageUrls.length + index && styles.editImageTileHero]}>
                      <Image source={{ uri: asset.uri }} style={styles.editImageThumb} resizeMode="cover" />
                      <Text style={styles.editImageBadge}>New</Text>
                      {selectedEditHeroImageIndex === editImageUrls.length + index ? <Text style={styles.editImageHeroBadge}>Hero</Text> : null}
                      <TouchableOpacity style={styles.editImageHeroButton} onPress={() => setSelectedEditHeroImageIndex(editImageUrls.length + index)}>
                        <Text style={styles.editImageHeroButtonText}>{selectedEditHeroImageIndex === editImageUrls.length + index ? 'Hero Image' : 'Set Hero'}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={styles.editImageRemove} onPress={() => removePendingImageAt(index)}>
                        <Text style={styles.editImageRemoveText}>Remove</Text>
                      </TouchableOpacity>
                    </View>
                  ))}
                </View>
                <TouchableOpacity
                  style={[styles.secondaryBtn, editImageUrls.length + images.length >= 6 && styles.primaryBtnDisabled]}
                  onPress={pickImages}
                  disabled={editImageUrls.length + images.length >= 6}
                >
                  <Text style={styles.secondaryBtnText}>Add Images</Text>
                </TouchableOpacity>
                <Text style={styles.helperText}>New photos are analyzed before saving. Keep at least one image on the listing.</Text>
              </View>
            ) : null}

            {!editingListingId && (
              <>
                <TouchableOpacity style={styles.primaryBtn} onPress={pickImages}>
                  <Text style={styles.primaryBtnText}>Choose Photos (1-6)</Text>
                </TouchableOpacity>
                <Text style={styles.helperText}>Selected: {images.length}</Text>
                {images.length > 0 ? (
                  <View style={styles.editImageGrid}>
                    {images.map((asset, index) => (
                      <View key={`${asset?.uri || 'pending'}-${index}`} style={[styles.editImageTile, selectedHeroImageIndex === index && styles.editImageTileHero]}>
                        <Image source={{ uri: asset.uri }} style={styles.editImageThumb} resizeMode="cover" />
                        {selectedHeroImageIndex === index ? <Text style={styles.editImageHeroBadge}>Hero</Text> : null}
                        <TouchableOpacity style={styles.editImageHeroButton} onPress={() => setSelectedHeroImageIndex(index)}>
                          <Text style={styles.editImageHeroButtonText}>Set Hero</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.editImageRemove} onPress={() => removePendingImageAt(index)}>
                          <Text style={styles.editImageRemoveText}>Remove</Text>
                        </TouchableOpacity>
                      </View>
                    ))}
                  </View>
                ) : null}
                <Text style={styles.label}>Category</Text>
                <View style={styles.modeRow}>
                  {[
                    { key: 'clothes', label: 'Clothes' },
                    { key: 'shoes', label: 'Shoes' },
                    { key: 'handbag', label: 'Handbag' },
                    { key: 'accessories', label: 'Accessories' },
                  ].map((option) => {
                    const selected = category === option.key;
                    return (
                      <TouchableOpacity
                        key={`create-category-${option.key}`}
                        style={[styles.modeBtn, selected && styles.modeBtnActive]}
                        onPress={() => {
                          setCategory(option.key);
                          if (itemSize && !sizeOptionsForCategory(option.key).includes(itemSize)) setItemSize('');
                        }}
                      >
                        <Text style={[styles.modeBtnText, selected && styles.modeBtnTextActive]}>{option.label}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
                <Text style={styles.label}>Condition</Text>
                <View style={styles.modeRow}>
                  {['NewWithTags', 'New', 'LikeNew'].map((condition) => (
                    <TouchableOpacity
                      key={condition}
                      style={[styles.modeBtn, userCondition === condition && styles.modeBtnActive]}
                      onPress={() => setUserCondition(condition)}
                    >
                      <Text style={[styles.modeBtnText, userCondition === condition && styles.modeBtnTextActive]}>
                        {condition === 'NewWithTags' ? 'New with Tags' : condition === 'LikeNew' ? 'Like New' : condition}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={styles.label}>Size</Text>
                {(() => {
                  const baseOptions = sizeOptionsForCategory(category);
                  if (baseOptions.length === 0) {
                    return <Text style={styles.helperText}>Select category first.</Text>;
                  }
                  return (
                    <View style={styles.tagChipRow}>
                      {baseOptions.map((size) => {
                        const selected = itemSize === size;
                        return (
                          <TouchableOpacity
                            key={`create-size-${size}`}
                            style={[styles.tagChip, selected && styles.tagChipActive]}
                            onPress={() => setItemSize(size)}
                          >
                            <Text style={[styles.tagChipText, selected && styles.tagChipTextActive]}>{size}</Text>
                          </TouchableOpacity>
                        );
                      })}
                      {itemSize ? (
                        <TouchableOpacity style={styles.tagChip} onPress={() => setItemSize('')}>
                          <Text style={styles.tagChipText}>Clear</Text>
                        </TouchableOpacity>
                      ) : null}
                    </View>
                  );
                })()}
              </>
            )}

            {wizardStep === 2 && editingListingId && (
              <>
                <Text style={styles.label}>Category</Text>
                <TextInput value={category} onChangeText={setCategory} style={styles.input} placeholder="clothes / shoes / handbag / accessories" />
                <Text style={styles.label}>Title</Text>
                <TextInput value={itemTitle} onChangeText={setItemTitle} style={[styles.input, styles.multiInput]} multiline />
                <Text style={styles.label}>Description</Text>
                <TextInput value={itemDescription} onChangeText={setItemDescription} style={[styles.input, styles.multiInput]} multiline />
                <Text style={styles.label}>Condition</Text>
                <View style={styles.modeRow}>
                  {['NewWithTags', 'New', 'LikeNew'].map((condition) => (
                    <TouchableOpacity
                      key={condition}
                      style={[styles.modeBtn, userCondition === condition && styles.modeBtnActive]}
                      onPress={() => setUserCondition(condition)}
                    >
                      <Text style={[styles.modeBtnText, userCondition === condition && styles.modeBtnTextActive]}>
                        {condition === 'NewWithTags' ? 'New with Tags' : condition === 'LikeNew' ? 'Like New' : condition}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={styles.label}>Size</Text>
                {(() => {
                  const categoryForSize = category || editingListing?.analysis?.category || editingListing?.category || '';
                  const brandForSize = editingListing?.analysis?.brand?.name || editingListing?.brand || analysisResult?.brand?.name || '';
                  const sizeChartUrl = brandSizeChartUrl(brandForSize, categoryForSize);
                  const baseOptions = sizeOptionsForCategory(categoryForSize);
                  const normalizedCurrentSize = String(itemSize || '').trim();
                  const sizeOptions = normalizedCurrentSize && !baseOptions.includes(normalizedCurrentSize)
                    ? [...baseOptions, normalizedCurrentSize]
                    : baseOptions;
                  if (sizeOptions.length === 0) {
                    return <Text style={styles.helperText}>Select category first.</Text>;
                  }
                  return (
                    <View style={styles.tagChipRow}>
                      {sizeOptions.map((size) => {
                        const selected = itemSize === size;
                        return (
                          <TouchableOpacity
                            key={`listing-size-${size}`}
                            style={[styles.tagChip, selected && styles.tagChipActive]}
                            onPress={() => setItemSize(size)}
                          >
                            <Text style={[styles.tagChipText, selected && styles.tagChipTextActive]}>{size}</Text>
                          </TouchableOpacity>
                        );
                      })}
                      {itemSize ? (
                        <TouchableOpacity
                          style={styles.tagChip}
                          onPress={() => setItemSize('')}
                        >
                          <Text style={styles.tagChipText}>Clear</Text>
                        </TouchableOpacity>
                      ) : null}
                      {sizeChartUrl ? (
                        <TouchableOpacity
                          style={[styles.tagChip, styles.sizeChartChip]}
                          onPress={() => Linking.openURL(sizeChartUrl)}
                          accessibilityRole="link"
                          accessibilityLabel={`Open ${brandForSize} size chart`}
                        >
                          <Text style={styles.tagChipText}>Size Chart</Text>
                        </TouchableOpacity>
                      ) : null}
                    </View>
                  );
                })()}
              </>
            )}

            {wizardStep === 3 && editingListingId && (
              <>
                <Text style={styles.label}>Trade notes</Text>
                <TextInput value={tradeNotes} onChangeText={setTradeNotes} style={styles.input} />
              </>
            )}

            <View style={styles.actionRow}>
              {editingListingId && wizardStep > 1 && (
                <TouchableOpacity style={styles.secondaryBtn} onPress={prevStep}>
                  <Text style={styles.secondaryBtnText}>Back</Text>
                </TouchableOpacity>
              )}
              {editingListingId && wizardStep < 3 && (
                <TouchableOpacity style={styles.primaryBtn} onPress={nextStep}>
                  <Text style={styles.primaryBtnText}>Next</Text>
                </TouchableOpacity>
              )}
              {(!editingListingId || wizardStep === 3) && (
                <TouchableOpacity style={[styles.primaryBtn, loading && styles.primaryBtnDisabled]} onPress={publishListing} disabled={loading}>
                  <Text style={styles.primaryBtnText}>{editingListingId ? 'Save Changes' : 'Create Listing'}</Text>
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
                const selectableAddresses = completeShippingAddresses(shippingAddresses);
                const selectedAddressId = selectedAddressByOffer[offerId] || (selectableAddresses.length === 1 ? selectableAddresses[0].id : '');
                const offeredChoices = offerOfferedListings(offer);
                const selectedOfferedListingId = offerAcceptedListingById[offerId] || offer?.selected_offered_listing_id || (offeredChoices.length === 1 ? listingIdOf(offeredChoices[0]) : '');
                const labels = Array.isArray(shippingLabelsByOffer[offerId]) ? shippingLabelsByOffer[offerId] : [];
                const quote = shippingQuoteByOffer[offerId] || null;
                const shippingBusy = Boolean(shippingBusyByOffer[offerId]);
                const offerActionBusy = offerActionBusyById[offerId] || '';
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
                          {selectableAddresses.length === 0 ? (
                            <Text style={styles.helperText}>Add a complete shipping address in Profile.</Text>
                          ) : (
                            selectableAddresses.map((address) => {
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
                        <Text style={styles.label}>Accepted offered item</Text>
                        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.addressRow}>
                          {offeredChoices.length === 0 ? (
                            <Text style={styles.helperText}>No offered items available.</Text>
                          ) : (
                            offeredChoices.map((listing, idx) => {
                              const listingId = listingIdOf(listing);
                              const active = listingId === selectedOfferedListingId;
                              return (
                                <TouchableOpacity
                                  key={`${offerId}-offered-choice-${listingId || idx}`}
                                  style={[styles.addressChip, active && styles.addressChipActive]}
                                  onPress={() => setOfferAcceptedListingById((prev) => ({ ...prev, [offerId]: listingId }))}
                                >
                                  <Text style={[styles.addressChipText, active && styles.addressChipTextActive]} numberOfLines={1}>
                                    {(listing?.title || `Item ${idx + 1}`).toUpperCase()}
                                  </Text>
                                  <Text style={[styles.addressChipSubText, active && styles.addressChipSubTextActive]}>
                                    {money(listing?.estimated_value || 0)}
                                  </Text>
                                </TouchableOpacity>
                              );
                            })
                          )}
                        </ScrollView>
                        <View style={styles.actionRow}>
                          <TouchableOpacity
                            style={[styles.primaryBtn, offerActionBusy && styles.primaryBtnDisabled]}
                            onPress={() => respondToOffer(offerId, 'accepted')}
                            disabled={Boolean(offerActionBusy) || !selectedOfferedListingId}
                          >
                            <Text style={styles.primaryBtnText}>{offerActionBusy === 'accepted' ? 'Accepting...' : 'Accept Trade'}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            style={[styles.secondaryBtn, offerActionBusy && styles.primaryBtnDisabled]}
                            onPress={() => respondToOffer(offerId, 'declined')}
                            disabled={Boolean(offerActionBusy)}
                          >
                            <Text style={styles.secondaryBtnText}>{offerActionBusy === 'declined' ? 'Declining...' : 'Decline'}</Text>
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
                        {quote ? (
                          <Text style={styles.helperText}>
                            Quote: {quote.carrier || 'USPS'} {quote.service_level || ''}{quote.amount ? ` • ${quote.currency || 'USD'} ${quote.amount}` : ''}
                          </Text>
                        ) : null}
                        <View style={styles.actionRow}>
                          <TouchableOpacity
                            style={styles.secondaryBtn}
                            onPress={() => loadShippingQuoteForOffer(offerId)}
                            disabled={shippingBusy}
                          >
                            <Text style={styles.secondaryBtnText}>{shippingBusy ? 'Loading...' : 'Get Shipping Quote'}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            style={[styles.primaryBtn, shippingBusy && styles.primaryBtnDisabled]}
                            onPress={() => createShippingLabelsForOffer(offerId)}
                            disabled={shippingBusy}
                          >
                            <Text style={styles.primaryBtnText}>{shippingBusy ? 'Creating...' : 'Create Label'}</Text>
                          </TouchableOpacity>
                        </View>
                        {labels.length === 0 ? (
                          <Text style={styles.helperText}>No labels yet. Get a quote, then create a label.</Text>
                        ) : (
                          labels.map((shipment) => (
                            <View key={shipment.shipment_id} style={styles.shipmentCard}>
                              <Text style={styles.shipmentTitle}>{shipment.carrier} • {shipment.service_level}</Text>
                              <Text style={styles.shipmentMeta}>Tracking: {shipment.tracking_number || 'pending'}</Text>
                              <Text style={styles.shipmentMeta}>Status: {shipmentTrackingLabel(shipment)}</Text>
                              {shipment.tracking_status_details ? (
                                <Text style={styles.shipmentMeta}>{shipment.tracking_status_details}</Text>
                              ) : null}
                              {shipment.tracking_eta ? (
                                <Text style={styles.shipmentMeta}>Estimated delivery: {shipment.tracking_eta}</Text>
                              ) : null}
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

            {clerkEnabled ? (
              <>
                <Text style={styles.label}>Signed In As</Text>
                <Text style={styles.helperText}>{clerkUserLabel || 'Authenticated user'}</Text>
              </>
            ) : null}

            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
              {[
                { key: 'account', label: 'Account' },
                { key: 'style', label: 'Style' },
                { key: 'shipping', label: 'Shipping' },
                { key: 'subscription', label: 'Plan' },
                { key: 'payments', label: 'Payments' },
                { key: 'legal', label: 'Legal' },
              ].map((section) => {
                const active = profileSection === section.key;
                return (
                  <TouchableOpacity
                    key={section.key}
                    style={[styles.filterButton, active && styles.filterButtonActive]}
                    onPress={() => setProfileSection(section.key)}
                  >
                    <Text style={[styles.filterButtonText, active && styles.filterButtonTextActive]}>{section.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>

            {profileSection === 'account' ? (
              <>
            <View style={styles.profileDivider} />
            <Text style={styles.label}>First Name</Text>
            <TextInput
              value={profileQuiz?.first_name || ''}
              onChangeText={(value) => updateProfileStyleField('first_name', value)}
              style={styles.input}
              placeholder="First name"
              autoCapitalize="words"
            />
            <Text style={styles.label}>Last Name</Text>
            <TextInput
              value={profileQuiz?.last_name || ''}
              onChangeText={(value) => updateProfileStyleField('last_name', value)}
              style={styles.input}
              placeholder="Last name"
              autoCapitalize="words"
            />
            <Text style={styles.label}>Email Address</Text>
            <TextInput
              value={profileQuiz?.email || ''}
              onChangeText={(value) => updateProfileStyleField('email', value)}
              style={styles.input}
              placeholder="email@example.com"
              autoCapitalize="none"
              keyboardType="email-address"
            />
            <Text style={styles.label}>Phone</Text>
            <TextInput
              value={profileQuiz?.shipping_phone || ''}
              onChangeText={(value) => updateProfileStyleField('shipping_phone', value)}
              style={styles.input}
              placeholder="Phone number"
              keyboardType="phone-pad"
            />
            <Text style={styles.label}>Birthday</Text>
            <TextInput
              value={profileQuiz?.birthday || ''}
              onChangeText={(value) => updateProfileStyleField('birthday', value)}
              style={styles.input}
              placeholder="YYYY-MM-DD"
              keyboardType="numbers-and-punctuation"
            />
            {!!profileSaveMsg && <Text style={styles.notice}>{profileSaveMsg}</Text>}
            <TouchableOpacity
              style={[styles.primaryBtn, profileSaveBusy && styles.primaryBtnDisabled]}
              onPress={saveStylePreferences}
              disabled={profileSaveBusy}
            >
              <Text style={styles.primaryBtnText}>{profileSaveBusy ? 'Saving...' : 'Save Account'}</Text>
            </TouchableOpacity>
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
            <View style={styles.alertPreferenceList}>
              {ALERT_CATEGORIES.map((category) => {
                const enabled = Boolean(alertPrefs?.[category.key]);
                return (
                  <View key={category.key} style={styles.alertPreferenceRow}>
                    <Text style={styles.alertPreferenceLabel}>{category.label}</Text>
                    <TouchableOpacity
                      style={[styles.alertToggle, enabled && styles.alertToggleActive]}
                      onPress={() => toggleAlertPreference(category.key)}
                    >
                      <Text style={[styles.alertToggleText, enabled && styles.alertToggleTextActive]}>
                        {enabled ? 'On' : 'Off'}
                      </Text>
                    </TouchableOpacity>
                  </View>
                );
              })}
            </View>
            <TouchableOpacity
              style={styles.secondaryBtn}
              onPress={() => sendLocalNotification('Jouft Notifications', 'Push alerts are active on this device.')}
            >
              <Text style={styles.secondaryBtnText}>Test Notification</Text>
            </TouchableOpacity>
              </>
            ) : null}

            {profileSection === 'style' ? (
              <>
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
            <Text style={styles.label}>Describe Your Style</Text>
            <View style={styles.tagChipRow}>
              {STYLE_DESCRIPTOR_OPTIONS.map((styleOption) => {
                const selected = Array.isArray(profileQuiz?.style_descriptors) && profileQuiz.style_descriptors.includes(styleOption);
                return (
                  <TouchableOpacity
                    key={`style-${styleOption}`}
                    style={[styles.tagChip, selected && styles.tagChipActive]}
                    onPress={() => toggleProfileLimitedArray('style_descriptors', styleOption, 3)}
                  >
                    <Text style={[styles.tagChipText, selected && styles.tagChipTextActive]}>{styleOption}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <Text style={styles.label}>What Brings You to JOUFT?</Text>
            <View style={styles.tagChipRow}>
              {JOUFT_GOAL_OPTIONS.map((goalOption) => {
                const selected = Array.isArray(profileQuiz?.jouft_goals) && profileQuiz.jouft_goals.includes(goalOption);
                return (
                  <TouchableOpacity
                    key={`goal-${goalOption}`}
                    style={[styles.tagChip, selected && styles.tagChipActive]}
                    onPress={() => toggleProfileLimitedArray('jouft_goals', goalOption, 2)}
                  >
                    <Text style={[styles.tagChipText, selected && styles.tagChipTextActive]}>{goalOption}</Text>
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
              </>
            ) : null}

            {profileSection === 'shipping' ? (
              <>
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
                  <TouchableOpacity
                    style={styles.secondaryBtnCompact}
                    onPress={() => loadAddressSuggestionsFor(entry)}
                    disabled={Boolean(addressSuggestBusyById[entry.id])}
                  >
                    <Text style={styles.secondaryBtnText}>
                      {addressSuggestBusyById[entry.id] ? 'Finding...' : 'Find Address Suggestions'}
                    </Text>
                  </TouchableOpacity>
                  {Array.isArray(addressSuggestionsById[entry.id]) && addressSuggestionsById[entry.id].length > 0 ? (
                    <View style={styles.addressSuggestionList}>
                      {addressSuggestionsById[entry.id].map((suggestion, idx) => (
                        <TouchableOpacity
                          key={`${entry.id}-suggestion-${idx}`}
                          style={styles.addressSuggestionCard}
                          onPress={() => applyAddressSuggestion(entry.id, suggestion)}
                        >
                          <Text style={styles.addressSuggestionText}>
                            {suggestion.formatted || [suggestion.street_address, suggestion.city, suggestion.state, suggestion.postal_code].filter(Boolean).join(', ')}
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  ) : null}
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
              </>
            ) : null}

            {profileSection === 'subscription' ? (
              <>
            <View style={styles.profileDivider} />
            <Text style={styles.label}>Subscription</Text>
            <View style={styles.profilePlanList}>
              {SUBSCRIPTION_PLANS.map((plan) => {
                const selected = subscriptionPlan === plan.key;
                const activePlan = String(profileQuiz?.subscription_plan || '') === plan.key
                  && ['active', 'trialing'].includes(String(profileQuiz?.subscription_status || '').toLowerCase());
                const amount = subscriptionCycle === 'annual' ? plan.annual : plan.monthly;
                return (
                  <TouchableOpacity
                    key={plan.key}
                    style={[
                      styles.profilePlanCard,
                      selected && !activePlan && styles.profilePlanCardSelected,
                      activePlan && styles.profilePlanCardActive,
                    ]}
                    onPress={() => {
                      setSubscriptionPlan(plan.key);
                      setProfileSaveMsg('');
                    }}
                  >
                    <View style={styles.profilePlanTitleRow}>
                      <Text style={styles.profilePlanTitle}>{plan.label}</Text>
                      {activePlan ? <Text style={styles.profilePlanActiveBadge}>Active</Text> : null}
                    </View>
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
                onPress={() => {
                  setSubscriptionCycle('monthly');
                  setProfileSaveMsg('');
                }}
              >
                <Text style={[styles.modeBtnText, subscriptionCycle === 'monthly' && styles.modeBtnTextActive]}>Monthly</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modeBtn, subscriptionCycle === 'annual' && styles.modeBtnActive]}
                onPress={() => {
                  setSubscriptionCycle('annual');
                  setProfileSaveMsg('');
                }}
              >
                <Text style={[styles.modeBtnText, subscriptionCycle === 'annual' && styles.modeBtnTextActive]}>Annual (10% Off)</Text>
              </TouchableOpacity>
            </View>
            {(() => {
              const selectedPlan = SUBSCRIPTION_PLANS.find((plan) => plan.key === subscriptionPlan);
              const amount = subscriptionCycle === 'annual' ? Number(selectedPlan?.annual || 0) : Number(selectedPlan?.monthly || 0);
              if (amount <= 0) return null;
              return (
                <>
                  <Text style={styles.label}>Payment Method For This Subscription</Text>
                  {paymentMethods.length === 0 ? (
                    <Text style={styles.helperText}>Add a payment method before activating a paid plan.</Text>
                  ) : (
                    <View style={styles.profilePlanList}>
                      {paymentMethods.map((method) => {
                        const selectedForSubscription = method.payment_method_id === selectedSubscriptionPaymentMethodId;
                        return (
                          <TouchableOpacity
                            key={`subscription-payment-${method.payment_method_id}`}
                            style={[styles.profilePaymentCard, selectedForSubscription && styles.profilePaymentCardSelected]}
                            onPress={() => setSelectedSubscriptionPaymentMethodId(method.payment_method_id)}
                          >
                            <Text style={styles.offerItemTitle}>
                              {method.label || method.brand || method.method_type || 'Payment Method'}
                              {method.is_default ? ' • Default' : ''}
                            </Text>
                            <Text style={styles.offerItemMeta}>
                              {selectedForSubscription ? 'SELECTED FOR SUBSCRIPTION' : 'TAP TO USE FOR SUBSCRIPTION'}
                            </Text>
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  )}
                </>
              );
            })()}
            <Text style={styles.helperText}>
              Current status: {titleCase(profileQuiz?.subscription_status || 'not active')}
              {profileQuiz?.subscription_renewal_date ? ` • Renews ${profileQuiz.subscription_renewal_date}` : ''}
            </Text>
            {!!profileSaveMsg && <Text style={styles.notice}>{profileSaveMsg}</Text>}
            <TouchableOpacity
              style={[styles.primaryBtn, profileSaveBusy && styles.primaryBtnDisabled]}
              onPress={() => saveSubscriptionSettings(subscriptionPlan, subscriptionCycle)}
              disabled={profileSaveBusy}
            >
              <Text style={styles.primaryBtnText}>{profileSaveBusy ? 'Activating...' : (subscriptionPlan === 'free' ? 'Use Free Plan' : 'Activate Subscription')}</Text>
            </TouchableOpacity>
              </>
            ) : null}

            {profileSection === 'payments' ? (
              <>
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
              </>
            ) : null}

            {profileSection === 'legal' ? (
              <>
            <View style={styles.profileDivider} />
            <Text style={styles.label}>Legal & Contact</Text>
            <View style={styles.profileLegalCard}>
              <Text style={styles.offerLaneLabel}>Company Address</Text>
              {CONTACT_ADDRESS_LINES.map((line) => (
                <Text key={line} style={styles.profileLegalText}>{line}</Text>
              ))}
              <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => Linking.openURL(CONTACT_DIRECTIONS_URL)}>
                <Text style={styles.secondaryBtnText}>Get Directions</Text>
              </TouchableOpacity>
            </View>
            <View style={styles.profileLegalCard}>
              <Text style={styles.offerLaneLabel}>Contact Email</Text>
              <TouchableOpacity onPress={() => Linking.openURL(`mailto:${CONTACT_EMAIL}`)}>
                <Text style={styles.profileLegalLink}>{CONTACT_EMAIL}</Text>
              </TouchableOpacity>
            </View>
            <View style={styles.profileLegalActions}>
              <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => Linking.openURL(TERMS_URL)}>
                <Text style={styles.secondaryBtnText}>Terms</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => Linking.openURL(PRIVACY_POLICY_URL)}>
                <Text style={styles.secondaryBtnText}>Privacy Policy</Text>
              </TouchableOpacity>
            </View>
              </>
            ) : null}

            {clerkEnabled && onSignOut ? (
              <View style={styles.profileSignOutFooter}>
                <TouchableOpacity style={styles.secondaryBtn} onPress={onSignOut}>
                  <Text style={styles.secondaryBtnText}>Sign Out</Text>
                </TouchableOpacity>
              </View>
            ) : null}
          </View>
        )}

        {selectedOffer ? (() => {
          const offerId = selectedOffer.offer_id;
          const targetListing = selectedOffer?.target_listing || null;
          const offeredListings = offerOfferedListings(selectedOffer);
          const targetGallery = listingGallery(targetListing, apiBaseUrl);
          const selectableAddresses = completeShippingAddresses(shippingAddresses);
          const selectedAddressId = selectedAddressByOffer[offerId] || (selectableAddresses.length === 1 ? selectableAddresses[0].id : '');
          const selectedOfferedListingId = offerAcceptedListingById[offerId] || selectedOffer?.selected_offered_listing_id || (offeredListings.length === 1 ? listingIdOf(offeredListings[0]) : '');
          const labels = Array.isArray(shippingLabelsByOffer[offerId]) ? shippingLabelsByOffer[offerId] : [];
	          const quote = shippingQuoteByOffer[offerId] || null;
	          const shippingBusy = Boolean(shippingBusyByOffer[offerId]);
	          const offerActionBusy = offerActionBusyById[offerId] || '';
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
                      {targetListing?.brand || 'Unknown'} • {displayConditionLabel(targetListing?.condition || 'unknown')} • {titleCase(targetListing?.category || 'listing')}
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
                              {listing?.brand || 'Unknown'} • {displayConditionLabel(listing?.condition || 'unknown')} • ${Number(listing?.estimated_value || 0).toFixed(0)}
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
                      <Text style={styles.helperText}>
                        Shipping cost to send your item: {
                          quote?.status === 'quoted' && quote?.amount
                            ? `${quote.currency || 'USD'} ${quote.amount} • ${quote.carrier || 'USPS'} ${quote.service_level || ''}`
                            : quote?.status === 'loading'
                              ? 'Calculating...'
                              : 'Unavailable until shipping addresses are complete.'
                        }
                      </Text>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.addressRow}>
                        {selectableAddresses.length === 0 ? (
                          <Text style={styles.helperText}>Add a complete shipping address in Profile.</Text>
                        ) : (
                          selectableAddresses.map((address) => {
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
                      <Text style={styles.label}>Accepted offered item</Text>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.addressRow}>
                        {offeredListings.length === 0 ? (
                          <Text style={styles.helperText}>No offered items available.</Text>
                        ) : (
                          offeredListings.map((listing, idx) => {
                            const listingId = listingIdOf(listing);
                            const active = listingId === selectedOfferedListingId;
                            return (
                              <TouchableOpacity
                                key={`${offerId}-detail-offered-choice-${listingId || idx}`}
                                style={[styles.addressChip, active && styles.addressChipActive]}
                                onPress={() => setOfferAcceptedListingById((prev) => ({ ...prev, [offerId]: listingId }))}
                              >
                                <Text style={[styles.addressChipText, active && styles.addressChipTextActive]} numberOfLines={1}>
                                  {(listing?.title || `Item ${idx + 1}`).toUpperCase()}
                                </Text>
                                <Text style={[styles.addressChipSubText, active && styles.addressChipSubTextActive]}>
                                  {money(listing?.estimated_value || 0)}
                                </Text>
                              </TouchableOpacity>
                            );
                          })
                        )}
                      </ScrollView>
                      <View style={styles.actionRow}>
	                        <TouchableOpacity
	                          style={[styles.primaryBtn, offerActionBusy && styles.primaryBtnDisabled]}
	                          onPress={() => respondToOffer(offerId, 'accepted')}
	                          disabled={Boolean(offerActionBusy) || !selectedOfferedListingId}
	                        >
	                          <Text style={styles.primaryBtnText}>{offerActionBusy === 'accepted' ? 'Accepting...' : 'Accept Trade'}</Text>
	                        </TouchableOpacity>
	                        <TouchableOpacity
	                          style={[styles.secondaryBtn, offerActionBusy && styles.primaryBtnDisabled]}
	                          onPress={() => respondToOffer(offerId, 'declined')}
	                          disabled={Boolean(offerActionBusy)}
	                        >
	                          <Text style={styles.secondaryBtnText}>{offerActionBusy === 'declined' ? 'Declining...' : 'Decline'}</Text>
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
                      {quote ? (
                        <Text style={styles.helperText}>
                          Quote: {quote.carrier || 'USPS'} {quote.service_level || ''}{quote.amount ? ` • ${quote.currency || 'USD'} ${quote.amount}` : ''}
                        </Text>
                      ) : null}
                      <View style={styles.actionRow}>
                        <TouchableOpacity
                          style={styles.secondaryBtn}
                          onPress={() => loadShippingQuoteForOffer(offerId)}
                          disabled={shippingBusy}
                        >
                          <Text style={styles.secondaryBtnText}>{shippingBusy ? 'Loading...' : 'Get Shipping Quote'}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          style={[styles.primaryBtn, shippingBusy && styles.primaryBtnDisabled]}
                          onPress={() => createShippingLabelsForOffer(offerId)}
                          disabled={shippingBusy}
                        >
                          <Text style={styles.primaryBtnText}>{shippingBusy ? 'Creating...' : 'Create Label'}</Text>
                        </TouchableOpacity>
                      </View>
                      {labels.length === 0 ? (
                        <Text style={styles.helperText}>No labels yet. Get a quote, then create a label.</Text>
                      ) : (
                        labels.map((shipment) => (
                          <View key={`${offerId}-${shipment.shipment_id}`} style={styles.shipmentCard}>
                            <Text style={styles.shipmentTitle}>{shipment.carrier} • {shipment.service_level}</Text>
                            <Text style={styles.shipmentMeta}>Tracking: {shipment.tracking_number || 'pending'}</Text>
                            <Text style={styles.shipmentMeta}>Status: {shipmentTrackingLabel(shipment)}</Text>
                            {shipment.tracking_status_details ? (
                              <Text style={styles.shipmentMeta}>{shipment.tracking_status_details}</Text>
                            ) : null}
                            {shipment.tracking_eta ? (
                              <Text style={styles.shipmentMeta}>Estimated delivery: {shipment.tracking_eta}</Text>
                            ) : null}
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

        {tradeComposerTarget ? (() => {
          const targetGallery = listingGallery(tradeComposerTarget, apiBaseUrl);
          const selectedOfferListings = tradeOfferCandidates
            .filter((listing) => tradeOfferListingIds.includes(listing?.listing_id));
          const targetValue = Number(tradeComposerTarget?.estimated_value || 0);
          const withinBand = targetValue > 0 && selectedOfferListings.length > 0
            ? selectedOfferListings.every((listing) => Math.abs(Number(listing?.estimated_value || 0) - targetValue) / targetValue <= 0.30)
            : false;
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
                      {tradeComposerTarget?.brand || 'Unknown'} • {displayConditionLabel(tradeComposerTarget?.condition || 'unknown')} • {money(tradeComposerTarget?.estimated_value)}
                    </Text>
                    <TouchableOpacity
                      style={styles.secondaryBtnCompact}
                      onPress={() => {
                        const target = tradeComposerTarget;
                        closeTradeComposer();
                        openListingDetails(target, 'marketplace');
                      }}
                    >
                      <Text style={styles.secondaryBtnText}>View Details</Text>
                    </TouchableOpacity>
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
                    <Text style={styles.helperText}>
                      Selected choices: {selectedOfferListings.length} • Target: {money(targetValue)}
                    </Text>
                    <Text style={withinBand ? styles.notice : styles.error}>
                      {withinBand ? 'Each selected item is within the 30% trade band' : 'Select at least one item within the 30% trade band'}
                    </Text>
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
                        style={[styles.primaryBtn, (tradeOfferBusy || !withinBand) && styles.primaryBtnDisabled]}
                        onPress={submitTradeOffer}
                        disabled={tradeOfferBusy || !withinBand}
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
      <Modal
        visible={Boolean(appAlert)}
        animationType="fade"
        transparent
        onRequestClose={() => {
          const onSecondary = appAlert?.onSecondary;
          setAppAlert(null);
          if (typeof onSecondary === 'function') onSecondary();
        }}
      >
        <View style={styles.appAlertOverlay}>
          <View style={styles.appAlertCard}>
            <Text style={styles.appAlertEyebrow}>JOUFT</Text>
            <Text style={styles.appAlertTitle}>{appAlert?.title || 'Notice'}</Text>
            <Text style={styles.appAlertMessage}>{appAlert?.message || ''}</Text>
            <View style={styles.appAlertActions}>
              {appAlert?.secondaryLabel ? (
                <TouchableOpacity
                  style={styles.secondaryBtnCompact}
                  onPress={() => {
                    const onSecondary = appAlert?.onSecondary;
                    setAppAlert(null);
                    if (typeof onSecondary === 'function') onSecondary();
                  }}
                >
                  <Text style={styles.secondaryBtnText}>{appAlert.secondaryLabel}</Text>
                </TouchableOpacity>
              ) : null}
              {appAlert?.primaryLabel ? (
                <TouchableOpacity
                  style={styles.primaryBtnCompact}
                  onPress={() => {
                    if (typeof appAlert?.onPrimary === 'function') appAlert.onPrimary();
                    else setAppAlert(null);
                  }}
                >
                  <Text style={styles.primaryBtnText}>{appAlert.primaryLabel}</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          </View>
        </View>
      </Modal>
      <Modal
        visible={Boolean(selectedGalleryImage)}
        animationType="fade"
        transparent={false}
        onRequestClose={() => setSelectedGalleryImage(null)}
      >
        <SafeAreaView style={styles.galleryModalRoot}>
          <View style={styles.galleryModalHeader}>
            <TouchableOpacity
              style={[styles.secondaryBtnCompact, styles.galleryModalCloseButton]}
              onPress={() => setSelectedGalleryImage(null)}
              hitSlop={{ top: 10, right: 10, bottom: 10, left: 10 }}
            >
              <Text style={styles.secondaryBtnText}>Close</Text>
            </TouchableOpacity>
          </View>
          {selectedGalleryImage ? (
            <Image
              source={{ uri: selectedGalleryImage }}
              style={styles.galleryModalImage}
              resizeMode="contain"
            />
          ) : null}
        </SafeAreaView>
      </Modal>
      <View style={styles.tabContainer}>
        {TABS.map((tab) => (
          <AppTabButton key={tab} tab={tab} activeTab={activeTab === 'editListing' ? 'closet' : activeTab} onPress={handleTabPress} />
        ))}
      </View>
    </SafeAreaView>
  );
}

function ClerkAuthScreen() {
  const [authPanelOpen, setAuthPanelOpen] = useState(false);
  const [mode, setMode] = useState('sign_in');
  const [authEntryPoint, setAuthEntryPoint] = useState('sign_in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [pendingSignInVerification, setPendingSignInVerification] = useState(false);
  const [signInVerificationStep, setSignInVerificationStep] = useState('first_email_code');
  const [pendingSignUpVerification, setPendingSignUpVerification] = useState(false);
  const [pendingPasswordReset, setPendingPasswordReset] = useState(false);
  const [busy, setBusy] = useState(false);
  const [oauthBusy, setOauthBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const { isLoaded: signInLoaded, signIn, setActive: setSignInActive } = useSignIn();
  const { isLoaded: signUpLoaded, signUp, setActive: setSignUpActive } = useSignUp();
  const { startOAuthFlow: startFacebookOAuthFlow } = useOAuth({ strategy: 'oauth_facebook' });
  const { startOAuthFlow: startGoogleOAuthFlow } = useOAuth({ strategy: 'oauth_google' });

  function clerkErrorMessage(e, fallback) {
    const message = e?.errors?.[0]?.longMessage || e?.errors?.[0]?.message || e?.message || fallback;
    if (String(message || '').toLowerCase().includes('verification strategy')) {
      return `${message} Enable email code verification in Clerk, or change the mobile flow to match the enabled Clerk verification method.`;
    }
    return message;
  }

  function resetAuthFlow(nextMode) {
    setMode(nextMode);
    setError('');
    setNotice('');
    setVerificationCode('');
    setPassword('');
    setPendingSignInVerification(false);
    setSignInVerificationStep('first_email_code');
    setPendingSignUpVerification(false);
    setPendingPasswordReset(false);
  }

  function openAuth(nextMode) {
    setAuthEntryPoint(nextMode === 'sign_up' ? 'request_access' : 'sign_in');
    resetAuthFlow(nextMode);
    setAuthPanelOpen(true);
  }

  async function submitOAuth(provider) {
    const startOAuthFlow = provider === 'google' ? startGoogleOAuthFlow : startFacebookOAuthFlow;
    const providerLabel = provider === 'google' ? 'Google' : 'Facebook';
    setOauthBusy(provider);
    setError('');
    setNotice('');
    try {
      const { createdSessionId, setActive } = await startOAuthFlow();
      if (createdSessionId && setActive) {
        await setActive({ session: createdSessionId });
        return;
      }
      setNotice(`${providerLabel} sign-in was cancelled or did not complete.`);
    } catch (e) {
      setError(clerkErrorMessage(e, `${providerLabel} sign-in failed.`));
    } finally {
      setOauthBusy('');
    }
  }

  async function prepareSignInSecondFactor(result) {
    const secondFactors = Array.isArray(result?.supportedSecondFactors) ? result.supportedSecondFactors : [];
    const emailCodeFactor = secondFactors.find((factor) => factor?.strategy === 'email_code');
    if (emailCodeFactor?.emailAddressId) {
      await signIn.prepareSecondFactor({
        strategy: 'email_code',
        emailAddressId: emailCodeFactor.emailAddressId,
      });
      setSignInVerificationStep('second_email_code');
      setPendingSignInVerification(true);
      setNotice('Enter the additional sign-in code Clerk sent to your email.');
      return;
    }
    const totpFactor = secondFactors.find((factor) => factor?.strategy === 'totp');
    if (totpFactor) {
      setSignInVerificationStep('second_totp');
      setPendingSignInVerification(true);
      setNotice('Enter the authenticator code for this account.');
      return;
    }
    setError('This account requires another sign-in step that the mobile app does not support yet.');
  }

  async function prepareSignInEmailCode(result) {
    const passwordFactor = (result?.supportedFirstFactors || []).find((factor) => factor?.strategy === 'password');
    if (passwordFactor) {
      if (!password.trim()) {
        setError('Enter your password to sign in.');
        return;
      }
      const passwordResult = await signIn.attemptFirstFactor({
        strategy: 'password',
        password,
      });
      if (passwordResult?.status === 'complete' && passwordResult?.createdSessionId) {
        await setSignInActive({ session: passwordResult.createdSessionId });
        return;
      }
      if (passwordResult?.status === 'needs_second_factor') {
        await prepareSignInSecondFactor(passwordResult);
        return;
      }
      setError('Additional sign-in steps are required for this account.');
      return;
    }

    const emailCodeFactor = (result?.supportedFirstFactors || []).find((factor) => factor?.strategy === 'email_code');
    if (!emailCodeFactor?.emailAddressId) {
      setError('This account needs a sign-in method that the mobile app does not support yet.');
      return;
    }
    await signIn.prepareFirstFactor({
      strategy: 'email_code',
      emailAddressId: emailCodeFactor.emailAddressId,
    });
    setSignInVerificationStep('first_email_code');
    setPendingSignInVerification(true);
    setNotice('Enter the sign-in code Clerk sent to your email.');
  }

  async function submitSignInVerification() {
    if (!signInLoaded) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = signInVerificationStep === 'second_email_code'
        ? await signIn.attemptSecondFactor({
          strategy: 'email_code',
          code: verificationCode.trim(),
        })
        : signInVerificationStep === 'second_totp'
          ? await signIn.attemptSecondFactor({
            strategy: 'totp',
            code: verificationCode.trim(),
          })
          : await signIn.attemptFirstFactor({
            strategy: 'email_code',
            code: verificationCode.trim(),
          });
      if (result?.status === 'complete' && result?.createdSessionId) {
        await setSignInActive({ session: result.createdSessionId });
        return;
      }
      if (result?.status === 'needs_second_factor') {
        await prepareSignInSecondFactor(result);
        return;
      }
      setError('Additional sign-in steps are required for this account.');
    } catch (e) {
      setError(clerkErrorMessage(e, 'Verification failed.'));
    } finally {
      setBusy(false);
    }
  }

  async function submitSignIn() {
    if (!signInLoaded) return;
    if (pendingSignInVerification) {
      await submitSignInVerification();
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const payload = { identifier: email.trim() };
      if (password.trim()) payload.password = password;
      const result = await signIn.create(payload);
      if (result?.status === 'complete' && result?.createdSessionId) {
        await setSignInActive({ session: result.createdSessionId });
        return;
      }
      if (result?.status === 'needs_second_factor') {
        await prepareSignInSecondFactor(result);
        return;
      }
      await prepareSignInEmailCode(result);
    } catch (e) {
      const message = clerkErrorMessage(e, 'Sign in failed.');
      if (String(message || '').toLowerCase().includes('verification strategy')) {
        try {
          const result = await signIn.create({ identifier: email.trim() });
          await prepareSignInEmailCode(result);
        } catch (fallbackError) {
          setError(clerkErrorMessage(fallbackError, 'Sign in failed.'));
        }
      } else {
        setError(message);
      }
    } finally {
      setBusy(false);
    }
  }

  async function submitSignUpVerification() {
    if (!signUpLoaded) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await signUp.attemptEmailAddressVerification({
        code: verificationCode.trim(),
      });
      if (result?.status === 'complete' && result?.createdSessionId) {
        await setSignUpActive({ session: result.createdSessionId });
        return;
      }
      setError('Additional sign-up steps are required for this account.');
    } catch (e) {
      setError(clerkErrorMessage(e, 'Verification failed.'));
    } finally {
      setBusy(false);
    }
  }

  async function submitSignUp() {
    if (!signUpLoaded) return;
    if (pendingSignUpVerification) {
      await submitSignUpVerification();
      return;
    }
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
      await signUp.prepareEmailAddressVerification({ strategy: 'email_code' });
      setPendingSignUpVerification(true);
      setNotice('Enter the verification code Clerk sent to your email.');
    } catch (e) {
      setError(clerkErrorMessage(e, 'Sign up failed.'));
    } finally {
      setBusy(false);
    }
  }

  async function submitPasswordReset() {
    if (!signInLoaded) return;
    const identifier = email.trim();
    if (!identifier) {
      setError('Enter your email address to reset your password.');
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (!pendingPasswordReset) {
        await signIn.create({
          strategy: 'reset_password_email_code',
          identifier,
        });
        setPendingPasswordReset(true);
        setNotice('Clerk sent a password reset code to your email.');
        return;
      }

      const result = await signIn.attemptFirstFactor({
        strategy: 'reset_password_email_code',
        code: verificationCode.trim(),
        password,
      });
      if (result?.status === 'needs_new_password') {
        const resetResult = await signIn.resetPassword({
          password,
          signOutOfOtherSessions: true,
        });
        if (resetResult?.status === 'complete' && resetResult?.createdSessionId) {
          await setSignInActive({ session: resetResult.createdSessionId });
          return;
        }
      }
      if (result?.status === 'complete' && result?.createdSessionId) {
        await setSignInActive({ session: result.createdSessionId });
        return;
      }
      setError('Additional password reset steps are required for this account.');
    } catch (e) {
      setError(clerkErrorMessage(e, 'Password reset failed.'));
    } finally {
      setBusy(false);
    }
  }

  function authTitleForMode() {
    if (mode === 'reset_password') return 'Reset Password';
    if (authEntryPoint === 'request_access') return 'Request Access';
    return mode === 'sign_in' ? 'Sign In' : 'Create Account';
  }

  return (
    <SafeAreaView style={styles.authRoot}>
      <StatusBar style="dark" />
      <ScrollView style={styles.authScroll} contentContainerStyle={styles.authScrollContent}>
        <View style={styles.mobileAuthHero}>
          <View style={styles.mobileAuthTopbar}>
            <Text style={styles.mobileAuthLogo}>JOUFT</Text>
            <Text style={styles.mobileAuthPill}>INVITE ONLY</Text>
          </View>
          <Image
            source={{ uri: 'https://images.unsplash.com/photo-1617038220319-276d3cfab638?auto=format&fit=crop&w=1200&q=80' }}
            style={styles.mobileAuthHeroImage}
          />
          <View style={styles.mobileAuthCopy}>
            <Text style={styles.sectionEyebrow}>TRADE. ELEVATE. BELONG.</Text>
            <Text style={styles.mobileAuthTitle}>The Fashion Trading Platform for Collectors</Text>
            <Text style={styles.mobileAuthText}>
              Trade authentic fashion with a curated community built around style, value, and trust.
            </Text>
            <View style={styles.authHeroActions}>
              <TouchableOpacity style={styles.primaryBtn} onPress={() => openAuth('sign_up')}>
                <Text style={styles.primaryBtnText}>Request Access</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.secondaryBtn} onPress={() => openAuth('sign_in')}>
                <Text style={styles.secondaryBtnText}>Log In</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>

        <View style={styles.authValueStrip}>
          <View style={styles.authValueItem}>
            <Text style={styles.authValueTitle}>Curated Quality</Text>
            <Text style={styles.authValueText}>Discover pieces matched by style and value.</Text>
          </View>
          <View style={styles.authValueItem}>
            <Text style={styles.authValueTitle}>Secure Trades</Text>
            <Text style={styles.authValueText}>Accept offers and manage shipping in one place.</Text>
          </View>
          <View style={styles.authValueItem}>
            <Text style={styles.authValueTitle}>Sustainable Style</Text>
            <Text style={styles.authValueText}>Extend item life while refreshing your closet.</Text>
          </View>
        </View>

        <Modal
          visible={authPanelOpen}
          animationType="slide"
          transparent
          onRequestClose={() => setAuthPanelOpen(false)}
        >
          <View style={styles.authModalOverlay}>
            <ScrollView
              style={styles.authModalScroll}
              contentContainerStyle={styles.authModalContent}
              keyboardShouldPersistTaps="handled"
            >
              <View style={[styles.authCard, styles.authModalCard]}>
                <View style={styles.authPanelHeader}>
                  <View>
                    <Text style={styles.sectionEyebrow}>Jouft Access</Text>
                    <Text style={styles.authTitle}>{authTitleForMode()}</Text>
                  </View>
                  <TouchableOpacity style={styles.secondaryBtnCompact} onPress={() => setAuthPanelOpen(false)}>
                    <Text style={styles.secondaryBtnText}>Close</Text>
                  </TouchableOpacity>
                </View>

                <TouchableOpacity
                  style={[styles.facebookBtn, oauthBusy && styles.primaryBtnDisabled]}
                  onPress={() => submitOAuth('facebook')}
                  disabled={Boolean(oauthBusy)}
                >
                  <Text style={styles.facebookBtnText}>{oauthBusy === 'facebook' ? 'Connecting...' : 'Continue with Facebook'}</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.googleBtn, oauthBusy && styles.primaryBtnDisabled]}
                  onPress={() => submitOAuth('google')}
                  disabled={Boolean(oauthBusy)}
                >
                  <Text style={styles.googleBtnText}>{oauthBusy === 'google' ? 'Connecting...' : 'Continue with Google'}</Text>
                </TouchableOpacity>

                <View style={styles.authDivider}>
                  <View style={styles.authDividerLine} />
                  <Text style={styles.authDividerText}>or</Text>
                  <View style={styles.authDividerLine} />
                </View>

                {authEntryPoint === 'request_access' ? null : (
                  <View style={styles.modeRow}>
                    <TouchableOpacity style={[styles.modeBtn, mode === 'sign_in' && styles.modeBtnActive]} onPress={() => resetAuthFlow('sign_in')}>
                      <Text style={[styles.modeBtnText, mode === 'sign_in' && styles.modeBtnTextActive]}>Sign In</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.modeBtn, mode === 'sign_up' && styles.modeBtnActive]} onPress={() => resetAuthFlow('sign_up')}>
                      <Text style={[styles.modeBtnText, mode === 'sign_up' && styles.modeBtnTextActive]}>Create Account</Text>
                    </TouchableOpacity>
                  </View>
                )}

                <Text style={styles.label}>Email</Text>
                <TextInput
                  value={email}
                  onChangeText={setEmail}
                  style={styles.input}
                  autoCapitalize="none"
                  keyboardType="email-address"
                  editable={!pendingSignInVerification && !pendingSignUpVerification}
                />
                {mode === 'reset_password' ? (
                  <>
                    {pendingPasswordReset ? (
                      <>
                        <Text style={styles.label}>Reset Code</Text>
                        <TextInput value={verificationCode} onChangeText={setVerificationCode} style={styles.input} autoCapitalize="none" keyboardType="number-pad" />
                        <Text style={styles.label}>New Password</Text>
                        <TextInput value={password} onChangeText={setPassword} style={styles.input} secureTextEntry autoCapitalize="none" />
                      </>
                    ) : null}
                  </>
                ) : !pendingSignInVerification && !pendingSignUpVerification ? (
                  <>
                    <Text style={styles.label}>Password</Text>
                    <TextInput value={password} onChangeText={setPassword} style={styles.input} secureTextEntry autoCapitalize="none" />
                    {mode === 'sign_in' ? (
                      <TouchableOpacity style={styles.authLinkButton} onPress={() => resetAuthFlow('reset_password')}>
                        <Text style={styles.authLinkText}>Forgot password?</Text>
                      </TouchableOpacity>
                    ) : null}
                  </>
                ) : (
                  <>
                    <Text style={styles.label}>Verification Code</Text>
                    <TextInput value={verificationCode} onChangeText={setVerificationCode} style={styles.input} autoCapitalize="none" keyboardType="number-pad" />
                  </>
                )}

                {!!error && <Text style={styles.error}>{error}</Text>}
                {!!notice && <Text style={styles.notice}>{notice}</Text>}

                <TouchableOpacity
                  style={[styles.primaryBtn, busy && styles.primaryBtnDisabled]}
                  onPress={mode === 'reset_password' ? submitPasswordReset : (mode === 'sign_in' ? submitSignIn : submitSignUp)}
                  disabled={busy}
                >
                  <Text style={styles.primaryBtnText}>
                    {busy ? 'Please wait...' : (mode === 'reset_password' ? (pendingPasswordReset ? 'Reset Password' : 'Send Reset Code') : ((pendingSignInVerification || pendingSignUpVerification) ? 'Verify Email' : (mode === 'sign_in' ? 'Sign In' : 'Create Account')))}
                  </Text>
                </TouchableOpacity>

                {mode === 'reset_password' ? (
                  <TouchableOpacity style={styles.authLinkButton} onPress={() => resetAuthFlow('sign_in')}>
                    <Text style={styles.authLinkText}>Back to sign in</Text>
                  </TouchableOpacity>
                ) : null}

              </View>
            </ScrollView>
          </View>
        </Modal>
      </ScrollView>
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

  const label = user?.fullName || user?.primaryEmailAddress?.emailAddress || user?.username || user?.id || 'Authenticated user';
  const clerkUserProfile = {
    id: user?.id || '',
    firstName: user?.firstName || '',
    lastName: user?.lastName || '',
    email: user?.primaryEmailAddress?.emailAddress || '',
  };

  return (
    <MarketplaceMobileApp
      clerkEnabled
      getBearerToken={getToken}
      clerkUserLabel={label}
      clerkUserProfile={clerkUserProfile}
      onSignOut={() => signOut()}
    />
  );
}

class RootErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <SafeAreaProvider>
          <SafeAreaView style={styles.authRoot}>
            <View style={styles.rootErrorCard}>
              <Text style={styles.authTitle}>Unable to Start</Text>
              <Text style={styles.error}>{this.state.error?.message || String(this.state.error)}</Text>
            </View>
          </SafeAreaView>
        </SafeAreaProvider>
      );
    }
    return this.props.children;
  }
}

function AppContent() {
  return (
    <SafeAreaProvider>
      {!CLERK_PUBLISHABLE_KEY ? (
        <MarketplaceMobileApp />
      ) : (
        <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY} tokenCache={tokenCache}>
          <ClerkMobileApp />
        </ClerkProvider>
      )}
    </SafeAreaProvider>
  );
}

export default function App() {
  return (
    <RootErrorBoundary>
      <AppContent />
    </RootErrorBoundary>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.bg },
  mainScroll: { flex: 1 },
  content: { paddingBottom: 18 },
  authRoot: {
    flex: 1,
    backgroundColor: theme.bg,
  },
  authScroll: {
    flex: 1,
  },
  authScrollContent: {
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 28,
    gap: 12,
  },
	  authCard: {
	    borderWidth: 1,
	    borderColor: theme.line,
	    backgroundColor: theme.surface,
	    padding: 14,
	    gap: 8,
	    borderRadius: 0,
	  },
  authModalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(16, 14, 12, 0.48)',
    justifyContent: 'center',
  },
  authModalScroll: {
    flex: 1,
  },
  authModalContent: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: 16,
    paddingVertical: 26,
  },
  authModalCard: {
    shadowColor: '#000',
    shadowOpacity: 0.2,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 12 },
    elevation: 12,
  },
  appAlertOverlay: {
    flex: 1,
    backgroundColor: 'rgba(16, 14, 12, 0.52)',
    justifyContent: 'center',
    paddingHorizontal: 18,
  },
	  appAlertCard: {
	    borderWidth: 1,
	    borderColor: 'rgba(92, 18, 28, 0.22)',
	    backgroundColor: theme.surface,
	    padding: 22,
	    gap: 10,
	    borderRadius: 0,
    shadowColor: '#000',
    shadowOpacity: 0.22,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 12 },
    elevation: 14,
  },
  appAlertEyebrow: {
    color: theme.muted,
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 4,
    textTransform: 'uppercase',
  },
  appAlertTitle: {
    color: theme.brand,
    fontFamily: 'Didot',
    fontSize: 36,
    lineHeight: 38,
  },
  appAlertMessage: {
    color: theme.muted,
    fontSize: 16,
    lineHeight: 23,
  },
  appAlertActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
    marginTop: 8,
  },
	  rootErrorCard: {
    margin: 16,
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: theme.surface,
    padding: 14,
    gap: 8,
	    borderRadius: 0,
	  },
  authTitle: {
    color: theme.text,
    fontSize: 30,
    lineHeight: 34,
    fontFamily: 'Didot',
  },
	  mobileAuthHero: {
	    overflow: 'hidden',
	    borderWidth: 1,
	    borderColor: theme.line,
	    backgroundColor: '#120d0c',
	    borderRadius: 0,
	  },
  mobileAuthTopbar: {
    paddingHorizontal: 14,
    paddingVertical: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  mobileAuthLogo: {
    color: '#fffaf5',
    fontFamily: 'Didot',
    fontSize: 28,
    letterSpacing: 1.8,
  },
	  mobileAuthPill: {
    color: '#f1e8e1',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.35)',
	    borderRadius: 0,
    paddingHorizontal: 10,
    paddingVertical: 6,
    fontSize: 10,
    letterSpacing: 1,
    fontWeight: '700',
  },
  mobileAuthHeroImage: {
    width: '100%',
    height: 250,
    backgroundColor: '#2d2521',
  },
  mobileAuthCopy: {
    padding: 16,
    gap: 10,
  },
  mobileAuthTitle: {
    color: '#fffaf5',
    fontFamily: 'Didot',
    fontSize: 38,
    lineHeight: 41,
  },
  mobileAuthText: {
    color: '#eadfd6',
    fontSize: 14,
    lineHeight: 20,
  },
  authHeroActions: {
    gap: 9,
    marginTop: 4,
  },
  authValueStrip: {
    gap: 8,
  },
	  authValueItem: {
	    borderWidth: 1,
	    borderColor: theme.line,
	    backgroundColor: theme.surface,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  authValueTitle: {
    color: theme.brand,
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  authValueText: {
    color: theme.muted,
    fontSize: 12,
    lineHeight: 17,
    marginTop: 2,
  },
  authPanelHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 10,
  },
	  facebookBtn: {
	    backgroundColor: '#1877f2',
	    borderRadius: 0,
	    paddingVertical: 13,
	    paddingHorizontal: 14,
	    alignItems: 'center',
	    minHeight: 44,
	  },
	  facebookBtnText: {
	    color: '#fff',
	    fontSize: 14,
	    fontWeight: '600',
	    letterSpacing: 0.6,
	  },
	  googleBtn: {
	    backgroundColor: theme.surface,
	    borderColor: theme.lineStrong,
	    borderRadius: 0,
	    borderWidth: 1,
	    paddingVertical: 13,
	    paddingHorizontal: 14,
	    alignItems: 'center',
	    minHeight: 44,
	    marginTop: 10,
	  },
	  googleBtnText: {
	    color: theme.text,
	    fontSize: 14,
	    fontWeight: '600',
	    letterSpacing: 0.6,
	  },
  authDivider: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 4,
  },
  authDividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: theme.line,
  },
  authDividerText: {
    color: theme.muted,
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  authLinkButton: {
    alignSelf: 'flex-start',
    paddingVertical: 6,
  },
  authLinkText: {
    color: theme.brand,
    fontSize: 13,
    fontWeight: '800',
    textDecorationLine: 'underline',
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
	    borderColor: theme.line,
	    borderRadius: 0,
    paddingHorizontal: 6,
    paddingVertical: 7,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 54,
  },
  tabButtonActive: { backgroundColor: theme.brand, borderColor: theme.brand },
  tabButtonIcon: {
    marginBottom: 2,
  },
  tabButtonText: { color: '#4a4139', fontSize: 10, letterSpacing: 0.8, fontWeight: '700', textTransform: 'uppercase' },
  tabButtonTextActive: { color: '#fff' },

	  section: {
	    marginHorizontal: 16,
	    marginBottom: 12,
	    backgroundColor: theme.surface,
	    borderRadius: 0,
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
  alertPreferenceList: {
    gap: 8,
  },
	  alertPreferenceRow: {
	    borderWidth: 1,
	    borderColor: theme.line,
	    borderRadius: 0,
    backgroundColor: '#fff',
    paddingHorizontal: 10,
    paddingVertical: 9,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  alertPreferenceLabel: {
    color: '#231c16',
    fontSize: 13,
    fontWeight: '700',
  },
	  alertToggle: {
	    minWidth: 54,
	    borderWidth: 1,
	    borderColor: theme.line,
	    borderRadius: 0,
    paddingHorizontal: 10,
    paddingVertical: 7,
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  alertToggleActive: {
    borderColor: theme.brand,
    backgroundColor: theme.brand,
  },
  alertToggleText: {
    color: theme.brand,
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  alertToggleTextActive: {
    color: '#fff',
  },
  profilePlanList: {
    gap: 8,
  },
	  profilePlanCard: {
	    borderWidth: 1,
	    borderColor: theme.line,
	    borderRadius: 0,
    padding: 10,
    backgroundColor: '#fff',
    gap: 3,
  },
	  profilePlanCardSelected: {
	    borderColor: theme.lineStrong,
	    backgroundColor: '#fff',
  },
  profilePlanCardActive: {
    borderColor: theme.brand,
    backgroundColor: theme.brandSoft,
  },
  profilePlanTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  profilePlanTitle: {
    color: '#231c16',
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: 0.4,
  },
  profilePlanActiveBadge: {
    color: '#fff',
    backgroundColor: theme.brand,
    overflow: 'hidden',
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 3,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
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
	    borderColor: theme.line,
	    borderRadius: 0,
    backgroundColor: '#fff',
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  headerActionText: { color: theme.brand, fontSize: 11, fontWeight: '700', letterSpacing: 1.1, textTransform: 'uppercase' },

  listingCard: {
    position: 'relative',
    borderWidth: 1,
    borderColor: theme.line,
    borderRadius: 0,
    overflow: 'hidden',
    backgroundColor: '#fff',
  },
  listingCardDisabled: {
    borderColor: '#d8cab8',
  },
  listingCardContentDisabled: {
    opacity: 0.3,
  },
  pendingReviewOverlay: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 5,
  },
  pendingReviewText: {
    borderWidth: 1,
    borderColor: 'rgba(90, 18, 27, 0.38)',
    backgroundColor: 'rgba(255, 255, 255, 0.94)',
    color: theme.brand,
    paddingVertical: 10,
    paddingHorizontal: 14,
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 1.4,
    lineHeight: 16,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  listingImage: { width: '100%', height: 220, backgroundColor: '#ddd4ca' },
  listingImageFallback: { alignItems: 'center', justifyContent: 'center' },
  listingBody: { padding: 12, gap: 8 },
  listingTitleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  listingTitle: {
    color: '#171511',
    fontSize: 18,
    lineHeight: 21,
    fontWeight: '600',
  },
  listingByline: {
    color: '#171511',
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
  likeButton: {
    width: 38,
    height: 38,
    borderWidth: 1,
    borderColor: '#d8c8b8',
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
  },
  likeButtonActive: {
    borderColor: theme.brand,
    backgroundColor: theme.brandSoft,
  },
  likeButtonText: {
    color: theme.brand,
    fontSize: 23,
    lineHeight: 26,
  },
  likeButtonTextActive: {
    color: theme.brand,
  },
  likeDetailButtonActive: {
    borderColor: theme.brand,
    backgroundColor: theme.brandSoft,
  },
  likeDetailButtonTextActive: {
    color: theme.brand,
  },
  likeDetailIconButton: {
    width: 54,
    minWidth: 54,
    height: 44,
    paddingHorizontal: 0,
    alignSelf: 'flex-start',
  },
  listingIconButton: {
    width: 44,
    minWidth: 44,
    height: 40,
    paddingHorizontal: 0,
    justifyContent: 'center',
    alignSelf: 'flex-start',
  },
  listingMeta: {
    color: '#55606f',
    fontSize: 12,
    lineHeight: 17,
    textTransform: 'uppercase',
    letterSpacing: 1.7,
  },
  statusBadge: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: '#d8c8b8',
    backgroundColor: '#f7f0e8',
    paddingHorizontal: 9,
    height: 40,
    justifyContent: 'center',
  },
  statusBadgeFailed: {
    borderColor: 'rgba(168,34,34,0.34)',
    backgroundColor: 'rgba(168,34,34,0.08)',
  },
  statusBadgeText: {
    color: '#4a4139',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  statusBadgeTextFailed: {
    color: theme.error,
  },
  analysisFailedText: {
    borderWidth: 1,
    borderColor: 'rgba(168,34,34,0.28)',
    backgroundColor: 'rgba(168,34,34,0.08)',
    color: theme.error,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
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
	    borderRadius: 0,
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
	    borderRadius: 0,
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: theme.surface,
    overflow: 'hidden',
  },
  listingDetailScreen: {
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: theme.surface,
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
  offerDetailTitleWrap: {
    flex: 1,
    minWidth: 0,
    paddingRight: 8,
  },
  offerDetailBackButton: {
    flexShrink: 0,
    minWidth: 68,
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
  listingDetailGalleryStack: {
    gap: 8,
  },
  listingDetailMatchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 10,
  },
  listingDetailActionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flexWrap: 'wrap',
  },
  listingDetailGalleryImageFull: {
    width: '100%',
    height: 260,
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: '#ece7df',
  },
  galleryModalRoot: {
    flex: 1,
    backgroundColor: '#0d0b0a',
  },
  galleryModalHeader: {
    paddingHorizontal: 12,
    paddingTop: 56,
    paddingBottom: 10,
    alignItems: 'flex-end',
    zIndex: 2,
  },
  galleryModalCloseButton: {
    minWidth: 92,
    minHeight: 44,
    justifyContent: 'center',
  },
  galleryModalImage: {
    flex: 1,
    width: '100%',
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
	    borderRadius: 0,
    padding: 9,
    gap: 6,
    backgroundColor: '#fff',
  },
	  profilePaymentCard: {
	    borderWidth: 1,
	    borderColor: theme.line,
	    borderRadius: 0,
    padding: 10,
    gap: 7,
    backgroundColor: '#fff',
  },
  profilePaymentCardSelected: {
    borderColor: theme.brand,
    backgroundColor: theme.brandSoft,
  },
	  profileLegalCard: {
	    borderWidth: 1,
	    borderColor: theme.line,
	    borderRadius: 0,
    padding: 10,
    gap: 7,
    backgroundColor: '#fff',
  },
  profileLegalText: {
    color: '#423935',
    fontSize: 13,
    lineHeight: 19,
  },
  profileLegalLink: {
    color: theme.brand,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '700',
  },
  profileLegalActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  profileSignOutFooter: {
    borderTopWidth: 1,
    borderTopColor: theme.line,
    marginTop: 12,
    paddingTop: 12,
  },
  profileAddressRow: {
    flexDirection: 'row',
    gap: 8,
  },
  addressSuggestionList: {
    gap: 6,
  },
	  addressSuggestionCard: {
	    borderWidth: 1,
	    borderColor: theme.line,
	    borderRadius: 0,
	    backgroundColor: '#fff',
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  addressSuggestionText: {
    color: '#342b24',
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
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
	    borderColor: theme.line,
	    borderRadius: 0,
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
	    borderRadius: 0,
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
	  editImagePanel: {
	    borderWidth: 1,
	    borderColor: theme.line,
	    borderRadius: 0,
    padding: 10,
    gap: 10,
    backgroundColor: '#fff',
  },
  editImageGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  editImageTile: {
    width: '31%',
    minWidth: 88,
    borderWidth: 1,
    borderColor: theme.line,
    backgroundColor: '#f5f1ea',
    overflow: 'hidden',
  },
  editImageTileHero: {
    borderColor: theme.brand,
    borderWidth: 2,
  },
  editImageThumb: {
    width: '100%',
    height: 96,
    backgroundColor: '#ece7df',
  },
  editImageRemove: {
    paddingVertical: 7,
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: theme.line,
    backgroundColor: '#fff',
  },
  editImageRemoveText: {
    color: '#6b4a36',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  editImageHeroButton: {
    paddingVertical: 7,
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: theme.line,
    backgroundColor: '#fffaf4',
  },
  editImageHeroButtonText: {
    color: theme.brand,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.7,
    textTransform: 'uppercase',
  },
  editImageBadge: {
    position: 'absolute',
    top: 5,
    left: 5,
    paddingHorizontal: 6,
    paddingVertical: 3,
    backgroundColor: 'rgba(32, 28, 23, 0.78)',
    color: '#fff',
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  editImageHeroBadge: {
    position: 'absolute',
    top: 5,
    right: 5,
    paddingHorizontal: 6,
    paddingVertical: 3,
    backgroundColor: theme.brand,
    color: '#fff',
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },

  label: { fontSize: 11, color: '#6c6359', fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase' },
	  input: {
	    borderWidth: 1,
	    borderColor: 'rgba(31, 26, 23, 0.18)',
	    borderRadius: 0,
	    minHeight: 44,
	    paddingHorizontal: 12,
	    paddingVertical: 10,
	    backgroundColor: '#fff',
	    color: '#1c1917',
	    fontSize: 15,
	    fontWeight: '500',
	  },
  multiInput: { minHeight: 74, textAlignVertical: 'top' },

  modeRow: { flexDirection: 'row', gap: 8, marginVertical: 2 },
	  modeBtn: {
	    flex: 1,
	    borderWidth: 1,
	    borderColor: theme.line,
	    borderRadius: 0,
	    minHeight: 44,
	    paddingVertical: 10,
	    alignItems: 'center',
	    backgroundColor: '#fff',
	    justifyContent: 'center',
	  },
	  modeBtnActive: { borderColor: theme.brand, backgroundColor: theme.brand },
	  modeBtnText: { color: theme.text, fontWeight: '600', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1.2 },
	  modeBtnTextActive: { color: '#fff' },

	  primaryBtn: {
	    backgroundColor: '#111',
	    borderRadius: 0,
	    borderWidth: 1,
	    borderColor: theme.lineStrong,
	    minHeight: 44,
	    paddingVertical: 11,
    paddingHorizontal: 14,
    alignItems: 'center',
	  },
	  primaryBtnText: { color: '#fff', fontWeight: '600', letterSpacing: 1.2, textTransform: 'uppercase', fontSize: 12 },
	  secondaryBtn: {
	    borderRadius: 0,
	    borderWidth: 1,
	    borderColor: theme.line,
	    minHeight: 44,
    paddingVertical: 11,
    paddingHorizontal: 14,
    alignItems: 'center',
    backgroundColor: '#fff',
  },
	  primaryBtnCompact: {
	    alignSelf: 'flex-start',
	    marginTop: 6,
	    backgroundColor: '#111',
	    borderRadius: 0,
	    borderWidth: 1,
	    borderColor: theme.lineStrong,
	    paddingVertical: 8,
    paddingHorizontal: 10,
    alignItems: 'center',
  },
  primaryBtnDisabled: {
    opacity: 0.5,
  },
	  secondaryBtnCompact: {
	    borderRadius: 0,
	    borderWidth: 1,
	    borderColor: theme.line,
	    paddingVertical: 7,
    paddingHorizontal: 9,
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  loadMoreButton: {
    alignSelf: 'stretch',
    justifyContent: 'center',
    marginTop: 8,
    marginBottom: 16,
    minHeight: 44,
  },
  dangerBtnCompact: {
    borderColor: '#b42318',
  },
  dangerBtnText: {
    color: '#b42318',
  },
  listingActionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 8,
    marginTop: 6,
  },
  listingTextButton: {
    minHeight: 40,
    justifyContent: 'center',
  },
  shareIconButton: {
    width: 42,
    minHeight: 40,
    justifyContent: 'center',
    paddingHorizontal: 0,
  },
	  secondaryBtnText: { color: theme.text, fontWeight: '600', letterSpacing: 1.2, textTransform: 'uppercase', fontSize: 12 },
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
	    borderColor: theme.line,
	    borderRadius: 0,
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
	    borderColor: theme.line,
	    borderRadius: 0,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#fff',
  },
	  tagChipActive: {
	    borderColor: theme.brand,
	    backgroundColor: theme.brand,
  },
  sizeChartChip: {
    borderColor: theme.brand,
    backgroundColor: '#fffaf4',
  },
	  tagChipText: {
	    color: theme.text,
	    fontWeight: '600',
    fontSize: 11,
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
	  tagChipTextActive: {
	    color: '#fff',
	  },

  helperText: { color: '#756b61' },
  loadingState: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 28,
  },
  loadingText: {
    color: '#7a7167',
    fontWeight: '700',
    textAlign: 'center',
  },
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingVertical: 28,
  },
  emptyTitle: {
    color: theme.text,
    fontSize: 18,
    fontWeight: '700',
    textAlign: 'center',
  },
  emptyText: { color: '#7a7167', textAlign: 'center', paddingVertical: 10 },
  error: { color: theme.error, fontWeight: '700', marginHorizontal: 16, marginBottom: 6 },
  notice: { color: theme.success, fontWeight: '700', marginHorizontal: 16, marginBottom: 6 },
});
