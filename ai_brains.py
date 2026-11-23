import os
import json

# Lista tuturor arhitecturilor AI disponibile in Launcher.
# Pe masura ce antrenam modele noi (Genetic AI, DQN Agent, PPO Agent), le inregistram aici
# si vor aparea automat in meniul dropdown din launcher.py pentru ambele echipe!
BASE_BUILD_NAME = "Base Build"
GENETIC_BUILD_NAME = "Genetic AI (GA)"

# Genomul implicit (exact parametrii tactici ai Base Build-ului nostru!)
DEFAULT_GENOME = {
    # --- Dribling & Progresie cu mingea ---
    "base_dribble_score": 92.0,
    "frontal_freedom_mult": 8.0,
    "open_lane_mult": 5.2,
    "carry_momentum_early": 38.0,
    "box_drive_bonus": 48.0,
    "dribble_duel_dist": 2.3,

    # --- Pase, Demarcare & Constructie ---
    "base_pass_score": 100.0,
    "optimal_pass_dist": 13.0,
    "forward_pass_mid": 44.0,
    "forward_pass_final": 62.0,
    "through_ball_bonus": 36.0,
    "better_spot_bonus": 42.0,
    "one_two_bonus": 20.0,
    "anti_pingpong_penalty": 55.0,
    "back_pass_penalty": 75.0,
    "attack_support_push": 1.0,

    # --- Suturi & Finalizare ---
    "kick_base_close": 242.0,
    "kick_base_box": 202.0,
    "kick_base_edge": 172.0,
    "shoot_range_max": 22.5,

    # --- Pressing & Compactitate Defensiva ---
    "press_engage_dist": 24.0,
    "secondary_press_def": 14.5,
    "secondary_press_att": 11.5,
    "def_line_base_x": 15.5,
    "def_cover_dist": 6.2,
    "def_mark_weight": 0.48,
}

# Limite realiste si generoase pentru evolutia genetica pe termen lung (fara plafoane artificiale)
GENOME_BOUNDS = {
    "base_dribble_score": (45.0, 140.0),
    "frontal_freedom_mult": (4.0, 14.0),
    "open_lane_mult": (2.0, 10.5),
    "carry_momentum_early": (5.0, 75.0),
    "box_drive_bonus": (10.0, 90.0),
    "dribble_duel_dist": (1.4, 3.6),
    "base_pass_score": (65.0, 160.0),
    "optimal_pass_dist": (8.0, 21.0),
    "forward_pass_mid": (15.0, 85.0),
    "forward_pass_final": (20.0, 110.0),
    "through_ball_bonus": (10.0, 85.0),
    "better_spot_bonus": (10.0, 85.0),
    "one_two_bonus": (0.0, 50.0),
    "anti_pingpong_penalty": (15.0, 95.0),
    "back_pass_penalty": (20.0, 145.0),
    "attack_support_push": (0.65, 1.40),
    "kick_base_close": (200.0, 300.0),
    "kick_base_box": (160.0, 260.0),
    "kick_base_edge": (125.0, 225.0),
    "shoot_range_max": (18.0, 27.0),
    "press_engage_dist": (14.0, 34.0),
    "secondary_press_def": (9.0, 22.0),
    "secondary_press_att": (7.0, 19.0),
    "def_line_base_x": (10.0, 26.0),
    "def_cover_dist": (3.5, 10.0),
    "def_mark_weight": (0.25, 0.72),
}


def get_available_ai_builds():
    """
    Returneaza lista build-urilor AI disponibile pentru selectie in Launcher.
    Detecteaza automat si modelele antrenate salvate in folderul models/.
    """
    builds = [BASE_BUILD_NAME]
    if os.path.exists("models/genetic_best.json"):
        builds.append(GENETIC_BUILD_NAME)
    if os.path.exists("models/dqn_policy.npz") or os.path.exists("models/dqn_policy.pt"):
        builds.append("DQN Agent (RL)")
    if os.path.exists("models/ppo_policy.npz") or os.path.exists("models/ppo_policy.pt"):
        builds.append("PPO Agent (RL)")
    return builds


def get_short_ai_tag(build_name):
    """
    Eticheta scurta pentru HUD (ex: 'BASE', 'GA', 'DQN', 'PPO').
    """
    name = str(build_name or BASE_BUILD_NAME).upper()
    if "GENETIC" in name or "(GA)" in name:
        return "GA"
    if "DQN" in name:
        return "DQN"
    if "PPO" in name:
        return "PPO"
    return "BASE"


class BaseBrain:
    """
    Creierul implicit (Heuristic Tactical AI - Base Build).
    Toate modelele viitoare de ML (GeneticBrain, DQNBrain, PPOBrain) mostenesc aceasta interfata
    pentru a putea fi incarcate independent pe Echipa A (Stanga/Red) si Echipa B (Dreapta/Blue).
    """
    def __init__(self, build_name=BASE_BUILD_NAME, custom_params=None):
        self.build_name = build_name
        self.params = dict(DEFAULT_GENOME)
        if custom_params:
            for k, v in custom_params.items():
                if k in self.params:
                    self.params[k] = float(v)

    def choose_action_override(self, state_features, heuristic_context):
        """
        Returneaza None pentru a folosi decizia euristica parametrizata din self.params.
        Modelele RL (DQN / PPO) vor suprascrie aceasta metoda pentru a returna actiunea aleasa de retea.
        """
        return None


class GeneticBrain(BaseBrain):
    """
    Creier evoluat prin Algoritm Genetic (GA).
    Incarca genomul optim din models/genetic_best.json (sau un genom dat in memorie).
    """
    def __init__(self, model_path="models/genetic_best.json", genome_dict=None):
        loaded_params = dict(DEFAULT_GENOME)
        if genome_dict is not None:
            loaded_params.update(genome_dict)
        elif os.path.exists(model_path):
            try:
                with open(model_path, "r") as f:
                    data = json.load(f)
                    genome = data.get("genome", data)
                    for k, v in genome.items():
                        if k in loaded_params:
                            loaded_params[k] = float(v)
            except Exception as e:
                print(f"ATENTIE: Nu am putut incarca {model_path} ({e}). Folosim Base Build.")
        super().__init__(build_name=GENETIC_BUILD_NAME, custom_params=loaded_params)


def load_brain(build_name):
    """
    Factory care incarca creierul AI corespunzator numelui selectat din Launcher.
    """
    build_name = str(build_name or BASE_BUILD_NAME)
    if "Genetic" in build_name or "(GA)" in build_name:
        return GeneticBrain()
    return BaseBrain(build_name=build_name)
