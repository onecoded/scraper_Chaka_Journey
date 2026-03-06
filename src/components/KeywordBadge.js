import React from 'react';
import { TouchableOpacity, Text, StyleSheet } from 'react-native';

const COLORS = [
  '#007AFF', '#34C759', '#FF9500', '#FF2D55',
  '#AF52DE', '#5AC8FA', '#FF6B6B', '#4CD964',
];

function colorForKeyword(kw) {
  let hash = 0;
  for (let i = 0; i < kw.length; i++) hash = kw.charCodeAt(i) + ((hash << 5) - hash);
  return COLORS[Math.abs(hash) % COLORS.length];
}

export default function KeywordBadge({ keyword, selected, onPress, small }) {
  const bg = colorForKeyword(keyword);
  return (
    <TouchableOpacity
      style={[
        styles.badge,
        { backgroundColor: selected ? bg : bg + '30', borderColor: bg },
        small && styles.small,
      ]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <Text style={[styles.text, { color: selected ? '#fff' : bg }, small && styles.smallText]}>
        {keyword}
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  badge: {
    borderRadius: 12,
    borderWidth: 1.5,
    paddingHorizontal: 10,
    paddingVertical: 4,
    margin: 3,
  },
  small: {
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 9,
    margin: 2,
  },
  text: {
    fontSize: 13,
    fontWeight: '600',
  },
  smallText: {
    fontSize: 11,
  },
});
