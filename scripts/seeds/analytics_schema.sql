-- ═══════════════════════════════════════════════════════════════════════════════
-- Vaidya Health Analytics Module — TimescaleDB Schema
-- ═══════════════════════════════════════════════════════════════════════════════
-- Purpose: Outbreak anomaly detection, epidemiological surveillance, and
--          real-time health analytics for district health officers
-- Tech:    TimescaleDB (PostgreSQL extension), continuous aggregates, ASHA alerts
-- Weeks:   10-13 (Analytics module)
-- ═══════════════════════════════════════════════════════════════════════════════

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS postgis;      -- For geospatial clustering
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- Query performance monitoring

-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 1: HYPERTABLES FOR TIME-SERIES DATA
-- ═══════════════════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────────────────
-- 1.1 Convert existing triage_events to hypertable (if not already)
-- ───────────────────────────────────────────────────────────────────────────────
-- This must run AFTER the table is created by Alembic migrations
SELECT create_hypertable(
    'triage_events',
    'event_time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '7 days',  -- Weekly chunks for performance
    migrate_data => TRUE
);

-- Add hypertable-optimized indexes
CREATE INDEX IF NOT EXISTS idx_triage_events_time_district 
    ON triage_events (event_time DESC, district_code);

CREATE INDEX IF NOT EXISTS idx_triage_events_time_diagnosis 
    ON triage_events (event_time DESC, diagnosis);

CREATE INDEX IF NOT EXISTS idx_triage_events_time_state 
    ON triage_events (event_time DESC, state_code);

-- Composite index for outbreak detection queries
CREATE INDEX IF NOT EXISTS idx_triage_events_outbreak_detection 
    ON triage_events (district_code, diagnosis, event_time DESC);


-- ───────────────────────────────────────────────────────────────────────────────
-- 1.2 New hypertable: symptom_events (fine-grained symptom tracking)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE symptom_events (
    id              UUID DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL,
    event_time      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Anonymised demographics
    district_code   VARCHAR(10),
    state_code      VARCHAR(5),
    age_group       VARCHAR(10),     -- child, adult, senior
    
    -- Symptom data (flattened for time-series analysis)
    symptom         VARCHAR(100) NOT NULL,  -- Single symptom per row (normalized)
    severity        INTEGER CHECK (severity BETWEEN 1 AND 10),
    duration_hours  INTEGER,
    
    -- Contextual flags
    is_red_flag     BOOLEAN DEFAULT FALSE,
    input_language  VARCHAR(5),
    
    PRIMARY KEY (event_time, id)
);

-- Convert to hypertable
SELECT create_hypertable(
    'symptom_events',
    'event_time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Indexes for symptom clustering and outbreak detection
CREATE INDEX idx_symptom_events_time_district_symptom 
    ON symptom_events (event_time DESC, district_code, symptom);

CREATE INDEX idx_symptom_events_time_symptom 
    ON symptom_events (event_time DESC, symptom);


-- ───────────────────────────────────────────────────────────────────────────────
-- 1.3 New hypertable: geospatial_events (lat/lng hotspot detection)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE geospatial_events (
    id              UUID DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL,
    event_time      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Location (anonymised to ~1km grid for DPDP Act compliance)
    location        GEOGRAPHY(POINT, 4326),  -- PostGIS geography type
    district_code   VARCHAR(10),
    state_code      VARCHAR(5),
    
    -- Event metadata
    diagnosis       VARCHAR(200),
    triage_level    INTEGER CHECK (triage_level BETWEEN 1 AND 5),
    age_group       VARCHAR(10),
    
    PRIMARY KEY (event_time, id)
);

-- Convert to hypertable
SELECT create_hypertable(
    'geospatial_events',
    'event_time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Spatial index for hotspot clustering (PostGIS GIST)
CREATE INDEX idx_geospatial_events_location_time 
    ON geospatial_events USING GIST (location, event_time);

CREATE INDEX idx_geospatial_events_time_district 
    ON geospatial_events (event_time DESC, district_code);


-- ───────────────────────────────────────────────────────────────────────────────
-- 1.4 New hypertable: asha_activity_events (ASHA worker engagement tracking)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE asha_activity_events (
    id                  UUID DEFAULT uuid_generate_v4(),
    event_time          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- ASHA worker
    asha_worker_id      UUID NOT NULL,
    district_code       VARCHAR(10),
    state_code          VARCHAR(5),
    
    -- Activity type
    activity_type       VARCHAR(50) NOT NULL,  -- assigned, acknowledged, completed, escalated
    session_id          UUID,
    triage_level        INTEGER,
    response_time_mins  INTEGER,  -- Time from assignment to acknowledgment
    
    -- Outcome
    outcome             VARCHAR(50),  -- patient_contacted, referred_to_hospital, self_care_advised, lost_contact
    
    PRIMARY KEY (event_time, id)
);

-- Convert to hypertable
SELECT create_hypertable(
    'asha_activity_events',
    'event_time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Indexes for ASHA performance analytics
CREATE INDEX idx_asha_activity_time_worker 
    ON asha_activity_events (event_time DESC, asha_worker_id);

CREATE INDEX idx_asha_activity_time_district 
    ON asha_activity_events (event_time DESC, district_code);


-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 2: CONTINUOUS AGGREGATES (Pre-computed materialized views)
-- ═══════════════════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────────────────
-- 2.1 Hourly diagnosis counts by district (for outbreak detection)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE MATERIALIZED VIEW diagnosis_counts_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', event_time) AS bucket,
    district_code,
    state_code,
    diagnosis,
    COUNT(*) AS case_count,
    AVG(triage_level) AS avg_triage_level,
    COUNT(*) FILTER (WHERE triage_level >= 4) AS urgent_cases
FROM triage_events
WHERE diagnosis IS NOT NULL
GROUP BY bucket, district_code, state_code, diagnosis
WITH NO DATA;

-- Refresh policy: update every 10 minutes for near-real-time
SELECT add_continuous_aggregate_policy(
    'diagnosis_counts_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '10 minutes',
    schedule_interval => INTERVAL '10 minutes'
);

-- Index for fast outbreak queries
CREATE INDEX idx_diagnosis_counts_hourly_lookup 
    ON diagnosis_counts_hourly (district_code, diagnosis, bucket DESC);


-- ───────────────────────────────────────────────────────────────────────────────
-- 2.2 Daily symptom prevalence by district
-- ───────────────────────────────────────────────────────────────────────────────
CREATE MATERIALIZED VIEW symptom_prevalence_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', event_time) AS bucket,
    district_code,
    state_code,
    symptom,
    COUNT(*) AS symptom_count,
    AVG(severity) AS avg_severity,
    COUNT(*) FILTER (WHERE is_red_flag) AS red_flag_count
FROM symptom_events
GROUP BY bucket, district_code, state_code, symptom
WITH NO DATA;

-- Refresh policy: update every hour
SELECT add_continuous_aggregate_policy(
    'symptom_prevalence_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);


-- ───────────────────────────────────────────────────────────────────────────────
-- 2.3 District-level triage summary (15-minute intervals)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE MATERIALIZED VIEW triage_summary_15min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', event_time) AS bucket,
    district_code,
    state_code,
    COUNT(*) AS total_cases,
    COUNT(*) FILTER (WHERE triage_level = 1) AS level_1_self_care,
    COUNT(*) FILTER (WHERE triage_level = 2) AS level_2_monitor,
    COUNT(*) FILTER (WHERE triage_level = 3) AS level_3_see_gp,
    COUNT(*) FILTER (WHERE triage_level = 4) AS level_4_urgent,
    COUNT(*) FILTER (WHERE triage_level = 5) AS level_5_emergency,
    AVG(triage_level) AS avg_triage_level
FROM triage_events
GROUP BY bucket, district_code, state_code
WITH NO DATA;

-- Refresh policy: update every 5 minutes for real-time dashboard
SELECT add_continuous_aggregate_policy(
    'triage_summary_15min',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes'
);


-- ───────────────────────────────────────────────────────────────────────────────
-- 2.4 ASHA worker performance metrics (daily)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE MATERIALIZED VIEW asha_performance_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', event_time) AS bucket,
    asha_worker_id,
    district_code,
    COUNT(*) AS total_assignments,
    COUNT(*) FILTER (WHERE activity_type = 'acknowledged') AS acknowledged_count,
    COUNT(*) FILTER (WHERE activity_type = 'completed') AS completed_count,
    AVG(response_time_mins) AS avg_response_time_mins,
    COUNT(*) FILTER (WHERE outcome = 'referred_to_hospital') AS referrals
FROM asha_activity_events
WHERE activity_type IN ('assigned', 'acknowledged', 'completed')
GROUP BY bucket, asha_worker_id, district_code
WITH NO DATA;

-- Refresh policy: update every 2 hours
SELECT add_continuous_aggregate_policy(
    'asha_performance_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '2 hours',
    schedule_interval => INTERVAL '2 hours'
);


-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 3: OUTBREAK DETECTION TABLES
-- ═══════════════════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────────────────
-- 3.1 Baseline statistics (historical averages for anomaly detection)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE outbreak_baselines (
    id                  SERIAL PRIMARY KEY,
    district_code       VARCHAR(10) NOT NULL,
    diagnosis           VARCHAR(200) NOT NULL,
    
    -- Time windows for baseline
    baseline_start      TIMESTAMPTZ NOT NULL,
    baseline_end        TIMESTAMPTZ NOT NULL,
    
    -- Statistical measures (computed from historical data)
    mean_cases_per_day  NUMERIC(10,2) NOT NULL,
    stddev_cases        NUMERIC(10,2) NOT NULL,
    median_cases        INTEGER,
    p95_cases           INTEGER,     -- 95th percentile threshold
    
    -- Metadata
    sample_size         INTEGER NOT NULL,  -- Number of days in baseline
    last_updated        TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE (district_code, diagnosis)
);

CREATE INDEX idx_outbreak_baselines_district 
    ON outbreak_baselines (district_code);


-- ───────────────────────────────────────────────────────────────────────────────
-- 3.2 Detected outbreak alerts (real-time anomaly tracking)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE outbreak_alerts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_time          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Alert metadata
    district_code       VARCHAR(10) NOT NULL,
    state_code          VARCHAR(5),
    diagnosis           VARCHAR(200) NOT NULL,
    
    -- Anomaly detection metrics
    current_cases       INTEGER NOT NULL,
    baseline_mean       NUMERIC(10,2) NOT NULL,
    z_score             NUMERIC(10,4) NOT NULL,  -- Standard deviations from mean
    percent_increase    NUMERIC(10,2),
    
    -- Alert severity
    severity            VARCHAR(20) NOT NULL,  -- warning, moderate, severe, critical
    alert_threshold     VARCHAR(50) NOT NULL,  -- z>2, z>3, p95_exceeded, doubling_time<7d
    
    -- Status tracking
    status              VARCHAR(20) DEFAULT 'active',  -- active, investigating, resolved, false_positive
    acknowledged_by     VARCHAR(100),
    acknowledged_at     TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    
    -- Actions taken
    asha_notified       BOOLEAN DEFAULT FALSE,
    district_officer_notified BOOLEAN DEFAULT FALSE,
    state_officer_notified BOOLEAN DEFAULT FALSE,
    
    -- Additional context
    affected_areas      JSONB,  -- List of sub-districts or villages with high concentration
    notes               TEXT
);

CREATE INDEX idx_outbreak_alerts_time_district 
    ON outbreak_alerts (alert_time DESC, district_code);

CREATE INDEX idx_outbreak_alerts_status 
    ON outbreak_alerts (status, severity);

CREATE INDEX idx_outbreak_alerts_diagnosis 
    ON outbreak_alerts (diagnosis, alert_time DESC);


-- ───────────────────────────────────────────────────────────────────────────────
-- 3.3 Geospatial disease clusters (hotspot detection results)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE disease_clusters (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Cluster characteristics
    district_code       VARCHAR(10) NOT NULL,
    diagnosis           VARCHAR(200) NOT NULL,
    cluster_center      GEOGRAPHY(POINT, 4326),  -- PostGIS point (lat/lng)
    cluster_radius_km   NUMERIC(10,2),
    
    -- Cluster metrics
    case_count          INTEGER NOT NULL,
    time_window_hours   INTEGER NOT NULL,  -- Time span of cases in cluster
    density_score       NUMERIC(10,4),     -- Cases per square km
    
    -- Statistical significance
    p_value             NUMERIC(10,6),     -- From spatial scan statistic
    relative_risk       NUMERIC(10,4),     -- RR compared to surrounding area
    
    -- Status
    status              VARCHAR(20) DEFAULT 'active',
    investigation_notes TEXT
);

CREATE INDEX idx_disease_clusters_time_district 
    ON disease_clusters (detected_at DESC, district_code);

CREATE INDEX idx_disease_clusters_location 
    ON disease_clusters USING GIST (cluster_center);


-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 4: ANALYTICS SUPPORT TABLES
-- ═══════════════════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────────────────
-- 4.1 Disease surveillance watchlist (diseases to monitor for outbreaks)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE disease_watchlist (
    id                      SERIAL PRIMARY KEY,
    diagnosis               VARCHAR(200) NOT NULL UNIQUE,
    
    -- Monitoring configuration
    is_notifiable           BOOLEAN DEFAULT FALSE,  -- IDSP notifiable disease
    outbreak_threshold_type VARCHAR(50) NOT NULL,   -- z_score, percent_increase, absolute_count
    threshold_value         NUMERIC(10,2) NOT NULL,
    
    -- Alert configuration
    auto_notify_asha        BOOLEAN DEFAULT TRUE,
    auto_notify_district    BOOLEAN DEFAULT FALSE,
    auto_notify_state       BOOLEAN DEFAULT FALSE,
    
    -- Disease characteristics
    typical_incubation_days INTEGER,
    is_seasonal             BOOLEAN DEFAULT FALSE,
    peak_months             INTEGER[],  -- Array: [6,7,8] for Jun-Aug
    
    -- Metadata
    icd10_code              VARCHAR(10),
    priority_level          INTEGER CHECK (priority_level BETWEEN 1 AND 5),
    notes                   TEXT,
    added_at                TIMESTAMPTZ DEFAULT NOW()
);

-- Seed with high-priority diseases
INSERT INTO disease_watchlist 
    (diagnosis, is_notifiable, outbreak_threshold_type, threshold_value, 
     auto_notify_district, priority_level, icd10_code) 
VALUES
    ('Dengue fever', TRUE, 'z_score', 2.0, TRUE, 5, 'A90'),
    ('Malaria', TRUE, 'z_score', 2.0, TRUE, 5, 'B50-B54'),
    ('Acute respiratory infection', FALSE, 'z_score', 2.5, TRUE, 4, 'J00-J22'),
    ('Gastroenteritis', FALSE, 'z_score', 2.5, TRUE, 3, 'A09'),
    ('Viral fever', FALSE, 'z_score', 3.0, FALSE, 3, 'R50'),
    ('COVID-19', TRUE, 'percent_increase', 20.0, TRUE, 5, 'U07.1'),
    ('Typhoid fever', TRUE, 'z_score', 2.0, TRUE, 5, 'A01'),
    ('Chickenpox', FALSE, 'z_score', 2.5, TRUE, 3, 'B01'),
    ('Measles', TRUE, 'z_score', 1.5, TRUE, 5, 'B05'),
    ('Japanese encephalitis', TRUE, 'absolute_count', 1.0, TRUE, 5, 'A83.0')
ON CONFLICT (diagnosis) DO NOTHING;


-- ───────────────────────────────────────────────────────────────────────────────
-- 4.2 Analytics dashboard cache (pre-computed for fast loading)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE TABLE analytics_cache (
    cache_key           VARCHAR(200) PRIMARY KEY,
    cache_value         JSONB NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ NOT NULL,
    computation_time_ms INTEGER
);

CREATE INDEX idx_analytics_cache_expiry 
    ON analytics_cache (expires_at);


-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 5: DATA RETENTION POLICIES (GDPR/DPDP Act compliance)
-- ═══════════════════════════════════════════════════════════════════════════════

-- Drop raw detailed data after 90 days, keep aggregates longer
SELECT add_retention_policy('triage_events', INTERVAL '90 days');
SELECT add_retention_policy('symptom_events', INTERVAL '90 days');
SELECT add_retention_policy('geospatial_events', INTERVAL '90 days');
SELECT add_retention_policy('asha_activity_events', INTERVAL '180 days');

-- Continuous aggregates retained for 2 years
SELECT add_retention_policy('diagnosis_counts_hourly', INTERVAL '730 days');
SELECT add_retention_policy('symptom_prevalence_daily', INTERVAL '730 days');
SELECT add_retention_policy('triage_summary_15min', INTERVAL '90 days');
SELECT add_retention_policy('asha_performance_daily', INTERVAL '730 days');


-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 6: HELPER FUNCTIONS & STORED PROCEDURES
-- ═══════════════════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────────────────
-- 6.1 Calculate baseline statistics for a disease in a district
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION calculate_outbreak_baseline(
    p_district_code VARCHAR(10),
    p_diagnosis VARCHAR(200),
    p_lookback_days INTEGER DEFAULT 60
) RETURNS VOID AS $$
DECLARE
    v_mean NUMERIC;
    v_stddev NUMERIC;
    v_median INTEGER;
    v_p95 INTEGER;
    v_count INTEGER;
BEGIN
    -- Compute statistics from historical hourly aggregates
    SELECT
        AVG(daily_cases),
        STDDEV(daily_cases),
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY daily_cases),
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY daily_cases),
        COUNT(*)
    INTO v_mean, v_stddev, v_median, v_p95, v_count
    FROM (
        SELECT
            DATE_TRUNC('day', bucket) AS day,
            SUM(case_count) AS daily_cases
        FROM diagnosis_counts_hourly
        WHERE district_code = p_district_code
          AND diagnosis = p_diagnosis
          AND bucket >= NOW() - INTERVAL '1 day' * p_lookback_days
        GROUP BY day
    ) daily_totals;
    
    -- Upsert baseline
    INSERT INTO outbreak_baselines (
        district_code,
        diagnosis,
        baseline_start,
        baseline_end,
        mean_cases_per_day,
        stddev_cases,
        median_cases,
        p95_cases,
        sample_size
    ) VALUES (
        p_district_code,
        p_diagnosis,
        NOW() - INTERVAL '1 day' * p_lookback_days,
        NOW(),
        COALESCE(v_mean, 0),
        COALESCE(v_stddev, 1),  -- Avoid division by zero
        COALESCE(v_median, 0),
        COALESCE(v_p95, 0),
        COALESCE(v_count, 0)
    )
    ON CONFLICT (district_code, diagnosis) 
    DO UPDATE SET
        baseline_start = EXCLUDED.baseline_start,
        baseline_end = EXCLUDED.baseline_end,
        mean_cases_per_day = EXCLUDED.mean_cases_per_day,
        stddev_cases = EXCLUDED.stddev_cases,
        median_cases = EXCLUDED.median_cases,
        p95_cases = EXCLUDED.p95_cases,
        sample_size = EXCLUDED.sample_size,
        last_updated = NOW();
END;
$$ LANGUAGE plpgsql;


-- ───────────────────────────────────────────────────────────────────────────────
-- 6.2 Detect outbreak anomalies for today
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION detect_outbreak_anomaly(
    p_district_code VARCHAR(10),
    p_diagnosis VARCHAR(200)
) RETURNS TABLE (
    is_outbreak BOOLEAN,
    severity VARCHAR(20),
    z_score NUMERIC,
    current_cases INTEGER,
    baseline_mean NUMERIC
) AS $$
DECLARE
    v_current_cases INTEGER;
    v_baseline_mean NUMERIC;
    v_stddev NUMERIC;
    v_z_score NUMERIC;
    v_severity VARCHAR(20);
    v_is_outbreak BOOLEAN;
BEGIN
    -- Get today's case count
    SELECT SUM(case_count)
    INTO v_current_cases
    FROM diagnosis_counts_hourly
    WHERE district_code = p_district_code
      AND diagnosis = p_diagnosis
      AND bucket >= DATE_TRUNC('day', NOW())
      AND bucket < DATE_TRUNC('day', NOW()) + INTERVAL '1 day';
    
    v_current_cases := COALESCE(v_current_cases, 0);
    
    -- Get baseline statistics
    SELECT mean_cases_per_day, stddev_cases
    INTO v_baseline_mean, v_stddev
    FROM outbreak_baselines
    WHERE district_code = p_district_code
      AND diagnosis = p_diagnosis;
    
    -- Handle missing baseline
    IF v_baseline_mean IS NULL THEN
        RETURN QUERY SELECT FALSE, 'no_baseline'::VARCHAR, NULL::NUMERIC, v_current_cases, NULL::NUMERIC;
        RETURN;
    END IF;
    
    -- Calculate z-score
    IF v_stddev > 0 THEN
        v_z_score := (v_current_cases - v_baseline_mean) / v_stddev;
    ELSE
        v_z_score := 0;
    END IF;
    
    -- Determine severity
    v_is_outbreak := FALSE;
    v_severity := 'normal';
    
    IF v_z_score >= 4.0 THEN
        v_is_outbreak := TRUE;
        v_severity := 'critical';
    ELSIF v_z_score >= 3.0 THEN
        v_is_outbreak := TRUE;
        v_severity := 'severe';
    ELSIF v_z_score >= 2.5 THEN
        v_is_outbreak := TRUE;
        v_severity := 'moderate';
    ELSIF v_z_score >= 2.0 THEN
        v_is_outbreak := TRUE;
        v_severity := 'warning';
    END IF;
    
    RETURN QUERY SELECT v_is_outbreak, v_severity, v_z_score, v_current_cases, v_baseline_mean;
END;
$$ LANGUAGE plpgsql;


-- ───────────────────────────────────────────────────────────────────────────────
-- 6.3 Get geospatial hotspots using DBSCAN-like clustering
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION detect_geospatial_hotspots(
    p_district_code VARCHAR(10),
    p_diagnosis VARCHAR(200),
    p_hours_back INTEGER DEFAULT 24,
    p_radius_km NUMERIC DEFAULT 5.0,
    p_min_cases INTEGER DEFAULT 5
) RETURNS TABLE (
    cluster_center GEOGRAPHY,
    case_count INTEGER,
    radius_km NUMERIC
) AS $$
BEGIN
    -- Simple spatial clustering using ST_ClusterDBSCAN
    RETURN QUERY
    WITH recent_cases AS (
        SELECT location
        FROM geospatial_events
        WHERE district_code = p_district_code
          AND diagnosis = p_diagnosis
          AND event_time >= NOW() - INTERVAL '1 hour' * p_hours_back
          AND location IS NOT NULL
    ),
    clustered AS (
        SELECT
            location,
            ST_ClusterDBSCAN(location::geometry, eps => p_radius_km * 1000, minpoints => p_min_cases) 
                OVER () AS cluster_id
        FROM recent_cases
    )
    SELECT
        ST_Centroid(ST_Union(location::geometry))::GEOGRAPHY AS cluster_center,
        COUNT(*)::INTEGER AS case_count,
        p_radius_km AS radius_km
    FROM clustered
    WHERE cluster_id IS NOT NULL
    GROUP BY cluster_id
    HAVING COUNT(*) >= p_min_cases
    ORDER BY case_count DESC;
END;
$$ LANGUAGE plpgsql;


-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 7: VIEWS FOR COMMON QUERIES
-- ═══════════════════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────────────────
-- 7.1 Current active outbreaks dashboard view
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW active_outbreaks AS
SELECT
    oa.id,
    oa.alert_time,
    oa.district_code,
    oa.state_code,
    oa.diagnosis,
    oa.current_cases,
    oa.baseline_mean,
    oa.z_score,
    oa.severity,
    oa.status,
    oa.asha_notified,
    oa.district_officer_notified,
    dw.is_notifiable,
    dw.priority_level,
    EXTRACT(EPOCH FROM (NOW() - oa.alert_time))/3600 AS hours_since_alert
FROM outbreak_alerts oa
LEFT JOIN disease_watchlist dw ON oa.diagnosis = dw.diagnosis
WHERE oa.status = 'active'
  AND oa.alert_time >= NOW() - INTERVAL '7 days'
ORDER BY oa.severity DESC, oa.alert_time DESC;


-- ───────────────────────────────────────────────────────────────────────────────
-- 7.2 District health summary (last 24 hours)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW district_health_summary AS
SELECT
    district_code,
    state_code,
    SUM(total_cases) AS total_cases_24h,
    SUM(level_5_emergency) AS emergency_cases,
    SUM(level_4_urgent) AS urgent_cases,
    AVG(avg_triage_level) AS avg_triage_level,
    MAX(bucket) AS last_updated
FROM triage_summary_15min
WHERE bucket >= NOW() - INTERVAL '24 hours'
GROUP BY district_code, state_code;


-- ───────────────────────────────────────────────────────────────────────────────
-- 7.3 Top diseases by district (last 7 days)
-- ───────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW top_diseases_by_district AS
WITH ranked_diseases AS (
    SELECT
        district_code,
        diagnosis,
        SUM(case_count) AS total_cases,
        AVG(avg_triage_level) AS avg_triage,
        ROW_NUMBER() OVER (PARTITION BY district_code ORDER BY SUM(case_count) DESC) AS rank
    FROM diagnosis_counts_hourly
    WHERE bucket >= NOW() - INTERVAL '7 days'
    GROUP BY district_code, diagnosis
)
SELECT
    district_code,
    diagnosis,
    total_cases,
    ROUND(avg_triage, 2) AS avg_triage_level
FROM ranked_diseases
WHERE rank <= 10
ORDER BY district_code, rank;


-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 8: PERFORMANCE OPTIMIZATION
-- ═══════════════════════════════════════════════════════════════════════════════

-- Compression for older chunks (saves 90% storage on time-series data)
SELECT add_compression_policy('triage_events', INTERVAL '7 days');
SELECT add_compression_policy('symptom_events', INTERVAL '7 days');
SELECT add_compression_policy('geospatial_events', INTERVAL '7 days');
SELECT add_compression_policy('asha_activity_events', INTERVAL '7 days');

-- Enable parallel query execution for large scans
ALTER TABLE triage_events SET (parallel_workers = 4);
ALTER TABLE symptom_events SET (parallel_workers = 4);

-- Analyze tables for query planner
ANALYZE triage_events;
ANALYZE symptom_events;
ANALYZE geospatial_events;
ANALYZE asha_activity_events;
ANALYZE outbreak_baselines;
ANALYZE outbreak_alerts;


-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 9: GRANTS & SECURITY
-- ═══════════════════════════════════════════════════════════════════════════════

-- Read-only analytics user for dashboards
-- CREATE ROLE vaidya_analytics WITH LOGIN PASSWORD 'secure_password_here';
-- GRANT CONNECT ON DATABASE vaidya TO vaidya_analytics;
-- GRANT USAGE ON SCHEMA public TO vaidya_analytics;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO vaidya_analytics;
-- GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO vaidya_analytics;

-- Application user (full CRUD on events, read on analytics)
-- CREATE ROLE vaidya_app WITH LOGIN PASSWORD 'app_password_here';
-- GRANT ALL PRIVILEGES ON DATABASE vaidya TO vaidya_app;


-- ═══════════════════════════════════════════════════════════════════════════════
-- END OF SCHEMA
-- ═══════════════════════════════════════════════════════════════════════════════
