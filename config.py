# DICTIONARUL JOCULUI

# STATES
STATE_IDLE = "IDLE"
STATE_CHASE = "CHASE"
STATE_KICK = "KICK"
STATE_RESET = "RESET"
STATE_DO_THROW_IN = "DO_THROW_IN"
STATE_WAIT_THROW_IN = "WAIT_THROW_IN"
STATE_DO_CORNER = "DO_CORNER"
STATE_WAIT_CORNER = "WAIT_CORNER"
STATE_DO_GOAL_KICK = "DO_GOAL_KICK"
STATE_WAIT_GOAL_KICK = "WAIT_GOAL_KICK"
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
STATUS_CORNER = "CORNER"
STATUS_GOAL_KICK = "GOAL_KICK"
STATUS_START_GAME = "START_GAME"
STATUS_MATCH_OVER = "MATCH_OVER"

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

# DEAD BALL (OUT / CORNER / GOAL KICK)
# viteza cu care se pozitioneaza jucatorii care asteapta (alergare tactica in careu / teren)
WAIT_POSITIONING_SPEED = 0.70
# viteza executantului catre minge la faza fixa
TAKER_POSITIONING_SPEED = 0.70
# fluier dinamic arbitrul: timp minim de asezare si timp maxim de siguranta (secunde)
OUT_OF_PLAY_ROLL_SECONDS = 1.6       # cate secunde vedem mingea cum iese din teren (slow-motion) inainte sa fie pusa pe punct
GOAL_CELEBRATION_SECONDS = 3.5       # cate secunde ramane mingea in plasa portii dupa gol inainte de centrare
RESTART_PREPARE_MIN_SECONDS = 3.2
RESTART_PREPARE_MAX_SECONDS = 4.8
RESTART_PREPARE_SECONDS = 3.0  # mentinut pentru compatibilitate

# GOALKEEPING & DEFLECTIONS
GK_SAVE_RADIUS = 3.0                 # raza de plonjon / acoperire portar (marita usor pentru parade spectaculoase)
GK_DIVE_SPEED = 1.25                 # viteza de deplasare la plonjon pentru a apara sutul spre colturi
GK_CATCH_SPEED_THRESHOLD = 1.6       # suturi sub aceasta viteza sau pe centrul corpului sunt prinse direct
GK_PARRY_CORNER_CHANCE = 0.50        # 50% sanse ca suturile tari sa fie deviate peste linia de fund in CORNER
GK_PARRY_REBOUND_CHANCE = 0.30       # 30% sanse ca suturile tari sa fie respinse in fata portii (rebound)
GK_PARRY_HOLD_CHANCE = 0.20          # 20% sanse de prindere la sut tare

# FIZICA SI SPATIERE (AERISIREA TERENULUI)
PLAYER_COLLISION_DIAMETER = 1.4      # diametru coliziune jucator-jucator (redus de la 2.0 pentru spatii mai aerisite)
OUTFIELD_BALL_RADIUS = 1.3           # raza de control/interceptie minge pentru jucatorii de camp (redusa de la 2.0)

# SUTURI SI FINALIZARE
SHOT_POWER_MIN = 2.4                 # forta minima la sut (plasat / finete)
SHOT_POWER_MAX = 3.3                 # forta maxima la sut (puternic, dar uman si parabil)

# AUT DE MARGINE (OPTIUNI DE PASA SCURTA)
THROW_IN_SUPPORT_DIST_SHORT = 9.0    # distanta primului coechipier de sprijin scurt la aut
THROW_IN_SUPPORT_DIST_MID = 14.0     # distanta celui de-al doilea coechipier de sprijin la aut

# echipa care REPUNE: urca si ofera optiuni langa minge
RESTART_ATTACK_X_PULL = 0.35    # cat se apropie de minge pe X (0 = ramane, 1 = ajunge la minge)
RESTART_ATTACK_Y_PULL = 0.35    # cat se apropie de minge pe Y
RESTART_ATTACK_PUSH = 10.0      # cu cate unitati urca in plus spre poarta adversa

# echipa care APARA: se retrage, se strange pe partea mingii, sta intre minge si poarta
RESTART_DEFEND_X_PULL = 0.15    # cat se apropie de minge pe X
RESTART_DEFEND_Y_PULL = 0.5     # cat se strange pe Y spre minge (acoperire)
RESTART_DEFEND_DROP = 8.0       # cu cate unitati se retrage spre propria poarta
RESTART_DEFEND_GOALSIDE_MARGIN = 3.0  # distanta minima in spatele mingii (goal-side)

# PLAYERS
NUM_OF_PLAYERS = 10