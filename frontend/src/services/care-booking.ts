/**
 * Vaidya — Care booking service (teleconsult booking, status, cancel, geocode)
 * Falls back to demo mode when the backend is unreachable.
 */

import { apiClient } from './api';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface TeleconsultBookingBody {
  slot_id?:           string;
  doctor_name:        string;
  specialty:          string;
  available_at:       string;
  platform:           string;
  patient_name?:      string;
  patient_phone?:     string;
  symptoms_summary?:  string;
}

export interface TeleconsultBookingResponse {
  booking_id:         string;
  status:             string;
  doctor_name:        string;
  scheduled_at:       string;
  platform:           string;
  booking_url:        string;
  confirmation_code:  string;
}

export interface TeleconsultStatusResponse {
  booking_id:   string;
  status:       string;
  doctor_name:  string;
  scheduled_at: string;
  platform:     string;
  notes?:       string;
}

export interface TeleconsultCancelBody {
  reason?: string;
}

export interface TeleconsultCancelResponse {
  booking_id:   string;
  status:       'cancelled';
  cancelled_at: string;
}

export interface GeocodeResponse {
  lat:               number;
  lng:               number;
  formatted_address: string;
  district:          string;
  state:             string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function demoDelay(ms = 700): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function demoBookingId(): string {
  return `BK${Date.now().toString().slice(-8)}`;
}

function demoConfirmationCode(): string {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  return Array.from({ length: 6 }, () => chars[Math.floor(Math.random() * chars.length)]).join('');
}

// ── Demo data ─────────────────────────────────────────────────────────────────

const DEMO_PLATFORMS: Record<string, string> = {
  eSanjeevani: 'https://esanjeevaniopd.in',
  Apollo247:   'https://www.apollo247.com/teleconsult',
  Practo:      'https://www.practo.com/consult',
};

// ── Care Booking API ──────────────────────────────────────────────────────────

export async function bookTeleconsult(body: TeleconsultBookingBody): Promise<TeleconsultBookingResponse> {
  try {
    const { data } = await apiClient.post('/care/teleconsult/book', body, { timeout: 12_000 });
    return data;
  } catch {
    await demoDelay(1000);
    const bookingId   = demoBookingId();
    const platformUrl = DEMO_PLATFORMS[body.platform] ?? DEMO_PLATFORMS['eSanjeevani'];
    return {
      booking_id:        bookingId,
      status:            'confirmed',
      doctor_name:       body.doctor_name,
      scheduled_at:      body.available_at,
      platform:          body.platform,
      booking_url:       `${platformUrl}?booking=${bookingId}`,
      confirmation_code: demoConfirmationCode(),
    };
  }
}

export async function getTeleconsultStatus(booking_id: string): Promise<TeleconsultStatusResponse> {
  try {
    const { data } = await apiClient.get(`/care/teleconsult/${booking_id}/status`, { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(600);
    return {
      booking_id,
      status:       'confirmed',
      doctor_name:  'Dr. Priya Krishnamurthy',
      scheduled_at: new Date(Date.now() + 2 * 3600 * 1000).toISOString(),
      platform:     'eSanjeevani',
      notes:        'Please keep your ABHA ID and Aadhaar number ready for verification.',
    };
  }
}

export async function cancelTeleconsult(
  booking_id: string,
  body?:       TeleconsultCancelBody,
): Promise<TeleconsultCancelResponse> {
  try {
    const { data } = await apiClient.post(`/care/teleconsult/${booking_id}/cancel`, body ?? {}, { timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(600);
    return {
      booking_id,
      status:       'cancelled',
      cancelled_at: new Date().toISOString(),
    };
  }
}

export async function geocodeLocation(params: {
  address?: string;
  lat?:     number;
  lng?:     number;
}): Promise<GeocodeResponse> {
  try {
    const { data } = await apiClient.get('/care/geocode', { params, timeout: 8_000 });
    return data;
  } catch {
    await demoDelay(500);
    if (params.lat != null && params.lng != null) {
      return {
        lat:               params.lat,
        lng:               params.lng,
        formatted_address: 'Saravanampatti, Coimbatore, Tamil Nadu 641035',
        district:          'Coimbatore',
        state:             'Tamil Nadu',
      };
    }
    return {
      lat:               11.0168,
      lng:               76.9558,
      formatted_address: `${params.address ?? 'Coimbatore'}, Tamil Nadu`,
      district:          'Coimbatore',
      state:             'Tamil Nadu',
    };
  }
}
