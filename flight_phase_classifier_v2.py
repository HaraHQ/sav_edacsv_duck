#!/usr/bin/env python3

import sys
import io
import json
import os
import re
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import argparse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                   encoding='utf-8', errors='replace')

# 
#  AIRCRAFT CONFIGURATION
#  V3 ADDITION: Hysteresis thresholds appended to every config block.
#               Enter threshold is STRICTER than exit threshold.
#               The gap between them is the hysteresis dead-band.
# 

AIRCRAFT_CONFIGS: Dict[str, Dict] = {
    "Cessna 208 Caravan": {
        #  V2: Rotation / climb (unchanged) 
        "rotation_ias"          : 58.0,
        "climb_torque_min"      : 1200.0,
        "climb_rate_threshold"  : 400.0,    # static fallback; adaptive overrides
        #  V2: Ground ops 
        "taxi_speed_threshold"  : 6.0,
        "definitely_airborne_ias": 55.0,
        "liftoff_AltAAL"           : 30.0,     # static fallback
        #  V2: Landing 
        "flare_AltAAL"             : 50.0,
        "touchdown_AltAAL"         : 15.0,
        #  V2: Engine / power 
        "idle_ng_max"           : 68.0,
        "idle_fflow_max"        : 80.0,
        "takeoff_torque_min"    : 1100.0,
        #  V2: Cruise band 
        "cruise_fflow_min"      : 120.0,
        "cruise_fflow_max"      : 350.0,
        "steep_turn_bank"       : 45.0,
        "hard_landing_g"        : 1.8,
        "high_wind_landing_kts" : 15.0,
        "cruise_AltAAL_min"        : 1000.0,   # static fallback
        #  V3: Hysteresis - CLIMB 
        "climb_rate_enter"      : 450.0,
        "climb_rate_exit"       : 300.0,
        #  V3: Hysteresis - DESCENT 
        "descent_rate_enter"    : 450.0,
        "descent_rate_exit"     : 250.0,
        #  V3: Hysteresis - AIRBORNE 
        "liftoff_AltAAL_enter"     : 40.0,
        "liftoff_AltAAL_exit"      : 20.0,
        #  Event detection thresholds 
        # Verify ITT limits against aircraft AMM before deploying.
        "vmo_kias"              : 175.0,    # max operating speed (KIAS)
        "vref_approach"         : 82.0,     # approach speed proxy (med weight)
        "hard_landing_g_critical": 2.1,     # above this  S3 hard landing
        "low_airspeed_warn"     : 78.0,     # KIAS - S2 low airspeed (ÃÂÃÂ Vs1 + margin)
        "low_airspeed_critical" : 68.0,     # KIAS - S3 low airspeed
        "itt_warn"              : 740.0,    # Â°C - above max continuous (PT6A-114A)
        "itt_limit"             : 800.0,    # Â°C - approaching takeoff limit
        "rapid_power_warn"      : 200.0,    # ftÂ·lb/s torque rate - S1
        "rapid_power_critical"  : 400.0,    # ftÂ·lb/s torque rate - S2
        #  Spec event thresholds 
        "hard_landing_g"        : 1.70,    # g - LGN000 S2 (spec)
        "hard_landing_g_critical": 1.90,   # g - LGN000 S3 (spec)
        "ng_limit"              : 101.6,   # % - FEN400 Ng redline (B model)
        "torque_limit_takeoff"  : 1865.0,  # ftÂ·lb - TEQ002 (208/208B)
        "np_limit_takeoff"      : 1910.0,  # rpm - TEP000
        "vmo_s1"                : 171.0,   # KIAS - FSA999 S1
        "vmo_s2"                : 173.0,   # KIAS - FSA999 S2
        "vmo_s3"                : 175.0,   # KIAS - FSA999 S3 redline
        "alt_warn"              : 15000.0, # ft MSL - FAS000 S2
        "alt_limit"             : 25000.0, # ft MSL - FAS000 S3
    },
    "Cessna 208B Grand Caravan": {
        "rotation_ias"          : 60.0,
        "climb_torque_min"      : 1200.0,
        "climb_rate_threshold"  : 400.0,
        "taxi_speed_threshold"  : 6.0,
        "definitely_airborne_ias": 57.0,
        "liftoff_AltAAL"           : 30.0,
        "flare_AltAAL"             : 50.0,
        "touchdown_AltAAL"         : 15.0,
        "idle_ng_max"           : 68.0,
        "idle_fflow_max"        : 85.0,
        "takeoff_torque_min"    : 1100.0,
        "cruise_fflow_min"      : 130.0,
        "cruise_fflow_max"      : 380.0,
        "steep_turn_bank"       : 45.0,
        "hard_landing_g"        : 1.8,
        "high_wind_landing_kts" : 15.0,
        "cruise_AltAAL_min"        : 1000.0,
        "climb_rate_enter"      : 450.0,
        "climb_rate_exit"       : 300.0,
        "descent_rate_enter"    : 450.0,
        "descent_rate_exit"     : 250.0,
        "liftoff_AltAAL_enter"     : 40.0,
        "liftoff_AltAAL_exit"      : 20.0,
        "vmo_kias"              : 175.0,
        "vref_approach"         : 85.0,
        "hard_landing_g_critical": 2.1,
        "low_airspeed_warn"     : 78.0,
        "low_airspeed_critical" : 68.0,
        "itt_warn"              : 740.0,
        "itt_limit"             : 800.0,
        "rapid_power_warn"      : 200.0,
        "rapid_power_critical"  : 400.0,
        #  Spec event thresholds 
        "hard_landing_g"        : 1.70,
        "hard_landing_g_critical": 1.90,
        "ng_limit"              : 101.6,   # % - FEN400 (B model)
        "torque_limit_takeoff"  : 1865.0,  # ftÂ·lb - TEQ002
        "np_limit_takeoff"      : 1910.0,
        "vmo_s1"                : 171.0,
        "vmo_s2"                : 173.0,
        "vmo_s3"                : 175.0,
        "alt_warn"              : 15000.0,
        "alt_limit"             : 25000.0,
    },
    "Cessna 208B Grand Caravan EX": {
        "rotation_ias"          : 60.0,
        "climb_torque_min"      : 1300.0,
        "climb_rate_threshold"  : 400.0,
        "taxi_speed_threshold"  : 6.0,
        "definitely_airborne_ias": 57.0,
        "liftoff_AltAAL"           : 30.0,
        "flare_AltAAL"             : 50.0,
        "touchdown_AltAAL"         : 15.0,
        "idle_ng_max"           : 68.0,
        "idle_fflow_max"        : 90.0,
        "takeoff_torque_min"    : 1200.0,
        "cruise_fflow_min"      : 140.0,
        "cruise_fflow_max"      : 400.0,
        "steep_turn_bank"       : 45.0,
        "hard_landing_g"        : 1.8,
        "high_wind_landing_kts" : 15.0,
        "cruise_AltAAL_min"        : 1000.0,
        "climb_rate_enter"      : 500.0,
        "climb_rate_exit"       : 320.0,
        "descent_rate_enter"    : 500.0,
        "descent_rate_exit"     : 280.0,
        "liftoff_AltAAL_enter"     : 40.0,
        "liftoff_AltAAL_exit"      : 20.0,
        "vmo_kias"              : 175.0,
        "vref_approach"         : 88.0,
        "hard_landing_g_critical": 2.1,
        "low_airspeed_warn"     : 80.0,
        "low_airspeed_critical" : 70.0,
        "itt_warn"              : 750.0,    # PT6A-140A  verify against AMM
        "itt_limit"             : 810.0,
        "rapid_power_warn"      : 200.0,
        "rapid_power_critical"  : 400.0,
        #  Spec event thresholds 
        "hard_landing_g"        : 1.70,
        "hard_landing_g_critical": 1.90,
        "ng_limit"              : 103.7,   # % - FEN400 EX model (PT6A-140A)
        "torque_limit_takeoff"  : 2397.0,  # ftÂ·lb - TEQ002 EX model
        "np_limit_takeoff"      : 1910.0,
        "vmo_s1"                : 171.0,
        "vmo_s2"                : 173.0,
        "vmo_s3"                : 175.0,
        "alt_warn"              : 15000.0,
        "alt_limit"             : 25000.0,
    },
    "Generic": {
        "rotation_ias"          : 60.0,
        "climb_torque_min"      : 1000.0,
        "climb_rate_threshold"  : 300.0,
        "taxi_speed_threshold"  : 5.0,
        "definitely_airborne_ias": 50.0,
        "liftoff_AltAAL"           : 30.0,
        "flare_AltAAL"             : 50.0,
        "touchdown_AltAAL"         : 15.0,
        "idle_ng_max"           : 68.0,
        "idle_fflow_max"        : 80.0,
        "takeoff_torque_min"    : 900.0,
        "cruise_fflow_min"      : 100.0,
        "cruise_fflow_max"      : 350.0,
        "steep_turn_bank"       : 45.0,
        "hard_landing_g"        : 1.8,
        "high_wind_landing_kts" : 15.0,
        "cruise_AltAAL_min"        : 1000.0,
        "climb_rate_enter"      : 380.0,
        "climb_rate_exit"       : 220.0,
        "descent_rate_enter"    : 380.0,
        "descent_rate_exit"     : 200.0,
        "liftoff_AltAAL_enter"     : 35.0,
        "liftoff_AltAAL_exit"      : 15.0,
        "vmo_kias"              : 175.0,
        "vref_approach"         : 85.0,
        "hard_landing_g_critical": 2.1,
        "low_airspeed_warn"     : 75.0,
        "low_airspeed_critical" : 65.0,
        "itt_warn"              : 740.0,
        "itt_limit"             : 800.0,
        "rapid_power_warn"      : 200.0,
        "rapid_power_critical"  : 400.0,
        #  Spec event thresholds 
        "hard_landing_g"        : 1.70,
        "hard_landing_g_critical": 1.90,
        "ng_limit"              : 101.6,   # % - generic fallback
        "torque_limit_takeoff"  : 1865.0,
        "np_limit_takeoff"      : 1910.0,
        "vmo_s1"                : 171.0,
        "vmo_s2"                : 173.0,
        "vmo_s3"                : 175.0,
        "alt_warn"              : 15000.0,
        "alt_limit"             : 25000.0,
    },
}

# 
#  FLIGHT EVENT DEFINITIONS
#
#  Severity levels
#  ---------------
#  S1  Notice    - informational; review if it recurs as a pattern.
#  S2  Warning   - SOP deviation or operational risk; investigate.
#  S3  Critical  - airworthiness concern or imminent safety risk; mandatory
#                  report and engineering review before next flight.
#
#  Event names use the official FDA Aering spec codes (e.g. LGN000, LSA505)
#  with a severity suffix, e.g. LGN000_S3, LSA505_S1.
#  Multiple events on the same row are pipe-separated: LGN000_S3|LVD030_S2.
#
#  Fields per severity tier
#  ------------------------
#  min_duration  Consecutive 1-Hz rows the condition must hold before the
#                event is confirmed (filters sensor spikes).
#  description   Human-readable text for reports and dashboard tooltips.
#
#  NOTE: ITT limits must be verified against the aircraft AMM before
#  deploying in a production environment.
# 

#  JSON EVENT DEFINITIONS LOADER
#  Reads EDA_Event.json from the same directory as this file.
#  Falls back gracefully if the file is missing.

_EVENT_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'EDA_Event.json')


def load_event_definitions(path: str = _EVENT_JSON_PATH) -> list:
    """Load event definitions from EDA_Event.json.
    Returns an empty list if the file cannot be found or parsed."""
    try:
        with open(path, 'r', encoding='utf-8') as _f:
            return json.load(_f)
    except Exception as _e:
        print(f"  [WARN] Could not load event definitions from {path}: {_e}")
        return []


FLIGHT_EVENT_DEFINITIONS: Dict[str, Dict] = {

    #  Landing impact 
    # LGN000  spec limits: S2  1.70 g, S3  1.90 g
    'NORM_G_HI_TDWN': {
        'S2': {'min_duration': 2,
               'description': 'LGN000: Firm landing  1.70 g  log and monitor'},
        'S3': {'min_duration': 2,
               'description': 'LGN000: Hard landing  1.90 g  maintenance inspection before next flight'},
    },

    #  Approach / descent 
    # LVD030  rate of descent high below 500 ft
    'ROD_HI_500FT': {
        'S1': {'min_duration': 3,
               'description': 'LVD030: Descent rate  1000 fpm below 500 ft AltAAL'},
        'S2': {'min_duration': 3,
               'description': 'LVD030: Descent rate  1300 fpm below 500 ft AltAAL  unstabilised approach'},
        'S3': {'min_duration': 3,
               'description': 'LVD030: Descent rate  1700 fpm below 500 ft AltAAL  CFIT risk'},
    },

    # LXX100  unstable approach (composite: speed + VS)
    'UNSTABLE_APP': {
        'S2': {'min_duration': 3,
               'description': 'LXX100: Speed or descent rate outside limits at 1000 ft AltAAL'},
        'S3': {'min_duration': 3,
               'description': 'LXX100: Speed or descent rate outside limits at 500 ft AltAAL'},
    },

    # LSA505  airspeed high 1000-500 ft
    'AIR_SPD_HI_1000_500FT': {
        'S1': {'min_duration': 15,
               'description': 'LSA505: IAS  125 kts at 1000-500 ft AltAAL'},
        'S2': {'min_duration': 15,
               'description': 'LSA505: IAS  135 kts at 1000-500 ft AltAAL'},
        'S3': {'min_duration': 15,
               'description': 'LSA505: IAS  155 kts at 1000-500 ft AltAAL'},
    },

    # LSA512  airspeed high 500-50 ft
    'AIR_SPD_HI_500_50FT': {
        'S1': {'min_duration': 5,
               'description': 'LSA512: IAS  105 kts at 500-50 ft AltAAL'},
        'S2': {'min_duration': 5,
               'description': 'LSA512: IAS  110 kts at 500-50 ft AltAAL'},
        'S3': {'min_duration': 5,
               'description': 'LSA512: IAS  115 kts at 500-50 ft AltAAL'},
    },

    # LSA513  airspeed high below 50 ft
    'AIR_SPD_HI_50FT': {
        'S1': {'min_duration': 5,
               'description': 'LSA513: IAS  90 kts below 50 ft AltAAL'},
        'S2': {'min_duration': 5,
               'description': 'LSA513: IAS  95 kts below 50 ft AltAAL'},
        'S3': {'min_duration': 5,
               'description': 'LSA513: IAS  100 kts below 50 ft AltAAL'},
    },

    # LSA514  airspeed high at landing
    'AIR_SPD_HI_LDG': {
        'S1': {'min_duration': 5,
               'description': 'LSA514: IAS  90 kts at landing  overrun risk'},
        'S2': {'min_duration': 5,
               'description': 'LSA514: IAS  95 kts at landing'},
        'S3': {'min_duration': 5,
               'description': 'LSA514: IAS  100 kts at landing  runway excursion risk'},
    },

    # LSA620  airspeed low 1000-500 ft
    'AIR_SPD_LO_1000_500FT': {
        'S3': {'min_duration': 5,
               'description': 'LSA620: IAS <= 72 kts at 1000-500 ft AltAAL  reduced stall margin'},
    },

    # LSA621  airspeed low 500-50 ft
    'AIR_SPD_LO_500_50FT': {
        'S1': {'min_duration': 5,
               'description': 'LSA621: IAS <= 72 kts at 500-50 ft AltAAL'},
        'S2': {'min_duration': 5,
               'description': 'LSA621: IAS <= 70 kts at 500-50 ft AltAAL'},
        'S3': {'min_duration': 5,
               'description': 'LSA621: IAS <= 69 kts at 500-50 ft AltAAL  stall risk'},
    },

    # LSA622  airspeed low at landing
    'AIR_SPD_LO_LDG': {
        'S1': {'min_duration': 5,
               'description': 'LSA622: IAS <= 65 kts at landing  hard landing / tail-strike risk'},
        'S2': {'min_duration': 5,
               'description': 'LSA622: IAS <= 63 kts at landing'},
        'S3': {'min_duration': 5,
               'description': 'LSA622: IAS <= 60 kts at landing  imminent stall'},
    },

    # LSA700  airspeed low 35-400 ft (departure side)
    'AIR_SPD_LO_35_400FT': {
        'S2': {'min_duration': 5,
               'description': 'LSA700: IAS <= 65 kts at 35-400 ft AltAAL  engine failure / windshear risk'},
        'S3': {'min_duration': 5,
               'description': 'LSA700: IAS <= 63 kts at 35-400 ft AltAAL  LOC-I risk'},
    },

    # LSA701  airspeed low 400-1500 ft
    'AIR_SPD_LO_400_1500FT': {
        'S3': {'min_duration': 5,
               'description': 'LSA701: IAS <= 75 kts at 400-1500 ft AltAAL  reduced safety margin'},
    },

    # TSA260  airspeed low at liftoff
    'AIR_SPD_LO_LIFTOFF': {
        'S2': {'min_duration': 5,
               'description': 'TSA260: IAS <= 55 kts at liftoff  tail strike / engine failure risk'},
        'S3': {'min_duration': 5,
               'description': 'TSA260: IAS <= 50 kts at liftoff  critical'},
    },

    #  Takeoff & liftoff 
    # TGN000  normal acceleration high during takeoff
    'NORM_G_HI_TO': {
        'S1': {'min_duration': 1,
               'description': 'TGN000: Normal accel  1.30 g during takeoff roll  control abnormality'},
        'S2': {'min_duration': 1,
               'description': 'TGN000: Normal accel  1.35 g during takeoff  tail strike risk'},
        'S3': {'min_duration': 1,
               'description': 'TGN000: Normal accel  1.40 g during takeoff  tail strike imminent'},
    },

    # TPA029  pitch high at takeoff
    'PITCH_HI_TO': {
        'S2': {'min_duration': 2,
               'description': 'TPA029: Pitch  13.5° during takeoff  tail strike / obstacle clearance risk'},
        'S3': {'min_duration': 2,
               'description': 'TPA029: Pitch  15° during takeoff  tail strike risk'},
    },

    # TEQ002  engine torque high at takeoff
    'ENG_TORQ_TO_HI': {
        'S3': {'min_duration': 1,
               'description': 'TEQ002: Torque exceeds POH takeoff limit  engine overstress, maintenance check required'},
    },

    # TEP000  propeller speed high at takeoff
    'PROP_SPD_TO_HI': {
        'S3': {'min_duration': 3,
               'description': 'TEP000: Np  1910 rpm during takeoff  propeller / gearbox stress'},
    },

    # TXX001  autopilot engaged early
    'AP_ENGAGED_EARLY_TO': {
        'S1': {'min_duration': 1,
               'description': 'TXX001: Autopilot engaged below 900 ft AAL after liftoff'},
        'S2': {'min_duration': 1,
               'description': 'TXX001: Autopilot engaged below 500 ft AAL  SOP deviation'},
        'S3': {'min_duration': 1,
               'description': 'TXX001: Autopilot engaged below 100 ft AAL  critical SOP violation'},
    },

    # TXX000/TXX002  rejected takeoff speed tiers
    'RTO_HI_SPD': {
        'S3': {'min_duration': 3,
               'description': 'TXX000: Rejected takeoff at GndSpd  70 kts  brake and structural inspection'},
    },

    'RTO_LO_SPD': {
        'S3': {'min_duration': 3,
               'description': 'TXX002: Rejected takeoff at GndSpd  40 kts  log and inspect brakes'},
    },

    # GSG001  taxi speed high
    'GND_SPD_HI_TAXI': {
        'S3': {'min_duration': 3,
               'description': 'GSG001: Groundspeed  32 kts while taxiing  brake wear / ground incident risk'},
    },

    #  Roll / bank 
    # TRA000  roll high liftoff to 20 ft
    'ROLL_HI_LIFTOFF_20FT': {
        'S1': {'min_duration': 3,
               'description': 'TRA000: Roll  15Â° at 0-20 ft AltAAL  directional control concern'},
        'S2': {'min_duration': 3,
               'description': 'TRA000: Roll  20Â° at 0-20 ft AltAAL'},
        'S3': {'min_duration': 3,
               'description': 'TRA000: Roll  30Â° at 0-20 ft AltAAL  engine failure / windshear'},
    },

    # TRA005  roll high 20-100 ft
    'ROLL_HI_20_100FT': {
        'S1': {'min_duration': 3,
               'description': 'TRA005: Roll  15Â° at 20-100 ft AltAAL'},
        'S2': {'min_duration': 3,
               'description': 'TRA005: Roll  20Â° at 20-100 ft AltAAL'},
        'S3': {'min_duration': 3,
               'description': 'TRA005: Roll  30Â° at 20-100 ft AltAAL  LOC-I risk'},
    },

    # TRA006  roll high 100-500 ft
    'ROLL_HI_100_500FT': {
        'S1': {'min_duration': 3,
               'description': 'TRA006: Roll  31Â° at 100-500 ft AltAAL'},
        'S2': {'min_duration': 3,
               'description': 'TRA006: Roll  41Â° at 100-500 ft AltAAL'},
        'S3': {'min_duration': 3,
               'description': 'TRA006: Roll  46Â° at 100-500 ft AltAAL  LOC-I risk'},
    },

    # FRA003  roll high above 500 ft
    'ROLL_HI_500FT': {
        'S1': {'min_duration': 3,
               'description': 'FRA003: Roll  35° above 500 ft AltAAL  outside normal ops'},
        'S2': {'min_duration': 3,
               'description': 'FRA003: Roll  41° above 500 ft AltAAL'},
        'S3': {'min_duration': 3,
               'description': 'FRA003: Roll  46° above 500 ft AltAAL  pilot over-control / system malfunction'},
    },

    #  Altitude / height loss 
    # TAA005  height loss 20-400 ft
    'HGT_LOSS_20_400FT': {
        'S1': {'min_duration': 1,
               'description': 'TAA005: Height loss  50 ft at 20-400 ft AltAAL  obstacle clearance reduced'},
        'S2': {'min_duration': 1,
               'description': 'TAA005: Height loss  75 ft at 20-400 ft AltAAL'},
        'S3': {'min_duration': 1,
               'description': 'TAA005: Height loss  100 ft at 20-400 ft AltAAL  engine failure / windshear'},
    },

    # TAA006  height loss 400-1000 ft
    'HGT_LOSS_400_1000FT': {
        'S1': {'min_duration': 1,
               'description': 'TAA006: Height loss  100 ft at 400-1000 ft AltAAL'},
        'S2': {'min_duration': 1,
               'description': 'TAA006: Height loss  150 ft at 400-1000 ft AltAAL'},
        'S3': {'min_duration': 1,
               'description': 'TAA006: Height loss  200 ft at 400-1000 ft AltAAL  CFIT risk'},
    },

    #  Airspeed 
    # FSA999  VMO exceedance (all phases, 3-tier)
    'AIR_SPD_VMO_EXCD': {
        'S1': {'min_duration': 5,
               'description': 'FSA999: IAS  171 kts  VMO onset'},
        'S2': {'min_duration': 5,
               'description': 'FSA999: IAS  173 kts  VMO exceedance, structural concern'},
        'S3': {'min_duration': 5,
               'description': 'FSA999: IAS  175 kts  VMO redline, mandatory structural log'},
    },


    #  Engine / systems 
    # FEN400  Ng redline (all phases, S3 only per spec)
    'ENG_N1_HI': {
        'S3': {'min_duration': 2,
               'description': 'FEN400: Ng at or above redline  mandatory engine inspection before next flight'},
    },

    # In FLIGHT_EVENT_DEFINITIONS:
    'ENG_GND_IDLE': {
        'S3': {'min_duration': 1,
            'description': 'FEQ200: Engine shut down with < 59s ground idle — insufficient turbine cooling'},
    },

    # FAS000  maximum altitude (all phases)
    'MAX_ALT_EXCD': {
        'S2': {'min_duration': 5,
               'description': 'FAS000: Altitude  15,000 ft MSL  above certified ceiling'},
        'S3': {'min_duration': 5,
               'description': 'FAS000: Altitude  25,000 ft MSL  structural / physiological limit'},
    },

    #  Engine ITT  4 separate events per spec 
    # GET050  engine start
    'ENG_GAS_TEMP_START_HI': {
        'S3': {'min_duration': 3,
               'description': 'GET050: ITT  900°C during engine start  hot start risk'},
    },
    # TET000  takeoff (5-min window)
    'ENG_GAS_TEMP_TO_HI': {
        'S3': {'min_duration': 3,
               'description': 'TET000: ITT exceeds takeoff limit during 5-min TO period'},
    },
    # GET070  climb (sustained 180 s)
    'ENG_GAS_TEMP_CLIMB_HI': {
        'S3': {'min_duration': 180,
               'description': 'GET070: ITT exceeds continuous climb limit for  180 s'},
    },
    # GET080  cruise
    'ENG_GAS_TEMP_CRUISE_HI': {
        'S3': {'min_duration': 5,
               'description': 'GET080: ITT exceeds cruise limit  accelerated turbine wear'},
    },

}
# 
#  STATE-MACHINE TRANSITION TABLE  (unchanged from v2)
# 

VALID_TRANSITIONS: Dict[str, List[str]] = {
    "PRE-FLIGHT"       : ["PRE-FLIGHT", "TAXI OUT"],
    "TAXI OUT"         : ["TAXI OUT", "TAKEOFF"],
    "TAKEOFF"          : ["TAKEOFF", "INITIAL CLIMB", "LANDING"], # Aborted Takeoff
    "INITIAL CLIMB"    : ["INITIAL CLIMB", "CLIMB", "CRUISE", "DESCENT", "PRE-FLIGHT", "TAXI OUT","TAKEOFF", ],
    "CLIMB"            : ["CLIMB", "CRUISE", "DESCENT"],
    "CRUISE"           : ["CRUISE", "CLIMB", "DESCENT"],
    "DESCENT"          : ["DESCENT", "APPROACH", "CLIMB", "CRUISE"],
    "APPROACH"         : ["APPROACH", "FINAL APPROACH", "INITIAL CLIMB", "LANDING"], # For Go-Around
    "FINAL APPROACH"   : ["FINAL APPROACH", "LANDING"], # For Go-Around
    "LANDING"          : ["LANDING", "TAXI IN"],
    "TAXI IN"          : ["TAXI IN"],
}

# Transitions that are NEVER allowed regardless of MAX_HOLD.
# Phase progression is strictly forward  once past a phase,
# the aircraft cannot return to it under any sensor condition.
NEVER_BACKWARD: Dict[str, set] = {
    "TAXI OUT"      : {"PRE-FLIGHT"},
    "TAKEOFF"       : {"PRE-FLIGHT", "TAXI OUT", "TAXI IN"},
    "INITIAL CLIMB" : {"PRE-FLIGHT", "TAXI OUT", "TAKEOFF", "TAXI IN"},
    "CLIMB"         : {"PRE-FLIGHT", "TAXI OUT", "TAKEOFF", "TAXI IN", "INITIAL CLIMB"},
    "CRUISE"        : {"PRE-FLIGHT", "TAXI OUT", "TAKEOFF", "TAXI IN"},
    "DESCENT"       : {"PRE-FLIGHT", "TAXI OUT", "TAKEOFF", "TAXI IN"},
    "APPROACH"      : {"PRE-FLIGHT", "TAXI OUT", "TAKEOFF", "TAXI IN", "CRUISE"},
    "FINAL APPROACH": {"PRE-FLIGHT", "TAXI OUT", "TAKEOFF", "TAXI IN", "DESCENT"},
    "LANDING"       : {"PRE-FLIGHT", "TAXI OUT", "TAKEOFF", "TAXI IN", "DESCENT", "APPROACH", "FINAL APPROACH"},
}


# 
#  HELPER: SAFE NUMERIC CONVERSION  (unchanged from v2)
# 

def safe_num(series: pd.Series, fill: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors='coerce').fillna(fill)

# 
#  V3 UTILITY: TEMPORAL PERSISTENCE FILTER
# 

def require_persistence(mask: pd.Series, min_duration: int) -> pd.Series:
    """
    Return a boolean Series where True is only set where the condition in
    `mask` has been continuously True for at least `min_duration` rows.

    Implementation operates entirely on numpy arrays so it is immune to
    duplicate, non-contiguous, or non-monotonic pandas index labels 
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

    #  Step 1: build run-length confirmed array using numpy only 
    # For each position i, compute how many consecutive True values end at i.
    # If that count >= min_duration, the end of a qualifying run is confirmed.
    run_len = np.zeros(n, dtype=int)
    for i in range(n):
        if arr[i]:
            run_len[i] = run_len[i - 1] + 1 if i > 0 else 1
        else:
            run_len[i] = 0

    confirmed_end = run_len >= min_duration   # bool array

    #  Step 2: back-propagate the confirmed end flag to the run start 
    # For every confirmed end position, mark the preceding (min_duration-1)
    # positions True as well, so the entire qualifying run is labelled.
    confirmed = np.zeros(n, dtype=bool)
    for i in range(n):
        if confirmed_end[i]:
            start = max(0, i - min_duration + 1)
            confirmed[start : i + 1] = True

    return pd.Series(confirmed, index=original_index)


# 
#  MAIN CLASSIFIER --
#  AIRPORT IDENTIFICATION   GPS-based, radius 8 km
#  Used to apply airport-specific event thresholds (e.g. WAYY taxi speed).
#  Expand this dict to add more airports as needed.
# 

SPECIAL_AIRPORTS: Dict[str, tuple] = {
    # ICAO  : (lat,      lon)
    'WAYY'  : (-4.5283,  136.8872),   # Mozes Kilangin, Timika
}
_AIRPORT_RADIUS_KM = 8.0             # within 8 km = at that airport


def _nearest_icao(lat: float, lon: float) -> str:
    """Return the ICAO code of the nearest special airport within radius, else ''."""
    import math
    def _hav(lat1, lon1, lat2, lon2) -> float:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 +             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    best_icao, best_dist = '', float('inf')
    for icao, (alat, alon) in SPECIAL_AIRPORTS.items():
        d = _hav(lat, lon, alat, alon)
        if d < best_dist:
            best_dist, best_icao = d, icao
    return best_icao if best_dist <= _AIRPORT_RADIUS_KM else ''


def _icao_from_filename(path: str) -> str:
    """Try to derive a departure ICAO from the input filename."""
    stem = Path(path).stem.upper()
    # Prefer explicit known special airports in the filename.
    for icao in SPECIAL_AIRPORTS.keys():
        if icao in stem:
            return icao

    # Fallback: use the first 4-character alphanumeric prefix.
    if len(stem) >= 4 and re.match(r'^[A-Z0-9]{4}', stem):
        return stem[:4]

    return ''


class FOQAFlightClassifier:

    SMOOTHING_MIN_DURATION = 4

    # Minimum data rows needed to compute adaptive thresholds.
    # Below this, static config values are used as-is.
    ADAPTIVE_MIN_ROWS = 100

    def __init__(self, aircraft_type: str = "Generic", debug_mode: bool = False,
                 dep_icao: str = "", arr_icao: str = ""):
        self.cfg          = AIRCRAFT_CONFIGS.get(aircraft_type, AIRCRAFT_CONFIGS["Generic"])
        self.aircraft_type = aircraft_type
        self.dep_icao     = dep_icao.upper().strip()
        self.arr_icao     = arr_icao.upper().strip()
        self.debug_mode   = debug_mode
        # JSON-driven event definitions (loaded once per classifier instance)
        self.event_defs: list = load_event_definitions()

        # V3: Adaptive thresholds  populated by compute_adaptive_thresholds()
        # before the classification loop. Initialised to static config values
        # so _classify_row() can read them unconditionally via self._dyn.
        self._dyn: Dict[str, float] = {
            'climb_rate'   : self.cfg['climb_rate_threshold'],
            'descent_rate' : self.cfg['climb_rate_threshold'],   # same default
            'cruise_AltAAL'   : self.cfg['cruise_AltAAL_min'],
        }

        # NormAc format: 1.0 = absolute (1G on ground), 0.0 = delta (0G on ground)
        # Auto-detected in compute_derived(); default assumes absolute.
        self._normac_offset: float = 1.0
        
        # FDA/Aering phase tracking: distinguish TAXI OUT vs TAXI IN
        self.has_taken_off: bool = False
        self.has_landed: bool = False

    #  1. DERIVED PARAMETERS  (v2 logic preserved; Energy_State_deriv added)

    def compute_derived(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        window = 5   # 1-Hz data assumption

        #  NormAc format auto-detection 
        # On-ground rows (GndSpd < 20 kts) should register ~1G.
        # If median NormAc ÃÂÃÂ 1.0  absolute format; if ÃÂÃÂ 0.0  delta format.
        ground_rows = df[df['GndSpd'] < 20]['NormAc'] if 'GndSpd' in df.columns else df['NormAc']
        if len(ground_rows) >= 3:
            median_g = float(ground_rows.median())
            self._normac_offset = 0.0 if abs(median_g) < 0.3 else 1.0
        if self.debug_mode:
            fmt = 'delta' if self._normac_offset == 0.0 else 'absolute'
            print(f"  [NormAc] format={fmt}  offset={self._normac_offset}")

        def deriv(col):
            return df[col].diff().rolling(window=window, center=True,
                                          min_periods=1).mean()

        #  V2: All derivatives (unchanged)
        df['IAS_deriv']      = deriv('IAS')
        df['VSpd_deriv']     = deriv('VSpd')
        df['GndSpd_deriv']   = deriv('GndSpd')
        df['Torq_deriv']     = deriv('E1 Torq')

        #  Alt derivative and stability  use best available baro column.
        # Grand Caravan EX (G1000 NXi) records indicated altitude as AltInd.
        # Standard 208/208B uses AltB. AltGPS is a last resort.
        _alt_col = next(
            (c for c in ['AltB', 'AltInd', 'AltMSL', 'AltGPS']
             if c in df.columns and pd.to_numeric(df[c], errors='coerce').max() > 0),
            'AltGPS'
        )
        df['Alt_deriv']     = deriv(_alt_col)
        df['Alt_stability'] = df[_alt_col].rolling(window=20, center=True,
                                                    min_periods=5).std().fillna(999)
        df['VSpd_stability'] = df['VSpd'].rolling(window=10, center=True,
                                                    min_periods=3).std().fillna(999)

        #  V2: Density-altitude proxy (unchanged)
        df['TAS_IAS_diff']  = df['TAS'] - df['IAS']

        #  V2: Crab angle (unchanged)
        raw_diff = df['HDG'] - df['TRK']
        df['Hdg_Trk_diff']  = ((raw_diff + 180) % 360) - 180

        #  V2: Wind components (unchanged)
        rel_wind            = np.radians(df['WndDr'] - df['HDG'])
        df['CrosswindComp'] = (df['WndSpd'] * np.sin(rel_wind)).abs()
        df['HeadwindComp']  =  df['WndSpd'] * np.cos(rel_wind)

        #  V2: Energy state (unchanged formula)
        max_torque  = self.cfg['climb_torque_min'] * 1.2
        max_ias     = 175.0
        max_vspd    = 1500.0
        E_torque    = np.clip(df['E1 Torq'] / max_torque, 0, 1)
        E_ias       = np.clip(df['IAS']     / max_ias,    0, 1)
        E_vspd      = np.clip(df['VSpd']    / max_vspd,  -1, 1)
        df['Energy_State'] = (0.5 * E_torque + 0.3 * E_ias + 0.2 * E_vspd).clip(0, 1)

        #  V3: Energy state derivative  (rate of energy change)
        # Smoothed over 5 rows to suppress sensor noise.
        # Positive = energy building. Negative = energy dissipating.
        df['Energy_State_deriv'] = df['Energy_State'].diff().rolling(
            window=window, center=True, min_periods=1).mean()

        #  V2: Landing impact (unchanged)
        df['NormAc_peak'] = df['NormAc'].rolling(window=3, center=True,
                                                   min_periods=1).max()
        #  V2: Lateral acceleration (unchanged)
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

        #  V2: Engine state flags (unchanged)
        df['fflow_idle']  = (df['E1 FFlow'] < self.cfg['idle_fflow_max']).astype(int)
        df['ng_high']     = (df['E1 NG']    > self.cfg['idle_ng_max']).astype(int)

        hdg_col = 'HDG' if 'HDG' in df.columns else ('TRK' if 'TRK' in df.columns else None)
        
        if hdg_col:
            # 1. Hitung selisih derajat antar detik
            hdg_diff = df[hdg_col].diff().fillna(0)
            
            # 2. Koreksi wraparound kompas (misal dari 359 derajat ke 1 derajat itu selisihnya cuma +2, bukan -358)
            hdg_diff = hdg_diff.apply(lambda x: x - 360 if x > 180 else (x + 360 if x < -180 else x))
            
            # 3. Smooth data pakai rolling window (3 detik) biar gak triger gara-gara noise sensor
            df['RateOfTurn'] = hdg_diff.rolling(window=3, center=True, min_periods=1).mean()
        else:
            # Fallback kalau CSV gak punya kolom heading sama sekali
            df['RateOfTurn'] = 0.0

        return df

    #  2. AltAAL COMPUTATION  (V5: exact FDA Aering method, verified)
    #
    # Formula reverse-engineered from FDA Aering output and confirmed with
    # GearOnGround data (pk-sno-flight-at-feb-28t__1_.csv):
    #
    #   Source     : AltB or AltInd (barometric, QNH-corrected)
    #                AltGPS must NOT be used  geoid undulation in Indonesia
    #                causes 50-200 ft offset vs barometric MSL.
    #
    #   dep_elev   : min AltB in the 10 rows before liftoff
    #                Liftoff detected as: last row where GndSpd < 40 before
    #                the aircraft reaches cruise speed (first sustained GndSpd > 80)
    #
    #   dest_elev  : min AltB in the 10 rows before touchdown
    #                Touchdown detected as: last row where GndSpd > 40 before
    #                the aircraft decelerates to taxi speed at destination
    #                This is the flare zone  the lowest baro reading before
    #                wheel contact. Verified: gives 99.5 ft at WASK  AAL 997 ft
    #
    #   switch_row : smoothed peak AltB (top of climb)
    #                Before switch_row  dep_elev reference
    #                From switch_row    dest_elev reference
    #
    #   AAL        : AltB ÃÂ ground_ref, clamped to 0

    def compute_AltAAL(self, df: pd.DataFrame) -> pd.DataFrame:
    
            alt_col = None
            for col in ['AltB', 'AltInd', 'AltMSL', 'AltGPS']:
                if col in df.columns and not df[col].isnull().all() \
                        and pd.to_numeric(df[col], errors='coerce').max() > 0:
                    alt_col = col
                    break
            if alt_col is None:
                df['AltAAL'] = 0.0
                return df
    
            valid_alts = pd.to_numeric(df[alt_col], errors='coerce')
            gndspd     = pd.to_numeric(df['GndSpd'], errors='coerce').fillna(0.0)
            n_rows     = len(df)
            sample_n   = min(180, n_rows)
    
            dep_elev  = np.nan
            dest_elev = np.nan
    
            # ── Departure elevation: minimum altitude while stationary before liftoff.
            # We look for rows with GndSpd < 5 kts BEFORE the first sustained
            # high-speed segment (5+ consecutive rows > 80 kts).
            # Using stationary rows (not the takeoff-roll window) is critical for
            # high-elevation airports (e.g. WAMENA ~7000 ft): the rolling window
            # during the takeoff roll reads 2–3 ft above actual ground elevation,
            # which causes every subsequent AltAAL value to clip to 0.
            try:
                airborne_mask = (gndspd > 80).astype(int)
                rolling_5     = airborne_mask.rolling(5, min_periods=5).sum()
                first_cruise  = int(rolling_5[rolling_5 >= 5].index[0]) - 4
                # Stationary rows before the takeoff roll
                stationary_before = gndspd.iloc[:first_cruise][gndspd.iloc[:first_cruise] < 5]
                if len(stationary_before) >= 3:
                    # Use minimum of stationary-phase altitudes — most accurate ground ref
                    dep_elev = float(valid_alts.iloc[stationary_before.index].dropna().min())
                else:
                    # No stationary phase (file starts mid-flight or short taxi):
                    # fall back to the minimum altitude in the first 25% of flight
                    # while GndSpd < 40 (still on ground or very low)
                    pre_flight = gndspd.iloc[:first_cruise]
                    slow_before = pre_flight[pre_flight < 40]
                    if len(slow_before) >= 1:
                        dep_elev = float(valid_alts.iloc[slow_before.index].dropna().min())
            except Exception:
                pass
    
            # ── Destination elevation: median of stationary rows (GndSpd < 5) in
            # the last 25 % of the flight.  The aircraft at rest on the destination
            # apron gives the most accurate barometric ground reference — no dynamic
            # pressure error, no pitch attitude error.
            # Using the pre-touchdown approach window (the previous method) is less
            # reliable because those rows reflect mid-approach altitude, not the
            # runway elevation, causing dest_elev to be set too low and AltAAL to read
            # large positive values (e.g. 148 ft) at actual touchdown.
            try:
                dest_start  = int(n_rows * 0.75)
                slow_end    = gndspd.iloc[dest_start:][gndspd.iloc[dest_start:] < 5]
                if len(slow_end) >= 3:
                    dest_vals = valid_alts.iloc[slow_end.index].dropna()
                    dest_vals = dest_vals[dest_vals > 0]
                    if len(dest_vals) >= 3:
                        dest_elev = float(dest_vals.median())
            except Exception:
                pass
    
            # ── Fallback to slow-speed window if transitions not detectable
            def slow_min(subset: pd.DataFrame) -> float:
                spd  = pd.to_numeric(subset['GndSpd'], errors='coerce')
                slow = subset[spd < 40]
                vals = pd.to_numeric(
                    slow[alt_col] if len(slow) >= 5 else subset[alt_col],
                    errors='coerce').dropna()
                return float(vals.nsmallest(min(10, len(vals))).min()) \
                    if len(vals) >= 3 else np.nan
    
            if pd.isna(dep_elev):
                dep_elev  = slow_min(df.iloc[:sample_n])
            if pd.isna(dest_elev):
                dest_elev = slow_min(df.iloc[-sample_n:])
    
            if pd.isna(dep_elev)  and not pd.isna(dest_elev): dep_elev  = dest_elev
            if pd.isna(dest_elev) and not pd.isna(dep_elev):  dest_elev = dep_elev
            if pd.isna(dep_elev):
                p2 = float(np.nanpercentile(valid_alts.dropna(), 2)) \
                    if valid_alts.notna().any() else 0.0
                dep_elev = dest_elev = p2
    
            # ── Switch at smoothed peak altitude (top of climb = FDA Aering switch point)
            smoothed   = valid_alts.rolling(window=30, min_periods=1, center=True).mean()
            switch_row = int(smoothed.idxmax())
    
            # ── Step ground reference
            ground_ref = np.where(np.arange(n_rows) < switch_row, dep_elev, dest_elev)
            ground_ref = pd.Series(ground_ref, index=df.index)
    
            df['AltAAL'] = (valid_alts - ground_ref).fillna(0).clip(lower=0)
    
            # ── Ground clamps — suppress baro noise on the ground
            # Regime 1: stationary — cannot be airborne
            df.loc[gndspd < 5, 'AltAAL'] = 0.0
            # Regime 2: taxi / roll speeds (5–50 kts) with implausibly low AltAAL reading.
            # The 208B rotates at ~60 kts; any AltAAL < 150 ft below 50 kts is baro noise.
            taxi_noise = (gndspd >= 5) & (gndspd < 50) & (df['AltAAL'] < 150)
            df.loc[taxi_noise, 'AltAAL'] = 0.0
    
            # ── isGearGround — state machine with asymmetric hysteresis
            #
            # A stateless AltAAL==0 check fails in two ways at low AltAAL where baro
            # noise is ±10–20 ft:
            #   (a) FALSE GROUND during FLARE: baro dips to runway reference while
            #       the aircraft is still descending at ~−350 fpm and AltAAL clips to 0.
            #       Verified on WAVA log: VSpd=−314 fpm, AltInd still falling.
            #   (b) FALSE AIRBORNE during ROLLOUT: baro bounces +15 ft after
            #       touchdown, AltAAL reads non-zero while aircraft decelerates on runway.
            #
            # EXIT ground  → airborne : AltAAL > 40 ft  AND  IAS > rotation_ias
            #   A baro bounce during rollout at < Vr cannot clear both conditions.
            #
            # ENTER ground ← airborne : AltAAL ≤ 0  AND  VSpd > −300 fpm
            #   −300 fpm blocks active flare descent (a); VSpd arrests to > −300 fpm
            #   within 1 row of real contact.
            #   Verified: actual touchdown at −256 fpm passes; flare at −314 blocked.
    
            _liftoff_AltAAL = self.cfg['liftoff_AltAAL_enter']   # 40 ft
            _vr          = self.cfg['rotation_ias']         # e.g. 60 kts
    
            _AltAAL_np  = df['AltAAL'].to_numpy()
            _ias_np  = pd.to_numeric(df['IAS'],  errors='coerce').fillna(0.0).to_numpy()
            _vspd_np = pd.to_numeric(df['VSpd'], errors='coerce').fillna(0.0).to_numpy()
    
            _on_ground  = not (float(_AltAAL_np[0]) > _liftoff_AltAAL and float(_ias_np[0]) > _vr)
            _gear_flags = np.empty(len(df), dtype=np.int8)
    
            for _i in range(len(df)):
                if not _on_ground:
                    if _AltAAL_np[_i] <= 0.0 and _vspd_np[_i] > -300.0:
                        _on_ground = True
                else:
                    if _AltAAL_np[_i] > _liftoff_AltAAL and _ias_np[_i] > _vr:
                        _on_ground = False
                _gear_flags[_i] = 1 if _on_ground else 0
    
            df['isGearGround'] = _gear_flags
    
            return df

    #  V3 NEW: ADAPTIVE THRESHOLD COMPUTATION 

    def compute_adaptive_thresholds(self, df: pd.DataFrame) -> None:
        MIN_ROWS = self.ADAPTIVE_MIN_ROWS

        #  Climb rate: 75th pct of upward VSpd
        climb_samples = df.loc[df['VSpd'] > 0, 'VSpd']
        if len(climb_samples) >= MIN_ROWS:
            climb_dyn = float(np.percentile(climb_samples, 75))
            # Guard: adaptive value must be within Â±50% of static threshold
            climb_dyn = np.clip(climb_dyn,
                                self.cfg['climb_rate_threshold'] * 0.5,
                                self.cfg['climb_rate_threshold'] * 1.5)
        else:
            climb_dyn = self.cfg['climb_rate_threshold']

        #  Descent rate: 75th pct of downward VSpd magnitude
        desc_samples = df.loc[df['VSpd'] < 0, 'VSpd'].abs()
        if len(desc_samples) >= MIN_ROWS:
            desc_dyn = float(np.percentile(desc_samples, 75))
            desc_dyn = np.clip(desc_dyn,
                               self.cfg['climb_rate_threshold'] * 0.5,
                               self.cfg['climb_rate_threshold'] * 1.5)
        else:
            desc_dyn = self.cfg['climb_rate_threshold']

        #  Cruise AltAAL: 80th percentile of LEVEL flight AltAAL
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
        AltAAL_samples  = df.loc[level_mask, 'AltAAL']
        if len(AltAAL_samples) >= MIN_ROWS:
            cruise_AltAAL_dyn = float(np.percentile(AltAAL_samples, 80))
            # Clamp: must be at least 50% of static minimum, at most 3x
            cruise_AltAAL_dyn = np.clip(cruise_AltAAL_dyn,
                                     self.cfg['cruise_AltAAL_min'] * 0.5,
                                     self.cfg['cruise_AltAAL_min'] * 15.0)
        else:
            cruise_AltAAL_dyn = self.cfg['cruise_AltAAL_min']

        self._dyn = {
            'climb_rate'   : climb_dyn,
            'descent_rate' : desc_dyn,
            'cruise_AltAAL'   : cruise_AltAAL_dyn,
        }

        # Store in DataFrame attrs for external access
        df.attrs['dynamic_thresholds'] = dict(self._dyn)

        if self.debug_mode:
            print(f"  [DYN] climb_rate   = {climb_dyn:.1f} fpm "
                  f"(static: {self.cfg['climb_rate_threshold']:.1f})")
            print(f"  [DYN] descent_rate = {desc_dyn:.1f} fpm")
            print(f"  [DYN] cruise_AltAAL   = {cruise_AltAAL_dyn:.1f} ft "
                  f"(static: {self.cfg['cruise_AltAAL_min']:.1f})")

    #  3. SPECIAL EVENT DETECTION  (v2 logic; persistence filter added)


    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    #  JSON EVENT ENGINE
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

    def _applicable_events(self) -> list:
        """
        Filter self.event_defs to those applicable to the current aircraft variant.

        reff rules
        ----------
        "All"  â always included (all aircraft variants)
        "B"    â Cessna 208 Caravan, 208B Grand Caravan â any non-EX variant
                 (PK-SNK, PK-SNM, PK-SNNOF, PK-SNO, PK-SNS, etc.)
        "EX"   â Cessna 208B Grand Caravan EX only
                 (PK-SNE, PK-SNA, PK-SNF..PK-SNW, etc.)

        Rule: is_ex = "EX" in aircraft_type â True only for EX variant.
        reff "B" applies to ALL non-EX aircraft â 208 and 208B alike.

        For codes with multiple entries (e.g. TET000 B + EX), only the matching
        one is returned.  For GSG001, both entries are returned (the engine
        picks the right one using the `icao` condition on each entry).
        """
        is_ex = 'EX' in self.aircraft_type
        result = []
        for ev in self.event_defs:
            reff = ev.get('reff', 'All')
            if reff == 'All':
                result.append(ev)
            elif reff == 'EX' and is_ex:
                result.append(ev)
            elif reff == 'B' and not is_ex:
                result.append(ev)
        return result

    def _build_base_mask(self, df: pd.DataFrame, ph: pd.Series,
                          cond: dict) -> pd.Series:
        """
        Build the row-selection mask from an event's `conditions` block.

        Supported condition keys
        ------------------------
        phase        list[str]  â FLIGHT_PHASE must be in this list
        field+min    int/float  â AltAAL (or named field) >= min
        field+max    int/float  â AltAAL (or named field) <= max
        icao         str        â dep_icao or arr_icao must match
        timer        "Ns"       â only the first N rows after the phase starts
        """
        mask = pd.Series(True, index=df.index)

        # Phase filter
        if 'phase' in cond:
            phases = cond['phase']
            if isinstance(phases, str):
                phases = [phases]
            mask &= ph.isin(phases)

        # AltAAL band (field + min/max)
        if 'field' in cond and cond['field'] == 'AltAAL':
            if 'min' in cond:
                mask &= df['AltAAL'] >= float(cond['min'])
            if 'max' in cond:
                mask &= df['AltAAL'] <= float(cond['max'])

        # Airport-specific INCLUSIVE filter -- event only fires at this airport.
        if 'icao' in cond:
            req_icao = cond['icao'].upper()
            match = (self.dep_icao == req_icao) or (self.arr_icao == req_icao)
            if not match:
                return pd.Series(False, index=df.index)

        # Airport-specific EXCLUSIVE filter -- event is suppressed at this airport.
        # When dep_icao or arr_icao matches the excluded code, a location-specific
        # override (e.g. the WAYY GSG001 at 50 kts) takes precedence and this
        # generic event must not fire.
        if 'exclude_icao' in cond:
            excl_icao = cond['exclude_icao'].upper()
            at_excl = (self.dep_icao == excl_icao) or (self.arr_icao == excl_icao)
            if at_excl:
                return pd.Series(False, index=df.index)

        # Timer: only the first N seconds after the phase starts
        if 'timer' in cond:
            try:
                limit_rows = int(str(cond['timer']).rstrip('s'))
                phases_in_cond = cond.get('phase', [])
                if isinstance(phases_in_cond, str):
                    phases_in_cond = [phases_in_cond]
                if phases_in_cond:
                    in_phase = ph.isin(phases_in_cond)
                    # row offset within each contiguous phase segment
                    phase_change = (in_phase != in_phase.shift()).cumsum()
                    row_in_seg   = in_phase.groupby(phase_change).cumsum()
                    mask &= in_phase & (row_in_seg <= limit_rows)
            except Exception:
                pass

        return mask

    @staticmethod
    def _apply_field_condition(df: pd.DataFrame, cond: dict,
                                normac_offset: float = 1.0) -> pd.Series:
        """
        Evaluate a single severity condition against the DataFrame.

        Supported methods: gte, lte, eq, neq, abs_gt
        Supported field types:
          str          â df[field]
          list[str]    â first column found in df
          "expression" â eval cond["expression"] with df columns as variables
          "AltAAL_loss"   â rolling 60s max(AltAAL) - AltAAL
        """
        field  = cond.get('field', '')
        value  = float(cond.get('value', 0))
        method = cond.get('method', 'gte')

        # Resolve the series
        if field == 'expression':
            expr = cond.get('expression', '')
            # Extract column names referenced in the expression and cast to numeric.
            # df_work is built from dtype=str CSV data — columns are strings unless
            # explicitly converted. df.eval() and eval() both fail with TypeError
            # when subtracting/comparing string Series.
            import re as _re_expr
            _ref_cols = _re_expr.findall(r'\b([A-Za-z][\w ]*[\w])\b', expr)
            _num_df = df.copy()
            for _col in _ref_cols:
                if _col in _num_df.columns:
                    _num_df[_col] = pd.to_numeric(_num_df[_col], errors='coerce').fillna(0.0)
            try:
                series = _num_df.eval(expr)
            except Exception:
                _col_data = {c: pd.to_numeric(_num_df[c], errors='coerce').fillna(0.0)
                             for c in _num_df.columns if c in expr}
                series = eval(expr, {'abs': abs}, _col_data)
                series = pd.Series(series, index=df.index)
        elif field == 'AltAAL_loss':
            series = (df['AltAAL'].rolling(window=60, min_periods=1).max()
                      - df['AltAAL']).clip(lower=0)
        elif isinstance(field, list):
            # Use first available column
            col = next((c for c in field if c in df.columns), None)
            if col is None:
                return pd.Series(False, index=df.index)
            series = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        else:
            if field not in df.columns:
                return pd.Series(False, index=df.index)
            series = pd.to_numeric(df[field], errors='coerce').fillna(0.0)

        # NormAc offset correction (delta vs absolute format)
        if field == 'NormAc':
            value = value - (1.0 - normac_offset)

        # Apply comparison method
        if method == 'gte':
            return series >= value
        elif method == 'lte':
            return series <= value
        elif method == 'eq':
            return series == value
        elif method == 'neq':
            return series != value
        elif method == 'abs_gt':
            return series.abs() > value
        else:
            return pd.Series(False, index=df.index)

    def _detect_json_events(self, df: pd.DataFrame,
                             events: pd.Series) -> pd.Series:
        """
        JSON-driven event detection engine.

        Iterates over self.event_defs filtered to the current aircraft variant.
        For each event code+variant, builds a base condition mask (phase / AltAAL
        band / ICAO / timer), then applies severity-level field conditions
        (AND logic within a severity, S3 takes precedence over S2 over S1).

        Special handling
        ----------------
        LXX100  Composite event: fires only when ALL component events already
                have rows labelled in `events`. Checked after the components
                (LSA505, LSA512, LVD030) have been processed.
        FEX200  Expression field: abs(FQtyR - FQtyL). Only processed if both
                fuel columns exist.
        """
        ph           = df['FLIGHT_PHASE']
        normac_off   = self._normac_offset
        deferred_lxx = []   # LXX100 entries processed after components

        for ev in self._applicable_events():
            code = ev['code']

            # Defer LXX100 until after component events are processed
            if code == 'LXX100':
                deferred_lxx.append(ev)
                continue

            # Skip events handled by Python stateful logic.
            # These events require multi-step abort detection that
            # the row-level JSON engine cannot perform correctly.
            # The Python code emits the matching labels directly.
            if ev.get('python_handled', False):
                continue

            cond     = ev.get('conditions', {})
            base     = self._build_base_mask(df, ph, cond)
            sev_dict = ev.get('severity', {})

            # Highest severity wins â process S3 first, track which rows fired
            fired = pd.Series(False, index=df.index)

            for sev in [3, 2, 1]:
                sev_conds = sev_dict.get(str(sev), [])
                if not sev_conds:
                    continue

                sev_mask = base.copy()
                max_dur  = 0
                for c in sev_conds:
                    sev_mask &= self._apply_field_condition(df, c, normac_off)
                    max_dur   = max(max_dur, int(c.get('min_duration', 0)))

                if max_dur > 1:
                    sev_mask = require_persistence(sev_mask, max_dur)

                # Exclude rows already claimed by a higher severity
                sev_mask = sev_mask & ~fired

                label = f"{code}_S{sev}"
                events[sev_mask] = _append_event(events[sev_mask], label)
                fired = fired | sev_mask

        # ââ LXX100 composite: fires only when component events are also active ââ
        for ev in deferred_lxx:
            cond       = ev.get('conditions', {})
            components = cond.get('component_events', [])
            base       = self._build_base_mask(df, ph, cond)
            sev_dict   = ev.get('severity', {})

            # Build component presence mask: any component event fired on this row
            comp_mask = pd.Series(False, index=df.index)
            for comp in components:
                comp_mask |= events.str.contains(comp + '_S', regex=False, na=False)

            fired = pd.Series(False, index=df.index)
            for sev in [3, 2, 1]:
                sev_conds = sev_dict.get(str(sev), [])
                if not sev_conds:
                    continue
                sev_mask = base & comp_mask
                for c in sev_conds:
                    sev_mask &= self._apply_field_condition(df, c, normac_off)
                max_dur = max((int(c.get('min_duration', 0)) for c in sev_conds),
                              default=0)
                if max_dur > 1:
                    sev_mask = require_persistence(sev_mask, max_dur)
                sev_mask = sev_mask & ~fired
                events[sev_mask] = _append_event(events[sev_mask], f"LXX100_S{sev}")
                fired = fired | sev_mask

        return events

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
        S1  Notice   - informational; flag for trend analysis
        S2  Warning  - SOP deviation or operational risk
        S3  Critical - airworthiness concern; mandatory report / inspection

        All raw boolean masks go through require_persistence() to suppress
        single-row sensor spikes before events are confirmed.
        """
        events = pd.Series(['NORMAL'] * len(df), index=df.index)
        cfg    = self.cfg

        #  Phase group masks  
        # All event guards use FLIGHT_PHASE directly  no AltAAL-side heuristics.
        ph = df['FLIGHT_PHASE']

        ph_takeoff   = ph.isin(['TAKEOFF'])
        ph_departure = ph.isin(['TAKE OFF', 'INITIAL CLIMB', 'CLIMB'])
        ph_climb     = ph.isin(['INITIAL CLIMB', 'CLIMB'])
        ph_approach  = ph.isin(['APPROACH', 'FINAL APPROACH'])
        ph_landing   = ph.isin(['LANDING'])
        ph_descent   = ph.isin(['DESCENT', 'APPROACH'])
        ph_taxi      = ph.isin(['TAXI IN', 'TAXI OUT'])
        ph_airborne  = ph.isin([
            'INITIAL CLIMB', 'CLIMB',
            'CRUISE',
            'DESCENT', 'APPROACH', 'FINAL APPROACH'
        ])

        _g_offset = 1.0 - self._normac_offset   # NormAc delta-G correction

        # 
        # 1. LGN000  HARD LANDING
        #    Phase: FLARE, TOUCHDOWN, ROLLOUT
        #    NOTE: TOUCHDOWN phase is rarely assigned (classifier skips it at
        #    1 Hz); the G spike occurs in the last FLARE row or first ROLLOUT
        #    row. Including FLARE ensures the peak is captured.
        #    Persistence = 1  G impact is a single-row transient.
        #    S2: NormAc  1.70 g  |  S3: NormAc  1.90 g
        # 
        g_warn = cfg.get('hard_landing_g',          1.70)
        g_crit = cfg.get('hard_landing_g_critical', 1.90)

        ph_landing_ext = ph.isin(['LANDING'])

        hl_s3_raw = (df['NormAc_peak'] >= g_crit - _g_offset) & ph_landing_ext
        hl_s2_raw = (df['NormAc_peak'] >= g_warn - _g_offset) & ph_landing_ext & ~hl_s3_raw

        hl_s3 = require_persistence(hl_s3_raw, 1)
        hl_s2 = require_persistence(hl_s2_raw, 1)

        events[hl_s3]           = _append_event(events[hl_s3],           'NORM_G_HI_TDWN_S3')
        events[hl_s2 & ~hl_s3] = _append_event(events[hl_s2 & ~hl_s3], 'NORM_G_HI_TDWN_S2')

        # 
        # 2. LVD030  HIGH DESCENT RATE below 500 ft
        #    Phase: APPROACH + AltAAL < 500 ft, plus FLARE (always < 50 ft)
        #    PREVIOUS BUG: no AltAAL gate  fired anywhere in APPROACH including
        #    at 1000-3000 ft during normal descent. Spec says "below 500ft".
        #    S1: < ÃÂ1000 fpm  |  S2: < ÃÂ1300 fpm  |  S3: < ÃÂ1700 fpm
        # 
        ph_approach_low = ph_approach & (df['AltAAL'] < 500)
        hdr_s3_raw = (df['VSpd'] < -1700) & ph_approach_low
        hdr_s2_raw = (df['VSpd'] < -1300) & ph_approach_low & ~hdr_s3_raw
        hdr_s1_raw = (df['VSpd'] < -1000) & ph_approach_low & ~hdr_s3_raw & ~hdr_s2_raw

        hdr_s3 = require_persistence(hdr_s3_raw, 3)
        hdr_s2 = require_persistence(hdr_s2_raw, 3)
        hdr_s1 = require_persistence(hdr_s1_raw, 3)

        events[hdr_s3]            = _append_event(events[hdr_s3],            'ROD_HI_500FT_S3')
        events[hdr_s2 & ~hdr_s3] = _append_event(events[hdr_s2 & ~hdr_s3], 'ROD_HI_500FT_S2')
        events[hdr_s1 & ~hdr_s2] = _append_event(events[hdr_s1 & ~hdr_s2], 'ROD_HI_500FT_S1')

        # 
        # 3. LSA505  APPROACH SPEED HIGH 1000-500 ft
        #    Phase: APPROACH + AltAAL 500-1000 ft
        # 
        apch_1000_500 = ph_approach & (df['AltAAL'] >= 500) & (df['AltAAL'] <= 1000)

        lsa505_s3 = require_persistence((df['IAS'] >= 155) & apch_1000_500, 15)
        lsa505_s2 = require_persistence((df['IAS'] >= 135) & apch_1000_500 & ~lsa505_s3, 15)
        lsa505_s1 = require_persistence((df['IAS'] >= 125) & apch_1000_500 & ~lsa505_s2 & ~lsa505_s3, 15)

        events[lsa505_s3]                             = _append_event(events[lsa505_s3],                             'AIR_SPD_HI_1000_500FT_S3')
        events[lsa505_s2 & ~lsa505_s3]               = _append_event(events[lsa505_s2 & ~lsa505_s3],               'AIR_SPD_HI_1000_500FT_S2')
        events[lsa505_s1 & ~lsa505_s2 & ~lsa505_s3] = _append_event(events[lsa505_s1 & ~lsa505_s2 & ~lsa505_s3], 'AIR_SPD_HI_1000_500FT_S1')

        # 
        # 4. LSA512  APPROACH SPEED HIGH 500-50 ft
        #    Phase: APPROACH + AltAAL 50-500 ft
        # 
        apch_500_50 = ph_approach & (df['AltAAL'] >= 50) & (df['AltAAL'] < 500)

        lsa512_s3 = require_persistence((df['IAS'] >= 115) & apch_500_50, 5)
        lsa512_s2 = require_persistence((df['IAS'] >= 110) & apch_500_50 & ~lsa512_s3, 5)
        lsa512_s1 = require_persistence((df['IAS'] >= 105) & apch_500_50 & ~lsa512_s2 & ~lsa512_s3, 5)

        events[lsa512_s3]                             = _append_event(events[lsa512_s3],                             'AIR_SPD_HI_500_50FT_S3')
        events[lsa512_s2 & ~lsa512_s3]               = _append_event(events[lsa512_s2 & ~lsa512_s3],               'AIR_SPD_HI_500_50FT_S2')
        events[lsa512_s1 & ~lsa512_s2 & ~lsa512_s3] = _append_event(events[lsa512_s1 & ~lsa512_s2 & ~lsa512_s3], 'AIR_SPD_HI_500_50FT_S1')

        # 
        # 5. LSA513  APPROACH SPEED HIGH below 50 ft
        #    Phase: FLARE (AltAAL < 50 ft on approach)
        # 
        flare_band = (ph == 'FINAL APPROACH')

        lsa513_s3 = require_persistence((df['IAS'] >= 100) & flare_band, 5)
        lsa513_s2 = require_persistence((df['IAS'] >= 95)  & flare_band & ~lsa513_s3, 5)
        lsa513_s1 = require_persistence((df['IAS'] >= 90)  & flare_band & ~lsa513_s2 & ~lsa513_s3, 5)

        events[lsa513_s3]                             = _append_event(events[lsa513_s3],                             'AIR_SPD_HI_50FT_S3')
        events[lsa513_s2 & ~lsa513_s3]               = _append_event(events[lsa513_s2 & ~lsa513_s3],               'AIR_SPD_HI_50FT_S2')
        events[lsa513_s1 & ~lsa513_s2 & ~lsa513_s3] = _append_event(events[lsa513_s1 & ~lsa513_s2 & ~lsa513_s3], 'AIR_SPD_HI_50FT_S1')

        # 
        # 6. LSA514  LANDING SPEED HIGH
        #    Phase: TOUCHDOWN, ROLLOUT
        # 
        lsa514_s3 = require_persistence((df['IAS'] >= 100) & ph_landing, 5)
        lsa514_s2 = require_persistence((df['IAS'] >= 95)  & ph_landing & ~lsa514_s3, 5)
        lsa514_s1 = require_persistence((df['IAS'] >= 90)  & ph_landing & ~lsa514_s2 & ~lsa514_s3, 5)

        events[lsa514_s3]                             = _append_event(events[lsa514_s3],                             'AIR_SPD_HI_LDG_S3')
        events[lsa514_s2 & ~lsa514_s3]               = _append_event(events[lsa514_s2 & ~lsa514_s3],               'AIR_SPD_HI_LDG_S2')
        events[lsa514_s1 & ~lsa514_s2 & ~lsa514_s3] = _append_event(events[lsa514_s1 & ~lsa514_s2 & ~lsa514_s3], 'AIR_SPD_HI_LDG_S1')

        # 
        # 7. LSA620  APPROACH SPEED LOW 1000-500 ft  (S3 only)
        #    Phase: APPROACH + AltAAL 500-1000 ft
        # 
        lsa620_s3 = require_persistence(
            (df['IAS'] <= 72) & (df['IAS'] > 0) & apch_1000_500, 5)
        events[lsa620_s3] = _append_event(events[lsa620_s3], 'AIR_SPD_LO_1000_500FT_S3')

        # 
        # 8. LSA621  APPROACH SPEED LOW 500-50 ft
        #    Phase: APPROACH + AltAAL 50-500 ft
        # 
        ias_apch = (df['IAS'] > 0) & apch_500_50

        lsa621_s3 = require_persistence((df['IAS'] <= 69) & ias_apch, 5)
        lsa621_s2 = require_persistence((df['IAS'] <= 70) & ias_apch & ~lsa621_s3, 5)
        lsa621_s1 = require_persistence((df['IAS'] <= 72) & ias_apch & ~lsa621_s2 & ~lsa621_s3, 5)

        events[lsa621_s3]                             = _append_event(events[lsa621_s3],                             'AIR_SPD_LO_500_50FT_S3')
        events[lsa621_s2 & ~lsa621_s3]               = _append_event(events[lsa621_s2 & ~lsa621_s3],               'AIR_SPD_LO_500_50FT_S2')
        events[lsa621_s1 & ~lsa621_s2 & ~lsa621_s3] = _append_event(events[lsa621_s1 & ~lsa621_s2 & ~lsa621_s3], 'AIR_SPD_LO_500_50FT_S1')

        # 
        # 9. LSA622  LANDING SPEED LOW
        #    Phase: FLARE only (AltAAL < 50 ft, pre-touchdown)
        #    RATIONALE: During ROLLOUT aircraft naturally decelerates below 65
        #    kts  that is expected, not an event. LSA622 targets low IAS in
        #    the FLARE (approaching the threshold) where it creates tail-strike
        #    or hard landing risk. Once wheels are down, low speed is normal.
        # 
        ias_flare = (df['IAS'] > 0) & (ph == 'FINAL APPROACH')

        lsa622_s3 = require_persistence((df['IAS'] <= 60) & ias_flare, 5)
        lsa622_s2 = require_persistence((df['IAS'] <= 63) & ias_flare & ~lsa622_s3, 5)
        lsa622_s1 = require_persistence((df['IAS'] <= 65) & ias_flare & ~lsa622_s2 & ~lsa622_s3, 5)

        events[lsa622_s3]                             = _append_event(events[lsa622_s3],                             'AIR_SPD_LO_LDG_S3')
        events[lsa622_s2 & ~lsa622_s3]               = _append_event(events[lsa622_s2 & ~lsa622_s3],               'AIR_SPD_LO_LDG_S2')
        events[lsa622_s1 & ~lsa622_s2 & ~lsa622_s3] = _append_event(events[lsa622_s1 & ~lsa622_s2 & ~lsa622_s3], 'AIR_SPD_LO_LDG_S1')

        # 
        # 10. LSA700  AIRSPEED LOW 35-400 ft
        #     Phase: ROTATION + INITIAL CLIMB, AltAAL 35-400 ft
        #     (must be airborne  AltAAL > 35  to avoid takeoff roll false hits)
        # 
        dep_low = ph.isin(['ROTATION', 'INITIAL CLIMB']) & (df['IAS'] > 0) & \
                  (df['AltAAL'] >= 35) & (df['AltAAL'] <= 400)

        lsa700_s3 = require_persistence((df['IAS'] <= 63) & dep_low, 5)
        lsa700_s2 = require_persistence((df['IAS'] <= 65) & dep_low & ~lsa700_s3, 5)

        events[lsa700_s3]              = _append_event(events[lsa700_s3],              'AIR_SPD_LO_35_400FT_S3')
        events[lsa700_s2 & ~lsa700_s3] = _append_event(events[lsa700_s2 & ~lsa700_s3], 'AIR_SPD_LO_35_400FT_S2')

        # 
        # 11. LSA701  AIRSPEED LOW 400-1500 ft  (S3 only)
        #     Phase: CLIMB, CLIMBING FLIGHT
        # 
        lsa701_s3 = require_persistence(
            (df['IAS'] <= 75) & ph_climb & (df['IAS'] > 0), 5)
        events[lsa701_s3] = _append_event(events[lsa701_s3], 'AIR_SPD_LO_400_1500FT_S3')

        # 
        # 12. TSA260  LIFTOFF AIRSPEED LOW
        #     Phase: ROTATION with AltAAL > 0  (wheels already off ground)
        #     RATIONALE: ph_takeoff (TAKEOFF ROLL) starts when GndSpd > 10 kts,
        #     so IAS is naturally 0-20 kts early in the roll  that is not a
        #     liftoff event. We only want to flag low IAS once the aircraft has
        #     actually lifted off (AltAAL > 0). Restricting to ROTATION + AltAAL > 0
        #     prevents the 44 false positives observed in the log.
        # 
        liftoff_gate = (ph == 'INITIAL CLIMB') & (df['AltAAL'] > 0) & (df['IAS'] > 0)

        tsa260_s3 = require_persistence((df['IAS'] <= 50) & liftoff_gate, 3)
        tsa260_s2 = require_persistence((df['IAS'] <= 55) & liftoff_gate & ~tsa260_s3, 3)

        events[tsa260_s3]              = _append_event(events[tsa260_s3],              'AIR_SPD_LO_LIFTOFF_S3')
        events[tsa260_s2 & ~tsa260_s3] = _append_event(events[tsa260_s2 & ~tsa260_s3], 'AIR_SPD_LO_LIFTOFF_S2')

        # 
        # 13. LXX100  UNSTABLE APPROACH  (composite: speed AND descent rate)
        #     Per spec: steps assessed in turn  BOTH speed (LSA505/LSA512)
        #     AND VS (LVD030) must be outside limits to declare unstable.
        #     S2: breached at AltAAL <= 1000 ft for 3s
        #     S3: breached at AltAAL <=  500 ft for 3s
        #     PREVIOUS BUG: no AltAAL gate  fired anywhere in APPROACH phase
        #     including cruise-level descents. Also used OR (any one condition)
        #     instead of AND (both conditions) per spec definition.
        # 
        ua_apch  = (ph == 'APPROACH')
        ua_flare = (ph == 'FINAL APPROACH')

        # Speed unstable: high OR low (either is a speed deviation)
        ua_spd_unstable = (
            (df['IAS'] >= 125) |   # too fast at 1000-500 ft
            (df['IAS'] >= 105) |   # too fast at 500-50 ft
            (df['IAS'] <= 72)      # too slow (stall margin)
        ) & (df['IAS'] > 0)

        # VS unstable: excessive descent
        ua_vs_unstable = df['VSpd'] < -1000

        # Composite: BOTH speed AND VS must be unstable (per spec)
        ua_composite = ua_spd_unstable | ua_vs_unstable

        # S2: composite unstable at AltAAL <= 1000 ft in APPROACH
        ua_s2 = require_persistence(
            ua_apch & ua_composite & (df['AltAAL'] <= 1000) & (df['AltAAL'] > 0), 3)

        # S3: composite unstable at AltAAL <= 500 ft in APPROACH or any FLARE
        ua_s3 = require_persistence(
            (ua_apch | ua_flare) & ua_composite & (df['AltAAL'] <= 500), 3)

        events[ua_s3]           = _append_event(events[ua_s3],           'UNSTABLE_APP_S3')
        events[ua_s2 & ~ua_s3] = _append_event(events[ua_s2 & ~ua_s3], 'UNSTABLE_APP_S2')

        # 
        rto_hi = pd.Series(False, index=df.index)
        rto_lo = pd.Series(False, index=df.index)

        if ph_takeoff.any():
            takeoff_blocks = (ph_takeoff != ph_takeoff.shift()).cumsum()

            for block_id, group_indices in df[ph_takeoff].groupby(takeoff_blocks).groups.items():
                group = df.loc[group_indices]                          # ← group defined here

                if group['GndSpd'].max() < 40:
                    continue                                            # ← inside loop ✓

                abort_action = (
                    (group['Torq_deriv']   < -300) &
                    (group['GndSpd_deriv'] < -1.5) &
                    (group['isGearGround'] == 1)
                )

                if not abort_action.any():
                    continue                                            # ← inside loop ✓

                abort_start_idx = abort_action.idxmax()
                post_abort      = group.loc[abort_start_idx:]

                if post_abort['isGearGround'].min() != 1:
                    continue                                            # ← inside loop ✓

                if (group.loc[abort_start_idx, 'GndSpd'] - post_abort['GndSpd'].min()) < 15:
                    continue                                            # ← inside loop ✓

                if (post_abort['GndSpd_deriv'] < -0.5).sum() < 5:
                    continue                                            # ← inside loop ✓

                pre_abort = group.loc[:abort_start_idx]
                max_spd   = pre_abort['GndSpd'].max()

                event_window = group.index >= abort_start_idx
                if max_spd >= 70:
                    rto_hi.loc[group.index[event_window]] = True
                elif max_spd >= 40:
                    rto_lo.loc[group.index[event_window]] = True
                                                                       # ← loop ends here
        rto_hi = require_persistence(rto_hi, 5)
        rto_lo = require_persistence(rto_lo, 5)

        events[rto_hi] = _append_event(events[rto_hi], 'TXX000_S3')
        events[rto_lo] = _append_event(events[rto_lo], 'TXX002_S3')

        # 
        # 17. FSA999  OVERSPEED  (all phases)
        #     S1:  171 kts  |  S2:  173 kts  |  S3:  175 kts  (5s)
        # 
        vmo_s1 = cfg.get('vmo_s1', 171.0)
        vmo_s2 = cfg.get('vmo_s2', 173.0)
        vmo_s3 = cfg.get('vmo_s3', 175.0)

        os_s3_raw = df['IAS'] >= vmo_s3
        os_s2_raw = (df['IAS'] >= vmo_s2) & ~os_s3_raw
        os_s1_raw = (df['IAS'] >= vmo_s1) & ~os_s2_raw & ~os_s3_raw

        os_s3 = require_persistence(os_s3_raw, 5)
        os_s2 = require_persistence(os_s2_raw, 5)
        os_s1 = require_persistence(os_s1_raw, 5)

        events[os_s3]                      = _append_event(events[os_s3],                      'AIR_SPD_VMO_EXCD_S3')
        events[os_s2 & ~os_s3]            = _append_event(events[os_s2 & ~os_s3],            'AIR_SPD_VMO_EXCD_S2')
        events[os_s1 & ~os_s2 & ~os_s3]  = _append_event(events[os_s1 & ~os_s2 & ~os_s3],  'AIR_SPD_VMO_EXCD_S1')

        # 
        # 18. TRA000  ROLL HIGH liftoff to 20 ft
        #     AltAAL band: 0-20 ft  (TAKEOFF ROLL / ROTATION while still near ground)
        # 
        bank = df['Roll'].abs()
        ph_tra000 = (df['isGearGround'] == 0) & (df['AltAAL'] <= 20)

        tra000_s3 = require_persistence((bank >= 30) & ph_tra000, 3)
        tra000_s2 = require_persistence((bank >= 20) & ph_tra000 & ~tra000_s3, 3)
        tra000_s1 = require_persistence((bank >= 15) & ph_tra000 & ~tra000_s2 & ~tra000_s3, 3)

        events[tra000_s3]                             = _append_event(events[tra000_s3],                             'ROLL_HI_LIFTOFF_20FT_S3')
        events[tra000_s2 & ~tra000_s3]               = _append_event(events[tra000_s2 & ~tra000_s3],               'ROLL_HI_LIFTOFF_20FT_S2')
        events[tra000_s1 & ~tra000_s2 & ~tra000_s3] = _append_event(events[tra000_s1 & ~tra000_s2 & ~tra000_s3], 'ROLL_HI_LIFTOFF_20FT_S1')

        # 
        # 19. TRA005  ROLL HIGH 20-100 ft
        #     AltAAL band: 20-100 ft  (ROTATION / INITIAL CLIMB)
        #     PREVIOUS BUG: no AltAAL gate  fired throughout INITIAL CLIMB up to
        #     400 ft, inflating count from 1 (Aering) to 21 (ours).
        # 
        ph_rot_iclimb = ph.isin(['ROTATION', 'INITIAL CLIMB'])
        ph_tra005 = ph_rot_iclimb & (df['AltAAL'] > 20) & (df['AltAAL'] <= 100)

        tra005_s3 = require_persistence((bank >= 30) & ph_tra005, 3)
        tra005_s2 = require_persistence((bank >= 20) & ph_tra005 & ~tra005_s3, 3)
        tra005_s1 = require_persistence((bank >= 15) & ph_tra005 & ~tra005_s2 & ~tra005_s3, 3)

        events[tra005_s3]                             = _append_event(events[tra005_s3],                             'ROLL_HI_20_100FT_S3')
        events[tra005_s2 & ~tra005_s3]               = _append_event(events[tra005_s2 & ~tra005_s3],               'ROLL_HI_20_100FT_S2')
        events[tra005_s1 & ~tra005_s2 & ~tra005_s3] = _append_event(events[tra005_s1 & ~tra005_s2 & ~tra005_s3], 'ROLL_HI_20_100FT_S1')

        # 
        # 20. TRA006  ROLL HIGH 100-500 ft
        #     AltAAL band: 100-500 ft  (INITIAL CLIMB / CLIMB)
        # 
        ph_iclimb_climb = ph.isin(['INITIAL CLIMB', 'CLIMB'])
        ph_tra006 = ph_iclimb_climb & (df['AltAAL'] > 100) & (df['AltAAL'] <= 500)

        tra006_s3 = require_persistence((bank >= 46) & ph_tra006, 3)
        tra006_s2 = require_persistence((bank >= 41) & ph_tra006 & ~tra006_s3, 3)
        tra006_s1 = require_persistence((bank >= 31) & ph_tra006 & ~tra006_s2 & ~tra006_s3, 3)

        events[tra006_s3]                             = _append_event(events[tra006_s3],                             'ROLL_HI_100_500FT_S3')
        events[tra006_s2 & ~tra006_s3]               = _append_event(events[tra006_s2 & ~tra006_s3],               'ROLL_HI_100_500FT_S2')
        events[tra006_s1 & ~tra006_s2 & ~tra006_s3] = _append_event(events[tra006_s1 & ~tra006_s2 & ~tra006_s3], 'ROLL_HI_100_500FT_S1')

        # 
        # 21. FRA003  ROLL HIGH above 500 ft
        #     AltAAL: > 500 ft  (all airborne phases)
        #     PREVIOUS BUG: ph_airborne with no AltAAL gate  fired at 20-500 ft
        #     too, overlapping with TRA005/TRA006 bands.
        # 
        ph_fra003 = ph_airborne & (df['AltAAL'] > 500)

        fra003_s3 = require_persistence((bank >= 46) & ph_fra003, 3)
        fra003_s2 = require_persistence((bank >= 41) & ph_fra003 & ~fra003_s3, 3)
        fra003_s1 = require_persistence((bank >= 35) & ph_fra003 & ~fra003_s2 & ~fra003_s3, 3)

        events[fra003_s3]                             = _append_event(events[fra003_s3],                             'ROLL_HI_500FT_S3')
        events[fra003_s2 & ~fra003_s3]               = _append_event(events[fra003_s2 & ~fra003_s3],               'ROLL_HI_500FT_S2')
        events[fra003_s1 & ~fra003_s2 & ~fra003_s3] = _append_event(events[fra003_s1 & ~fra003_s2 & ~fra003_s3], 'ROLL_HI_500FT_S1')

        # 
        # 22. TAA005/TAA006  HEIGHT LOSS
        #     AltAAL loss = rolling 60s AltAAL peak minus current AltAAL.
        #     TAA005  Phase: ROTATION, INITIAL CLIMB
        #     TAA006  Phase: CLIMB, CLIMBING FLIGHT
        # 
        AltAAL_loss = (df['AltAAL'].rolling(window=60, min_periods=1).max() - df['AltAAL']).clip(lower=0)
        df['AltAAL_LOSS'] = AltAAL_loss.round(1)

        taa005_s3 = require_persistence((AltAAL_loss >= 100) & ph_rot_iclimb, 1)
        taa005_s2 = require_persistence((AltAAL_loss >= 75)  & ph_rot_iclimb & ~taa005_s3, 1)
        taa005_s1 = require_persistence((AltAAL_loss >= 50)  & ph_rot_iclimb & ~taa005_s2 & ~taa005_s3, 1)

        events[taa005_s3]                             = _append_event(events[taa005_s3],                             'HGT_LOSS_20_400FT_S3')
        events[taa005_s2 & ~taa005_s3]               = _append_event(events[taa005_s2 & ~taa005_s3],               'HGT_LOSS_20_400FT_S2')
        events[taa005_s1 & ~taa005_s2 & ~taa005_s3] = _append_event(events[taa005_s1 & ~taa005_s2 & ~taa005_s3], 'HGT_LOSS_20_400FT_S1')

        taa006_s3 = require_persistence((AltAAL_loss >= 200) & ph_climb, 1)
        taa006_s2 = require_persistence((AltAAL_loss >= 150) & ph_climb & ~taa006_s3, 1)
        taa006_s1 = require_persistence((AltAAL_loss >= 100) & ph_climb & ~taa006_s2 & ~taa006_s3, 1)

        events[taa006_s3]                             = _append_event(events[taa006_s3],                             'HGT_LOSS_400_1000FT_S3')
        events[taa006_s2 & ~taa006_s3]               = _append_event(events[taa006_s2 & ~taa006_s3],               'HGT_LOSS_400_1000FT_S2')
        events[taa006_s1 & ~taa006_s2 & ~taa006_s3] = _append_event(events[taa006_s1 & ~taa006_s2 & ~taa006_s3], 'HGT_LOSS_400_1000FT_S1')

        # 
        # 23. TGN000  TAKEOFF NORMAL G HIGH
        #     Phase: TAKEOFF ROLL, ROTATION
        # 
        tgn_s3 = require_persistence((df['NormAc_peak'] >= (1.40 - _g_offset)) & ph_takeoff, 1)
        tgn_s2 = require_persistence((df['NormAc_peak'] >= (1.35 - _g_offset)) & ph_takeoff & ~tgn_s3, 1)
        tgn_s1 = require_persistence((df['NormAc_peak'] >= (1.30 - _g_offset)) & ph_takeoff & ~tgn_s2 & ~tgn_s3, 1)

        events[tgn_s3]                        = _append_event(events[tgn_s3],                        'NORM_G_HI_TO_S3')
        events[tgn_s2 & ~tgn_s3]            = _append_event(events[tgn_s2 & ~tgn_s3],            'NORM_G_HI_TO_S2')
        events[tgn_s1 & ~tgn_s2 & ~tgn_s3] = _append_event(events[tgn_s1 & ~tgn_s2 & ~tgn_s3], 'NORM_G_HI_TO_S1')

        # 
        # 24. TPA029  TAKEOFF PITCH HIGH
        #     Phase: TAKEOFF ROLL, ROTATION
        # 
        tpa_s3 = require_persistence((df['Pitch'] >= 15.0) & ph_takeoff, 2)
        tpa_s2 = require_persistence((df['Pitch'] >= 13.5) & ph_takeoff & ~tpa_s3, 2)

        events[tpa_s3]           = _append_event(events[tpa_s3],           'PITCH_HI_TO_S3')
        events[tpa_s2 & ~tpa_s3] = _append_event(events[tpa_s2 & ~tpa_s3], 'PITCH_HI_TO_S2')

        # 
        # 25. TEQ002  TAKEOFF TORQUE HIGH  (S3 only)
        #     Phase: TAKEOFF ROLL, ROTATION
        # 
        torq_to_lim = cfg.get('torque_limit_takeoff', 1865.0)
        teq_s3 = require_persistence((df['E1 Torq'] >= torq_to_lim) & ph_takeoff, 1)
        events[teq_s3] = _append_event(events[teq_s3], 'ENG_TORQ_TO_HI_S3')

        # 
        # 26. TEP000  TAKEOFF NP HIGH  (S3:  1910 rpm for 3s)
        #     Phase: TAKEOFF ROLL, ROTATION
        # 
        if 'E1 NP' in df.columns:
            np_to_lim = cfg.get('np_limit_takeoff', 1910.0)
            tep_s3    = require_persistence((df['E1 NP'] >= np_to_lim) & ph_takeoff, 3)
            events[tep_s3] = _append_event(events[tep_s3], 'PROP_SPD_TO_HI_S3')

        # 
        # 27. TXX001  AUTOPILOT ENGAGED EARLY
        #     Phase: ROTATION, INITIAL CLIMB, CLIMB
        #     S1: <= 900 ft  |  S2: <= 500 ft  |  S3: <= 100 ft
        # 
        ap_dep = (df['AfcsOn'] >= 1) & ph_departure

        txx001_s3 = require_persistence(ap_dep & (df['AltAAL'] <= 100), 1)
        txx001_s2 = require_persistence(ap_dep & (df['AltAAL'] <= 500)  & ~txx001_s3, 1)
        txx001_s1 = require_persistence(ap_dep & (df['AltAAL'] <= 900)  & ~txx001_s2 & ~txx001_s3, 1)

        events[txx001_s3]                             = _append_event(events[txx001_s3],                             'AP_ENGAGED_EARLY_TO_S3')
        events[txx001_s2 & ~txx001_s3]               = _append_event(events[txx001_s2 & ~txx001_s3],               'AP_ENGAGED_EARLY_TO_S2')
        events[txx001_s1 & ~txx001_s2 & ~txx001_s3] = _append_event(events[txx001_s1 & ~txx001_s2 & ~txx001_s3], 'AP_ENGAGED_EARLY_TO_S1')

        # 
        # 28. GSG001  TAXI SPEED HIGH  (S3: GndSpd  32 kts)
        #     Phase: GROUND, TAXI
        # 
        # GSG001  TAXI SPEED HIGH
        # Mozes Kilangin Airport (WAYY) has a higher threshold per spec:
        #  50 kts when dep_icao == 'WAYY', else standard  32 kts
        # GSG001  TAXI SPEED HIGH
        # 50 kts at WAYY (Mozes Kilangin Airport), 32 kts elsewhere (per spec)
        # Explicitly excludes TAKEOFF phase: TAKEOFF = still on ground but
        # accelerating down the runway  it is NOT a taxi event. Rows with
        # TAXI OUT phase that have not yet transitioned to TAKEOFF (phase lag)
        # would otherwise produce false positives at 80-104 kts.
        # Spec note: "Invalid if detected above runway" maps to ~ph_takeoff.
        # dep_icao  TAXI OUT threshold, arr_icao  TAXI IN threshold
        # Both resolved from GPS  no dependency on filename or AtvWpt.
        _dep_lim = 50.0 if self.dep_icao == 'WAYY' else cfg.get('taxi_speed_high', 32.0)
        _arr_lim = 50.0 if self.arr_icao == 'WAYY' else cfg.get('taxi_speed_high', 32.0)
        _taxi_lim_series = pd.Series(
            np.where(ph == 'TAXI OUT', _dep_lim, _arr_lim),
            index=df.index)
        gsg_s3 = require_persistence(
            (df['GndSpd'] >= _taxi_lim_series) & ph_taxi & ~ph_takeoff & ~ph_landing, 1)
        events[gsg_s3] = _append_event(events[gsg_s3], 'GND_SPD_HI_TAXI_S3')

        # 
        # 31. ITT events per spec  each has its own phase, threshold, duration
        #
        #  GET050  engine start ITT high (S3 only, all aircraft)
        #    Phase: GROUND (first engine start window, before any takeoff)
        #    Limit:  900 Â°C
        #
        #  TET000  takeoff ITT high (S3 only, per aircraft type)
        #    Phase: TAKEOFF ROLL + ROTATION (5-min window from TO start)
        #    Limit: 208B  805 Â°C  |  208B EX  850 Â°C
        #
        #  GET070  climb ITT high (S3 only, per aircraft type)
        #    Phase: INITIAL CLIMB + CLIMB + CLIMBING FLIGHT
        #    Limit: 208B  765 Â°C for 180 s  |  208B EX  825 Â°C for 180 s
        #
        #  GET080  cruise ITT high (S3 only, per aircraft type)
        #    Phase: CRUISE
        #    Limit: 208B  740 Â°C  |  208B EX  805 Â°C
        # 
        if 'E1 ITT' in df.columns:
            _is_ex = 'EX' in self.aircraft_type

            # GET050  engine start (ground, before TO)
            itt_start_lim = 900.0
            ph_gnd_only   = (ph == 'PRE-FLIGHT')
            get050_s3 = require_persistence(
                (df['E1 ITT'] >= itt_start_lim) & ph_gnd_only, 3)
            events[get050_s3] = _append_event(events[get050_s3], 'ENG_GAS_TEMP_START_HI_S3')

            # TET000  takeoff ITT (TAKEOFF ROLL + ROTATION)
            itt_to_lim = 850.0 if _is_ex else 805.0
            tet000_s3 = require_persistence(
                (df['E1 ITT'] >= itt_to_lim) & ph_takeoff, 3)
            events[tet000_s3] = _append_event(events[tet000_s3], 'ENG_GAS_TEMP_TO_HI_S3')

            # GET070  climb ITT (spec: must sustain 180 s = 180 rows at 1 Hz)
            itt_climb_lim = 825.0 if _is_ex else 765.0
            ph_climb_itt  = ph.isin(['INITIAL CLIMB', 'CLIMB'])
            get070_s3 = require_persistence(
                (df['E1 ITT'] >= itt_climb_lim) & ph_climb_itt, 180)
            events[get070_s3] = _append_event(events[get070_s3], 'ENG_GAS_TEMP_CLIMB_HI_S3')

            # GET080  cruise ITT (instantaneous exceedance at cruise)
            itt_cruise_lim = 805.0 if _is_ex else 740.0
            ph_cruise_itt  = ph.isin(['CRUISE'])
            get080_s3 = require_persistence(
                (df['E1 ITT'] >= itt_cruise_lim) & ph_cruise_itt, 5)
            events[get080_s3] = _append_event(events[get080_s3], 'ENG_GAS_TEMP_CRUISE_HI_S3')

        # 
        # 32. FEN400  HIGH NG SPEED  (all phases per spec, S3 only)
        # 
        if 'E1 NG' in df.columns:
            hi_ng_s3 = require_persistence(df['E1 NG'] >= cfg.get('ng_limit', 101.6), 2)
            events[hi_ng_s3] = _append_event(events[hi_ng_s3], 'ENG_N1_HI_S3')

        # 
        # 33. FAS000  MAX ALTITUDE  (all phases per spec)
        # 
        _alt_src = next(
            (c for c in ['AltB', 'AltInd', 'AltMSL', 'AltGPS']
             if c in df.columns and pd.to_numeric(df[c], errors='coerce').max() > 0),
            None
        )
        _alt_col = pd.to_numeric(df[_alt_src], errors='coerce').fillna(0.0) \
                   if _alt_src else pd.Series(0.0, index=df.index)
        ma_s3 = require_persistence(_alt_col >= cfg.get('alt_limit', 25000.0), 5)
        ma_s2 = require_persistence((_alt_col >= cfg.get('alt_warn', 15000.0)) & ~ma_s3, 5)
 
        events[ma_s3]           = _append_event(events[ma_s3],           'MAX_ALT_EXCD_S3')
        events[ma_s2 & ~ma_s3] = _append_event(events[ma_s2 & ~ma_s3], 'MAX_ALT_EXCD_S2')

        # 34. FEQ200 — ENGINE GROUND IDLE
        # Idle is confirmed by THREE simultaneous conditions:
        #   1. NG <= idle_ng_max (68%)           -- engine in ground idle range
        #   2. FFlow in (idle_fflow_min, idle_fflow_max)
        #        > idle_fflow_min (5 GPH)         -- excludes engine-off (FFlow=0)
        #        <= idle_fflow_max (85 GPH)        -- excludes power-on rows
        #   3. FFlow rolling std (5 rows) < 2.0  -- stable, not in shutdown transition
        #      (shutdown: FFlow drops 17->12->6->2->0 over ~5 rows, std spikes to ~5-7)
        #   4. GndSpd < 5 kts                    -- stationary
        #   5. Phase == TAXI IN
        #
        # Counting backwards from the END of TAXI IN gives the last unbroken
        # idle block.  Fires if 0 < duration < 59 s (insufficient cooling time).
        taxi_in_rows = df[ph == 'TAXI IN']
        if len(taxi_in_rows) > 0:
            _fflow_min  = cfg.get('idle_fflow_min', 5.0)   # excludes engine-off rows
            _fflow_max  = cfg.get('idle_fflow_max', 85.0)
            _fflow_std  = df['E1 FFlow'].rolling(window=5, min_periods=1).std().fillna(999.0)
            idle_mask = (
                (df['E1 NG']    <= cfg.get('idle_ng_max', 68.0)) &
                (df['E1 FFlow'] >  _fflow_min) &           # exclude engine-off (FFlow=0)
                (df['E1 FFlow'] <= _fflow_max) &
                (_fflow_std     <  2.0) &                  # exclude shutdown transition
                (df['GndSpd']   <  5.0) &
                (ph == 'TAXI IN')
            )
            # Count the last unbroken idle block.
            # Scan backwards from the last TRUE row in idle_mask
            # (not from the absolute end of TAXI IN) so that engine-off
            # rows after shutdown don't break the backward scan.
            if idle_mask.any():
                last_true_pos = idle_mask.values[::-1].argmax()   # 0-based from end
                last_true_idx = len(idle_mask) - 1 - int(last_true_pos)
                reversed_from_last = idle_mask.iloc[:last_true_idx + 1].iloc[::-1]
                last_idle_dur = int(reversed_from_last.cumprod().sum())
            else:
                last_idle_dur = 0

            if 0 < last_idle_dur < 59:
                last_idle_rows           = idle_mask.iloc[-last_idle_dur:]
                feq200_mask              = pd.Series(False, index=df.index)
                feq200_mask.loc[last_idle_rows.index] = True
                feq200_s3                = require_persistence(feq200_mask, 1)
                events[feq200_s3]        = _append_event(events[feq200_s3], 'ENG_GND_IDLE_S3')
    
        # ââ JSON-driven detection (replaces hardcoded per-event blocks) ââ
        events = self._detect_json_events(df, events)

        df['FLIGHT_EVENT'] = events

        # SEVERITY: highest S-level (1/2/3) of any event on that row, 0 = NORMAL
        import re as _re_sev
        def _max_sev(val: str) -> int:
            if not val or val == 'NORMAL': return 0
            nums = _re_sev.findall(r'_S([123])', str(val))
            return max(int(n) for n in nums) if nums else 0
        df['SEVERITY'] = df['FLIGHT_EVENT'].apply(_max_sev)

        return df

    def extract_event_windows(self, df):
        """
        Collapse contiguous FLIGHT_EVENT rows into discrete event window records.

        FIXED: Uses string-matching instead of `.explode()` to prevent Index duplication errors.

        Each returned dict contains:
            event        base event name WITHOUT severity suffix (e.g. 'NORM_G_HI_TDWN')
            severity     integer 1 / 2 / 3  (parsed from _S{n} suffix)
            label        full label as stored in FLIGHT_EVENT (e.g. 'NORM_G_HI_TDWN_S3')
            phase        dominant FLIGHT_PHASE during the event window
            start_row    first DataFrame index of the window
            end_row      last DataFrame index of the window
            duration_sec number of rows (1-Hz assumption)
            peak_value   type-appropriate peak (g / fpm / kts / deg / rpm / %)
            peak_unit    unit string matching DB column: g / fpm / kts / deg / rpm / %
        """

        #  peak_unit lookup per event base name 
        _PEAK_UNIT: dict = {
            'NORM_G_HI_TDWN':           'g',
            'NORM_G_HI_TO':             'g',
            'ROD_HI_500FT':             'fpm',
            'HGT_LOSS_20_400FT':        'ft',
            'HGT_LOSS_400_1000FT':      'ft',
            'AIR_SPD_HI_1000_500FT':    'kts',
            'AIR_SPD_HI_500_50FT':      'kts',
            'AIR_SPD_HI_50FT':          'kts',
            'AIR_SPD_HI_LDG':           'kts',
            'AIR_SPD_VMO_EXCD':         'kts',
            'AIR_SPD_LO_1000_500FT':    'kts',
            'AIR_SPD_LO_500_50FT':      'kts',
            'AIR_SPD_LO_LDG':           'kts',
            'AIR_SPD_LO_35_400FT':      'kts',
            'AIR_SPD_LO_400_1500FT':    'kts',
            'AIR_SPD_LO_LIFTOFF':       'kts',
            'GND_SPD_HI_TAXI':          'kts',
            'TXX000':                   'kts',
            'TXX002':                   'kts',
            'ROLL_HI_LIFTOFF_20FT':     'deg',
            'ROLL_HI_20_100FT':         'deg',
            'ROLL_HI_100_500FT':        'deg',
            'ROLL_HI_500FT':            'deg',
            'PITCH_HI_TO':              'deg',
            'ENG_TORQ_TO_HI':           'ft-lb',
            'PROP_SPD_TO_HI':           'rpm',
            'ENG_N1_HI':                '%',
            'ENG_GAS_TEMP_START_HI':    'degC',
            'ENG_GAS_TEMP_TO_HI':       'degC',
            'ENG_GAS_TEMP_CLIMB_HI':    'degC',
            'ENG_GAS_TEMP_CRUISE_HI':   'degC',
            'MAX_ALT_EXCD':             'ft',
            'AP_ENGAGED_EARLY_TO':      'ft',
            'ENG_GND_IDLE': 's'   # peak = AltAAL at engagement
        }
        events = []

        if 'FLIGHT_EVENT' not in df.columns:
            return events

        # Collect unique event labels present in the DataFrame
        unique_labels = set()
        for val in df['FLIGHT_EVENT'].dropna().unique():
            if val != 'NORMAL':
                unique_labels.update(str(val).split('|'))

        for label in sorted(unique_labels):
            #  Parse base name and severity from label (e.g. 'NORM_G_HI_TDWN_S3')
            import re as _re
            sev_match = _re.search(r'_S([123])$', label)
            if sev_match:
                severity  = int(sev_match.group(1))
                base_name = label[:sev_match.start()]
            else:
                # Legacy label without suffix  treat as S1
                severity  = 1
                base_name = label

            # Boolean mask for this specific label WITHOUT exploding the index
            mask = df['FLIGHT_EVENT'].fillna('').str.contains(label, regex=False)
            groups = (mask != mask.shift()).cumsum()

            for _, grp in df[mask].groupby(groups):
                start_idx    = grp.index[0]
                end_idx      = grp.index[-1]
                duration_sec = len(grp)

                #  Peak value  select the most meaningful sensor per event type
                peak_value = None

                if base_name == 'NORM_G_HI_TDWN' and 'NormAc_peak' in grp.columns:
                    peak_value = float(grp['NormAc_peak'].max())

                elif base_name == 'ROD_HI_500FT' and 'VSpd' in grp.columns:
                    peak_value = float(grp['VSpd'].min())   # most negative fpm

                elif base_name in (
                    # IAS high events  max IAS
                    'AIR_SPD_HI_1000_500FT', 'AIR_SPD_HI_500_50FT', 'AIR_SPD_HI_50FT', 'AIR_SPD_HI_LDG', 'AIR_SPD_VMO_EXCD',
                ) and 'IAS' in grp.columns:
                    peak_value = float(grp['IAS'].max())

                elif base_name in (
                    # IAS low events  min IAS
                    'AIR_SPD_LO_1000_500FT', 'AIR_SPD_LO_500_50FT', 'AIR_SPD_LO_LDG', 'AIR_SPD_LO_35_400FT', 'AIR_SPD_LO_400_1500FT', 'AIR_SPD_LO_LIFTOFF',
                ) and 'IAS' in grp.columns:
                    peak_value = float(grp['IAS'].min())

                elif base_name in ('ROLL_HI_LIFTOFF_20FT', 'ROLL_HI_20_100FT', 'ROLL_HI_100_500FT', 'ROLL_HI_500FT') \
                        and 'Roll' in grp.columns:
                    peak_value = float(grp['Roll'].abs().max())

                elif base_name in ('HGT_LOSS_20_400FT', 'HGT_LOSS_400_1000FT'):
                    if 'AltAAL_LOSS' in grp.columns:
                        peak_value = float(grp['AltAAL_LOSS'].max())
                    elif 'AltAAL' in grp.columns:
                        peak_value = float(
                            (grp['AltAAL'].rolling(window=60, min_periods=1).max()
                             - grp['AltAAL']).clip(lower=0).max())

                elif base_name == 'NORM_G_HI_TO' and 'NormAc_peak' in grp.columns:
                    peak_value = float(grp['NormAc_peak'].max())

                elif base_name == 'PITCH_HI_TO' and 'Pitch' in grp.columns:
                    peak_value = float(grp['Pitch'].max())

                elif base_name == 'ENG_TORQ_TO_HI' and 'E1 Torq' in grp.columns:
                    peak_value = float(grp['E1 Torq'].max())

                elif base_name == 'PROP_SPD_TO_HI' and 'E1 NP' in grp.columns:
                    peak_value = float(grp['E1 NP'].max())

                elif base_name == 'ENG_N1_HI' and 'E1 NG' in grp.columns:
                    peak_value = float(grp['E1 NG'].max())

                elif base_name == 'MAX_ALT_EXCD':
                    _alt = next(
                        (c for c in ['AltB', 'AltInd', 'AltMSL', 'AltGPS']
                         if c in grp.columns),
                        None
                    )
                    if _alt:
                        peak_value = float(grp[_alt].max())

                elif base_name == 'GND_SPD_HI_TAXI' and 'GndSpd' in grp.columns:
                    peak_value = float(grp['GndSpd'].max())
                
                elif base_name == 'ENG_GND_IDLE' and 'E1 NG' in grp.columns:
                     peak_value = float(len(grp))   # report the actual idle duration in seconds

                # In extract_event_windows — HGT_LOSS peak value block
                elif base_name in ('TXX000', 'TXX002') and 'GndSpd' in grp.columns:
                    # Report the peak speed reached before the abort, not the speed during decel
                    peak_value = float(grp['GndSpd'].max())

                elif base_name == 'NormAc' in grp.columns:
                    peak_value = float(grp['NormAc'].min())

                elif base_name == 'Pitch' in grp.columns:
                    peak_value = float(grp['Pitch'].max())

                elif base_name in (
                    'ENG_GAS_TEMP_START_HI', 'ENG_GAS_TEMP_TO_HI',
                    'ENG_GAS_TEMP_CLIMB_HI', 'ENG_GAS_TEMP_CRUISE_HI',
                ) and 'E1 ITT' in grp.columns:
                    peak_value = float(grp['E1 ITT'].max())

                #  Dominant phase for this window 
                phase_in_window = 'UNKNOWN'
                if 'FLIGHT_PHASE' in grp.columns:
                    phase_in_window = str(
                        grp['FLIGHT_PHASE'].value_counts().idxmax()
                    )

                events.append({
                    'event'       : base_name,
                    'severity'    : severity,
                    'label'       : label,
                    'phase'       : phase_in_window,
                    'start_row'   : int(start_idx),
                    'end_row'     : int(end_idx),
                    'duration_sec': int(duration_sec),
                    'peak_value'  : round(peak_value, 2) if peak_value is not None else None,
                    'peak_unit'   : _PEAK_UNIT.get(base_name),
                })

        #  Sort chronologically then merge windows of the same label
        #    that are within 30 s of each other (prevents fragmentation
        #    of a single continuous event into many short windows).
        events.sort(key=lambda x: x['start_row'])
        events = self._merge_event_windows(events, gap_sec=30)
        return events

    @staticmethod
    def _merge_event_windows(windows: list, gap_sec: int = 30) -> list:
        """
        Merge consecutive windows of the same event label where the gap
        between end_row of the previous and start_row of the next is
        <= gap_sec rows (1 Hz assumption).

        The merged window takes the worst peak value and sums duration.
        """
        if not windows:
            return windows

        merged = []
        prev = dict(windows[0])  # copy

        for w in windows[1:]:
            same_label = (w['label'] == prev['label'])
            gap        = w['start_row'] - prev['end_row']

            if same_label and gap <= gap_sec:
                # Extend previous window
                prev['end_row']      = w['end_row']
                prev['duration_sec'] += w['duration_sec'] + gap

                # Keep worst peak
                if prev['peak_value'] is None:
                    prev['peak_value'] = w['peak_value']
                elif w['peak_value'] is not None:
                    # For descent/G events: most negative; for others: max abs
                    if prev['peak_value'] < 0 or w['peak_value'] < 0:
                        prev['peak_value'] = round(
                            min(prev['peak_value'], w['peak_value']), 2)
                    else:
                        prev['peak_value'] = round(
                            max(prev['peak_value'], w['peak_value']), 2)
                # phase stays as the dominant phase of the first sub-window
            else:
                merged.append(prev)
                prev = dict(w)

        merged.append(prev)
        return merged


    #  4. SINGLE-ROW CLASSIFIER

    def _classify_row(self,
                      AltAAL, gndspd, ias, vspd, torque, fflow, ng,
                      pitch, roll, latac, normac,
                      ias_d, vspd_d, gspd_d, torq_d,
                      alt_stab, alt_deriv, energy, energy_d, afcs, gps_ok,
                      in_airborne_hyst: bool,
                      in_climb_hyst:    bool,
                      in_descent_hyst:  bool,
                      prev_phase: str,
                      sm_corrected: bool,
                      gear_on_ground: bool,
                      ) -> Tuple[str, float, str]:
        """
        Classify a single row using plain scalar arguments.

        CONFIDENCE FIX  Branch-local snapshot scoring
        -----------------------------------------------
        The original implementation used a single global witness accumulator
        across all layers.  Every rejected layer (GO-AROUND fails, ROTATION
        fails, APPROACH failsÃÂ¦) added to witnesses_possible without adding
        to witnesses_hit, collapsing cruise confidence to ~0.26 even on a
        perfect, stable cruise row.

        Fix: the W() closure records ALL checks globally for the reason string,
        but confidence is computed from a SNAPSHOT taken immediately before
        each phase's specific witness checks.  Only the delta
        (hit_since_snap / possible_since_snap) is used as the confidence base.

        This means:
        - CRUISE confidence = fraction of {LevelVSpd, AltStable, AFCS, CruiseAlt}
          that fired  not diluted by failed GO-AROUND / CLIMB / DESCENT checks.
        - GROUND confidence = fraction of ground-specific positive witnesses.
        - GO-AROUND confidence = fraction of {TorqRise, VSpdRecov} that fired.

        All classification DECISIONS (which phase wins) are identical to before.
        Only the confidence NUMBER changes.

        GROUND PHASES  positive witness design
        ----------------------------------------
        Previously ground phases scored near 0 because the two "gate" checks
        (IAS_FLY and AltAAL_FLY) both failed, giving 0 hits / 2 possible.
        Ground phases now use POSITIVE witnesses that are true when on the ground,
        scored from their own snapshot, giving meaningful confidence values.
        """
        cfg  = self.cfg
        dyn  = self._dyn

        #  Global witness log (for PHASE_REASON string only)
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

        # 
        # LAYER 1 - AIRBORNE GATE
        # Determines ground vs airborne routing.
        # These checks are NOT counted in phase confidence  they are a
        # routing gate, not witnesses for any specific phase.
        #
        # isGearGround hard-gate logic:
        #   gear_on_ground=True  (AltAAL==0)  unconditionally route to ground
        #     branch. IAS and hysteresis are irrelevant  if AltAAL is zero the
        #     barometric model says the aircraft is at ground elevation.
        #   gear_on_ground=False (AltAAL>0)   gear has left the ground.
        #     Relax the IAS requirement when hysteresis is already active
        #     (handles sensor-lag at liftoff / touch-and-go transitions).
        #     Allow in_airborne_hyst alone to confirm airborne when AltAAL>0,
        #     covering brief IAS dropout during rotation.
        # 
        if gear_on_ground:
            # AltAAL == 0  gear is on ground. Hard-route to ground branch.
            # Ignore IAS, hysteresis, and prev_phase  barometric model is
            # definitive here and prevents airborne mis-classification during
            # slow taxi or engine run-up with momentarily elevated IAS.
            is_airborne     = False
            definitely_ground = True
        else:
            # AltAAL > 0  gear is confirmed off ground.
            # Relax IAS threshold when hysteresis is already active (aircraft
            # was recently established as airborne and AltAAL has not returned to 0).
            ias_thr = (cfg['definitely_airborne_ias'] * 0.85
                       if in_airborne_hyst else cfg['definitely_airborne_ias'])
            AltAAL_thr = cfg['liftoff_AltAAL_exit'] if in_airborne_hyst else cfg['liftoff_AltAAL_enter']
            # Two paths to confirm airborne when gear is off ground:
            #   a) IAS+AltAAL meet thresholds (primary)
            #   b) hysteresis already active + AltAAL > 0 (handles IAS sensor lag)
            is_airborne     = ((ias > ias_thr) and (AltAAL > AltAAL_thr)) or \
                              (in_airborne_hyst and AltAAL > 0)
            definitely_ground = not is_airborne

        if definitely_ground:
            #  ROLLOUT/LANDING: confirmed by prior landing phase + high speed
            if gndspd > 40 and prev_phase in ('APPROACH', 'FINAL APPROACH', 'LANDING',
                                               'DESCENT'):
                s = snap()
                W(gndspd > 40,  'GndSpdHigh')
                W(prev_phase in ('APPROACH','FINAL APPROACH','LANDING','DESCENT'), 'PriorLanding')
                W(gear_on_ground, 'GearOnGnd')
                return "LANDING", conf_from_snap(s), _reason("LANDING", reason_tags[s[2]:])

            #  TAKEOFF: torque committed + accelerating
            s = snap()
            torq_ok  = W(torque > cfg['takeoff_torque_min'], 'TorqHigh')
            accel_ok = W(gspd_d > 0.5, 'GspdAccel')
            W(gear_on_ground, 'GearOnGnd')
            if torq_ok and accel_ok and gndspd > 15:
                return "TAKEOFF", conf_from_snap(s), _reason("TAKEOFF", reason_tags[s[2]:])

            #  TAXI OUT or TAXI IN: moving but not committed to takeoff
            s = snap()
            if gndspd > cfg['taxi_speed_threshold']:
                W(gndspd > cfg['taxi_speed_threshold'], 'GndSpdTaxi')
                W(ias < cfg['definitely_airborne_ias'], 'IAS_Slow')
                W(gear_on_ground, 'GearOnGnd')
                phase_name = "TAXI IN" if self.has_landed else "TAXI OUT"
                return phase_name, conf_from_snap(s), _reason(phase_name, reason_tags[s[2]:])

            #  Stationary on ground: PRE-FLIGHT, holding, or TAXI IN
            # CRITICAL: once past PRE-FLIGHT, a GndSpd=0 row means runway
            # hold or power check, NOT a return to pre-flight state.
            s = snap()
            W(gndspd < cfg['taxi_speed_threshold'], 'GndSpdLow')
            W(ias     < cfg['definitely_airborne_ias'], 'IAS_Slow')
            W(gear_on_ground, 'GearOnGnd')
            _past_prefl = {
                'TAXI OUT', 'TAKEOFF', 'INITIAL CLIMB', 'CLIMB',
                'CRUISE', 'DESCENT', 'APPROACH', 'FINAL APPROACH',
                'LANDING', 'TAXI IN',
            }
            if self.has_landed:
                phase_name = "TAXI IN"
            elif prev_phase in _past_prefl:
                phase_name = "TAXI OUT"   # runway hold, keep forward
            else:
                phase_name = "PRE-FLIGHT"
            return phase_name, conf_from_snap(s), _reason(phase_name, reason_tags[s[2]:])

        #  From here: aircraft is confirmed airborne (gear_on_ground=False + is_airborne) 
        # Add GearOffGnd as a positive witness for the first airborne-branch layer
        # that fires. This boosts confidence on all airborne phases when AltAAL > 0.
        W(not gear_on_ground, 'GearOffGnd')

        # 
        # LAYER 2 - GO-AROUND  INITIAL CLIMB
        # 
        if AltAAL < 300 and vspd > -200 and \
                prev_phase in ('APPROACH', 'FINAL APPROACH', 'LANDING', 'DESCENT'):
            s = snap()
            torq_rise   = W(torq_d  > 200, 'TorqRise')
            vspd_recov  = W(vspd_d  >  50, 'VSpdRecov')
            if torq_rise and vspd_recov:
                return "INITIAL CLIMB", conf_from_snap(s), _reason("INITIAL CLIMB", reason_tags[s[2]:])

        # 
        # LAYER 3 - TAKEOFF / INITIAL CLIMB
        # 
        if AltAAL < 300 and vspd > 0 and \
                prev_phase in ('TAKEOFF', 'INITIAL CLIMB', 'PRE-FLIGHT', 'TAXI OUT'):
            s = snap()
            pitch_ok = W(pitch   >  2,                         'PitchPos')
            ias_ok   = W(ias    >= cfg['rotation_ias'] - 5,    'IAS_Vr')
            torq_ok  = W(torque >  cfg['climb_torque_min'],    'TorqClimb')
            if pitch_ok and ias_ok and torq_ok:
                # All rotation and early climb = TAKEOFF or INITIAL CLIMB
                ph = "TAKEOFF" if AltAAL < 100 else "INITIAL CLIMB"
                return ph, conf_from_snap(s), _reason(ph, reason_tags[s[2]:])

        if AltAAL < 1000 and \
                prev_phase in ('INITIAL CLIMB', 'TAKEOFF'):
            s = snap()
            vspd_ok = W(vspd   >  dyn['climb_rate'],        'VSpdClimb')
            torq_ok = W(torque >  cfg['climb_torque_min'],  'TorqClimb')
            if vspd_ok and torq_ok:
                return "INITIAL CLIMB", conf_from_snap(s), _reason("INITIAL CLIMB", reason_tags[s[2]:])

        # 
        # LAYER 4 - LANDING BAND
        # 
        if AltAAL < cfg['touchdown_AltAAL']:
            s = snap()
            W(normac > 1.15, 'NormAcSpike')
            W(gndspd > 20,   'GndSpdOk')
            return "LANDING", conf_from_snap(s), _reason("LANDING", reason_tags[s[2]:])

        if AltAAL < cfg['flare_AltAAL']:
            s = snap()
            W(pitch > 2,      'PitchFlare')
            W(vspd  > -400,   'VSpdArrest')
            return "LANDING", conf_from_snap(s), _reason("LANDING", reason_tags[s[2]:])

        # 
        # LAYER 5 - APPROACH BAND (split into APPROACH vs FINAL APPROACH)
        # 
        if AltAAL < 1500:
            s = snap()
            desc_ok = W(vspd < -100, 'VSpdDesc') or (not gps_ok and alt_deriv < -50)
            ias_ok  = W(ias  > (cfg['rotation_ias'] - 10), 'IAS_Apch')
            if desc_ok and ias_ok:
                # Split APPROACH vs FINAL APPROACH at 500ft AltAAL
                phase_name = "FINAL APPROACH" if AltAAL <= 500 else "APPROACH"
                return phase_name, conf_from_snap(s), _reason(phase_name, reason_tags[s[2]:])

        # 
        # LAYER 6 - ENERGY-STATE ROUTING
        # Each sub-category gets its own snapshot so only its specific
        # witnesses affect its confidence score.
        # 

        #  CLIMB (merged CLIMB + CLIMBING FLIGHT)
        # Scoring witnesses: VSpdClimb, TorqHigh, AltRise (3 witnesses, need 2)
        climb_thr     = cfg['climb_rate_exit'] if in_climb_hyst else cfg['climb_rate_enter']
        s = snap()
        is_climbing   = W(vspd   > climb_thr,               'VSpdClimb')
        has_climb_pwr = W(torque > cfg['climb_torque_min'],  'TorqHigh')
        alt_rising    = W(alt_deriv > 50,                    'AltRise')
        climb_score   = is_climbing + has_climb_pwr + alt_rising
        if climb_score >= 2:
            return "CLIMB", conf_from_snap(s), _reason("CLIMB", reason_tags[s[2]:])

        #  DESCENT (merged DESCENT + DESCENDING FLIGHT)
        # Scoring witnesses: VSpdDesc, FFlowIdle, AltFall (3 witnesses, need 2)
        desc_thr      = cfg['descent_rate_exit'] if in_descent_hyst else cfg['descent_rate_enter']
        s = snap()
        is_descending  = W(vspd    < -desc_thr,             'VSpdDesc')
        is_idle_pwr    = W(fflow   < cfg['idle_fflow_max'], 'FFlowIdle')
        alt_falling    = W(alt_deriv < -50,                 'AltFall')
        descent_score  = is_descending + alt_falling + is_idle_pwr
        if descent_score >= 2:
            return "DESCENT", conf_from_snap(s), _reason("DESCENT", reason_tags[s[2]:])

        #  CRUISE
        # Scoring witnesses: LevelVSpd, AltStable, CruiseAlt (3 core witnesses)
        # AFCS is a BONUS confidence boost, not a scoring witness.
        afcs_on      = (afcs == 1)
        s = snap()
        is_level       = W(abs(vspd) < 200,               'LevelVSpd')
        alt_stable     = W(alt_stab  < 80,                'AltStable')
        in_cruise_band = W(AltAAL       > dyn['cruise_AltAAL'], 'CruiseAlt')
        if afcs_on:
            W(True, 'AFCS')
        cruise_score   = is_level + alt_stable + in_cruise_band + afcs_on
        if cruise_score >= 2:
            return "CRUISE", conf_from_snap(s), _reason("CRUISE", reason_tags[s[2]:])

        #  CRUISE catch-all (for any remaining level flight or maneuvering)
        if is_level or abs(roll) > 25:
            s2 = snap()
            W(abs(vspd) < 200, 'LevelVSpd')
            return "CRUISE", conf_from_snap(s2), _reason("CRUISE", reason_tags[s2[2]:])

        #  Hold: nothing matched
        return prev_phase, 0.1, f"{prev_phase}|Hold"

    #  5. TRANSITION VALIDATOR  (v2 logic unchanged)

    def _validate_transition(self, prev: Optional[str], raw: str) -> str:
        if prev is None:
            return raw
        allowed = VALID_TRANSITIONS.get(prev, list(VALID_TRANSITIONS.keys()))
        if raw in allowed:
            return raw
        return prev

    #  6. SMOOTHER  (v2 logic unchanged  single-pass O(n))

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

    #  7. POST-PASS AUDITOR  (v2 logic unchanged; stability index added)

    def _post_audit(self, df: pd.DataFrame) -> pd.DataFrame:
        """Vectorised segment-level consistency. Unchanged from v2."""
        phases = df['FLIGHT_PHASE'].copy()

        # Rule 1: CRUISE below cruise_AltAAL_min  DESCENT
        cruise_too_low = (phases == 'CRUISE') & (df['AltAAL'] < self.cfg['cruise_AltAAL_min'])
        phases[cruise_too_low] = 'DESCENT'

        # Rule 2: APPROACH with mean VSpd > 100 fpm (climbing)  CLIMB
        approach_mask = phases == 'APPROACH'
        if approach_mask.any():
            group_id = (approach_mask != approach_mask.shift()).cumsum()
            approach_groups = group_id[approach_mask]
            mean_vspd = df.loc[approach_mask, 'VSpd'].groupby(approach_groups).mean()
            bad_groups = set(mean_vspd[mean_vspd > 100].index)
            if bad_groups:
                bad_rows = approach_mask & group_id.isin(bad_groups)
                phases[bad_rows] = 'CLIMB'

        df['FLIGHT_PHASE'] = phases
        return df

    #  V3 NEW: PHASE STABILITY INDEX 

    def _compute_phase_stability(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute PHASE_STABILITY  rolling 10-row same-phase agreement ratio.

        Definition
        ----------
        For each row i, PHASE_STABILITY is the fraction of rows in the
        window [i-9 ÃÂ¦ i] that have the SAME phase as row i.

        Value of 1.0 = phase has been identical for 10 consecutive rows.
        Value of 0.1 = maximum instability (every row different in window).

        Use in FOQA
        -----------
        * KPI computation should filter or weight by PHASE_STABILITY.
          A metric computed during a low-stability zone (e.g., 0.3) is
          less reliable than one during a stable cruise (1.0).
        * PHASE_STABILITY < 0.5 during approach  flag for manual review.
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

    #  8. MAIN PIPELINE  (V3: adds adaptive thresholds, new columns, debug)

    def classify(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Execute the full classification pipeline.

        V2 pipeline (steps 1-6, all preserved):
        1. Compute derived parameters
        2. Compute dynamic AltAAL
        3. Detect special events
        4. First-pass phase classification (state-machine loop)
        5. Temporal smoothing
        6. Post-pass audit

        V3 additions:
        2a. Compute adaptive thresholds (between AltAAL and events)
        4.  Loop now tracks hysteresis state, collects confidence + reason
        6a. Compute PHASE_STABILITY index (after audit)
        
        V4 FDA/Aering:
        - Direct FDA phase naming (no conversion)
        - Context-aware TAXI OUT vs TAXI IN
        - APPROACH vs FINAL APPROACH split at 500ft
        """
        # Reset state for each flight
        self.has_taken_off = False
        self.has_landed = False
        
        #  Ensure a clean 0-based integer index throughout the pipeline.
        # G1000 CSVs read with skiprows can carry duplicate or non-contiguous
        # index labels which cause pandas to raise
        # "cannot reindex on an axis with duplicate labels"
        # inside rolling / iloc[::-1] operations in require_persistence().
        df = df.reset_index(drop=True)

        print("  [1/8] Computing derived parameters...")
        df = self.compute_derived(df)

        print("  [2/8] Computing dynamic AltAAL (gradient model)...")
        df = self.compute_AltAAL(df)

        print("  [2b/8] Resolving departure / arrival ICAO from GPS track...")
        # Identify the GPS coordinate columns. Garmin G1000/G950 CSVs use
        # 'Latitude' and 'Longitude'; guard against missing columns gracefully.
        _lat_col = next((c for c in ['Latitude', 'Lat', 'LAT'] if c in df.columns), None)
        _lon_col = next((c for c in ['Longitude', 'Lon', 'LON'] if c in df.columns), None)

        if _lat_col and _lon_col:
            # Build a mask of rows with a valid GPS fix.
            # GPS_quality was computed in compute_derived(): 1 = good, 0 = degraded.
            # We also require that the coordinate values are actually numeric and non-zero.
            _gps_valid = (
                (df['GPS_quality'] == 1) &
                (pd.to_numeric(df[_lat_col], errors='coerce').notna()) &
                (pd.to_numeric(df[_lon_col], errors='coerce').notna()) &
                (pd.to_numeric(df[_lat_col], errors='coerce').abs() > 0.001) &
                (pd.to_numeric(df[_lon_col], errors='coerce').abs() > 0.001)
            )
            _valid_rows = df[_gps_valid]

            if not _valid_rows.empty:
                # --- Departure ICAO: use filename-derived code first.
                # Only override if dep_icao was not supplied by the caller.
                if not self.dep_icao:
                    _first = _valid_rows.iloc[0]
                    _dep_lat = float(pd.to_numeric(_first[_lat_col], errors='coerce'))
                    _dep_lon = float(pd.to_numeric(_first[_lon_col], errors='coerce'))
                    self.dep_icao = _nearest_icao(_dep_lat, _dep_lon)
                    if self.debug_mode:
                        print(f"  [GPS] dep_icao resolved: '{self.dep_icao}' "
                              f"from ({_dep_lat:.4f}, {_dep_lon:.4f})")

                # --- Arrival ICAO: use the last several valid GPS rows.
                _arr_rows = _valid_rows.tail(min(10, len(_valid_rows)))
                _arr_lat = float(pd.to_numeric(_arr_rows[_lat_col], errors='coerce').median())
                _arr_lon = float(pd.to_numeric(_arr_rows[_lon_col], errors='coerce').median())
                self.arr_icao = _nearest_icao(_arr_lat, _arr_lon)
                if self.debug_mode:
                    print(f"  [GPS] arr_icao resolved: '{self.arr_icao}' "
                          f"from last {_arr_rows.shape[0]} valid rows "
                          f"({_arr_lat:.4f}, {_arr_lon:.4f})")
            else:
                if self.debug_mode:
                    print("  [GPS] No valid GPS rows found — dep_icao/arr_icao unchanged.")
        else:
            if self.debug_mode:
                print(f"  [GPS] Latitude/Longitude columns not found in CSV — "
                      f"dep_icao/arr_icao unchanged. Columns present: "
                      f"{[c for c in df.columns if 'lat' in c.lower() or 'lon' in c.lower()]}")

        print("  [3/8] Computing adaptive thresholds...")
        self.compute_adaptive_thresholds(df)

        print("  [4/8] First-pass classification (hysteresis + confidence)...")

        #  Pre-extract all columns to numpy arrays (v2 optimisation preserved)
        def _arr(col: str) -> np.ndarray:
            return df[col].to_numpy(dtype=float, na_value=0.0)

        a_AltAAL      = _arr('AltAAL')
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
        a_gear     = _arr('isGearGround')

        phases:      List[str]   = []
        confidences: List[float] = []
        reasons:     List[str]   = []

        current_phase: Optional[str] = None
        hold_count    = 0
        MAX_HOLD      = 5

        #  V3: Hysteresis state (tracked in loop, NOT in _classify_row)
        # These booleans represent whether the aircraft is currently
        # considered to be "in" the airborne/climb/descent state.
        # They are updated AFTER each row is classified.
        in_airborne_hyst = False
        in_climb_hyst    = False
        in_descent_hyst  = False

        cfg = self.cfg   # local ref for speed

        for i in range(len(df)):
            raw_phase, raw_conf, raw_reason = self._classify_row(
                float(a_AltAAL[i]),      float(a_gndspd[i]),  float(a_ias[i]),
                float(a_vspd[i]),     float(a_torque[i]),  float(a_fflow[i]),
                float(a_ng[i]),       float(a_pitch[i]),   float(a_roll[i]),
                float(a_latac[i]),    float(a_normac[i]),
                float(a_ias_d[i]),    float(a_vspd_d[i]),  float(a_gspd_d[i]),
                float(a_torq_d[i]),   float(a_altstab[i]), float(a_altd[i]),
                float(a_energy[i]),   float(a_energy_d[i]),
                float(a_afcs[i]),     float(a_gpsq[i]),
                in_airborne_hyst, in_climb_hyst, in_descent_hyst,
                current_phase or "PRE-FLIGHT",
                sm_corrected=(hold_count > 0),
                gear_on_ground=bool(a_gear[i] == 1),
            )

            #  State machine validation (v2 logic unchanged)
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
                    # Hard guard: never allow forbidden backward transitions
                    # even when MAX_HOLD is reached.
                    _forbidden = NEVER_BACKWARD.get(current_phase, set())
                    if hold_count >= MAX_HOLD and raw_phase not in _forbidden:
                        validated  = raw_phase
                        hold_count = 0
                    elif raw_phase in _forbidden:
                        hold_count = 0   # reset  stop burning hold budget
                        validated  = current_phase
                    else:
                        validated = current_phase

            if a_AltAAL[i] > cfg['liftoff_AltAAL_enter']:
                in_airborne_hyst = True
            elif a_AltAAL[i] < cfg['liftoff_AltAAL_exit']:
                in_airborne_hyst = False

            if a_vspd[i] > cfg['climb_rate_enter']:
                in_climb_hyst = True
            elif a_vspd[i] < cfg['climb_rate_exit']:
                in_climb_hyst = False

            if a_vspd[i] < -cfg['descent_rate_enter']:
                in_descent_hyst = True
            elif a_vspd[i] > -cfg['descent_rate_exit']:
                in_descent_hyst = False
            
            if validated in ('TAKEOFF', 'INITIAL CLIMB'):
                self.has_taken_off = True
            if validated == 'LANDING' and self.has_taken_off:
                self.has_landed = True

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

        print("  [5/8] Smoothing phase labels...")
        df = self._smooth_phases(df)

        print("  [6/8] Post-pass audit...")
        df = self._post_audit(df)

        print("  [7/8] Computing phase stability index...")
        df = self._compute_phase_stability(df)

        print("  [8/8] Detecting events (phase-aware)...")
        df = self.detect_special_events(df)

        if self.debug_mode:
            n_total    = len(df)
            n_low_conf = (df['PHASE_CONFIDENCE'] < 0.5).sum()
            print(f"\n  [DEBUG] Rows with low confidence (<0.5): "
                  f"{n_low_conf} / {n_total} ({n_low_conf/n_total*100:.1f}%)")
            print(f"  [DEBUG] Mean confidence: {df['PHASE_CONFIDENCE'].mean():.3f}")
            print(f"  [DEBUG] Mean stability : {df['PHASE_STABILITY'].mean():.3f}")
            print(f"  [DEBUG] Events fired:")
            all_ev = df['FLIGHT_EVENT'].str.split('|').explode()
            for ev, cnt in all_ev.value_counts().items():
                if ev != 'NORMAL':
                    print(f"           {ev:30s}: {cnt:4d} rows")

        return df

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

    Returns float ÃÂÃÂ [0.0, 1.0]
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
        'AltGPS', 'AltB', 'AltInd', 'AltMSL', 'TAS', 'HDG', 'TRK',
        'WndSpd', 'WndDr', 'WptDst', 'AfcsOn',
        'GPSfix', 'HAL', 'VAL',
    ]
    for col in expected:
        if col not in df.columns:
            df[col] = 0.0
    return df

def process_flight_log(input_file: str,
                       output_file: str,
                       aircraft_type: str = "Generic",
                       debug_mode: bool   = False,
                       dep_icao: str = "",
                       arr_icao: str = "") -> None:
    print(f"\n{'='*60}")
    print(f"  FOQA Flight Phase Classifier -- v4.0 FDA/Aering")
    print(f"  Aircraft : {aircraft_type}")
    print(f"  Input    : {input_file}")
    print(f"  Output   : {output_file}")
    print(f"  Debug    : {'ON' if debug_mode else 'off'}")
    print(f"{'='*60}\n")

    with open(input_file, 'r', encoding='latin-1', errors='replace') as f:
        header_line1 = f.readline()
        header_line2 = f.readline()
        header_line3 = f.readline().strip()

    if Path(input_file).resolve() == Path(output_file).resolve():
        raise ValueError(
            f"input_file and output_file must be different paths  "
            f"refusing to overwrite source data.\n"
            f"  input : {input_file}"
        )

    df_raw = pd.read_csv(input_file, skiprows=2, dtype=str,
                         encoding='latin-1', on_bad_lines='skip')
    df_raw.columns = df_raw.columns.str.strip()
    original_columns = df_raw.columns.tolist()

    _CLASSIFIER_COLS = [
        'FLIGHT_PHASE', 'FLIGHT_EVENT', 'SEVERITY',
        'PHASE_CONFIDENCE', 'PHASE_REASON', 'PHASE_STABILITY',
        'AltAAL', 'isGearGround', 'AltAAL_LOSS'
    ]
    collision = [c for c in _CLASSIFIER_COLS if c in original_columns]
    if collision:
        raise ValueError(
            f"File already contains classifier columns {collision}  "
            f"use the original source CSV, not a pre-classified output.\n"
            f"  file: {input_file}"
        )

    numeric_cols = [
        'VSpd', 'IAS', 'GndSpd', 'Pitch', 'Roll', 'LatAc', 'NormAc',
        'E1 FFlow', 'E1 Torq', 'E1 NP', 'E1 NG', 'E1 ITT',
        'AltGPS', 'AltB', 'AltInd', 'AltMSL', 'TAS', 'HDG', 'TRK',
        'WndSpd', 'WndDr', 'WptDst', 'AfcsOn', 'GPSfix', 'HAL', 'VAL',
    ]

    df_work = df_raw.copy()
    for col in numeric_cols:
        if col in df_work.columns:
            df_work[col] = pd.to_numeric(df_work[col], errors='coerce').fillna(0.0)

    df_work = ensure_columns(df_work)

    dep_icao = _icao_from_filename(input_file)
    if dep_icao and debug_mode:
        print(f"  [FILENAME] dep_icao parsed from filename: '{dep_icao}'")

    classifier = FOQAFlightClassifier(aircraft_type=aircraft_type,
                                       debug_mode=debug_mode,
                                       dep_icao=dep_icao,
                                       arr_icao=arr_icao)
    df_work = classifier.classify(df_work)
    df_work['AltAAL'] = df_work['AltAAL'].round(1)
    df_out = pd.concat(
        [df_raw[original_columns].reset_index(drop=True),
         df_work[_CLASSIFIER_COLS].reset_index(drop=True)],
        axis=1,
    )

    print("\n--- Phase Distribution -------------------------------------------")
    for phase, count in df_work['FLIGHT_PHASE'].value_counts().sort_index().items():
        pct       = count / len(df_work) * 100
        mask      = df_work['FLIGHT_PHASE'] == phase
        mean_conf = df_work.loc[mask, 'PHASE_CONFIDENCE'].mean()
        print(f"  {phase:22s}: {count:5d} rows  ({pct:5.1f}%)  "
              f"conf={mean_conf:.2f}")

    print("\n--- Special Events -----------------------------------------------")
    all_events = df_work['FLIGHT_EVENT'].str.split('|').explode()
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
    print(f"  Mean confidence : {df_work['PHASE_CONFIDENCE'].astype(float).mean():.3f}")
    print(f"  Mean stability  : {df_work['PHASE_STABILITY'].astype(float).mean():.3f}")
    dyn = df_work.attrs.get('dynamic_thresholds', {})
    if dyn:
        print(f"  Dynamic climb rate   : {dyn.get('climb_rate', 'N/A'):.1f} fpm")
        print(f"  Dynamic descent rate : {dyn.get('descent_rate', 'N/A'):.1f} fpm")
        print(f"  Dynamic cruise AltAAL   : {dyn.get('cruise_AltAAL', 'N/A'):.1f} ft")

    import csv as _csv
    print(f"\nWriting output to: {output_file}")
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        f.write(header_line1 if header_line1.endswith('\n') else header_line1 + '\n')
        f.write(header_line2 if header_line2.endswith('\n') else header_line2 + '\n')
        f.write(header_line3 + ',' + ','.join(_CLASSIFIER_COLS) + '\n')
        writer = _csv.writer(f, quoting=_csv.QUOTE_MINIMAL)
        for row in df_out.itertuples(index=False, name=None):
            writer.writerow(row)

    print(f"\nOK Done.\n")

def main():
    parser = argparse.ArgumentParser(
        description='FOQA Flight Phase Classifier v4.0 - Cessna 208 family (FDA/Aering)')
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