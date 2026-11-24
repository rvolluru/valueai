import React, { useState } from 'react';
import { Keyboard, Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const isoDate = (year, month, day) => `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

export default function BirthdayPicker({ value, onChange, inputStyle }) {
  const [open, setOpen] = useState(false);
  const [year, setYear] = useState(2000);
  const [month, setMonth] = useState(0);
  const [selected, setSelected] = useState('');
  const [selecting, setSelecting] = useState(null);
  const today = new Date();
  const latest = new Date(today.getFullYear() - 18, today.getMonth(), today.getDate());
  const maximum = isoDate(latest.getFullYear(), latest.getMonth(), latest.getDate());
  const years = Array.from({ length: latest.getFullYear() - 1900 + 1 }, (_, index) => latest.getFullYear() - index);
  const start = new Date(year, month, 1).getDay();
  const days = new Date(year, month + 1, 0).getDate();
  function show() {
    Keyboard.dismiss();
    const valid = /^\d{4}-\d{2}-\d{2}$/.test(value || '') && value <= maximum;
    const parts = valid ? value.split('-').map(Number) : [latest.getFullYear(), 1, 1];
    setYear(parts[0]); setMonth(parts[1] - 1); setSelected(valid ? value : ''); setSelecting(null); setOpen(true);
  }
  function move(delta) {
    const next = new Date(year, month + delta, 1);
    setYear(next.getFullYear()); setMonth(next.getMonth());
  }
  return <>
    <TouchableOpacity style={[inputStyle, styles.field]} onPress={show} accessibilityRole="button" accessibilityLabel={value ? `Birthday: ${value}. Choose date` : 'Choose birthday'}>
      <Text style={[styles.text, !value && styles.placeholder]}>{value || 'Select birthday'}</Text><Text style={styles.icon}>▦</Text>
    </TouchableOpacity>
    <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
      <View style={styles.backdrop}><View style={styles.card} accessibilityViewIsModal>
        <Text style={styles.title}>Birthday</Text>
        <Text style={styles.help}>Select your date of birth. You must be 18 or older.</Text>
        <View style={styles.row}>
          <TouchableOpacity accessibilityLabel="Previous month" disabled={year === 1900 && month === 0} onPress={() => move(-1)} style={styles.control}><Text>‹</Text></TouchableOpacity>
          <TouchableOpacity accessibilityLabel="Choose month" onPress={() => setSelecting(selecting === 'month' ? null : 'month')} style={styles.control}><Text>{months[month]} ▾</Text></TouchableOpacity>
          <TouchableOpacity accessibilityLabel="Choose year" onPress={() => setSelecting(selecting === 'year' ? null : 'year')} style={styles.control}><Text>{year} ▾</Text></TouchableOpacity>
          <TouchableOpacity accessibilityLabel="Next month" disabled={year === latest.getFullYear() && month >= latest.getMonth()} onPress={() => move(1)} style={styles.control}><Text>›</Text></TouchableOpacity>
        </View>
        {selecting ? <ScrollView style={styles.choices} keyboardShouldPersistTaps="handled">
          {(selecting === 'year' ? years : months).map((item, index) => <TouchableOpacity key={item} style={styles.choice} accessibilityRole="button" onPress={() => {
            if (selecting === 'year') { setYear(item); if (item === latest.getFullYear() && month > latest.getMonth()) setMonth(latest.getMonth()); }
            else setMonth(index);
            setSelecting(null);
          }}><Text>{item}</Text></TouchableOpacity>)}
        </ScrollView> : <View style={styles.calendar}>
          {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map(day => <View key={day} style={styles.day}><Text style={styles.help}>{day}</Text></View>)}
          {Array.from({ length: start + days }, (_, index) => {
            const day = index - start + 1;
            if (day < 1) return <View key={index} style={styles.day} />;
            const date = isoDate(year, month, day);
            const disabled = date > maximum;
            return <TouchableOpacity key={index} disabled={disabled} accessibilityRole="button" accessibilityLabel={date} accessibilityState={{ selected: selected === date, disabled }} onPress={() => setSelected(date)} style={[styles.day, selected === date && styles.selected]}>
              <Text style={[styles.text, disabled && styles.placeholder, selected === date && styles.selectedText]}>{day}</Text>
            </TouchableOpacity>;
          })}
        </View>}
        <View style={styles.actions}>
          <TouchableOpacity onPress={() => setOpen(false)} style={styles.control} accessibilityRole="button"><Text>Cancel</Text></TouchableOpacity>
          <TouchableOpacity disabled={!selected} onPress={() => { onChange(selected); setOpen(false); }} style={[styles.confirm, !selected && { opacity: .4 }]} accessibilityRole="button"><Text style={styles.selectedText}>Use date</Text></TouchableOpacity>
        </View>
      </View></View>
    </Modal>
  </>;
}
const styles = StyleSheet.create({
  field: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 48 },
  text: { fontSize: 16, color: '#171511' }, placeholder: { color: '#999' }, icon: { color: '#5a121b', fontSize: 22 },
  backdrop: { flex: 1, backgroundColor: '#0007', justifyContent: 'center', padding: 20 },
  card: { backgroundColor: '#fbf8f2', padding: 20, width: '100%', maxWidth: 420, alignSelf: 'center', borderRadius: 8 },
  title: { fontSize: 22, fontWeight: '600', color: '#5a121b' }, help: { fontSize: 13, color: '#6f675f', marginVertical: 8 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, control: { padding: 12, minHeight: 44 },
  calendar: { flexDirection: 'row', flexWrap: 'wrap' }, day: { width: '14.2857%', minHeight: 42, alignItems: 'center', justifyContent: 'center' },
  selected: { backgroundColor: '#5a121b', borderRadius: 4 }, selectedText: { color: '#fff', fontWeight: '600' },
  choices: { height: 285 }, choice: { minHeight: 44, padding: 12, borderBottomWidth: 1, borderBottomColor: '#e5dfd7' },
  actions: { flexDirection: 'row', justifyContent: 'flex-end', alignItems: 'center', marginTop: 12, gap: 12 }, confirm: { backgroundColor: '#5a121b', padding: 14 },
});
