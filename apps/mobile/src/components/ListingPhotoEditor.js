import React, { useEffect, useState } from 'react';
import { Modal, View, Text, Image, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as ImageManipulator from 'expo-image-manipulator';
import { cropPixels } from '../../../../packages/app-client/src/photoEdits';

const full = { x: 0, y: 0, width: 100, height: 100 };
export default function ListingPhotoEditor({ uri, onCancel, onApply }) {
  const [photo, setPhoto] = useState(null);
  const [crop, setCrop] = useState(full);
  const [zoom, setZoom] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    Image.getSize(uri, (width, height) => { if (active) setPhoto({ uri, width, height }); },
      () => { if (active) setError('Unable to open this photo. Please try again.'); });
    return () => { active = false; };
  }, [uri]);
  async function rotate() {
    setBusy(true); setError('');
    try {
      const next = await ImageManipulator.manipulateAsync(photo.uri, [{ rotate: 90 }], { compress: 1, format: ImageManipulator.SaveFormat.JPEG });
      setPhoto(next); setCrop(full);
    } catch { setError('Unable to rotate this photo.'); }
    finally { setBusy(false); }
  }
  async function save() {
    setBusy(true); setError('');
    try {
      const result = await ImageManipulator.manipulateAsync(photo.uri,
        [{ crop: cropPixels(photo.width, photo.height, crop) }], { compress: .95, format: ImageManipulator.SaveFormat.JPEG });
      await onApply({ ...result, mimeType: 'image/jpeg', fileName: `edited-${Date.now()}.jpg` });
    } catch { setError('Unable to save photo edits. Your original is unchanged. Please retry.'); }
    finally { setBusy(false); }
  }
  const button = (label, action, disabled = false) => <TouchableOpacity accessibilityRole="button" style={styles.button} onPress={action} disabled={busy || disabled}><Text style={styles.label}>{label}</Text></TouchableOpacity>;
  return <Modal visible animationType="slide" onRequestClose={() => { if (!busy) onCancel(); }}>
    <SafeAreaView style={styles.screen}>
      <View style={styles.row}>{button('Cancel', onCancel)}<Text style={styles.title}>Edit photo</Text>{button('Use photo', save, !photo)}</View>
      <Text style={styles.hint}>Zoom to inspect. Adjust the crop box below. Edits apply only when you save the listing.</Text>
      <ScrollView style={{ flex: 1 }} maximumZoomScale={4} minimumZoomScale={1} centerContent>
        <ScrollView horizontal>
        {photo && <View style={{ width: 320 * zoom, height: 320 * zoom * photo.height / photo.width, alignSelf: 'center' }}>
          <Image source={{ uri: photo.uri }} style={StyleSheet.absoluteFill} resizeMode="contain" />
          <View pointerEvents="none" style={{ position: 'absolute', borderWidth: 2, borderColor: '#ffffff', backgroundColor: '#ffffff15',
            left: `${crop.x}%`, top: `${crop.y}%`, width: `${crop.width}%`, height: `${crop.height}%` }} />
        </View>}
        </ScrollView>
      </ScrollView>
      {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
      {busy ? <ActivityIndicator /> : null}
      <View style={styles.row}>{button('Zoom −', () => setZoom(v => Math.max(1, v - .5)))}{button('Zoom +', () => setZoom(v => Math.min(3, v + .5)))}{button('Rotate 90°', rotate, !photo)}{button('Reset', () => { setCrop(full); setZoom(1); setPhoto(null); Image.getSize(uri, (width, height) => setPhoto({ uri, width, height })); })}</View>
      {['x', 'y', 'width', 'height'].map(key => <View style={styles.row} key={key}><Text style={styles.label}>{({x:'Left',y:'Top',width:'Width',height:'Height'})[key]} {crop[key]}%</Text>
        {button('−', () => setCrop(c => ({ ...c, [key]: Math.max(key === 'x' || key === 'y' ? 0 : 10, c[key] - 5) })))}
        {button('+', () => setCrop(c => {
          const next = { ...c, [key]: Math.min(100, c[key] + 5) };
          next.x = Math.min(next.x, 100 - next.width); next.y = Math.min(next.y, 100 - next.height);
          next.width = Math.min(next.width, 100 - next.x); next.height = Math.min(next.height, 100 - next.y);
          return next;
        }))}</View>)}
    </SafeAreaView>
  </Modal>;
}
const styles = StyleSheet.create({ screen: { flex: 1, backgroundColor: '#f8f4ee', padding: 12 }, row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }, button: { padding: 12, minHeight: 44, borderWidth: 1, borderColor: '#d8cec5', backgroundColor: 'white' }, label: { color: '#64141f', fontSize: 13 }, title: { fontSize: 20, color: '#64141f' }, hint: { marginVertical: 10, color: '#625b55' }, error: { color: '#b00020', margin: 8 } });
