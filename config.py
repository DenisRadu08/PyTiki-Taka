# DICTIONARUL JOCULUI

# STATES
STATE_IDLE = "IDLE"
STATE_CHASE = "CHASE"
STATE_KICK = "KICK"
STATE_RESET = "RESET"
STATE_DO_THROW_IN = "DO_THROW_IN"
STATE_WAIT_THROW_IN = "WAIT_THROW_IN"
STATE_DRIBBLE = "DRIBBLE"
STATE_DRIBBLE_DUEL = "DRIBBLE_DUEL"
STATE_PASS = "PASS"
STATE_ATTACK_SUPPORT = "ATTACK_SUPPORT"
STATE_DEFEND_SUPPORT = "DEFEND_SUPPORT"
STATE_CONTROL_BALL = "CONTROL_BALL"
STATE_GK_DEFEND_GOAL = "GK_DEFEND_GOAL"
STATE_GK_CLEAR_BALL = "GK_CLEAR_BALL"
STATE_GK_HOLD_BALL = "GK_HOLD_BALL"


# STATUSES
STATUS_PLAYING = "PLAYING"
STATUS_GOAL = "GOAL"
STATUS_OUT = "OUT"
STATUS_START_GAME = "START_GAME"

# STARTING POSITIONS
STARTING_POSITIONS = {
    #"1" : {"x": 0, "y": 50, "team": "A", "role": "GK"},       # ====== RED TEAM ======
    #"2" : {"x": 15, "y": 50, "team": "A", "role": "FIELD"},   # ====== RED TEAM ======
    #"101" : {"x": 85, "y": 40, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====
    #"102" : {"x": 55, "y": 45, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====
    
    # Goalkeeper
    "1" : {"x": 2, "y": 50, "team": "A", "role": "GK"},       # ====== RED TEAM ======
    
    # Defenders
    "2" : {"x": 18, "y": 90, "team": "A", "role": "FIELD"},   # ====== RED TEAM ======
    "3" : {"x": 15, "y": 65, "team": "A", "role": "FIELD"},   # ====== RED TEAM ======
    "4" : {"x": 15, "y": 35, "team": "A", "role": "FIELD"},   # ====== RED TEAM ======
    "5" : {"x": 18, "y": 10, "team": "A", "role": "FIELD"},   # ====== RED TEAM ======
    
    # Midfielders
    "6" : {"x": 30, "y": 80, "team": "A", "role": "FIELD"},   # ====== RED TEAM ======
    "7" : {"x": 25, "y": 50, "team": "A", "role": "FIELD"},   # ====== RED TEAM ======
    "8" : {"x": 30, "y": 20, "team": "A", "role": "FIELD"},   # ====== RED TEAM ======

    # Forwards
    "9" : {"x": 45, "y": 85, "team": "A", "role": "FIELD"},   # ====== RED TEAM ======
    "10" : {"x": 40, "y": 50, "team": "A", "role": "FIELD"},   # ====== RED TEAM ======
    "11" : {"x": 45, "y": 15, "team": "A", "role": "FIELD"},   # ====== RED TEAM ======
    
    # Goalkeeper
    "101" : {"x": 98, "y": 50, "team":"B", "role": "GK"},  # ====== BLUE TEAM =====

    # Defenders
    "102" : {"x": 85, "y": 85, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====
    "103" : {"x": 88, "y": 60, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====
    "104" : {"x": 88, "y": 40, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====
    "105" : {"x": 85, "y": 15, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====

    # Midfielders 1
    "106" : {"x": 78, "y": 65, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====
    "107" : {"x": 78, "y": 35, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====

    # Midfielders 2
    "108" : {"x": 70, "y": 80, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====
    "109" : {"x": 70, "y": 20, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====

    # Forwards
    "110" : {"x": 55, "y": 65, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====
    "111" : {"x": 55, "y": 35, "team":"B", "role": "FIELD"},  # ====== BLUE TEAM =====
}

# PLAYERS
NUM_OF_PLAYERS = 10