import React, { useMemo, useRef, useState } from 'react';
import { Linking, Modal, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { SUPPORT_CATEGORIES, SUPPORT_CONTACT, searchSupportArticles, supportEmailUrl } from '../../../../packages/app-client/src/supportContent.mjs';

export default function HelpSupport({ buttonStyle, textStyle }) {
  const scrollRef = useRef(null);
  const contactPosition = useRef(0);
  const [visible, setVisible] = useState(false);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All topics');
  const [expanded, setExpanded] = useState('');
  const [linkError, setLinkError] = useState('');
  const articles = useMemo(() => searchSupportArticles(query, category), [query, category]);
  async function openLink(url) {
    setLinkError('');
    try { await Linking.openURL(url); }
    catch { setLinkError(`Could not open the link. You can email ${SUPPORT_CONTACT.email} or call ${SUPPORT_CONTACT.phone}.`); }
  }
  function close() { setVisible(false); setQuery(''); setCategory('All topics'); setExpanded(''); setLinkError(''); }
  return <>
    <TouchableOpacity style={buttonStyle} accessibilityRole="button" onPress={() => setVisible(true)}><Text style={textStyle}>Help &amp; Support</Text></TouchableOpacity>
    <Modal visible={visible} animationType="slide" presentationStyle="fullScreen" onRequestClose={close}>
      <SafeAreaProvider><SafeAreaView style={s.root} edges={['top', 'right', 'bottom', 'left']}>
        <View style={s.header}><Text accessibilityRole="header" style={s.title}>Help &amp; Support</Text><TouchableOpacity accessibilityRole="button" accessibilityLabel="Close help and support" style={s.button} onPress={close}><Text style={s.buttonText}>Close</Text></TouchableOpacity></View>
        <ScrollView ref={scrollRef} contentContainerStyle={s.content} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
          <Text style={s.text}>Find an answer, get unstuck, or reach the Jouft team.</Text>
          <TouchableOpacity accessibilityRole="button" onPress={() => scrollRef.current?.scrollTo({ y: contactPosition.current, animated: true })}><Text style={s.link}>Contact the team</Text></TouchableOpacity>
          <Text style={s.label}>Search help</Text>
          <TextInput style={s.input} accessibilityLabel="Search help" placeholder="Try publish, AI preview, or shipping" value={query} onChangeText={setQuery} maxLength={160} autoCapitalize="none" autoCorrect={false} clearButtonMode="while-editing" returnKeyType="search" />
          <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={s.topics} keyboardShouldPersistTaps="handled">
            {['All topics', ...SUPPORT_CATEGORIES].map(topic => <TouchableOpacity key={topic} accessibilityRole="button" accessibilityState={{ selected: category === topic }} style={[s.topic, category === topic && s.selected]} onPress={() => { setCategory(topic); setQuery(''); setExpanded(''); }}><Text style={[s.buttonText, category === topic && s.selectedText]}>{topic}</Text></TouchableOpacity>)}
          </ScrollView>
          <Text accessibilityRole="header" style={s.heading}>{category === 'All topics' ? 'Common questions' : category}</Text>
          <Text accessibilityLiveRegion="polite" style={s.text}>{articles.length} {articles.length === 1 ? 'answer' : 'answers'}</Text>
          {articles.length === 0 ? <View style={s.card}><Text style={s.heading}>No answers found</Text><Text style={s.text}>Try a shorter search or contact us below.</Text><TouchableOpacity style={s.button} accessibilityRole="button" onPress={() => { setQuery(''); setCategory('All topics'); }}><Text style={s.buttonText}>Clear search and filters</Text></TouchableOpacity></View> : articles.map(article => <View key={article.id} style={s.article}>
            <TouchableOpacity style={s.question} accessibilityRole="button" accessibilityState={{ expanded: expanded === article.id }} onPress={() => setExpanded(expanded === article.id ? '' : article.id)}><Text style={s.questionText}>{article.title}</Text><Text style={s.expand} accessible={false}>{expanded === article.id ? '−' : '+'}</Text></TouchableOpacity>
            {expanded === article.id && <View style={s.answer}>{article.body.map(paragraph => <Text key={paragraph} style={s.text}>{paragraph}</Text>)}{article.links?.map(link => <TouchableOpacity key={link.path} accessibilityRole="link" onPress={() => openLink(`https://jouft.com${link.path}`)}><Text style={s.link}>{link.label}</Text></TouchableOpacity>)}</View>}
          </View>)}
          <View style={s.card} onLayout={event => { contactPosition.current = event.nativeEvent.layout.y; }}>
            <Text accessibilityRole="header" style={s.heading}>Contact Jouft</Text>
            <Text style={s.text}>For a listing problem, email us with your account email, listing or trade reference, device/app version, and what happened.</Text>
            <TouchableOpacity accessibilityRole="link" style={[s.button, s.selected]} onPress={() => openLink(supportEmailUrl(category === 'All topics' ? '' : category))}><Text style={s.selectedText}>Email support</Text></TouchableOpacity>
            <Text style={s.text}>Opens a draft in your email app. Review and send it to contact us; opening a draft does not submit a request.</Text>
            <Text selectable style={s.text}>{SUPPORT_CONTACT.email}</Text>
            <TouchableOpacity accessibilityRole="link" onPress={() => openLink(SUPPORT_CONTACT.phoneUrl)}><Text style={s.link}>Call {SUPPORT_CONTACT.phone}</Text></TouchableOpacity>
            <Text style={s.text}>Attach a screenshot with private details hidden if useful. Never send passwords, verification codes, or full card details.</Text>
            {linkError ? <Text accessibilityRole="alert" style={s.error}>{linkError}</Text> : null}
            {[['Privacy Policy', '/privacy'], ['Terms', '/terms'], ['Data deletion', '/data-deletion']].map(([label, path]) => <TouchableOpacity key={path} accessibilityRole="link" onPress={() => openLink(`https://jouft.com${path}`)}><Text style={s.link}>{label}</Text></TouchableOpacity>)}
          </View>
        </ScrollView>
      </SafeAreaView></SafeAreaProvider>
    </Modal>
  </>;
}
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#f8f5ef' },
  header: { padding: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderBottomWidth: 1, borderColor: '#d7cec5' },
  title: { flex: 1, fontSize: 23, fontWeight: '700', color: '#53191f' },
  heading: { fontSize: 21, fontWeight: '700', color: '#35262a' },
  content: { padding: 18, gap: 14 }, text: { color: '#4f5560', fontSize: 15, lineHeight: 24 },
  label: { color: '#35262a', fontSize: 15, fontWeight: '700' },
  input: { minHeight: 48, borderWidth: 1, borderColor: '#b8aca2', backgroundColor: '#fff', padding: 12, color: '#121a24', fontSize: 16 },
  topics: { gap: 8, paddingVertical: 6 }, topic: { padding: 12, borderWidth: 1, borderColor: '#d7cec5', justifyContent: 'center' },
  selected: { backgroundColor: '#53191f', borderColor: '#53191f' }, selectedText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  button: { minHeight: 44, borderWidth: 1, borderColor: '#b8aca2', padding: 12, alignItems: 'center', justifyContent: 'center' }, buttonText: { fontSize: 14, fontWeight: '600', color: '#53191f' },
  article: { borderBottomWidth: 1, borderColor: '#d7cec5' }, question: { paddingVertical: 14, flexDirection: 'row', gap: 12, alignItems: 'center' },
  questionText: { flex: 1, fontSize: 17, lineHeight: 25, fontWeight: '600', color: '#35262a' }, expand: { fontSize: 24, color: '#53191f' },
  answer: { paddingBottom: 16, gap: 12 }, card: { padding: 18, borderWidth: 1, borderColor: '#d7cec5', backgroundColor: '#fff', gap: 14, marginTop: 10 },
  link: { color: '#53191f', textDecorationLine: 'underline', fontSize: 15, paddingVertical: 6 }, error: { color: '#9a251d', fontSize: 15 },
});
