-- AgentGuard Weather Platform Schema
-- PostgreSQL database schema for weather data benchmark
-- Source: WeatherAPI.com historical data
--
-- Design note: the raw layer deliberately has NO unique constraints on the
-- fact tables and NO check constraints. Injected duplicates and invalid
-- values must load; benchmark tasks detect them downstream via SQL.

-- ============================================================================
-- LOCATIONS TABLE
-- ============================================================================
-- Stores information about weather monitoring locations (cities)

CREATE TABLE IF NOT EXISTS locations (
    location_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    region VARCHAR(100),
    country VARCHAR(100) NOT NULL,
    latitude DECIMAL(9, 6),
    longitude DECIMAL(9, 6),
    timezone_id VARCHAR(50),
    query_string VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_location_coords UNIQUE (latitude, longitude)
);

CREATE INDEX IF NOT EXISTS idx_locations_country ON locations(country);
CREATE INDEX IF NOT EXISTS idx_locations_name ON locations(name);

COMMENT ON TABLE locations IS 'Weather monitoring locations (cities)';
COMMENT ON COLUMN locations.query_string IS 'Original query string used to fetch this location';


-- ============================================================================
-- DAILY WEATHER TABLE
-- ============================================================================
-- Stores daily weather summaries for each location

CREATE TABLE IF NOT EXISTS daily_weather (
    id SERIAL PRIMARY KEY,
    location_id INTEGER NOT NULL REFERENCES locations(location_id),
    date DATE NOT NULL,
    
    -- Temperature metrics (Celsius)
    max_temp_c DECIMAL(5, 2),
    min_temp_c DECIMAL(5, 2),
    avg_temp_c DECIMAL(5, 2),
    
    -- Wind
    max_wind_kph DECIMAL(6, 2),
    
    -- Precipitation
    total_precip_mm DECIMAL(7, 2),
    total_snow_cm DECIMAL(6, 2),
    
    -- Visibility and humidity
-- No CHECK constraint: the raw layer intentionally accepts dirty data
-- (injected invalid values are a benchmark quality issue, detected via SQL)
    avg_visibility_km DECIMAL(5, 2),
    avg_humidity INTEGER,
    
    -- Rain/Snow predictions
    daily_will_it_rain SMALLINT,
    daily_chance_of_rain INTEGER,
    daily_will_it_snow SMALLINT,
    daily_chance_of_snow INTEGER,
    
    -- Condition
    condition_text VARCHAR(50),
    condition_code INTEGER,
    
    -- UV Index
    uv_index DECIMAL(4, 2),
    
    -- Astronomical data
    sunrise TIME,
    sunset TIME,
    moonrise TIME,
    moonset TIME,
    moon_phase VARCHAR(30),
    moon_illumination INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daily_weather_date ON daily_weather(date);
CREATE INDEX IF NOT EXISTS idx_daily_weather_location ON daily_weather(location_id);
CREATE INDEX IF NOT EXISTS idx_daily_weather_condition ON daily_weather(condition_code);

COMMENT ON TABLE daily_weather IS 'Daily weather summaries per location';
COMMENT ON COLUMN daily_weather.condition_code IS 'WeatherAPI condition code for weather icons';


-- ============================================================================
-- HOURLY WEATHER TABLE
-- ============================================================================
-- Stores hourly weather observations for each location

CREATE TABLE IF NOT EXISTS hourly_weather (
    id SERIAL PRIMARY KEY,
    location_id INTEGER NOT NULL REFERENCES locations(location_id),
    datetime TIMESTAMP NOT NULL,
    
    -- Temperature (Celsius)
    temp_c DECIMAL(5, 2),
    feels_like_c DECIMAL(5, 2),
    dewpoint_c DECIMAL(5, 2),
    heatindex_c DECIMAL(5, 2),
    windchill_c DECIMAL(5, 2),
    
    -- Wind
    wind_kph DECIMAL(6, 2),
    wind_degree INTEGER,
    wind_dir VARCHAR(3),
    gust_kph DECIMAL(6, 2),
    
    -- Pressure and precipitation
    pressure_mb DECIMAL(7, 2),
    precip_mm DECIMAL(6, 2),
    snow_cm DECIMAL(5, 2),
    
    -- Humidity and visibility
    humidity INTEGER,
    cloud INTEGER,
    visibility_km DECIMAL(5, 2),
    
    -- UV and day/night
    uv_index DECIMAL(4, 2),
    is_day SMALLINT,
    
    -- Condition
    condition_text VARCHAR(50),
    condition_code INTEGER,
    
    -- Precipitation chances
    chance_of_rain INTEGER,
    chance_of_snow INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_hourly_weather_datetime ON hourly_weather(datetime);
CREATE INDEX IF NOT EXISTS idx_hourly_weather_location ON hourly_weather(location_id);
CREATE INDEX IF NOT EXISTS idx_hourly_weather_date ON hourly_weather((datetime::date));

COMMENT ON TABLE hourly_weather IS 'Hourly weather observations per location';
COMMENT ON COLUMN hourly_weather.is_day IS '1 = day, 0 = night';


-- ============================================================================
-- WEATHER ALERTS TABLE (for future use)
-- ============================================================================
-- Stores weather alerts and warnings

CREATE TABLE IF NOT EXISTS weather_alerts (
    id SERIAL PRIMARY KEY,
    location_id INTEGER NOT NULL REFERENCES locations(location_id),
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    headline VARCHAR(255),
    description TEXT,
    effective_at TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_weather_alerts_location ON weather_alerts(location_id);
CREATE INDEX IF NOT EXISTS idx_weather_alerts_effective ON weather_alerts(effective_at);

COMMENT ON TABLE weather_alerts IS 'Weather alerts and warnings per location';


-- ============================================================================
-- DATA QUALITY ISSUES LOG (for benchmark tracking)
-- ============================================================================
-- Tracks intentionally injected data quality issues

CREATE TABLE IF NOT EXISTS data_quality_log (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    issue_type VARCHAR(30) NOT NULL,  -- 'duplicate', 'null', 'invalid', 'orphan'
    record_id INTEGER,
    column_name VARCHAR(50),
    original_value TEXT,
    injected_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dq_log_table ON data_quality_log(table_name);
CREATE INDEX IF NOT EXISTS idx_dq_log_type ON data_quality_log(issue_type);

COMMENT ON TABLE data_quality_log IS 'Log of intentionally injected data quality issues for benchmark testing';


-- ============================================================================
-- USEFUL VIEWS
-- ============================================================================

-- View: Daily weather with location details
CREATE OR REPLACE VIEW v_daily_weather_full AS
SELECT 
    dw.*,
    l.name AS location_name,
    l.country,
    l.latitude,
    l.longitude,
    l.timezone_id
FROM daily_weather dw
JOIN locations l ON dw.location_id = l.location_id;

COMMENT ON VIEW v_daily_weather_full IS 'Daily weather with location details';


-- View: Monthly weather averages per location
CREATE OR REPLACE VIEW v_monthly_averages AS
SELECT 
    location_id,
    DATE_TRUNC('month', date) AS month,
    COUNT(*) AS days_recorded,
    ROUND(AVG(avg_temp_c)::numeric, 2) AS avg_temp_c,
    ROUND(MAX(max_temp_c)::numeric, 2) AS max_temp_c,
    ROUND(MIN(min_temp_c)::numeric, 2) AS min_temp_c,
    ROUND(SUM(total_precip_mm)::numeric, 2) AS total_precip_mm,
    ROUND(AVG(avg_humidity)::numeric, 1) AS avg_humidity,
    ROUND(AVG(max_wind_kph)::numeric, 2) AS avg_max_wind_kph
FROM daily_weather
GROUP BY location_id, DATE_TRUNC('month', date);

COMMENT ON VIEW v_monthly_averages IS 'Monthly weather averages per location';


-- View: Extreme weather days (hottest, coldest, wettest)
CREATE OR REPLACE VIEW v_extreme_weather AS
SELECT 
    dw.location_id,
    l.name AS location_name,
    dw.date,
    dw.max_temp_c,
    dw.min_temp_c,
    dw.total_precip_mm,
    dw.max_wind_kph,
    dw.condition_text,
    CASE 
        WHEN dw.max_temp_c = (SELECT MAX(max_temp_c) FROM daily_weather WHERE location_id = dw.location_id) THEN 'Hottest Day'
        WHEN dw.min_temp_c = (SELECT MIN(min_temp_c) FROM daily_weather WHERE location_id = dw.location_id) THEN 'Coldest Day'
        WHEN dw.total_precip_mm = (SELECT MAX(total_precip_mm) FROM daily_weather WHERE location_id = dw.location_id) THEN 'Wettest Day'
        WHEN dw.max_wind_kph = (SELECT MAX(max_wind_kph) FROM daily_weather WHERE location_id = dw.location_id) THEN 'Windiest Day'
    END AS extreme_type
FROM daily_weather dw
JOIN locations l ON dw.location_id = l.location_id
WHERE 
    dw.max_temp_c = (SELECT MAX(max_temp_c) FROM daily_weather WHERE location_id = dw.location_id)
    OR dw.min_temp_c = (SELECT MIN(min_temp_c) FROM daily_weather WHERE location_id = dw.location_id)
    OR dw.total_precip_mm = (SELECT MAX(total_precip_mm) FROM daily_weather WHERE location_id = dw.location_id AND total_precip_mm > 0)
    OR dw.max_wind_kph = (SELECT MAX(max_wind_kph) FROM daily_weather WHERE location_id = dw.location_id);

COMMENT ON VIEW v_extreme_weather IS 'Extreme weather days per location';


-- View: Data quality summary (for benchmark evaluation)
CREATE OR REPLACE VIEW v_data_quality_summary AS
SELECT 
    'locations' AS table_name,
    COUNT(*) AS total_records,
    COUNT(*) - COUNT(DISTINCT (latitude, longitude)) AS potential_duplicates,
    SUM(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 ELSE 0 END) AS null_coordinates
FROM locations
UNION ALL
SELECT 
    'daily_weather' AS table_name,
    COUNT(*) AS total_records,
    COUNT(*) - COUNT(DISTINCT (location_id, date)) AS potential_duplicates,
    SUM(CASE WHEN avg_temp_c IS NULL THEN 1 ELSE 0 END) AS null_values
FROM daily_weather
UNION ALL
SELECT 
    'hourly_weather' AS table_name,
    COUNT(*) AS total_records,
    COUNT(*) - COUNT(DISTINCT (location_id, datetime)) AS potential_duplicates,
    SUM(CASE WHEN temp_c IS NULL THEN 1 ELSE 0 END) AS null_values
FROM hourly_weather;

COMMENT ON VIEW v_data_quality_summary IS 'Summary of data quality issues per table';
