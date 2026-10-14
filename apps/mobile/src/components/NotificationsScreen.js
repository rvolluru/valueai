import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native';

export default function NotificationsScreen({ load, markRead, onOpen, onBack }) {
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [more, setMore] = useState(false);
  async function fetchPage(reset = false) {
    setBusy(true); setError('');
    try {
      const result = await load(reset ? 0 : items.length);
      setItems(previous => reset ? result.items : [...previous, ...result.items.filter(item => !previous.some(old => old.notification_id === item.notification_id))]);
      setMore(Boolean(result.has_more));
    } catch { setError('Unable to load notifications. Please try again.'); }
    finally { setBusy(false); }
  }
  useEffect(() => { fetchPage(true); }, []);
  async function open(item) {
    try {
      if (!item.read_at) await markRead(item.notification_id);
      setItems(previous => previous.map(old => old.notification_id === item.notification_id ? { ...old, read_at: new Date().toISOString() } : old));
      if (item.action_tab) onOpen(item);
    } catch { setError('Unable to update this notification. Please try again.'); }
  }
  const button = (label, action, disabled = false) => <TouchableOpacity accessibilityRole="button" style={styles.action} disabled={disabled} onPress={action}><Text style={styles.label}>{label}</Text></TouchableOpacity>;
  return <View style={styles.screen}><View style={styles.row}>{button('Back', onBack)}<Text style={styles.title}>Notifications</Text>{button('Refresh', () => fetchPage(true), busy)}</View>
    <Text style={styles.body}>Your trade updates, listing activity, and shipping notifications.</Text>
    {error ? <Text accessibilityRole="alert" style={styles.body}>{error}</Text> : null}
    {!busy && !items.length && !error ? <Text style={styles.body}>No notifications yet. Your updates will appear here.</Text> : null}
    {items.map(item => <TouchableOpacity accessibilityRole="button" key={item.notification_id} style={[styles.item, !item.read_at && styles.unread]} onPress={() => open(item)}>
      <Text style={styles.heading}>{item.title}{item.read_at ? '' : ' • Unread'}</Text><Text style={styles.body}>{item.body}</Text><Text style={styles.date}>{new Date(item.created_at).toLocaleString()}</Text>
    </TouchableOpacity>)}
    {busy ? <ActivityIndicator /> : null}{more ? button('Load older notifications', () => fetchPage(), busy) : null}
  </View>;
}
const styles = StyleSheet.create({ screen: { padding: 16, backgroundColor: '#f8f4ee' }, row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }, action: { padding: 12, minHeight: 44 }, label: { color: '#64141f' }, title: { fontSize: 26, color: '#64141f', fontFamily: 'BodoniModa_500Medium' }, heading: { fontSize: 17, color: '#64141f', fontFamily: 'PlusJakartaSans_600SemiBold' }, item: { padding: 16, marginVertical: 6, backgroundColor: 'white', borderWidth: 1, borderColor: '#ded6cc' }, unread: { borderLeftWidth: 4, borderLeftColor: '#64141f' }, body: { color: '#514b46', marginVertical: 8, fontSize: 14 }, date: { color: '#746c64', fontSize: 12 } });
