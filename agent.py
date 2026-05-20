import zmq
import json
import math
import random
from config import *

class PlayerAgent:
    def __init__(self, agent_id, team):
        self.x = 0.0
        self.y = 0.0
        self.start_x = self.x
        self.start_y = self.y
        self.state = STATE_IDLE
        self.agent_id=agent_id
        self.team = team
        self.last_logged_state = None
        self.stun_frames = 0
        self.duel_frames = 0
        self.ignore_ball_frames = 0
        self.context=zmq.Context()
        # Sockets
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self.dealer_socket = self.context.socket(zmq.DEALER)
        self.dealer_socket.setsockopt_string(zmq.IDENTITY, str(agent_id))
        # poller
        self.poller = zmq.Poller()
        # vrem sa ascultam daca motorul a strigat unde e mingea
        self.poller.register(self.sub_socket, zmq.POLLIN)
        # ii spunem poller-ului sa stea cu ochii si pe DEALER
        self.poller.register(self.dealer_socket, zmq.POLLIN)
        # conectarea la motor
        self.sub_socket.connect("tcp://localhost:5555")
        self.dealer_socket.connect("tcp://localhost:5556")

    def run(self):
        # Inregistrare agenti
        intention = {
            "agent_id" : self.agent_id,
            "team" : self.team,
            "action" : STATE_IDLE
        }
        self.dealer_socket.send_json(intention)
        print(f"Agentul {self.agent_id} s-a inregistrat")
        while True:
            # verificam daca motorul a trimis ceva
            events = dict(self.poller.poll(timeout=10))
            # daca motorul a trimis ceva
            if self.sub_socket in events:
                message = self.sub_socket.recv_json()
                # atribuim noile coordonate ale agentului
                # verificam daca agentul exista in mesaj (pentru prima iteratie, motorul nu stie de agenti)
                if str(self.agent_id) in message["players"]:
                    self.x = message["players"][str(self.agent_id)]["x"]
                    self.y = message["players"][str(self.agent_id)]["y"]
                    self.start_x = message["players"][str(self.agent_id)]["start_x"]
                    self.start_y = message["players"][str(self.agent_id)]["start_y"]
                
                    # Acceptam deciziile de stare ale Arbitrului (ex: STUN / Pedeapsa)
                    self.state = message["players"][str(self.agent_id)]["state"]
                    self.stun_frames = message["players"][str(self.agent_id)]["stun_frames"]
                

                # ---------------DEBUG CONSOLA-----------------
                # (MOMENTAN) print(f"Agentul {self.agent_id} (X: {self.x:.2f}, Y: {self.y:.2f}) vede mingea la Coordonatele {message['ball']['x']}, {message['ball']['y']}")
                # ---------------DEBUG CONSOLA-----------------
                

                

                # ==== COEFICIENTI PENTRU PASA =====
                closest_opponent_distance = 100
                # Raza de pericol a primitorului de lungimea pasei
                pressure_radius_coef = 0.5
                # Scorul pentru cea mai buna pasa
                best_pass_score = -999
                # Punct optim pentru pasa
                optimal_point_for_pass = 12
                # Coeficient de severitate
                severity_short_pass = 2.0
                severity_long_pass = 0.5
                # Pentru siguranta
                best_pass_target_id = None
                best_pass_target_distance = 0.0
                # ==================================
            
                for player_id, player_data in message["players"].items():
                
                    # verificam sa nu fie el insusi
                    if str(player_id) == str(self.agent_id):
                        continue
                    # daca e coechipier
                    if player_data["team"] == self.team:
                        # Scor initial pentru pasa
                        current_pass_score = 100
                        closest_opponent_to_receiver = 100

                        # bucla pentru a afla cel mai apropiat adversar de coechipierul caruia vrem sa ii pasam
                        for opponent_id, opponent_data in message["players"].items():
                            
                            if opponent_data["stun_frames"] > 0:
                                continue

                            if opponent_data["team"] != self.team:
                                distance_opponent_to_receiver =  math.sqrt((opponent_data["x"] - player_data["x"])**2 + (opponent_data["y"] - player_data["y"])**2)
                                if distance_opponent_to_receiver < closest_opponent_to_receiver:
                                    closest_opponent_to_receiver = distance_opponent_to_receiver
                                    closest_opponent_to_receiver_id = opponent_id

                        distance_agent_to_teammate = self.calculate_distance(player_data["x"], player_data["y"])
                        # cat de departe e coechipierul fata de "punctul optim de pasa"
                        deviation = abs(distance_agent_to_teammate - optimal_point_for_pass)
                        
                        # raza de presiune, cu cat e mai departe coechipierul, cu atat...
                        # ...poate fi adversarul la o distanta mai mare de el 
                        pressure_radius = distance_agent_to_teammate * pressure_radius_coef
                        
                        # daca adversarul e prea aproape de coechipier, nu pasam
                        if closest_opponent_to_receiver < pressure_radius:
                            current_pass_score -= 100 

                        # coechipierul e prea aproape => creste severitatea penalizarii
                        if distance_agent_to_teammate < optimal_point_for_pass:    
                            pass_penalty = (deviation ** 2) * severity_short_pass
                        # coechipierul e mai departe => creste mai lent severitatea
                        else:
                            pass_penalty = deviation * severity_long_pass
                        current_pass_score -= pass_penalty
                        
                        # coechipierul e in fata noastra, spre poarta adversa
                        if (float(self.start_x) < 50.0 and player_data["x"] > self.x) or (float(self.start_x) > 50.0 and player_data["x"] < self.x):
                            current_pass_score += 10
                        else:
                            # coechipierul e in spatele nostru
                            current_pass_score -= 5
                        
                        if current_pass_score > best_pass_score:
                            best_pass_target_id = player_id
                            best_pass_target_distance = distance_agent_to_teammate
                            best_pass_score = current_pass_score
                            
                    # daca e adversar 
                    else:
                        # daca adversarul e pe jos, mergem mai departe
                        if player_data["stun_frames"] > 0:
                            continue
                        distance_agent_to_opponent = self.calculate_distance(player_data["x"], player_data["y"])
                        if distance_agent_to_opponent < closest_opponent_distance:
                            closest_opponent_distance = distance_agent_to_opponent
                            closest_opponent_id = player_id

                # Verificam cine are posesia
                we_have_possession = False
                if message["possession"] is not None:
                    if message["players"][message["possession"]]["team"] == self.team:
                        we_have_possession = True
                        

                # ========================================================
                # INCEPE MECIUL (START_GAME) SAU S-A INSCRIS UN GOL (GOAL)
                # ========================================================
                if message["game_status"] in [STATUS_START_GAME, STATUS_GOAL]:
                    intention = self.player_in_position(target_x = self.start_x, target_y = self.start_y, position = "POS_STARTGAME")
                    if intention is not None:
                        self.dealer_socket.send_json(intention)
                
                # ===================================
                # MINGEA A IESIT IN OUT (OUT)
                # ===================================
                elif message["game_status"] == STATUS_OUT:

                    # 1. Atribuirea rolurilor (se executa o singura data)
                    # daca agentul NU este inca intr-o stare de aut, il punem sa aleaga
                    if self.state not in [STATE_DO_THROW_IN, STATE_WAIT_THROW_IN]: # NOU
                        if self.agent_id == message["last_touch"]:
                            self.state = STATE_WAIT_THROW_IN
                        else:
                            self.state = STATE_DO_THROW_IN
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)
                    
                    # 2. Executia (se verifica fiecare cadru cat timp e aut)
                    # E IN DO_THROW_IN SI AJUNGE LA MINGE
                    if self.state == STATE_DO_THROW_IN and self.calculate_distance(message["ball"]["x"],message["ball"]["y"]) < 1.0:
                        intention = self.prepare_kick(50.0, 50.0, power = 5.0)
                        self.dealer_socket.send_json(intention)
                        self.state = STATE_IDLE # am aruncat mingea!
                
                # ===================================
                # JOCUL ESTE IN DESFASURARE (PLAYING)
                # ===================================
                else:

                    # daca agentul e aproape de minge, trimite intentia de a o urmari
                    # mealy machine
                    distance_agent_to_ball = self.calculate_distance(message['ball']['x'],message['ball']['y'])
                    # unde avanseaza agentii
                    if float(self.start_x) < 50.0:
                        target_x = 100.0 # agentii din stanga ataca dreapta
                    else:
                        target_x = 0.0 # agentii din dreapta ataca stanga

                    # agentii alearga 80% pe linia lor dar 20% spre poarta
                    center_of_goal = 50.0
                    target_y = random.uniform((((0.8 * self.y) + (0.2 * center_of_goal)) - 4), (((0.8 * self.y) + (0.2 * center_of_goal)) + 4))
                    distance_agent_to_opponent_goal = self.calculate_distance(target_x, target_y)
                    
                    # GUARD CLAUSE pentru stun
                    if self.stun_frames > 0:
                        pass

                    # E IN (DO/WAIT)_THROW_IN SI AUT-UL A FOST EXECUTAT => TRECE IN IDLE 
                    elif self.state in [STATE_DO_THROW_IN, STATE_WAIT_THROW_IN]:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # TRANZITIA DUPA RESET
                    elif self.state == STATE_RESET:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)
                    
                    # TRANZITIA DUPA SUT
                    # E IN KICK, DUPA CE A SUTAT TRECE IN IDLE
                    elif self.state == STATE_KICK:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # TRANZITIA DUPA PASA
                    # DUPA CE A PASAT, TRECE IN IDLE
                    elif self.state == STATE_PASS:
                        self.state = STATE_ATTACK_SUPPORT 
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # TRANZITIA DUPA DRIBBLE DUEL
                    # in functie de duel_frames
                    elif self.state == STATE_DRIBBLE_DUEL:
                        if self.duel_frames == 0:
                            self.state = STATE_IDLE
                        else:
                            self.duel_frames -= 1
                        
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    
                    # TRANZITIA DUPA DRIBBLING
                    # E IN DRIBBLING, DUPA CE IMPINGE MINGEA MAI IN FATA, FUGE DUPA EA
                    elif self.state == STATE_DRIBBLE:
                        self.state = STATE_CHASE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # REACTIA DUPA PASA, CAND E IN ATAC
                    elif self.state == STATE_ATTACK_SUPPORT :

                        # abia am pasat, avansam spre poarta
                        if self.ignore_ball_frames > 0:
                            self.ignore_ball_frames -= 1
                            target_y = self.get_evasive_target(target_x, target_y, message)
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : target_x,
                                "target_y" : target_y
                            }

                        # mingea ajunge la adversari sau se apropie de agent => intram in IDLE
                        elif self.ignore_ball_frames == 0 and we_have_possession == False:
                            self.state = STATE_IDLE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }

                        # timer-ul a expirat si avem in continuare posesia
                        else:
                            target_y = self.get_evasive_target(target_x, target_y, message)
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : target_x,
                                "target_y" : target_y
                            }
                        
                        self.dealer_socket.send_json(intention)
                    
                    # SUSTINEREA APARARII
                    elif self.state == STATE_DEFEND_SUPPORT:
                        # adversarul se apropie cu mingea => il atacam
                        if distance_agent_to_ball < 20.0:
                            self.state = STATE_CHASE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }
                        
                        # un coleg a recuperat mingea
                        elif we_have_possession == True:
                            self.state = STATE_IDLE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }
                        
                        # mingea e tot la adversari si departe
                        else:
                            self.state = STATE_DEFEND_SUPPORT
                            target_x = 0.7 * self.start_x + 0.3 * message["ball"]["x"]
                            target_y = 0.7 * self.start_y + 0.3 * message["ball"]["y"]
                            target_y = self.get_evasive_target(target_x, target_y, message)
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : target_x,
                                "target_y" : target_y
                            }
                        
                        self.dealer_socket.send_json(intention)

                    # RENUNTAREA LA URMARIRE 1
                    # E IN CHASE SI RAMANE PREA DEPARTE => TRECE IN IDLE
                    elif self.state == STATE_CHASE and distance_agent_to_ball > 30:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # RENUNTAREA LA URMARIRE 2
                    # E IN CHASE DAR UN COECHIPIER AJUNGE LA MINGE => TRECE IN IDLE
                    elif self.state == STATE_CHASE and we_have_possession == True and message["possession"] != str(self.agent_id):
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # GANDIREA FARA MINGE
                    elif self.state == STATE_IDLE:
                        # echipa are posesia => sustine atacul
                        if we_have_possession == True:
                            self.state = STATE_ATTACK_SUPPORT
                            target_y = self.get_evasive_target(target_x, target_y, message)
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : target_x,
                                "target_y" : target_y
                            }
                        # echipa nu are posesia si e aproape de minge => intra in CHASE
                        elif we_have_possession == False and distance_agent_to_ball < 20.0:
                            self.state = STATE_CHASE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }
                        # nu are posesia si e departe de minge => sustine apararea
                        else:
                            self.state = STATE_DEFEND_SUPPORT
                            target_x = 0.7 * self.start_x + 0.3 * message["ball"]["x"]
                            target_y = 0.7 * self.start_y + 0.3 * message["ball"]["y"]
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : target_x,
                                "target_y" : target_y
                            }
                        # trimit intentia pe retea
                        self.dealer_socket.send_json(intention)

                    # E IN CHASE SI A AJUNS LA MINGE SI NU ARE NIMENI POSESIA => intra in CONTROL_BALL
                    elif self.state == STATE_CHASE and distance_agent_to_ball < 2.0 and message["possession"] is None:
                        self.state = STATE_CONTROL_BALL
                        intention = self.prepare_kick(target_x, target_y, power = 0.1, action_type = STATE_CONTROL_BALL)
                        self.dealer_socket.send_json(intention)

                    # A FURAT CINEVA MINGEA
                    elif self.state == STATE_CONTROL_BALL and message["possession"] not in [None, str(self.agent_id)]:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)
                
                    # AVEM POSESIA -> DECIDEM CE FACEM CU MINGEA
                    elif message["possession"] == str(self.agent_id):

                        # CALCULAM SCORUL PENTRU DRIBLING
                        base_dribble_score = 50.0
                        dribble_multiplier = 10.0
                        dribble_score = base_dribble_score + (closest_opponent_distance * dribble_multiplier)

                        # CALCULAM SCORUL PENTRU SUT
                        goal_x = 100.0 if float(self.start_x) < 50.0 else 0.0
                        goal_y = 50.0

                        dx_shot = goal_x - self.x
                        dy_shot = goal_y - self.y
                        distance_ball_to_goal = math.hypot(dx_shot, dy_shot)

                        # Scor de baza: 150 puncte minus distanta
                        penalty_for_distance = 3.0
                        kick_score = 150.0 - (distance_ball_to_goal * penalty_for_distance)

                        # normalizarea vectorului de sut
                        if distance_ball_to_goal > 0.01:
                            nx_shot = dx_shot / distance_ball_to_goal
                            ny_shot = dy_shot / distance_ball_to_goal
                        else:
                            nx_shot, ny_shot = 1.0, 0.0
                        
                        # Verificam culoarul de sut
                        for opponent_id, opponent_data in message["players"].items():
                            # ignoram portarul (fix de moment)
                            if opponent_data["start_x"] == 0 and opponent_data["start_y"] == 50:
                                continue
                            if opponent_data["team"] != self.team and opponent_data["stun_frames"] == 0:

                                # vectorul de la noi la adversar
                                dx_opp = opponent_data["x"] - self.x
                                dy_opp = opponent_data["y"] - self.y

                                # produsul scalar
                                # cat a inaintat mingea pana in dreptul adversarului
                                d_length = (dx_opp * nx_shot) + (dy_opp * ny_shot)

                                # verificam daca adversarul e in fata noastra si intre noi si poarta
                                if 0 < d_length < distance_ball_to_goal:

                                    # produs vectorial
                                    # distanta laterala fata de traiectorie
                                    d_perpendicular = abs((dx_opp * ny_shot) - (dy_opp * nx_shot))

                                    # latimea conului
                                    starting_distance_width = 2.0
                                    distance_width_coefficient = 0.5
                                    cone_width = starting_distance_width + (d_length * distance_width_coefficient)

                                    # daca e in interiorul conului, blocheaza culoarul
                                    if d_perpendicular < cone_width:
                                        penalty_for_blocking = 80
                                        kick_score -= penalty_for_blocking

                        # DECIZIA: SUT VS PASA VS DRIBLING
                        
                        # Sut
                        if (kick_score > best_pass_score and kick_score > dribble_score) or distance_agent_to_opponent_goal < 10.0:
                            self.state = STATE_KICK
                            goal_y = random.uniform(41.0, 58.9)
                            intention = self.prepare_kick(goal_x, goal_y, power = 3.0, action_type = STATE_KICK)

                        # Pasa
                        elif best_pass_score > dribble_score and best_pass_score > kick_score:
                            self.state = STATE_PASS
                            self.ignore_ball_frames = 20 
                            pass_power = min(max(best_pass_target_distance * 0.10, 1.5), 6.0) # viteza pasei
                            pass_target_x = message["players"][str(best_pass_target_id)]["x"] + random.uniform(-3.0, 3.0)
                            pass_target_y = message["players"][str(best_pass_target_id)]["y"] + random.uniform(-3.0, 3.0)
                            intention = self.prepare_kick(pass_target_x, pass_target_y, power = pass_power, action_type = STATE_PASS)
                                
                        # Am decis sa pastram mingea, acum vedem in ce stare o facem
                        # Dribble sau Dribble Duel
                        else:
                            # suntem sub presiune, intram in duel cu adversarul
                            if closest_opponent_distance < 5.0:
                                self.state = STATE_DRIBBLE_DUEL
                                self.duel_frames = 60
                                target_y = self.get_evasive_target(target_x, target_y, message)
                                intention = self.prepare_kick(target_x, target_y, power = 1.5, action_type = STATE_DRIBBLE)
                            # suntem liberi, inaintam cu mingea
                            else:
                                self.state = STATE_DRIBBLE
                                target_y = self.get_evasive_target(target_x, target_y, message)
                                intention = self.prepare_kick(target_x, target_y, power = 1.0, action_type = STATE_DRIBBLE)
                                    
                        # print(f"Sut: {kick_score}, Pasa: {best_pass_score}, Dribbling: {dribble_score}")
                        self.dealer_socket.send_json(intention)



            # printam state-ul agentului (DEBUGGING)
            self.print_state(self.state)

            # verificam daca motorul ne-a raspuns
            if self.dealer_socket in events:
                reply_bytes = self.dealer_socket.recv()
                reply = json.loads(reply_bytes.decode('utf-8'))
        



    # calculam distanta dintre agent si o tinta oarecare
    def calculate_distance(self, target_x, target_y):
        distance = math.sqrt((self.x-target_x)**2 + (self.y - target_y)**2)
        return distance

    # functie pentru lovirea mingii (sut, pasa, out, etc)
    def prepare_kick(self, target_x, target_y, power, action_type = STATE_KICK):

        # 1. Calculam diferentele si distanta
        dx = target_x - self.x
        dy = target_y - self.y
        distance_to_target = math.hypot(dx, dy)

        # 2. Normalizam si aplicam forta
        if distance_to_target > 0:
            kick_vx = (dx/distance_to_target) * power
            kick_vy = (dy/distance_to_target) * power
        else:
            kick_vx = 0
            kick_vy = 0

        intention = {
            "agent_id" : self.agent_id,
            "action" : action_type,
            "kick_vx" : kick_vx,
            "kick_vy" : kick_vy
        }
        return intention

    def player_in_position(self, target_x, target_y, position):
        if self.calculate_distance(target_x, target_y) < 2.0:
            if self.state != STATE_IDLE:
                self.state = STATE_IDLE
                intention = {
                    "agent_id" : self.agent_id,
                    "action" : self.state
                }
                return intention
        else: 
            if self.state != STATE_RESET:
                self.state = STATE_RESET
                intention = {
                    "agent_id" : self.agent_id,
                    "action" : self.state
                }
                return intention

        # nu s-a schimbat nimic
        return None
            
    def print_state(self, curr_state):
        if curr_state != self.last_logged_state:
            print(f"Agent {self.agent_id} -> {curr_state}")
            self.last_logged_state = curr_state
        
    # EVITAREA OBSTACOLELOR
    def get_evasive_target(self, target_x, target_y, message):
        # cat de departe se uita in fata
        radar_scan_distance = 3.0
        # cat de lata e banda noastra de alergare
        avoidance_lane_width = 1.5 
        # cat ocolim oponentul
        avoid_opponent = 3.0

        for player_id, player_data in message["players"].items():
            # ne evitam pe noi insine
            if str(player_id) == str(self.agent_id):
                continue

            # daca el are mingea, nu il ocolim (pentru a permite deposedarile)
            if str(player_id) == str(message.get("possession")):
                continue

            distance_agent_to_obstacle = self.calculate_distance(player_data["x"], player_data["y"])

            # e prea aproape? (< 3.0m)
            if distance_agent_to_obstacle < radar_scan_distance:
                # e in fata mea?
                is_in_front = False
                # alergam spre dreapta
                if target_x > self.x and player_data["x"] > self.x:
                    is_in_front = True
                # alergam spre stanga
                elif target_x < self.x and player_data["x"] < self.x:
                    is_in_front = True
                                        
                if is_in_front:
                    # ne blocheaza banda de alergare?
                    if abs(player_data["y"] - self.y) < avoidance_lane_width:
                        # ocolim adversarul
                        if player_data["y"] > self.y:
                            target_y = max(self.y - avoid_opponent, 0.1)
                        else:
                            target_y = min(self.y + avoid_opponent, 99.9)
                        # am gasit si ocolit obstacolul, iesim din bucla
                        break
        return target_y
        