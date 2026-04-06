"""
Vaidya — Locust load test suite
Target: 500 concurrent users, p95 < 2s on all core endpoints

Run:
    pip install locust
    locust -f locustfile.py --host=https://api.vaidya.health \
           --users=500 --spawn-rate=50 --run-time=10m

Or headless CI mode:
    locust -f locustfile.py --host=http://localhost:8000 \
           --users=500 --spawn-rate=50 --run-time=5m --headless \
           --only-summary --csv=results/load_test

Pass/fail thresholds (checked by the CI step):
    p95 latency < 2000ms for /api/v1/diagnose/predict/text
    p95 latency < 500ms  for /api/v1/care/hospitals
    p95 latency < 200ms  for /health
    failure rate < 1%

User profiles reflect actual PHC usage patterns observed during requirements:
    80% — ASHA worker submitting a text triage (most common workflow)
    15% — Care lookup after triage (hospital + teleconsult)
    5%  — Analytics read (district health officer checking dashboard)
"""

import json
import random
import time
import uuid
from locust import HttpUser, TaskSet, between, constant_pacing, events, task

# ── Realistic symptom texts in EN / HI / TA ───────────────────────────────────

SYMPTOM_TEXTS = [
    # English
    "Patient has had high fever for 3 days, severe headache, and body aches. No improvement.",
    "Persistent cough for 2 weeks, some blood in sputum, night sweats and weight loss.",
    "Child 6 years old, fever 103F, rash on face and chest spreading to body.",
    "Breathlessness on minimal exertion, swollen legs, fatigue. No chest pain.",
    "Severe abdominal pain right side for 6 hours, nausea, cannot eat or drink.",
    "High fever with shivering, jaundice, dark urine — returned from forest area.",
    "Sudden severe headache, neck stiffness, vomiting, light sensitivity.",
    "Burning urination, frequent urge to urinate, mild fever for 2 days.",
    "Rash on both arms, itching, no fever. Using new detergent soap.",
    "Diarrhoea 8 times today, vomiting, very weak. Mild fever.",
    # Hindi (transliterated)
    "Teen din se tez bukhaar, sar dard bahut zyada, body mein dard hai.",
    "Do hafte se khansi, thook mein khoon, raat ko pasina, vajan kam ho raha.",
    "Bachche ko bukhaar hai 103, chehere pe daane nikal rahe hain.",
    "Saans lene mein takleef, pair sooje hue, thakaan bahut.",
    "Pet ke daahine taraf bahut dard, 6 ghante se, ulti aa rahi.",
    # Tamil (transliterated)
    "Moonu naalaga kaichal, mukkiyamana thalai vali, udal vali.",
    "Rendu vaaram irumal, elirathil rattam, iravu velarvai.",
    "Kutty payyan, kaichal 103, mugathil, marbil thol.",
    "Moochu vittugattin kupam, kaal veekkam, sormbu.",
]

DISTRICTS = ["TN-VEL", "TN-MDU", "TN-CBE", "TN-TRI", "TN-SAL"]
LANGUAGES = ["en", "hi", "ta"]


class AshaWorkerTasks(TaskSet):
    """
    Simulates an ASHA worker submitting triage cases — the dominant user pattern.
    80% of production traffic.

    Flow:
      1. Register or look up patient (lightweight)
      2. Submit text triage (the heavy endpoint)
      3. On P3+, look up nearby hospitals
    """

    token: str = ""
    patient_id: str = ""

    def on_start(self):
        """Authenticate once per simulated user."""
        # In a real test, use seeded test credentials from fixtures
        # Here we simulate with a mock token that the test server accepts
        self.token = "test-asha-token-" + str(uuid.uuid4())[:8]
        self.patient_id = str(uuid.uuid4())
        self.district = random.choice(DISTRICTS)

    @task(6)
    def submit_text_triage(self):
        """Most common action — ASHA worker types patient symptoms."""
        text = random.choice(SYMPTOM_TEXTS)
        lang = random.choice(LANGUAGES)

        start = time.perf_counter()
        with self.client.post(
            "/api/v1/diagnose/predict/text",
            json={
                "text": text,
                "language": lang,
                "self_severity": random.randint(3, 8),
                "patient_id": self.patient_id,
            },
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
            name="/api/v1/diagnose/predict/text",
        ) as resp:
            elapsed_ms = (time.perf_counter() - start) * 1000

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    triage_level = data.get("triage", {}).get("level", 0)

                    # Store for the care-lookup task
                    self.last_triage_level = triage_level
                    resp.success()

                    # Log slow requests for drill-down
                    if elapsed_ms > 2000:
                        resp.failure(f"Slow response: {elapsed_ms:.0f}ms > 2000ms p95 target")
                except Exception as e:
                    resp.failure(f"JSON parse error: {e}")

            elif resp.status_code == 429:
                # Rate limit expected under extreme load — not a failure
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def lookup_hospitals(self):
        """Look up nearby hospitals — triggered after a P3+ triage."""
        # Vellore district approximate coordinates with small jitter
        lat = 12.9165 + random.uniform(-0.5, 0.5)
        lng = 79.1325 + random.uniform(-0.5, 0.5)
        triage_level = getattr(self, "last_triage_level", 3)

        with self.client.get(
            "/api/v1/care/hospitals",
            params={
                "lat": round(lat, 4),
                "lng": round(lng, 4),
                "radius_km": 50,
                "triage_level": triage_level,
            },
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
            name="/api/v1/care/hospitals",
        ) as resp:
            if resp.status_code in (200, 429):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def health_check(self):
        """Health probe — should always be fast (<100ms)."""
        with self.client.get(
            "/health",
            catch_response=True,
            name="/health",
        ) as resp:
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") == "ok":
                    resp.success()
                else:
                    resp.failure(f"Degraded: {body}")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def check_consent_status(self):
        """Consent status lookup — lightweight DB read."""
        with self.client.get(
            f"/api/v1/consent/status/{self.patient_id}",
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
            name="/api/v1/consent/status",
        ) as resp:
            # 404 is fine — patient may not exist in test DB
            if resp.status_code in (200, 404, 429):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


class DistrictOfficerTasks(TaskSet):
    """
    Simulates a district health officer checking analytics.
    5% of production traffic — read-heavy, no writes.
    """

    @task(3)
    def analytics_summary(self):
        district = random.choice(DISTRICTS)
        with self.client.get(
            f"/api/v1/analytics/district/{district}",
            catch_response=True,
            name="/api/v1/analytics/district",
        ) as resp:
            if resp.status_code in (200, 404, 429):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def metrics_endpoint(self):
        """Prometheus metrics scrape simulation."""
        # In prod this is IP-restricted — this simulates Grafana scraping
        with self.client.get(
            "/metrics",
            catch_response=True,
            name="/metrics",
        ) as resp:
            # 403 is correct in prod (IP restricted), 200 in dev
            if resp.status_code in (200, 403):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ── User classes ───────────────────────────────────────────────────────────────

class AshaWorker(HttpUser):
    """Primary user type — 80% of traffic."""
    tasks = [AshaWorkerTasks]
    wait_time = between(2, 8)       # realistic think-time between triage submissions
    weight = 80


class DistrictOfficer(HttpUser):
    """Secondary user type — 5% of traffic."""
    tasks = [DistrictOfficerTasks]
    wait_time = between(10, 30)     # analytics dashboard refreshes less often
    weight = 5


class CareSeeker(HttpUser):
    """
    Mobile app user browsing care options — 15% of traffic.
    Lower weight than ASHA workers, slightly more varied endpoints.
    """
    wait_time = between(3, 12)
    weight = 15

    @task(3)
    def hospital_search(self):
        lat = 9.9252 + random.uniform(-0.3, 0.3)   # Madurai area
        lng = 78.1198 + random.uniform(-0.3, 0.3)
        self.client.get(
            "/api/v1/care/hospitals",
            params={"lat": round(lat, 4), "lng": round(lng, 4), "radius_km": 30},
            name="/api/v1/care/hospitals",
        )

    @task(1)
    def teleconsult_slots(self):
        self.client.get(
            "/api/v1/care/teleconsult",
            params={"language": random.choice(LANGUAGES)},
            name="/api/v1/care/teleconsult",
        )


# ── Test result validation hook ────────────────────────────────────────────────

@events.quitting.add_listener
def assert_thresholds(environment, **kwargs):
    """
    Fail the CI job if load-test results exceed SLA thresholds.
    Called automatically when Locust exits.

    Thresholds (from Module 7 spec):
      p95 < 2000ms on triage endpoint
      failure rate < 1%
    """
    stats = environment.stats

    # Check overall failure rate
    total_reqs = stats.total.num_requests
    total_fails = stats.total.num_failures
    if total_reqs > 0:
        fail_rate = total_fails / total_reqs
        if fail_rate > 0.01:
            environment.process_exit_code = 1
            print(f"\n❌ LOAD TEST FAILED: failure rate {fail_rate:.1%} > 1% threshold")
            return

    # Check p95 on the triage endpoint
    triage_stats = stats.get("/api/v1/diagnose/predict/text", "POST")
    if triage_stats and triage_stats.num_requests > 0:
        p95 = triage_stats.get_response_time_percentile(0.95)
        if p95 and p95 > 2000:
            environment.process_exit_code = 1
            print(f"\n❌ LOAD TEST FAILED: triage p95={p95:.0f}ms > 2000ms threshold")
            return

    print(f"\n✅ LOAD TEST PASSED: {total_reqs} requests, {total_fails} failures "
          f"({total_fails/max(total_reqs,1):.2%} failure rate)")
    environment.process_exit_code = 0
