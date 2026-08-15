"""
Team metadata: conference and division assignments.
Used by the schedule generator to build a realistic placeholder schedule
(more games against conference/division opponents than cross-conference).
"""

TEAMS = {
    # Eastern Conference - Atlantic
    "BOS": {"conference": "East", "division": "Atlantic"},
    "BKN": {"conference": "East", "division": "Atlantic"},
    "NYK": {"conference": "East", "division": "Atlantic"},
    "PHI": {"conference": "East", "division": "Atlantic"},
    "TOR": {"conference": "East", "division": "Atlantic"},
    # Eastern Conference - Central
    "CHI": {"conference": "East", "division": "Central"},
    "CLE": {"conference": "East", "division": "Central"},
    "DET": {"conference": "East", "division": "Central"},
    "IND": {"conference": "East", "division": "Central"},
    "MIL": {"conference": "East", "division": "Central"},
    # Eastern Conference - Southeast
    "ATL": {"conference": "East", "division": "Southeast"},
    "CHA": {"conference": "East", "division": "Southeast"},
    "MIA": {"conference": "East", "division": "Southeast"},
    "ORL": {"conference": "East", "division": "Southeast"},
    "WAS": {"conference": "East", "division": "Southeast"},
    # Western Conference - Northwest
    "DEN": {"conference": "West", "division": "Northwest"},
    "MIN": {"conference": "West", "division": "Northwest"},
    "OKC": {"conference": "West", "division": "Northwest"},
    "POR": {"conference": "West", "division": "Northwest"},
    "UTA": {"conference": "West", "division": "Northwest"},
    # Western Conference - Pacific
    "GSW": {"conference": "West", "division": "Pacific"},
    "LAC": {"conference": "West", "division": "Pacific"},
    "LAL": {"conference": "West", "division": "Pacific"},
    "PHX": {"conference": "West", "division": "Pacific"},
    "SAC": {"conference": "West", "division": "Pacific"},
    # Western Conference - Southwest
    "DAL": {"conference": "West", "division": "Southwest"},
    "HOU": {"conference": "West", "division": "Southwest"},
    "MEM": {"conference": "West", "division": "Southwest"},
    "NOP": {"conference": "West", "division": "Southwest"},
    "SAS": {"conference": "West", "division": "Southwest"},
}

TEAM_LIST = list(TEAMS.keys())

assert len(TEAM_LIST) == 30, "Expected 30 NBA teams"
