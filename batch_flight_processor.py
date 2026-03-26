#!/usr/bin/env python3
"""
Batch Flight Phase Processor - v4.0 FDA/Aering Compatible
==========================================================
Processes G1000/G950 CSV flight logs through FOQAFlightClassifier v4.0 and writes
classified output with all seven result columns:

    FLIGHT_PHASE     Phase label (CRUISE, APPROACH, FINAL APPROACH, TAKEOFF, LANDING, ...)
                     Uses FDA/Aering standard naming:
                     - PRE-FLIGHT (ground before taxi)
                     - TAXI OUT (taxi to runway)
                     - TAKEOFF (takeoff roll + rotation)
                     - INITIAL CLIMB (first climb + go-arounds)
                     - CLIMB (sustained climb)
                     - CRUISE (level flight + maneuvering)
                     - DESCENT (descent from cruise)
                     - APPROACH (approach > 500ft AGL)
                     - FINAL APPROACH (final approach Ã¢ÂÂ¤ 500ft AGL)
                     - LANDING (flare + touchdown + rollout)
                     - TAXI IN (taxi after landing)
    
    FLIGHT_EVENT     Pipe-separated severity-tagged events (LGN000_S3|...)
                     or NORMAL if no exceedance detected.
    PHASE_CONFIDENCE Per-row confidence score 0.0-1.0
    PHASE_REASON     Witness tags explaining the phase decision
    PHASE_STABILITY  Rolling 10-row same-phase agreement ratio
    AGL              Above Ground Level altitude (ft), barometric-derived
    isGearGround     1 when AGL == 0 (gear on ground), 0 when airborne

After classification each file's event windows are extracted via
classifier.extract_event_windows() Ã¢ÂÂ one record per discrete event
occurrence: start row, end row, duration, peak value, severity.

Usage
-----
    python batch_flight_processor.py input/ output/
    python batch_flight_processor.py input/ output/ --aircraft "Cessna 208B Grand Caravan EX"
    python batch_flight_processor.py input/ output/ --flatten --debug
    python batch_flight_processor.py --list-aircraft
"""

import csv
import json
import os
import argparse
import re
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

# Ã¢ÂÂÃ¢ÂÂ Classifier Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
try:
    from flight_phase_classifier import (
        FOQAFlightClassifier,
        AIRCRAFT_CONFIGS,
        FLIGHT_EVENT_DEFINITIONS,
        ensure_columns,
    )
except ImportError as e:
    raise SystemExit(
        f"\n[ERROR] Could not import flight_phase_classifier.py: {e}\n"
        "Ensure flight_phase_classifier.py is in the same directory.\n"
    )

# Ã¢ÂÂÃ¢ÂÂ Optional registration map Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
try:
    from aircraft_registration_map import get_aircraft_type_from_path
    REGISTRATION_MAP_AVAILABLE = True
except ImportError:
    REGISTRATION_MAP_AVAILABLE = False

# Ã¢ÂÂÃ¢ÂÂ Numeric columns the classifier expects Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
NUMERIC_COLUMNS = [
    'VSpd', 'IAS', 'GndSpd', 'Pitch', 'Roll', 'LatAc', 'NormAc',
    'E1 FFlow', 'E1 Torq', 'E1 NP', 'E1 NG', 'E1 ITT',
    'AltGPS', 'AltB', 'AltInd', 'AltMSL', 'TAS', 'HDG', 'TRK',
    'WndSpd', 'WndDr', 'WptDst', 'AfcsOn',
    'GPSfix', 'HAL', 'VAL',
]

# Columns appended to every output CSV
CLASSIFIER_COLUMNS = [
    'FLIGHT_PHASE', 'FLIGHT_EVENT', 'SEVERITY',
    'PHASE_CONFIDENCE', 'PHASE_REASON', 'PHASE_STABILITY',
    'AGL', 'isGearGround',
]


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

class BatchFlightProcessor:

    def __init__(self, input_dir: str, output_dir: str,
                 aircraft_type: str = 'Auto',
                 debug: bool = False):
        self.input_dir     = Path(input_dir)
        self.output_dir    = Path(output_dir)
        self.aircraft_type = aircraft_type
        self.debug         = debug

        self.processing_log: list = []
        self.summary_stats = {
            'total_files'       : 0,
            'processed_files'   : 0,
            'skipped_files'     : 0,
            'failed_files'      : 0,
            'total_rows'        : 0,
            'phase_distribution': {},
            'event_distribution': {},   # label Ã¢ÂÂ occurrence count
            'mean_confidence'   : [],   # per-file values; averaged at end
            'mean_stability'    : [],
        }

    # Ã¢ÂÂÃ¢ÂÂ Aircraft type resolution Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

    def detect_aircraft_type(self, csv_file: Path) -> str:
        """
        Priority order:
          1. Registration-to-type map (folder / filename match)
          2. airframe_name field in G1000 CSV header line 1
          3. Fuzzy match against AIRCRAFT_CONFIGS keys
          4. Generic fallback
        """
        if REGISTRATION_MAP_AVAILABLE:
            ac = get_aircraft_type_from_path(str(csv_file))
            if ac:
                return ac

        try:
            with open(csv_file, 'r', encoding='latin-1', errors='replace') as f:
                first_line = f.readline()

            # G1000 header: key=value or key="value"
            m = re.search(r'airframe_name="?([^",\n]+)"?', first_line, re.I)
            if m:
                airframe = m.group(1).strip()
                if airframe in AIRCRAFT_CONFIGS:
                    return airframe
                lower = airframe.lower()
                for known in AIRCRAFT_CONFIGS:
                    if known.lower() in lower or lower in known.lower():
                        return known
        except Exception:
            pass

        return 'Generic'

    # Ã¢ÂÂÃ¢ÂÂ Already-classified check Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

    @staticmethod
    def _is_classified(header_line3: str) -> bool:
        return 'FLIGHT_PHASE' in header_line3

    # Ã¢ÂÂÃ¢ÂÂ Single file Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

    def process_single_file(self, input_file: Path,
                             output_file: Path,
                             aircraft_type: str) -> bool:
        try:
            # Ã¢ÂÂÃ¢ÂÂ Guard: never overwrite the source file Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            if input_file.resolve() == output_file.resolve():
                raise ValueError(
                    f"input and output are the same file Ã¢ÂÂ "
                    f"refusing to overwrite source data: {input_file}"
                )

            # Ã¢ÂÂÃ¢ÂÂ Read 3-line G1000 header Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            with open(input_file, 'r', encoding='latin-1', errors='replace') as f:
                header_line1 = f.readline()
                header_line2 = f.readline()
                header_line3 = f.readline().rstrip('\n')

            # Ã¢ÂÂÃ¢ÂÂ Skip already-classified files Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            if self._is_classified(header_line3):
                return self._handle_already_classified(input_file, aircraft_type)

            # Ã¢ÂÂÃ¢ÂÂ Load original data as pure strings Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            # dtype=str keeps every value exactly as recorded.
            # df_raw is NEVER written to after this point.
            df_raw = pd.read_csv(input_file, skiprows=2, dtype=str,
                                 encoding='latin-1', on_bad_lines='skip')
            df_raw.columns = df_raw.columns.str.strip()
            original_columns = df_raw.columns.tolist()

            if df_raw.empty:
                raise ValueError("No data rows after header.")

            # Ã¢ÂÂÃ¢ÂÂ Guard: refuse pre-classified input Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            collision = [c for c in CLASSIFIER_COLUMNS if c in original_columns]
            if collision:
                raise ValueError(
                    f"File already contains classifier columns {collision}. "
                    f"Use the original source CSV."
                )

            # Ã¢ÂÂÃ¢ÂÂ Drop duplicate timestamps into a new frame (df_raw unchanged) Ã¢ÂÂ
            time_cols = [c for c in original_columns if c in ('Lcl Date', 'Lcl Time')]
            if len(time_cols) == 2:
                df_dedup = df_raw.drop_duplicates(subset=time_cols, keep='last') \
                                 .reset_index(drop=True)
                dropped = len(df_raw) - len(df_dedup)
                if dropped:
                    print(f"    [INFO] Dropped {dropped} duplicate timestamp row(s)")
            else:
                df_dedup = df_raw.reset_index(drop=True)

            # Ã¢ÂÂÃ¢ÂÂ Numeric working copy for classification Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            df_work = df_dedup.copy()
            for col in NUMERIC_COLUMNS:
                if col in df_work.columns:
                    df_work[col] = pd.to_numeric(
                        df_work[col], errors='coerce').fillna(0.0)
            df_work = ensure_columns(df_work)
            df_work = df_work.reset_index(drop=True)

            # Ã¢ÂÂÃ¢ÂÂ Classify Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            # Extract departure ICAO from filename: log_YYMMDD_HHMMSS_ICAO.csv
            _stem_parts = input_file.stem.split('_')
            dep_icao    = _stem_parts[-1].upper() if len(_stem_parts) >= 4 else ''
            clf     = FOQAFlightClassifier(
                aircraft_type=aircraft_type, debug_mode=self.debug,
                dep_icao=dep_icao)
            df_work = clf.classify(df_work)
            df_work['AGL'] = df_work['AGL'].round(1)
            # Ã¢ÂÂÃ¢ÂÂ Build output: original strings + classifier results Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            # df_dedup (and df_raw) are only read here Ã¢ÂÂ never written to.
            # df_out is a brand-new frame; no column of df_dedup is mutated.
            df_out = pd.concat(
                [df_dedup[original_columns].reset_index(drop=True),
                 df_work[CLASSIFIER_COLUMNS].reset_index(drop=True)],
                axis=1,
            )

            # Ã¢ÂÂÃ¢ÂÂ Extract structured event windows Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            event_windows = clf.extract_event_windows(df_work)

            # Ã¢ÂÂÃ¢ÂÂ Quality metrics (all reads from df_work) Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            mean_conf  = float(df_work['PHASE_CONFIDENCE'].astype(float).mean())
            mean_stab  = float(df_work['PHASE_STABILITY'].astype(float).mean())
            dyn_thresh = df_work.attrs.get('dynamic_thresholds', {})

            # Ã¢ÂÂÃ¢ÂÂ Aggregate stats Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            phase_counts = df_work['FLIGHT_PHASE'].value_counts().to_dict()

            event_counts: dict = {}
            for ew in event_windows:
                lbl = ew['label']
                event_counts[lbl] = event_counts.get(lbl, 0) + 1

            self.summary_stats['processed_files'] += 1
            self.summary_stats['total_rows']      += len(df_out)
            self.summary_stats['mean_confidence'].append(mean_conf)
            self.summary_stats['mean_stability'].append(mean_stab)

            for phase, count in phase_counts.items():
                self.summary_stats['phase_distribution'][phase] = (
                    self.summary_stats['phase_distribution'].get(phase, 0) + count)
            for lbl, cnt in event_counts.items():
                self.summary_stats['event_distribution'][lbl] = (
                    self.summary_stats['event_distribution'].get(lbl, 0) + cnt)

            # Ã¢ÂÂÃ¢ÂÂ Write output CSV (input_file never opened for writing) Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            output_file.parent.mkdir(parents=True, exist_ok=True)
            self._write_classified_csv(
                output_file, header_line1, header_line2, header_line3,
                df_out, original_columns)

            # Ã¢ÂÂÃ¢ÂÂ Console summary Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            self._print_file_summary(
                phase_counts, event_windows, mean_conf, mean_stab,
                dyn_thresh, len(df_out))

            self.processing_log.append({
                'file'              : input_file.name,
                'aircraft_type'     : aircraft_type,
                'status'            : 'success',
                'rows'              : len(df_out),
                'phases'            : phase_counts,
                'event_occurrences' : event_counts,
                'event_windows'     : event_windows,
                'mean_confidence'   : round(mean_conf, 3),
                'mean_stability'    : round(mean_stab, 3),
                'dynamic_thresholds': dyn_thresh,
            })
            return True

        except Exception:
            self.summary_stats['failed_files'] += 1
            err = traceback.format_exc().strip().splitlines()[-1]
            print(f"  [FAILED] {input_file.name}: {err}")
            if self.debug:
                traceback.print_exc()
            self.processing_log.append({
                'file'         : input_file.name,
                'aircraft_type': aircraft_type,
                'status'       : 'failed',
                'error'        : err,
            })
            return False

    # Ã¢ÂÂÃ¢ÂÂ Already-classified handler Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

    def _handle_already_classified(self, input_file: Path,
                                    aircraft_type: str) -> bool:
        print(f"  [SKIP] already classified: {input_file.name}")
        try:
            df = pd.read_csv(input_file, skiprows=2, dtype=str,
                             encoding='latin-1', on_bad_lines='skip')
            df.columns = df.columns.str.strip()
            rows = len(df)

            phase_counts = df['FLIGHT_PHASE'].value_counts().to_dict() \
                           if 'FLIGHT_PHASE' in df.columns else {}
            mean_conf = float(pd.to_numeric(
                df['PHASE_CONFIDENCE'], errors='coerce').mean()) \
                if 'PHASE_CONFIDENCE' in df.columns else 0.0
            mean_stab = float(pd.to_numeric(
                df['PHASE_STABILITY'], errors='coerce').mean()) \
                if 'PHASE_STABILITY' in df.columns else 0.0

            event_counts: dict = {}
            if 'FLIGHT_EVENT' in df.columns:
                ev_series = df['FLIGHT_EVENT'].str.split('|').explode()
                ev_series = ev_series[ev_series.notna() & (ev_series != 'NORMAL')]
                for lbl, cnt in ev_series.value_counts().items():
                    event_counts[str(lbl)] = int(cnt)

            self.summary_stats['skipped_files'] += 1
            self.summary_stats['total_rows']    += rows
            if not pd.isna(mean_conf):
                self.summary_stats['mean_confidence'].append(mean_conf)
            if not pd.isna(mean_stab):
                self.summary_stats['mean_stability'].append(mean_stab)
            for phase, count in phase_counts.items():
                self.summary_stats['phase_distribution'][phase] = (
                    self.summary_stats['phase_distribution'].get(phase, 0) + count)

        except Exception:
            rows, phase_counts, event_counts = 0, {}, {}
            mean_conf = mean_stab = 0.0

        self.processing_log.append({
            'file'              : input_file.name,
            'aircraft_type'     : aircraft_type,
            'status'            : 'skipped',
            'rows'              : rows,
            'phases'            : phase_counts,
            'event_occurrences' : event_counts,
            'event_windows'     : [],
            'mean_confidence'   : round(mean_conf, 3),
            'mean_stability'    : round(mean_stab, 3),
        })
        return True

    # Ã¢ÂÂÃ¢ÂÂ CSV writer Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

    @staticmethod
    def _write_classified_csv(output_file: Path,
                               header_line1: str, header_line2: str,
                               header_line3: str,
                               df_out: pd.DataFrame,
                               original_columns: list) -> None:
        """
        Write classified CSV preserving the 3-line G1000 header.

        df_out must already contain original_columns + CLASSIFIER_COLUMNS.
        It is a new frame built by the caller Ã¢ÂÂ no original frame is mutated.
        Uses csv.writer for correct quoting (PHASE_REASON may contain commas).
        """
        out_cols = original_columns + CLASSIFIER_COLUMNS
        rows_df  = df_out[out_cols].fillna('')

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            f.write(header_line1 if header_line1.endswith('\n') else header_line1 + '\n')
            f.write(header_line2 if header_line2.endswith('\n') else header_line2 + '\n')
            f.write(header_line3 + ',' + ','.join(CLASSIFIER_COLUMNS) + '\n')

            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            for row in rows_df.itertuples(index=False, name=None):
                writer.writerow(row)

    # Ã¢ÂÂÃ¢ÂÂ Per-file console summary Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

    def _print_file_summary(self, phase_counts: dict, event_windows: list,
                             mean_conf: float, mean_stab: float,
                             dyn_thresh: dict, n_rows: int) -> None:
        top = sorted(phase_counts.items(), key=lambda x: -x[1])[:5]
        print(f"    Phases  : {'  '.join(f'{ph}={c}' for ph, c in top)}")
        print(f"    Quality : conf={mean_conf:.2f}  stab={mean_stab:.2f}  rows={n_rows:,}")

        if event_windows:
            # Group by base event name
            ev_groups: dict = {}
            for ew in event_windows:
                b = ew['event']
                s = ew.get('severity', 1)
                if b not in ev_groups:
                    ev_groups[b] = {'count': 0, 'max_sev': 0}
                ev_groups[b]['count']  += 1
                ev_groups[b]['max_sev'] = max(ev_groups[b]['max_sev'], s)
            summary = ', '.join(
                f"{b}ÃÂ{d['count']}(S{d['max_sev']})"
                for b, d in sorted(ev_groups.items()))
            print(f"    Events  : {summary}")
            for ew in event_windows:
                peak = f"  peak={ew['peak_value']:.2f}" \
                       if ew.get('peak_value') is not None else ''
                print(f"      [{ew['label']:42s}] "
                      f"rows {ew['start_row']}Ã¢ÂÂ{ew['end_row']} "
                      f"({ew['duration_sec']}s){peak}")
        else:
            print(f"    Events  : none")

        if self.debug and dyn_thresh:
            print(f"    DynThr  : "
                  f"climb={dyn_thresh.get('climb_rate', '?'):.0f}fpm  "
                  f"desc={dyn_thresh.get('descent_rate', '?'):.0f}fpm  "
                  f"cruiseAGL={dyn_thresh.get('cruise_agl', '?'):.0f}ft")

    # Ã¢ÂÂÃ¢ÂÂ File discovery Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

    # G1000 filename pattern: log_YYMMDD_HHMMSS_ICAO.csv
    # Files that don't match are not flight logs Ã¢ÂÂ skip silently.
    _G1000_PATTERN = re.compile(
        r'^log_\d{6}_\d{6}_[A-Z0-9]{4}\.csv$', re.IGNORECASE
    )

    def find_csv_files(self, pattern: str = '**/*.csv') -> list:
        files = list(self.input_dir.glob(pattern))
        result = []
        for f in files:
            if 'BATCH_SUMMARY' in f.name.upper():
                continue
            if not self._G1000_PATTERN.match(f.name):
                print(f"  [SKIP] No ICAO in filename: {f.name}")
                continue
            result.append(f)
        return sorted(result)

    # Ã¢ÂÂÃ¢ÂÂ Batch entry point Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

    def process_batch(self, preserve_structure: bool = True,
                      pattern: str = '**/*.csv') -> None:
        csv_files = self.find_csv_files(pattern)
        self.summary_stats['total_files'] = len(csv_files)

        if not csv_files:
            print(f"[INFO] No CSV files found in: {self.input_dir}")
            return

        print(f"\nFound {len(csv_files)} file(s). Starting batch...\n")

        current_folder    = None
        folder_file_count = 0

        for csv_file in csv_files:
            try:
                folder_label = str(csv_file.parent.relative_to(self.input_dir))
                if folder_label == '.':
                    folder_label = 'Root'
            except ValueError:
                folder_label = csv_file.parent.name

            if folder_label != current_folder:
                if current_folder is not None:
                    print(f"\n  Ã¢ÂÂ {current_folder} Ã¢ÂÂ {folder_file_count} file(s) done")
                    print('  ' + 'Ã¢ÂÂ' * 54)
                print(f"\n  Folder: {folder_label}")
                current_folder    = folder_label
                folder_file_count = 0

            ac_type = (self.detect_aircraft_type(csv_file)
                       if self.aircraft_type == 'Auto' else self.aircraft_type)

            if preserve_structure:
                output_file = self.output_dir / csv_file.relative_to(self.input_dir)
            else:
                output_file = self.output_dir / csv_file.name

            print(f"\n  Ã¢ÂÂº {csv_file.name}  [{ac_type}]")
            if self.process_single_file(csv_file, output_file, ac_type):
                folder_file_count += 1

        if current_folder is not None:
            print(f"\n  Ã¢ÂÂ {current_folder} Ã¢ÂÂ {folder_file_count} file(s) done")

        self._print_terminal_summary()
        self._write_summary_report()

    # Ã¢ÂÂÃ¢ÂÂ Terminal summary Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

    def _print_terminal_summary(self) -> None:
        stats = self.summary_stats
        total = stats['total_rows']
        mc    = stats['mean_confidence']
        ms    = stats['mean_stability']
        mean_conf = sum(mc) / len(mc) if mc else 0.0
        mean_stab = sum(ms) / len(ms) if ms else 0.0

        print(f"\n{'='*60}")
        print(f"  BATCH COMPLETE")
        print(f"  Files      : {stats['processed_files']} processed  "
              f"{stats['skipped_files']} skipped  "
              f"{stats['failed_files']} failed  "
              f"/ {stats['total_files']} total")
        print(f"  Rows       : {total:,}")
        print(f"  Confidence : mean={mean_conf:.3f}")
        print(f"  Stability  : mean={mean_stab:.3f}")
        print(f"{'='*60}")

        if stats['phase_distribution']:
            print("\n  Phase Distribution:")
            for phase, count in sorted(stats['phase_distribution'].items()):
                pct = count / total * 100 if total else 0
                print(f"    {phase:25s}: {count:8,d}  ({pct:5.1f}%)")

        if stats['event_distribution']:
            print("\n  Event Occurrences (all flights):")
            for lbl, cnt in sorted(stats['event_distribution'].items(),
                                   key=lambda x: -x[1]):
                m    = re.search(r'_S([123])$', lbl)
                sev  = int(m.group(1)) if m else 0
                base = lbl[:m.start()] if m else lbl
                edef = FLIGHT_EVENT_DEFINITIONS.get(base, {})
                desc = edef.get(f's{sev}', {}).get('description',
                       edef.get('description', ''))[:50]
                print(f"    {lbl:45s}: {cnt:4d}  {desc}")

        failed = [e for e in self.processing_log if e['status'] == 'failed']
        if failed:
            print(f"\n  Ã¢ÂÂ   Failed ({len(failed)}):")
            for e in failed:
                print(f"    Ã¢ÂÂ¢ {e['file']}: {e.get('error', '')}")
        print()

    # Ã¢ÂÂÃ¢ÂÂ Report writer Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

    def _write_summary_report(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stats = self.summary_stats
        total = stats['total_rows']
        now   = datetime.now()

        mc = stats['mean_confidence']
        ms = stats['mean_stability']
        mean_conf = sum(mc) / len(mc) if mc else 0.0
        mean_stab = sum(ms) / len(ms) if ms else 0.0

        # Ã¢ÂÂÃ¢ÂÂ JSON Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
        def _native(obj):
            if isinstance(obj, (np.integer,)):  return int(obj)
            if isinstance(obj, (np.floating,)):  return float(obj)
            if isinstance(obj, dict):            return {k: _native(v) for k, v in obj.items()}
            if isinstance(obj, list):            return [_native(i) for i in obj]
            return obj

        log_path = self.output_dir / 'processing_log.json'
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(_native({
                'timestamp'       : now.isoformat(),
                'input_directory' : str(self.input_dir),
                'output_directory': str(self.output_dir),
                'summary': {
                    'total_files'      : stats['total_files'],
                    'processed_files'  : stats['processed_files'],
                    'skipped_files'    : stats['skipped_files'],
                    'failed_files'     : stats['failed_files'],
                    'total_rows'       : total,
                    'mean_confidence'  : round(mean_conf, 3),
                    'mean_stability'   : round(mean_stab, 3),
                    'phase_distribution': stats['phase_distribution'],
                    'event_distribution': stats['event_distribution'],
                },
                'files': self.processing_log,
            }), f, indent=2)

        # Ã¢ÂÂÃ¢ÂÂ Text Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
        SEP  = '=' * 70
        SEP2 = '-' * 70
        report_path = self.output_dir / 'BATCH_SUMMARY_REPORT.txt'

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(SEP + '\n')
            f.write('BATCH FLIGHT PHASE CLASSIFICATION REPORT\n')
            f.write('Classifier : FOQAFlightClassifier\n')
            f.write(SEP + '\n\n')
            f.write(f'Date/Time        : {now.strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Input Directory  : {self.input_dir}\n')
            f.write(f'Output Directory : {self.output_dir}\n\n')

            f.write('PROCESSING SUMMARY\n')
            f.write(SEP + '\n')
            f.write(f'Files found      : {stats["total_files"]}\n')
            f.write(f'Processed        : {stats["processed_files"]}\n')
            f.write(f'Skipped          : {stats["skipped_files"]} (already classified)\n')
            f.write(f'Failed           : {stats["failed_files"]}\n')
            f.write(f'Total rows       : {total:,}\n')
            f.write(f'Mean confidence  : {mean_conf:.3f}\n')
            f.write(f'Mean stability   : {mean_stab:.3f}\n\n')

            failed = [e for e in self.processing_log if e['status'] == 'failed']
            if failed:
                f.write('FAILED FILES\n' + SEP + '\n')
                for e in failed:
                    f.write(f'  {e["file"]}\n')
                    f.write(f'    Error: {e.get("error", "Unknown")}\n')
                f.write('\n')

            f.write('OVERALL PHASE DISTRIBUTION\n' + SEP + '\n')
            for phase, count in sorted(stats['phase_distribution'].items()):
                pct = count / total * 100 if total else 0
                f.write(f'  {phase:25s}: {count:9,d} rows  ({pct:5.1f}%)\n')
            f.write('\n')

            if stats['event_distribution']:
                f.write('EVENT OCCURRENCES (all flights)\n' + SEP + '\n')
                for lbl, cnt in sorted(stats['event_distribution'].items(),
                                        key=lambda x: -x[1]):
                    m    = re.search(r'_S([123])$', lbl)
                    sev  = int(m.group(1)) if m else 0
                    base = lbl[:m.start()] if m else lbl
                    edef = FLIGHT_EVENT_DEFINITIONS.get(base, {})
                    desc = edef.get(f's{sev}', {}).get('description',
                           edef.get('description', ''))
                    f.write(f'  {lbl:45s}: {cnt:4d} occurrences\n')
                    if desc:
                        f.write(f'    {desc}\n')
                f.write('\n')

            f.write('\nINDIVIDUAL FLIGHT DETAILS\n' + SEP + '\n\n')
            for entry in self.processing_log:
                f.write(f'File     : {entry["file"]}\n')
                f.write(f'Aircraft : {entry["aircraft_type"]}\n')

                if entry['status'] == 'failed':
                    f.write(f'Status   : FAILED\n')
                    f.write(f'Error    : {entry.get("error", "Unknown")}\n\n')
                    f.write(SEP2 + '\n\n')
                    continue

                rows  = entry.get('rows', 0)
                label = 'SKIPPED (already classified)' \
                        if entry['status'] == 'skipped' else 'SUCCESS'
                f.write(f'Status   : {label}\n')
                f.write(f'Rows     : {rows:,}\n')
                f.write(f'Confidence (mean) : {entry.get("mean_confidence", 0):.3f}\n')
                f.write(f'Stability  (mean) : {entry.get("mean_stability",  0):.3f}\n')

                dyn = entry.get('dynamic_thresholds', {})
                if dyn:
                    f.write('Dynamic thresholds:\n')
                    f.write(f'  Climb rate   : {dyn.get("climb_rate",   "N/A"):.1f} fpm\n')
                    f.write(f'  Descent rate : {dyn.get("descent_rate", "N/A"):.1f} fpm\n')
                    f.write(f'  Cruise AGL   : {dyn.get("cruise_agl",   "N/A"):.1f} ft\n')

                phases = entry.get('phases', {})
                if phases:
                    f.write('Phases:\n')
                    for ph, cnt in sorted(phases.items(), key=lambda x: -x[1]):
                        pct = cnt / rows * 100 if rows else 0
                        f.write(f'  {ph:25s}: {cnt:6d}  ({pct:5.1f}%)\n')

                ews = entry.get('event_windows', [])
                if ews:
                    f.write('Events (discrete occurrences):\n')
                    for ew in ews:
                        peak = (f"  peak={ew['peak_value']:.2f}"
                                if ew.get('peak_value') is not None else '')
                        base = ew['event']
                        sev  = ew.get('severity', 1)
                        edef = FLIGHT_EVENT_DEFINITIONS.get(base, {})
                        desc = edef.get(f's{sev}', {}).get(
                               'description', '')[:60]
                        f.write(
                            f'  [{ew["label"]:42s}] '
                            f'rows {ew["start_row"]:5d}Ã¢ÂÂ{ew["end_row"]:5d} '
                            f'({ew["duration_sec"]:3d}s){peak}\n')
                        if desc:
                            f.write(f'    {desc}\n')
                else:
                    f.write('Events: none\n')

                f.write('\n' + SEP2 + '\n\n')

        print(f'\n  Reports written:')
        print(f'    {report_path}')
        print(f'    {log_path}')


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
#  CLI
# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def main():
    parser = argparse.ArgumentParser(
        description='Batch FOQA Flight Phase Classifier v4.0 (FDA/Aering)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Directory layouts
-----------------
Single folder:          input/flight_001.csv
Multi-aircraft folders: input/PK-SNO/flight_001.csv
                        input/PK-SNE/flight_002.csv

Phase Names (FDA/Aering Standard)
----------------------------------
PRE-FLIGHT, TAXI OUT, TAKEOFF, INITIAL CLIMB, CLIMB, CRUISE,
DESCENT, APPROACH, FINAL APPROACH, LANDING, TAXI IN

"""
)

    parser.add_argument('input_dir',  nargs='?', help='Input directory')
    parser.add_argument('output_dir', nargs='?', help='Output directory')
    parser.add_argument('--aircraft', '-a', default='Auto',
                        help='Force aircraft type (default: Auto-detect)')
    parser.add_argument('--flatten',  action='store_true',
                        help='Write all files flat Ã¢ÂÂ no subfolder mirror')
    parser.add_argument('--pattern',  default='**/*.csv',
                        help='Glob pattern (default: **/*.csv)')
    parser.add_argument('--debug',    action='store_true',
                        help='Enable classifier debug output')
    parser.add_argument('--list-aircraft',      action='store_true',
                        help='Print aircraft configurations and exit')
    parser.add_argument('--show-registrations', action='store_true',
                        help='Print registration map and exit')

    args = parser.parse_args()

    if args.list_aircraft:
        print('\nAvailable Aircraft Configurations')
        print('=' * 60)
        for ac, cfg in AIRCRAFT_CONFIGS.items():
            print(f'\n{ac}:')
            for k, v in cfg.items():
                print(f'  {k:<35s}: {v}')
        return

    if args.show_registrations:
        if REGISTRATION_MAP_AVAILABLE:
            from aircraft_registration_map import print_registration_summary
            print_registration_summary()
        else:
            print('[ERROR] aircraft_registration_map.py not found.')
        return

    if not args.input_dir or not args.output_dir:
        parser.error('input_dir and output_dir are required.')
    if not os.path.isdir(args.input_dir):
        raise SystemExit(f'[ERROR] Input directory not found: {args.input_dir}')
    os.makedirs(args.output_dir, exist_ok=True)

    BatchFlightProcessor(
        input_dir     = args.input_dir,
        output_dir    = args.output_dir,
        aircraft_type = args.aircraft,
        debug         = args.debug,
    ).process_batch(
        preserve_structure = not args.flatten,
        pattern            = args.pattern,
    )


if __name__ == '__main__':
    main()
