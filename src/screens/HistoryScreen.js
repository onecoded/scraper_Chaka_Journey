import React from 'react';
import {
  View, Text, FlatList, StyleSheet, SafeAreaView,
} from 'react-native';
import { useApp } from '../context/AppContext';
import KeywordBadge from '../components/KeywordBadge';

function HistoryCard({ record }) {
  const date = new Date(record.timestamp);
  const label = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  const time = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

  return (
    <View style={styles.card}>
      <View style={styles.cardTop}>
        <Text style={styles.modeTag}>{record.groupMode ? '👥 Group' : '💬 Individual'}</Text>
        <Text style={styles.timestamp}>{label} · {time}</Text>
      </View>

      <Text style={styles.messageText} numberOfLines={3}>{record.message}</Text>

      {record.keywords && record.keywords.length > 0 && (
        <View style={styles.kwRow}>
          <Text style={styles.kwLabel}>Keywords: </Text>
          {record.keywords.map((kw) => (
            <KeywordBadge key={kw} keyword={kw} selected small />
          ))}
        </View>
      )}

      <Text style={styles.recipientLabel}>
        Recipients ({record.recipients?.length || 0}):
      </Text>
      <Text style={styles.recipientList}>
        {(record.recipients || []).map((r) => r.name).join(', ')}
      </Text>
    </View>
  );
}

export default function HistoryScreen() {
  const { messageHistory } = useApp();

  return (
    <SafeAreaView style={styles.container}>
      <FlatList
        data={messageHistory}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <HistoryCard record={item} />}
        contentContainerStyle={{ padding: 12, paddingBottom: 40 }}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>📭</Text>
            <Text style={styles.emptyTitle}>No messages yet</Text>
            <Text style={styles.emptyHint}>
              Go to the Send tab, pick some contacts, and fire off your first text!
            </Text>
          </View>
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F2F2F7' },
  card: {
    backgroundColor: '#fff', borderRadius: 12, padding: 14, marginBottom: 10,
    shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 4, elevation: 2,
  },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  modeTag: { fontSize: 13, fontWeight: '700', color: '#007AFF' },
  timestamp: { fontSize: 12, color: '#888' },
  messageText: { fontSize: 15, color: '#1C1C1E', lineHeight: 20, marginBottom: 8 },
  kwRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', marginBottom: 6 },
  kwLabel: { fontSize: 12, color: '#6E6E73', fontWeight: '600' },
  recipientLabel: { fontSize: 12, fontWeight: '700', color: '#6E6E73', marginTop: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  recipientList: { fontSize: 13, color: '#3C3C43', marginTop: 2 },
  empty: { alignItems: 'center', marginTop: 80, paddingHorizontal: 32 },
  emptyIcon: { fontSize: 52, marginBottom: 12 },
  emptyTitle: { fontSize: 20, fontWeight: '700', color: '#1C1C1E', marginBottom: 8 },
  emptyHint: { fontSize: 15, color: '#888', textAlign: 'center', lineHeight: 22 },
});
