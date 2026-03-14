import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import Constants from 'expo-constants';
import { StatusBar } from 'expo-status-bar';

const API_DEFAULT = Constants.expoConfig?.extra?.apiBaseUrl || 'http://127.0.0.1:8000';

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

function buildAuthHeaders({ authMode, apiKey, bearerToken }) {
  if (authMode === 'bearer' && bearerToken.trim()) {
    return { Authorization: `Bearer ${bearerToken.trim()}` };
  }
  return { 'x-api-key': apiKey.trim() };
}

async function analyzeItem({
  apiBaseUrl,
  authMode,
  apiKey,
  bearerToken,
  images,
  category,
  userCondition,
  itemDescription,
  debug,
}) {
  const fd = new FormData();
  images.forEach((img, idx) => {
    fd.append('images', {
      uri: img.uri,
      name: img.fileName || `upload-${idx + 1}.jpg`,
      type: img.mimeType || 'image/jpeg',
    });
  });
  if (category) fd.append('category', category);
  if (userCondition) fd.append('user_condition', userCondition);
  if (itemDescription) fd.append('item_description', itemDescription);
  fd.append('debug', String(debug));

  const res = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/analyze`, {
    method: 'POST',
    headers: buildAuthHeaders({ authMode, apiKey, bearerToken }),
    body: fd,
  });

  let payload = null;
  try {
    payload = await res.json();
  } catch {
    // noop
  }

  if (!res.ok) {
    const detail = Array.isArray(payload?.detail) ? payload.detail[0]?.msg : payload?.detail;
    throw new Error(detail || `API error (${res.status})`);
  }
  return payload;
}

async function createListing({
  apiBaseUrl,
  authMode,
  apiKey,
  bearerToken,
  payload,
}) {
  const res = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/listings`, {
    method: 'POST',
    headers: {
      ...buildAuthHeaders({ authMode, apiKey, bearerToken }),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  let data = null;
  try {
    data = await res.json();
  } catch {
    // noop
  }

  if (!res.ok) {
    const detail = Array.isArray(data?.detail) ? data.detail[0]?.msg : data?.detail;
    throw new Error(detail || `API error (${res.status})`);
  }
  return data;
}

async function fetchListings({
  apiBaseUrl,
  authMode,
  apiKey,
  bearerToken,
  limit = 20,
}) {
  const res = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/listings?limit=${limit}`, {
    method: 'GET',
    headers: buildAuthHeaders({ authMode, apiKey, bearerToken }),
  });

  let data = null;
  try {
    data = await res.json();
  } catch {
    // noop
  }

  if (!res.ok) {
    const detail = Array.isArray(data?.detail) ? data.detail[0]?.msg : data?.detail;
    throw new Error(detail || `API error (${res.status})`);
  }
  return data;
}

function StepBadge({ num, label, active, done }) {
  return (
    <View style={[styles.stepBadge, active && styles.stepBadgeActive]}>
      <Text style={[styles.stepNum, done && styles.stepNumDone]}>{num}</Text>
      <Text style={styles.stepLabel}>{label}</Text>
    </View>
  );
}

export default function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState(API_DEFAULT);
  const [authMode, setAuthMode] = useState('api_key'); // api_key | bearer
  const [apiKey, setApiKey] = useState('local-dev-key');
  const [bearerToken, setBearerToken] = useState('');

  const [wizardStep, setWizardStep] = useState(1);
  const [images, setImages] = useState([]);
  const [category, setCategory] = useState('');
  const [itemTitle, setItemTitle] = useState('');
  const [itemDescription, setItemDescription] = useState('');
  const [userCondition, setUserCondition] = useState('');

  const [listingMode, setListingMode] = useState('sell_trade');
  const [askingValue, setAskingValue] = useState('');
  const [tradeNotes, setTradeNotes] = useState('');

  const [analysisResult, setAnalysisResult] = useState(null);
  const [myListings, setMyListings] = useState([]);
  const [listingsLoading, setListingsLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const canNext = useMemo(() => {
    if (wizardStep === 1) return images.length >= 1 && images.length <= 4;
    if (wizardStep === 2) return !!userCondition;
    return true;
  }, [wizardStep, images.length, userCondition]);

  function authReady() {
    if (authMode === 'bearer') return Boolean(bearerToken.trim());
    return Boolean(apiKey.trim());
  }

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

  async function analyzePhotosStep1() {
    if (!authReady()) {
      setError(authMode === 'bearer' ? 'Bearer token required.' : 'API key required.');
      return false;
    }
    setLoading(true);
    setError('');
    setNotice('');
    try {
      const payload = await analyzeItem({
        apiBaseUrl,
        authMode,
        apiKey,
        bearerToken,
        images,
        category,
        userCondition: '',
        itemDescription: itemDescription.trim(),
        debug: true,
      });
      setAnalysisResult(payload);
      if (!category && payload?.category) setCategory(payload.category);

      const gptTitle = payload?.item_profile?.model_identification?.name?.trim?.() || '';
      const suggestedDesc = buildSuggestedDescriptionFromProfile(payload?.item_profile);
      if (!itemTitle.trim() && gptTitle) setItemTitle(gptTitle);
      if (!itemDescription.trim() && suggestedDesc) setItemDescription(suggestedDesc);
      return true;
    } catch (e) {
      setError(e.message || String(e));
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function analyzePricingStep2() {
    if (!authReady()) {
      setError(authMode === 'bearer' ? 'Bearer token required.' : 'API key required.');
      return false;
    }
    setLoading(true);
    setError('');
    setNotice('');
    try {
      const payload = await analyzeItem({
        apiBaseUrl,
        authMode,
        apiKey,
        bearerToken,
        images,
        category,
        userCondition,
        itemDescription: itemDescription.trim(),
        debug: true,
      });
      setAnalysisResult(payload);
      if (payload?.valuation?.estimated_value != null) {
        setAskingValue(String(Math.round(payload.valuation.estimated_value)));
      } else {
        setAskingValue('');
      }
      return true;
    } catch (e) {
      setError(e.message || String(e));
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function nextStep() {
    if (!canNext) {
      setError(wizardStep === 1 ? 'Upload 1 to 4 images before continuing.' : 'Condition is required.');
      return;
    }

    if (wizardStep === 1) {
      const ok = await analyzePhotosStep1();
      if (!ok) return;
    }

    if (wizardStep === 2) {
      const ok = await analyzePricingStep2();
      if (!ok) return;
    }

    setError('');
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
      setError(authMode === 'bearer' ? 'Bearer token required.' : 'API key required.');
      return;
    }

    setLoading(true);
    setError('');
    setNotice('');
    try {
      const payload = {
        title: itemTitle.trim() || itemDescription.trim() || `${analysisResult.brand?.name || 'Item'} ${analysisResult.category || ''}`.trim(),
        mode: listingMode,
        category: analysisResult.category,
        brand: analysisResult.brand?.name || 'unknown',
        condition: userCondition || analysisResult.condition?.grade || 'Good',
        estimated_value: Number(askingValue || analysisResult.valuation?.estimated_value || 0),
        city: 'Your area',
        image: images[0]?.uri || null,
        wants: tradeNotes.trim() || 'Open to similar-value offers',
        tags: [userCondition || analysisResult.condition?.grade || 'Good', analysisResult.brand?.name || 'unknown', listingMode.replace('_', '/')],
        source_item_id: analysisResult.item_id,
        analysis: analysisResult,
      };

      const created = await createListing({
        apiBaseUrl,
        authMode,
        apiKey,
        bearerToken,
        payload,
      });
      setNotice(`Listing published (${created.listing_id.slice(0, 8)}...)`);
      await refreshListings();
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function refreshListings() {
    if (!authReady()) {
      setError(authMode === 'bearer' ? 'Bearer token required.' : 'API key required.');
      return;
    }
    setListingsLoading(true);
    setError('');
    try {
      const payload = await fetchListings({
        apiBaseUrl,
        authMode,
        apiKey,
        bearerToken,
        limit: 20,
      });
      setMyListings(payload?.items || []);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setListingsLoading(false);
    }
  }

  return (
    <View style={styles.root}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.h1}>ValueAI Mobile</Text>
        <Text style={styles.sub}>3-step listing wizard</Text>

        <View style={styles.card}>
          <Text style={styles.label}>API Base URL</Text>
          <TextInput value={apiBaseUrl} onChangeText={setApiBaseUrl} style={styles.input} autoCapitalize="none" />

          <View style={styles.modeRow}>
            <TouchableOpacity
              style={[styles.modeBtn, authMode === 'api_key' && styles.modeBtnActive]}
              onPress={() => setAuthMode('api_key')}
            >
              <Text style={[styles.modeBtnText, authMode === 'api_key' && styles.modeBtnTextActive]}>API Key</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modeBtn, authMode === 'bearer' && styles.modeBtnActive]}
              onPress={() => setAuthMode('bearer')}
            >
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
                style={[styles.input, styles.area2]}
                multiline
                autoCapitalize="none"
                placeholder="Paste a valid Clerk JWT"
              />
            </>
          )}
        </View>

        <View style={styles.stepsRow}>
          <StepBadge num={1} label="Upload" active={wizardStep === 1} done={wizardStep > 1} />
          <StepBadge num={2} label="Details" active={wizardStep === 2} done={wizardStep > 2} />
          <StepBadge num={3} label="Review" active={wizardStep === 3} done={false} />
        </View>

        <View style={styles.card}>
          {wizardStep === 1 && (
            <>
              <Text style={styles.stepTitle}>Step 1: Upload images + GPT profile</Text>
              <TouchableOpacity style={styles.primaryBtn} onPress={pickImages}>
                <Text style={styles.primaryBtnText}>Choose Photos (1-4)</Text>
              </TouchableOpacity>
              <Text style={styles.muted}>Selected: {images.length}</Text>
              <View style={styles.previewRow}>
                {images.map((img) => (
                  <Image key={img.uri} source={{ uri: img.uri }} style={styles.previewImg} />
                ))}
              </View>
            </>
          )}

          {wizardStep === 2 && (
            <>
              <Text style={styles.stepTitle}>Step 2: Item details</Text>
              <Text style={styles.label}>Category</Text>
              <TextInput value={category} onChangeText={setCategory} style={styles.input} placeholder="clothes / shoes / handbag" />
              <Text style={styles.label}>Title</Text>
              <TextInput value={itemTitle} onChangeText={setItemTitle} style={[styles.input, styles.area2]} multiline />
              <Text style={styles.label}>Item description</Text>
              <TextInput value={itemDescription} onChangeText={setItemDescription} style={[styles.input, styles.area4]} multiline />
              <Text style={styles.label}>Condition (user input)</Text>
              <TextInput value={userCondition} onChangeText={setUserCondition} style={styles.input} placeholder="New / LikeNew / Good / Fair / Poor" />
              <Text style={styles.label}>GPT item profile</Text>
              <Text style={styles.profileText}>{analysisResult?.item_profile ? JSON.stringify(analysisResult.item_profile, null, 2) : 'No profile yet'}</Text>
            </>
          )}

          {wizardStep === 3 && (
            <>
              <Text style={styles.stepTitle}>Step 3: Review + publish</Text>
              <Text style={styles.label}>Listing mode</Text>
              <TextInput value={listingMode} onChangeText={setListingMode} style={styles.input} />
              <Text style={styles.label}>Target asking value (USD)</Text>
              <TextInput value={askingValue} onChangeText={setAskingValue} style={styles.input} keyboardType="numeric" />
              <Text style={styles.label}>Trade notes</Text>
              <TextInput value={tradeNotes} onChangeText={setTradeNotes} style={styles.input} />
              <Text style={styles.muted}>Estimated from Step 2: {analysisResult?.valuation?.estimated_value ?? 'n/a'}</Text>
            </>
          )}

          {!!error && <Text style={styles.error}>{error}</Text>}
          {!!notice && <Text style={styles.notice}>{notice}</Text>}

          <View style={styles.btnRow}>
            {wizardStep > 1 && (
              <TouchableOpacity style={styles.secondaryBtn} onPress={prevStep} disabled={loading}>
                <Text style={styles.secondaryBtnText}>Back</Text>
              </TouchableOpacity>
            )}
            {wizardStep < 3 && (
              <TouchableOpacity style={styles.primaryBtn} onPress={nextStep} disabled={loading}>
                <Text style={styles.primaryBtnText}>
                  {loading && wizardStep === 1 ? 'Analyzing photos...' : loading && wizardStep === 2 ? 'Analyzing pricing...' : 'Next'}
                </Text>
              </TouchableOpacity>
            )}
            {wizardStep === 3 && (
              <TouchableOpacity style={styles.primaryBtn} onPress={publishListing} disabled={loading}>
                <Text style={styles.primaryBtnText}>{loading ? 'Publishing...' : 'Publish Listing'}</Text>
              </TouchableOpacity>
            )}
          </View>

          {loading && <ActivityIndicator style={{ marginTop: 8 }} />}
        </View>

        <View style={styles.card}>
          <View style={styles.listingsHeader}>
            <Text style={styles.stepTitle}>My Listings</Text>
            <TouchableOpacity style={styles.secondaryBtn} onPress={refreshListings} disabled={listingsLoading}>
              <Text style={styles.secondaryBtnText}>{listingsLoading ? 'Refreshing...' : 'Refresh'}</Text>
            </TouchableOpacity>
          </View>
          {myListings.length === 0 ? (
            <Text style={styles.muted}>No listings loaded yet.</Text>
          ) : (
            myListings.map((item) => (
              <View key={item.listing_id} style={styles.listingCard}>
                <Text style={styles.listingTitle}>{item.title}</Text>
                <Text style={styles.muted}>
                  {item.brand} • {item.category} • {item.condition}
                </Text>
                <Text style={styles.muted}>
                  ${Number(item.estimated_value || 0).toFixed(0)} • {item.mode}
                </Text>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#f3f6fb' },
  content: { padding: 16, gap: 12 },
  h1: { fontSize: 26, fontWeight: '700', color: '#122034' },
  sub: { color: '#506079', marginBottom: 2 },

  card: {
    backgroundColor: '#fff',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#d9e2ef',
    padding: 12,
    gap: 8,
  },

  modeRow: { flexDirection: 'row', gap: 8, marginVertical: 4 },
  modeBtn: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#d9e2ef',
    borderRadius: 10,
    paddingVertical: 8,
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  modeBtnActive: { borderColor: '#0f766e', backgroundColor: '#e7f6f4' },
  modeBtnText: { color: '#334155', fontWeight: '600' },
  modeBtnTextActive: { color: '#0f766e' },

  stepsRow: { flexDirection: 'row', gap: 8 },
  stepBadge: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#d9e2ef',
    borderRadius: 10,
    padding: 8,
    backgroundColor: '#fff',
  },
  stepBadgeActive: { borderColor: '#0f766e', backgroundColor: '#e7f6f4' },
  stepNum: {
    width: 24,
    height: 24,
    borderRadius: 99,
    textAlign: 'center',
    textAlignVertical: 'center',
    fontWeight: '700',
    color: '#334155',
    backgroundColor: '#e2e8f0',
    marginBottom: 6,
    overflow: 'hidden',
  },
  stepNumDone: { backgroundColor: '#bfdbfe' },
  stepLabel: { fontSize: 12, fontWeight: '600', color: '#334155' },

  stepTitle: { fontSize: 16, fontWeight: '700', color: '#122034', marginBottom: 4 },
  label: { fontSize: 12, color: '#5b6b82', fontWeight: '600' },
  input: {
    borderWidth: 1,
    borderColor: '#d9e2ef',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    backgroundColor: '#fff',
  },
  area2: { minHeight: 52, textAlignVertical: 'top' },
  area4: { minHeight: 96, textAlignVertical: 'top' },

  primaryBtn: {
    backgroundColor: '#0f766e',
    borderRadius: 10,
    paddingVertical: 11,
    paddingHorizontal: 14,
    alignItems: 'center',
  },
  primaryBtnText: { color: '#fff', fontWeight: '700' },
  secondaryBtn: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    paddingVertical: 11,
    paddingHorizontal: 14,
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  secondaryBtnText: { color: '#334155', fontWeight: '700' },
  btnRow: { flexDirection: 'row', gap: 8, marginTop: 4 },
  listingsHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  listingCard: {
    borderWidth: 1,
    borderColor: '#d9e2ef',
    borderRadius: 10,
    padding: 10,
    backgroundColor: '#fff',
    gap: 2,
  },
  listingTitle: { fontSize: 14, fontWeight: '700', color: '#1f2937' },

  previewRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 2 },
  previewImg: { width: 70, height: 70, borderRadius: 8, backgroundColor: '#dbe4f0' },

  profileText: {
    borderWidth: 1,
    borderColor: '#d9e2ef',
    borderRadius: 10,
    padding: 10,
    minHeight: 100,
    fontFamily: 'Courier',
    fontSize: 12,
    color: '#374151',
  },

  muted: { color: '#64748b', fontSize: 12 },
  error: { color: '#b91c1c', fontWeight: '600' },
  notice: { color: '#0f766e', fontWeight: '600' },
});
