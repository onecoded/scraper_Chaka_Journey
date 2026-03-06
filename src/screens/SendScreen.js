import React, { useState, useMemo } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, TextInput,
  StyleSheet, Alert, Switch, ScrollView, SafeAreaView,
} from 'react-native';
import * as SMS from 'expo-sms';
import { useApp } from '../context/AppContext';
import KeywordBadge from '../components/KeywordBadge';

function ContactRow({ contact, selected, onToggle }) {
  return (
    <TouchableOpacity style={[styles.row, selected && styles.rowSelected]} onPress={onToggle} activeOpacity={0.7}>
      <View style={[styles.avatar, selected && styles.avatarSelected]}>
        <Text style={styles.avatarText}>
          {selected ? '✓' : contact.name.charAt(0).toUpperCase()}
        </Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.rowName}>{contact.name}</Text>
        <Text style={styles.rowPhone}>{contact.phone}</Text>
        <View style={styles.kwRow}>
          {(contact.keywords || []).map((kw) => (
            <KeywordBadge key={kw} keyword={kw} selected small />
          ))}
        </View>
      </View>
    </TouchableOpacity>
  );
}

export default function SendScreen() {
  const { contacts, allKeywords, addMessageRecord } = useApp();

  const [selectedKeywords, setSelectedKeywords] = useState([]);
  const [selectedContacts, setSelectedContacts] = useState([]);
  const [messageText, setMessageText] = useState('');
  const [groupMode, setGroupMode] = useState(false); // false = individual, true = group thread
  const [step, setStep] = useState('filter'); // 'filter' | 'compose'

  const filteredContacts = useMemo(() => {
    if (selectedKeywords.length === 0) return contacts;
    return contacts.filter((c) =>
      selectedKeywords.some((kw) => (c.keywords || []).map((k) => k.toLowerCase()).includes(kw))
    );
  }, [contacts, selectedKeywords]);

  const toggleKeyword = (kw) => {
    setSelectedKeywords((prev) =>
      prev.includes(kw) ? prev.filter((k) => k !== kw) : [...prev, kw]
    );
    // Reset contact selection when filter changes
    setSelectedContacts([]);
  };

  const toggleContact = (id) => {
    setSelectedContacts((prev) =>
      prev.includes(id) ? prev.filter((cid) => cid !== id) : [...prev, id]
    );
  };

  const selectAll = () => {
    setSelectedContacts(filteredContacts.map((c) => c.id));
  };

  const clearSelection = () => setSelectedContacts([]);

  const chosenContacts = contacts.filter((c) => selectedContacts.includes(c.id));
  const phones = chosenContacts.map((c) => c.phone);

  const handleSend = async () => {
    if (phones.length === 0) {
      Alert.alert('No recipients', 'Please select at least one contact.');
      return;
    }
    if (!messageText.trim()) {
      Alert.alert('Empty message', 'Please type a message before sending.');
      return;
    }

    const available = await SMS.isAvailableAsync();
    if (!available) {
      Alert.alert(
        'SMS not available',
        'This device cannot send SMS. On a simulator, use a real iPhone to send texts.'
      );
      return;
    }

    try {
      const recipients = groupMode ? phones : phones; // expo-sms handles both
      const { result } = await SMS.sendSMSAsync(recipients, messageText.trim(), {});

      if (result === 'sent' || result === 'unknown') {
        addMessageRecord({
          message: messageText.trim(),
          recipients: chosenContacts.map((c) => ({ id: c.id, name: c.name, phone: c.phone })),
          keywords: selectedKeywords,
          groupMode,
        });
        Alert.alert('Done', groupMode ? 'Group message sent!' : 'Individual messages queued!', [
          { text: 'OK', onPress: () => { setMessageText(''); setStep('filter'); setSelectedContacts([]); } },
        ]);
      }
    } catch (err) {
      Alert.alert('Error', 'Could not open SMS app: ' + err.message);
    }
  };

  if (step === 'compose') {
    return (
      <SafeAreaView style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => setStep('filter')}>
            <Text style={styles.backBtn}>‹ Back</Text>
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Compose Message</Text>
          <View style={{ width: 60 }} />
        </View>

        <ScrollView style={{ flex: 1 }} keyboardShouldPersistTaps="handled">
          {/* Recipients Summary */}
          <View style={styles.section}>
            <Text style={styles.sectionLabel}>To ({chosenContacts.length})</Text>
            <View style={styles.recipientChips}>
              {chosenContacts.map((c) => (
                <View key={c.id} style={styles.chip}>
                  <Text style={styles.chipText}>{c.name}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Group vs Individual toggle */}
          <View style={styles.section}>
            <View style={styles.toggleRow}>
              <View>
                <Text style={styles.toggleLabel}>
                  {groupMode ? 'Group Message' : 'Individual Messages'}
                </Text>
                <Text style={styles.toggleHint}>
                  {groupMode
                    ? 'Everyone sees the same thread'
                    : 'Each person gets a separate text'}
                </Text>
              </View>
              <Switch
                value={groupMode}
                onValueChange={setGroupMode}
                trackColor={{ false: '#ccc', true: '#007AFF' }}
                thumbColor="#fff"
              />
            </View>
          </View>

          {/* Message Body */}
          <View style={styles.section}>
            <Text style={styles.sectionLabel}>Message</Text>
            <TextInput
              style={styles.messageInput}
              value={messageText}
              onChangeText={setMessageText}
              placeholder="Type your message here…"
              placeholderTextColor="#999"
              multiline
              numberOfLines={6}
              textAlignVertical="top"
            />
            <Text style={styles.charCount}>{messageText.length} characters</Text>
          </View>
        </ScrollView>

        <View style={styles.sendBar}>
          <TouchableOpacity style={styles.sendBtn} onPress={handleSend}>
            <Text style={styles.sendBtnText}>
              {groupMode ? `Send Group Text` : `Send ${phones.length} Individual Text${phones.length !== 1 ? 's' : ''}`}
            </Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // Step: filter + select contacts
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Send Message</Text>
      </View>

      {/* Keyword filter pills */}
      <View style={styles.filterSection}>
        <Text style={styles.sectionLabel}>Filter by Keyword</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ paddingVertical: 4 }}>
          {allKeywords.map((kw) => (
            <KeywordBadge
              key={kw}
              keyword={kw}
              selected={selectedKeywords.includes(kw)}
              onPress={() => toggleKeyword(kw)}
            />
          ))}
        </ScrollView>
        {selectedKeywords.length > 0 && (
          <TouchableOpacity onPress={() => { setSelectedKeywords([]); setSelectedContacts([]); }}>
            <Text style={styles.clearFilter}>Clear filter</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Select all / clear */}
      <View style={styles.selectionBar}>
        <Text style={styles.selectionCount}>
          {selectedContacts.length} of {filteredContacts.length} selected
        </Text>
        <TouchableOpacity onPress={selectedContacts.length === filteredContacts.length ? clearSelection : selectAll}>
          <Text style={styles.selectionAction}>
            {selectedContacts.length === filteredContacts.length ? 'Deselect All' : 'Select All'}
          </Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={filteredContacts}
        keyExtractor={(c) => c.id}
        renderItem={({ item }) => (
          <ContactRow
            contact={item}
            selected={selectedContacts.includes(item.id)}
            onToggle={() => toggleContact(item.id)}
          />
        )}
        contentContainerStyle={{ paddingBottom: 100 }}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No contacts match these keywords.</Text>
          </View>
        }
      />

      {selectedContacts.length > 0 && (
        <View style={styles.sendBar}>
          <TouchableOpacity style={styles.sendBtn} onPress={() => setStep('compose')}>
            <Text style={styles.sendBtnText}>
              Compose Message → {selectedContacts.length} contact{selectedContacts.length !== 1 ? 's' : ''}
            </Text>
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F2F2F7' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 14, backgroundColor: '#fff',
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#C8C8CC',
  },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#000' },
  backBtn: { fontSize: 17, color: '#007AFF', width: 60 },
  filterSection: {
    backgroundColor: '#fff', padding: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#E5E5EA',
  },
  sectionLabel: {
    fontSize: 12, fontWeight: '700', color: '#6E6E73',
    textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6,
  },
  clearFilter: { color: '#FF3B30', fontSize: 13, marginTop: 6 },
  selectionBar: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 8,
    backgroundColor: '#F2F2F7',
  },
  selectionCount: { fontSize: 13, color: '#6E6E73' },
  selectionAction: { fontSize: 14, color: '#007AFF', fontWeight: '600' },
  row: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: '#fff', marginHorizontal: 12, marginTop: 6,
    borderRadius: 12, padding: 12,
    shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 3, elevation: 1,
  },
  rowSelected: { borderWidth: 2, borderColor: '#007AFF' },
  avatar: {
    width: 42, height: 42, borderRadius: 21, backgroundColor: '#C7C7CC',
    alignItems: 'center', justifyContent: 'center', marginRight: 12,
  },
  avatarSelected: { backgroundColor: '#007AFF' },
  avatarText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  rowName: { fontSize: 15, fontWeight: '600', color: '#000' },
  rowPhone: { fontSize: 12, color: '#888', marginTop: 1 },
  kwRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 3 },
  empty: { alignItems: 'center', marginTop: 60 },
  emptyText: { color: '#999', fontSize: 16 },
  sendBar: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    padding: 16, backgroundColor: 'rgba(242,242,247,0.95)',
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#C8C8CC',
  },
  sendBtn: {
    backgroundColor: '#007AFF', borderRadius: 14,
    paddingVertical: 14, alignItems: 'center',
  },
  sendBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  // Compose step
  section: {
    backgroundColor: '#fff', marginHorizontal: 12, marginTop: 12,
    borderRadius: 12, padding: 14,
    shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 3, elevation: 1,
  },
  recipientChips: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 4 },
  chip: {
    backgroundColor: '#007AFF20', borderRadius: 10, borderWidth: 1,
    borderColor: '#007AFF', paddingHorizontal: 10, paddingVertical: 4, margin: 2,
  },
  chipText: { color: '#007AFF', fontSize: 13, fontWeight: '600' },
  toggleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  toggleLabel: { fontSize: 15, fontWeight: '600', color: '#000' },
  toggleHint: { fontSize: 12, color: '#888', marginTop: 2, maxWidth: 220 },
  messageInput: {
    backgroundColor: '#F2F2F7', borderRadius: 10, padding: 12,
    fontSize: 16, color: '#000', minHeight: 120, marginTop: 6,
  },
  charCount: { fontSize: 12, color: '#999', textAlign: 'right', marginTop: 4 },
});
