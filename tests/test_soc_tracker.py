"""Tests for soc_tracker module."""

from toybaru.soc_tracker import log_snapshot, get_consumption_estimate, get_snapshot_history


def test_log_snapshot():
    log_snapshot(vin="TEST", soc=80, range_km=250.0, odometer=10000.0)
    history = get_snapshot_history()
    assert len(history) == 1
    assert history[0]["soc"] == 80


def test_log_snapshot_dedup():
    log_snapshot(vin="TEST", soc=80, range_km=250.0, odometer=10000.0)
    log_snapshot(vin="TEST", soc=80, range_km=250.0, odometer=10000.0)
    assert len(get_snapshot_history()) == 1


def test_log_snapshot_different_soc():
    log_snapshot(vin="TEST", soc=80, range_km=250.0, odometer=10000.0)
    log_snapshot(vin="TEST", soc=75, range_km=230.0, odometer=10000.0)
    assert len(get_snapshot_history()) == 2


def test_log_snapshot_different_odo():
    log_snapshot(vin="TEST", soc=80, range_km=250.0, odometer=10000.0)
    log_snapshot(vin="TEST", soc=80, range_km=250.0, odometer=10050.0)
    assert len(get_snapshot_history()) == 2


def test_log_snapshot_none_soc():
    log_snapshot(vin="TEST", soc=None, range_km=250.0, odometer=10000.0)
    assert len(get_snapshot_history()) == 0


def test_consumption_estimate_no_data():
    result = get_consumption_estimate()
    assert result["kwh_per_100km"] is None
    assert result["entries"] == 0


def test_consumption_estimate():
    # Simulate a drive: 80% -> 70% over 50km (odometer 10000 -> 10050)
    log_snapshot(vin="TEST", soc=80, range_km=260.0, odometer=10000.0)
    log_snapshot(vin="TEST", soc=70, range_km=220.0, odometer=10050.0)
    result = get_consumption_estimate()
    assert result["segments"] == 1
    assert result["total_km"] == 50.0
    # 10% of 71.4 kWh = 7.14 kWh / 50 km * 100 = 14.28 kWh/100km
    assert 14 <= result["kwh_per_100km"] <= 15


def test_snapshot_history_order():
    log_snapshot(vin="TEST", soc=90, range_km=300.0, odometer=9000.0)
    log_snapshot(vin="TEST", soc=80, range_km=260.0, odometer=9100.0)
    log_snapshot(vin="TEST", soc=70, range_km=220.0, odometer=9200.0)
    history = get_snapshot_history()
    assert len(history) == 3
    # Chronological order (oldest first)
    assert history[0]["soc"] == 90
    assert history[-1]["soc"] == 70


def test_snapshot_history_limit():
    for s in range(100, 90, -1):
        log_snapshot(vin="TEST", soc=s, range_km=float(s * 3), odometer=float(10000 + (100 - s) * 50))
    history = get_snapshot_history(limit=3)
    assert len(history) == 3
