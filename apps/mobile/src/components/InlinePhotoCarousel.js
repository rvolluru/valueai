import React, { useRef, useState } from 'react';
import { Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { nextGalleryIndex } from '../lib/galleryPaging.mjs';
import { isMannequinImage, MANNEQUIN_DISCLAIMER } from '../../../../packages/app-client/src/mannequinDisclosure';

export default function InlinePhotoCarousel({ images, onOpen, listing }) {
  const pager = useRef(null);
  const [width, setWidth] = useState(0);
  const [index, setIndex] = useState(0);
  const [failed, setFailed] = useState({});
  function move(step) {
    const next = nextGalleryIndex(index, step, images.length);
    setIndex(next);
    pager.current?.scrollTo({ x: next * width, animated: true });
  }
  return <View onLayout={({ nativeEvent }) => {
    const nextWidth = nativeEvent.layout.width;
    if (nextWidth !== width) {
      setWidth(nextWidth);
      pager.current?.scrollTo({ x: index * nextWidth, animated: false });
    }
  }}>
    <View>
    {width > 0 && <ScrollView ref={pager} horizontal pagingEnabled showsHorizontalScrollIndicator={false}
      onMomentumScrollEnd={({ nativeEvent }) => setIndex(nextGalleryIndex(Math.round(nativeEvent.contentOffset.x / width), 0, images.length))}>
      {images.map((src, idx) => <TouchableOpacity key={`${src}-${idx}`} accessibilityLabel={`Magnify photo ${idx + 1}`} onPress={() => onOpen(idx)} style={{ width, flexShrink: 0 }}>
        {failed[src] ? <View style={{ width, height: 400, alignItems: 'center', justifyContent: 'center' }}><Text>Image unavailable</Text></View>
          : <Image source={{ uri: src }} style={{ width, height: 400 }} resizeMode="contain" onError={() => setFailed(previous => ({ ...previous, [src]: true }))} />}
      </TouchableOpacity>)}
    </ScrollView>}
    {images.length > 1 && <View pointerEvents="box-none" style={styles.controls}>
      <TouchableOpacity accessibilityRole="button" accessibilityLabel="Previous photo" disabled={index === 0 || !width} style={[styles.arrow, index === 0 && styles.disabled]} onPress={() => move(-1)}><Ionicons name="chevron-back" size={24} color="#4a161b" /></TouchableOpacity>
      <Text style={styles.count} accessibilityLiveRegion="polite">{index + 1} / {images.length}</Text>
      <TouchableOpacity accessibilityRole="button" accessibilityLabel="Next photo" disabled={index === images.length - 1 || !width} style={[styles.arrow, index === images.length - 1 && styles.disabled]} onPress={() => move(1)}><Ionicons name="chevron-forward" size={24} color="#4a161b" /></TouchableOpacity>
    </View>}
    </View>
    {isMannequinImage(listing, images[index]) && <Text style={styles.disclaimer}>{MANNEQUIN_DISCLAIMER}</Text>}
  </View>;
}
const styles = StyleSheet.create({
  disclaimer: { color: '#655f59', fontSize: 12, lineHeight: 18, marginTop: 8 },
  controls: { position: 'absolute', top: 0, bottom: 0, left: 8, right: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  arrow: { minWidth: 48, minHeight: 48, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.8)' },
  count: { position: 'absolute', bottom: 12, alignSelf: 'center', left: '40%', right: '40%', textAlign: 'center', padding: 4, borderRadius: 12, backgroundColor: 'rgba(255,255,255,0.85)' },
  disabled: { opacity: 0.3 },
});
