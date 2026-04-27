import { initializeApp, getApps } from 'firebase/app';
import type { Auth } from 'firebase/auth';
import type { Firestore } from 'firebase/firestore';

const firebaseConfig = {
  apiKey:            process.env.EXPO_PUBLIC_FIREBASE_API_KEY,
  authDomain:        process.env.EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId:         process.env.EXPO_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket:     process.env.EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.EXPO_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId:             process.env.EXPO_PUBLIC_FIREBASE_APP_ID,
};

// ── Lazy singletons ───────────────────────────────────────────────────────────
// Firebase APIs must NOT run at module level. On some Android devices
// initializeAuth() throws synchronously before React can mount, which crashes
// the entire JS module graph → black screen with no spinner and no error UI.
// All callers use getFirebaseAuth() / getFirebaseDb() instead of direct exports.

let _auth: Auth | null = null;
let _db:   Firestore | null = null;

function ensureApp() {
  return getApps().length > 0 ? getApps()[0] : initializeApp(firebaseConfig);
}

export function getFirebaseAuth(): Auth {
  if (!_auth) {
    const { initializeAuth, getReactNativePersistence, getAuth } =
      require('firebase/auth') as typeof import('firebase/auth');
    const AsyncStorage =
      require('@react-native-async-storage/async-storage').default;
    try {
      _auth = initializeAuth(ensureApp(), {
        persistence: getReactNativePersistence(AsyncStorage),
      });
    } catch (e: any) {
      // Already initialized (e.g. concurrent call) — grab the existing instance
      if (e?.code === 'auth/already-initialized') {
        _auth = getAuth(ensureApp());
      } else {
        throw e;
      }
    }
  }
  return _auth!;
}

export function getFirebaseDb(): Firestore {
  if (!_db) {
    const { getFirestore } =
      require('firebase/firestore') as typeof import('firebase/firestore');
    _db = getFirestore(ensureApp());
  }
  return _db!;
}
