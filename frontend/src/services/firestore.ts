import {
  collection, addDoc, query, where, orderBy,
  getDocs, serverTimestamp, limit, doc, getDoc, setDoc, increment,
  Timestamp,
} from 'firebase/firestore';
import { getFirebaseDb } from './firebase';

const SESSIONS_COL = 'sessions';

export async function saveSessionToFirestore(
  userId:  string,
  session: Record<string, any>,
): Promise<void> {
  try {
    await addDoc(collection(getFirebaseDb(), SESSIONS_COL), {
      userId,
      primaryDiagnosis:  session.diagnosis?.primary_diagnosis ?? session.primary_diagnosis ?? '',
      confidence:        session.diagnosis?.confidence        ?? session.confidence        ?? 0,
      triageLevel:       session.triage?.level                ?? null,
      triageLabel:       session.triage?.label                ?? null,
      diagnosisSource:   session.diagnosis?.diagnosis_source  ?? 'xgboost',
      language:          session.input_language               ?? 'en',
      savedAt:           serverTimestamp(),
    });
  } catch (err) {
    console.warn('Firestore save failed:', err);
  }
}

export async function incrementSessionCounter(): Promise<void> {
  try {
    await setDoc(
      doc(getFirebaseDb(), 'stats', 'global'),
      { totalSessions: increment(1), lastUpdated: serverTimestamp() },
      { merge: true },
    );
  } catch (err) {
    console.warn('Counter increment failed:', err);
  }
}

export async function getSessionCount(): Promise<number> {
  try {
    const snap = await getDoc(doc(getFirebaseDb(), 'stats', 'global'));
    return snap.data()?.totalSessions ?? 0;
  } catch {
    return 0;
  }
}

export interface OutbreakSignal {
  diagnosis: string;
  count:     number;
  hours:     number;
}

/**
 * Checks whether any diagnosis has appeared ≥ threshold times across ALL users
 * in the last `hours` hours. Returns the top signal if one exists, else null.
 * Used to surface community-level outbreak warnings on the home screen.
 */
export async function checkOutbreakSignal(
  hours:     number = 48,
  threshold: number = 5,
): Promise<OutbreakSignal | null> {
  try {
    const since = Timestamp.fromDate(new Date(Date.now() - hours * 60 * 60 * 1000));
    const q = query(
      collection(getFirebaseDb(), SESSIONS_COL),
      where('savedAt', '>=', since),
      orderBy('savedAt', 'desc'),
      limit(200),
    );
    const snap = await getDocs(q);
    const counts: Record<string, number> = {};
    snap.docs.forEach((d) => {
      const dx = d.data().primaryDiagnosis;
      if (dx) counts[dx] = (counts[dx] ?? 0) + 1;
    });
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    if (top && top[1] >= threshold) {
      return { diagnosis: top[0], count: top[1], hours };
    }
    return null;
  } catch {
    return null;
  }
}

export async function loadSessionsFromFirestore(
  userId: string,
): Promise<any[]> {
  try {
    const q = query(
      collection(getFirebaseDb(), SESSIONS_COL),
      where('userId', '==', userId),
      orderBy('savedAt', 'desc'),
      limit(20),
    );
    const snap = await getDocs(q);
    return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
  } catch (err) {
    console.warn('Firestore load failed:', err);
    return [];
  }
}
