"""Trip storage - SQLite database for all historical trip data."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from toybaru.const import DATA_DIR

DB_PATH = DATA_DIR / "trips.db"

_UPSERT_SQL = """
    INSERT INTO trips (
        id, vin, category, start_ts, end_ts, length_m, duration_s, duration_idle_s,
        max_speed, avg_speed, fuel_consumption,
        start_lat, start_lon, end_lat, end_lon, night_trip,
        length_overspeed, duration_overspeed, length_highway, duration_highway,
        countries,
        score_global, score_acceleration, score_braking, score_constant_speed, score_advice,
        hdc_ev_time, hdc_ev_distance, hdc_charge_time, hdc_charge_dist,
        hdc_eco_time, hdc_eco_dist, hdc_power_time, hdc_power_dist,
        behaviours_json, route_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        vin=excluded.vin,
        length_m=excluded.length_m, duration_s=excluded.duration_s,
        max_speed=excluded.max_speed, avg_speed=excluded.avg_speed,
        score_global=excluded.score_global, score_acceleration=excluded.score_acceleration,
        score_braking=excluded.score_braking, score_constant_speed=excluded.score_constant_speed,
        hdc_ev_time=excluded.hdc_ev_time, hdc_ev_distance=excluded.hdc_ev_distance,
        hdc_charge_time=excluded.hdc_charge_time, hdc_charge_dist=excluded.hdc_charge_dist,
        hdc_eco_time=excluded.hdc_eco_time, hdc_eco_dist=excluded.hdc_eco_dist,
        hdc_power_time=excluded.hdc_power_time, hdc_power_dist=excluded.hdc_power_dist,
        behaviours_json=excluded.behaviours_json, route_json=excluded.route_json,
        imported_at=datetime('now')
"""


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY,
            category INTEGER,
            start_ts TEXT,
            end_ts TEXT,
            length_m INTEGER,
            duration_s INTEGER,
            duration_idle_s INTEGER,
            max_speed REAL,
            avg_speed REAL,
            fuel_consumption REAL,
            start_lat REAL,
            start_lon REAL,
            end_lat REAL,
            end_lon REAL,
            night_trip INTEGER,
            length_overspeed INTEGER,
            duration_overspeed INTEGER,
            length_highway INTEGER,
            duration_highway INTEGER,
            countries TEXT,
            score_global INTEGER,
            score_acceleration INTEGER,
            score_braking INTEGER,
            score_constant_speed INTEGER,
            score_advice INTEGER,
            hdc_ev_time INTEGER,
            hdc_ev_distance INTEGER,
            hdc_charge_time INTEGER,
            hdc_charge_dist INTEGER,
            hdc_eco_time INTEGER,
            hdc_eco_dist INTEGER,
            hdc_power_time INTEGER,
            hdc_power_dist INTEGER,
            behaviours_json TEXT,
            route_json TEXT,
            raw_json TEXT,
            imported_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trips_start_ts ON trips(start_ts)")
    # Migration: add vin column if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(trips)").fetchall()]
    if "vin" not in cols:
        conn.execute("ALTER TABLE trips ADD COLUMN vin TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trips_vin ON trips(vin)")
    conn.commit()
    return conn


def _trip_to_row(trip: dict[str, Any], vin: str | None = None) -> tuple:
    s = trip.get("summary", {})
    scores = trip.get("scores", {})
    hdc = trip.get("hdc", {})
    return (
        trip.get("id"),
        vin,
        trip.get("category"),
        s.get("startTs"),
        s.get("endTs"),
        s.get("length"),
        s.get("duration"),
        s.get("durationIdle"),
        s.get("maxSpeed"),
        s.get("averageSpeed"),
        s.get("fuelConsumption"),
        s.get("startLat"),
        s.get("startLon"),
        s.get("endLat"),
        s.get("endLon"),
        1 if s.get("nightTrip") else 0,
        s.get("lengthOverspeed"),
        s.get("durationOverspeed"),
        s.get("lengthHighway"),
        s.get("durationHighway"),
        json.dumps(s.get("countries", [])),
        scores.get("global"),
        scores.get("acceleration"),
        scores.get("braking"),
        scores.get("constantSpeed"),
        scores.get("advice"),
        hdc.get("evTime"),
        hdc.get("evDistance"),
        hdc.get("chargeTime"),
        hdc.get("chargeDist"),
        hdc.get("ecoTime"),
        hdc.get("ecoDist"),
        hdc.get("powerTime"),
        hdc.get("powerDist"),
        json.dumps(trip.get("behaviours", [])),
        json.dumps(trip.get("route", [])),
    )


def upsert_trips(trips: list[dict[str, Any]], vin: str | None = None) -> tuple[int, int]:
    """Bulk upsert trips. Returns (new_count, updated_count)."""
    conn = _get_db()
    new = 0
    updated = 0
    for trip in trips:
        existing = conn.execute("SELECT 1 FROM trips WHERE id = ?", (trip.get("id"),)).fetchone()
        conn.execute(_UPSERT_SQL, _trip_to_row(trip, vin))
        if existing:
            updated += 1
        else:
            new += 1
    conn.commit()
    conn.close()
    return new, updated


def get_latest_trip_timestamp() -> str | None:
    """Get the start_ts of the newest trip in the DB."""
    conn = _get_db()
    row = conn.execute("SELECT MAX(start_ts) FROM trips").fetchone()
    conn.close()
    return row[0] if row else None


def estimate_kwh_100km(avg_speed: float, reku_pct: float, power_pct: float) -> float:
    """Estimate energy consumption in kWh/100km from trip characteristics."""
    v = max(avg_speed, 1)
    e_base = 10.0
    e_speed = 0.0013 * v * v
    e_regen = -(reku_pct / 100) * 5.0
    e_power = (power_pct / 100) * 5.0
    e_aux = 2.0 * (100 / v)
    return max(e_base + e_speed + e_regen + e_power + e_aux, 5.0)


def get_detailed_stats(vin: str | None = None, from_date: str | None = None, to_date: str | None = None) -> dict:
    """Comprehensive stats for the stats page."""
    conn = _get_db()
    w = "WHERE 1=1"
    p: list = []
    if vin:
        w += " AND vin = ?"; p.append(vin)
    if from_date:
        w += " AND start_ts >= ?"; p.append(from_date)
    if to_date:
        w += " AND start_ts <= ?"; p.append(to_date + "T23:59:59Z")

    # Overview
    ov = conn.execute(f"""
        SELECT COUNT(*), SUM(length_m), SUM(duration_s), AVG(avg_speed), MAX(max_speed),
               AVG(score_global), MIN(start_ts), MAX(start_ts),
               SUM(hdc_charge_dist), SUM(hdc_ev_distance), SUM(hdc_eco_dist), SUM(hdc_power_dist),
               SUM(duration_idle_s), SUM(length_highway), SUM(duration_highway),
               AVG(score_acceleration), AVG(score_braking), AVG(score_constant_speed),
               SUM(CASE WHEN night_trip=1 THEN 1 ELSE 0 END),
               SUM(length_overspeed)
        FROM trips {w}
    """, p).fetchone()

    if not ov or not ov[0]:
        conn.close()
        return {"total_trips": 0}

    total_trips, total_m, total_s, avg_spd, max_spd = ov[0], ov[1] or 0, ov[2] or 0, ov[3], ov[4]
    ev_d = ov[9] or 1

    # Monthly
    monthly = conn.execute(f"""
        SELECT SUBSTR(start_ts,1,7) as month, COUNT(*) as trips,
               ROUND(SUM(length_m)/1000.0) as km, ROUND(AVG(avg_speed),1) as spd,
               ROUND(AVG(score_global),1) as score,
               ROUND(AVG(CASE WHEN hdc_ev_distance>0 THEN hdc_charge_dist*100.0/hdc_ev_distance END),1) as reku,
               ROUND(AVG(CASE WHEN hdc_ev_distance>0 THEN hdc_eco_dist*100.0/hdc_ev_distance END),1) as eco,
               ROUND(AVG(CASE WHEN hdc_ev_distance>0 THEN hdc_power_dist*100.0/hdc_ev_distance END),1) as pwr
        FROM trips {w} GROUP BY month ORDER BY month
    """, p).fetchall()

    # Weekday
    weekday = conn.execute(f"""
        SELECT CASE CAST(strftime('%w', start_ts) AS INTEGER)
            WHEN 0 THEN 'Sun' WHEN 1 THEN 'Mon' WHEN 2 THEN 'Tue' WHEN 3 THEN 'Wed'
            WHEN 4 THEN 'Thu' WHEN 5 THEN 'Fri' WHEN 6 THEN 'Sat' END as day,
            COUNT(*) as trips, ROUND(SUM(length_m)/1000.0) as km
        FROM trips {w}
        GROUP BY strftime('%w', start_ts)
        ORDER BY CAST(strftime('%w', start_ts) AS INTEGER)
    """, p).fetchall()

    # Hour of day
    hourly = conn.execute(f"""
        SELECT CAST(SUBSTR(start_ts,12,2) AS INTEGER) as hour, COUNT(*) as trips, ROUND(SUM(length_m)/1000.0) as km
        FROM trips {w} GROUP BY hour ORDER BY hour
    """, p).fetchall()

    # Speed categories
    speed_cats = conn.execute(f"""
        SELECT
            SUM(CASE WHEN avg_speed < 40 THEN 1 ELSE 0 END) as city,
            SUM(CASE WHEN avg_speed >= 40 AND avg_speed < 80 THEN 1 ELSE 0 END) as rural,
            SUM(CASE WHEN avg_speed >= 80 THEN 1 ELSE 0 END) as highway,
            SUM(CASE WHEN avg_speed < 40 THEN length_m ELSE 0 END) as city_m,
            SUM(CASE WHEN avg_speed >= 40 AND avg_speed < 80 THEN length_m ELSE 0 END) as rural_m,
            SUM(CASE WHEN avg_speed >= 80 THEN length_m ELSE 0 END) as highway_m
        FROM trips {w}
    """, p).fetchone()

    # Score distribution (buckets of 10)
    score_dist = conn.execute(f"""
        SELECT (score_global / 10) * 10 as bucket, COUNT(*) as cnt
        FROM trips {w} AND score_global IS NOT NULL
        GROUP BY bucket ORDER BY bucket
    """, p).fetchall()

    # Records
    records = {}
    for label, sql in [
        ("longest_trip", f"SELECT id, length_m, start_ts FROM trips {w} ORDER BY length_m DESC LIMIT 1"),
        ("fastest_avg", f"SELECT id, avg_speed, start_ts FROM trips {w} ORDER BY avg_speed DESC LIMIT 1"),
        ("best_score", f"SELECT id, score_global, start_ts FROM trips {w} AND score_global IS NOT NULL ORDER BY score_global DESC LIMIT 1"),
        ("best_reku", f"SELECT id, ROUND(hdc_charge_dist*100.0/hdc_ev_distance,1), start_ts FROM trips {w} AND hdc_ev_distance>0 ORDER BY hdc_charge_dist*1.0/hdc_ev_distance DESC LIMIT 1"),
        ("top_speed", f"SELECT id, max_speed, start_ts FROM trips {w} ORDER BY max_speed DESC LIMIT 1"),
    ]:
        r = conn.execute(sql, p).fetchone()
        if r:
            records[label] = {"id": r[0], "value": r[1], "date": r[2]}

    # Most km in a day
    best_day = conn.execute(f"""
        SELECT SUBSTR(start_ts,1,10) as day, ROUND(SUM(length_m)/1000.0,1) as km, COUNT(*) as trips
        FROM trips {w} GROUP BY day ORDER BY km DESC LIMIT 1
    """, p).fetchone()

    conn.close()

    days = max(1, round(((__import__('datetime').datetime.fromisoformat(ov[7].replace('Z','')) - __import__('datetime').datetime.fromisoformat(ov[6].replace('Z',''))).days))  if ov[6] and ov[7] else 1)

    return {
        "total_trips": total_trips,
        "total_km": round(total_m / 1000, 1),
        "total_hours": round(total_s / 3600, 1),
        "avg_speed": round(avg_spd, 1) if avg_spd else 0,
        "max_speed": max_spd,
        "avg_score": round(ov[5], 1) if ov[5] else 0,
        "avg_score_accel": round(ov[15], 1) if ov[15] else 0,
        "avg_score_braking": round(ov[16], 1) if ov[16] else 0,
        "avg_score_consistency": round(ov[17], 1) if ov[17] else 0,
        "first_trip": ov[6],
        "last_trip": ov[7],
        "days_span": days,
        "reku_pct": round(ov[8] / ev_d * 100, 1) if ev_d else 0,
        "eco_pct": round(ov[10] / ev_d * 100, 1) if ev_d else 0,
        "power_pct": round(ov[11] / ev_d * 100, 1) if ev_d else 0,
        "night_trips": ov[18],
        "night_pct": round(ov[18] / total_trips * 100, 1) if total_trips else 0,
        "overspeed_km": round((ov[19] or 0) / 1000, 1),
        "idle_hours": round((ov[12] or 0) / 3600, 1),
        "avg_trip_km": round(total_m / 1000 / total_trips, 1),
        "avg_trip_min": round(total_s / 60 / total_trips, 0),
        "trips_per_day": round(total_trips / days, 1),
        "km_per_day": round(total_m / 1000 / days, 1),
        "monthly": [{"month": r[0], "trips": r[1], "km": r[2], "speed": r[3], "score": r[4], "reku": r[5], "eco": r[6], "power": r[7]} for r in monthly],
        "weekday": [{"day": r[0], "trips": r[1], "km": r[2]} for r in weekday],
        "hourly": [{"hour": r[0], "trips": r[1], "km": r[2]} for r in hourly],
        "speed_cats": {
            "city_trips": speed_cats[0] or 0, "rural_trips": speed_cats[1] or 0, "highway_trips": speed_cats[2] or 0,
            "city_km": round((speed_cats[3] or 0) / 1000), "rural_km": round((speed_cats[4] or 0) / 1000), "highway_km": round((speed_cats[5] or 0) / 1000),
        },
        "score_dist": [{"bucket": f"{r[0]}-{r[0]+9}", "count": r[1]} for r in score_dist],
        "records": records,
        "best_day": {"date": best_day[0], "km": best_day[1], "trips": best_day[2]} if best_day else None,
        "est_avg_kwh_100km": round(estimate_kwh_100km(avg_spd or 50, ov[8]/ev_d*100 if ev_d else 20, ov[11]/ev_d*100 if ev_d else 20), 1) if avg_spd else None,
    }


def get_trip_count() -> int:
    conn = _get_db()
    count = conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    conn.close()
    return count


def get_trips_from_db(
    limit: int = 50,
    offset: int = 0,
    from_date: str | None = None,
    to_date: str | None = None,
    vin: str | None = None,
) -> list[dict]:
    conn = _get_db()
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM trips WHERE 1=1"
    params = []
    if vin:
        sql += " AND vin = ?"
        params.append(vin)
    if from_date:
        sql += " AND start_ts >= ?"
        params.append(from_date)
    if to_date:
        sql += " AND start_ts <= ?"
        params.append(to_date + "T23:59:59Z")
    sql += " ORDER BY start_ts DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        ev_d = d.get("hdc_ev_distance") or 0
        if ev_d > 0 and d.get("avg_speed"):
            reku_pct = (d.get("hdc_charge_dist") or 0) / ev_d * 100
            power_pct = (d.get("hdc_power_dist") or 0) / ev_d * 100
            d["est_kwh_100km"] = round(estimate_kwh_100km(d["avg_speed"], reku_pct, power_pct), 1)
        else:
            d["est_kwh_100km"] = None
        result.append(d)
    return result


def get_stats() -> dict:
    conn = _get_db()
    row = conn.execute("""
        SELECT
            COUNT(*) as total_trips,
            SUM(length_m) as total_distance_m,
            SUM(duration_s) as total_duration_s,
            AVG(avg_speed) as avg_speed,
            MAX(max_speed) as max_speed,
            AVG(score_global) as avg_score,
            MIN(start_ts) as first_trip,
            MAX(start_ts) as last_trip,
            SUM(hdc_charge_dist) as total_reku_m,
            SUM(hdc_ev_distance) as total_ev_m,
            SUM(hdc_eco_dist) as total_eco_m,
            SUM(hdc_power_dist) as total_power_m
        FROM trips
    """).fetchone()
    conn.close()
    if not row or not row[0]:
        return {"total_trips": 0}
    return {
        "total_trips": row[0],
        "total_km": round(row[1] / 1000, 1) if row[1] else 0,
        "total_hours": round(row[2] / 3600, 1) if row[2] else 0,
        "avg_speed": round(row[3], 1) if row[3] else 0,
        "max_speed": row[4],
        "avg_score": round(row[5], 1) if row[5] else 0,
        "first_trip": row[6],
        "last_trip": row[7],
        "reku_pct": round(row[8] / row[9] * 100, 1) if row[9] else 0,
        "eco_pct": round(row[10] / row[9] * 100, 1) if row[9] else 0,
        "power_pct": round(row[11] / row[9] * 100, 1) if row[9] else 0,
        "est_avg_kwh_100km": round(estimate_kwh_100km(
            row[3] or 50,
            (row[8] / row[9] * 100) if row[9] else 20,
            (row[11] / row[9] * 100) if row[9] else 20,
        ), 1) if row[3] else None,
    }
