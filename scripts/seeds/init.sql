-- Vaidya — PostgreSQL init script
-- Runs once on first container start
-- Sets up TimescaleDB extension + hypertable for triage_events

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable PostGIS for geospatial ASHA lookup (optional but recommended)
-- CREATE EXTENSION IF NOT EXISTS postgis;

-- triage_events will be created by Alembic migrations.
-- After migration runs, convert to hypertable:
-- SELECT create_hypertable('triage_events', 'event_time', if_not_exists => TRUE);

-- Seed: demo ASHA worker for development
-- (Real data: 900k+ workers from NHM open dataset — scripts/seeds/load_asha.py)
INSERT INTO asha_workers (id, name, phone, latitude, longitude, village, district_code, state_code, active)
VALUES
  (uuid_generate_v4(), 'Meenakshi Sundaram', '9876543210', 12.9716, 79.1587, 'Katpadi', 'TN33', 'TN', true),
  (uuid_generate_v4(), 'Sunita Devi',        '9876543211', 12.9800, 79.1600, 'Gudiyatham', 'TN33', 'TN', true),
  (uuid_generate_v4(), 'Lakshmi Bai',        '9876543212', 12.9650, 79.1550, 'Arni', 'TN33', 'TN', true)
ON CONFLICT DO NOTHING;

-- Seed: demo hospitals for development
INSERT INTO hospitals (id, name, hospital_type, address, district_code, state_code, latitude, longitude, ambulance_108, open_24h, pmjay_empanelled)
VALUES
  (uuid_generate_v4(), 'CMC Vellore',         'district', 'Ida Scudder Rd, Vellore 632004', 'TN33', 'TN', 12.9249, 79.1325, true,  true,  true),
  (uuid_generate_v4(), 'PHC Katpadi',          'phc',      'Katpadi, Vellore 632007',         'TN33', 'TN', 12.9716, 79.1587, false, false, true),
  (uuid_generate_v4(), 'CHC Gudiyatham',       'chc',      'Gudiyatham, Vellore 632602',      'TN33', 'TN', 12.9527, 78.8686, false, false, true),
  (uuid_generate_v4(), 'Apollo Reach Vellore', 'private',  'NH 48, Vellore 632004',           'TN33', 'TN', 12.9177, 79.1320, true,  true,  false)
ON CONFLICT DO NOTHING;
