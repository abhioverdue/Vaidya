/**
 * Vaidya — Auth service
 * Handles login, register, OTP request/verify, reset-password.
 * All calls gracefully fall back to demo mode when the backend is unreachable.
 */

import { apiClient } from './api';
import { isNetworkUnreachable } from './demoData';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AuthUser {
  id:         string;
  name:       string;
  phone:      string;
  age_group?: 'child' | 'adult' | 'senior';
}

export interface AuthResponse {
  access_token: string;
  token_type:   string;
  user:         AuthUser;
}

export interface OtpResponse {
  message:     string;
  expires_in:  number;   // seconds
}

// ── Demo helpers ──────────────────────────────────────────────────────────────

const DEMO_OTP = '123456';

let _demoOtpStore: Record<string, string> = {};   // phone → OTP (demo only)

function makeDemoUser(phone: string, name: string): AuthUser {
  return {
    id:         `demo-${phone}`,
    name:       name || 'Demo User',
    phone,
    age_group:  'adult',
  };
}

async function demoDelay(ms = 900): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Auth API ──────────────────────────────────────────────────────────────────

/**
 * Login with mobile + password.
 * Returns AuthResponse on success.
 */
export async function authLogin(
  phone:    string,
  password: string,
): Promise<AuthResponse> {
  try {
    const { data } = await apiClient.post<AuthResponse>('/auth/login', {
      phone,
      password,
    });
    return data;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      await demoDelay();
      // Demo: any phone + any password works
      return {
        access_token: `demo-token-${Date.now()}`,
        token_type:   'bearer',
        user:         makeDemoUser(phone, 'Demo User'),
      };
    }
    throw err;
  }
}

/**
 * Register a new account.
 * Backend creates the user; returns the auth token immediately.
 */
export async function authRegister(
  name:     string,
  phone:    string,
  password: string,
): Promise<AuthResponse> {
  try {
    const { data } = await apiClient.post<AuthResponse>('/auth/register', {
      name,
      phone,
      password,
    });
    return data;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      await demoDelay(1200);
      return {
        access_token: `demo-token-${Date.now()}`,
        token_type:   'bearer',
        user:         makeDemoUser(phone, name),
      };
    }
    throw err;
  }
}

/**
 * Request OTP for a phone number.
 * type = 'register' | 'reset'
 */
export async function authRequestOtp(
  phone: string,
  type:  'register' | 'reset',
): Promise<OtpResponse> {
  try {
    const { data } = await apiClient.post<OtpResponse>('/auth/otp/request', {
      phone,
      type,
    });
    return data;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      await demoDelay(800);
      _demoOtpStore[phone] = DEMO_OTP;
      return {
        message:    `Demo OTP sent to ${phone}. Use code: ${DEMO_OTP}`,
        expires_in: 300,
      };
    }
    throw err;
  }
}

/**
 * Verify OTP code.
 * Returns { valid: true } on success.
 */
export async function authVerifyOtp(
  phone: string,
  otp:   string,
): Promise<{ valid: boolean; message: string }> {
  try {
    const { data } = await apiClient.post<{ valid: boolean; message: string }>(
      '/auth/otp/verify',
      { phone, otp },
    );
    return data;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      await demoDelay(600);
      const valid = otp === DEMO_OTP || otp === (_demoOtpStore[phone] ?? DEMO_OTP);
      return {
        valid,
        message: valid ? 'OTP verified successfully' : 'Invalid OTP. Demo code is 123456',
      };
    }
    throw err;
  }
}

/**
 * Reset password using verified OTP.
 */
export async function authResetPassword(
  phone:       string,
  otp:         string,
  newPassword: string,
): Promise<{ message: string }> {
  try {
    const { data } = await apiClient.post<{ message: string }>(
      '/auth/password/reset',
      { phone, otp, new_password: newPassword },
    );
    return data;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      await demoDelay(800);
      const valid = otp === DEMO_OTP || otp === (_demoOtpStore[phone] ?? DEMO_OTP);
      if (!valid) throw new Error('Invalid OTP. Demo code is 123456');
      return { message: 'Password reset successfully.' };
    }
    throw err;
  }
}

/**
 * Change password (authenticated user).
 */
export async function authChangePassword(
  currentPassword: string,
  newPassword:     string,
  token:           string,
): Promise<{ message: string }> {
  try {
    const { data } = await apiClient.post<{ message: string }>(
      '/auth/password/change',
      { current_password: currentPassword, new_password: newPassword },
      { headers: { Authorization: `Bearer ${token}` } },
    );
    return data;
  } catch (err) {
    if (isNetworkUnreachable(err)) {
      await demoDelay(600);
      return { message: 'Password changed successfully.' };
    }
    throw err;
  }
}
