import React, { useState } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, TextInput,
  StyleSheet, Alert, Modal, ScrollView, SafeAreaView,
} from 'react-native';
import { useApp } from '../context/AppContext';
import KeywordBadge from '../components/KeywordBadge';

function ContactCard({ contact, onEdit, onDelete }) {
  return (
    <View style={styles.card}>
      <View style={styles.avatar}>
        <Text style={styles.avatarText}>{contact.name.charAt(0).toUpperCase()}</Text>
      </View>
      <View style={styles.cardInfo}>
        <Text style={styles.cardName}>{contact.name}</Text>
        <Text style={styles.cardPhone}>{contact.phone}</Text>
        <View style={styles.keywordRow}>
          {(contact.keywords || []).map((kw) => (
            <KeywordBadge key={kw} keyword={kw} selected small />
          ))}
        </View>
      </View>
      <View style={styles.cardActions}>
        <TouchableOpacity onPress={() => onEdit(contact)} style={styles.actionBtn}>
          <Text style={styles.editIcon}>✏️</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => onDelete(contact.id)} style={styles.actionBtn}>
          <Text style={styles.deleteIcon}>🗑️</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function ContactModal({ visible, contact, allKeywords, onSave, onClose }) {
  const [name, setName] = useState(contact?.name || '');
  const [phone, setPhone] = useState(contact?.phone || '');
  const [selectedKws, setSelectedKws] = useState(contact?.keywords || []);
  const [newKw, setNewKw] = useState('');

  const isEdit = !!contact;

  const toggleKw = (kw) => {
    setSelectedKws((prev) =>
      prev.includes(kw) ? prev.filter((k) => k !== kw) : [...prev, kw]
    );
  };

  const addNewKw = () => {
    const trimmed = newKw.trim().toLowerCase();
    if (trimmed && !selectedKws.includes(trimmed)) {
      setSelectedKws((prev) => [...prev, trimmed]);
    }
    setNewKw('');
  };

  const handleSave = () => {
    if (!name.trim() || !phone.trim()) {
      Alert.alert('Missing Info', 'Please enter a name and phone number.');
      return;
    }
    onSave({ name: name.trim(), phone: phone.trim(), keywords: selectedKws });
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <SafeAreaView style={styles.modal}>
        <View style={styles.modalHeader}>
          <TouchableOpacity onPress={onClose}>
            <Text style={styles.cancelBtn}>Cancel</Text>
          </TouchableOpacity>
          <Text style={styles.modalTitle}>{isEdit ? 'Edit Contact' : 'New Contact'}</Text>
          <TouchableOpacity onPress={handleSave}>
            <Text style={styles.saveBtn}>Save</Text>
          </TouchableOpacity>
        </View>

        <ScrollView style={styles.modalBody} keyboardShouldPersistTaps="handled">
          <Text style={styles.fieldLabel}>Name</Text>
          <TextInput
            style={styles.input}
            value={name}
            onChangeText={setName}
            placeholder="Full name"
            placeholderTextColor="#999"
          />

          <Text style={styles.fieldLabel}>Phone Number</Text>
          <TextInput
            style={styles.input}
            value={phone}
            onChangeText={setPhone}
            placeholder="+1 (555) 000-0000"
            placeholderTextColor="#999"
            keyboardType="phone-pad"
          />

          <Text style={styles.fieldLabel}>Keywords</Text>
          <Text style={styles.fieldHint}>Tap to toggle existing keywords, or add new ones</Text>

          <View style={styles.kwGrid}>
            {allKeywords.map((kw) => (
              <KeywordBadge
                key={kw}
                keyword={kw}
                selected={selectedKws.includes(kw)}
                onPress={() => toggleKw(kw)}
              />
            ))}
          </View>

          <View style={styles.addKwRow}>
            <TextInput
              style={[styles.input, { flex: 1, marginBottom: 0 }]}
              value={newKw}
              onChangeText={setNewKw}
              placeholder="Add new keyword…"
              placeholderTextColor="#999"
              onSubmitEditing={addNewKw}
              returnKeyType="done"
            />
            <TouchableOpacity onPress={addNewKw} style={styles.addKwBtn}>
              <Text style={styles.addKwBtnText}>Add</Text>
            </TouchableOpacity>
          </View>

          {selectedKws.length > 0 && (
            <View style={{ marginTop: 12 }}>
              <Text style={styles.fieldLabel}>Selected Keywords</Text>
              <View style={styles.kwGrid}>
                {selectedKws.map((kw) => (
                  <KeywordBadge
                    key={kw}
                    keyword={kw}
                    selected
                    onPress={() => toggleKw(kw)}
                  />
                ))}
              </View>
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

export default function ContactsScreen() {
  const { contacts, allKeywords, addContact, updateContact, deleteContact } = useApp();
  const [search, setSearch] = useState('');
  const [modalVisible, setModalVisible] = useState(false);
  const [editTarget, setEditTarget] = useState(null);

  const filtered = contacts.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.phone.includes(search) ||
    (c.keywords || []).some((k) => k.toLowerCase().includes(search.toLowerCase()))
  );

  const handleSave = (data) => {
    if (editTarget) {
      updateContact(editTarget.id, data);
    } else {
      addContact(data);
    }
    setModalVisible(false);
    setEditTarget(null);
  };

  const handleEdit = (contact) => {
    setEditTarget(contact);
    setModalVisible(true);
  };

  const handleDelete = (id) => {
    Alert.alert('Delete Contact', 'Remove this contact?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => deleteContact(id) },
    ]);
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.searchRow}>
        <TextInput
          style={styles.searchInput}
          value={search}
          onChangeText={setSearch}
          placeholder="Search name, phone, keyword…"
          placeholderTextColor="#999"
          clearButtonMode="while-editing"
        />
      </View>

      <FlatList
        data={filtered}
        keyExtractor={(c) => c.id}
        renderItem={({ item }) => (
          <ContactCard contact={item} onEdit={handleEdit} onDelete={handleDelete} />
        )}
        contentContainerStyle={{ paddingBottom: 100 }}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No contacts found.</Text>
          </View>
        }
      />

      <TouchableOpacity
        style={styles.fab}
        onPress={() => { setEditTarget(null); setModalVisible(true); }}
      >
        <Text style={styles.fabText}>＋</Text>
      </TouchableOpacity>

      <ContactModal
        visible={modalVisible}
        contact={editTarget}
        allKeywords={allKeywords}
        onSave={handleSave}
        onClose={() => { setModalVisible(false); setEditTarget(null); }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F2F2F7' },
  searchRow: { padding: 12, backgroundColor: '#fff', borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#C8C8CC' },
  searchInput: {
    backgroundColor: '#F2F2F7', borderRadius: 10, paddingHorizontal: 12,
    paddingVertical: 8, fontSize: 16, color: '#000',
  },
  card: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff',
    marginHorizontal: 12, marginTop: 8, borderRadius: 12, padding: 12,
    shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 4, elevation: 2,
  },
  avatar: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: '#007AFF',
    alignItems: 'center', justifyContent: 'center', marginRight: 12,
  },
  avatarText: { color: '#fff', fontSize: 18, fontWeight: '700' },
  cardInfo: { flex: 1 },
  cardName: { fontSize: 16, fontWeight: '600', color: '#000' },
  cardPhone: { fontSize: 13, color: '#666', marginTop: 1 },
  keywordRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 4 },
  cardActions: { flexDirection: 'row' },
  actionBtn: { padding: 6 },
  editIcon: { fontSize: 18 },
  deleteIcon: { fontSize: 18 },
  fab: {
    position: 'absolute', bottom: 28, right: 20,
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: '#007AFF', alignItems: 'center', justifyContent: 'center',
    shadowColor: '#007AFF', shadowOpacity: 0.4, shadowRadius: 8, elevation: 6,
  },
  fabText: { color: '#fff', fontSize: 28, lineHeight: 32 },
  empty: { alignItems: 'center', marginTop: 60 },
  emptyText: { color: '#999', fontSize: 16 },
  // Modal
  modal: { flex: 1, backgroundColor: '#F2F2F7' },
  modalHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 14, backgroundColor: '#fff',
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#C8C8CC',
  },
  modalTitle: { fontSize: 17, fontWeight: '600', color: '#000' },
  cancelBtn: { fontSize: 17, color: '#FF3B30' },
  saveBtn: { fontSize: 17, color: '#007AFF', fontWeight: '600' },
  modalBody: { padding: 16 },
  fieldLabel: { fontSize: 13, fontWeight: '600', color: '#6E6E73', marginTop: 16, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 },
  fieldHint: { fontSize: 12, color: '#999', marginBottom: 8 },
  input: {
    backgroundColor: '#fff', borderRadius: 10, paddingHorizontal: 14,
    paddingVertical: 11, fontSize: 16, color: '#000', marginBottom: 4,
    borderWidth: StyleSheet.hairlineWidth, borderColor: '#C8C8CC',
  },
  kwGrid: { flexDirection: 'row', flexWrap: 'wrap' },
  addKwRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  addKwBtn: {
    backgroundColor: '#007AFF', borderRadius: 10,
    paddingHorizontal: 16, paddingVertical: 11,
  },
  addKwBtnText: { color: '#fff', fontWeight: '600', fontSize: 15 },
});
