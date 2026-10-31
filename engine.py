from config import STATUS_MATCH_OVER
import zmq
import time
import json
import math
from config import *
import random

class MatchEngine:
    def __init__(self):
        # Motorul de retea
        self.context = zmq.Context()
        # Socket-urile
        self.pub_socket = self.context.socket(zmq.PUB)
        self.router_socket = self.context.socket(zmq.ROUTER)
        # Legarea socket-urilor
        self.pub_socket.bind("tcp://*:5555")
        self.router_socket.bind("tcp://*:5556")
        # Poller
        self.poller = zmq.Poller()
        self.poller.register(self.router_socket, zmq.POLLIN)
        # Mingea
        self.ball = {
            "x": 50.0,
            "y": 50.0,
            "velocity_x": 0.0,
            "velocity_y": 0.0
            }
        # Status joc
        self.game_status = STATUS_START_GAME 
        # Jucatori
        self.players = {}
        # Ultimul jucator care a atins mingea (pentru OUT/CORNER)
        self.last_touch = None
        # Echipa care a lovit mingea cel mai recent si actiunea executata (KICK, PASS, DRIBBLE)
        self.kicking_team = None
        self.kick_action = None
        # Cine are posesiea mingii
        self.possession = None
        # Destinatarul pasei in desfasurare
        self.intended_receiver = None
        # Echipa care incepe de la mijloc
        self.kickoff_team = random.choice(["A", "B"])
        # Goluri
        self.score_A = 0
        self.score_B = 0
        # Timp si setari implicite
        self.start_time = None
        self.match_duration_real_seconds = 180.0 # 3 minute
        # Controlul fluierului arbitrului la faze fixe (OUT, CORNER, GOAL_KICK)
        self.restart_ready = True
        self.restart_start_time = None
        self.restart_ball_placed = True
        self.restart_ball_x = 50.0
        self.restart_ball_y = 50.0
        self.goal_time = None
        self.goal_ball_centered = True

        # Citim settings.json (bridge-ul catre Launcher)
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
                match_rules = settings.get("match_rules", {})

                # Suprascriem varibilele daca exista in fisier
                if "match_duration_real_seconds" in match_rules:
                    self.match_duration_real_seconds = float(match_rules["match_duration_real_seconds"])
                
                print(f"Setari incarcate din JSON: Timp={self.match_duration_real_seconds}s")
        except FileNotFoundError:
            print("Nu s-a gasit settings.json. Folosim setarile implicite.")

    
    def run(self):
        # 1. BUCLA PRINCIPALA A JOCULUI (Tine serverul viu la infinit)
        while True:

            # BUCLA SECUNDARA DE DRENARE A COZII
            while True:
                # Verificam daca sunt mesaje de la jucatori
                events = dict(self.poller.poll(timeout=0))
                # verificam daca un agent a trimis o cerere
                if self.router_socket in events:
                    message = self.router_socket.recv_multipart()
                    agent_identity, agent_message = message
                    intention = json.loads(agent_message.decode('utf-8'))

                    # extragem ID-ul ca string curat
                    agent_id_str = str(intention["agent_id"])
                    # adaugam jucatorul in dictionar daca nu exista
                    if agent_id_str not in self.players:
                        if agent_id_str == "1":  
                            tunnel_x = 45      
                            tunnel_y = 100  
                        else:
                            tunnel_x = 55
                            tunnel_y = 100     

                        player_team = STARTING_POSITIONS.get(agent_id_str, {}).get("team")
                        if not player_team:
                            player_team = intention.get("team", "A" if int(agent_id_str) < 100 else "B")

                        self.players[agent_id_str] = {
                            "start_x" : STARTING_POSITIONS[agent_id_str]["x"],
                            "start_y" : STARTING_POSITIONS[agent_id_str]["y"],
                            "x" : tunnel_x, 
                            "y" : tunnel_y, 
                            "state" : STATE_IDLE,
                            "stun_frames" : 0,
                            "team" : player_team,
                            "role" : STARTING_POSITIONS.get(agent_id_str, {}).get("role", "FIELD")
                        }

                    if str(intention["action"]) in [STATE_KICK, STATE_DRIBBLE, STATE_PASS, STATE_CONTROL_BALL, STATE_GK_CLEAR_BALL]: 
                        if self.game_status in [STATUS_PLAYING, STATUS_OUT, STATUS_CORNER, STATUS_GOAL_KICK]: 

                            # Nu permitem executia sutului daca arbitrul inca tine faza blocata pentru asezarea echipelor
                            if self.game_status in [STATUS_OUT, STATUS_CORNER, STATUS_GOAL_KICK] and (not self.restart_ready or not self.restart_ball_placed):
                                pass
                            else:
                                # extragem pozitia reala a jucatorului din mintea Serverului
                                server_player_x = self.players[agent_id_str]["x"]
                                server_player_y = self.players[agent_id_str]["y"]

                                # calculam distanta absoluta pana la minge
                                distance_to_ball = self.calculate_distance(server_player_x, server_player_y, self.ball["x"], self.ball["y"])

                                # permitem sutul doar daca agentul e fizic langa minge (2.5m in joc deschis, 5.0m la faze fixe)
                                max_kick_dist = 2.5 if self.game_status == STATUS_PLAYING else 5.0
                                if distance_to_ball < max_kick_dist:
                                    self.ball["velocity_x"] = float(intention["kick_vx"])
                                    self.ball["velocity_y"] = float(intention["kick_vy"])
                                    self.last_touch = intention["agent_id"] 
                                    self.possession = agent_id_str
                                    self.kicking_team = self.players[agent_id_str]["team"]
                                    self.kick_action = str(intention["action"])

                                    if "target_agent_id" in intention and intention["target_agent_id"] is not None:
                                        self.intended_receiver = str(intention["target_agent_id"])
                                    elif str(intention["action"]) in [STATE_KICK, STATE_DRIBBLE, STATE_GK_CLEAR_BALL, STATE_CONTROL_BALL]:
                                        self.intended_receiver = None
                                else:
                                    # printam tentativa de "frauda" pentru debug
                                    print(f"Motorul a respins sutul agentului {agent_id_str}. Era la {distance_to_ball:.2f} distanta de minge!")

                    # actualizam starea jucatorului
                    self.players[str(intention["agent_id"])]["state"] = intention["action"]

                    # salvam destinatia DOAR daca agentul ne-a trimis-o
                    if "target_x" in intention and "target_y" in intention:
                        self.players[agent_id_str]["target_x"] = float(intention["target_x"]) 
                        self.players[agent_id_str]["target_y"] = float(intention["target_y"])
                    elif intention["action"] in [STATE_CHASE, STATE_DRIBBLE, STATE_DRIBBLE_DUEL]:
                        self.players[agent_id_str].pop("target_x", None)
                        self.players[agent_id_str].pop("target_y", None)

                    reply_dict = {"status": "approved"}
                    reply_bytes = json.dumps(reply_dict).encode('utf-8')
                    self.router_socket.send_multipart([agent_identity, reply_bytes])
                else:
                    break

            # miscarea agentilor
            for player_id, player_data in self.players.items():

                # daca avem STUN, scadem un time frame si ramanem in IDLE
                if player_data["stun_frames"] > 0:
                    player_data["state"] = STATE_IDLE
                    player_data["stun_frames"] -= 1
                    continue

                # daca suntem in CHASE, fugim direct spre minge
                if player_data["state"] in [STATE_CHASE, STATE_DRIBBLE, STATE_DRIBBLE_DUEL]:
                    if player_data["state"] == STATE_CHASE and str(player_id) == str(self.intended_receiver) and "target_x" in player_data and "target_y" in player_data:
                        self.move_player_towards(player_data, player_data["target_x"], player_data["target_y"], speed = 0.85)
                    else:
                        self.move_player_towards(player_data, self.ball["x"], self.ball["y"], speed = 0.85)
                
                # daca suntem in RESET, ne intoarcem la pozitia initiala de pe teren (1.0 speed)
                elif player_data["state"] == STATE_RESET:
                    self.move_player_towards(player_data, player_data["start_x"], player_data["start_y"], speed = 0.6)
                
                # daca suntem in DO_THROW_IN, DO_CORNER sau DO_GOAL_KICK, merge rapid spre a bate faza fixa (0.70 speed)
                elif player_data["state"] in [STATE_DO_THROW_IN, STATE_DO_CORNER, STATE_DO_GOAL_KICK]:
                    tx_take = self.restart_ball_x if not self.restart_ball_placed else self.ball["x"]
                    ty_take = self.restart_ball_y if not self.restart_ball_placed else self.ball["y"]
                    self.move_player_towards(player_data, tx_take, ty_take, speed = TAKER_POSITIONING_SPEED)

                # daca suntem in WAIT_THROW_IN, WAIT_CORNER sau WAIT_GOAL_KICK, ne asezam sprintat spre tinta primita de la agent
                elif player_data["state"] in [STATE_WAIT_THROW_IN, STATE_WAIT_CORNER, STATE_WAIT_GOAL_KICK]:
                    if "target_x" in player_data and "target_y" in player_data:
                        self.move_player_towards(player_data, player_data["target_x"], player_data["target_y"], speed = WAIT_POSITIONING_SPEED)

                # daca suntem in DEFEND_GOAL, portarul plonjeaza rapid catre tinta
                elif player_data["state"] == STATE_GK_DEFEND_GOAL:
                    if "target_x" in player_data and "target_y" in player_data:
                        self.move_player_towards(player_data, player_data["target_x"], player_data["target_y"], speed = GK_DIVE_SPEED)

                # daca suntem in ATTACK_SUPORT, agentul sprinteaza pe demarcare / sustinere ofensiva (0.82 speed)
                elif player_data["state"] == STATE_ATTACK_SUPPORT:
                    if "target_x" in player_data and "target_y" in player_data:
                        self.move_player_towards(player_data, player_data["target_x"], player_data["target_y"], speed = 0.82)
                
                # daca suntem in DEFEND_SUPPORT, agentul se pozitioneaza in aparare
                elif player_data["state"] == STATE_DEFEND_SUPPORT:
                    if "target_x" in player_data and "target_y" in player_data:
                        self.move_player_towards(player_data, player_data["target_x"], player_data["target_y"], speed = 0.7)
                    

            if self.game_status == STATUS_GOAL and not self.goal_ball_centered:
                if self.goal_time is not None and (time.time() - self.goal_time) < GOAL_CELEBRATION_SECONDS:
                    self.ball["velocity_x"] *= 0.78
                    self.ball["velocity_y"] *= 0.78
                    if self.ball["x"] < 50.0:
                        self.ball["x"] = max(-2.6, min(-0.4, self.ball["x"]))
                    else:
                        self.ball["x"] = min(102.6, max(100.4, self.ball["x"]))
                    self.ball["y"] = max(41.5, min(58.5, self.ball["y"]))
                else:
                    self.ball["velocity_x"] = 0.0
                    self.ball["velocity_y"] = 0.0
                    self.ball["x"] = 50.0
                    self.ball["y"] = 50.0
                    self.goal_ball_centered = True

            if self.game_status in [STATUS_START_GAME, STATUS_GOAL]:
                if self.goal_ball_centered and self.are_players_ready():
                    self.game_status = STATUS_PLAYING
                    
                    # pornim ceasul doar la primul fluier de start
                    if self.start_time is None:
                        self.start_time = time.time()

            if self.game_status in [STATUS_OUT, STATUS_CORNER, STATUS_GOAL_KICK]:
                # 0. Rulare vizuala slow-motion a mingii in afara terenului inainte de asezarea pe punct
                if not self.restart_ball_placed:
                    if self.restart_start_time is not None and (time.time() - self.restart_start_time) < OUT_OF_PLAY_ROLL_SECONDS:
                        self.ball["velocity_x"] *= 0.88
                        self.ball["velocity_y"] *= 0.88
                        self.ball["x"] = max(-3.5, min(103.5, self.ball["x"]))
                        self.ball["y"] = max(-2.8, min(102.8, self.ball["y"]))
                    else:
                        self.ball["velocity_x"] = 0.0
                        self.ball["velocity_y"] = 0.0
                        self.ball["x"] = self.restart_ball_x
                        self.ball["y"] = self.restart_ball_y
                        self.restart_ball_placed = True
                # fluier dinamic pentru asezarea echipelor inainte de executie
                if not self.restart_ready:
                    if self.restart_start_time is not None:
                        elapsed = time.time() - self.restart_start_time
                        # 1. Timp minim de asezare tactica
                        if elapsed >= RESTART_PREPARE_MIN_SECONDS:
                            # 2. Verificam daca executantul a ajuns la minge
                            taker_at_ball = False
                            for p_id, p in self.players.items():
                                if p["state"] in [STATE_DO_THROW_IN, STATE_DO_CORNER, STATE_DO_GOAL_KICK]:
                                    if self.calculate_distance(p["x"], p["y"], self.ball["x"], self.ball["y"]) < 2.5:
                                        taker_at_ball = True
                                        break
                            # Daca executantul este la minge SAU a trecut timpul maxim de siguranta (4.5s)
                            if taker_at_ball or elapsed >= RESTART_PREPARE_MAX_SECONDS:
                                self.restart_ready = True
                    else:
                        self.restart_ready = True

                # cand mingea prinde viteza dupa executie, jocul revine in desfasurare
                if self.restart_ball_placed and self.restart_ready and (self.ball["velocity_x"] != 0.0 or self.ball["velocity_y"] != 0.0):
                    self.game_status = STATUS_PLAYING
                    self.restart_ready = True

            # ===========================================
            # --------- SISTEMUL ANTI-COLLIDE -----------
            # ===========================================
            player_ids = list(self.players.keys())

            # parcurgem fiecare pereche unica
            for i in range(len(player_ids)):
                for j in range(i+1, len(player_ids)):
                    p1_id = player_ids[i]
                    p2_id = player_ids[j]

                    p1 = self.players[p1_id]
                    p2 = self.players[p2_id]

                    # calculam distanta dintre ei
                    dist = self.calculate_distance(p1["x"], p1["y"], p2["x"], p2["y"])

                    # evitam impartirea la zero daca sunt spawnati fix in acelasi pixel
                    if dist == 0:
                        p1["x"] += 0.1
                        dist = 0.1

                    collision_diameter = PLAYER_COLLISION_DIAMETER

                    # au intrat unul in altul?
                    if dist < collision_diameter:
                        # calculam suprapunerea
                        overlap = collision_diameter - dist

                        # directia in care ii impingem
                        dx = (p1["x"] - p2["x"]) / dist
                        dy = (p1["y"] - p2["y"]) / dist

                        # vector perpendicular (tangential) pentru a devia usor jucatorii si a evita blocarea "frunte in frunte"
                        tx = -dy
                        ty = dx

                        # fiecare e impins jumatate de distanta + o usoara alunecare laterala organica
                        push_back = overlap / 2.0
                        slide = push_back * 0.35

                        # aplicam forta de respingere cu separare curata
                        p1["x"] += (dx * push_back) + (tx * slide)
                        p1["y"] += (dy * push_back) + (ty * slide)

                        p2["x"] -= (dx * push_back) + (tx * slide)
                        p2["y"] -= (dy * push_back) + (ty * slide)

                        # Guard Clause pentru ca coechipierii sa nu 
                        # incerce sa faca tackle intre ei
                        if p1["team"] == p2["team"]:
                            continue

                        # MECANICA DE TACKLE
                        if self.possession in [p1_id, p2_id]:

                            if self.possession == p1_id:
                                attacker_id, attacker, defender_id, defender = p1_id, p1, p2_id, p2
                            else:
                                 attacker_id, attacker, defender_id, defender = p2_id, p2, p1_id, p1
                        
                        # deposedarea poate avea loc daca fundasul il urmareste pe atacant
                        # jucatorul de atac nu trebuie sa fie portarul
                            if defender["state"] == STATE_CHASE and attacker["state"] not in [STATE_GK_HOLD_BALL, STATE_GK_CLEAR_BALL]:
                                
                                # viteza mingii pentru a vedea directia de atac
                                vx = self.ball["velocity_x"]
                                vy = self.ball["velocity_y"]
                                speed = math.hypot(vx, vy)

                                # daca atacantul sta pe loc, e deposedare usoara
                                # daca se misca, calculam unghiul
                                if speed > 0.5:
                                    # directia mingii pe axe
                                    nx_ball = vx / speed
                                    ny_ball = vy / speed

                                    # vectorul de impact fata de atacant
                                    impact_dx = defender["x"] - attacker["x"]
                                    impact_dy = defender["y"] - attacker["y"]
                                    dist_impact = math.hypot(impact_dx, impact_dy)

                                    if dist_impact > 0:
                                        # directia aparatorului pe axe
                                        nx_def = impact_dx / dist_impact
                                        ny_def = impact_dy / dist_impact

                                        # aplicam produsul scalar
                                        dot_product = (nx_ball * nx_def) + (ny_ball * ny_def)


                                        # cazul 1: vine din fata sau usor lateral
                                        # sansa de deposedare creste cu cat e mai "in fata"
                                        if dot_product > 0.0:
                                            tackle_chance = 0.4 + dot_product * 0.5
                                        
                                        # cazul 2: vine din spate
                                        # sansa de deposedare scade cu cat e mai "in spate"
                                        else:
                                            tackle_chance = 0.3 + dot_product * 0.2

                                        # TACKLE REUSIT => ATTACKER STUN
                                        if random.random() < tackle_chance:
                                            attacker["stun_frames"] = random.randint(5,35)
                                            attacker["state"] = STATE_IDLE
                                            self.possession = defender_id

                                            # rezolvarea suprapunerii -> knockback
                                            # impingem atacantul in spate ca efect al deposedarii
                                            attacker["x"] -= nx_def * 2.0
                                            attacker["y"] -= ny_def * 2.0

                                                # respingem mingea din piciorul atacantului
                                            self.ball["velocity_x"] = nx_def * 1.0
                                            self.ball["velocity_y"] = ny_def * 1.0
                                            self.last_touch = defender_id
                                            self.possession = None
                                            self.intended_receiver = None
                                            self.kicking_team = defender.get("team")
                                            self.kick_action = None
                                            print(f"Agentul {defender_id} a reusit tackle")
                                        
                                        # TACKLE RATAT => DEFENDER STUN
                                        else:
                                            # tackle ratat din fata => Stun mediu
                                            if dot_product > 0.5:
                                                stun = random.randint(16,25)
                                            
                                            # tackle ratat din corp la corp => Stun mic
                                            elif dot_product >= -0.5:
                                                stun = random.randint(5,15)

                                            # tackle ratat din spate => Stun mare
                                            else:
                                                stun = random.randint(26,35)

                                            defender["state"] = STATE_IDLE
                                            defender["stun_frames"] = stun
                                            print(f"Agentul {defender_id} NU a reusit tackle")
                                else:
                                    # Atacantul sta pe loc sau se misca foarte lent (speed <= 0.5) => deposedare din presiune imediata
                                    impact_dx = defender["x"] - attacker["x"]
                                    impact_dy = defender["y"] - attacker["y"]
                                    dist_impact = math.hypot(impact_dx, impact_dy)
                                    if dist_impact > 0:
                                        nx_def = impact_dx / dist_impact
                                        ny_def = impact_dy / dist_impact
                                    else:
                                        nx_def, ny_def = 1.0, 0.0

                                    tackle_chance = 0.70
                                    if random.random() < tackle_chance:
                                        attacker["stun_frames"] = random.randint(5, 20)
                                        attacker["state"] = STATE_IDLE
                                        self.possession = defender_id
                                        self.last_touch = defender_id
                                        attacker["x"] -= nx_def * 1.5
                                        attacker["y"] -= ny_def * 1.5
                                        self.ball["velocity_x"] = nx_def * 0.8
                                        self.ball["velocity_y"] = ny_def * 0.8
                                        self.intended_receiver = None
                                        self.kicking_team = defender.get("team")
                                        self.kick_action = None
                                        print(f"Agentul {defender_id} a deposedat atacantul oprit din cursa")
                                    else:
                                        defender["stun_frames"] = random.randint(8, 18)
                                        defender["state"] = STATE_IDLE
                                        print(f"Agentul {defender_id} a faultat usor sau a fost fentat")

            # ==================================================
            # ------------ SISTEMUL ANTI-COLLIDE ---------------
            # ==================================================



            # miscarea mingii
            # 1. aplicam viteza
            self.ball['x'] += self.ball['velocity_x']
            self.ball['y'] += self.ball['velocity_y']
            # 2. aplicam frecarea
            self.ball['velocity_x'] *= 0.95
            self.ball['velocity_y'] *= 0.95

            # Daca o pasa s-a oprit / a pierdut elanul (viteza sub 0.3), mingea devine libera pentru oricine
            ball_current_speed = math.hypot(self.ball['velocity_x'], self.ball['velocity_y'])
            if self.intended_receiver is not None and ball_current_speed < 0.3:
                self.intended_receiver = None

            # verificam daca mingea e libera sau in posesia cuiva
            if self.possession is not None:
                possessor_data = self.players[self.possession]
                # Daca posesorul este portarul care tine mingea, mingea ramane lipita de el
                if possessor_data.get("role") == "GK" and possessor_data.get("state") in [STATE_GK_HOLD_BALL, STATE_GK_DEFEND_GOAL]:
                    offset_x = 0.5 if possessor_data["x"] < 50.0 else -0.5
                    self.ball["x"] = possessor_data["x"] + offset_x
                    self.ball["y"] = possessor_data["y"]
                    self.ball["velocity_x"] = 0.0
                    self.ball["velocity_y"] = 0.0
                else:
                    distance_possessor_to_ball = self.calculate_distance(possessor_data["x"], possessor_data["y"], self.ball["x"], self.ball["y"])
                    if distance_possessor_to_ball > 3.0:
                        self.possession = None

            # ==================================================
            # ------ SISTEMUL ANTI-COLLIDE JUCATOR-MINGE -------
            # ==================================================

            for player_id, player_data in self.players.items():
                
                # daca jucatorul a cazut la pamant, mingea trece peste el
                # pentru a nu bloca driblingurile lansate pe langa el
                if player_data["stun_frames"] > 0:
                    continue

                is_gk = (player_data.get("role") == "GK" or player_id in ["1", "101"])
                if self.game_status != STATUS_PLAYING:
                    break
                collision_radius = GK_SAVE_RADIUS if is_gk else OUTFIELD_BALL_RADIUS

                distance_to_ball = self.calculate_distance(player_data["x"], player_data["y"], self.ball["x"], self.ball["y"])

                # pragul de coliziune
                if distance_to_ball < collision_radius and player_id != self.possession:
                    
                    dx = self.ball["x"] - player_data["x"]
                    dy = self.ball["y"] - player_data["y"]

                    dot_product = dx * self.ball["velocity_x"] + dy * self.ball["velocity_y"]

                    # mingea se indreapta spre jucator
                    if dot_product < 0:
                        
                        # calculam viteza mingii inainte de impact
                        ball_speed = math.hypot(self.ball["velocity_x"], self.ball["velocity_y"])

                        # ========================================================
                        # INTERVENTIE PORTAR (SPECIALIZATA PENTRU REALISM FOTBAL)
                        # ========================================================
                        if is_gk:
                            # 1. Prindere sigura daca mingea e usoara/medie SAU vine fix in corpul portarului
                            if ball_speed < GK_CATCH_SPEED_THRESHOLD or distance_to_ball < 1.3:
                                self.ball["velocity_x"] = 0.0
                                self.ball["velocity_y"] = 0.0
                                self.ball["x"] = player_data["x"] + (0.5 if player_data["x"] < 50.0 else -0.5)
                                self.ball["y"] = player_data["y"]
                                self.last_touch = player_id
                                self.possession = player_id
                                self.intended_receiver = None
                                print(f"Portarul {player_id} a retinut mingea sigur in brate!")
                                break

                            # 2. Sut tare -> Portarul intervine (50% Corner, 30% Rebound, 20% Prindere)
                            save_roll = random.random()
                            if save_roll < GK_PARRY_CORNER_CHANCE:
                                # DEVIERE IN CORNER: Portarul impinge mingea peste linia de fund, pe langa bara sau peste transversala
                                self.last_touch = player_id
                                self.possession = None
                                self.intended_receiver = None

                                deflection_side = -1.0 if self.ball["y"] < 50.0 else 1.0
                                vy_push = deflection_side * random.uniform(1.3, 2.3)
                                
                                if player_data["team"] == "A":
                                    # Apara poarta din stanga (x <= 0). Mingea e deviata spre x <= 0
                                    self.ball["velocity_x"] = random.uniform(-2.2, -1.3)
                                    self.ball["velocity_y"] = vy_push
                                else:
                                    # Apara poarta din dreapta (x >= 100). Mingea e deviata spre x >= 100
                                    self.ball["velocity_x"] = random.uniform(1.3, 2.2)
                                    self.ball["velocity_y"] = vy_push

                                print(f"Parada spectaculoasa a portarului {player_id}! Mingea este deviata in CORNER!")
                                break

                            elif save_roll < (GK_PARRY_CORNER_CHANCE + GK_PARRY_REBOUND_CHANCE):
                                # RESPINGERE IN FATA PORTII (REBOUND): mingea este blocata si sare in careu
                                self.last_touch = player_id
                                self.possession = None
                                self.intended_receiver = None

                                if player_data["team"] == "A":
                                    self.ball["velocity_x"] = random.uniform(0.6, 1.2)  # sare inapoi spre teren
                                else:
                                    self.ball["velocity_x"] = random.uniform(-1.2, -0.6)

                                self.ball["velocity_y"] = random.uniform(-0.8, 0.8)
                                print(f"Reflex excelent al portarului {player_id}! Respingere in fata portii (rebound)!")
                                break

                            else:
                                # PRINDERE LA SUT TARE
                                self.ball["velocity_x"] = 0.0
                                self.ball["velocity_y"] = 0.0
                                self.ball["x"] = player_data["x"] + (0.5 if player_data["x"] < 50.0 else -0.5)
                                self.ball["y"] = player_data["y"]
                                self.last_touch = player_id
                                self.possession = player_id
                                self.intended_receiver = None
                                print(f"Portarul {player_id} retine un sut puternic!")
                                break

                        # ========================================================
                        # INTERVENTIE JUCATOR DE CAMP
                        # ========================================================
                        else:
                            player_team = player_data.get("team")
                            kicker_team = self.kicking_team or (self.players[str(self.last_touch)]["team"] if str(self.last_touch) in self.players else None)
                            is_teammate = (player_team is not None and kicker_team is not None and player_team == kicker_team)
                            is_intended_receiver = (self.intended_receiver is not None and str(player_id) == str(self.intended_receiver))

                            # 1. Preluare curata pentru coechipier sau destinatar:
                            # O pasa sau minge trimisa de un coechipier NU ricoseaza NICIODATA, indiferent de forta!
                            if is_teammate or is_intended_receiver:
                                self.ball["velocity_x"] = 0.0
                                self.ball["velocity_y"] = 0.0
                                self.last_touch = player_id
                                self.possession = player_id
                                self.intended_receiver = None
                                self.kicking_team = player_team
                                self.kick_action = None
                                break # oprim cautarea ca sa nu loveasca 2 jucatori in aceeasi milisecunda

                            # 2. Interventie adversar:
                            else:
                                # A. Blocaj defensiv la SUT puternic pe poarta (STATE_KICK, viteza >= 2.2) => Ricoseu / Deviere
                                if self.kick_action == STATE_KICK and ball_speed >= 2.2:
                                    self.ball["velocity_x"] *= random.uniform(-0.5, 0.3)
                                    # deviem mingea random, inspre margine
                                    deflection_y = random.choice([-1, 1])
                                    self.ball["velocity_y"] = deflection_y * random.uniform(ball_speed * 0.8, ball_speed * 1.5)
                                    self.last_touch = player_id
                                    self.possession = None
                                    self.intended_receiver = None
                                    self.kicking_team = player_team
                                    self.kick_action = None
                                    break
                                # B. Interceptie curata de catre adversar (pasa, degajare, minge libera)
                                else:
                                    self.ball["velocity_x"] = 0.0
                                    self.ball["velocity_y"] = 0.0
                                    self.last_touch = player_id
                                    self.possession = player_id
                                    self.intended_receiver = None
                                    self.kicking_team = player_team
                                    self.kick_action = None
                                    break

            # ==================================================
            # ------ SISTEMUL ANTI-COLLIDE JUCATOR-MINGE -------
            # ==================================================

            # ==================================================
            # VERIFICAREA IESIRII DIN TEREN (DOAR IN TIMPUL JOCULUI ACTIV)
            # ==================================================
            if self.game_status == STATUS_PLAYING:

                # GOL pentru echipa B sau IESIRE LINIE DE FUND (STÂNGA: x <= 0)
                if self.ball['x'] <= 0:
                    if self.ball['y'] >= 41.0 and self.ball['y'] <= 59.0:
                        print("GOAL!!! GOAL!!! GOAL!!!")
                        self.game_status = STATUS_GOAL
                        self.possession = None
                        self.intended_receiver = None
                        self.goal_time = time.time()
                        self.goal_ball_centered = False
                        # Lasam mingea sa intre si sa se opreasca in plasa portii pentru 3.5 secunde
                        self.ball['velocity_x'] = max(-0.45, self.ball['velocity_x'] * 0.35)
                        self.ball['velocity_y'] *= 0.25
                        self.kickoff_team = "A" 
                        self.score_B += 1
                    else:
                        # Mingea a iesit in spatele portii A (stanga)
                        last_touch_team = self.players[str(self.last_touch)]["team"] if str(self.last_touch) in self.players else "B"
                        self.possession = None
                        self.intended_receiver = None
                        self.ball['velocity_x'] *= 0.35
                        self.ball['velocity_y'] *= 0.35
                        self.restart_ready = False
                        self.restart_ball_placed = False
                        self.restart_start_time = time.time()
                        
                        if last_touch_team == "A":
                            # A atins ultimul -> CORNER pentru Echipa B
                            print("CORNER pentru Echipa B!")
                            self.game_status = STATUS_CORNER
                            self.restart_ball_x = 1.0
                            self.restart_ball_y = 1.0 if self.ball['y'] < 50.0 else 99.0
                        else:
                            # B atins ultimul -> AUT DE POARTA (GOAL KICK) pentru Echipa A
                            print("AUT DE POARTA pentru Echipa A!")
                            self.game_status = STATUS_GOAL_KICK
                            self.restart_ball_x = 6.0
                            self.restart_ball_y = 50.0

                # GOL pentru echipa A sau IESIRE LINIE DE FUND (DREAPTA: x >= 100)
                elif self.ball['x'] >= 100:
                    if self.ball['y'] >= 41.0 and self.ball['y'] <= 59.0:
                        print("GOAL!!! GOAL!!! GOAL!!!")
                        self.game_status = STATUS_GOAL
                        self.possession = None
                        self.intended_receiver = None
                        self.goal_time = time.time()
                        self.goal_ball_centered = False
                        # Lasam mingea sa intre si sa se opreasca in plasa portii pentru 3.5 secunde
                        self.ball['velocity_x'] = min(0.45, self.ball['velocity_x'] * 0.35)
                        self.ball['velocity_y'] *= 0.25
                        self.kickoff_team = "B"
                        self.score_A += 1
                    else:
                        # Mingea a iesit in spatele portii B (dreapta)
                        last_touch_team = self.players[str(self.last_touch)]["team"] if str(self.last_touch) in self.players else "A"
                        self.possession = None
                        self.intended_receiver = None
                        self.ball['velocity_x'] *= 0.35
                        self.ball['velocity_y'] *= 0.35
                        self.restart_ready = False
                        self.restart_ball_placed = False
                        self.restart_start_time = time.time()
                        
                        if last_touch_team == "B":
                            # B atins ultimul -> CORNER pentru Echipa A
                            print("CORNER pentru Echipa A!")
                            self.game_status = STATUS_CORNER
                            self.restart_ball_x = 99.0
                            self.restart_ball_y = 1.0 if self.ball['y'] < 50.0 else 99.0
                        else:
                            # A atins ultimul -> AUT DE POARTA (GOAL KICK) pentru Echipa B
                            print("AUT DE POARTA pentru Echipa B!")
                            self.game_status = STATUS_GOAL_KICK
                            self.restart_ball_x = 94.0
                            self.restart_ball_y = 50.0

                # AUT DE MARGINE (SUS: y <= 0)
                elif self.ball['y'] <= 0:
                    print("Out de margine!")     
                    self.game_status = STATUS_OUT
                    self.restart_ready = False
                    self.restart_ball_placed = False
                    self.restart_start_time = time.time()
                    self.possession = None
                    self.intended_receiver = None
                    self.restart_ball_x = max(2.0, min(98.0, self.ball['x']))
                    self.restart_ball_y = 1.0
                    self.ball['velocity_x'] *= 0.35
                    self.ball['velocity_y'] *= 0.35

                # AUT DE MARGINE (JOS: y >= 100)
                elif self.ball['y'] >= 100:
                    print("Out de margine!")       
                    self.game_status = STATUS_OUT
                    self.restart_ready = False
                    self.restart_ball_placed = False
                    self.restart_start_time = time.time()
                    self.possession = None
                    self.intended_receiver = None
                    self.restart_ball_x = max(2.0, min(98.0, self.ball['x']))
                    self.restart_ball_y = 99.0
                    self.ball['velocity_x'] *= 0.35
                    self.ball['velocity_y'] *= 0.35

            # calculam timpul virtual curent
            virtual_minutes = 0.0
            if self.start_time is not None:
                real_elapsed = time.time() - self.start_time
                virtual_minutes = (real_elapsed / self.match_duration_real_seconds) * 90.0

                # oprim ceasul la 90:00
                if virtual_minutes > 90:
                    virtual_minutes = 90.0
            
            # ==================================================
            # -------------- LOGICA DE MATCH OVER --------------
            # ==================================================
            # Daca timpul a atins 90 minute (si nu suntem deja in match over)
            if virtual_minutes >= 90.0 and self.game_status != STATUS_MATCH_OVER:
                print("MATCH OVER! Fluier final.")
                self.game_status = STATUS_MATCH_OVER

                # Oprim mingea pentru a semnaliza sfarsitul
                self.ball['velocity_x'] *= 0.2
                self.ball['velocity_y'] *= 0.2

            # broadcast al jocului
            # dupa ce am facut update-ul agentilor
            game_state = {
                "ball" : self.ball,
                "players" : self.players,
                "game_status" : self.game_status,
                "last_touch" : self.last_touch,
                "possession" : self.possession,
                "kickoff_team" : self.kickoff_team,
                "intended_receiver" : self.intended_receiver,
                "score_A" : self.score_A,
                "score_B" : self.score_B,
                "time" : virtual_minutes,
                "restart_ready" : self.restart_ready,
                "restart_ball_placed" : self.restart_ball_placed,
                "restart_ball_x" : self.restart_ball_x,
                "restart_ball_y" : self.restart_ball_y
            }
            
            

            self.pub_socket.send_json(game_state)
            # delay pentru a limita FPS-ul
            time.sleep(0.05)

    def move_player_towards(self, player_data, target_x, target_y, speed):
        player_x = player_data["x"]
        player_y = player_data["y"]

        diff_x = target_x - player_x
        diff_y = target_y - player_y
        distance = math.hypot(diff_x, diff_y)

        # daca distanta e mai mare decat viteza, face pasul cu viteza respectiva
        if distance > speed:
            player_data["x"] += (diff_x / distance) * speed
            player_data["y"] += (diff_y / distance) * speed
        else:
            # clamping
            player_data["x"] = target_x
            player_data["y"] = target_y

    def are_players_ready(self):
        # daca nu avem destui jucatori conectati, nu suntem gata
        if len(self.players) < NUM_OF_PLAYERS:
            return False

        # verificam fizic fiecare jucator
        for p in self.players.values():
            dx = p["x"] - p["start_x"]
            dy = p["y"] - p["start_y"]

            distance = math.hypot(dx, dy)

            # daca un singur jucator e la distanta de >=2, nu e gata, deci
            # meciul nu incepe
            if distance >= 5.0:
                return False

        # toti sunt la pozitiile lor!
        return True
    
    # calculam distanta dintre doua puncte oarecare pe server
    def calculate_distance(self, x1, y1, x2, y2):
        distance = math.sqrt((x1 - x2)**2 + (y1 - y2)**2)
        return distance
             
    