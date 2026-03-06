import React, { createContext, useContext, useState, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const AppContext = createContext(null);

// Sample seed contacts so the app works without device contacts permission
const SEED_CONTACTS = [
  { id: '1', name: 'Alice Johnson', phone: '+15551234001', keywords: ['family', 'vip'] },
  { id: '2', name: 'Bob Smith',     phone: '+15551234002', keywords: ['work', 'team'] },
  { id: '3', name: 'Carol Davis',   phone: '+15551234003', keywords: ['family', 'friends'] },
  { id: '4', name: 'David Lee',     phone: '+15551234004', keywords: ['work', 'vip'] },
  { id: '5', name: 'Eva Martinez',  phone: '+15551234005', keywords: ['friends', 'team'] },
  { id: '6', name: 'Frank Wilson',  phone: '+15551234006', keywords: ['work'] },
];

export function AppProvider({ children }) {
  const [contacts, setContacts] = useState([]);
  const [allKeywords, setAllKeywords] = useState([]);
  const [messageHistory, setMessageHistory] = useState([]);
  const [loaded, setLoaded] = useState(false);

  // Persist & hydrate from AsyncStorage
  useEffect(() => {
    (async () => {
      try {
        const stored = await AsyncStorage.getItem('@contacts');
        const storedHistory = await AsyncStorage.getItem('@messageHistory');
        if (stored) {
          const parsed = JSON.parse(stored);
          setContacts(parsed);
          rebuildKeywords(parsed);
        } else {
          setContacts(SEED_CONTACTS);
          rebuildKeywords(SEED_CONTACTS);
        }
        if (storedHistory) {
          setMessageHistory(JSON.parse(storedHistory));
        }
      } catch (_) {}
      setLoaded(true);
    })();
  }, []);

  const persist = async (updated) => {
    try {
      await AsyncStorage.setItem('@contacts', JSON.stringify(updated));
    } catch (_) {}
  };

  const persistHistory = async (updated) => {
    try {
      await AsyncStorage.setItem('@messageHistory', JSON.stringify(updated));
    } catch (_) {}
  };

  const rebuildKeywords = (list) => {
    const set = new Set();
    list.forEach((c) => (c.keywords || []).forEach((k) => set.add(k.toLowerCase())));
    setAllKeywords([...set].sort());
  };

  const addContact = (contact) => {
    const updated = [...contacts, { ...contact, id: Date.now().toString(), keywords: contact.keywords || [] }];
    setContacts(updated);
    rebuildKeywords(updated);
    persist(updated);
  };

  const updateContact = (id, changes) => {
    const updated = contacts.map((c) => (c.id === id ? { ...c, ...changes } : c));
    setContacts(updated);
    rebuildKeywords(updated);
    persist(updated);
  };

  const deleteContact = (id) => {
    const updated = contacts.filter((c) => c.id !== id);
    setContacts(updated);
    rebuildKeywords(updated);
    persist(updated);
  };

  const getContactsByKeywords = (keywords) => {
    if (!keywords || keywords.length === 0) return contacts;
    return contacts.filter((c) =>
      keywords.some((kw) => (c.keywords || []).map((k) => k.toLowerCase()).includes(kw.toLowerCase()))
    );
  };

  const addMessageRecord = (record) => {
    const updated = [{ ...record, id: Date.now().toString(), timestamp: new Date().toISOString() }, ...messageHistory];
    setMessageHistory(updated);
    persistHistory(updated);
  };

  return (
    <AppContext.Provider
      value={{
        contacts,
        allKeywords,
        messageHistory,
        loaded,
        addContact,
        updateContact,
        deleteContact,
        getContactsByKeywords,
        addMessageRecord,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export const useApp = () => useContext(AppContext);
