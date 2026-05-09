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
            "x": 50,
            "y": 50,
            "velocity_x": 0.0,
            "velocity_y": 0.0
            }
        # Status joc
        self.game_status = STATUS_START_GAME 
        # Jucatori
        self.players = {}
        # Ultimul jucator care a atins mingea (pentru OUT/CORNER)
        self.last_touch = None
        # Cine are posesiea mingii
        self.possession = None

    
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

                        self.players[agent_id_str] = {
                            "start_x" : STARTING_POSITIONS[agent_id_str]["x"],
                            "start_y" : STARTING_POSITIONS[agent_id_str]["y"],
                            "x" : tunnel_x, 
                            "y" : tunnel_y, 
                            "state" : STATE_IDLE,
                            "stun_frames" : 0,
                            "team" : intention.get("team", "Unknown") 
                        }

                    if str(intention["action"]) in [STATE_KICK, STATE_DRIBBLE, STATE_PASS, STATE_GK_CLEAR_BALL]: 
                        if self.game_status in [STATUS_PLAYING, STATUS_OUT]: 

                            # extragem pozitia reala a jucatorului din mintea Serverului
                            server_player_x = self.players[agent_id_str]["x"]
                            server_player_y = self.players[agent_id_str]["y"]

                            # calculam distanta absoluta pana la minge
                            distance_to_ball = self.calculate_distance(server_player_x, server_player_y, self.ball["x"], self.ball["y"])

                            # permitem sutul doar daca agentul e fizic langa minge
                            if distance_to_ball < 5.0:
                                self.ball["velocity_x"] = float(intention["kick_vx"])
                                self.ball["velocity_y"] = float(intention["kick_vy"])
                                self.last_touch = intention["agent_id"] 
                                self.possession = agent_id_str
                            else:
                                # printam tentativa de "frauda" pentru debug
                                print(f"Motorul a respins sutul agentului {agent_id_str}. Era la {distance_to_ball:.2f} distanta de minge!")

                    # actualizam starea jucatorului
                    self.players[str(intention["agent_id"])]["state"] = intention["action"]

                    # salvam destinatia DOAR daca agentul ne-a trimis-o
                    if "target_x" in intention and "target_y" in intention:
                        self.players[agent_id_str]["target_x"] = float(intention["target_x"]) 
                        self.players[agent_id_str]["target_y"] = float(intention["target_y"])

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

                # daca suntem in CHASE, fugim spre minge (1.5 speed)
                if player_data["state"] in [STATE_CHASE, STATE_DRIBBLE, STATE_DRIBBLE_DUEL]:
                    self.move_player_towards(player_data, self.ball["x"], self.ball["y"], speed = 1.5)
                
                # daca suntem in RESET, ne intoarcem la pozitia initiala de pe teren (1.0 speed)
                elif player_data["state"] == STATE_RESET:
                    self.move_player_towards(player_data, player_data["start_x"], player_data["start_y"], speed = 1.0)
                
                # daca suntem in DO_THROW_IN, merge usor spre a bate out-ul (0.5 speed)
                elif player_data["state"] == STATE_DO_THROW_IN:
                    self.move_player_towards(player_data, self.ball["x"], self.ball["y"], speed = 0.5)

                # daca suntem in DEFEND_GOAL, il mutam catre tinta salvata in mintea serverului
                elif player_data["state"] == STATE_GK_DEFEND_GOAL:
                    if "target_x" in player_data and "target_y" in player_data:
                        self.move_player_towards(player_data, player_data["target_x"], player_data["target_y"], speed = 1.0)

            if self.game_status in [STATUS_START_GAME, STATUS_GOAL]:
                if self.are_players_ready():
                    self.game_status = STATUS_PLAYING

            if self.game_status == STATUS_OUT:
                if self.ball["velocity_x"] != 0.0 and self.ball["velocity_y"] != 0.0:
                    self.game_status = STATUS_PLAYING

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

                    collision_diameter = 2.0

                    # au intrat unul in altul?
                    if dist < collision_diameter:
                        # calculam suprapunerea
                        overlap = collision_diameter - dist

                        # directia in care ii impingem
                        dx = (p1["x"] - p2["x"]) / dist
                        dy = (p1["y"] - p2["y"]) / dist

                        # fiecare e impins jumatate de distanta
                        push_back = overlap / 2.0

                        # aplicam forta de respingere
                        p1["x"] += dx * push_back
                        p1["y"] += dy * push_back

                        p2["x"] -= dx * push_back
                        p2["y"] -= dy * push_back

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
                                            attacker["stun_frames"] = random.randint(5,55)
                                            attacker["state"] = STATE_IDLE
                                            self.possession = defender_id
                                                # respingem mingea din piciorul atacantului
                                            self.ball["velocity_x"] = nx_def * 1.0
                                            self.ball["velocity_y"] = ny_def * 1.0
                                            print(f"Agentul {defender_id} a reusit tackle")
                                        
                                        # TACKLE RATAT => DEFENDER STUN
                                        else:
                                            # tackle ratat din fata => Stun mediu
                                            if dot_product > 0.5:
                                                stun = random.randint(20,35)
                                            
                                            # tackle ratat din corp la corp => Stun mic
                                            elif dot_product >= -0.5:
                                                stun = random.randint(5,15)

                                            # tackle ratat din spate => Stun mare
                                            else:
                                                stun = random.randint(40,55)

                                            defender["state"] = STATE_IDLE
                                            defender["stun_frames"] = stun
                                            print(f"Agentul {defender_id} NU a reusit tackle")

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

            # verificam daca mingea e libera sau in posesia cuiva
            if self.possession is not None:
                possessor_data = self.players[self.possession]
                distance_possessor_to_ball = self.calculate_distance(possessor_data["x"], possessor_data["y"], self.ball["x"], self.ball["y"])
                if distance_possessor_to_ball > 3.0:
                    self.possession = None

            # ==================================================
            # ------ SISTEMUL ANTI-COLLIDE JUCATOR-MINGE -------
            # ==================================================

            for player_id, player_data in self.players.items():
                
                distance_to_ball = self.calculate_distance(player_data["x"], player_data["y"], self.ball["x"], self.ball["y"])

                # pragul de coliziune
                if distance_to_ball < 2.0 and player_id != self.possession:
                    
                    dx = self.ball["x"] - player_data["x"]
                    dy = self.ball["y"] - player_data["y"]

                    dot_product = dx * self.ball["velocity_x"] + dy * self.ball["velocity_y"]

                    # mingea se indreapta spre jucator
                    if dot_product < 0:
                        
                        # calculam viteza mingii inainte de impact
                        ball_speed = math.hypot(self.ball["velocity_x"], self.ball["velocity_y"])

                        # daca e pasa/sut slab => Preluare / Prindere
                        if ball_speed < 1.5:
                            self.ball["velocity_x"] = 0.0
                            self.ball["velocity_y"] = 0.0
                            self.last_touch = player_id
                            self.possession = player_id
                            break # oprim cautarea ca sa nu loveasca 2 jucatori in aceeasi milisecunda
                        # daca e sut puternic => Ricoseu / Respingere
                        else:
                            self.ball["velocity_x"] *= random.uniform(-0.5, 0.3)
                            # deviem mingea random, inspre margine
                            deflection_y = random.choice([-1, 1])
                            self.ball["velocity_y"] = deflection_y * random.uniform(ball_speed * 0.8, ball_speed * 1.5)
                            self.last_touch = player_id
                            self.possession = None
                            break

            # ==================================================
            # ------ SISTEMUL ANTI-COLLIDE JUCATOR-MINGE -------
            # ==================================================

            # OUT + GOAL?
            if self.ball['x'] <= 0:
                if self.ball['y'] >= 40 and self.ball['y'] <=60:
                    print("GOAL!!! GOAL!!! GOAL!!!")
                    self.game_status = STATUS_GOAL
                    self.possession = None
                    self.ball['velocity_x'] = 0
                    self.ball['velocity_y'] = 0
                    self.ball['x'] = 50
                    self.ball['y'] = 50
                else:
                    self.ball['velocity_x'] *= -1
                    
                    self.ball['x'] = 0
            if self.ball['x'] >= 100:
                if self.ball['y'] >= 40 and self.ball['y'] <=60:
                    print("GOAL!!! GOAL!!! GOAL!!!")
                    self.game_status = STATUS_GOAL
                    self.possession = None
                    self.ball['velocity_x'] = 0
                    self.ball['velocity_y'] = 0
                    self.ball['x'] = 50
                    self.ball['y'] = 50
                else:
                    self.ball['velocity_x'] *= -1
                    self.ball['x'] = 100
            if self.ball['y'] <= 0:
                # pentru a avea o singura data print-ul
                if self.ball['velocity_y'] != 0:   
                    print("Out de margine!")     
                self.game_status = STATUS_OUT
                self.possession = None
                self.ball['y'] = 0
                self.ball['velocity_x'] = 0
                self.ball['velocity_y'] = 0
            if self.ball['y'] >= 100:
                # pentru a avea o singura data print-ul
                if self.ball['velocity_y'] != 0:    
                    print("Out de margine!")       
                self.game_status = STATUS_OUT
                self.possession = None
                self.ball['y'] = 100
                self.ball['velocity_x'] = 0
                self.ball['velocity_y'] = 0

            # broadcast al jocului
            # dupa ce am facut update-ul agentilor
            game_state = {
                "ball" : self.ball,
                "players" : self.players,
                "game_status" : self.game_status,
                "last_touch" : self.last_touch,
                "possession" : self.possession 
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
            if distance >= 2.0:
                return False

        # toti sunt la pozitiile lor!
        return True
    
    # calculam distanta dintre doua puncte oarecare pe server
    def calculate_distance(self, x1, y1, x2, y2):
        distance = math.sqrt((x1 - x2)**2 + (y1 - y2)**2)
        return distance
             
    