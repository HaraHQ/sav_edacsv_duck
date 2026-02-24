#!/usr/bin/env python3

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import argparse

AIRCRAFT_CONFIGS: Dict[str, Dict] = {
    "Cessna 208 Caravan": {
        # ROTATION/CLIMB
        "rotation_ias"          : 58.0,
        "climb_torque_min"      : 1200.0,
        "climb_rate_threshold"  : 400.0,    # static fallback; adaptive overrides
        # GROUND
        "definitely_airborne_ias": 55.0,
        "liftoff_agl"           : 30.0,     # static fallback
        # LAND
        "flare_agl"             : 50.0,
        "touchdown_agl"         : 15.0,
        # ENGINE
        "idle_fflow_max"        : 80.0,
        "takeoff_torque_min"    : 1100.0,
        # CRUISE
        "cruise_fflow_min"      : 120.0,
        "cruise_fflow_max"      : 350.0,
        "steep_turn_bank"       : 45.0,
        "hard_landing_g"        : 1.8,
        "high_wind_landing_kts" : 15.0,
        "cruise_agl_min"        : 1000.0,   # static fallback
        "climb_rate_enter"      : 450.0,    # fpm – stricter than static threshold
        "climb_rate_exit"       : 300.0,    # fpm – looser than enter
        # DESCENT 
        "descent_rate_enter"    : 450.0,    # fpm downward to START descent
        "descent_rate_exit"     : 250.0,    # fpm – looser exit
        # AIRBORNE 
        "liftoff_agl_enter"     : 40.0,     # ft
        "liftoff_agl_exit"      : 20.0,     # ft
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
    },
}


EVENT_PERSISTENCE: Dict[str, int] = {
    'GO_AROUND'          : 3,   # seconds – rapid power + climb recovery
    'REJECTED_TAKEOFF'   : 3,   # seconds – must be decelerating consistently
    'UNSTABLE_APPROACH'  : 5,   # seconds – brief speed deviation ≠ unstable
    'UNSTABLE_DEPARTURE' : 5,
    'UNSTABLE_CIRCUIT'   : 4,
    'HARD_LANDING'       : 2,   # g-spike – brief but real; 2 rows minimum
}

 # machine state

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

def safe_num(series: pd.Series, fill: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors='coerce').fillna(fill)

def require_persistence(mask: pd.Series, min_duration: int) -> pd.Series:
    """
    Design rationale
    ----------------
    A single-row sensor spike (e.g. a 2g NormAc transient from a pothole on
    the taxiway) should not trigger HARD_LANDING.  A genuine hard landing
    event will hold the g-load above threshold for multiple consecutive rows.

    Implementation uses a rolling sum window of size `min_duration`.
    If the sum equals `min_duration`, all rows in that window satisfied the
    condition continuously — so the LAST row of the window is confirmed.
    We then back-fill the confirmed True value to the window START using
    a backward rolling max, so the entire run is marked True, not just
    the final row.

    """
    if min_duration <= 1:
        return mask.copy()

    int_mask = mask.astype(int)

    rolling_sum   = int_mask.rolling(window=min_duration,
                                      min_periods=min_duration).sum()
    confirmed_end = (rolling_sum >= min_duration)
    rev_max   = (confirmed_end.iloc[::-1]
                              .rolling(window=min_duration, min_periods=1)
                              .max()
                              .iloc[::-1])
    confirmed = rev_max.astype(bool)
    confirmed.index = mask.index   # restore original index alignment
    return confirmed


class FOQAFlightClassifier:
    """
    Key architectural decisions
    ------------------------------------------------
    * Multi-witness rule: at minimum 2 independent parameters must agree.
    * Energy-state vector: torque + IAS + VSpd normalised to 0–1.
    * Dynamic AGL: gradient interpolation from departure to destination.
    * GPS quality gate: degraded GPS reduces confidence but does not halt.
    * Separate event column: FLIGHT_EVENT never overwrites FLIGHT_PHASE.
    """

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

    def compute_derived(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        if 'dt' not in df.columns:
            if 'Lcl Date' in df.columns and 'Lcl Time' in df.columns:
                datetime_col = pd.to_datetime(df['Lcl Date'] + ' ' + df['Lcl Time'], errors='coerce')
                df['dt'] = datetime_col.diff().dt.total_seconds().replace(0, 1).fillna(1)
            else:
                df['dt'] = 1.0

        window = 5   # 1-Hz data assumption

        def deriv(col):
            # True derivative: change in value divided by change in time (dt)
            return (df[col].diff() / df['dt']).rolling(window=window, center=True, min_periods=1).mean()

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

        # ── V2: GPS quality gate (unchanged thresholds)
        gps_ok            = (df['GPSfix'] >= 3)
        hal_ok            = (df['HAL']    <  0.3)
        val_ok            = (df['VAL']    <  150)
        df['GPS_quality'] = (gps_ok & hal_ok & val_ok).astype(int)

        # ── V2: Engine state flags (unchanged)
        df['fflow_idle']  = (df['E1 FFlow'] < self.cfg['idle_fflow_max']).astype(int)
        df['ng_high']     = (df['E1 NG']    > self.cfg['idle_ng_max']).astype(int)

        return df

    # ── 2. AGL COMPUTATION  (V3: true gradient replaces flat step model)

    def compute_agl(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Dynamic ground elevation reference – robust to sloped runways.

        V2 strategy (preserved):
        * Best altitude source: GPS → Baro → MSL.
        * Departure elevation = median of 10 lowest GPS altitudes while GndSpd < 40.
        * Destination elevation = same, from last 3 minutes.
        * Peak-based split: before peak uses dep_elev, after peak uses dest_elev.
        * AGL clamp: GndSpd < 40 and AGL < 0 → force AGL = 0.

        V3 upgrade: True linear gradient
        ---------------------------------
        V2 used a flat reference (dep_elev before peak, dest_elev after peak),
        creating a step discontinuity at the peak.

        V3 builds a linearly interpolated ground reference across the ENTIRE
        flight using np.linspace(dep_elev, dest_elev, n_rows).

        This means:
        - AGL increases smoothly as the aircraft gains terrain clearance
          during climb over rising terrain.
        - AGL decreases smoothly as the destination sits lower than departure.
        - The step discontinuity at the peak is eliminated entirely.
        - Sloped runway robustness is preserved: both anchors still use the
          median-of-10-lowest method.

        Distance-weighted variant (when TRK + GndSpd available):
        If cumulative distance along track can be estimated (GndSpd integration),
        we weight the gradient by actual distance flown rather than row count.
        This is more accurate for variable-speed flights (climb slow, cruise fast).
        """
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
        """
        Compute per-flight adaptive thresholds from data percentiles.

        Rationale
        ---------
        Static thresholds assume average conditions.  A flight at high density
        altitude (DA) will have lower climb rates than sea-level operations.
        A heavy-cargo 208B will climb more slowly than an empty one.

        By calibrating to the actual VSpd distribution of each flight,
        the classifier automatically adjusts for:
        - DA effects on climb performance
        - Weight and CG variations
        - Engine condition trends over time

        Thresholds computed
        -------------------
        climb_rate    = 75th percentile of positive VSpd values.
                        This is the "normal climb" rate for this flight.
                        Only positive VSpd rows are included to exclude
                        descent and level flight from the sample.

        descent_rate  = 75th percentile of absolute negative VSpd values.
                        Same logic inverted for descent.

        cruise_agl    = 60th percentile of AGL during airborne rows
                        (IAS > 50 kts).  This captures the typical cruise
                        altitude band for this specific route.

        Fallback: if fewer than ADAPTIVE_MIN_ROWS are available for any
        computation, the static config value is used.

        Stored in: self._dyn  (read by _classify_row via scalar copies)
                   df.attrs['dynamic_thresholds']  (for external inspection)
        """
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

        # ── Cruise AGL: 60th pct of AGL while airborne (IAS > 50)
        air_mask     = df['IAS'] > 50
        agl_samples  = df.loc[air_mask, 'AGL']
        if len(agl_samples) >= MIN_ROWS:
            cruise_agl_dyn = float(np.percentile(agl_samples, 60))
            cruise_agl_dyn = max(cruise_agl_dyn, self.cfg['cruise_agl_min'] * 0.5)
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
        Scan flight data BEFORE phase classification and mark events.

        V2 events (all preserved):
            HARD_LANDING, GO_AROUND, REJECTED_TAKEOFF,
            UNSTABLE_APPROACH, UNSTABLE_DEPARTURE, UNSTABLE_CIRCUIT,
            STEEP_TURN, ENGINE_IDLE_DESCENT, HIGH_WIND_LANDING

        V3 addition: require_persistence() applied to critical events.
        Also includes strict 500ft Approach and 400ft Departure FOQA gates.
        """
        events = pd.Series(['NORMAL'] * len(df), index=df.index)

        # ── HARD LANDING
        hard_land_raw = (
            (df['NormAc_peak'] >= self.cfg['hard_landing_g']) &
            (df['AGL'] < 30) &
            (df['GndSpd'] > 30)
        )
        hard_land_mask = require_persistence(hard_land_raw, EVENT_PERSISTENCE['HARD_LANDING'])
        events[hard_land_mask] = _append_event(events[hard_land_mask], 'HARD_LANDING')

        # ── GO-AROUND
        go_around_raw = (
            (df['AGL'] < 300) &
            (df['Torq_deriv'] > 200) &
            (df['VSpd_deriv'] > 50) &
            (df['VSpd'] > -200)
        )
        go_around_mask = require_persistence(go_around_raw, EVENT_PERSISTENCE['GO_AROUND'])
        events[go_around_mask] = _append_event(events[go_around_mask], 'GO_AROUND')

        # ── REJECTED TAKEOFF
        rto_raw = (
            (df['GndSpd'] > 40) &
            (df['Torq_deriv'] < -200) &
            (df['GndSpd_deriv'] < -1.0) &
            (df['AGL'] < 30)
        )
        rto_mask = require_persistence(rto_raw, EVENT_PERSISTENCE['REJECTED_TAKEOFF'])
        events[rto_mask] = _append_event(events[rto_mask], 'REJECTED_TAKEOFF')

        # ── INSTABILITY EVENTS — context-separated
        peak_pos     = int(df['AGL'].argmax())
        is_dep_side  = pd.Series(False, index=df.index)
        is_arr_side  = pd.Series(False, index=df.index)
        is_dep_side.iloc[:peak_pos] = True
        is_arr_side.iloc[peak_pos:] = True

        vref_proxy  = self.cfg['rotation_ias'] + 5
        vclimb_min  = self.cfg['climb_rate_threshold']

        arr_ias_low      = df['IAS'] < (vref_proxy - 10)
        arr_ias_high     = df['IAS'] > (vref_proxy + 20)
        dep_ias_low      = df['IAS'] < (self.cfg['rotation_ias'] - 5)
        dep_ias_high     = df['IAS'] > (self.cfg['rotation_ias'] + 30)
        arr_vs_excess    = df['VSpd'] < -1200
        dep_vs_low       = df['VSpd'] < (vclimb_min * 0.5)
        arr_bank_excess  = df['Roll'].abs() > 10
        dep_bank_excess  = df['Roll'].abs() > 20
        arr_pwr_unstable = df['E1 Torq'] < 400
        dep_pwr_low      = df['E1 Torq'] < self.cfg['climb_torque_min'] * 0.7

        # ── APPROACH INSTABILITY SCORING ──
        ua_score = (
            (arr_ias_low | arr_ias_high).astype(int) +
            arr_vs_excess.astype(int) +
            arr_bank_excess.astype(int) +
            arr_pwr_unstable.astype(int)
        )
        
        # 1. Continuous Band Instability (Persistent instability from 1000ft to 50ft)
        ua_band_raw = (
            is_arr_side & (df['AGL'] <= 1000) & (df['AGL'] > 50) &
            (df['VSpd'] < -50) & (ua_score >= 2)
        )
        ua_band_mask = require_persistence(ua_band_raw, EVENT_PERSISTENCE['UNSTABLE_APPROACH'])

        # 2. Strict 500 ft AGL Gate (Snapshot at exactly 500ft)
        crossed_500ft = (df['AGL'].shift(1) > 500) & (df['AGL'] <= 500) & is_arr_side & (df['VSpd'] < -50)
        gate_failed_raw = crossed_500ft & (ua_score >= 1)
        gate_failed_mask = gate_failed_raw.rolling(window=5, min_periods=1).max().fillna(0).astype(bool)

        # Combine both detection methods
        ua_mask = ua_band_mask | gate_failed_mask
        events[ua_mask] = _append_event(events[ua_mask], 'UNSTABLE_APPROACH')

        # ── DEPARTURE INSTABILITY SCORING ──
        ud_score = (
            (dep_ias_low | dep_ias_high).astype(int) +
            dep_vs_low.astype(int) +
            dep_bank_excess.astype(int) +
            dep_pwr_low.astype(int)
        )
        
        # 1. Continuous Band Instability (Persistent instability from 30ft to 1500ft)
        ud_band_raw = (
            is_dep_side & (df['AGL'] <= 1500) & (df['AGL'] > 30) &
            (df['VSpd'] > -200) & (ud_score >= 2)
        )
        ud_band_mask = require_persistence(ud_band_raw, EVENT_PERSISTENCE['UNSTABLE_DEPARTURE'])

        # 2. Strict 400 ft AGL Departure Gate (Snapshot at exactly 400ft)
        crossed_400ft = (df['AGL'].shift(1) < 400) & (df['AGL'] >= 400) & is_dep_side & (df['VSpd'] > 50)
        dep_gate_failed_raw = crossed_400ft & (ud_score >= 1)
        dep_gate_failed_mask = dep_gate_failed_raw.rolling(window=5, min_periods=1).max().fillna(0).astype(bool)

        # Combine both detection methods
        ud_mask = ud_band_mask | dep_gate_failed_mask
        events[ud_mask] = _append_event(events[ud_mask], 'UNSTABLE_DEPARTURE')

        # ── UNSTABLE CIRCUIT ──
        uc_speed_bad = (df['IAS'] < (vref_proxy - 15)) | (df['IAS'] > (vref_proxy + 25))
        uc_vs_bad    = (df['VSpd'] < -1500) | (df['VSpd'] > 1500)
        uc_bank_bad  = df['Roll'].abs() > 30
        uc_score     = (uc_speed_bad.astype(int) + uc_vs_bad.astype(int) +
                        uc_bank_bad.astype(int))
        uc_raw = (
            (df['AGL'] >= 200) & (df['AGL'] <= 1500) &
            (~ua_mask) & (~ud_mask) & (uc_score >= 2)
        )
        uc_mask = require_persistence(uc_raw, EVENT_PERSISTENCE['UNSTABLE_CIRCUIT'])
        events[uc_mask] = _append_event(events[uc_mask], 'UNSTABLE_CIRCUIT')

        # ── STEEP TURN
        steep_mask = (df['Roll'].abs() > self.cfg['steep_turn_bank']) & (df['AGL'] > 200)
        events[steep_mask] = _append_event(events[steep_mask], 'STEEP_TURN')

        # ── ENGINE IDLE DESCENT
        idle_desc_raw = (
            (df['VSpd'] < -300) & (df['fflow_idle'] == 1) & (df['AGL'] > 500)
        )
        idle_desc_rolling = idle_desc_raw.rolling(window=30, min_periods=30).sum()
        events[idle_desc_rolling >= 30] = _append_event(
            events[idle_desc_rolling >= 30], 'ENGINE_IDLE_DESCENT')

        # ── HIGH WIND LANDING
        hw_mask = (
            (df['CrosswindComp'] > self.cfg['high_wind_landing_kts']) &
            (df['AGL'] < 500) & (df['GndSpd'] > 20)
        )
        events[hw_mask] = _append_event(events[hw_mask], 'HIGH_WIND_LANDING')

        df['FLIGHT_EVENT'] = events
        return df

    # ── 4. SINGLE-ROW CLASSIFIER  (V3: returns tuple, adds confidence + reason)

    def _classify_row(self,
                      # ── Positional scalars (all pre-extracted numpy floats)
                      agl, gndspd, ias, vspd, torque, fflow, ng,
                      pitch, roll, latac, normac,
                      ias_d, vspd_d, gspd_d, torq_d,
                      alt_stab, alt_deriv, energy, energy_d, afcs, gps_ok,
                      # ── V3: Hysteresis state flags (managed in classify loop)
                      in_airborne_hyst: bool,
                      in_climb_hyst:    bool,
                      in_descent_hyst:  bool,
                      # ── State machine context
                      prev_phase: str,
                      # ── V3: Whether last transition was SM-corrected (penalty)
                      sm_corrected: bool,
                      ) -> Tuple[str, float, str]:
        """
        Classify a single row using plain scalar arguments.

        V2 decision layers (all preserved, no logic removed):
        1. Ground-lock gate
        2. Go-Around interrupt
        3. Rotation / Initial Climb
        4. Landing band (Touchdown / Flare)
        5. Approach band
        6. Energy-state routing (Climb / Cruise / Descent / Level / Maneuvering)

        V3 changes:
        - Hysteresis flags (in_airborne_hyst, in_climb_hyst, in_descent_hyst)
          replace hard threshold crossings for airborne, climb, and descent
          entry/exit decisions. The actual threshold comparison is still here,
          but the RESULT depends on the hysteresis state tracked in the loop.
        - Returns (phase, confidence, reason) instead of just phase.
        - confidence: fraction of possible witnesses that were satisfied,
          with GPS and SM penalties applied.
        - reason: pipe-separated string of triggered witness tags, ≤120 chars.
        - Energy_State_deriv (energy_d) used to break CLIMB/CLIMBING FLIGHT
          and DESCENT/DESCENDING FLIGHT ties.
        """
        cfg  = self.cfg
        dyn  = self._dyn   # adaptive thresholds

        # ── Witness accumulators for confidence scoring
        witnesses_possible = 0
        witnesses_hit      = 0
        reason_tags: List[str] = []

        def W(hit: bool, tag: str) -> bool:
            """Record a witness check and return the bool."""
            nonlocal witnesses_possible, witnesses_hit
            witnesses_possible += 1
            if hit:
                witnesses_hit += 1
                reason_tags.append(tag)
            return hit

        # ─────────────────────────────────────────────────────────────────
        # LAYER 1 – GROUND LOCK  (v2 logic; hysteresis applied to AGL gate)
        # ─────────────────────────────────────────────────────────────────
        # V2: required IAS > definitely_airborne_ias AND AGL > liftoff_agl
        # V3: the AGL gate now uses hysteresis:
        #   - If NOT currently in airborne hyst: need AGL > liftoff_agl_ENTER
        #   - If already in airborne hyst:       only need AGL > liftoff_agl_EXIT
        # IAS gate is unchanged (no hysteresis — IAS is a clean witness).

        agl_enter_thr = cfg['liftoff_agl_enter']
        agl_exit_thr  = cfg['liftoff_agl_exit']
        agl_thr       = agl_exit_thr if in_airborne_hyst else agl_enter_thr

        is_ias_airborne = W(ias > cfg['definitely_airborne_ias'], 'IAS_FLY')
        is_agl_airborne = W(agl > agl_thr,                        'AGL_FLY')
        is_airborne     = is_ias_airborne and is_agl_airborne
        definitely_ground = not is_airborne

        if definitely_ground:
            # Sub-classify ground ops (v2 logic unchanged)
            if gndspd > 40 and prev_phase in ('APPROACH', 'FLARE', 'TOUCHDOWN',
                                               'ROLLOUT', 'DESCENDING FLIGHT'):
                conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
                return "ROLLOUT", conf, _reason("ROLLOUT", reason_tags)

            if (W(torque > cfg['takeoff_torque_min'], 'TorqHigh') and
                    W(gspd_d > 0.5, 'GspdAccel') and
                    gndspd > 15):
                conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
                return "TAKEOFF ROLL", conf, _reason("TAKEOFF ROLL", reason_tags)

            if gndspd > cfg['taxi_speed_threshold']:
                conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
                return "TAXI", conf, _reason("TAXI", reason_tags)

            conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
            return "GROUND", conf, _reason("GROUND", reason_tags)

        # ─────────────────────────────────────────────────────────────────
        # LAYER 2 – GO-AROUND  (v2 logic unchanged)
        # ─────────────────────────────────────────────────────────────────
        if (agl < 300 and
                W(torq_d > 200, 'TorqRise') and
                W(vspd_d > 50, 'VSpdRecov') and
                vspd > -200 and
                prev_phase in ('APPROACH', 'FLARE', 'TOUCHDOWN', 'DESCENDING FLIGHT')):
            conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
            return "GO-AROUND", conf, _reason("GO-AROUND", reason_tags)

        # ─────────────────────────────────────────────────────────────────
        # LAYER 3 – ROTATION / INITIAL CLIMB  (v2 logic unchanged)
        # ─────────────────────────────────────────────────────────────────
        if (agl < 300 and
                W(pitch > 2, 'PitchPos') and
                W(ias >= (cfg['rotation_ias'] - 5), 'IAS_Vr') and
                W(torque > cfg['climb_torque_min'], 'TorqClimb') and
                vspd > 0 and
                prev_phase in ('TAKEOFF ROLL', 'ROTATION', 'GROUND', 'TAXI')):
            conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
            if agl < 100:
                return "ROTATION", conf, _reason("ROTATION", reason_tags)
            return "INITIAL CLIMB", conf, _reason("INITIAL CLIMB", reason_tags)

        if (agl < 1000 and
                W(vspd > dyn['climb_rate'], 'VSpdClimb') and
                W(torque > cfg['climb_torque_min'], 'TorqClimb') and
                prev_phase in ('ROTATION', 'INITIAL CLIMB', 'TAKEOFF ROLL')):
            conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
            return "INITIAL CLIMB", conf, _reason("INITIAL CLIMB", reason_tags)

        # ─────────────────────────────────────────────────────────────────
        # LAYER 4 – LANDING BAND  (v2 logic unchanged)
        # ─────────────────────────────────────────────────────────────────
        if agl < cfg['touchdown_agl']:
            W(normac > 1.15, 'NormAcSpike')
            W(gndspd > 20,   'GndSpdOk')
            conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
            if gndspd > 40:
                return "ROLLOUT", conf, _reason("ROLLOUT", reason_tags)
            return "TOUCHDOWN", conf, _reason("TOUCHDOWN", reason_tags)

        if agl < cfg['flare_agl']:
            has_flare = W(pitch > 2, 'PitchFlare') and W(vspd > -400, 'VSpdArrest')
            conf      = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
            if has_flare:
                return "FLARE", conf, _reason("FLARE", reason_tags)
            return "APPROACH", conf, _reason("APPROACH", reason_tags)

        # ─────────────────────────────────────────────────────────────────
        # LAYER 5 – APPROACH BAND  (v2 logic unchanged)
        # ─────────────────────────────────────────────────────────────────
        if agl < 1500:
            desc_ok = W(vspd < -100, 'VSpdDesc') or (not gps_ok and alt_deriv < -50)
            ias_ok  = W(ias > (cfg['rotation_ias'] - 10), 'IAS_Apch')
            if desc_ok and ias_ok:
                conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
                return "APPROACH", conf, _reason("APPROACH", reason_tags)

        # ─────────────────────────────────────────────────────────────────
        # LAYER 6 – ENERGY-STATE ROUTING  (V3: hysteresis + energy_d tiebreaker)
        # ─────────────────────────────────────────────────────────────────

        # ── Climb detection with hysteresis
        # Enter: VSpd > climb_rate_enter (stricter)
        # Stay:  VSpd > climb_rate_exit  (looser — hysteresis gap)
        climb_thr     = cfg['climb_rate_exit'] if in_climb_hyst else cfg['climb_rate_enter']
        is_climbing   = W(vspd > climb_thr,              'VSpdClimb')
        has_climb_pwr = W(torque > cfg['climb_torque_min'], 'TorqHigh')
        alt_rising    = W(alt_deriv > 50,                'AltRise')
        # V3: energy slope as tiebreaker witness
        energy_building = W(energy_d > 0.005,            'EnergyUp')

        climb_score = is_climbing + has_climb_pwr + alt_rising
        if climb_score >= 2:
            conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
            # V3: energy_d breaks CLIMB vs CLIMBING FLIGHT tie
            # If energy is building and AGL is low → active CLIMB
            # If energy is flat/falling → transition to cruise → CLIMBING FLIGHT
            if agl < 3000 or prev_phase in ('INITIAL CLIMB', 'ROTATION'):
                return "CLIMB", conf, _reason("CLIMB", reason_tags)
            if energy_building or energy_d > 0.002:
                return "CLIMB", conf, _reason("CLIMB", reason_tags)
            return "CLIMBING FLIGHT", conf, _reason("CLIMBING FLIGHT", reason_tags)

        # ── Descent detection with hysteresis
        desc_thr      = cfg['descent_rate_exit'] if in_descent_hyst else cfg['descent_rate_enter']
        is_descending = W(vspd < -desc_thr,              'VSpdDesc')
        is_idle_pwr   = W(fflow < cfg['idle_fflow_max'], 'FFlowIdle')
        alt_falling   = W(alt_deriv < -50,               'AltFall')
        # V3: energy bleeding as tiebreaker
        energy_falling = W(energy_d < -0.005,            'EnergyDown')

        descent_score = is_descending + alt_falling + is_idle_pwr
        if descent_score >= 2:
            conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
            # V3: energy_d breaks DESCENT vs DESCENDING FLIGHT
            # Idle power + energy bleeding = clean idle descent (DESCENT)
            # Powered descent = DESCENDING FLIGHT
            if is_idle_pwr and (energy_falling or energy_d < -0.003):
                return "DESCENT", conf, _reason("DESCENT", reason_tags)
            return "DESCENDING FLIGHT", conf, _reason("DESCENDING FLIGHT", reason_tags)

        # ── Cruise / Level flight
        is_level       = W(abs(vspd) < 200,             'LevelVSpd')
        alt_stable     = W(alt_stab < 80,               'AltStable')
        afcs_on        = W(afcs == 1,                   'AFCS')
        in_cruise_band = W(agl > dyn['cruise_agl'],     'CruiseAlt')

        cruise_score = is_level + alt_stable + in_cruise_band + afcs_on
        if cruise_score >= 3:
            conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
            # V3: if energy is noticeably trending, prefer LEVEL FLIGHT over CRUISE
            if abs(energy_d) > 0.01:
                return "LEVEL FLIGHT", conf, _reason("LEVEL FLIGHT", reason_tags)
            return "CRUISE", conf, _reason("CRUISE", reason_tags)

        # ── Maneuvering (v2 logic unchanged)
        if (W(abs(roll) > 25, 'BankHigh') and W(latac > 0.15, 'LatAcHigh') and agl > 200):
            conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
            return "MANEUVERING", conf, _reason("MANEUVERING", reason_tags)

        # ── Level flight catch-all
        if is_level:
            conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected)
            return "LEVEL FLIGHT", conf, _reason("LEVEL FLIGHT", reason_tags)

        # ── Hold previous phase if nothing matched
        conf = _confidence(witnesses_hit, witnesses_possible, gps_ok, sm_corrected) * 0.5
        return prev_phase, conf, f"{prev_phase}|Hold"

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
        df = self.compute_derived(df)
        df = self.compute_agl(df)
        self.compute_adaptive_thresholds(df)
        df = self.detect_special_events(df)

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

        df = self._smooth_phases(df)
        df = self._post_audit(df)
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
    if not tags:
        return phase
    tag_str = ' + '.join(tags)
    result  = f"{phase} | {tag_str}"
    return result[:120]


# utility

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


# read/write input output

def process_flight_log(input_file: str,
                       output_file: str,
                       aircraft_type: str = "Generic",
                       debug_mode: bool   = False) -> None:
    print(f"\n{'='*60}")
    print(f"  FOQA Flight Phase Classifier  –  v3.0")
    print(f"  Aircraft : {aircraft_type}")
    print(f"  Input    : {input_file}")
    print(f"  Output   : {output_file}")
    print(f"  Debug    : {'ON' if debug_mode else 'off'}")
    print(f"{'='*60}\n")

    # Read Headers
    with open(input_file, 'r') as f:
        header_line1 = f.readline()
        header_line2 = f.readline()
        header_line3 = f.readline().strip()

    # Read Data
    df_raw = pd.read_csv(input_file, skiprows=2, dtype=str, encoding= 'latin1')
    df_raw.columns = df_raw.columns.str.strip()
    original_columns = df_raw.columns.tolist()

    numeric_cols = [
        'VSpd', 'IAS', 'GndSpd', 'Pitch', 'Roll', 'LatAc', 'NormAc',
        'E1 FFlow', 'E1 Torq', 'E1 NP', 'E1 NG', 'E1 ITT',
        'AltGPS', 'AltB', 'AltMSL', 'TAS', 'HDG', 'TRK',
        'WndSpd', 'WndDr', 'WptDst', 'AfcsOn', 'GPSfix', 'HAL', 'VAL',
    ]
    df_work = df_raw.copy()

    # ── 1. TIME PARSING FIX ──
    # Create a reliable time delta (dt) to handle 1-Hz lag or dropped frames
    if 'Lcl Date' in df_work.columns and 'Lcl Time' in df_work.columns:
        df_work['Datetime'] = pd.to_datetime(df_work['Lcl Date'] + ' ' + df_work['Lcl Time'], errors='coerce')
        # Calculate difference in seconds. Replace 0s with 1s to prevent division-by-zero errors later.
        df_work['dt'] = df_work['Datetime'].diff().dt.total_seconds().replace(0, 1).fillna(1)
    else:
        df_work['dt'] = 1.0  # Fallback to strict 1-Hz assumption if time columns are missing

    # ── 2. INTERPOLATION FIX ──
    for col in numeric_cols:
        if col in df_work.columns:
            df_work[col] = pd.to_numeric(df_work[col], errors='coerce')
            # Interpolate up to 3 seconds of missing data to prevent false 0.0 drops
            df_work[col] = df_work[col].interpolate(method='linear', limit=3).fillna(0.0)

    df_work = ensure_columns(df_work)

    # Run Classifier
    classifier = FOQAFlightClassifier(aircraft_type=aircraft_type,
                                       debug_mode=debug_mode)
    df_work = classifier.classify(df_work)

    # Copy all result columns back to the raw dataframe
    df_raw['FLIGHT_PHASE']     = df_work['FLIGHT_PHASE']
    df_raw['FLIGHT_EVENT']     = df_work['FLIGHT_EVENT']
    df_raw['PHASE_CONFIDENCE'] = df_work['PHASE_CONFIDENCE']
    df_raw['PHASE_REASON']     = df_work['PHASE_REASON']
    df_raw['PHASE_STABILITY']  = df_work['PHASE_STABILITY']

    # ── Summary Prints ──
    print("\n─── Phase Distribution ───────────────────────────────────────")
    for phase, count in df_raw['FLIGHT_PHASE'].value_counts().sort_index().items():
        pct  = count / len(df_raw) * 100
        mask = df_raw['FLIGHT_PHASE'] == phase
        mean_conf = df_raw.loc[mask, 'PHASE_CONFIDENCE'].mean()
        print(f"  {phase:22s}: {count:5d} rows  ({pct:5.1f}%)  "
              f"conf={mean_conf:.2f}")

    print("\n─── Special Events ───────────────────────────────────────────")
    all_events = df_raw['FLIGHT_EVENT'].str.split('|').explode()
    for ev, cnt in all_events.value_counts().items():
        if ev != 'NORMAL':
            print(f"  {ev:35s}: {cnt:4d} rows")

    print(f"\n─── Quality Metrics ──────────────────────────────────────────")
    print(f"  Mean confidence : {df_raw['PHASE_CONFIDENCE'].astype(float).mean():.3f}")
    print(f"  Mean stability  : {df_raw['PHASE_STABILITY'].astype(float).mean():.3f}")
    dyn = df_work.attrs.get('dynamic_thresholds', {})
    if dyn:
        print(f"  Dynamic climb rate   : {dyn.get('climb_rate', 'N/A'):.1f} fpm")
        print(f"  Dynamic descent rate : {dyn.get('descent_rate', 'N/A'):.1f} fpm")
        print(f"  Dynamic cruise AGL   : {dyn.get('cruise_agl', 'N/A'):.1f} ft")

    # ── Write output ──
    print(f"\nWriting output to: {output_file}")
    with open(output_file, 'w') as f:
        f.write(header_line1)
        f.write(header_line2)
        f.write(header_line3 +
                ',FLIGHT_PHASE,FLIGHT_EVENT,PHASE_CONFIDENCE,PHASE_REASON,PHASE_STABILITY\n')
        for idx, row in df_raw.iterrows():
            orig  = df_raw.loc[idx, original_columns].tolist()
            line  = ','.join(str(x) if pd.notna(x) else '' for x in orig)
            f.write(f"{line},"
                    f"{row['FLIGHT_PHASE']},"
                    f"{row['FLIGHT_EVENT']},"
                    f"{row['PHASE_CONFIDENCE']},"
                    f"\"{row['PHASE_REASON']}\","
                    f"{row['PHASE_STABILITY']}\n")

    print(f"\n✓ Done.\n")

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