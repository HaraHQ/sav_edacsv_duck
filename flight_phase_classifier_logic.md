# Flight Phase Classifier Logic Documentation

## Overview

This document describes the flight phase classification algorithm used to automatically detect and classify different phases of flight from aircraft telemetry data. The logic can be ported to the PHP-based EDA project.

## Core Concept

The classifier uses a **state machine** with **hard gates** (strict thresholds) and **AGL (Above Ground Level) calculation** to determine flight phases from CSV telemetry data.

## Aircraft Configurations

Different aircraft types have different performance characteristics:

| Aircraft Type | Climb Torque Min | Rotation IAS | Taxi Speed | Climb Rate |
|--------------|------------------|--------------|------------|------------|
| Cessna 208 Caravan | 1200 ft-lb | 58 kts | 6 kts | 400 fpm |
| Cessna 208B Grand Caravan | 1200 ft-lb | 60 kts | 6 kts | 400 fpm |
| Cessna 208B Grand Caravan EX | 1300 ft-lb | 60 kts | 6 kts | 400 fpm |
| Generic | 1000 ft-lb | 60 kts | 5 kts | 300 fpm |

## Key Parameters Used

- **AGL**: Above Ground Level altitude (calculated dynamically)
- **GndSpd**: Ground speed (knots)
- **IAS**: Indicated Airspeed (knots)
- **VSpd**: Vertical Speed (feet per minute)
- **E1 Torq**: Engine torque (ft-lb)
- **Pitch**: Pitch angle (degrees)
- **AltGPS/AltB/AltMSL**: Altitude sources (GPS prioritized)

## AGL Calculation Logic

**Critical for Papua/mountainous terrain operations:**

```
1. Sample first 180 rows (3 min) → Departure elevation
2. Sample last 180 rows (3 min) → Destination elevation
3. Find peak altitude → Split point
4. Before peak: Use departure elevation as ground reference
5. After peak: Use destination elevation as ground reference
6. AGL = Current_Altitude - Ground_Reference
```

**Fallbacks:**
- If departure missing → Use destination
- If destination missing → Use departure
- If both missing → Use minimum altitude of entire flight

## Decision Gates (Priority Order)

### 1. SPEED GATE (Primary - "Papua Fix")
```
IF GndSpd < 40 knots → DEFINITELY ON GROUND
```
This overrides GPS altitude errors on sloped runways.

### 2. ALTITUDE GATE (Secondary)
```
IF AGL < 75 feet → NEAR GROUND
```

### 3. POWER GATE
```
IF Torque > climb_torque_min → HIGH POWER
```

### 4. CLIMB/DESCENT GATE
```
IF VSpd > 400 fpm → CLIMBING
IF VSpd < -400 fpm → DESCENDING
```

## Flight Phase Classification Logic

### Ground Operations (AGL < 75 OR GndSpd < 40)

```
IF GndSpd > 40:
    IF previous_phase in [APPROACH, FLARE, TOUCHDOWN, DESCENDING FLIGHT]:
        → ROLLOUT
    IF previous_phase in [TAKEOFF ROLL, ROTATION]:
        → TAKEOFF ROLL
    ELSE:
        → TOUCHDOWN

IF high_power AND moving AND GndSpd > 15:
    → TAKEOFF ROLL

IF moving (GndSpd > taxi_threshold):
    → TAXI
ELSE:
    → GROUND
```

### Flight Operations (Airborne AND GndSpd >= 40)

```
IF AGL < 200 AND high_power AND pitch > 0 AND VSpd > 0:
    → ROTATION

IF AGL < 200 AND NOT high_power:
    IF pitch > 0:
        → FLARE
    ELSE:
        → APPROACH

IF climbing:
    IF AGL < 500:
        → INITIAL CLIMB
    ELSE:
        → CLIMB / CLIMBING FLIGHT

IF descending:
    IF AGL < 1000:
        → APPROACH
    ELSE:
        → DESCENT / DESCENDING FLIGHT

IF stable (low VSpd variance):
    IF high_altitude:
        → CRUISE
    ELSE:
        → LEVEL FLIGHT

ELSE:
    → MANEUVERING
```

## State Machine Transitions

Valid transitions prevent impossible phase jumps:

```
GROUND → TAXI → TAKEOFF ROLL → ROTATION → INITIAL CLIMB → CLIMB
                                              ↓
                                          CRUISE ← → LEVEL FLIGHT
                                              ↓
                                          DESCENT → APPROACH → FLARE → TOUCHDOWN → ROLLOUT → TAXI
```

**Special allowances:**
- TAXI can jump to CLIMBING FLIGHT (missed takeoff detection)
- TAKEOFF ROLL can jump to CLIMB (missed rotation)
- APPROACH can jump to TOUCHDOWN (missed flare)

## Implementation Steps for PHP/EDA Project

### 1. Database Schema Addition
```sql
ALTER TABLE flight_data ADD COLUMN phase VARCHAR(50);
ALTER TABLE flight_data ADD COLUMN agl FLOAT;
```

### 2. Configuration Storage
Store aircraft configs in `config/aircraft_configs.php`:
```php
return [
    'Cessna 208 Caravan' => [
        'climb_torque_min' => 1200.0,
        'rotation_ias' => 58.0,
        // ...
    ]
];
```

### 3. AGL Calculation Function
Create `src/AglCalculator.php` with:
- `calculateDepartureElevation()`
- `calculateDestinationElevation()`
- `calculateAgl()`

### 4. Phase Classifier Function
Create `src/FlightPhaseClassifier.php` with:
- `classifyPhase($row, $prevPhase, $config)`
- `isValidTransition($from, $to)`
- `processFlightData($csvData, $aircraftType)`

### 5. Integration Points

**Option A: Real-time (during CSV import)**
```php
// In process_queue.php
foreach ($rows as $row) {
    $row['agl'] = $aglCalculator->calculate($row, $groundRef);
    $row['phase'] = $classifier->classify($row, $prevPhase);
    // Insert to DuckDB
}
```

**Option B: Post-processing (after import)**
```php
// New endpoint: /eda/classify-phases
// Run classification on existing data
$db->query("UPDATE flight_data SET phase = ...");
```

### 6. API Endpoint Addition
```php
// GET /eda/phases?acReg=PK-SNP&date=2025-11-22
// Returns: phase distribution, timeline, statistics
```

## Key Considerations for PHP Port

1. **Performance**: Process in batches (1000 rows at a time)
2. **Memory**: Use generators for large CSV files
3. **Derivatives**: Calculate rolling averages using array_slice
4. **State persistence**: Track previous phase across rows
5. **Validation**: Log invalid transitions for debugging

## Testing Strategy

1. **Ground truth data**: Manually label 1-2 flights
2. **Edge cases**: 
   - Short flights (< 10 min)
   - Touch-and-go landings
   - Go-arounds
   - Sloped runways (Papua)
3. **Metrics**: Accuracy per phase, transition correctness

## Expected Output Format

```json
{
  "acReg": "PK-SNP",
  "date": "2025-11-22",
  "phases": [
    {
      "phase": "GROUND",
      "startTime": "08:27:56",
      "endTime": "08:30:12",
      "duration": 136,
      "avgAgl": 0,
      "avgSpeed": 0
    },
    {
      "phase": "TAXI",
      "startTime": "08:30:12",
      "endTime": "08:32:45",
      "duration": 153,
      "avgAgl": 0,
      "avgSpeed": 8.5
    }
    // ...
  ]
}
```

## Benefits for EDA Project

1. **Automatic flight segmentation** for analysis
2. **Torque exceedance detection** per phase (e.g., only flag during CLIMB)
3. **Phase-specific statistics** (avg torque in cruise, max speed in takeoff)
4. **Anomaly detection** (unexpected phase transitions)
5. **Flight quality metrics** (smooth approaches, stable climbs)

## Next Steps

1. Port AGL calculation to PHP
2. Implement phase classifier with state machine
3. Add phase column to DuckDB queries
4. Create phase visualization endpoint
5. Integrate with existing chart endpoint for phase-colored graphs
