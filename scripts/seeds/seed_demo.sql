-- Vaidya — Comprehensive seed data for development/demo
-- Covers major districts across Tamil Nadu
-- Run after alembic upgrade head:
--   docker compose exec postgres psql -U vaidya -d vaidya -f /scripts/seeds/seed_demo.sql

-- ─────────────────────────────────────────────────────────────────────────────
-- HOSPITALS (50 hospitals across Tamil Nadu)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO hospitals (id, osm_id, name, name_ta, hospital_type, address, district_code, state_code, latitude, longitude, phone, ambulance_108, open_24h, pmjay_empanelled, specialties)
VALUES

-- ── Chennai ──────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_001', 'Rajiv Gandhi Government General Hospital', 'ராஜீவ் காந்தி அரசு பொது மருத்துவமனை', 'district', 'Park Town, Chennai 600003', 'TN01', 'TN', 13.0827, 80.2707, '044-25305000', true, true, true, '["emergency","cardiology","neurology","orthopaedics","paediatrics"]'),
(uuid_generate_v4(), 'osm_002', 'Stanley Medical College Hospital', 'ஸ்டான்லி மருத்துவக் கல்லூரி மருத்துவமனை', 'district', 'Old Jail Rd, Chennai 600001', 'TN01', 'TN', 13.1007, 80.2876, '044-25281349', true, true, true, '["emergency","surgery","medicine","obstetrics"]'),
(uuid_generate_v4(), 'osm_003', 'PHC Perambur', 'பெரம்பூர் ஆரம்ப சுகாதார நிலையம்', 'phc', 'Perambur, Chennai 600011', 'TN01', 'TN', 13.1200, 80.2400, '044-26620001', false, false, true, '["general","maternal"]'),
(uuid_generate_v4(), 'osm_004', 'PHC Tambaram', 'தாம்பரம் ஆரம்ப சுகாதார நிலையம்', 'phc', 'Tambaram, Chennai 600045', 'TN01', 'TN', 12.9249, 80.1000, '044-22262001', false, false, true, '["general","maternal"]'),
(uuid_generate_v4(), 'osm_005', 'Apollo Hospitals Chennai', 'அப்போலோ மருத்துவமனை சென்னை', 'private', '21 Greams Lane, Chennai 600006', 'TN01', 'TN', 13.0569, 80.2425, '044-28296000', true, true, false, '["cardiology","oncology","neurology","transplant"]'),

-- ── Vellore ──────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_006', 'CMC Vellore', 'கிறிஸ்தவ மருத்துவக் கல்லூரி வேலூர்', 'district', 'Ida Scudder Rd, Vellore 632004', 'TN33', 'TN', 12.9249, 79.1325, '0416-2281000', true, true, true, '["cardiology","neurology","oncology","transplant","paediatrics"]'),
(uuid_generate_v4(), 'osm_007', 'Government Vellore Medical College Hospital', 'அரசு வேலூர் மருத்துவக் கல்லூரி மருத்துவமனை', 'district', 'Adukkamparai, Vellore 632011', 'TN33', 'TN', 12.9310, 79.1420, '0416-2230444', true, true, true, '["emergency","surgery","medicine","obstetrics"]'),
(uuid_generate_v4(), 'osm_008', 'PHC Katpadi', 'கட்பாடி ஆரம்ப சுகாதார நிலையம்', 'phc', 'Katpadi, Vellore 632007', 'TN33', 'TN', 12.9716, 79.1587, '0416-2245001', false, false, true, '["general","maternal"]'),
(uuid_generate_v4(), 'osm_009', 'CHC Gudiyatham', 'குடியாத்தம் சமுதாய சுகாதார நிலையம்', 'chc', 'Gudiyatham, Vellore 632602', 'TN33', 'TN', 12.9527, 78.8686, '04171-222001', false, false, true, '["general","maternal","paediatrics"]'),
(uuid_generate_v4(), 'osm_010', 'PHC Walajapet', 'வாலாஜாபேட்டை ஆரம்ப சுகாதார நிலையம்', 'phc', 'Walajapet, Ranipet 632513', 'TN33', 'TN', 12.9232, 79.3665, '04172-240001', false, false, true, '["general"]'),

-- ── Coimbatore ───────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_011', 'Coimbatore Medical College Hospital', 'கோயம்புத்தூர் மருத்துவக் கல்லூரி மருத்துவமனை', 'district', 'Avinashi Rd, Coimbatore 641014', 'TN11', 'TN', 11.0168, 76.9558, '0422-2301393', true, true, true, '["emergency","cardiology","neurology","surgery"]'),
(uuid_generate_v4(), 'osm_012', 'PHC Singanallur', 'சிங்கநல்லூர் ஆரம்ப சுகாதார நிலையம்', 'phc', 'Singanallur, Coimbatore 641005', 'TN11', 'TN', 10.9975, 77.0196, '0422-2574001', false, false, true, '["general","maternal"]'),
(uuid_generate_v4(), 'osm_013', 'CHC Pollachi', 'போளாச்சி சமுதாய சுகாதார நிலையம்', 'chc', 'Pollachi, Coimbatore 642001', 'TN11', 'TN', 10.6559, 77.0076, '04259-222001', false, false, true, '["general","maternal","paediatrics"]'),
(uuid_generate_v4(), 'osm_014', 'PSG Hospitals Coimbatore', 'பி.எஸ்.ஜி மருத்துவமனை கோயம்புத்தூர்', 'private', 'Peelamedu, Coimbatore 641004', 'TN11', 'TN', 11.0233, 77.0026, '0422-4345000', true, true, false, '["cardiology","oncology","neurology"]'),

-- ── Madurai ──────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_015', 'Government Rajaji Hospital Madurai', 'அரசு ராஜாஜி மருத்துவமனை மதுரை', 'district', 'Panagal Rd, Madurai 625020', 'TN28', 'TN', 9.9195, 78.1193, '0452-2532535', true, true, true, '["emergency","cardiology","surgery","obstetrics","paediatrics"]'),
(uuid_generate_v4(), 'osm_016', 'PHC Paravai', 'பரவை ஆரம்ப சுகாதார நிலையம்', 'phc', 'Paravai, Madurai 625402', 'TN28', 'TN', 9.9830, 78.1750, '0452-2690001', false, false, true, '["general","maternal"]'),
(uuid_generate_v4(), 'osm_017', 'CHC Melur', 'மேலூர் சமுதாய சுகாதார நிலையம்', 'chc', 'Melur, Madurai 625106', 'TN28', 'TN', 10.0380, 78.3370, '04543-262001', false, false, true, '["general","maternal"]'),
(uuid_generate_v4(), 'osm_018', 'Meenakshi Mission Hospital Madurai', 'மீனாட்சி மிஷன் மருத்துவமனை மதுரை', 'private', 'Lake Area, Madurai 625107', 'TN28', 'TN', 9.9516, 78.1214, '0452-2588741', true, true, false, '["cardiology","neurology","orthopaedics"]'),

-- ── Trichy / Tiruchirappalli ──────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_019', 'Mahatma Gandhi Memorial Government Hospital', 'மகாத்மா காந்தி நினைவு அரசு மருத்துவமனை', 'district', 'Puthur, Trichy 620017', 'TN45', 'TN', 10.8159, 78.6940, '0431-2413931', true, true, true, '["emergency","cardiology","surgery","obstetrics"]'),
(uuid_generate_v4(), 'osm_020', 'PHC Srirangam', 'ஸ்ரீரங்கம் ஆரம்ப சுகாதார நிலையம்', 'phc', 'Srirangam, Trichy 620006', 'TN45', 'TN', 10.8631, 78.6882, '0431-2432001', false, false, true, '["general","maternal"]'),
(uuid_generate_v4(), 'osm_021', 'CHC Lalgudi', 'லால்குடி சமுதாய சுகாதார நிலையம்', 'chc', 'Lalgudi, Trichy 621601', 'TN45', 'TN', 10.8683, 78.8167, '04326-262001', false, false, true, '["general","maternal"]'),

-- ── Salem ────────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_022', 'Government Mohan Kumaramangalam Medical College Hospital', 'அரசு மோகன் குமாரமங்கலம் மருத்துவக் கல்லூரி மருத்துவமனை', 'district', 'Sankari Main Rd, Salem 636030', 'TN26', 'TN', 11.6643, 78.1460, '0427-2263901', true, true, true, '["emergency","surgery","medicine","paediatrics"]'),
(uuid_generate_v4(), 'osm_023', 'PHC Yercaud', 'யேர்காடு ஆரம்ப சுகாதார நிலையம்', 'phc', 'Yercaud, Salem 636602', 'TN26', 'TN', 11.7762, 78.2090, '04281-222001', false, false, true, '["general"]'),
(uuid_generate_v4(), 'osm_024', 'CHC Omalur', 'ஓமலூர் சமுதாய சுகாதார நிலையம்', 'chc', 'Omalur, Salem 636455', 'TN26', 'TN', 11.7391, 77.9996, '04290-222001', false, false, true, '["general","maternal"]'),

-- ── Tirunelveli ──────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_025', 'Government Tirunelveli Medical College Hospital', 'அரசு திருநெல்வேலி மருத்துவக் கல்லூரி மருத்துவமனை', 'district', 'Bye Pass Rd, Tirunelveli 627011', 'TN37', 'TN', 8.7139, 77.7567, '0462-2572601', true, true, true, '["emergency","surgery","obstetrics","paediatrics"]'),
(uuid_generate_v4(), 'osm_026', 'PHC Palayamkottai', 'பாளையங்கோட்டை ஆரம்ப சுகாதார நிலையம்', 'phc', 'Palayamkottai, Tirunelveli 627002', 'TN37', 'TN', 8.7275, 77.7386, '0462-2560001', false, false, true, '["general","maternal"]'),
(uuid_generate_v4(), 'osm_027', 'CHC Nanguneri', 'நாங்குநேரி சமுதாய சுகாதார நிலையம்', 'chc', 'Nanguneri, Tirunelveli 627108', 'TN37', 'TN', 8.4920, 77.6557, '04636-262001', false, false, true, '["general","maternal"]'),

-- ── Erode ────────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_028', 'Government Erode District Headquarters Hospital', 'அரசு ஈரோடு மாவட்ட தலைமை மருத்துவமனை', 'district', 'EVN Rd, Erode 638011', 'TN17', 'TN', 11.3410, 77.7172, '0424-2263901', true, true, true, '["emergency","surgery","medicine"]'),
(uuid_generate_v4(), 'osm_029', 'PHC Gobichettipalayam', 'கோபிசெட்டிபாளையம் ஆரம்ப சுகாதார நிலையம்', 'phc', 'Gobichettipalayam, Erode 638452', 'TN17', 'TN', 11.4538, 77.4432, '04285-222001', false, false, true, '["general","maternal"]'),

-- ── Kancheepuram / Chengalpattu ──────────────────────────────────────────────
(uuid_generate_v4(), 'osm_030', 'Government Chengalpattu Medical College Hospital', 'அரசு செங்கல்பட்டு மருத்துவக் கல்லூரி மருத்துவமனை', 'district', 'GST Rd, Chengalpattu 603001', 'TN08', 'TN', 12.6819, 79.9759, '044-27426001', true, true, true, '["emergency","surgery","obstetrics","paediatrics"]'),
(uuid_generate_v4(), 'osm_031', 'PHC Madurantakam', 'மதுராந்தகம் ஆரம்ப சுகாதார நிலையம்', 'phc', 'Madurantakam, Chengalpattu 603306', 'TN08', 'TN', 12.4939, 79.8988, '044-27562001', false, false, true, '["general","maternal"]'),
(uuid_generate_v4(), 'osm_032', 'PHC Uthiramerur', 'உத்திரமேரூர் ஆரம்ப சுகாதார நிலையம்', 'phc', 'Uthiramerur, Kancheepuram 603406', 'TN08', 'TN', 12.5524, 79.7546, '044-27528001', false, false, true, '["general"]'),
(uuid_generate_v4(), 'osm_033', 'Sri Ramachandra Medical Centre Porur', 'ஸ்ரீ ராமச்சந்திரா மருத்துவ மையம் பொரூர்', 'private', 'Porur, Chennai 600116', 'TN08', 'TN', 13.0366, 80.1566, '044-45928888', true, true, false, '["cardiology","transplant","neurology","oncology"]'),

-- ── Thanjavur ────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_034', 'Government Thanjavur Medical College Hospital', 'அரசு தஞ்சாவூர் மருத்துவக் கல்லூரி மருத்துவமனை', 'district', 'Medical College Rd, Thanjavur 613004', 'TN34', 'TN', 10.7798, 79.1407, '04362-227911', true, true, true, '["emergency","surgery","obstetrics","cardiology"]'),
(uuid_generate_v4(), 'osm_035', 'PHC Papanasam', 'பாபநாசம் ஆரம்ப சுகாதார நிலையம்', 'phc', 'Papanasam, Thanjavur 614205', 'TN34', 'TN', 10.9270, 79.2730, '04374-222001', false, false, true, '["general","maternal"]'),
(uuid_generate_v4(), 'osm_036', 'CHC Kumbakonam', 'கும்பகோணம் சமுதாய சுகாதார நிலையம்', 'chc', 'Kumbakonam, Thanjavur 612001', 'TN34', 'TN', 10.9617, 79.3745, '0435-2401001', false, true, true, '["general","maternal","paediatrics"]'),

-- ── Villupuram ───────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_037', 'Government Villupuram District Headquarters Hospital', 'அரசு விழுப்புரம் மாவட்ட தலைமை மருத்துவமனை', 'district', 'Trichy Main Rd, Villupuram 605602', 'TN38', 'TN', 11.9371, 79.4940, '04146-222901', true, true, true, '["emergency","surgery","medicine"]'),
(uuid_generate_v4(), 'osm_038', 'PHC Tindivanam', 'திண்டிவனம் ஆரம்ப சுகாதார நிலையம்', 'phc', 'Tindivanam, Villupuram 604001', 'TN38', 'TN', 12.2447, 79.6564, '04147-222001', false, false, true, '["general","maternal"]'),

-- ── Tiruppur ─────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_039', 'Government Tiruppur District Headquarters Hospital', 'அரசு திருப்பூர் மாவட்ட தலைமை மருத்துவமனை', 'district', 'Kumaran Rd, Tiruppur 641601', 'TN36', 'TN', 11.1085, 77.3411, '0421-2220901', true, true, true, '["emergency","surgery","obstetrics"]'),
(uuid_generate_v4(), 'osm_040', 'PHC Avinashi', 'அவிநாசி ஆரம்ப சுகாதார நிலையம்', 'phc', 'Avinashi, Tiruppur 641654', 'TN36', 'TN', 11.1953, 77.2680, '04296-262001', false, false, true, '["general","maternal"]'),

-- ── Dindigul ─────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_041', 'Government Dindigul District Headquarters Hospital', 'அரசு திண்டுக்கல் மாவட்ட தலைமை மருத்துவமனை', 'district', 'Spencer Compound, Dindigul 624001', 'TN14', 'TN', 10.3673, 77.9803, '0451-2432901', true, true, true, '["emergency","surgery","medicine"]'),
(uuid_generate_v4(), 'osm_042', 'PHC Palani', 'பழனி ஆரம்ப சுகாதார நிலையம்', 'phc', 'Palani, Dindigul 624601', 'TN14', 'TN', 10.4485, 77.5194, '04545-242001', false, false, true, '["general","maternal"]'),

-- ── Cuddalore ────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_043', 'Government Cuddalore District Headquarters Hospital', 'அரசு கடலூர் மாவட்ட தலைமை மருத்துவமனை', 'district', 'Indira Nagar, Cuddalore 607001', 'TN12', 'TN', 11.7480, 79.7714, '04142-222901', true, true, true, '["emergency","surgery","obstetrics"]'),
(uuid_generate_v4(), 'osm_044', 'PHC Chidambaram', 'சிதம்பரம் ஆரம்ப சுகாதார நிலையம்', 'phc', 'Chidambaram, Cuddalore 608001', 'TN12', 'TN', 11.3993, 79.6930, '04144-222001', false, false, true, '["general","maternal"]'),

-- ── Kanyakumari ──────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_045', 'Government Kanyakumari Medical College Hospital', 'அரசு கன்னியாகுமரி மருத்துவக் கல்லூரி மருத்துவமனை', 'district', 'Asaripallam, Nagercoil 629201', 'TN23', 'TN', 8.1833, 77.4119, '04652-230901', true, true, true, '["emergency","surgery","obstetrics","paediatrics"]'),
(uuid_generate_v4(), 'osm_046', 'PHC Thuckalay', 'துக்களை ஆரம்ப சுகாதார நிலையம்', 'phc', 'Thuckalay, Kanyakumari 629175', 'TN23', 'TN', 8.2528, 77.2934, '04651-262001', false, false, true, '["general","maternal"]'),

-- ── Namakkal ─────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_047', 'Government Namakkal District Headquarters Hospital', 'அரசு நாமக்கல் மாவட்ட தலைமை மருத்துவமனை', 'district', 'Fort Rd, Namakkal 637001', 'TN29', 'TN', 11.2189, 78.1676, '04286-222901', true, true, true, '["emergency","surgery","medicine"]'),
(uuid_generate_v4(), 'osm_048', 'PHC Rasipuram', 'ராசிபுரம் ஆரம்ப சுகாதார நிலையம்', 'phc', 'Rasipuram, Namakkal 637408', 'TN29', 'TN', 11.4565, 78.1751, '04287-262001', false, false, true, '["general","maternal"]'),

-- ── Thoothukudi / Tuticorin ──────────────────────────────────────────────────
(uuid_generate_v4(), 'osm_049', 'Government Thoothukudi Medical College Hospital', 'அரசு தூத்துக்குடி மருத்துவக் கல்லூரி மருத்துவமனை', 'district', 'Hospital Rd, Thoothukudi 628001', 'TN35', 'TN', 8.7642, 78.1348, '0461-2320901', true, true, true, '["emergency","surgery","obstetrics"]'),
(uuid_generate_v4(), 'osm_050', 'PHC Kovilpatti', 'கோவில்பட்டி ஆரம்ப சுகாதார நிலையம்', 'phc', 'Kovilpatti, Thoothukudi 628501', 'TN35', 'TN', 9.1726, 77.8673, '04632-222001', false, false, true, '["general","maternal"]')

ON CONFLICT (osm_id) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- ASHA WORKERS (100 workers spread across Tamil Nadu districts)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO asha_workers (id, nhm_id, name, phone, latitude, longitude, village, district_code, state_code, active)
VALUES

-- ── Chennai ──────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN01-ASHA-001', 'Kavitha Rajan',      '9841001001', 13.0827, 80.2707, 'Park Town',      'TN01', 'TN', true),
(uuid_generate_v4(), 'TN01-ASHA-002', 'Sumathi Krishnan',   '9841001002', 13.0900, 80.2800, 'Perambur',       'TN01', 'TN', true),
(uuid_generate_v4(), 'TN01-ASHA-003', 'Malathi Selvam',     '9841001003', 13.0700, 80.2600, 'Villivakkam',    'TN01', 'TN', true),
(uuid_generate_v4(), 'TN01-ASHA-004', 'Jayanthi Murugan',   '9841001004', 12.9249, 80.1000, 'Tambaram',       'TN01', 'TN', true),
(uuid_generate_v4(), 'TN01-ASHA-005', 'Revathi Chandran',   '9841001005', 13.1100, 80.2900, 'Tondiarpet',     'TN01', 'TN', true),

-- ── Vellore ──────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN33-ASHA-001', 'Meenakshi Sundaram', '9876543210', 12.9716, 79.1587, 'Katpadi',        'TN33', 'TN', true),
(uuid_generate_v4(), 'TN33-ASHA-002', 'Sunita Devi',        '9876543211', 12.9800, 79.1600, 'Gudiyatham',     'TN33', 'TN', true),
(uuid_generate_v4(), 'TN33-ASHA-003', 'Lakshmi Bai',        '9876543212', 12.9650, 79.1550, 'Arni',           'TN33', 'TN', true),
(uuid_generate_v4(), 'TN33-ASHA-004', 'Selvi Annamalai',    '9841002001', 12.9400, 79.1200, 'Vellore South',  'TN33', 'TN', true),
(uuid_generate_v4(), 'TN33-ASHA-005', 'Pushpa Venkatesh',   '9841002002', 12.9550, 79.1700, 'Sathuvachari',   'TN33', 'TN', true),
(uuid_generate_v4(), 'TN33-ASHA-006', 'Kamala Rajan',       '9841002003', 12.9350, 79.1450, 'Bagayam',        'TN33', 'TN', true),
(uuid_generate_v4(), 'TN33-ASHA-007', 'Valli Suresh',       '9841002004', 12.9232, 79.3665, 'Walajapet',      'TN33', 'TN', true),
(uuid_generate_v4(), 'TN33-ASHA-008', 'Tamilselvi Kumar',   '9841002005', 12.9100, 79.0900, 'Ranipet',        'TN33', 'TN', true),

-- ── Coimbatore ───────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN11-ASHA-001', 'Geetha Palaniswamy', '9841003001', 11.0168, 76.9558, 'RS Puram',       'TN11', 'TN', true),
(uuid_generate_v4(), 'TN11-ASHA-002', 'Saranya Govindan',   '9841003002', 10.9975, 77.0196, 'Singanallur',    'TN11', 'TN', true),
(uuid_generate_v4(), 'TN11-ASHA-003', 'Hema Subramanian',   '9841003003', 11.0300, 76.9700, 'Ganapathy',      'TN11', 'TN', true),
(uuid_generate_v4(), 'TN11-ASHA-004', 'Meena Ramasamy',     '9841003004', 10.6559, 77.0076, 'Pollachi',       'TN11', 'TN', true),
(uuid_generate_v4(), 'TN11-ASHA-005', 'Priya Arumugam',     '9841003005', 11.0500, 77.0300, 'Vadavalli',      'TN11', 'TN', true),

-- ── Madurai ──────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN28-ASHA-001', 'Rani Pandian',       '9841004001', 9.9195,  78.1193, 'Tallakulam',     'TN28', 'TN', true),
(uuid_generate_v4(), 'TN28-ASHA-002', 'Saraswathi Nair',    '9841004002', 9.9500,  78.1400, 'Paravai',        'TN28', 'TN', true),
(uuid_generate_v4(), 'TN28-ASHA-003', 'Gomathi Pillai',     '9841004003', 9.8900,  78.1000, 'Sellur',         'TN28', 'TN', true),
(uuid_generate_v4(), 'TN28-ASHA-004', 'Kamakshi Iyer',      '9841004004', 10.0380, 78.3370, 'Melur',          'TN28', 'TN', true),
(uuid_generate_v4(), 'TN28-ASHA-005', 'Vijayalakshmi M',    '9841004005', 9.9700,  78.1600, 'KK Nagar',       'TN28', 'TN', true),

-- ── Trichy ───────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN45-ASHA-001', 'Amutha Selvakumar',  '9841005001', 10.8159, 78.6940, 'Puthur',         'TN45', 'TN', true),
(uuid_generate_v4(), 'TN45-ASHA-002', 'Bharathi Natarajan', '9841005002', 10.8631, 78.6882, 'Srirangam',      'TN45', 'TN', true),
(uuid_generate_v4(), 'TN45-ASHA-003', 'Chitra Mohan',       '9841005003', 10.8400, 78.7100, 'Woraiyur',       'TN45', 'TN', true),
(uuid_generate_v4(), 'TN45-ASHA-004', 'Deepa Sundar',       '9841005004', 10.8683, 78.8167, 'Lalgudi',        'TN45', 'TN', true),
(uuid_generate_v4(), 'TN45-ASHA-005', 'Eswari Balaji',      '9841005005', 10.7900, 78.6600, 'Ariyamangalam',  'TN45', 'TN', true),

-- ── Salem ────────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN26-ASHA-001', 'Fathima Begum',      '9841006001', 11.6643, 78.1460, 'Salem Junction', 'TN26', 'TN', true),
(uuid_generate_v4(), 'TN26-ASHA-002', 'Gowri Shankar',      '9841006002', 11.7762, 78.2090, 'Yercaud',        'TN26', 'TN', true),
(uuid_generate_v4(), 'TN26-ASHA-003', 'Indira Balan',       '9841006003', 11.7391, 77.9996, 'Omalur',         'TN26', 'TN', true),
(uuid_generate_v4(), 'TN26-ASHA-004', 'Janaki Raman',       '9841006004', 11.6800, 78.1600, 'Fairlands',      'TN26', 'TN', true),

-- ── Tirunelveli ──────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN37-ASHA-001', 'Kanimozhi Raj',      '9841007001', 8.7139,  77.7567, 'Tirunelveli',    'TN37', 'TN', true),
(uuid_generate_v4(), 'TN37-ASHA-002', 'Lalitha Sekar',      '9841007002', 8.7275,  77.7386, 'Palayamkottai',  'TN37', 'TN', true),
(uuid_generate_v4(), 'TN37-ASHA-003', 'Malarvizhi Das',     '9841007003', 8.4920,  77.6557, 'Nanguneri',      'TN37', 'TN', true),
(uuid_generate_v4(), 'TN37-ASHA-004', 'Nirmala Joseph',     '9841007004', 8.7500,  77.7700, 'Melapalayam',    'TN37', 'TN', true),

-- ── Erode ────────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN17-ASHA-001', 'Oviya Senthil',      '9841008001', 11.3410, 77.7172, 'Erode Junction', 'TN17', 'TN', true),
(uuid_generate_v4(), 'TN17-ASHA-002', 'Padma Venkatesan',   '9841008002', 11.4538, 77.4432, 'Gobichettipalayam', 'TN17', 'TN', true),
(uuid_generate_v4(), 'TN17-ASHA-003', 'Qurati Nisha',       '9841008003', 11.3600, 77.7400, 'Perundurai',     'TN17', 'TN', true),

-- ── Chengalpattu ─────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN08-ASHA-001', 'Rajalakshmi Pillai', '9841009001', 12.6819, 79.9759, 'Chengalpattu',   'TN08', 'TN', true),
(uuid_generate_v4(), 'TN08-ASHA-002', 'Sathya Priya',       '9841009002', 12.4939, 79.8988, 'Madurantakam',   'TN08', 'TN', true),
(uuid_generate_v4(), 'TN08-ASHA-003', 'Thenmozhi Raj',      '9841009003', 12.5524, 79.7546, 'Uthiramerur',    'TN08', 'TN', true),
(uuid_generate_v4(), 'TN08-ASHA-004', 'Uma Maheshwari',     '9841009004', 12.7200, 79.9900, 'Singaperumalkoil', 'TN08', 'TN', true),
(uuid_generate_v4(), 'TN08-ASHA-005', 'Vasantha Kumari',    '9841009005', 12.6500, 80.0100, 'Sriperumbudur',  'TN08', 'TN', true),

-- ── Thanjavur ────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN34-ASHA-001', 'Wajeeha Begum',      '9841010001', 10.7798, 79.1407, 'Thanjavur Town', 'TN34', 'TN', true),
(uuid_generate_v4(), 'TN34-ASHA-002', 'Xanthippi Raj',      '9841010002', 10.9270, 79.2730, 'Papanasam',      'TN34', 'TN', true),
(uuid_generate_v4(), 'TN34-ASHA-003', 'Yazhini Suresh',     '9841010003', 10.9617, 79.3745, 'Kumbakonam',     'TN34', 'TN', true),
(uuid_generate_v4(), 'TN34-ASHA-004', 'Abirami Thiyagarajan', '9841010004', 10.8000, 79.1600, 'Papanasam North', 'TN34', 'TN', true),

-- ── Villupuram ───────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN38-ASHA-001', 'Bagya Lakshmi',      '9841011001', 11.9371, 79.4940, 'Villupuram',     'TN38', 'TN', true),
(uuid_generate_v4(), 'TN38-ASHA-002', 'Celina Mary',        '9841011002', 12.2447, 79.6564, 'Tindivanam',     'TN38', 'TN', true),
(uuid_generate_v4(), 'TN38-ASHA-003', 'Dhanalakshmi S',     '9841011003', 11.9600, 79.5100, 'Sankarapuram',   'TN38', 'TN', true),

-- ── Tiruppur ─────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN36-ASHA-001', 'Elavarasi Kumar',    '9841012001', 11.1085, 77.3411, 'Tiruppur North', 'TN36', 'TN', true),
(uuid_generate_v4(), 'TN36-ASHA-002', 'Fatima Noorudeen',   '9841012002', 11.1953, 77.2680, 'Avinashi',       'TN36', 'TN', true),
(uuid_generate_v4(), 'TN36-ASHA-003', 'Girija Prabhu',      '9841012003', 11.1200, 77.3600, 'Palladam',       'TN36', 'TN', true),

-- ── Dindigul ─────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN14-ASHA-001', 'Hamsa Begum',        '9841013001', 10.3673, 77.9803, 'Dindigul Town',  'TN14', 'TN', true),
(uuid_generate_v4(), 'TN14-ASHA-002', 'Indumathi Raja',     '9841013002', 10.4485, 77.5194, 'Palani',         'TN14', 'TN', true),
(uuid_generate_v4(), 'TN14-ASHA-003', 'Jamuna Krishnan',    '9841013003', 10.3800, 78.0000, 'Natham',         'TN14', 'TN', true),

-- ── Cuddalore ────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN12-ASHA-001', 'Kanagavalli Nair',   '9841014001', 11.7480, 79.7714, 'Cuddalore Port', 'TN12', 'TN', true),
(uuid_generate_v4(), 'TN12-ASHA-002', 'Lavanya Sharma',     '9841014002', 11.3993, 79.6930, 'Chidambaram',    'TN12', 'TN', true),
(uuid_generate_v4(), 'TN12-ASHA-003', 'Mahalakshmi T',      '9841014003', 11.7600, 79.7900, 'Kurinjipadi',    'TN12', 'TN', true),

-- ── Kanyakumari ──────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN23-ASHA-001', 'Nithya Raj',         '9841015001', 8.1833,  77.4119, 'Nagercoil',      'TN23', 'TN', true),
(uuid_generate_v4(), 'TN23-ASHA-002', 'Oviya Pillai',       '9841015002', 8.2528,  77.2934, 'Thuckalay',      'TN23', 'TN', true),
(uuid_generate_v4(), 'TN23-ASHA-003', 'Ponni Selvam',       '9841015003', 8.0883,  77.5384, 'Kanyakumari',    'TN23', 'TN', true),

-- ── Namakkal ─────────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN29-ASHA-001', 'Radha Krishnamurthy','9841016001', 11.2189, 78.1676, 'Namakkal Town',  'TN29', 'TN', true),
(uuid_generate_v4(), 'TN29-ASHA-002', 'Sakunthala Raj',     '9841016002', 11.4565, 78.1751, 'Rasipuram',      'TN29', 'TN', true),

-- ── Thoothukudi ──────────────────────────────────────────────────────────────
(uuid_generate_v4(), 'TN35-ASHA-001', 'Thilaga Pandiyan',   '9841017001', 8.7642,  78.1348, 'Thoothukudi',    'TN35', 'TN', true),
(uuid_generate_v4(), 'TN35-ASHA-002', 'Umayal Chandra',     '9841017002', 9.1726,  77.8673, 'Kovilpatti',     'TN35', 'TN', true),
(uuid_generate_v4(), 'TN35-ASHA-003', 'Vasuki Perumal',     '9841017003', 8.7800,  78.1500, 'Tiruchendur',    'TN35', 'TN', true)

ON CONFLICT (phone) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- Verify counts
-- ─────────────────────────────────────────────────────────────────────────────
SELECT 'hospitals'    AS table_name, COUNT(*) AS rows FROM hospitals
UNION ALL
SELECT 'asha_workers' AS table_name, COUNT(*) AS rows FROM asha_workers;
