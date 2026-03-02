#!/usr/bin/env python3

import pandas as pd
import numpy as np
import os
import glob
import argparse
from pathlib import Path
from datetime import datetime
import json

#  Import classifier 
try:
    import flight_phase_classifier
except ImportError as e:
    raise SystemExit(
        f"\n[ERROR] Could not import flight_phase_classifier.py: {e}\n"
        "Ensure flight_phase_classifier.py is in the same directory "
        "as this script.\n"
    )

# ── Optional registration map ─────────────────────────────────────────────────
try:
    from aircraft_registration_map import (
        get_aircraft_type_from_registration,
        get_aircraft_type_from_path,
        AIRCRAFT_REGISTRATION_MAP,
    )
    REGISTRATION_MAP_AVAILABLE = True
except ImportError:
    REGISTRATION_MAP_AVAILABLE = False

# ── All numeric columns expected by the v2 classifier ───────────────────────
NUMERIC_COLUMNS = [
    'VSpd', 'IAS', 'GndSpd', 'Pitch', 'Roll', 'LatAc', 'NormAc',
    'E1 FFlow', 'E1 Torq', 'E1 NP', 'E1 NG', 'E1 ITT',
    'AltGPS', 'AltB', 'AltMSL', 'TAS', 'HDG', 'TRK',
    'WndSpd', 'WndDr', 'WptDst', 'AfcsOn',
    'GPSfix', 'HAL', 'VAL',
]


class BatchFlightProcessor:

    def __init__(self, input_dir: str, output_dir: str,
                 aircraft_type: str = "Auto"):
        self.input_dir    = Path(input_dir)
        self.output_dir   = Path(output_dir)
        self.aircraft_type = aircraft_type
        self.processing_log: list = []
        self.summary_stats = {
            'total_files'       : 0,
            'processed_files'   : 0,
            'skipped_files'     : 0,
            'failed_files'      : 0,
            'total_rows'        : 0,
            'phase_distribution': {},
            'event_distribution': {},
        }

    # ── Aircraft type detection ───────────────────────────────────────────────

    def detect_aircraft_type(self, csv_file: Path) -> str:
        # Priority 1 — registration map
        if REGISTRATION_MAP_AVAILABLE:
            aircraft = get_aircraft_type_from_path(str(csv_file))
            if aircraft:
                return aircraft

        # Priority 2/3 — G1000 CSV header field
        try:
            with open(csv_file, 'r', errors='replace') as f:
                first_line = f.readline()

            if 'airframe_name=' in first_line:
                start = first_line.find('airframe_name="') + len('airframe_name="')
                end   = first_line.find('"', start)
                airframe_name = first_line[start:end].strip()

                # Exact match first
                if airframe_name in flight_phase_classifier.AIRCRAFT_CONFIGS:
                    return airframe_name

                # Fuzzy — check if any known config key appears in the header string
                airframe_lower = airframe_name.lower()
                for known in flight_phase_classifier.AIRCRAFT_CONFIGS:
                    if known.lower() in airframe_lower or airframe_lower in known.lower():
                        return known

        except Exception:
            pass

        return "Generic"

    # ── Single file processing ────────────────────────────────────────────────

    def process_single_file(self, input_file: Path,
                             output_file: Path,
                             aircraft_type: str) -> bool:
        """
          FLIGHT_PHASE  — phase label (e.g. CRUISE, APPROACH)
          FLIGHT_EVENT  — special event flags (e.g. HARD_LANDING, GO_AROUND)
                          or 'NORMAL' if no event detected.
        """
        try:
            # ── Read raw file, preserving the 3-line G1000 header ────────────
            with open(input_file, 'r', errors='replace') as f:
                header_line1 = f.readline()   # G1000 metadata
                header_line2 = f.readline()   # Units row
                header_line3 = f.readline().strip()  # Column names

            # ── Skip files that are already classified ────────────────────────
            # Checks the column header line for the FLIGHT_PHASE marker so
            # rerunning the batch on the same input folder is safe.
            if 'FLIGHT_PHASE' in header_line3:
                print(f"  [SKIP] already classified: {input_file.name}")
                self.summary_stats['processed_files'] += 1
                # Count as success so totals remain accurate
                df_check = pd.read_csv(input_file, skiprows=2, dtype=str,
                                       on_bad_lines='skip')
                df_check.columns = df_check.columns.str.strip()
                phase_counts = df_check['FLIGHT_PHASE'].value_counts().to_dict() \
                               if 'FLIGHT_PHASE' in df_check.columns else {}
                self.summary_stats['total_rows'] += len(df_check)
                for phase, count in phase_counts.items():
                    self.summary_stats['phase_distribution'][phase] = (
                        self.summary_stats['phase_distribution'].get(phase, 0) + count
                    )
                self.processing_log.append({
                    'file'         : input_file.name,
                    'aircraft_type': aircraft_type,
                    'status'       : 'skipped',
                    'rows'         : len(df_check),
                    'phases'       : phase_counts,
                    'events'       : {},
                })
                return True

            df_raw = pd.read_csv(input_file, skiprows=2, dtype=str)
            df_raw.columns = df_raw.columns.str.strip()
            original_columns = df_raw.columns.tolist()

            if df_raw.empty:
                raise ValueError("File contains no data rows after the header.")

            # ── Deduplicate rows with identical Lcl Date + Lcl Time ──────────
            # G1000 1-Hz logging can record the same second twice when the GPS
            # clock stutters or straddles a second boundary. Duplicate timestamp
            # rows corrupt rolling / diff operations downstream. Keep the last
            # occurrence (most complete sensor snapshot) and reset to a clean
            # sequential integer index.
            time_cols = [c for c in df_raw.columns
                         if c.strip() in ('Lcl Date', 'Lcl Time')]
            if len(time_cols) == 2:
                before = len(df_raw)
                df_raw = df_raw.drop_duplicates(subset=time_cols, keep='last')
                dupes  = before - len(df_raw)
                if dupes > 0:
                    print(f"    [INFO] Removed {dupes} duplicate timestamp row(s)")
            df_raw = df_raw.reset_index(drop=True)

            # ── Build numeric working copy ────────────────────────────────────
            df_work = df_raw.copy()
            for col in NUMERIC_COLUMNS:
                if col in df_work.columns:
                    df_work[col] = pd.to_numeric(df_work[col],
                                                  errors='coerce').fillna(0.0)

            # Fill any columns missing from this log file with zeros
            df_work = flight_phase_classifier.ensure_columns(df_work)

            # ── Reset to clean 0-based index before classification ────────────
            # G1000 CSVs read with skiprows can carry duplicate or non-contiguous
            # index labels which cause pandas to raise
            # "cannot reindex on an axis with duplicate labels"
            # inside rolling / iloc[::-1] operations in require_persistence().
            df_work = df_work.reset_index(drop=True)

            # ── Classify ──────────────────────────────────────────────────────
            classifier = flight_phase_classifier.FOQAFlightClassifier(aircraft_type=aircraft_type)
            df_work    = classifier.classify(df_work)

            # ── Propagate all 5 classifier output columns back to raw frame ──
            df_raw['FLIGHT_PHASE']     = df_work['FLIGHT_PHASE'].values
            df_raw['FLIGHT_EVENT']     = df_work['FLIGHT_EVENT'].values
            df_raw['PHASE_CONFIDENCE'] = df_work['PHASE_CONFIDENCE'].values
            df_raw['PHASE_REASON']     = df_work['PHASE_REASON'].values
            df_raw['PHASE_STABILITY']  = df_work['PHASE_STABILITY'].values

            # ── Statistics ───────────────────────────────────────────────────
            phase_counts = df_raw['FLIGHT_PHASE'].value_counts().to_dict()
            event_series = df_raw['FLIGHT_EVENT'].str.split('|').explode()
            event_counts = event_series[event_series != 'NORMAL'] \
                                .value_counts().to_dict()

            self.summary_stats['processed_files'] += 1
            self.summary_stats['total_rows']      += len(df_raw)

            for phase, count in phase_counts.items():
                self.summary_stats['phase_distribution'][phase] = (
                    self.summary_stats['phase_distribution'].get(phase, 0) + count
                )
            for event, count in event_counts.items():
                self.summary_stats['event_distribution'][event] = (
                    self.summary_stats['event_distribution'].get(event, 0) + count
                )

            # ── Write output (preserve 3-line G1000 header) ──────────────────
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w') as f:
                f.write(header_line1)
                f.write(header_line2)
                f.write(header_line3 +
                        ',FLIGHT_PHASE,FLIGHT_EVENT'
                        ',PHASE_CONFIDENCE,PHASE_REASON,PHASE_STABILITY\n')

                for idx, row in df_raw.iterrows():
                    orig_vals = df_raw.loc[idx, original_columns].tolist()
                    line = ','.join(
                        str(x) if pd.notna(x) else '' for x in orig_vals
                    )
                    f.write(
                        f"{line},"
                        f"{row['FLIGHT_PHASE']},"
                        f"{row['FLIGHT_EVENT']},"
                        f"{row['PHASE_CONFIDENCE']},"
                        f"\"{row['PHASE_REASON']}\","   # quoted: may contain commas
                        f"{row['PHASE_STABILITY']}\n"
                    )

            self.processing_log.append({
                'file'         : input_file.name,
                'aircraft_type': aircraft_type,
                'status'       : 'success',
                'rows'         : len(df_raw),
                'phases'       : phase_counts,
                'events'       : event_counts,
            })

            return True

        except Exception as exc:
            self.summary_stats['failed_files'] += 1
            self.processing_log.append({
                'file'         : input_file.name,
                'aircraft_type': aircraft_type,
                'status'       : 'failed',
                'error'        : str(exc),
            })
            print(f"  [FAILED] {input_file.name}: {exc}")
            return False

    # ── File discovery ────────────────────────────────────────────────────────

    def find_csv_files(self, pattern: str = "**/*.csv") -> list:
        """Return sorted list of CSV files, excluding already-classified outputs."""
        files = list(self.input_dir.glob(pattern))
        # Skip files that already contain our output markers
        files = [
            f for f in files
            if 'FLIGHT_PHASE' not in f.name.upper()
            and 'BATCH_SUMMARY' not in f.name.upper()
        ]
        return sorted(files)

    # ── Batch entry point ─────────────────────────────────────────────────────

    def process_batch(self, preserve_structure: bool = True,
                      pattern: str = "**/*.csv") -> None:
        """Process all matching CSV files under input_dir."""
        csv_files = self.find_csv_files(pattern)
        self.summary_stats['total_files'] = len(csv_files)

        if not csv_files:
            print(f"[INFO] No CSV files found in: {self.input_dir}")
            return

        print(f"\nFound {len(csv_files)} file(s). Starting batch classification...\n")

        current_folder    = None
        folder_file_count = 0

        for csv_file in csv_files:
            # ── Folder change banner ─────────────────────────────────────────
            try:
                folder_label = str(csv_file.parent.relative_to(self.input_dir))
                if folder_label == '.':
                    folder_label = "Root"
            except ValueError:
                folder_label = csv_file.parent.name

            if folder_label != current_folder:
                if current_folder is not None:
                    print(f"  ✓ {current_folder} — {folder_file_count} file(s) done")
                    print("  " + "─" * 50)
                print(f"\n  Folder: {folder_label}")
                current_folder    = folder_label
                folder_file_count = 0

            # ── Determine aircraft type ──────────────────────────────────────
            if self.aircraft_type == "Auto":
                aircraft_type = self.detect_aircraft_type(csv_file)
            else:
                aircraft_type = self.aircraft_type

            # ── Output path ──────────────────────────────────────────────────
            if preserve_structure:
                relative_path = csv_file.relative_to(self.input_dir)
                output_file   = self.output_dir / relative_path
            else:
                output_file = self.output_dir / csv_file.name

            # ── Process ──────────────────────────────────────────────────────
            print(f"  Processing: {csv_file.name}  [{aircraft_type}]")
            success = self.process_single_file(csv_file, output_file, aircraft_type)

            if success:
                folder_file_count += 1

        # Final folder close
        if current_folder is not None:
            print(f"  ✓ {current_folder} — {folder_file_count} file(s) done")

        # ── Reports ──────────────────────────────────────────────────────────
        self._print_terminal_summary()
        self._write_summary_report()

    # ── Terminal summary ──────────────────────────────────────────────────────

    def _print_terminal_summary(self) -> None:
        stats = self.summary_stats
        total = stats['total_rows']
        print(f"\n{'='*60}")
        print(f"  BATCH COMPLETE")
        print(f"  Files  : {stats['processed_files']} ok / "
              f"{stats.get('skipped_files', 0)} skipped / "
              f"{stats['failed_files']} failed / {stats['total_files']} total")
        print(f"  Rows   : {total:,}")
        print(f"{'='*60}")

        if stats['phase_distribution']:
            print("\n  Phase Distribution (all flights):")
            for phase, count in sorted(stats['phase_distribution'].items()):
                pct = count / total * 100 if total else 0
                print(f"    {phase:22s}: {count:7,d}  ({pct:5.1f}%)")

        if stats['event_distribution']:
            print("\n  Special Events Detected:")
            for ev, count in sorted(stats['event_distribution'].items(),
                                    key=lambda x: -x[1]):
                print(f"    {ev:30s}: {count:4d} rows")

        failed = [e for e in self.processing_log if e['status'] == 'failed']
        if failed:
            print(f"\n  ⚠  Failed files ({len(failed)}):")
            for entry in failed:
                print(f"    • {entry['file']}")
                print(f"      {entry.get('error', 'Unknown error')}")
        print()

    # ── Report files ─────────────────────────────────────────────────────────

    def _write_summary_report(self) -> None:
        """Write BATCH_SUMMARY_REPORT.txt and processing_log.json."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stats = self.summary_stats
        total = stats['total_rows']
        now   = datetime.now()

        # ── JSON log ─────────────────────────────────────────────────────────
        log_path = self.output_dir / 'processing_log.json'
        with open(log_path, 'w') as f:
            json.dump({
                'timestamp'       : now.isoformat(),
                'input_directory' : str(self.input_dir),
                'output_directory': str(self.output_dir),
                'summary'         : stats,
                'files'           : self.processing_log,
            }, f, indent=2)

        # ── Text report ──────────────────────────────────────────────────────
        report_path = self.output_dir / 'BATCH_SUMMARY_REPORT.txt'
        SEP = "=" * 70

        with open(report_path, 'w') as f:
            f.write(SEP + "\n")
            f.write("BATCH FLIGHT PHASE CLASSIFICATION REPORT\n")
            f.write("Classifier: flight_phase_classifier.py — FOQAFlightClassifier v2\n")
            f.write(SEP + "\n\n")
            f.write(f"Date/Time        : {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Input Directory  : {self.input_dir}\n")
            f.write(f"Output Directory : {self.output_dir}\n\n")

            f.write("PROCESSING SUMMARY\n")
            f.write(SEP + "\n")
            f.write(f"Files found      : {stats['total_files']}\n")
            f.write(f"Processed OK     : {stats['processed_files']}\n")
            f.write(f"Skipped (already classified): {stats.get('skipped_files', 0)}\n")
            f.write(f"Failed           : {stats['failed_files']}\n")
            f.write(f"Total rows       : {total:,}\n\n")

            # Failed files
            failed = [e for e in self.processing_log if e['status'] == 'failed']
            if failed:
                f.write("FAILED FILES\n")
                f.write(SEP + "\n")
                for entry in failed:
                    f.write(f"  {entry['file']}\n")
                    f.write(f"    Error: {entry.get('error', 'Unknown')}\n")
                f.write("\n")

            # Phase distribution
            f.write("OVERALL PHASE DISTRIBUTION (all flights)\n")
            f.write(SEP + "\n")
            for phase, count in sorted(stats['phase_distribution'].items()):
                pct = count / total * 100 if total else 0
                f.write(f"  {phase:22s}: {count:8,d} rows  ({pct:5.1f}%)\n")

            # Event distribution
            if stats['event_distribution']:
                f.write("\nSPECIAL EVENTS DETECTED (all flights)\n")
                f.write(SEP + "\n")
                for ev, count in sorted(stats['event_distribution'].items(),
                                        key=lambda x: -x[1]):
                    f.write(f"  {ev:30s}: {count:4d} rows\n")

            # Per-file detail
            f.write("\n\nINDIVIDUAL FLIGHT DETAILS\n")
            f.write(SEP + "\n\n")
            for entry in self.processing_log:
                f.write(f"File    : {entry['file']}\n")
                f.write(f"Aircraft: {entry['aircraft_type']}\n")

                if entry['status'] in ('success', 'skipped'):
                    rows = entry['rows']
                    label = 'SKIPPED (already classified)' \
                            if entry['status'] == 'skipped' else 'SUCCESS'
                    f.write(f"Status  : {label}\n")
                    f.write(f"Rows    : {rows:,}\n")

                    f.write("Phases  :\n")
                    for phase, count in sorted(entry['phases'].items()):
                        pct = count / rows * 100 if rows else 0
                        f.write(f"  {phase:22s}: {count:5d}  ({pct:5.1f}%)\n")

                    if entry.get('events'):
                        f.write("Events  :\n")
                        for ev, count in sorted(entry['events'].items(),
                                                key=lambda x: -x[1]):
                            f.write(f"  {ev:30s}: {count:4d} rows\n")
                else:
                    f.write(f"Status  : FAILED\n")
                    f.write(f"Error   : {entry.get('error', 'Unknown')}\n")

                f.write("\n" + "-" * 70 + "\n\n")

        print(f"  Reports written:")
        print(f"    {report_path}")
        print(f"    {log_path}")


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Batch flight phase classifier — FOQAFlightClassifier v2',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Directory layouts supported
---------------------------
Single aircraft folder:
  input/
  ├── flight_001.csv
  └── flight_002.csv

Multiple aircraft folders (Auto mode picks type per folder):
  input/
  ├── PK-SNO/
  │   └── flight_001.csv
  └── PK-ABC/
      └── flight_001.csv

Examples
--------
  # Auto-detect aircraft type, mirror folder structure in output
  python batch_flight_processor.py input/ output/

  # Force specific aircraft type
  python batch_flight_processor.py input/ output/ --aircraft "Cessna 208B Grand Caravan"

  # Flatten output (all files in one output folder)
  python batch_flight_processor.py input/ output/ --flatten

  # Show all configured aircraft types and their thresholds
  python batch_flight_processor.py --list-aircraft
"""
    )

    parser.add_argument('input_dir',  nargs='?',
                        help='Input directory containing CSV files')
    parser.add_argument('output_dir', nargs='?',
                        help='Output directory for classified files')
    parser.add_argument('--aircraft', '-a', default='Auto',
                        help='Aircraft type (default: Auto)')
    parser.add_argument('--flatten', action='store_true',
                        help='Flatten output — no subfolder structure')
    parser.add_argument('--pattern', default='**/*.csv',
                        help='Glob pattern for file search (default: **/*.csv)')
    parser.add_argument('--list-aircraft', action='store_true',
                        help='Print available aircraft configurations and exit')
    parser.add_argument('--show-registrations', action='store_true',
                        help='Print aircraft registration mapping and exit')

    args = parser.parse_args()

    # ── Info-only modes ───────────────────────────────────────────────────────
    if args.list_aircraft:
        print("\nAvailable Aircraft Configurations")
        print("=" * 60)
        for aircraft, cfg in flight_phase_classifier.AIRCRAFT_CONFIGS.items():
            print(f"\n{aircraft}:")
            for key, val in cfg.items():
                print(f"  {key:<30s}: {val}")
        return

    if args.show_registrations:
        if REGISTRATION_MAP_AVAILABLE:
            from aircraft_registration_map import print_registration_summary
            print_registration_summary()
        else:
            print("[ERROR] aircraft_registration_map.py not found.")
        return

    # ── Validate required arguments ───────────────────────────────────────────
    if not args.input_dir or not args.output_dir:
        parser.error("input_dir and output_dir are required.")

    if not os.path.isdir(args.input_dir):
        raise SystemExit(f"[ERROR] Input directory not found: {args.input_dir}")

    os.makedirs(args.output_dir, exist_ok=True)

    # ── Run ───────────────────────────────────────────────────────────────────
    processor = BatchFlightProcessor(
        input_dir     = args.input_dir,
        output_dir    = args.output_dir,
        aircraft_type = args.aircraft,
    )
    processor.process_batch(
        preserve_structure = not args.flatten,
        pattern            = args.pattern,
    )

if __name__ == "__main__":
    main()