import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AppProvider } from './src/context/AppContext';
import ContactsScreen from './src/screens/ContactsScreen';
import SendScreen from './src/screens/SendScreen';
import HistoryScreen from './src/screens/HistoryScreen';

const Tab = createBottomTabNavigator();

function TabIcon({ icon, focused }) {
  return (
    <View style={{ alignItems: 'center', justifyContent: 'center' }}>
      <Text style={{ fontSize: 22, opacity: focused ? 1 : 0.45 }}>{icon}</Text>
    </View>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <AppProvider>
        <NavigationContainer>
          <StatusBar style="dark" />
          <Tab.Navigator
            screenOptions={{
              headerStyle: { backgroundColor: '#fff', shadowColor: 'transparent' },
              headerTitleStyle: { fontSize: 17, fontWeight: '700' },
              tabBarStyle: {
                backgroundColor: '#fff',
                borderTopColor: '#E5E5EA',
                paddingTop: 4,
              },
              tabBarActiveTintColor: '#007AFF',
              tabBarInactiveTintColor: '#8E8E93',
              tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
            }}
          >
            <Tab.Screen
              name="Send"
              component={SendScreen}
              options={{
                title: 'Send',
                headerTitle: 'GroupText',
                tabBarIcon: ({ focused }) => <TabIcon icon="✉️" focused={focused} />,
              }}
            />
            <Tab.Screen
              name="Contacts"
              component={ContactsScreen}
              options={{
                title: 'Contacts',
                tabBarIcon: ({ focused }) => <TabIcon icon="👤" focused={focused} />,
              }}
            />
            <Tab.Screen
              name="History"
              component={HistoryScreen}
              options={{
                title: 'History',
                tabBarIcon: ({ focused }) => <TabIcon icon="🕐" focused={focused} />,
              }}
            />
          </Tab.Navigator>
        </NavigationContainer>
      </AppProvider>
    </SafeAreaProvider>
  );
}
