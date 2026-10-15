import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, AppState, Image, Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { CameraView } from 'expo-camera';
import { Ionicons } from '@expo/vector-icons';

export default function ListingCamera({ maxPhotos, onUsePhotos, onCancel }) {
  const cameraRef = useRef(null);
  const captureBusyRef = useRef(false);
  const finishedRef = useRef(false);
  const mountedRef = useRef(true);
  const photosRef = useRef([]);
  const [photos, setPhotos] = useState([]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [foreground, setForeground] = useState(AppState.currentState === 'active');

  useEffect(() => {
    mountedRef.current = true;
    const subscription = AppState.addEventListener('change', (state) => {
      setForeground(state === 'active');
      setReady(false);
    });
    return () => { mountedRef.current = false; subscription.remove(); };
  }, []);

  function updatePhotos(next) {
    photosRef.current = next;
    setPhotos(next);
  }

  async function capture() {
    if (!ready || !foreground || finishedRef.current || captureBusyRef.current || photosRef.current.length >= maxPhotos) return;
    captureBusyRef.current = true;
    setBusy(true);
    setError('');
    try {
      const photo = await cameraRef.current?.takePictureAsync({ quality: 0.9 });
      if (!photo?.uri) throw new Error('No photo returned');
      if (mountedRef.current) updatePhotos([...photosRef.current, {
        uri: photo.uri, width: photo.width, height: photo.height,
        mimeType: 'image/jpeg', fileName: `listing-${Date.now()}.jpg`,
      }]);
    } catch {
      if (mountedRef.current) setError('Could not take this photo. Please try again.');
    } finally {
      captureBusyRef.current = false;
      if (mountedRef.current) setBusy(false);
    }
  }

  function cancel() {
    if (captureBusyRef.current || finishedRef.current) return;
    const discard = () => { finishedRef.current = true; onCancel(); };
    if (!photosRef.current.length) { discard(); return; }
    Alert.alert('Discard these photos?', 'These photos have not been added to your listing.', [
      { text: 'Keep taking photos', style: 'cancel' },
      { text: 'Discard', style: 'destructive', onPress: discard },
    ]);
  }

  const full = photos.length >= maxPhotos;
  return <Modal visible animationType="slide" presentationStyle="fullScreen" onRequestClose={cancel}><SafeAreaProvider><SafeAreaView style={styles.screen} edges={['top', 'bottom', 'left', 'right']}>
    <View style={styles.header}>
      <TouchableOpacity onPress={cancel} disabled={busy} accessibilityRole="button" accessibilityLabel="Cancel taking photos" hitSlop={8} style={styles.headerButton}>
        <Text style={styles.actionText}>Cancel</Text>
      </TouchableOpacity>
      <Text style={styles.title} numberOfLines={1}>Take listing photos</Text>
      <Text style={styles.count}>{photos.length}/{maxPhotos}</Text>
    </View>
    <View style={styles.preview}>
      {foreground && <CameraView ref={cameraRef} style={StyleSheet.absoluteFill} facing="back" mode="picture" autofocus="on"
        onCameraReady={() => { setReady(true); setError(''); }}
        onMountError={() => { setReady(false); setError('Camera unavailable. Close this screen and use Photo Library, or try a physical device.'); }} />}
    </View>
    <View style={styles.footer}>
      <Text style={styles.guidance}>{full ? 'Photo limit reached. Remove a photo to take another.' : 'Capture the front, back, label, and important details.'}</Text>
      {error ? <Text style={styles.error} accessibilityRole="alert">{error}</Text> : null}
      {photos.length > 0 && <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.thumbnails}>
        {photos.map((photo, index) => <View key={photo.uri} style={styles.thumbnail}>
          <Image source={{ uri: photo.uri }} style={styles.image} accessibilityLabel={`Captured photo ${index + 1}`} />
          <TouchableOpacity style={styles.remove} disabled={busy} accessibilityRole="button" accessibilityLabel={`Remove photo ${index + 1}`}
            onPress={() => updatePhotos(photosRef.current.filter((entry) => entry.uri !== photo.uri))}>
            <Ionicons name="close-circle" size={26} color="#fff" />
          </TouchableOpacity>
        </View>)}
      </ScrollView>}
      <View style={styles.controls}>
        <TouchableOpacity style={[styles.shutter, (!ready || busy || full || !foreground) && styles.disabled]} onPress={capture}
          disabled={!ready || busy || full || !foreground} accessibilityRole="button" accessibilityLabel="Take photo">
          {busy ? <ActivityIndicator color="#4a161b" /> : <Ionicons name="camera" size={30} color="#4a161b" />}
        </TouchableOpacity>
        <TouchableOpacity style={[styles.useButton, (!photos.length || busy) && styles.disabled]} disabled={!photos.length || busy}
          accessibilityRole="button" onPress={() => {
            if (captureBusyRef.current || finishedRef.current) return;
            finishedRef.current = true;
            onUsePhotos(photosRef.current);
          }}>
          <Text style={styles.useText}>Use Photos ({photos.length})</Text>
        </TouchableOpacity>
      </View>
    </View>
  </SafeAreaView></SafeAreaProvider></Modal>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#fbf8f2' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 8, minHeight: 60 },
  headerButton: { minHeight: 44, minWidth: 72, justifyContent: 'center', paddingHorizontal: 8 },
  title: { flex: 1, textAlign: 'center', marginHorizontal: 8, fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 15, color: '#18181b' },
  actionText: { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, color: '#4a161b' },
  count: { minWidth: 48, textAlign: 'right', fontFamily: 'PlusJakartaSans_600SemiBold', color: '#4a161b' },
  preview: { flex: 1, backgroundColor: '#18181b' },
  footer: { padding: 16, gap: 12 },
  guidance: { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 12, color: '#4f5560' },
  error: { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 12, color: '#a82222' },
  thumbnails: { gap: 10 },
  thumbnail: { width: 80, height: 90 },
  image: { width: '100%', height: '100%', borderRadius: 4 },
  remove: { position: 'absolute', right: 0, top: 0, minWidth: 44, minHeight: 44, alignItems: 'flex-end', backgroundColor: 'rgba(0,0,0,.25)' },
  controls: { flexDirection: 'row', alignItems: 'center', gap: 20 },
  shutter: { width: 64, height: 64, borderRadius: 32, borderWidth: 3, borderColor: '#4a161b', alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff' },
  useButton: { flex: 1, minHeight: 48, alignItems: 'center', justifyContent: 'center', backgroundColor: '#4a161b', padding: 12 },
  useText: { fontFamily: 'PlusJakartaSans_700Bold', color: '#fff', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 },
  disabled: { opacity: 0.4 },
});
