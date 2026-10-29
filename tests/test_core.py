import os, tempfile, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
_tdb = os.path.join(tempfile.gettempdir(), 'procureyard_test.db').replace('\\', '/')
os.environ.setdefault('DATABASE_URL', f'sqlite:///{_tdb}')
os.environ.setdefault('PAYSWIFT_BASE_URL', 'http://127.0.0.1:9999')
import app

def test_fare_rounding_and_surge():
    t={'distance_km':'9.0','surge_multiplier':'1.5'}
    assert app.fare(t)==101
    assert app.round_rupee(64.5)==65

def test_rider_id_normalization_for_messy_export():
    assert app.norm_rider('R7')=='R007'
    assert app.expected_trip_for('R007','T840677')['rider_id']=='R7'

def test_trip_payout_is_based_on_provider_export_line():
    t=app.expected_trip_for('R003','T926334')
    assert t is not None
    assert app.fare(t)-app.actual_trip_paid(t)==25

def test_implausible_distance_not_used_as_normal_fare():
    t=app.expected_trip_for('R031','T312538')
    assert float(t['distance_km'])>250

def test_policy_window_uses_received_at():
    state={}
    assert app.date_from_text('19 sept ke orders','2026-09-22T10:00:00+05:30',state).isoformat()=='2026-09-19'
