#!/usr/bin/env python3
"""
Batch Flight Phase Processor - v4.0 FDA/Aering Compatible (with Split-Log Merging)
==================================================================================
Processes G1000/G950 CSV flight logs through FOQAFlightClassifier v4.0 and writes
classified output with all seven result columns.

This version seamlessly stitches fragmented flight logs (split during a single
flight) while extracting advanced routing (ICAO) and flight duration metrics.

    FLIGHT_PHASE     Phase label (CRUISE, APPROACH, FINAL APPROACH, TAKEOFF, LANDING, ...)
                     Uses FDA/Aering standard naming:
                     - PRE-FLIGHT (ground before taxi)
                     - TAXI OUT (taxi to runway)
                     - TAKEOFF (takeoff roll + rotation)
                     - INITIAL CLIMB (first climb + go-arounds)
                     - CLIMB (sustained climb)
                     - CRUISE (level flight + maneuvering)
                     - DESCENT (descent from cruise)
                     - APPROACH (approach > 500ft AltAAL)
                     - FINAL APPROACH (final approach ≤ 500ft AltAAL)
                     - LANDING (flare + touchdown + rollout)
                     - TAXI IN (taxi after landing)
    
    FLIGHT_EVENT     Pipe-separated severity-tagged events (LGN000_S3|...)
                     or NORMAL if no exceedance detected.
    SEVERITY         Maximum severity integer (0-3) for the row
    PHASE_CONFIDENCE Per-row confidence score 0.0-1.0
    PHASE_REASON     Witness tags explaining the phase decision
    PHASE_STABILITY  Rolling 10-row same-phase agreement ratio
    AltAAL           Above Ground Level altitude (ft), barometric-derived
    isGearGround     1 when AltAAL == 0 (gear on ground), 0 when airborne

Usage
-----
    python batch_flight_processor.py input/ output/
    python batch_flight_processor.py input/ output/ --aircraft "Cessna 208B Grand Caravan EX"
    python batch_flight_processor.py input/ output/ --flatten --debug
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

# ── Classifier ────────────────────────────────────────────────────────────
try:
    from flight_phase_classifier_v2 import (
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

# ── Optional registration map ──────────────────────────────────────────────
try:
    from aircraft_registration_map import get_aircraft_type_from_path
    REGISTRATION_MAP_AVAILABLE = True
except ImportError:
    REGISTRATION_MAP_AVAILABLE = False

# ── Numeric columns the classifier expects ──────────────────────────────────
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
    'AltAAL', 'isGearGround',
]


# ────────────────────────────────────────────────────────────────────────────

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
            'event_distribution': {},   
            'mean_confidence'   : [],   
            'mean_stability'    : [],
        }

    # ── Aircraft type resolution ──────────────────────────────────────────────

    def detect_aircraft_type(self, csv_file: Path) -> str:
        if REGISTRATION_MAP_AVAILABLE:
            ac = get_aircraft_type_from_path(str(csv_file))
            if ac:
                return ac

        try:
            with open(csv_file, 'r', encoding='latin-1', errors='replace') as f:
                first_line = f.readline()

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

    # ── ICAO extraction from filename ─────────────────────────────────────────

    @staticmethod
    def _extract_icao_from_filename(filename: str) -> str:
        stem = Path(filename).stem
        parts = stem.split('_')
        if parts:
            last = parts[-1].upper()
            if re.fullmatch(r'[A-Z0-9]{4}', last):
                return last
        for token in parts:
            t = token.upper()
            if re.fullmatch(r'[A-Z]{4}', t):
                return t
        return ''

    # ── Already-classified check ──────────────────────────────────────────────

    @staticmethod
    def _is_classified(header_line3: str) -> bool:
        return 'FLIGHT_PHASE' in header_line3

    # ── Single file ───────────────────────────────────────────────────────────

    def process_single_file(self, input_file: Path,
                             output_file: Path,
                             aircraft_type: str,
                             to_icao: str = 'UNKNOWN') -> bool:
        try:
            if input_file.resolve() == output_file.resolve():
                raise ValueError("input and output are the same file.")

            with open(input_file, 'r', encoding='latin-1', errors='replace') as f:
                header_line1 = f.readline()
                header_line2 = f.readline()
                header_line3 = f.readline().rstrip('\n')

            if self._is_classified(header_line3):
                return self._handle_already_classified(input_file, aircraft_type, to_icao)

            df_raw = pd.read_csv(input_file, skiprows=2, dtype=str,
                                 encoding='latin-1', on_bad_lines='skip')
            df_raw.columns = df_raw.columns.str.strip()
            original_columns = df_raw.columns.tolist()

            if df_raw.empty:
                raise ValueError("No data rows after header.")

            collision = [c for c in CLASSIFIER_COLUMNS if c in original_columns]
            if collision:
                raise ValueError(f"File already contains classifier columns {collision}.")

            time_cols = [c for c in original_columns if c in ('Lcl Date', 'Lcl Time')]
            if len(time_cols) == 2:
                df_dedup = df_raw.drop_duplicates(subset=time_cols, keep='last') \
                                 .reset_index(drop=True)
            else:
                df_dedup = df_raw.reset_index(drop=True)

            df_work = df_dedup.copy()
            for col in NUMERIC_COLUMNS:
                if col in df_work.columns:
                    df_work[col] = pd.to_numeric(
                        df_work[col], errors='coerce').fillna(0.0)
            df_work = ensure_columns(df_work)
            df_work = df_work.reset_index(drop=True)

            m_date = re.search(r'log_(\d{6})_', input_file.name, re.IGNORECASE)
            flight_date = str(m_date.group(1)) if m_date else ""
            dep_icao = self._extract_icao_from_filename(input_file.name)
            
            clf     = FOQAFlightClassifier(
                aircraft_type=aircraft_type, debug_mode=self.debug,
                dep_icao=dep_icao)
            df_work = clf.classify(df_work)
            df_work['AltAAL'] = df_work['AltAAL'].round(1)
            
            # Extract Times
            to_idx = -1
            ldg_idx = -1
            if 'FLIGHT_PHASE' in df_work.columns:
                phase_col = df_work['FLIGHT_PHASE'].iloc[:, 0] if isinstance(df_work['FLIGHT_PHASE'], pd.DataFrame) else df_work['FLIGHT_PHASE']
                phases_list = phase_col.astype(str).tolist()
                try: to_idx = phases_list.index('TAKEOFF')
                except ValueError: pass
                try: ldg_idx = len(phases_list) - 1 - phases_list[::-1].index('LANDING')
                except ValueError: pass

            t_start_str = ""
            t_end_str = ""
            duration_str = "00:00"

            if to_idx >= 0 and ldg_idx >= 0:
                if 'Lcl Time' in df_dedup.columns:
                    time_col = df_dedup['Lcl Time'].iloc[:, 0] if isinstance(df_dedup['Lcl Time'], pd.DataFrame) else df_dedup['Lcl Time']
                    time_list = time_col.astype(str).tolist()
                    t_start_str = ":".join((time_list[to_idx] if to_idx < len(time_list) else "").split(':')[:2])
                    t_end_str = ":".join((time_list[ldg_idx] if ldg_idx < len(time_list) else "").split(':')[:2])
                
                duration_sec = max(0, ldg_idx - to_idx)
                h, m = int(duration_sec // 3600), int((duration_sec % 3600) // 60)
                duration_str = f"{h:02d}:{m:02d}"

            df_out = pd.concat(
                [df_dedup[original_columns].reset_index(drop=True),
                 df_work[CLASSIFIER_COLUMNS].reset_index(drop=True)],
                axis=1,
            )

            event_windows = clf.extract_event_windows(df_work)
            mean_conf  = float(df_work['PHASE_CONFIDENCE'].astype(float).mean())
            mean_stab  = float(df_work['PHASE_STABILITY'].astype(float).mean())
            dyn_thresh = df_work.attrs.get('dynamic_thresholds', {})
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
                self.summary_stats['phase_distribution'][phase] = self.summary_stats['phase_distribution'].get(phase, 0) + count
            for lbl, cnt in event_counts.items():
                self.summary_stats['event_distribution'][lbl] = self.summary_stats['event_distribution'].get(lbl, 0) + cnt

            output_file.parent.mkdir(parents=True, exist_ok=True)
            self._write_classified_csv(output_file, header_line1, header_line2, header_line3, df_out, original_columns)
            self._print_file_summary(phase_counts, event_windows, mean_conf, mean_stab, dyn_thresh, len(df_out))

            self.processing_log.append({
                'file'              : input_file.name,
                'from_icao'         : dep_icao,
                'to_icao'           : to_icao if to_icao else None,
                'flight_date'       : flight_date,
                'takeoff_time'      : t_start_str,
                'landing_time'      : t_end_str,
                'flight_duration'   : duration_str,
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
            if self.debug: traceback.print_exc()
            self.processing_log.append({
                'file'         : input_file.name,
                'from_icao'    : self._extract_icao_from_filename(input_file.name),
                'to_icao'      : to_icao if to_icao else None,
                'aircraft_type': aircraft_type,
                'status'       : 'failed',
                'error'        : err,
            })
            return False

    # ── Already-classified handler ────────────────────────────────────────────

    def _handle_already_classified(self, input_file: Path,
                                    aircraft_type: str,
                                    to_icao: str = 'UNKNOWN') -> bool:
        print(f"  [SKIP] already classified: {input_file.name}")
        m_date = re.search(r'log_(\d{6})_', input_file.name, re.IGNORECASE)
        flight_date = str(m_date.group(1)) if m_date else ""
        dep_icao = self._extract_icao_from_filename(input_file.name)
                
        try:
            df = pd.read_csv(input_file, skiprows=2, dtype=str,
                             encoding='latin-1', on_bad_lines='skip')
            df.columns = df.columns.str.strip()
            rows = len(df)

            phase_counts = df['FLIGHT_PHASE'].value_counts().to_dict() if 'FLIGHT_PHASE' in df.columns else {}
            mean_conf = float(pd.to_numeric(df['PHASE_CONFIDENCE'], errors='coerce').mean()) if 'PHASE_CONFIDENCE' in df.columns else 0.0
            mean_stab = float(pd.to_numeric(df['PHASE_STABILITY'], errors='coerce').mean()) if 'PHASE_STABILITY' in df.columns else 0.0

            event_counts: dict = {}
            if 'FLIGHT_EVENT' in df.columns:
                ev_series = df['FLIGHT_EVENT'].str.split('|').explode()
                ev_series = ev_series[ev_series.notna() & (ev_series != 'NORMAL')]
                for lbl, cnt in ev_series.value_counts().items():
                    event_counts[str(lbl)] = int(cnt)
                    
            to_idx = -1; ldg_idx = -1
            t_start_str = ""; t_end_str = ""; duration_str = "00:00"
            
            if 'FLIGHT_PHASE' in df.columns and 'Lcl Time' in df.columns:
                phase_col = df['FLIGHT_PHASE'].iloc[:, 0] if isinstance(df['FLIGHT_PHASE'], pd.DataFrame) else df['FLIGHT_PHASE']
                phases_list = phase_col.astype(str).tolist()
                try: to_idx = phases_list.index('TAKEOFF')
                except ValueError: pass
                try: ldg_idx = len(phases_list) - 1 - phases_list[::-1].index('LANDING')
                except ValueError: pass
                
                if to_idx >= 0 and ldg_idx >= 0:
                    time_col = df['Lcl Time'].iloc[:, 0] if isinstance(df['Lcl Time'], pd.DataFrame) else df['Lcl Time']
                    time_list = time_col.astype(str).tolist()
                    t_start_str = ":".join((time_list[to_idx] if to_idx < len(time_list) else "").split(':')[:2])
                    t_end_str = ":".join((time_list[ldg_idx] if ldg_idx < len(time_list) else "").split(':')[:2])
                    duration_sec = max(0, ldg_idx - to_idx)
                    duration_str = f"{int(duration_sec // 3600):02d}:{int((duration_sec % 3600) // 60):02d}"

            self.summary_stats['skipped_files'] += 1
            self.summary_stats['total_rows']    += rows
            if not pd.isna(mean_conf): self.summary_stats['mean_confidence'].append(mean_conf)
            if not pd.isna(mean_stab): self.summary_stats['mean_stability'].append(mean_stab)
            for phase, count in phase_counts.items():
                self.summary_stats['phase_distribution'][phase] = self.summary_stats['phase_distribution'].get(phase, 0) + count
            for lbl, cnt in event_counts.items():
                self.summary_stats['event_distribution'][lbl] = self.summary_stats['event_distribution'].get(lbl, 0) + cnt

        except Exception:
            rows, phase_counts, event_counts = 0, {}, {}
            mean_conf = mean_stab = 0.0
            t_start_str = t_end_str = ""; duration_str = "00:00"

        self.processing_log.append({
            'file'              : input_file.name,
            'from_icao'         : dep_icao,
            'to_icao'           : to_icao if to_icao else None,
            'flight_date'       : flight_date,
            'takeoff_time'      : t_start_str,
            'landing_time'      : t_end_str,
            'flight_duration'   : duration_str,
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

    # ── Split-log detection methods (from V2) ────────────────────────────────

    @staticmethod
    def _boundary_info(csv_path: Path, position: str) -> dict:
        try:
            df = pd.read_csv(csv_path, skiprows=2, dtype=str, on_bad_lines='skip')
            df.columns = df.columns.str.strip()
            valid = df[df['Lcl Time'].str.strip() != ''].reset_index(drop=True)
            if valid.empty:
                return None

            def _f(row, col):
                try: return float(str(row.get(col, '')).strip() or '0')
                except (ValueError, TypeError): return 0.0

            if position == 'last':
                for i in range(len(valid) - 1, -1, -1):
                    row = valid.iloc[i]
                    if _f(row, 'IAS') > 0 or _f(row, 'GndSpd') > 0:
                        break
            else:
                for i in range(len(valid)):
                    row = valid.iloc[i]
                    if _f(row, 'IAS') > 0 or _f(row, 'GndSpd') > 0:
                        break

            from datetime import datetime as _dt
            dt = _dt.strptime(
                f'{row["Lcl Date"].strip()} {row["Lcl Time"].strip()}',
                '%Y-%m-%d %H:%M:%S')
            return {
                'dt'  : dt,
                'ias' : _f(row, 'IAS'),
                'gsp' : _f(row, 'GndSpd'),
                'alt' : _f(row, 'AltInd') or _f(row, 'AltB'),
                'date': row['Lcl Date'].strip(),
            }
        except Exception:
            return None

    @staticmethod
    def _is_split_continuation(file_a: Path, file_b: Path, max_gap_sec: int = 120) -> bool:
        end_a   = BatchFlightProcessor._boundary_info(file_a, 'last')
        start_b = BatchFlightProcessor._boundary_info(file_b, 'first')

        if end_a is None or start_b is None:
            return False
        if end_a['date'] != start_b['date']:
            return False

        gap = (start_b['dt'] - end_a['dt']).total_seconds()
        if not (0 < gap <= max_gap_sec):
            return False

        a_airborne = end_a['ias'] > 60 or end_a['gsp'] > 60
        b_airborne = start_b['ias'] > 60 or start_b['gsp'] > 60
        return a_airborne and b_airborne

    def _find_split_pairs(self, csv_files: list) -> dict:
        pairs: dict = {}   # secondary → primary
        skip:  set  = set()

        for i in range(len(csv_files) - 1):
            a = csv_files[i]
            b = csv_files[i + 1]
            if a.parent != b.parent: continue
            if a in skip: continue
            if self._is_split_continuation(a, b):
                pairs[b] = a
                skip.add(b)
                print(f"  [SPLIT] {a.name} + {b.name} → merged")
        return pairs

    # ── Merged-pair processor (V2 base + V2_1 extraction) ─────────────────────

    def process_split_pair(self, file_a: Path, file_b: Path,
                           output_file: Path, aircraft_type: str,
                           to_icao: str = 'UNKNOWN') -> bool:
        try:
            if file_a.resolve() == output_file.resolve() or file_b.resolve() == output_file.resolve():
                raise ValueError("output_file must differ from both input files.")

            with open(file_a, 'r', errors='replace') as f:
                header_line1 = f.readline()
                header_line2 = f.readline()
                header_line3 = f.readline().rstrip('\n')

            if self._is_classified(header_line3):
                print(f"  [SKIP] already classified (merged): {file_a.name}")
                self.summary_stats['skipped_files'] += 1
                return True

            df_a = pd.read_csv(file_a, skiprows=2, dtype=str, on_bad_lines='skip')
            df_b = pd.read_csv(file_b, skiprows=2, dtype=str, on_bad_lines='skip')
            df_a.columns = df_a.columns.str.strip()
            df_b.columns = df_b.columns.str.strip()

            if df_a.columns.tolist() != df_b.columns.tolist():
                raise ValueError(f"Column mismatch: {file_a.name} vs {file_b.name}")

            original_columns = df_a.columns.tolist()
            if [c for c in CLASSIFIER_COLUMNS if c in original_columns]:
                raise ValueError("Segments already contain classifier columns.")

            df_raw = pd.concat([df_a, df_b], ignore_index=True)

            time_cols = [c for c in original_columns if c in ('Lcl Date', 'Lcl Time')]
            if len(time_cols) == 2:
                df_dedup = df_raw.drop_duplicates(subset=time_cols, keep='last').reset_index(drop=True)
            else:
                df_dedup = df_raw.reset_index(drop=True)

            df_work = df_dedup.copy()
            for col in NUMERIC_COLUMNS:
                if col in df_work.columns:
                    df_work[col] = pd.to_numeric(df_work[col], errors='coerce').fillna(0.0)
            df_work = ensure_columns(df_work).reset_index(drop=True)

            m_date = re.search(r'log_(\d{6})_', file_a.name, re.IGNORECASE)
            flight_date = str(m_date.group(1)) if m_date else ""
            dep_icao = self._extract_icao_from_filename(file_a.name)

            clf = FOQAFlightClassifier(aircraft_type=aircraft_type, debug_mode=self.debug, dep_icao=dep_icao)
            df_work = clf.classify(df_work)
            df_work['AltAAL'] = df_work['AltAAL'].round(1)

            # V2_1 Time Extraction logic for merged logs
            to_idx = -1; ldg_idx = -1
            if 'FLIGHT_PHASE' in df_work.columns:
                phase_col = df_work['FLIGHT_PHASE'].iloc[:, 0] if isinstance(df_work['FLIGHT_PHASE'], pd.DataFrame) else df_work['FLIGHT_PHASE']
                phases_list = phase_col.astype(str).tolist()
                try: to_idx = phases_list.index('TAKEOFF')
                except ValueError: pass
                try: ldg_idx = len(phases_list) - 1 - phases_list[::-1].index('LANDING')
                except ValueError: pass

            t_start_str = ""; t_end_str = ""; duration_str = "00:00"
            if to_idx >= 0 and ldg_idx >= 0:
                if 'Lcl Time' in df_dedup.columns:
                    time_col = df_dedup['Lcl Time'].iloc[:, 0] if isinstance(df_dedup['Lcl Time'], pd.DataFrame) else df_dedup['Lcl Time']
                    time_list = time_col.astype(str).tolist()
                    t_start_str = ":".join((time_list[to_idx] if to_idx < len(time_list) else "").split(':')[:2])
                    t_end_str = ":".join((time_list[ldg_idx] if ldg_idx < len(time_list) else "").split(':')[:2])
                duration_sec = max(0, ldg_idx - to_idx)
                duration_str = f"{int(duration_sec // 3600):02d}:{int((duration_sec % 3600) // 60):02d}"

            df_out = pd.concat(
                [df_dedup[original_columns].reset_index(drop=True),
                 df_work[CLASSIFIER_COLUMNS].reset_index(drop=True)], axis=1)

            event_windows = clf.extract_event_windows(df_work)
            mean_conf = float(df_work['PHASE_CONFIDENCE'].astype(float).mean())
            mean_stab = float(df_work['PHASE_STABILITY'].astype(float).mean())
            dyn_thresh = df_work.attrs.get('dynamic_thresholds', {})
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
                self.summary_stats['phase_distribution'][phase] = self.summary_stats['phase_distribution'].get(phase, 0) + count
            for lbl, cnt in event_counts.items():
                self.summary_stats['event_distribution'][lbl] = self.summary_stats['event_distribution'].get(lbl, 0) + cnt

            output_file.parent.mkdir(parents=True, exist_ok=True)
            self._write_classified_csv(output_file, header_line1, header_line2, header_line3, df_out, original_columns)
            self._print_file_summary(phase_counts, event_windows, mean_conf, mean_stab, dyn_thresh, len(df_out))

            merged_name = f"{file_a.stem}+{file_b.stem}"
            self.processing_log.append({
                'file'              : merged_name,
                'from_icao'         : dep_icao,
                'to_icao'           : to_icao if to_icao else None,
                'flight_date'       : flight_date,
                'takeoff_time'      : t_start_str,
                'landing_time'      : t_end_str,
                'flight_duration'   : duration_str,
                'aircraft_type'     : aircraft_type,
                'status'            : 'success',
                'rows'              : len(df_out),
                'phases'            : phase_counts,
                'event_occurrences' : event_counts,
                'event_windows'     : event_windows,
                'mean_confidence'   : round(mean_conf, 3),
                'mean_stability'    : round(mean_stab, 3),
                'dynamic_thresholds': dyn_thresh,
                'split_merge'       : [file_a.name, file_b.name],
            })
            return True

        except Exception:
            self.summary_stats['failed_files'] += 1
            err = traceback.format_exc().strip().splitlines()[-1]
            print(f"  [FAILED] merge {file_a.name}+{file_b.name}: {err}")
            if self.debug: traceback.print_exc()
            self.processing_log.append({
                'file'         : f"{file_a.stem}+{file_b.stem}",
                'from_icao'    : self._extract_icao_from_filename(file_a.name),
                'to_icao'      : to_icao if to_icao else None,
                'aircraft_type': aircraft_type,
                'status'       : 'failed',
                'error'        : err,
                'split_merge'  : [file_a.name, file_b.name],
            })
            return False

    # ── CSV writer & console summary ───────────────────────────────────────────

    @staticmethod
    def _write_classified_csv(output_file: Path,
                               header_line1: str, header_line2: str,
                               header_line3: str,
                               df_out: pd.DataFrame,
                               original_columns: list) -> None:
        out_cols = original_columns + CLASSIFIER_COLUMNS
        rows_df  = df_out[out_cols].fillna('')

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            f.write(header_line1 if header_line1.endswith('\n') else header_line1 + '\n')
            f.write(header_line2 if header_line2.endswith('\n') else header_line2 + '\n')
            f.write(header_line3 + ',' + ','.join(CLASSIFIER_COLUMNS) + '\n')

            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            for row in rows_df.itertuples(index=False, name=None):
                writer.writerow(row)

    def _print_file_summary(self, phase_counts: dict, event_windows: list,
                             mean_conf: float, mean_stab: float,
                             dyn_thresh: dict, n_rows: int) -> None:
        top = sorted(phase_counts.items(), key=lambda x: x, reverse=True)[:5]
        print(f"    Phases  : {'  '.join(f'{ph}={c}' for ph, c in top)}")
        print(f"    Quality : conf={mean_conf:.2f}  stab={mean_stab:.2f}  rows={n_rows:,}")

        if event_windows:
            ev_groups: dict = {}
            for ew in event_windows:
                b = ew['event']
                s = ew.get('severity', 1)
                if b not in ev_groups:
                    ev_groups[b] = {'count': 0, 'max_sev': 0}
                ev_groups[b]['count']  += 1
                ev_groups[b]['max_sev'] = max(ev_groups[b]['max_sev'], s)
            summary = ', '.join(f"{b}×{d['count']}(S{d['max_sev']})" for b, d in sorted(ev_groups.items()))
            print(f"    Events  : {summary}")
            for ew in event_windows:
                peak = f"  peak={ew['peak_value']:.2f}" if ew.get('peak_value') is not None else ''
                print(f"      [{ew['label']:42s}] rows {ew['start_row']}–{ew['end_row']} ({ew['duration_sec']}s){peak}")
        else:
            print(f"    Events  : none")

        if self.debug and dyn_thresh:
            print(f"    DynThr  : climb={dyn_thresh.get('climb_rate', '?'):.0f}fpm  "
                  f"desc={dyn_thresh.get('descent_rate', '?'):.0f}fpm  "
                  f"cruiseAltAAL={dyn_thresh.get('cruise_AltAAL', '?'):.0f}ft")

    _G1000_PATTERN = re.compile(r'^log_\d{6}_\d{6}_[A-Z0-9]{4}\.csv$', re.IGNORECASE)

    def find_csv_files(self, pattern: str = '**/*.csv') -> list:
        files = list(self.input_dir.glob(pattern))
        result = []
        for f in files:
            if 'BATCH_SUMMARY' in f.name.upper(): continue
            if not self._G1000_PATTERN.match(f.name): continue
            result.append(f)
        return sorted(result)

    # ── Batch entry point (Merged V2 & V2_1) ───────────────────────────────────

    def process_batch(self, preserve_structure: bool = True, pattern: str = '**/*.csv') -> None:
        csv_files = self.find_csv_files(pattern)
        self.summary_stats['total_files'] = len(csv_files)

        if not csv_files:
            print(f"[INFO] No CSV files found in: {self.input_dir}")
            return

        print(f"\nFound {len(csv_files)} file(s). Starting batch...\n")

        _from_list = [self._extract_icao_from_filename(f.name) for f in csv_files]
        _to_map: dict = {}
        for _idx, _f in enumerate(csv_files):
            if _idx + 1 < len(csv_files):
                _to_map[_f] = _from_list[_idx + 1] 
            else:
                _to_map[_f] = None                   

        split_pairs      = self._find_split_pairs(csv_files)
        split_secondaries = set(split_pairs.keys())
        split_processed   = set()

        current_folder    = None
        folder_file_count = 0

        for csv_file in csv_files:
            try:
                folder_label = str(csv_file.parent.relative_to(self.input_dir))
                if folder_label == '.': folder_label = 'Root'
            except ValueError:
                folder_label = csv_file.parent.name

            if folder_label != current_folder:
                if current_folder is not None:
                    print(f"\n  ✓ {current_folder} — {folder_file_count} file(s) done\n  " + '─' * 54)
                print(f"\n  Folder: {folder_label}")
                current_folder    = folder_label
                folder_file_count = 0

            ac_type = self.detect_aircraft_type(csv_file) if self.aircraft_type == 'Auto' else self.aircraft_type

            if csv_file in split_secondaries:
                print(f"\n  ► {csv_file.name}  [merged into primary — skipped]")
                continue

            if csv_file in split_pairs.values() and csv_file not in split_processed:
                secondary = next(s for s, p in split_pairs.items() if p == csv_file)
                output_file = self.output_dir / csv_file.relative_to(self.input_dir) if preserve_structure else self.output_dir / csv_file.name
                
                # The destination of the merged flight is the destination of the secondary segment
                dest_icao = _to_map[secondary] or 'UNKNOWN'
                
                print(f"\n  ► {csv_file.name} + {secondary.name}  [{ac_type}] (split merge)")
                if self.process_split_pair(csv_file, secondary, output_file, ac_type, to_icao=dest_icao):
                    folder_file_count += 1
                split_processed.add(csv_file)
                continue

            output_file = self.output_dir / csv_file.relative_to(self.input_dir) if preserve_structure else self.output_dir / csv_file.name

            print(f"\n  ► {csv_file.name}  [{ac_type}]")
            if self.process_single_file(csv_file, output_file, ac_type, to_icao=_to_map[csv_file] or 'UNKNOWN'):
                folder_file_count += 1

        if current_folder is not None:
            print(f"\n  ✓ {current_folder} — {folder_file_count} file(s) done")

        self._print_terminal_summary()
        self._write_summary_report()

    # ── Output reporting (V2_1 Version) ────────────────────────────────────────

    def _print_terminal_summary(self) -> None:
        stats = self.summary_stats
        total = stats['total_rows']
        mc, ms = stats['mean_confidence'], stats['mean_stability']
        mean_conf = sum(mc) / len(mc) if mc else 0.0
        mean_stab = sum(ms) / len(ms) if ms else 0.0

        print(f"\n{'='*60}\n  BATCH COMPLETE")
        print(f"  Files      : {stats['processed_files']} processed  {stats['skipped_files']} skipped  {stats['failed_files']} failed  / {stats['total_files']} total")
        print(f"  Rows       : {total:,}\n  Confidence : mean={mean_conf:.3f}\n  Stability  : mean={mean_stab:.3f}\n{'='*60}")

        if stats['phase_distribution']:
            print("\n  Phase Distribution:")
            for phase, count in sorted(stats['phase_distribution'].items()):
                print(f"    {phase:25s}: {count:8,d}  ({(count / total * 100 if total else 0):5.1f}%)")

        if stats['event_distribution']:
            print("\n  Event Occurrences (all flights):")
            for lbl, cnt in sorted(stats['event_distribution'].items(), key=lambda x: x, reverse=True):
                m = re.search(r'_S()$', lbl)
                sev = int(m.group(1)) if m else 0
                base = lbl[:m.start()] if m else lbl
                edef = FLIGHT_EVENT_DEFINITIONS.get(base, {})
                desc = edef.get(f's{sev}', {}).get('description', edef.get('description', ''))[:50]
                print(f"    {lbl:45s}: {cnt:4d}  {desc}")

        failed = [e for e in self.processing_log if e['status'] == 'failed']
        if failed:
            print(f"\n  ⚠  Failed ({len(failed)}):")
            for e in failed: print(f"    • {e['file']}: {e.get('error', '')}")
        print()

    def _write_summary_report(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stats = self.summary_stats
        total = stats['total_rows']
        now   = datetime.now()
        mc, ms = stats['mean_confidence'], stats['mean_stability']
        mean_conf = sum(mc) / len(mc) if mc else 0.0
        mean_stab = sum(ms) / len(ms) if ms else 0.0

        def _native(obj):
            if isinstance(obj, (np.integer,)): return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, dict): return {k: _native(v) for k, v in obj.items()}
            if isinstance(obj, list): return [_native(i) for i in obj]
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

        SEP = '=' * 70
        report_path = self.output_dir / 'BATCH_SUMMARY_REPORT.txt'

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(SEP + '\nBATCH FLIGHT PHASE CLASSIFICATION REPORT\nClassifier : FOQAFlightClassifier\n' + SEP + '\n\n')
            f.write(f'Date/Time        : {now.strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Input Directory  : {self.input_dir}\nOutput Directory : {self.output_dir}\n\n')

            f.write('PROCESSING SUMMARY\n' + SEP + '\n')
            f.write(f'Files found      : {stats["total_files"]}\nProcessed        : {stats["processed_files"]}\n')
            f.write(f'Skipped          : {stats["skipped_files"]} (already classified)\nFailed           : {stats["failed_files"]}\n')
            f.write(f'Total rows       : {total:,}\nMean confidence  : {mean_conf:.3f}\nMean stability   : {mean_stab:.3f}\n\n')

            failed = [e for e in self.processing_log if e['status'] == 'failed']
            if failed:
                f.write('FAILED FILES\n' + SEP + '\n')
                for e in failed: f.write(f'  {e["file"]}\n    Error: {e.get("error", "Unknown")}\n')
                f.write('\n')

            f.write('OVERALL PHASE DISTRIBUTION\n' + SEP + '\n')
            for phase, count in sorted(stats['phase_distribution'].items()):
                f.write(f'  {phase:25s}: {count:9,d} rows  ({(count / total * 100 if total else 0):5.1f}%)\n')
            f.write('\n')

            if stats['event_distribution']:
                f.write('EVENT OCCURRENCES (all flights)\n' + SEP + '\n')
                for lbl, cnt in sorted(stats['event_distribution'].items(), key=lambda x: x, reverse=True):
                    m = re.search(r'_S()$', lbl)
                    sev = int(m.group(1)) if m else 0
                    base = lbl[:m.start()] if m else lbl
                    edef = FLIGHT_EVENT_DEFINITIONS.get(base, {})
                    desc = edef.get(f's{sev}', {}).get('description', edef.get('description', ''))
                    f.write(f'  {lbl:45s}: {cnt:4d} occurrences\n')
                    if desc: f.write(f'    {desc}\n')
                f.write('\n')

            f.write('\nINDIVIDUAL FLIGHT DETAILS\n' + SEP + '\n\n')
            for entry in self.processing_log:
                f.write(f'File     : {entry["file"]}\nAircraft : {entry["aircraft_type"]}\n')
                if entry['status'] == 'failed':
                    f.write(f'Status   : FAILED\nError    : {entry.get("error", "Unknown")}\n\n' + '-' * 70 + '\n\n')
                    continue

                rows = entry.get('rows', 0)
                f.write(f'Status   : {"SKIPPED" if entry["status"] == "skipped" else "SUCCESS"}\n')
                f.write(f'Date     : {entry.get("flight_date", "")}\nTakeoff  : {entry.get("takeoff_time", "")}\n')
                f.write(f'Landing  : {entry.get("landing_time", "")}\nDuration : {entry.get("flight_duration", "00:00")}\n')
                f.write(f'Rows     : {rows:,}\nConfidence (mean) : {entry.get("mean_confidence", 0):.3f}\nStability  (mean) : {entry.get("mean_stability", 0):.3f}\n')

                dyn = entry.get('dynamic_thresholds', {})
                if dyn:
                    f.write('Dynamic thresholds:\n')
                    f.write(f'  Climb rate   : {dyn.get("climb_rate", "N/A"):.1f} fpm\n  Descent rate : {dyn.get("descent_rate", "N/A"):.1f} fpm\n  Cruise AltAAL   : {dyn.get("cruise_AltAAL", "N/A"):.1f} ft\n')

                phases = entry.get('phases', {})
                if phases:
                    f.write('Phases:\n')
                    for ph, cnt in sorted(phases.items(), key=lambda x: x, reverse=True):
                        f.write(f'  {ph:25s}: {cnt:6d}  ({(cnt / rows * 100 if rows else 0):5.1f}%)\n')

                ews = entry.get('event_windows', [])
                if ews:
                    f.write('Events (discrete occurrences):\n')
                    for ew in ews:
                        peak = (f"  peak={ew['peak_value']:.2f}" if ew.get('peak_value') is not None else '')
                        base, sev = ew['event'], ew.get('severity', 1)
                        edef = FLIGHT_EVENT_DEFINITIONS.get(base, {})
                        desc = edef.get(f's{sev}', {}).get('description', '')[:60]
                        f.write(f'  [{ew["label"]:42s}] rows {ew["start_row"]:5d}–{ew["end_row"]:5d} ({ew["duration_sec"]:3d}s){peak}\n')
                        if desc: f.write(f'    {desc}\n')
                else: f.write('Events: none\n')
                f.write('\n' + '-' * 70 + '\n\n')

        print(f'\n  Reports written:\n    {report_path}\n    {log_path}')

# ────────────────────────────────────────────────────────────────────────────
#  CLI
# ────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Batch FOQA Flight Phase Classifier v4.0 (FDA/Aering) - Split-Log Enabled',
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
    parser.add_argument('--aircraft', '-a', default='Auto', help='Force aircraft type')
    parser.add_argument('--flatten',  action='store_true', help='Write all files flat')
    parser.add_argument('--pattern',  default='**/*.csv', help='Glob pattern')
    parser.add_argument('--debug',    action='store_true', help='Enable debug output')
    parser.add_argument('--list-aircraft', action='store_true', help='Print configs and exit')
    parser.add_argument('--show-registrations', action='store_true', help='Print registrations and exit')

    args = parser.parse_args()

    if args.list_aircraft:
        print('\nAvailable Aircraft Configurations\n' + '=' * 60)
        for ac, cfg in AIRCRAFT_CONFIGS.items():
            print(f'\n{ac}:')
            for k, v in cfg.items(): print(f'  {k:<35s}: {v}')
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