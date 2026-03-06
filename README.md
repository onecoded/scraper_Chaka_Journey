# GroupText – iPhone Group Messaging App

A React Native (Expo) app for iPhone that lets you tag contacts with keywords, then blast texts to everyone sharing a keyword — either one-on-one or as a single group thread.

## Features

| Feature | Details |
|---|---|
| **Contact Management** | Add, edit, delete contacts with name, phone, and multiple keyword tags |
| **Keyword Filtering** | Tap keyword pills to instantly filter contacts who share that tag |
| **Select Recipients** | Pick any subset of the filtered contacts, or tap "Select All" |
| **Individual Mode** | Opens native SMS composer for each person separately |
| **Group Mode** | Opens a single group SMS thread with all selected numbers |
| **Message History** | Every send is logged with message preview, recipients, and keywords used |
| **Persistent Storage** | Contacts and history survive app restarts via AsyncStorage |

## Getting Started

### Prerequisites
- [Node.js](https://nodejs.org/) 18+
- [Expo CLI](https://docs.expo.dev/get-started/installation/) – `npm install -g expo-cli`
- [Expo Go](https://apps.apple.com/app/expo-go/id982107779) app on your iPhone

### Install & Run

```bash
npm install
npx expo start
```

Scan the QR code in Expo Go on your iPhone.

> **Note:** SMS sending requires a real iPhone device. It will not work in the iOS Simulator.

## How It Works

1. **Contacts tab** – Manage your contacts and assign keyword tags (e.g. `family`, `work`, `vip`).
2. **Send tab** – Filter contacts by keyword → select recipients → compose message → toggle Individual / Group → Send.
3. **History tab** – Review all past sends.

## Project Structure

```
App.js                        # Navigation shell
src/
  context/AppContext.js        # Global state (contacts, keywords, history)
  components/KeywordBadge.js   # Colored keyword pill component
  screens/
    ContactsScreen.js          # Contacts CRUD + keyword tagging
    SendScreen.js              # Filter → select → compose → send
    HistoryScreen.js           # Message history log
```
