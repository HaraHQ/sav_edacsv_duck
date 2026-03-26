# Aircraft Registration Mapping
# Format: 'REGISTRATION': 'Aircraft Type'
AIRCRAFT_REGISTRATION_MAP = {
    # Cessna 208 Caravan (Standard)
    'PK-SNK': 'Cessna 208 Caravan', # Torq limit - 1865
    'PK-SNM': 'Cessna 208 Caravan',
    'PK-SNNOF': 'Cessna 208 Caravan',
    
    # Cessna 208B Grand Caravan
    'PK-SNO': 'Cessna 208B Grand Caravan', # Torq limit - 1865
    'PK-SNS': 'Cessna 208B Grand Caravan',
    
    # Cessna 208B Grand Caravan EX
    'PK-SNE': 'Cessna 208B Grand Caravan EX', # Torq limit - 2397
    'PK-SNA': 'Cessna 208B Grand Caravan EX',
    'PK-SNF': 'Cessna 208B Grand Caravan EX',
    'PK-SNG': 'Cessna 208B Grand Caravan EX',
    'PK-SNH': 'Cessna 208B Grand Caravan EX',
    'PK-SNI': 'Cessna 208B Grand Caravan EX',
    'PK-SNJ': 'Cessna 208B Grand Caravan EX',
    'PK-SNL': 'Cessna 208B Grand Caravan EX',
    'PK-SNN': 'Cessna 208B Grand Caravan EX',
    'PK-SNP': 'Cessna 208B Grand Caravan EX',
    'PK-SNR': 'Cessna 208B Grand Caravan EX',
    'PK-SNT': 'Cessna 208B Grand Caravan EX',
    'PK-SNV': 'Cessna 208B Grand Caravan EX',
    'PK-SNW': 'Cessna 208B Grand Caravan EX',
}


def get_aircraft_type_from_registration(registration: str) -> str:
    # Normalize registration (uppercase, remove spaces/dashes)
    normalized = registration.upper().replace(' ', '').replace('-', '')
    
    # Try exact match first
    if registration.upper() in AIRCRAFT_REGISTRATION_MAP:
        return AIRCRAFT_REGISTRATION_MAP[registration.upper()]
    
    # Try normalized match
    for reg, aircraft_type in AIRCRAFT_REGISTRATION_MAP.items():
        if reg.replace('-', '') == normalized:
            return aircraft_type
    
    return None


def get_aircraft_type_from_path(file_path: str) -> str:
    import os
    
    # Split path into components
    path_parts = file_path.replace('\\', '/').split('/')
    
    # Check each part for a known registration
    for part in path_parts:
        aircraft_type = get_aircraft_type_from_registration(part)
        if aircraft_type:
            return aircraft_type
    
    return None

# Quick reference for adding new aircraft
def print_registration_summary():
    """Print a summary of all registered aircraft by type."""
    from collections import defaultdict
    
    by_type = defaultdict(list)
    for reg, aircraft_type in sorted(AIRCRAFT_REGISTRATION_MAP.items()):
        by_type[aircraft_type].append(reg)
    
    print("Aircraft Registration Summary")
    print("=" * 70)
    for aircraft_type, registrations in sorted(by_type.items()):
        print(f"\n{aircraft_type}:")
        print(f"  Count: {len(registrations)}")
        print(f"  Registrations: {', '.join(registrations)}")
    print("\n" + "=" * 70)
    print(f"Total Aircraft: {len(AIRCRAFT_REGISTRATION_MAP)}")


if __name__ == "__main__":
    print_registration_summary()
