import React, { useEffect, useRef, useState } from 'react';
import { Alert, Text, View } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import ListingAgentChat from './ListingAgentChat';
import { appendListingPhotos } from '../lib/listingPhotos.mjs';

// Selection is local to this linked workflow, never the regular listing form.
export default function ThreadListingWorkflow({ onBusyChange, ...props }) {
  const [images, setImages] = useState([]);
  const [error, setError] = useState('');
  const [picking, setPicking] = useState(false);
  const [childBusy, setChildBusy] = useState(false);
  const busy = useRef(onBusyChange);
  busy.current = onBusyChange;
  useEffect(() => { busy.current?.(picking || childBusy); return () => busy.current?.(false); }, [picking, childBusy]);
  async function pick(source) {
    if (picking || images.length >= 6) return;
    setPicking(true);
    setError('');
    try {
      const permission = source === 'camera' ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) { setError('Photo access was not granted. Your saved photos are unchanged.'); return; }
      const result = source === 'camera'
        ? await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.9 })
        : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsMultipleSelection: true, quality: 0.9, selectionLimit: 6 - images.length });
      if (!result.canceled) setImages(current => appendListingPhotos(current, result.assets || []));
    } catch { setError('Unable to open photos. Try again or choose the photo library.'); }
    finally { setPicking(false); }
  }
  return <View>{error ? <Text accessibilityRole="alert" style={props.styles.error}>{error}</Text> : null}
    <ListingAgentChat {...props} hideComposer images={images} onBusyChange={setChildBusy} onClearPhotos={() => setImages([])} onPickPhotos={() => Alert.alert('Add listing photos', 'Choose a photo source.', [
      { text: 'Take photo', onPress: () => pick('camera') }, { text: 'Photo library', onPress: () => pick('library') }, { text: 'Cancel', style: 'cancel' },
    ])} />
  </View>;
}
