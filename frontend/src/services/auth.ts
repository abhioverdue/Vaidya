/**
 * Vaidya — Auth service (Firebase Email/Password)
 * Falls back to demo mode when Firebase is unreachable.
 */

import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signOut,
  updateProfile,
  reauthenticateWithCredential,
  EmailAuthProvider,
  updatePassword,
  sendPasswordResetEmail,
} from 'firebase/auth';
import { getFirebaseAuth } from './firebase';
import { apiClient } from './api';
import { isNetworkUnreachable } from './demoData';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AuthUser {
  id:         string;
  name:       string;
  email:      string;
  age_group?: 'child' | 'adult' | 'senior';
}

export interface AuthResponse {
  access_token: string;
  token_type:   string;
  user:         AuthUser;
}

export interface OtpResponse {
  message:    string;
  expires_in: number;
  /** Present only when SMS could not be delivered (no FAST2SMS key configured).
   *  null when a real SMS was sent — nothing leaks in production. */
  demo_otp:   string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeDemoUser(email: string, name: string): AuthUser {
  return { id: `demo-${email}`, name: name || 'Demo User', email, age_group: 'adult' };
}

async function demoDelay(ms = 900): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function firebaseErrMsg(code: string): string {
  switch (code) {
    case 'auth/invalid-credential':
    case 'auth/user-not-found':
    case 'auth/wrong-password':       return 'Invalid email or password.';
    case 'auth/email-already-in-use': return 'An account with this email already exists.';
    case 'auth/weak-password':        return 'Password must be at least 6 characters.';
    case 'auth/invalid-email':        return 'Enter a valid email address.';
    case 'auth/too-many-requests':    return 'Too many attempts. Please try again later.';
    case 'auth/network-request-failed': return 'No internet connection.';
    default: return 'Something went wrong. Please try again.';
  }
}

// ── Auth API ──────────────────────────────────────────────────────────────────

export async function authLogin(
  email:    string,
  password: string,
): Promise<AuthResponse> {
  try {
    const cred  = await signInWithEmailAndPassword(getFirebaseAuth(), email, password);
    const token = await cred.user.getIdToken();
    return {
      access_token: token,
      token_type:   'bearer',
      user: {
        id:        cred.user.uid,
        name:      cred.user.displayName ?? 'User',
        email,
        age_group: 'adult',
      },
    };
  } catch (err: any) {
    if (err?.code?.startsWith('auth/')) throw new Error(firebaseErrMsg(err.code));
    if (isNetworkUnreachable(err)) {
      await demoDelay();
      return {
        access_token: `demo-token-${Date.now()}`,
        token_type:   'bearer',
        user:         makeDemoUser(email, 'Demo User'),
      };
    }
    throw err;
  }
}

export async function authRegister(
  name:     string,
  email:    string,
  password: string,
): Promise<AuthResponse> {
  try {
    const cred  = await createUserWithEmailAndPassword(getFirebaseAuth(), email, password);
    await updateProfile(cred.user, { displayName: name });
    const token = await cred.user.getIdToken();
    return {
      access_token: token,
      token_type:   'bearer',
      user: { id: cred.user.uid, name, email, age_group: 'adult' },
    };
  } catch (err: any) {
    if (err?.code?.startsWith('auth/')) throw new Error(firebaseErrMsg(err.code));
    if (isNetworkUnreachable(err)) {
      await demoDelay(1200);
      return {
        access_token: `demo-token-${Date.now()}`,
        token_type:   'bearer',
        user:         makeDemoUser(email, name),
      };
    }
    throw err;
  }
}

export async function authSignOut(): Promise<void> {
  try { await signOut(getFirebaseAuth()); } catch {}
}

export async function authSendPasswordReset(email: string): Promise<void> {
  try {
    await sendPasswordResetEmail(getFirebaseAuth(), email);
  } catch (err: any) {
    if (err?.code?.startsWith('auth/')) throw new Error(firebaseErrMsg(err.code));
    throw err;
  }
}

export async function authChangePassword(
  email:           string,
  currentPassword: string,
  newPassword:     string,
): Promise<{ message: string }> {
  const user = getFirebaseAuth().currentUser;
  if (!user) throw new Error('You must be signed in to change your password.');
  try {
    const credential = EmailAuthProvider.credential(email, currentPassword);
    await reauthenticateWithCredential(user, credential);
    await updatePassword(user, newPassword);
    return { message: 'Password changed successfully.' };
  } catch (err: any) {
    if (err?.code?.startsWith('auth/')) throw new Error(firebaseErrMsg(err.code));
    throw err;
  }
}

// ── Legacy OTP helpers (kept for verify-otp.tsx compatibility) ────────────────

export async function authRequestOtp(
  phone: string,
  type:  'register' | 'reset',
): Promise<OtpResponse> {
  try {
    const { data } = await apiClient.post('/auth/otp/send', { phone, type }, { timeout: 8_000 });
    return {
      message:    data.message,
      expires_in: data.expires_in ?? 300,
      demo_otp:   data.demo_otp ?? null,
    };
  } catch (err: any) {
    if (isNetworkUnreachable(err)) {
      await demoDelay(800);
      return { message: 'OTP generated for your session.', expires_in: 300, demo_otp: '123456' };
    }
    throw err;
  }
}

export async function authVerifyOtp(
  phone: string,
  otp:   string,
): Promise<{ valid: boolean; message: string }> {
  try {
    const { data } = await apiClient.post('/auth/otp/verify', { phone, otp }, { timeout: 8_000 });
    return { valid: data.valid, message: data.message };
  } catch (err: any) {
    if (isNetworkUnreachable(err)) {
      await demoDelay(600);
      return { valid: true, message: 'OTP verified (offline demo).' };
    }
    throw err;
  }
}

export async function authResetPassword(
  phone:       string,
  otp:         string,
  newPassword: string,
): Promise<{ message: string }> {
  try {
    const { data } = await apiClient.post('/auth/otp/reset-password', {
      phone,
      otp,
      new_password: newPassword,
    }, { timeout: 8_000 });
    return { message: data.message };
  } catch (err: any) {
    if (isNetworkUnreachable(err)) {
      await demoDelay(600);
      return { message: 'Password reset successfully. You can now sign in.' };
    }
    const detail = err?.detail || err?.response?.data?.detail || err?.message || '';
    throw new Error(detail && !detail.startsWith('API error') ? detail : 'Password reset failed. Please try again.');
  }
}
