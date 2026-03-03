#!/usr/bin/env python3

import sys
import io
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import argparse

# ── Force UTF-8 stdout on Windows (cp1252 can't encode box-drawing chars).
# sys.stdout.reconfigure() requires Python 3.7+ and a real TextIOWrapper.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                   encoding='utf-8', errors='replace')

# ─────────────────────────────────────────────────────────────────────────────
#  AIRCRAFT CONFIGURATION
#  V3 ADDITION: Hysteresis thresholds appended to every config block.
#               Enter threshold is STRICTER than exit threshold.
#               The gap between them is the hysteresis dead-band.
# ─────────────────────────────────────────────────────────────────────────────

AIRCRAFT_CONFIGS: Dict[str, Dict] = {
    "Cessna 208 Caravan": {
        # ── V2: Rotation / climb (unchanged) ──────────────────────────────
        "rotation_ias"          : 58.0,
        "climb_torque_min"      : 1200.0,
        "climb_rate_threshold"  : 400.0,    # static fallback; adaptive overrides
        # ── V2: Ground ops ────────────────────────────────────────────────
        "taxi_speed_threshold"  : 6.0,
        "definitely_airborne_ias": 55.0,
        "liftoff_agl"           : 30.0,     # static fallback
        # ── V2: Landing ───────────────────────────────────────────────────
        "flare_agl"             : 50.0,
        "touchdown_agl"         : 15.0,
        # ── V2: Engine / power ────────────────────────────────────────────
        "idle_ng_max"           : 68.0,
        "idle_fflow_max"        : 80.0,
        "takeoff_torque_min"    : 1100.0,
        # ── V2: Cruise band ───────────────────────────────────────────────
        "cruise_fflow_min"      : 120.0,
        "cruise_fflow_max"      : 350.0,
        "steep_turn_bank"       : 45.0,
        "hard_landing_g"        : 1.8,
        "high_wind_landing_kts" : 15.0,
        "cruise_agl_min"        : 1000.0,   # static fallback
        # ── V3: Hysteresis – CLIMB ────────────────────────────────────────
        "climb_rate_enter"      : 450.0,
        "climb_rate_exit"       : 300.0,
        # ── V3: Hysteresis – DESCENT ─────────────────────────────────────
        "descent_rate_enter"    : 450.0,
        "descent_rate_exit"     : 250.0,
        # ── V3: Hysteresis – AIRBORNE ────────────────────────────────────
        "liftoff_agl_enter"     : 40.0,
        "liftoff_agl_exit"      : 20.0,
        # ── Event detection thresholds ────────────────────────────────────
        # Verify ITT limits against aircraft AMM before deploying.
        "vmo_kias"              : 175.0,    # max operating speed (KIAS)
        "vref_approach"         : 82.0,     # approach speed proxy (med weight)
        "hard_landing_g_critical": 2.1,     # above this → S3 hard landing
        "low_airspeed_warn"     : 78.0,     # KIAS – S2 low airspeed (≈ Vs1 + margin)
        "low_airspeed_critical" : 68.0,     # KIAS – S3 low airspeed
        "itt_warn"              : 740.0,    # °C – above max continuous (PT6A-114A)
        "itt_limit"             : 800.0,    # °C – approaching takeoff limit
        "rapid_power_warn"      : 200.0,    # ft·lb/s torque rate – S1
        "rapid_power_critical"  : 400.0,    # ft·lb/s torque rate – S2
    },
    "Cessna 208B Grand Caravan": {
        "rotation_ias"          : 60.0,
        "climb_torque_min"      : 1200.0,
        "climb_rate_threshold"  : 400.0,
        "taxi_speed_threshold"  : 6.0,
        "definitely_airborne_ias": 57.0,
        "liftoff_agl"           : 30.0,
        "flare_agl"             : 50.0,
        "touchdown_agl"         : 15.0,
        "idle_ng_max"           : 68.0,
        "idle_fflow_max"        : 85.0,
        "takeoff_torque_min"    : 1100.0,
        "cruise_fflow_min"      : 130.0,
        "cruise_fflow_max"      : 380.0,
        "steep_turn_bank"       : 45.0,
        "hard_landing_g"        : 1.8,
        "high_wind_landing_kts" : 15.0,
        "cruise_agl_min"        : 1000.0,
        "climb_rate_enter"      : 450.0,
        "climb_rate_exit"       : 300.0,
        "descent_rate_enter"    : 450.0,
        "descent_rate_exit"     : 250.0,
        "liftoff_agl_enter"     : 40.0,
        "liftoff_agl_exit"      : 20.0,
        "vmo_kias"              : 175.0,
        "vref_approach"         : 85.0,
        "hard_landing_g_critical": 2.1,
        "low_airspeed_warn"     : 78.0,
        "low_airspeed_critical" : 68.0,
        "itt_warn"              : 740.0,
        "itt_limit"             : 800.0,
        "rapid_power_warn"      : 200.0,
        "rapid_power_critical"  : 400.0,
    },
    "Cessna 208B Grand Caravan EX": {
        "rotation_ias"          : 60.0,
        "climb_torque_min"      : 1300.0,
        "climb_rate_threshold"  : 400.0,
        "taxi_speed_threshold"  : 6.0,
        "definitely_airborne_ias": 57.0,
        "liftoff_agl"           : 30.0,
        "flare_agl"             : 50.0,
        "touchdown_agl"         : 15.0,
        "idle_ng_max"           : 68.0,
        "idle_fflow_max"        : 90.0,
        "takeoff_torque_min"    : 1200.0,
        "cruise_fflow_min"      : 140.0,
        "cruise_fflow_max"      : 400.0,
        "steep_turn_bank"       : 45.0,
        "hard_landing_g"        : 1.8,
        "high_wind_landing_kts" : 15.0,
        "cruise_agl_min"        : 1000.0,
        "climb_rate_enter"      : 500.0,
        "climb_rate_exit"       : 320.0,
        "descent_rate_enter"    : 500.0,
        "descent_rate_exit"     : 280.0,
        "liftoff_agl_enter"     : 40.0,
        "liftoff_agl_exit"      : 20.0,
        "vmo_kias"              : 175.0,
        "vref_approach"         : 88.0,
        "hard_landing_g_critical": 2.1,
        "low_airspeed_warn"     : 80.0,
        "low_airspeed_critical" : 70.0,
        "itt_warn"              : 750.0,    # PT6A-140A — verify against AMM
        "itt_limit"             : 810.0,
        "rapid_power_warn"      : 200.0,
        "rapid_power_critical"  : 400.0,
    },
    "Generic": {
        "rotation_ias"          : 60.0,
        "climb_torque_min"      : 1000.0,
        "climb_rate_threshold"  : 300.0,
        "taxi_speed_threshold"  : 5.0,
        "definitely_airborne_ias": 50.0,
        "liftoff_agl"           : 30.0,
        "flare_agl"             : 50.0,
        "touchdown_agl"         : 15.0,
        "idle_ng_max"           : 68.0,
        "idle_fflow_max"        : 80.0,
        "takeoff_torque_min"    : 900.0,
        "cruise_fflow_min"      : 100.0,
        "cruise_fflow_max"      : 350.0,
        "steep_turn_bank"       : 45.0,
        "hard_landing_g"        : 1.8,
        "high_wind_landing_kts" : 15.0,
        "cruise_agl_min"        : 1000.0,
        "climb_rate_enter"      : 380.0,
        "climb_rate_exit"       : 220.0,
        "descent_rate_enter"    : 380.0,
        "descent_rate_exit"     : 200.0,
        "liftoff_agl_enter"     : 35.0,
        "liftoff_agl_exit"      : 15.0,
        "vmo_kias"              : 175.0,
        "vref_approach"         : 85.0,
        "hard_landing_g_critical": 2.1,
        "low_airspeed_warn"     : 75.0,
        "low_airspeed_critical" : 65.0,
        "itt_warn"              : 740.0,
        "itt_limit"             : 800.0,
        "rapid_power_warn"      : 200.0,
        "rapid_power_critical"  : 400.0,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
#  FLIGHT EVENT DEFINITIONS
#
#  Severity levels
#  ---------------
#  S1  Notice    – informational; review if it recurs as a pattern.
#  S2  Warning   – SOP deviation or operational risk; investigate.
#  S3  Critical  – airworthiness concern or imminent safety risk; mandatory
#                  report and engineering review before next flight.
#
#  Event names are stored in the FLIGHT_EVENT column with a severity suffix,
#  e.g. HARD_LANDING_S3, HIGH_DESCENT_RATE_S2.
#  Multiple events on the same row are pipe-separated: A_S2|B_S1.
#
#  Fields per severity tier
#  ------------------------
#  min_duration  Consecutive 1-Hz rows the condition must hold before the
#                event is confirmed (filters sensor spikes).
#  description   Human-readable text for reports and dashboard tooltips.
#
#  NOTE: ITT limits must be verified against the aircraft AMM before
#  deploying in a production environment.
# ─────────────────────────────────────────────────────────────────────────────

FLIGHT_EVENT_DEFINITIONS: Dict[str, Dict] = {

    # ── Landing impact ────────────────────────────────────────────────────────
    'HARD_LANDING': {
        'S2': {'min_duration': 2,
               'description': 'Firm landing 1.8–2.1 g — log and monitor for structural trend'},
        'S3': {'min_duration': 2,
               'description': 'Hard landing > 2.1 g — maintenance inspection required before next flight'},
    },

    # ── Approach quality ──────────────────────────────────────────────────────
    'HIGH_DESCENT_RATE': {
        'S1': {'min_duration': 3,
               'description': 'Descent rate > 1000 fpm below 1000 AGL — review energy management'},
        'S2': {'min_duration': 3,
               'description': 'Descent rate > 1500 fpm below 500 AGL — unstabilised approach criterion'},
        'S3': {'min_duration': 2,
               'description': 'Descent rate > 2000 fpm below 500 AGL — CFIT risk, immediate correction required'},
    },

    'HIGH_APPROACH_SPEED': {
        'S1': {'min_duration': 5,
               'description': 'IAS > Vref+20 on approach below 500 AGL — float / overrun risk'},
        'S2': {'min_duration': 5,
               'description': 'IAS > Vref+35 on approach — significant runway excursion risk'},
    },

    'LOW_APPROACH_SPEED': {
        'S2': {'min_duration': 3,
               'description': 'IAS < Vref−10 on approach — stall margin reduced, go-around recommended'},
    },

    'UNSTABLE_APPROACH': {
        'S2': {'min_duration': 5,
               'description': 'Multi-parameter instability on approach (speed + VS + bank + power)'},
    },

    # ── Power management ──────────────────────────────────────────────────────
    'RAPID_POWER': {
        'S1': {'min_duration': 1,
               'description': 'Torque rate > 200 ft·lb/s — abrupt power application, compressor wear'},
        'S2': {'min_duration': 1,
               'description': 'Torque rate > 400 ft·lb/s — aggressive advance, compressor stall risk'},
    },

    # ── Airspeed deviations ───────────────────────────────────────────────────
    'OVERSPEED': {
        'S2': {'min_duration': 3,
               'description': 'IAS exceeds Vmo (175 KIAS) — structural load concern'},
        'S3': {'min_duration': 3,
               'description': 'IAS > Vmo+10 KIAS — approaching structural limit, mandatory log'},
    },

    'LOW_AIRSPEED': {
        'S2': {'min_duration': 3,
               'description': 'IAS below minimum airborne reference — reduced stall margin'},
        'S3': {'min_duration': 2,
               'description': 'IAS critically low airborne — imminent stall / LOC-I risk'},
    },

    # ── Attitude / maneuvering ────────────────────────────────────────────────
    'STEEP_BANK': {
        'S1': {'min_duration': 3,
               'description': 'Bank > 45° above 1000 AGL — outside normal ops, check airmanship'},
        'S2': {'min_duration': 3,
               'description': 'Bank > 30° below 1000 AGL — exceeds operational limit near terrain'},
        'S3': {'min_duration': 2,
               'description': 'Bank > 45° below 500 AGL — LOC-I risk, immediate correction required'},
    },

    'NEGATIVE_G': {
        'S1': {'min_duration': 1,
               'description': 'Brief negative G load — monitor for recurrence'},
        'S2': {'min_duration': 3,
               'description': 'Sustained negative G — fuel and oil system interruption risk'},
    },

    'TAIL_STRIKE_RISK': {
        'S2': {'min_duration': 2,
               'description': 'Pitch > 15° at low airspeed near ground — tail strike geometry'},
    },

    # ── Engine / systems ──────────────────────────────────────────────────────
    'HIGH_ITT': {
        'S2': {'min_duration': 5,
               'description': 'ITT above max continuous limit — accelerated hot-section wear'},
        'S3': {'min_duration': 3,
               'description': 'ITT at / above takeoff limit in cruise — mandatory engine inspection'},
    },

    # ── Procedural — informational ────────────────────────────────────────────
    'GO_AROUND': {
        'S1': {'min_duration': 3,
               'description': 'Go-around executed — review approach conditions'},
    },

    'REJECTED_TAKEOFF': {
        'S2': {'min_duration': 3,
               'description': 'High-speed rejected takeoff — brake and structural inspection required'},
    },

    'ENGINE_IDLE_DESCENT': {
        'S1': {'min_duration': 30,
               'description': 'Extended idle-power descent (> 30 s) — monitor turbine cooling'},
    },

    'HIGH_WIND_LANDING': {
        'S1': {'min_duration': 1,
               'description': 'Crosswind component above limit on approach — condition flag'},
    },

    'UNSTABLE_DEPARTURE': {
        'S1': {'min_duration': 5,
               'description': 'Speed / bank / VS instability on departure — review SOP compliance'},
    },

    'UNSTABLE_CIRCUIT': {
        'S1': {'min_duration': 4,
               'description': 'Circuit / pattern instability — review traffic pattern technique'},
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  STATE-MACHINE TRANSITION TABLE  (unchanged from v2)
# ─────────────────────────────────────────────────────────────────────────────

VALID_TRANSITIONS: Dict[str, List[str]] = {
    "GROUND"           : ["GROUND", "TAXI", "TAKEOFF ROLL"],
    "TAXI"             : ["TAXI", "GROUND", "TAKEOFF ROLL"],
    "TAKEOFF ROLL"     : ["TAKEOFF ROLL", "ROTATION", "INITIAL CLIMB",
                          "GROUND", "ROLLOUT"],
    "ROTATION"         : ["ROTATION", "INITIAL CLIMB", "TAKEOFF ROLL", "GROUND"],
    "INITIAL CLIMB"    : ["INITIAL CLIMB", "CLIMB", "CLIMBING FLIGHT",
                          "LEVEL FLIGHT", "GO-AROUND"],
    "CLIMB"            : ["CLIMB", "CLIMBING FLIGHT", "CRUISE", "LEVEL FLIGHT"],
    "CLIMBING FLIGHT"  : ["CLIMBING FLIGHT", "CLIMB", "CRUISE",
                          "LEVEL FLIGHT", "DESCENDING FLIGHT"],
    "CRUISE"           : ["CRUISE", "LEVEL FLIGHT", "CLIMBING FLIGHT",
                          "DESCENDING FLIGHT", "DESCENT", "MANEUVERING"],
    "LEVEL FLIGHT"     : ["LEVEL FLIGHT", "CRUISE", "CLIMBING FLIGHT",
                          "DESCENDING FLIGHT", "MANEUVERING"],
    "DESCENDING FLIGHT": ["DESCENDING FLIGHT", "DESCENT", "LEVEL FLIGHT",
                          "APPROACH", "CRUISE"],
    "DESCENT"          : ["DESCENT", "DESCENDING FLIGHT", "APPROACH", "LEVEL FLIGHT"],
    "APPROACH"         : ["APPROACH", "FLARE", "TOUCHDOWN",
                          "GO-AROUND", "LEVEL FLIGHT", "CLIMBING FLIGHT"],
    "FLARE"            : ["FLARE", "TOUCHDOWN", "ROLLOUT",
                          "GO-AROUND", "CLIMBING FLIGHT"],
    "TOUCHDOWN"        : ["TOUCHDOWN", "ROLLOUT", "GROUND"],
    "ROLLOUT"          : ["ROLLOUT", "TAXI", "GROUND"],
    "MANEUVERING"      : ["MANEUVERING", "LEVEL FLIGHT", "CLIMBING FLIGHT",
                          "DESCENDING FLIGHT", "CRUISE"],
    "GO-AROUND"        : ["GO-AROUND", "CLIMBING FLIGHT", "INITIAL CLIMB",
                          "LEVEL FLIGHT"],
}

# ─────────────────────────────────────────────────────────────────────────────
#  HELPER: SAFE NUMERIC CONVERSION  (unchanged from v2)
# ─────────────────────────────────────────────────────────────────────────────

def safe_num(series: pd.Series, fill: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors='coerce').fillna(fill)


# ─────────────────────────────────────────────────────────────────────────────
#  V3 UTILITY: TEMPORAL PERSISTENCE FILTER
# ─────────────────────────────────────────────────────────────────────────────

def require_persistence(mask: pd.Series, min_duration: int) -> pd.Series:
    """
    Return a boolean Series where True is only set where the condition in
    `mask` has been continuously True for at least `min_duration` rows.

    Implementation operates entirely on numpy arrays so it is immune to
    duplicate, non-contiguous, or non-monotonic pandas index labels —
    the root cause of the "cannot reindex on an axis with duplicate labels"
    error seen with G1000 CSVs that contain duplicate Lcl Time entries.

    The original index is preserved on the returned Series.
    """
    if min_duration <= 1:
        return mask.copy()

    original_index = mask.index
    arr = mask.to_numpy(dtype=bool)
    n   = len(arr)

    if n == 0:
        return mask.copy()

    # ── Step 1: build run-length confirmed array using numpy only ────────────
    # For each position i, compute how many consecutive True values end at i.
    # If that count >= min_duration, the end of a qualifying run is confirmed.
    run_len = np.zeros(n, dtype=int)
    for i in range(n):
        if arr[i]:
            run_len[i] = run_len[i - 1] + 1 if i > 0 else 1
        else:
            run_len[i] = 0

    confirmed_end = run_len >= min_duration   # bool array

    # ── Step 2: back-propagate the confirmed end flag to the run start ───────
    # For every confirmed end position, mark the preceding (min_duration-1)
    # positions True as well, so the entire qualifying run is labelled.
    confirmed = np.zeros(n, dtype=bool)
    for i in range(n):
        if confirmed_end[i]:
            start = max(0, i - min_duration + 1)
            confirmed[start : i + 1] = True

    return pd.Series(confirmed, index=original_index)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────

class FOQAFlightClassifier:

    SMOOTHING_MIN_DURATION = 4

    # Minimum data rows needed to compute adaptive thresholds.
    # Below this, static config values are used as-is.
    ADAPTIVE_MIN_ROWS = 100

    def __init__(self, aircraft_type: str = "Generic", debug_mode: bool = False):
        self.cfg          = AIRCRAFT_CONFIGS.get(aircraft_type, AIRCRAFT_CONFIGS["Generic"])
        self.aircraft_type = aircraft_type
        self.debug_mode   = debug_mode

        # V3: Adaptive thresholds — populated by compute_adaptive_thresholds()
        # before the classification loop. Initialised to static config values
        # so _classify_row() can read them unconditionally via self._dyn.
        self._dyn: Dict[str, float] = {
            'climb_rate'   : self.cfg['climb_rate_threshold'],
            'descent_rate' : self.cfg['climb_rate_threshold'],   # same default
            'cruise_agl'   : self.cfg['cruise_agl_min'],
        }
        self._normac_offset: float = 1.0   # updated by compute_derived()

    # ── 1. DERIVED PARAMETERS  (v2 logic preserved; Energy_State_deriv added)

    def compute_derived(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        window = 5   # 1-Hz data assumption

        # ── NormAc format detection ───────────────────────────────────────────
        # G1000 NormAc can be recorded in two formats:
        #   Absolute : 1.0 = 1G (standard straight-and-level)
        #   Delta    : 0.0 = 1G (deviation from 1G — records delta only)
        # Detection: sample NormAc on ground rows (GndSpd < 20 kts) where
        # physics dictates exactly 1G. Absolute median ≈ 1.0, delta ≈ 0.0.
        try:
            ground_rows   = df[pd.to_numeric(df['GndSpd'], errors='coerce') < 20]['NormAc']
            ground_median = float(pd.to_numeric(ground_rows, errors='coerce').dropna().median())
        except Exception:
            ground_median = 1.0

        if abs(ground_median - 1.0) < 0.25:
            self._normac_offset = 1.0   # absolute format (1G = 1.0)
        elif abs(ground_median) < 0.25:
            self._normac_offset = 0.0   # delta format    (1G = 0.0)
        else:
            self._normac_offset = ground_median   # unexpected — use actual ground median

        if self.debug_mode:
            fmt = 'ABSOLUTE' if self._normac_offset > 0.5 else 'DELTA'
            print(f"  [NormAc] Format: {fmt} "
                  f"(ground median={ground_median:.3f}, offset={self._normac_offset:.1f})")

        def deriv(col):
            return df[col].diff().rolling(window=window, center=True,
                                          min_periods=1).mean()

        # ── V2: All derivatives (unchanged)
        df['IAS_deriv']      = deriv('IAS')
        df['VSpd_deriv']     = deriv('VSpd')
        df['GndSpd_deriv']   = deriv('GndSpd')
        df['Alt_deriv']      = deriv('AltGPS')
        df['Torq_deriv']     = deriv('E1 Torq')

        # ── V2: Stability measures (unchanged)
        df['Alt_stability']  = df['AltGPS'].rolling(window=20, center=True,
                                                      min_periods=5).std().fillna(999)
        df['VSpd_stability'] = df['VSpd'].rolling(window=10, center=True,
                                                    min_periods=3).std().fillna(999)

        # ── V2: Density-altitude proxy (unchanged)
        df['TAS_IAS_diff']  = df['TAS'] - df['IAS']

        # ── V2: Crab angle (unchanged)
        raw_diff = df['HDG'] - df['TRK']
        df['Hdg_Trk_diff']  = ((raw_diff + 180) % 360) - 180

        # ── V2: Wind components (unchanged)
        rel_wind            = np.radians(df['WndDr'] - df['HDG'])
        df['CrosswindComp'] = (df['WndSpd'] * np.sin(rel_wind)).abs()
        df['HeadwindComp']  =  df['WndSpd'] * np.cos(rel_wind)

        # ── V2: Energy state (unchanged formula)
        max_torque  = self.cfg['climb_torque_min'] * 1.2
        max_ias     = 175.0
        max_vspd    = 1500.0
        E_torque    = np.clip(df['E1 Torq'] / max_torque, 0, 1)
        E_ias       = np.clip(df['IAS']     / max_ias,    0, 1)
        E_vspd      = np.clip(df['VSpd']    / max_vspd,  -1, 1)
        df['Energy_State'] = (0.5 * E_torque + 0.3 * E_ias + 0.2 * E_vspd).clip(0, 1)

        # ── V3: Energy state derivative  (rate of energy change)
        # Smoothed over 5 rows to suppress sensor noise.
        # Positive = energy building. Negative = energy dissipating.
        df['Energy_State_deriv'] = df['Energy_State'].diff().rolling(
            window=window, center=True, min_periods=1).mean()

        # ── V2: Landing impact (unchanged)
        df['NormAc_peak'] = df['NormAc'].rolling(window=3, center=True,
                                                   min_periods=1).max()
        # ── V2: Lateral acceleration (unchanged)
        df['LatAc_abs']   = df['LatAc'].abs()

        gpsFix_col  = pd.to_numeric(df['GPSfix'], errors='coerce').fillna(0)
        hal_col     = pd.to_numeric(df['HAL'],    errors='coerce').fillna(0)
        val_col     = pd.to_numeric(df['VAL'],    errors='coerce').fillna(0)

        gpsFix_real = bool(gpsFix_col.max() >= 1)
        hal_real    = bool(hal_col.max()    >  0.001)
        val_real    = bool(val_col.max()    >  0.1)

        gps_quality_mask = pd.Series(True, index=df.index)
        if gpsFix_real:
            gps_quality_mask &= (gpsFix_col >= 3)
        if hal_real:
            gps_quality_mask &= (hal_col < 0.3)
        if val_real:
            gps_quality_mask &= (val_col < 150)

        df['GPS_quality'] = gps_quality_mask.astype(int)

        # ── V2: Engine state flags (unchanged)
        df['fflow_idle']  = (df['E1 FFlow'] < self.cfg['idle_fflow_max']).astype(int)
        df['ng_high']     = (df['E1 NG']    > self.cfg['idle_ng_max']).astype(int)

        return df

    # ── 2. AGL COMPUTATION  (V3: true gradient replaces flat step model)

    def compute_agl(self, df: pd.DataFrame) -> pd.DataFrame:
        def get_ground_elev(subset: pd.DataFrame, alt_col: str) -> float:
            speeds = pd.to_numeric(subset['GndSpd'], errors='coerce')
            slow   = subset[speeds < 40]
            vals   = pd.to_numeric(slow[alt_col] if len(slow) >= 5
                                   else subset[alt_col], errors='coerce').dropna()
            if len(vals) < 3:
                return np.nan
            return float(vals.nsmallest(min(10, len(vals))).median())

        alt_col = None
        for col in ['AltGPS', 'AltB', 'AltMSL']:
            if col in df.columns and not df[col].isnull().all():
                alt_col = col
                break
        if alt_col is None:
            df['AGL'] = 0.0
            return df

        valid_alts = pd.to_numeric(df[alt_col], errors='coerce')
        n_rows     = len(df)
        sample_n   = min(180, n_rows)

        dep_elev   = get_ground_elev(df.iloc[:sample_n], alt_col)
        dest_elev  = get_ground_elev(df.iloc[-sample_n:], alt_col)

        # Fallback chain (identical to v2)
        if pd.isna(dep_elev) and not pd.isna(dest_elev): dep_elev  = dest_elev
        if pd.isna(dest_elev) and not pd.isna(dep_elev): dest_elev = dep_elev
        if pd.isna(dep_elev):
            p2 = float(np.nanpercentile(valid_alts.dropna(), 2)) \
                 if valid_alts.notna().any() else 0.0
            dep_elev = dest_elev = p2

        # ── V3: Distance-weighted gradient (optional, activates if GndSpd usable)
        # Estimate cumulative distance by integrating GndSpd (kts → nm per second).
        # Normalise 0→1 and use as the interpolation parameter instead of row count.
        # Fallback: row-count linear interpolation (equivalent to V2 but continuous).
        try:
            gndspd_kts = pd.to_numeric(df['GndSpd'], errors='coerce').fillna(0.0)
            # nm per row (1-Hz assumption: 1 sec per row, 1 kt = 1 nm/hr)
            dist_per_row   = gndspd_kts / 3600.0
            cum_dist       = dist_per_row.cumsum()
            total_dist     = float(cum_dist.iloc[-1])
            if total_dist > 0.5:   # at least 0.5 nm flown — use distance weight
                t = (cum_dist / total_dist).clip(0, 1).to_numpy()
            else:
                t = np.linspace(0.0, 1.0, n_rows)
        except Exception:
            t = np.linspace(0.0, 1.0, n_rows)

        # Ground reference interpolates from dep_elev to dest_elev
        ground_ref = pd.Series(dep_elev + t * (dest_elev - dep_elev),
                                index=df.index)

        df['AGL'] = (valid_alts - ground_ref).fillna(0).clip(lower=-50)

        # On-ground clamp: identical to v2
        on_ground_mask = (df['GndSpd'] < 40) & (df['AGL'] < 0)
        df.loc[on_ground_mask, 'AGL'] = 0.0

        return df

    # ── V3 NEW: ADAPTIVE THRESHOLD COMPUTATION ───────────────────────────────

    def compute_adaptive_thresholds(self, df: pd.DataFrame) -> None:
        MIN_ROWS = self.ADAPTIVE_MIN_ROWS

        # ── Climb rate: 75th pct of upward VSpd
        climb_samples = df.loc[df['VSpd'] > 0, 'VSpd']
        if len(climb_samples) >= MIN_ROWS:
            climb_dyn = float(np.percentile(climb_samples, 75))
            # Guard: adaptive value must be within ±50% of static threshold
            climb_dyn = np.clip(climb_dyn,
                                self.cfg['climb_rate_threshold'] * 0.5,
                                self.cfg['climb_rate_threshold'] * 1.5)
        else:
            climb_dyn = self.cfg['climb_rate_threshold']

        # ── Descent rate: 75th pct of downward VSpd magnitude
        desc_samples = df.loc[df['VSpd'] < 0, 'VSpd'].abs()
        if len(desc_samples) >= MIN_ROWS:
            desc_dyn = float(np.percentile(desc_samples, 75))
            desc_dyn = np.clip(desc_dyn,
                               self.cfg['climb_rate_threshold'] * 0.5,
                               self.cfg['climb_rate_threshold'] * 1.5)
        else:
            desc_dyn = self.cfg['climb_rate_threshold']

        # ── Cruise AGL: 80th percentile of LEVEL flight AGL
        #
        # Using 60th pct of all airborne rows was wrong: it included climb and
        # approach rows, inflating the threshold to 6,000-13,000 ft and causing
        # CruiseAlt to fail on every actual cruise row.
        #
        # Fix: filter to rows where VSpd is near-level (|VSpd| < 300 fpm) AND
        # IAS > 50 kts.  This isolates genuine level/cruise flight.  The 80th
        # percentile is used (not 60th) because we want the threshold to sit
        # BELOW most cruise rows -- a threshold that is exceeded by 80% of level
        # flight rows gives the CruiseAlt witness a high hit rate.
        level_mask   = (df['IAS'] > 50) & (df['VSpd'].abs() < 300)
        agl_samples  = df.loc[level_mask, 'AGL']
        if len(agl_samples) >= MIN_ROWS:
            cruise_agl_dyn = float(np.percentile(agl_samples, 80))
            # Clamp: must be at least 50% of static minimum, at most 3x
            cruise_agl_dyn = np.clip(cruise_agl_dyn,
                                     self.cfg['cruise_agl_min'] * 0.5,
                                     self.cfg['cruise_agl_min'] * 15.0)
        else:
            cruise_agl_dyn = self.cfg['cruise_agl_min']

        self._dyn = {
            'climb_rate'   : climb_dyn,
            'descent_rate' : desc_dyn,
            'cruise_agl'   : cruise_agl_dyn,
        }

        # Store in DataFrame attrs for external access
        df.attrs['dynamic_thresholds'] = dict(self._dyn)

        if self.debug_mode:
            print(f"  [DYN] climb_rate   = {climb_dyn:.1f} fpm "
                  f"(static: {self.cfg['climb_rate_threshold']:.1f})")
            print(f"  [DYN] descent_rate = {desc_dyn:.1f} fpm")
            print(f"  [DYN] cruise_agl   = {cruise_agl_dyn:.1f} ft "
                  f"(static: {self.cfg['cruise_agl_min']:.1f})")

    # ── 3. SPECIAL EVENT DETECTION  (v2 logic; persistence filter added)

    def detect_special_events(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect special flight events before phase classification.

        Event label convention
        ----------------------
        Every event name carries a severity suffix:  EVENTNAME_S{1|2|3}
        Where multiple tiers exist for the same event, only the highest
        severity is tagged per row (S3 takes precedence over S2, S2 over S1).
        Multiple distinct events on the same row are pipe-separated.

        Severity guide
        --------------
        S1  Notice   – informational; flag for trend analysis
        S2  Warning  – SOP deviation or operational risk
        S3  Critical – airworthiness concern; mandatory report / inspection

        All raw boolean masks go through require_persistence() to suppress
        single-row sensor spikes before events are confirmed.
        """
        events = pd.Series(['NORMAL'] * len(df), index=df.index)
        cfg    = self.cfg

        # ── Pre-computed helpers ──────────────────────────────────────────────
        vref      = cfg.get('vref_approach', cfg['rotation_ias'] + 22)
        vref_proxy = cfg['rotation_ias'] + 5   # lightweight Vref proxy for scoring

        peak_pos    = int(df['AGL'].argmax())
        is_dep_side = pd.Series(False, index=df.index)
        is_arr_side = pd.Series(False, index=df.index)
        is_dep_side.iloc[:peak_pos] = True
        is_arr_side.iloc[peak_pos:] = True

        airborne      = df['AGL'] > 50
        airborne_low  = (df['AGL'] > 10) & (df['AGL'] < 500)
        airborne_1k   = (df['AGL'] > 10) & (df['AGL'] < 1000)
        on_rwy        = (df['AGL'] < 30) & (df['GndSpd'] > 20)

        # ─────────────────────────────────────────────────────────────────────
        # 1. HARD LANDING
        #    S2: NormAc 1.8 – 2.1 g
        #    S3: NormAc > 2.1 g  (maintenance inspection required)
        # ─────────────────────────────────────────────────────────────────────
        # _g_offset converts physics thresholds to the CSV's recording scale:
        #   Absolute format (_normac_offset=1.0): _g_offset=0.0 → no change
        #   Delta format    (_normac_offset=0.0): _g_offset=1.0 → subtract 1.0
        # e.g. 1.8G physics → 1.8 absolute csv, 0.8 delta csv
        _g_offset = 1.0 - self._normac_offset

        g_warn = cfg['hard_landing_g']                       # default 1.8
        g_crit = cfg.get('hard_landing_g_critical', 2.1)

        hl_s3_raw = (df['NormAc_peak'] >= g_crit - _g_offset) & on_rwy
        hl_s2_raw = (df['NormAc_peak'] >= g_warn - _g_offset) & on_rwy & ~hl_s3_raw

        hl_s3 = require_persistence(hl_s3_raw, 2)
        hl_s2 = require_persistence(hl_s2_raw, 2)

        events[hl_s3]            = _append_event(events[hl_s3],            'HARD_LANDING_S3')
        events[hl_s2 & ~hl_s3]  = _append_event(events[hl_s2 & ~hl_s3],  'HARD_LANDING_S2')

        # ─────────────────────────────────────────────────────────────────────
        # 2. HIGH DESCENT RATE
        #    S1: < −1000 fpm below 1000 AGL  (poor energy management)
        #    S2: < −1500 fpm below 500 AGL   (unstabilised approach criterion)
        #    S3: < −2000 fpm below 500 AGL   (CFIT risk)
        # ─────────────────────────────────────────────────────────────────────
        hdr_s3_raw = (df['VSpd'] < -2000) & airborne_low
        hdr_s2_raw = (df['VSpd'] < -1500) & airborne_low  & ~hdr_s3_raw
        hdr_s1_raw = (df['VSpd'] < -1000) & airborne_1k   & ~hdr_s3_raw & ~hdr_s2_raw

        hdr_s3 = require_persistence(hdr_s3_raw, 2)
        hdr_s2 = require_persistence(hdr_s2_raw, 3)
        hdr_s1 = require_persistence(hdr_s1_raw, 3)

        events[hdr_s3]             = _append_event(events[hdr_s3],             'HIGH_DESCENT_RATE_S3')
        events[hdr_s2 & ~hdr_s3]  = _append_event(events[hdr_s2 & ~hdr_s3],  'HIGH_DESCENT_RATE_S2')
        events[hdr_s1 & ~hdr_s2]  = _append_event(events[hdr_s1 & ~hdr_s2],  'HIGH_DESCENT_RATE_S1')

        # ─────────────────────────────────────────────────────────────────────
        # 3. APPROACH SPEED DEVIATIONS (arrival side, below 500 AGL, descending)
        #    HIGH S1: IAS > Vref + 20  (float / overrun risk)
        #    HIGH S2: IAS > Vref + 35  (significant overrun risk)
        #    LOW  S2: IAS < Vref − 10  (stall margin reduced)
        # ─────────────────────────────────────────────────────────────────────
        on_approach = is_arr_side & airborne_low & (df['VSpd'] < -50)

        has_s2_raw = (df['IAS'] > vref + 35) & on_approach
        has_s1_raw = (df['IAS'] > vref + 20) & on_approach & ~has_s2_raw
        las_s2_raw = (df['IAS'] < vref - 10) & on_approach

        has_s2 = require_persistence(has_s2_raw, 5)
        has_s1 = require_persistence(has_s1_raw, 5)
        las_s2 = require_persistence(las_s2_raw, 3)

        events[has_s2]            = _append_event(events[has_s2],            'HIGH_APPROACH_SPEED_S2')
        events[has_s1 & ~has_s2] = _append_event(events[has_s1 & ~has_s2], 'HIGH_APPROACH_SPEED_S1')
        events[las_s2]            = _append_event(events[las_s2],            'LOW_APPROACH_SPEED_S2')

        # ─────────────────────────────────────────────────────────────────────
        # 4. UNSTABLE APPROACH  (multi-parameter, S2 only)
        #    Fires when ≥ 2 of: speed, VS, bank, power are simultaneously out.
        #    Scored independently from the speed-only events above.
        # ─────────────────────────────────────────────────────────────────────
        ua_score = (
            ((df['IAS'] < vref_proxy - 10) | (df['IAS'] > vref_proxy + 20)).astype(int) +
            (df['VSpd'] < -1200).astype(int) +
            (df['Roll'].abs() > 10).astype(int) +
            (df['E1 Torq'] < 400).astype(int)
        )
        ua_s2_raw = (
            is_arr_side & airborne_1k & (df['AGL'] > 10) &
            (df['VSpd'] < -50) & (ua_score >= 2)
        )
        ua_s2 = require_persistence(ua_s2_raw, 5)
        events[ua_s2] = _append_event(events[ua_s2], 'UNSTABLE_APPROACH_S2')

        # ─────────────────────────────────────────────────────────────────────
        # 5. GO-AROUND  (S1 — procedural flag, not a pilot error)
        #    Rapid power + positive VS recovery close to the ground, from a
        #    landing-band phase.
        # ─────────────────────────────────────────────────────────────────────
        ga_raw = (
            (df['AGL'] < 300) &
            (df['Torq_deriv'] > 200) &
            (df['VSpd_deriv'] > 50) &
            (df['VSpd'] > -200)
        )
        ga_s1 = require_persistence(ga_raw, 3)
        events[ga_s1] = _append_event(events[ga_s1], 'GO_AROUND_S1')

        # ─────────────────────────────────────────────────────────────────────
        # 6. REJECTED TAKEOFF  (S2)
        #    High-speed deceleration on the ground — brake and structural check.
        # ─────────────────────────────────────────────────────────────────────
        rto_raw = (
            (df['GndSpd'] > 40) &
            (df['Torq_deriv'] < -200) &
            (df['GndSpd_deriv'] < -1.0) &
            (df['AGL'] < 30)
        )
        rto_s2 = require_persistence(rto_raw, 3)
        events[rto_s2] = _append_event(events[rto_s2], 'REJECTED_TAKEOFF_S2')

        # ─────────────────────────────────────────────────────────────────────
        # 7. RAPID POWER APPLICATION
        #    Uses single-frame torque diff (1-Hz = ft·lb/s) for sensitivity.
        #    Smoothed Torq_deriv would understate brief throttle slams.
        #    S1: rate > rapid_power_warn  (200 ft·lb/s)
        #    S2: rate > rapid_power_critical  (400 ft·lb/s)
        # ─────────────────────────────────────────────────────────────────────
        rp_warn = cfg.get('rapid_power_warn',    200.0)
        rp_crit = cfg.get('rapid_power_critical', 400.0)
        torq_rate = df['E1 Torq'].diff().abs()   # raw 1-Hz rate (ft·lb/s)

        rp_s2_raw = (torq_rate > rp_crit) & (df['AGL'] > 0)
        rp_s1_raw = (torq_rate > rp_warn) & (df['AGL'] > 0) & ~rp_s2_raw

        rp_s2 = require_persistence(rp_s2_raw, 1)
        rp_s1 = require_persistence(rp_s1_raw, 1)

        events[rp_s2]            = _append_event(events[rp_s2],            'RAPID_POWER_S2')
        events[rp_s1 & ~rp_s2]  = _append_event(events[rp_s1 & ~rp_s2],  'RAPID_POWER_S1')

        # ─────────────────────────────────────────────────────────────────────
        # 8. OVERSPEED
        #    S2: IAS > Vmo  (structural load concern)
        #    S3: IAS > Vmo + 10  (approaching structural limit)
        # ─────────────────────────────────────────────────────────────────────
        vmo = cfg.get('vmo_kias', 175.0)

        os_s3_raw = (df['IAS'] > vmo + 10) & airborne
        os_s2_raw = (df['IAS'] > vmo)       & airborne & ~os_s3_raw

        os_s3 = require_persistence(os_s3_raw, 3)
        os_s2 = require_persistence(os_s2_raw, 3)

        events[os_s3]            = _append_event(events[os_s3],            'OVERSPEED_S3')
        events[os_s2 & ~os_s3]  = _append_event(events[os_s2 & ~os_s3],  'OVERSPEED_S2')

        # ─────────────────────────────────────────────────────────────────────
        # 9. LOW AIRSPEED  (airborne, not during normal approach / landing)
        #    Excludes AGL < 100 to avoid false triggers during flare / touchdown.
        #    S2: IAS < low_airspeed_warn      (reduced stall margin)
        #    S3: IAS < low_airspeed_critical  (imminent stall / LOC-I risk)
        # ─────────────────────────────────────────────────────────────────────
        la_warn = cfg.get('low_airspeed_warn',    78.0)
        la_crit = cfg.get('low_airspeed_critical', 68.0)
        airborne_enroute = (df['AGL'] > 100) & (df['IAS'] > 0)

        la_s3_raw = (df['IAS'] < la_crit) & airborne_enroute
        la_s2_raw = (df['IAS'] < la_warn) & airborne_enroute & ~la_s3_raw

        la_s3 = require_persistence(la_s3_raw, 2)
        la_s2 = require_persistence(la_s2_raw, 3)

        events[la_s3]            = _append_event(events[la_s3],            'LOW_AIRSPEED_S3')
        events[la_s2 & ~la_s3]  = _append_event(events[la_s2 & ~la_s3],  'LOW_AIRSPEED_S2')

        # ─────────────────────────────────────────────────────────────────────
        # 10. STEEP BANK
        #    S1: Roll > 45° above 1000 AGL  (airmanship / SOP check)
        #    S2: Roll > 30° below 1000 AGL  (exceeds low-altitude limit)
        #    S3: Roll > 45° below 500 AGL   (LOC-I risk zone)
        # ─────────────────────────────────────────────────────────────────────
        bank = df['Roll'].abs()

        sb_s3_raw = (bank > 45) & (df['AGL'] < 500)  & (df['AGL'] > 50)
        sb_s2_raw = (bank > 30) & (df['AGL'] < 1000) & (df['AGL'] > 50) & ~sb_s3_raw
        sb_s1_raw = (bank > 45) & (df['AGL'] >= 1000)

        sb_s3 = require_persistence(sb_s3_raw, 2)
        sb_s2 = require_persistence(sb_s2_raw, 3)
        sb_s1 = require_persistence(sb_s1_raw, 3)

        events[sb_s3]                      = _append_event(events[sb_s3],                      'STEEP_BANK_S3')
        events[sb_s2 & ~sb_s3]            = _append_event(events[sb_s2 & ~sb_s3],            'STEEP_BANK_S2')
        events[sb_s1 & ~sb_s2 & ~sb_s3]  = _append_event(events[sb_s1 & ~sb_s2 & ~sb_s3],  'STEEP_BANK_S1')

        # ─────────────────────────────────────────────────────────────────────
        # 11. NEGATIVE G
        #    S1: brief unloading (2+ row)
        #    S2: sustained (3+ rows) — fuel/oil system interruption risk
        # Threshold: 0G physics → 0.0 absolute csv, -1.0 delta csv
        # ─────────────────────────────────────────────────────────────────────
        neg_g_raw = (df['NormAc'] < (0.0 - _g_offset)) & airborne

        ng_s2 = require_persistence(neg_g_raw, 3)
        ng_s1 = require_persistence(neg_g_raw, 2) & ~ng_s2

        events[ng_s2]           = _append_event(events[ng_s2],           'NEGATIVE_G_S2')
        events[ng_s1 & ~ng_s2] = _append_event(events[ng_s1 & ~ng_s2], 'NEGATIVE_G_S1')

        # ─────────────────────────────────────────────────────────────────────
        # 12. TAIL STRIKE RISK  (S2)
        #    High pitch + low IAS near ground. Detect before rotation geometry
        #    becomes irreversible.
        # ─────────────────────────────────────────────────────────────────────
        ts_raw = (
            (df['Pitch'] > 15) &
            (df['IAS'] < cfg['rotation_ias'] + 10) &
            (df['AGL'] < 50) &
            (df['GndSpd'] > 30)
        )
        ts_s2 = require_persistence(ts_raw, 2)
        events[ts_s2] = _append_event(events[ts_s2], 'TAIL_STRIKE_RISK_S2')

        # ─────────────────────────────────────────────────────────────────────
        # 13. HIGH ITT  (verify limits against aircraft AMM)
        #    S2: above max continuous  (accelerated hot-section wear)
        #    S3: at / above takeoff limit in cruise  (mandatory engine inspection)
        # ─────────────────────────────────────────────────────────────────────
        if 'E1 ITT' in df.columns:
            itt_warn  = cfg.get('itt_warn',  740.0)
            itt_limit = cfg.get('itt_limit', 800.0)

            hi_itt_s3_raw = (df['E1 ITT'] > itt_limit) & airborne
            hi_itt_s2_raw = (df['E1 ITT'] > itt_warn)  & airborne & ~hi_itt_s3_raw

            hi_itt_s3 = require_persistence(hi_itt_s3_raw, 3)
            hi_itt_s2 = require_persistence(hi_itt_s2_raw, 5)

            events[hi_itt_s3]               = _append_event(events[hi_itt_s3],               'HIGH_ITT_S3')
            events[hi_itt_s2 & ~hi_itt_s3] = _append_event(events[hi_itt_s2 & ~hi_itt_s3], 'HIGH_ITT_S2')

        # ─────────────────────────────────────────────────────────────────────
        # 14. UNSTABLE DEPARTURE  (S1)
        #    ≥ 2 of: abnormal IAS / low VS / excessive bank / low torque
        # ─────────────────────────────────────────────────────────────────────
        ud_score = (
            ((df['IAS'] < cfg['rotation_ias'] - 5) |
             (df['IAS'] > cfg['rotation_ias'] + 30)).astype(int) +
            (df['VSpd'] < cfg['climb_rate_threshold'] * 0.5).astype(int) +
            (df['Roll'].abs() > 20).astype(int) +
            (df['E1 Torq'] < cfg['climb_torque_min'] * 0.7).astype(int)
        )
        ud_raw = (
            is_dep_side & (df['AGL'] < 1500) & (df['AGL'] > 30) &
            (df['VSpd'] > -200) & (ud_score >= 2)
        )
        ud_s1 = require_persistence(ud_raw, 5)
        events[ud_s1] = _append_event(events[ud_s1], 'UNSTABLE_DEPARTURE_S1')

        # ─────────────────────────────────────────────────────────────────────
        # 15. UNSTABLE CIRCUIT  (S1)
        #    Speed / bank / VS instability in circuit band (200–1500 AGL),
        #    excluding rows already tagged as unstable approach or departure.
        # ─────────────────────────────────────────────────────────────────────
        uc_score = (
            ((df['IAS'] < vref_proxy - 15) | (df['IAS'] > vref_proxy + 25)).astype(int) +
            ((df['VSpd'] < -1500) | (df['VSpd'] > 1500)).astype(int) +
            (df['Roll'].abs() > 30).astype(int)
        )
        uc_raw = (
            (df['AGL'] >= 200) & (df['AGL'] <= 1500) &
            ~ua_s2 & ~ud_s1 & (uc_score >= 2)
        )
        uc_s1 = require_persistence(uc_raw, 4)
        events[uc_s1] = _append_event(events[uc_s1], 'UNSTABLE_CIRCUIT_S1')

        # ─────────────────────────────────────────────────────────────────────
        # 16. ENGINE IDLE DESCENT  (S1 — informational)
        #    30 consecutive seconds of descending at idle power above 500 AGL.
        # ─────────────────────────────────────────────────────────────────────
        idle_desc_raw    = (df['VSpd'] < -300) & (df['fflow_idle'] == 1) & (df['AGL'] > 500)
        idle_desc_rolling = idle_desc_raw.rolling(window=30, min_periods=30).sum()
        events[idle_desc_rolling >= 30] = _append_event(
            events[idle_desc_rolling >= 30], 'ENGINE_IDLE_DESCENT_S1')

        # ─────────────────────────────────────────────────────────────────────
        # 17. HIGH WIND LANDING  (S1 — condition flag)
        # ─────────────────────────────────────────────────────────────────────
        hw_raw = (
            (df['CrosswindComp'] > cfg['high_wind_landing_kts']) &
            (df['AGL'] < 500) & (df['GndSpd'] > 20)
        )
        hw_s1 = require_persistence(hw_raw, 1)
        events[hw_s1] = _append_event(events[hw_s1], 'HIGH_WIND_LANDING_S1')

        df['FLIGHT_EVENT'] = events
        return df

    def extract_event_windows(self, df):
        """
        Collapse contiguous FLIGHT_EVENT rows into discrete event window records.

        FIXED: Uses string-matching instead of `.explode()` to prevent Index duplication errors.

        Each returned dict contains:
            event       base event name WITHOUT severity suffix (e.g. 'HARD_LANDING')
            severity    integer 1 / 2 / 3  (parsed from _S{n} suffix)
            label       full label as stored in FLIGHT_EVENT (e.g. 'HARD_LANDING_S3')
            start_row   first DataFrame index of the window
            end_row     last DataFrame index of the window
            duration_sec  number of rows (1-Hz assumption)
            peak_value  type-appropriate peak (g for landing, fpm for descent, etc.)
        """
        events = []

        if 'FLIGHT_EVENT' not in df.columns:
            return events

        # Collect unique event labels present in the DataFrame
        unique_labels = set()
        for val in df['FLIGHT_EVENT'].dropna().unique():
            if val != 'NORMAL':
                unique_labels.update(str(val).split('|'))

        for label in sorted(unique_labels):
            # ── Parse base name and severity from label (e.g. 'HARD_LANDING_S3')
            import re as _re
            sev_match = _re.search(r'_S([123])$', label)
            if sev_match:
                severity  = int(sev_match.group(1))
                base_name = label[:sev_match.start()]
            else:
                # Legacy label without suffix — treat as S1
                severity  = 1
                base_name = label

            # Boolean mask for this specific label WITHOUT exploding the index
            mask = df['FLIGHT_EVENT'].fillna('').str.contains(label, regex=False)
            groups = (mask != mask.shift()).cumsum()

            for _, grp in df[mask].groupby(groups):
                start_idx    = grp.index[0]
                end_idx      = grp.index[-1]
                duration_sec = len(grp)

                # ── Peak value — select the most meaningful sensor per event type
                peak_value = None

                if base_name == 'HARD_LANDING' and 'NormAc_peak' in grp.columns:
                    peak_value = float(grp['NormAc_peak'].max())

                elif base_name == 'HIGH_DESCENT_RATE' and 'VSpd' in grp.columns:
                    peak_value = float(grp['VSpd'].min())   # most negative fpm

                elif base_name in ('HIGH_APPROACH_SPEED', 'LOW_APPROACH_SPEED',
                                   'OVERSPEED', 'LOW_AIRSPEED') and 'IAS' in grp.columns:
                    peak_value = float(grp['IAS'].max()) \
                                 if 'HIGH' in base_name or 'OVER' in base_name \
                                 else float(grp['IAS'].min())

                elif base_name == 'RAPID_POWER' and 'E1 Torq' in grp.columns:
                    peak_value = float(grp['E1 Torq'].diff().abs().max())

                elif base_name == 'STEEP_BANK' and 'Roll' in grp.columns:
                    peak_value = float(grp['Roll'].abs().max())

                elif base_name == 'NEGATIVE_G' and 'NormAc' in grp.columns:
                    peak_value = float(grp['NormAc'].min())

                elif base_name == 'TAIL_STRIKE_RISK' and 'Pitch' in grp.columns:
                    peak_value = float(grp['Pitch'].max())

                elif base_name == 'HIGH_ITT' and 'E1 ITT' in grp.columns:
                    peak_value = float(grp['E1 ITT'].max())

                events.append({
                    'event'       : base_name,
                    'severity'    : severity,
                    'label'       : label,
                    'start_row'   : int(start_idx),
                    'end_row'     : int(end_idx),
                    'duration_sec': int(duration_sec),
                    'peak_value'  : round(peak_value, 2) if peak_value is not None else None,
                })

        # Sort by start row for chronological output
        events.sort(key=lambda x: x['start_row'])
        return events


    # ── 4. SINGLE-ROW CLASSIFIER

    def _classify_row(self,
                      agl, gndspd, ias, vspd, torque, fflow, ng,
                      pitch, roll, latac, normac,
                      ias_d, vspd_d, gspd_d, torq_d,
                      alt_stab, alt_deriv, energy, energy_d, afcs, gps_ok,
                      in_airborne_hyst: bool,
                      in_climb_hyst:    bool,
                      in_descent_hyst:  bool,
                      prev_phase: str,
                      sm_corrected: bool,
                      ) -> Tuple[str, float, str]:
        """
        Classify a single row using plain scalar arguments.

        CONFIDENCE FIX — Branch-local snapshot scoring
        -----------------------------------------------
        The original implementation used a single global witness accumulator
        across all layers.  Every rejected layer (GO-AROUND fails, ROTATION
        fails, APPROACH fails…) added to witnesses_possible without adding
        to witnesses_hit, collapsing cruise confidence to ~0.26 even on a
        perfect, stable cruise row.

        Fix: the W() closure records ALL checks globally for the reason string,
        but confidence is computed from a SNAPSHOT taken immediately before
        each phase's specific witness checks.  Only the delta
        (hit_since_snap / possible_since_snap) is used as the confidence base.

        This means:
        - CRUISE confidence = fraction of {LevelVSpd, AltStable, AFCS, CruiseAlt}
          that fired — not diluted by failed GO-AROUND / CLIMB / DESCENT checks.
        - GROUND confidence = fraction of ground-specific positive witnesses.
        - GO-AROUND confidence = fraction of {TorqRise, VSpdRecov} that fired.

        All classification DECISIONS (which phase wins) are identical to before.
        Only the confidence NUMBER changes.

        GROUND PHASES — positive witness design
        ----------------------------------------
        Previously ground phases scored near 0 because the two "gate" checks
        (IAS_FLY and AGL_FLY) both failed, giving 0 hits / 2 possible.
        Ground phases now use POSITIVE witnesses that are true when on the ground,
        scored from their own snapshot, giving meaningful confidence values.
        """
        cfg  = self.cfg
        dyn  = self._dyn

        # ── Global witness log (for PHASE_REASON string only)
        _hit_total = [0]
        _pos_total = [0]
        reason_tags: List[str] = []

        def W(hit: bool, tag: str) -> bool:
            """Record a witness globally and return the bool."""
            _pos_total[0] += 1
            if hit:
                _hit_total[0] += 1
                reason_tags.append(tag)
            return hit

        def snap() -> Tuple[int, int, int]:
            """
            Snapshot current global counts.
            Returns (hit_so_far, pos_so_far, tags_so_far).
            Pass to conf_from_snap() to get branch-local confidence.
            """
            return (_hit_total[0], _pos_total[0], len(reason_tags))

        def conf_from_snap(s: Tuple[int, int, int]) -> float:
            """
            Compute confidence from the DELTA since snapshot s.
            Only witnesses checked after snap() contribute to the score.
            """
            hit  = _hit_total[0] - s[0]
            pos  = _pos_total[0] - s[1]
            tags = reason_tags[s[2]:]
            return _confidence(hit, pos, gps_ok, sm_corrected)

        # ─────────────────────────────────────────────────────────────────
        # LAYER 1 – AIRBORNE GATE
        # Determines ground vs airborne routing.
        # These checks are NOT counted in phase confidence — they are a
        # routing gate, not witnesses for any specific phase.
        # ─────────────────────────────────────────────────────────────────
        agl_thr = cfg['liftoff_agl_exit'] if in_airborne_hyst else cfg['liftoff_agl_enter']
        is_airborne    = (ias > cfg['definitely_airborne_ias']) and (agl > agl_thr)
        definitely_ground = not is_airborne

        if definitely_ground:
            # ── ROLLOUT: confirmed by prior landing phase + high speed
            if gndspd > 40 and prev_phase in ('APPROACH', 'FLARE', 'TOUCHDOWN',
                                               'ROLLOUT', 'DESCENDING FLIGHT'):
                s = snap()
                W(gndspd > 40,  'GndSpdHigh')
                W(prev_phase in ('APPROACH','FLARE','TOUCHDOWN',
                                 'ROLLOUT','DESCENDING FLIGHT'), 'PriorLanding')
                return "ROLLOUT", conf_from_snap(s), _reason("ROLLOUT", reason_tags[s[2]:])

            # ── TAKEOFF ROLL: torque committed + accelerating
            s = snap()
            torq_ok  = W(torque > cfg['takeoff_torque_min'], 'TorqHigh')
            accel_ok = W(gspd_d > 0.5, 'GspdAccel')
            if torq_ok and accel_ok and gndspd > 15:
                return "TAKEOFF ROLL", conf_from_snap(s), _reason("TAKEOFF ROLL", reason_tags[s[2]:])

            # ── TAXI: moving but not committed to takeoff
            s = snap()
            if gndspd > cfg['taxi_speed_threshold']:
                W(gndspd > cfg['taxi_speed_threshold'], 'GndSpdTaxi')
                W(ias < cfg['definitely_airborne_ias'], 'IAS_Slow')
                return "TAXI", conf_from_snap(s), _reason("TAXI", reason_tags[s[2]:])

            # ── GROUND: stationary or engine-start only
            s = snap()
            W(gndspd < cfg['taxi_speed_threshold'], 'GndSpdLow')
            W(ias     < cfg['definitely_airborne_ias'], 'IAS_Slow')
            return "GROUND", conf_from_snap(s), _reason("GROUND", reason_tags[s[2]:])

        # ── From here: aircraft is confirmed airborne ──────────────────────

        # ─────────────────────────────────────────────────────────────────
        # LAYER 2 – GO-AROUND
        # ─────────────────────────────────────────────────────────────────
        if agl < 300 and vspd > -200 and \
                prev_phase in ('APPROACH', 'FLARE', 'TOUCHDOWN', 'DESCENDING FLIGHT'):
            s = snap()
            torq_rise   = W(torq_d  > 200, 'TorqRise')
            vspd_recov  = W(vspd_d  >  50, 'VSpdRecov')
            if torq_rise and vspd_recov:
                return "GO-AROUND", conf_from_snap(s), _reason("GO-AROUND", reason_tags[s[2]:])

        # ─────────────────────────────────────────────────────────────────
        # LAYER 3 – ROTATION / INITIAL CLIMB
        # ─────────────────────────────────────────────────────────────────
        if agl < 300 and vspd > 0 and \
                prev_phase in ('TAKEOFF ROLL', 'ROTATION', 'GROUND', 'TAXI'):
            s = snap()
            pitch_ok = W(pitch   >  2,                         'PitchPos')
            ias_ok   = W(ias    >= cfg['rotation_ias'] - 5,    'IAS_Vr')
            torq_ok  = W(torque >  cfg['climb_torque_min'],    'TorqClimb')
            if pitch_ok and ias_ok and torq_ok:
                ph = "ROTATION" if agl < 100 else "INITIAL CLIMB"
                return ph, conf_from_snap(s), _reason(ph, reason_tags[s[2]:])

        if agl < 1000 and \
                prev_phase in ('ROTATION', 'INITIAL CLIMB', 'TAKEOFF ROLL'):
            s = snap()
            vspd_ok = W(vspd   >  dyn['climb_rate'],        'VSpdClimb')
            torq_ok = W(torque >  cfg['climb_torque_min'],  'TorqClimb')
            if vspd_ok and torq_ok:
                return "INITIAL CLIMB", conf_from_snap(s), _reason("INITIAL CLIMB", reason_tags[s[2]:])

        # ─────────────────────────────────────────────────────────────────
        # LAYER 4 – LANDING BAND
        # ─────────────────────────────────────────────────────────────────
        if agl < cfg['touchdown_agl']:
            s = snap()
            W(normac > 1.15, 'NormAcSpike')
            W(gndspd > 20,   'GndSpdOk')
            ph = "ROLLOUT" if gndspd > 40 else "TOUCHDOWN"
            return ph, conf_from_snap(s), _reason(ph, reason_tags[s[2]:])

        if agl < cfg['flare_agl']:
            s = snap()
            pitch_ok = W(pitch > 2,      'PitchFlare')
            vspd_ok  = W(vspd  > -400,   'VSpdArrest')
            ph = "FLARE" if (pitch_ok and vspd_ok) else "APPROACH"
            return ph, conf_from_snap(s), _reason(ph, reason_tags[s[2]:])

        # ─────────────────────────────────────────────────────────────────
        # LAYER 5 – APPROACH BAND
        # ─────────────────────────────────────────────────────────────────
        if agl < 1500:
            s = snap()
            desc_ok = W(vspd < -100, 'VSpdDesc') or (not gps_ok and alt_deriv < -50)
            ias_ok  = W(ias  > (cfg['rotation_ias'] - 10), 'IAS_Apch')
            if desc_ok and ias_ok:
                return "APPROACH", conf_from_snap(s), _reason("APPROACH", reason_tags[s[2]:])

        # ─────────────────────────────────────────────────────────────────
        # LAYER 6 – ENERGY-STATE ROUTING
        # Each sub-category gets its own snapshot so only its specific
        # witnesses affect its confidence score.
        # ─────────────────────────────────────────────────────────────────

        # ── CLIMB
        # Scoring witnesses: VSpdClimb, TorqHigh, AltRise (3 witnesses, need ≥2)
        # Tiebreaker (NOT scored): energy_building — used only to choose
        # CLIMB vs CLIMBING FLIGHT.  If it were a scored witness it would
        # permanently reduce confidence on rows where energy is already
        # plateauing (normal mid-climb) even though the phase is correct.
        climb_thr     = cfg['climb_rate_exit'] if in_climb_hyst else cfg['climb_rate_enter']
        energy_building = energy_d > 0.005   # plain bool — not a W() call
        s = snap()
        is_climbing   = W(vspd   > climb_thr,               'VSpdClimb')
        has_climb_pwr = W(torque > cfg['climb_torque_min'],  'TorqHigh')
        alt_rising    = W(alt_deriv > 50,                    'AltRise')
        climb_score   = is_climbing + has_climb_pwr + alt_rising
        if climb_score >= 2:
            ph = "CLIMB" if (agl < 3000 or
                             prev_phase in ('INITIAL CLIMB', 'ROTATION') or
                             energy_building or energy_d > 0.002) else "CLIMBING FLIGHT"
            return ph, conf_from_snap(s), _reason(ph, reason_tags[s[2]:])

        # ── DESCENT
        # Scoring witnesses: VSpdDesc, FFlowIdle, AltFall (3 witnesses, need ≥2)
        # Tiebreaker (NOT scored): energy_falling — used only to choose
        # DESCENT vs DESCENDING FLIGHT.
        desc_thr      = cfg['descent_rate_exit'] if in_descent_hyst else cfg['descent_rate_enter']
        energy_falling = energy_d < -0.005   # plain bool — not a W() call
        s = snap()
        is_descending  = W(vspd    < -desc_thr,             'VSpdDesc')
        is_idle_pwr    = W(fflow   < cfg['idle_fflow_max'], 'FFlowIdle')
        alt_falling    = W(alt_deriv < -50,                 'AltFall')
        descent_score  = is_descending + alt_falling + is_idle_pwr
        if descent_score >= 2:
            ph = "DESCENT" if (is_idle_pwr and
                               (energy_falling or energy_d < -0.003)) else "DESCENDING FLIGHT"
            return ph, conf_from_snap(s), _reason(ph, reason_tags[s[2]:])

        # ── CRUISE / LEVEL FLIGHT
        # Scoring witnesses: LevelVSpd, AltStable, CruiseAlt (3 core witnesses)
        # AFCS is a BONUS confidence boost, not a scoring witness.
        # Rationale: hand-flying is normal procedure; penalising pilots who
        # don't use autopilot by capping cruise confidence at 3/4 = 0.75 is
        # operationally incorrect.  AFCS engagement is evidence OF cruise, not
        # a requirement for it.  It boosts confidence from 1.0 → 1.0 (already
        # at max when all 3 core fire) or adds a partial boost otherwise.
        # The threshold remains 2 of 3 core witnesses (same strictness as before).
        afcs_on      = (afcs == 1)   # plain bool — bonus, not a W() call
        s = snap()
        is_level       = W(abs(vspd) < 200,               'LevelVSpd')
        alt_stable     = W(alt_stab  < 80,                'AltStable')
        in_cruise_band = W(agl       > dyn['cruise_agl'], 'CruiseAlt')
        if afcs_on:
            W(True, 'AFCS')   # bonus: only called when actually true, no denominator hit when false
        cruise_score   = is_level + alt_stable + in_cruise_band + afcs_on
        if cruise_score >= 2:
            ph = "LEVEL FLIGHT" if abs(energy_d) > 0.01 else "CRUISE"
            return ph, conf_from_snap(s), _reason(ph, reason_tags[s[2]:])

        # ── MANEUVERING
        s = snap()
        bank_ok  = W(abs(roll) > 25,   'BankHigh')
        latac_ok = W(latac     > 0.15, 'LatAcHigh')
        if bank_ok and latac_ok and agl > 200:
            return "MANEUVERING", conf_from_snap(s), _reason("MANEUVERING", reason_tags[s[2]:])

        # ── LEVEL FLIGHT catch-all (is_level was computed in cruise block above)
        if is_level:
            # Reuse the cruise-block snapshot's level witness only
            s2 = snap()
            W(abs(vspd) < 200, 'LevelVSpd')
            return "LEVEL FLIGHT", conf_from_snap(s2), _reason("LEVEL FLIGHT", reason_tags[s2[2]:])

        # ── Hold: nothing matched
        return prev_phase, 0.1, f"{prev_phase}|Hold"

    # ── 5. TRANSITION VALIDATOR  (v2 logic unchanged)

    def _validate_transition(self, prev: Optional[str], raw: str) -> str:
        if prev is None:
            return raw
        allowed = VALID_TRANSITIONS.get(prev, list(VALID_TRANSITIONS.keys()))
        if raw in allowed:
            return raw
        return prev

    # ── 6. SMOOTHER  (v2 logic unchanged — single-pass O(n))

    def _smooth_phases(self, df: pd.DataFrame) -> pd.DataFrame:
        """Single-pass run-length smoother. Unchanged from v2."""
        PROTECTED = {'GO-AROUND'}
        phases    = df['FLIGHT_PHASE'].tolist()
        n         = len(phases)
        if n == 0:
            return df

        runs: List[List] = []
        for ph in phases:
            if runs and runs[-1][0] == ph:
                runs[-1][1] += 1
            else:
                runs.append([ph, 1])

        i = 0
        while i < len(runs):
            ph, cnt = runs[i]
            if cnt < self.SMOOTHING_MIN_DURATION and ph not in PROTECTED:
                if i + 1 < len(runs):
                    runs[i + 1][1] += cnt
                    runs.pop(i)
                elif i > 0:
                    runs[i - 1][1] += cnt
                    runs.pop(i)
                else:
                    i += 1
            else:
                i += 1

        smoothed: List[str] = []
        for ph, cnt in runs:
            smoothed.extend([ph] * cnt)

        df['FLIGHT_PHASE'] = smoothed
        return df

    # ── 7. POST-PASS AUDITOR  (v2 logic unchanged; stability index added)

    def _post_audit(self, df: pd.DataFrame) -> pd.DataFrame:
        """Vectorised segment-level consistency. Unchanged from v2."""
        phases = df['FLIGHT_PHASE'].copy()

        # Rule 1: CRUISE below cruise_agl_min → LEVEL FLIGHT
        cruise_too_low = (phases == 'CRUISE') & (df['AGL'] < self.cfg['cruise_agl_min'])
        phases[cruise_too_low] = 'LEVEL FLIGHT'

        # Rule 2: APPROACH with mean VSpd > 100 → LEVEL FLIGHT
        approach_mask = phases == 'APPROACH'
        if approach_mask.any():
            group_id = (approach_mask != approach_mask.shift()).cumsum()
            approach_groups = group_id[approach_mask]
            mean_vspd = df.loc[approach_mask, 'VSpd'].groupby(approach_groups).mean()
            bad_groups = set(mean_vspd[mean_vspd > 100].index)
            if bad_groups:
                bad_rows = approach_mask & group_id.isin(bad_groups)
                phases[bad_rows] = 'LEVEL FLIGHT'

        df['FLIGHT_PHASE'] = phases
        return df

    # ── V3 NEW: PHASE STABILITY INDEX ────────────────────────────────────────

    def _compute_phase_stability(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute PHASE_STABILITY — rolling 10-row same-phase agreement ratio.

        Definition
        ----------
        For each row i, PHASE_STABILITY is the fraction of rows in the
        window [i-9 … i] that have the SAME phase as row i.

        Value of 1.0 = phase has been identical for ≥10 consecutive rows.
        Value of 0.1 = maximum instability (every row different in window).

        Use in FOQA
        -----------
        * KPI computation should filter or weight by PHASE_STABILITY.
          A metric computed during a low-stability zone (e.g., 0.3) is
          less reliable than one during a stable cruise (1.0).
        * PHASE_STABILITY < 0.5 during approach → flag for manual review.
        * Can be used as a noise filter: only count events that occur
          during rows with PHASE_STABILITY > 0.7.

        Implementation
        --------------
        Vectorised: encode phases as integers, compute rolling mode agreement
        without a Python loop. O(n) via rolling sum per unique phase.
        """
        phases  = df['FLIGHT_PHASE']
        window  = 10
        n_rows  = len(df)
        result  = np.zeros(n_rows, dtype=float)

        # For each unique phase, compute rolling fraction of rows matching
        # that phase within the window.  Max across all phases = stability.
        for phase in phases.unique():
            is_phase     = (phases == phase).astype(float)
            rolling_frac = is_phase.rolling(window=window, min_periods=1).mean()
            # Assign to result only where this IS the current phase
            mask         = (phases == phase).to_numpy()
            result[mask] = rolling_frac.to_numpy()[mask]

        df['PHASE_STABILITY'] = result
        return df

    # ── 8. MAIN PIPELINE  (V3: adds adaptive thresholds, new columns, debug)

    def classify(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Execute the full classification pipeline.

        V2 pipeline (steps 1–6, all preserved):
        1. Compute derived parameters
        2. Compute dynamic AGL
        3. Detect special events
        4. First-pass phase classification (state-machine loop)
        5. Temporal smoothing
        6. Post-pass audit

        V3 additions:
        2a. Compute adaptive thresholds (between AGL and events)
        4.  Loop now tracks hysteresis state, collects confidence + reason
        6a. Compute PHASE_STABILITY index (after audit)
        """
        # ── Ensure a clean 0-based integer index throughout the pipeline.
        # G1000 CSVs read with skiprows can carry duplicate or non-contiguous
        # index labels which cause pandas to raise
        # "cannot reindex on an axis with duplicate labels"
        # inside rolling / iloc[::-1] operations in require_persistence().
        df = df.reset_index(drop=True)

        print("  [1/8] Computing derived parameters...")
        df = self.compute_derived(df)

        print("  [2/8] Computing dynamic AGL (gradient model)...")
        df = self.compute_agl(df)

        print("  [3/8] Computing adaptive thresholds...")
        self.compute_adaptive_thresholds(df)

        print("  [4/8] Detecting special events (with persistence filter)...")
        df = self.detect_special_events(df)

        events = self.extract_event_windows(df)

        print("\n===== EVENT WINDOWS =====")
        for e in events:
            print(e)

        print("  [5/8] First-pass classification (hysteresis + confidence)...")

        # ── Pre-extract all columns to numpy arrays (v2 optimisation preserved)
        def _arr(col: str) -> np.ndarray:
            return df[col].to_numpy(dtype=float, na_value=0.0)

        a_agl      = _arr('AGL')
        a_gndspd   = _arr('GndSpd')
        a_ias      = _arr('IAS')
        a_vspd     = _arr('VSpd')
        a_torque   = _arr('E1 Torq')
        a_fflow    = _arr('E1 FFlow')
        a_ng       = _arr('E1 NG')
        a_pitch    = _arr('Pitch')
        a_roll     = _arr('Roll')
        a_latac    = _arr('LatAc_abs')
        a_normac   = _arr('NormAc_peak')
        a_ias_d    = _arr('IAS_deriv')
        a_vspd_d   = _arr('VSpd_deriv')
        a_gspd_d   = _arr('GndSpd_deriv')
        a_torq_d   = _arr('Torq_deriv')
        a_altstab  = _arr('Alt_stability')
        a_altd     = _arr('Alt_deriv')
        a_energy   = _arr('Energy_State')
        a_energy_d = _arr('Energy_State_deriv')   # V3 addition
        a_afcs     = _arr('AfcsOn')
        a_gpsq     = _arr('GPS_quality')

        phases:      List[str]   = []
        confidences: List[float] = []
        reasons:     List[str]   = []

        current_phase: Optional[str] = None
        hold_count    = 0
        MAX_HOLD      = 5

        # ── V3: Hysteresis state (tracked in loop, NOT in _classify_row)
        # These booleans represent whether the aircraft is currently
        # considered to be "in" the airborne/climb/descent state.
        # They are updated AFTER each row is classified.
        in_airborne_hyst = False
        in_climb_hyst    = False
        in_descent_hyst  = False

        cfg = self.cfg   # local ref for speed

        for i in range(len(df)):
            raw_phase, raw_conf, raw_reason = self._classify_row(
                float(a_agl[i]),      float(a_gndspd[i]),  float(a_ias[i]),
                float(a_vspd[i]),     float(a_torque[i]),  float(a_fflow[i]),
                float(a_ng[i]),       float(a_pitch[i]),   float(a_roll[i]),
                float(a_latac[i]),    float(a_normac[i]),
                float(a_ias_d[i]),    float(a_vspd_d[i]),  float(a_gspd_d[i]),
                float(a_torq_d[i]),   float(a_altstab[i]), float(a_altd[i]),
                float(a_energy[i]),   float(a_energy_d[i]),
                float(a_afcs[i]),     float(a_gpsq[i]),
                in_airborne_hyst, in_climb_hyst, in_descent_hyst,
                current_phase or "GROUND",
                sm_corrected=(hold_count > 0),
            )

            # ── State machine validation (v2 logic unchanged)
            sm_corrected_this_row = False
            if current_phase is None:
                validated = raw_phase
                hold_count = 0
            else:
                allowed = VALID_TRANSITIONS.get(current_phase,
                                                list(VALID_TRANSITIONS.keys()))
                if raw_phase in allowed:
                    validated  = raw_phase
                    hold_count = 0
                else:
                    hold_count += 1
                    sm_corrected_this_row = True
                    if hold_count >= MAX_HOLD:
                        validated  = raw_phase
                        hold_count = 0
                    else:
                        validated = current_phase

            # ── V3: Update hysteresis state based on validated phase and sensors
            # Airborne hysteresis: enter when AGL > enter threshold, exit when < exit
            if a_agl[i] > cfg['liftoff_agl_enter']:
                in_airborne_hyst = True
            elif a_agl[i] < cfg['liftoff_agl_exit']:
                in_airborne_hyst = False

            # Climb hysteresis: enter when VSpd > climb_rate_enter
            if a_vspd[i] > cfg['climb_rate_enter']:
                in_climb_hyst = True
            elif a_vspd[i] < cfg['climb_rate_exit']:
                in_climb_hyst = False

            # Descent hysteresis: enter when VSpd < -descent_rate_enter
            if a_vspd[i] < -cfg['descent_rate_enter']:
                in_descent_hyst = True
            elif a_vspd[i] > -cfg['descent_rate_exit']:
                in_descent_hyst = False

            # ── Apply SM correction penalty to confidence AFTER validation
            final_conf = raw_conf
            if sm_corrected_this_row:
                final_conf = max(0.0, raw_conf - 0.2)  # SM penalty

            phases.append(validated)
            confidences.append(round(final_conf, 3))
            reasons.append(raw_reason[:120])   # hard cap at 120 chars
            current_phase = validated

        df['FLIGHT_PHASE']      = phases
        df['PHASE_CONFIDENCE']  = confidences
        df['PHASE_REASON']      = reasons

        print("  [6/8] Smoothing phase labels...")
        df = self._smooth_phases(df)

        print("  [7/8] Post-pass audit...")
        df = self._post_audit(df)

        print("  [8/8] Computing phase stability index...")
        df = self._compute_phase_stability(df)

        # ── V3: Debug output
        if self.debug_mode:
            n_total    = len(df)
            n_low_conf = (df['PHASE_CONFIDENCE'] < 0.5).sum()
            print(f"\n  [DEBUG] Rows with low confidence (<0.5): "
                  f"{n_low_conf} / {n_total} ({n_low_conf/n_total*100:.1f}%)")
            print(f"  [DEBUG] Mean confidence: {df['PHASE_CONFIDENCE'].mean():.3f}")
            print(f"  [DEBUG] Mean stability : {df['PHASE_STABILITY'].mean():.3f}")
            print(f"  [DEBUG] Event persistence stats:")
            all_ev = df['FLIGHT_EVENT'].str.split('|').explode()
            for ev, cnt in all_ev.value_counts().items():
                if ev != 'NORMAL':
                    print(f"           {ev:30s}: {cnt:4d} rows")

        return df


# ─────────────────────────────────────────────────────────────────────────────
#  V3 PRIVATE HELPERS  (module-level, not class methods for speed)
# ─────────────────────────────────────────────────────────────────────────────

def _confidence(witnesses_hit: int, witnesses_possible: int,
                gps_ok: float, sm_corrected: bool) -> float:
    """
    Compute normalised confidence score for a classified row.

    Formula
    -------
    base      = witnesses_hit / max(witnesses_possible, 1)
    gps_pen   = -0.15 if GPS quality is degraded
    sm_pen    = -0.20 if this call is made while hold_count > 0
                 (SM correction penalty applied externally after return)

    The SM penalty is applied EXTERNALLY in the classify() loop after
    _classify_row returns, so sm_corrected here is the state at call time
    (whether the *previous* row was corrected), not the current row.

    Returns float ∈ [0.0, 1.0]
    """
    base    = witnesses_hit / max(witnesses_possible, 1)
    gps_pen = 0.15 if (gps_ok < 1.0) else 0.0
    sm_pen  = 0.10 if sm_corrected    else 0.0
    return float(np.clip(base - gps_pen - sm_pen, 0.0, 1.0))


def _reason(phase: str, tags: List[str]) -> str:
    """
    Build the PHASE_REASON audit string.

    Format:  "PHASE | tag1 + tag2 + tag3"
    Example: "CLIMB | VSpdClimb + TorqHigh + AltRise"

    Capped at 120 characters for column storage efficiency.
    """
    if not tags:
        return phase
    tag_str = ' + '.join(tags)
    result  = f"{phase} | {tag_str}"
    return result[:120]


# ─────────────────────────────────────────────────────────────────────────────
#  UTILITY  (unchanged from v2)
# ─────────────────────────────────────────────────────────────────────────────

def _append_event(series: pd.Series, event: str) -> pd.Series:
    def _add(val):
        if val == 'NORMAL':      return event
        if event in val:          return val
        return f"{val}|{event}"
    return series.map(_add)


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all expected columns exist; fill with 0 if missing."""
    expected = [
        'VSpd', 'IAS', 'GndSpd', 'Pitch', 'Roll', 'LatAc', 'NormAc',
        'E1 FFlow', 'E1 Torq', 'E1 NP', 'E1 NG', 'E1 ITT',
        'AltGPS', 'AltB', 'AltMSL', 'TAS', 'HDG', 'TRK',
        'WndSpd', 'WndDr', 'WptDst', 'AfcsOn',
        'GPSfix', 'HAL', 'VAL',
    ]
    for col in expected:
        if col not in df.columns:
            df[col] = 0.0
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  FILE I/O  (updated to write 3 new columns)
# ─────────────────────────────────────────────────────────────────────────────

def process_flight_log(input_file: str,
                       output_file: str,
                       aircraft_type: str = "Generic",
                       debug_mode: bool   = False) -> None:
    print(f"\n{'='*60}")
    print(f"  FOQA Flight Phase Classifier -- v3.0")
    print(f"  Aircraft : {aircraft_type}")
    print(f"  Input    : {input_file}")
    print(f"  Output   : {output_file}")
    print(f"  Debug    : {'ON' if debug_mode else 'off'}")
    print(f"{'='*60}\n")

    with open(input_file, 'r') as f:
        header_line1 = f.readline()
        header_line2 = f.readline()
        header_line3 = f.readline().strip()

    df_raw = pd.read_csv(input_file, skiprows=2, dtype=str)
    df_raw.columns = df_raw.columns.str.strip()
    original_columns = df_raw.columns.tolist()

    numeric_cols = [
        'VSpd', 'IAS', 'GndSpd', 'Pitch', 'Roll', 'LatAc', 'NormAc',
        'E1 FFlow', 'E1 Torq', 'E1 NP', 'E1 NG', 'E1 ITT',
        'AltGPS', 'AltB', 'AltMSL', 'TAS', 'HDG', 'TRK',
        'WndSpd', 'WndDr', 'WptDst', 'AfcsOn', 'GPSfix', 'HAL', 'VAL',
    ]
    df_work = df_raw.copy()
    for col in numeric_cols:
        if col in df_work.columns:
            df_work[col] = pd.to_numeric(df_work[col], errors='coerce').fillna(0.0)

    df_work = ensure_columns(df_work)

    classifier = FOQAFlightClassifier(aircraft_type=aircraft_type,
                                       debug_mode=debug_mode)
    df_work = classifier.classify(df_work)

    # Copy all four result columns back
    df_raw['FLIGHT_PHASE']     = df_work['FLIGHT_PHASE']
    df_raw['FLIGHT_EVENT']     = df_work['FLIGHT_EVENT']
    df_raw['PHASE_CONFIDENCE'] = df_work['PHASE_CONFIDENCE']
    df_raw['PHASE_REASON']     = df_work['PHASE_REASON']
    df_raw['PHASE_STABILITY']  = df_work['PHASE_STABILITY']

    # ── Summary
    print("\n--- Phase Distribution -------------------------------------------")
    for phase, count in df_raw['FLIGHT_PHASE'].value_counts().sort_index().items():
        pct  = count / len(df_raw) * 100
        mask = df_raw['FLIGHT_PHASE'] == phase
        mean_conf = df_raw.loc[mask, 'PHASE_CONFIDENCE'].mean()
        print(f"  {phase:22s}: {count:5d} rows  ({pct:5.1f}%)  "
              f"conf={mean_conf:.2f}")

    print("\n--- Special Events -----------------------------------------------")
    all_events = df_raw['FLIGHT_EVENT'].str.split('|').explode()
    non_normal  = all_events[all_events != 'NORMAL']
    if non_normal.empty:
        print("  None detected")
    else:
        import re as _re
        for label, cnt in non_normal.value_counts().items():
            sev_m = _re.search(r'_S([123])$', label)
            sev   = f"  [S{sev_m.group(1)}]" if sev_m else ""
            base  = label[:sev_m.start()] if sev_m else label
            print(f"  {base:35s}{sev}  {cnt:4d} rows")

    print("\n--- Quality Metrics ----------------------------------------------")
    print(f"  Mean confidence : {df_raw['PHASE_CONFIDENCE'].astype(float).mean():.3f}")
    print(f"  Mean stability  : {df_raw['PHASE_STABILITY'].astype(float).mean():.3f}")
    dyn = df_work.attrs.get('dynamic_thresholds', {})
    if dyn:
        print(f"  Dynamic climb rate   : {dyn.get('climb_rate', 'N/A'):.1f} fpm")
        print(f"  Dynamic descent rate : {dyn.get('descent_rate', 'N/A'):.1f} fpm")
        print(f"  Dynamic cruise AGL   : {dyn.get('cruise_agl', 'N/A'):.1f} ft")

    # ── Write output
    print(f"\nWriting output to: {output_file}")
    with open(output_file, 'w') as f:
        f.write(header_line1)
        f.write(header_line2)
        # V3: four new columns appended to header
        f.write(header_line3 +
                ',FLIGHT_PHASE,FLIGHT_EVENT,PHASE_CONFIDENCE,PHASE_REASON,PHASE_STABILITY\n')
        for idx, row in df_raw.iterrows():
            orig  = df_raw.loc[idx, original_columns].tolist()
            line  = ','.join(str(x) if pd.notna(x) else '' for x in orig)
            f.write(f"{line},"
                    f"{row['FLIGHT_PHASE']},"
                    f"{row['FLIGHT_EVENT']},"
                    f"{row['PHASE_CONFIDENCE']},"
                    f"\"{row['PHASE_REASON']}\","   # quoted: contains commas
                    f"{row['PHASE_STABILITY']}\n")

    print(f"\nOK Done.\n")


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='FOQA Flight Phase Classifier v3.0 – Cessna 208 family')
    parser.add_argument('input_file',  help='Input Garmin G1000/G950 CSV')
    parser.add_argument('output_file', help='Output CSV with phase labels')
    parser.add_argument('--aircraft', '-a',
                        default='Generic',
                        choices=list(AIRCRAFT_CONFIGS.keys()),
                        help='Aircraft type')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode (print dynamic thresholds, '
                             'confidence stats, event persistence)')
    args = parser.parse_args()
    process_flight_log(args.input_file, args.output_file,
                       args.aircraft, debug_mode=args.debug)


if __name__ == "__main__":
    main()
