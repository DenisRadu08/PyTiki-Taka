from config import STATE_KICK
from config import STATE_CHASE
from config import STATE_IDLE
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
        self.deadlock_frames = 0
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
                
                # verificam cine incepe de la mijloc
                is_opponent_kickoff = (str(self.team) != str(message.get("kickoff_team")) and message["ball"]["x"] == 50.0 and message["ball"]["y"] == 50.0)

                # Verificam cine are posesia
                team_in_possession = None
                possessor_state = None
                is_gk_protected = False

                # cineva are mingea la picior acum?
                if message["possession"] is not None:
                    possessor_id = str(message["possession"])
                    team_in_possession = message["players"][possessor_id]["team"]
                    possessor_state = message["players"][possessor_id]["state"]
                    # verificam daca mingea e prinsa de portar
                    is_gk_protected = (possessor_state in [STATE_GK_HOLD_BALL, STATE_GK_CLEAR_BALL])
                
                # mingea este in aer/libera, cine a atins-o ultimul?
                elif message.get("last_touch") is not None:
                    last_touch_id = str(message["last_touch"])

                    # ne asiguram ca jucatorul inca exista in mintea serverului
                    if last_touch_id in message["players"]:
                        team_in_possession = message["players"][last_touch_id]["team"]

                # verdict: este echipa noastra in atac?
                we_have_possession = (team_in_possession == self.team)

                        
                # Calculam cel mai apropiat jucator activ
                distance_agent_to_ball = self.calculate_distance(message["ball"]["x"], message["ball"]["y"])
                am_i_closest_to_ball = True

                # verific sa nu fiu pe jos
                if self.stun_frames > 0:
                    am_i_closest_to_ball = False
                else:
                    for player_id, player_data in message["players"].items():
                        if player_data["team"] == self.team and str(player_id) != str(self.agent_id) and player_data["stun_frames"] == 0:
                            dist = math.hypot(player_data["x"] - message["ball"]["x"], player_data["y"] - message["ball"]["y"])
                            # daca un coleg valabil e mai aproape decat mine
                            if dist < distance_agent_to_ball:
                                am_i_closest_to_ball = False
                                break

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
                    if self.state not in [STATE_DO_THROW_IN, STATE_WAIT_THROW_IN]: 

                        # aflam echipa care a atins ultima mingea
                        last_touch_id = str(message["last_touch"])
                        last_touch_team = message["players"][last_touch_id]["team"]

                        # executam autul doar daca echipa noastra a primit aut...
                        # ...si suntem cel mai aproape de minge
                        if self.team != last_touch_team and am_i_closest_to_ball == True:
                            self.state = STATE_DO_THROW_IN
                        else:
                            # toti ceilalti asteapta sa se bata aut
                            self.state = STATE_WAIT_THROW_IN

                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)
                    
                    # 2. Executia (se verifica fiecare cadru cat timp e aut)
                    # E IN DO_THROW_IN SI AJUNGE LA MINGE
                    if self.state == STATE_DO_THROW_IN and self.calculate_distance(message["ball"]["x"],message["ball"]["y"]) < 1.0:
                        
                        # cautam cel mai apropiat coechipier pentru o repunere sigura
                        best_target_x, best_target_y = 50.0, 50.0
                        min_dist = 999.0

                        for player_id, player_data in message["players"].items():
                            # trebuie sa fie in echipa mea, sa nu fiu eu, si sa nu fie pe jos
                            if player_data["team"] == self.team and str(player_id) != str(self.agent_id) and player_data["stun_frames"] == 0:
                                dist = math.hypot(player_data["x"] - self.x, player_data["y"] - self.y)
                                if dist < min_dist:
                                    min_dist = dist
                                    best_target_x = player_data["x"]
                                    best_target_y = player_data["y"]
                        
                        # aruncam mingea
                        intention = self.prepare_kick(best_target_x, best_target_y, power = 2.0)
                        self.dealer_socket.send_json(intention)
                        self.state = STATE_IDLE # am aruncat mingea!
                
                # ===================================
                # JOCUL ESTE IN DESFASURARE (PLAYING)
                # ===================================
                else:

                    # ===============================
                    # -------- MEALY MACHINE --------
                    # ===============================
                    
                    distance_agent_to_ball = self.calculate_distance(message['ball']['x'],message['ball']['y'])
                    
                    # --- Senzor de deadlock ---
                    # numaram cati jucatori (aliati sau inamici) sunt lipiti de minge
                    players_near_ball = 0
                    for player_id, player_data in message["players"].items():
                        if player_data["stun_frames"] == 0:
                            dist_agent_to_ball = math.hypot(player_data["x"] - message["ball"]["x"], player_data["y"] - message["ball"]["y"])
                            if dist_agent_to_ball < 2.5: # raza gramezii
                                players_near_ball += 1

                    # daca sunt in gramada (eu si inca cineva) si stam asa
                    if distance_agent_to_ball < 2.5 and players_near_ball >= 2:
                        self.deadlock_frames += 1
                    else:
                        self.deadlock_frames = 0
                    

                    # --- SCORUL PENTRU PRESSING ---
                    # aflam X-ul portii pe care o aparam
                    own_goal_x = 0.0 if float(self.start_x) < 50.0 else 100.0
                    distance_ball_to_own_goal = abs(message["ball"]["x"] - own_goal_x)

                    # distanta ideala este cu 5 metri mai aproape de poarta,
                    # dar niciodata mai putin de 0 metri
                    ideal_distance = max(0.0, distance_ball_to_own_goal - 5.0)

                    # punctul ideal X: la 5 metri in fata adversarului
                    ideal_x = abs(ideal_distance - own_goal_x)
                    ideal_y = message["ball"]["y"]
                    if self.stun_frames > 0:
                        my_pressing_score = -999.0 # daca suntem pe jos
                    else:
                        # punctaj in functie de pozitia fata de punctul ideal
                        my_pressing_score = 100.0 - math.hypot(self.x - ideal_x, self.y - ideal_y)

                    # comparam cu scorurile coechipierilor
                    is_primary_chaser = True
                    for player_id, player_data in message["players"].items():
                        if player_data["team"] == self.team and str(player_id) != str(self.agent_id):
                            if player_data["stun_frames"] > 0:
                                continue

                            teammate_pressing_score = 100.0 - math.hypot(player_data["x"] - ideal_x, player_data["y"] - ideal_y)

                            # daca un coechipier are scor mai bun, nu fac eu pressing
                            if teammate_pressing_score > my_pressing_score:
                                is_primary_chaser = False
                                break
                    
                    # daca avem stun, nu facem pressing
                    if self.stun_frames > 0:
                        is_primary_chaser = False

                    # unde avanseaza agentii
                    if float(self.start_x) < 50.0:
                        target_x = 100.0 # agentii din stanga ataca dreapta
                    else:
                        target_x = 0.0 # agentii din dreapta ataca stanga

                    # agentii alearga 80% pe linia lor dar 20% spre poarta
                    center_of_goal = 50.0
                    target_y = random.uniform((((0.8 * self.y) + (0.2 * center_of_goal)) - 2), (((0.8 * self.y) + (0.2 * center_of_goal)) + 2))
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

                    # SUSTINERE ATAC (JOCUL FARA MINGE)
                    elif self.state == STATE_ATTACK_SUPPORT :

                        # --- BANDA ELASTICA ---
                        # jucatorii avanseaza in functie de pozitia mingii
                        # 1. calculam offset-ul mingii fata de centrul terenului
                        ball_shift_x = message["ball"]["x"] - 50.0

                        # 2. coeficientul de urcare
                        # 0.6 inseamna ca urca 80% din minge
                        slide_coefficient = 0.8

                        # impuls ofensiv
                        # jucatorii avanseaza mai mult cand sunt in atac,
                        # nu stau ancorati de pozitia de start_x
                        offensive_push = 25.0 if float(self.start_x) < 50.0 else -25.0

                        # 3. noul target X este baza jucatorului + offset-ul dinamic
                        dynamic_target_x = self.start_x + (ball_shift_x * slide_coefficient) + offensive_push

                        # 4. limitare ca sa nu iasa de pe teren sau sa nu intre in poarta
                        target_x = max(5.0, min(95.0, dynamic_target_x))

                        # 5. pe axa Y, pastam postul dar ne strangem 20% spre minge
                        # (suport pentru pasa)
                        target_y = (0.8 * self.start_y) + (0.2 * message["ball"]["y"])

                        # ----------------
                        # Demarcare activa
                        # ----------------
                        danger_radius = 5.0 # cat de departe simtim pericolul
                        for opoonent_id, opponent_data in message["players"].items():
                            if opponent_data["team"] != self.team and opponent_data["stun_frames"] == 0:

                                distance_agent_to_opponent = self.calculate_distance(opponent_data["x"], opponent_data["y"])

                                # daca intram in raza de pericol, ne demarcam
                                if distance_agent_to_opponent < danger_radius:

                                    # calculam directia de fuga
                                    dx_run = target_x - opponent_data["x"]
                                    dy_run = target_y - opponent_data["y"]
                                    distance_to_run = math.hypot(dx_run, dy_run)

                                    # normalizam vectorul
                                    if distance_to_run > 0.01:
                                        nx_run = dx_run / distance_to_run
                                        ny_run = dy_run / distance_to_run
                                    else:
                                        nx_run, ny_run = 1.0, 0.0
                                    
                                    # calculam intensitatea demarcarii
                                    push_strength = (danger_radius - distance_agent_to_opponent) * 1.5

                                    # aplicam deviatia
                                    target_x += nx_run * push_strength
                                    target_y += ny_run * push_strength

                        target_x = max(2.0, min(98.0, target_x))
                        target_y = max(2.0, min(98.0, target_y))
                          
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

                        # daca mingea e libera in aer si sunt cel mai aproape,
                        # merg sa o iau
                        elif message["possession"] is None and am_i_closest_to_ball == True and not is_opponent_kickoff:
                            self.state = STATE_CHASE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }

                        # mingea ajunge la adversari sau se apropie de agent => intram in IDLE
                        elif self.ignore_ball_frames == 0 and we_have_possession == False:
                            self.state = STATE_IDLE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }
                        
                        # mingea se apropie de noi => intram in CHASE
                        elif distance_agent_to_ball < 10.0 and message["possession"] != str(self.agent_id) and not (we_have_possession == True and message["possession"] is not None) and is_primary_chaser and not is_gk_protected and not is_opponent_kickoff:
                            self.state = STATE_CHASE
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

                        # daca mingea e libera, o recuperez
                        if message["possession"] is None and am_i_closest_to_ball == True and not is_opponent_kickoff:
                            self.state = STATE_CHASE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }

                        # adversarul are mingea la picior si eu sunt principalu aparator
                        elif message["possession"] is not None and not we_have_possession and is_primary_chaser == True and not is_gk_protected and not is_opponent_kickoff:
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
                    elif self.state == STATE_CHASE and we_have_possession == True and message["possession"] != str(self.agent_id) and message["possession"] is not None:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # RENUNTAREA LA URMARIRE 3
                    # E IN CHASE DAR PORTARUL PRINDE MINGEA => TRECE IN IDLE
                    elif self.state == STATE_CHASE and is_gk_protected:
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
                        elif we_have_possession == False and distance_agent_to_ball < 35.0 and is_primary_chaser == True and not is_gk_protected and not is_opponent_kickoff:
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

                    # rezolvarea blocajului
                    # daca a stat blocat 1.5 secunde (45 cadre)
                    elif self.deadlock_frames > 45:
                        self.deadlock_frames = 0
                        # resetam starea pentru a regandi tactica
                        self.state = STATE_IDLE

                        # alege o directie aleatorie scurta (degajare din gramada)
                        poke_x = message["ball"]["x"] + random.uniform(-15.0, 15.0)
                        poke_y = message["ball"]["y"] + random.uniform(-15.0, 15.0)

                        # fortam o pasa slaba/ciupire, ignorand limita fizica de 2.0
                        intention = self.prepare_kick(poke_x, poke_y, power = 1.5, action_type = STATE_KICK)
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

                        # =====================================
                        # CALCULAM CEA MAI BUNA OPTIUNE DE PASA
                        # ------- SI SCORUL PENTRU PASA -------
                        # =====================================
                         
                        # ==== COEFICIENTI PENTRU PASA =====
                        closest_opponent_distance = 100
                        # Raza de pericol a primitorului de lungimea pasei
                        pressure_radius_coef = 0.15
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
                        best_pass_target_x = 0.0
                        best_pass_target_y = 0.0
                        # ==================================
            
                        for player_id, player_data in message["players"].items():
                
                            # verificam sa nu fie el insusi
                            if str(player_id) == str(self.agent_id):
                                continue
                            # daca e coechipier
                            if player_data["team"] == self.team:

                                # nu pasam cu portarul
                                if float(player_data["start_x"]) in [2.0, 98.0]:
                                    continue

                                # proiectia in viitor
                                # aflam directia atacului
                                attack_direction = 1.0 if float(self.start_x) < 50.0 else -1.0
                                
                                # este o pasa ofensiva?
                                is_forward_pass = (attack_direction == 1.0 and player_data["x"] > self.x) or (attack_direction == -1.0 and player_data["x"] < self.x)

                                # daca e in fata, tintim la 4 metri inaintea lui, altfel, la picior
                                lead_distance = 0.1 if is_forward_pass else 0.0

                                # punctul tinta real in care vrem sa trimitem mingea
                                target_pass_x = player_data["x"] + (lead_distance * attack_direction)
                                target_pass_y = player_data["y"]

                                # limitare ca sa nu dam pase afara din teren
                                target_pass_x = max(2.0, min(98.0, target_pass_x))
                                
                                # Scor initial pentru pasa
                                current_pass_score = 110
                                closest_opponent_to_receiver = 100

                                # Verificam culoarul de pasa
                                dx_pass = target_pass_x - self.x
                                dy_pass = target_pass_y - self.y

                                distance_agent_to_pass_point = math.hypot(dx_pass, dy_pass)

                                if distance_agent_to_pass_point > 0.01:
                                    nx_pass = dx_pass / distance_agent_to_pass_point
                                    ny_pass = dy_pass / distance_agent_to_pass_point
                                else:
                                    nx_pass, ny_pass = 1.0,  0.0
                                
                                
                                # bucla pentru a afla cel mai apropiat adversar de coechipierul caruia vrem sa ii pasam
                                for opponent_id, opponent_data in message["players"].items():
                                    
                                    if opponent_data["stun_frames"] > 0:
                                        continue

                                    if opponent_data["team"] != self.team:
                                        # ne intereseaza adversarii apropiati de locul unde va ajunge mingea
                                        distance_opponent_to_target =  math.hypot(opponent_data["x"] - target_pass_x, opponent_data["y"] - target_pass_y)
                                        if distance_opponent_to_target < closest_opponent_to_receiver:
                                            closest_opponent_to_receiver = distance_opponent_to_target
                                            closest_opponent_to_receiver_id = opponent_id
                                    
                                    # vectorul de la noi la adversar
                                    dx_pass_opp = opponent_data["x"] - self.x
                                    dy_pass_opp = opponent_data["y"] - self.y

                                    # produsul scalar
                                    # cat a inaintat mingea pana in dreptul adversarului
                                    d_pass_length = (dx_pass_opp * nx_pass) + (dy_pass_opp * ny_pass)

                                    # verificam daca adversarul e in fata noastra si intre noi si coechipier
                                    if 0 < d_pass_length < distance_agent_to_pass_point:

                                        # produs vectorial
                                        # distanta laterala fata de traiectorie
                                        d_pass_perpendicular = abs((dx_pass_opp * ny_pass) - (dy_pass_opp * nx_pass))

                                        # latimea conului
                                        starting_distance_width = 0.5
                                        distance_width_coefficient = 0.08
                                        cone_width = starting_distance_width + (d_pass_length * distance_width_coefficient)

                                        # daca e in interiorul conului, blocheaza culoarul
                                        if d_pass_perpendicular < cone_width:
                                            penalty_for_blocking = 50
                                            current_pass_score -= penalty_for_blocking


                                # cat de departe e coechipierul fata de "punctul optim de pasa"
                                deviation = abs(distance_agent_to_pass_point - optimal_point_for_pass)
                                
                                # raza de presiune, cu cat e mai departe coechipierul, cu atat...
                                # ...poate fi adversarul la o distanta mai mare de el 
                                pressure_radius = min(3.5, distance_agent_to_pass_point * pressure_radius_coef)
                        
                                # daca adversarul e prea aproape de coechipier, nu pasam
                                if closest_opponent_to_receiver < pressure_radius:
                                    current_pass_score -= 100 

                                # coechipierul e prea aproape => creste severitatea penalizarii
                                if distance_agent_to_pass_point < optimal_point_for_pass:    
                                    pass_penalty = (deviation ** 2) * severity_short_pass
                                # coechipierul e mai departe => creste mai lent severitatea
                                else:
                                    pass_penalty = deviation * severity_long_pass
                                current_pass_score -= pass_penalty
                        
                                # coechipierul e in fata noastra, spre poarta adversa
                                if is_forward_pass:
                                    # daca e in ultima treime, scorul creste mai mult
                                    if (attack_direction == 1.0 and target_pass_x > 70.0) or (attack_direction == -1.0 and target_pass_x < 30.0):
                                        current_pass_score += 65
                                    else:
                                        current_pass_score += 30
                                else:
                                    # coechipierul e in spatele nostru
                                    current_pass_score -= 10
                                
                                if current_pass_score > best_pass_score:
                                    best_pass_target_id = player_id
                                    best_pass_target_distance = distance_agent_to_pass_point
                                    best_pass_target_x = target_pass_x
                                    best_pass_target_y = target_pass_y
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

                        # ===============================
                        # CALCULAM SCORUL PENTRU DRIBLING
                        # ===============================
                        base_dribble_score = 60.0
                        dribble_multiplier = 6.0

                        # CAP la +80 puncte => dribling maxim = 150
                        # daca are sub 10m liberi: Dribling (130) vs Pasa (140) => paseaza
                        # daca are peste 13m liberi: Dribling (150) vs Pasa Ofensiva (140) => sprinteaza cu mingea
                        dribble_score = base_dribble_score + min(80.0, closest_opponent_distance * dribble_multiplier)

                        # ==========================
                        # CALCULAM SCORUL PENTRU SUT
                        # ==========================
                        goal_x = 100.0 if float(self.start_x) < 50.0 else 0.0
                        goal_y = random.uniform(41.0, 58.9)

                        dx_shot = goal_x - self.x
                        dy_shot = goal_y - self.y
                        distance_ball_to_goal = math.hypot(dx_shot, dy_shot)

                        # Scor de baza: 150 puncte minus distanta
                        penalty_for_distance = 5.5
                        kick_score = 270.0 - (distance_ball_to_goal * penalty_for_distance)

                        # normalizarea vectorului de sut
                        if distance_ball_to_goal > 0.01:
                            nx_shot = dx_shot / distance_ball_to_goal
                            ny_shot = dy_shot / distance_ball_to_goal
                        else:
                            nx_shot, ny_shot = 1.0, 0.0
                        
                        # Verificam culoarul de sut
                        for opponent_id, opponent_data in message["players"].items():
                            # ignoram portarul
                            if opponent_data["start_x"] in [0, 100]:
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
                            intention = self.prepare_kick(goal_x, goal_y, power = 3.0, action_type = STATE_KICK)

                        # Pasa
                        elif best_pass_score > dribble_score and best_pass_score > kick_score:
                            self.state = STATE_PASS
                            self.ignore_ball_frames = 20 
                            pass_power = min(max(best_pass_target_distance * 0.15, 1.8), 3.5) # viteza pasei
                            
                            # Adaugam foarte putina randomizare fina doar pentru aspectul organic
                            final_target_x = best_pass_target_x # + random.uniform(-0.2, 0.2)
                            final_target_y = best_pass_target_y # + random.uniform(-0.2, 0.2)
                            intention = self.prepare_kick(final_target_x, final_target_y, power = pass_power, action_type = STATE_PASS)
                                
                        # Am decis sa pastram mingea, acum vedem in ce stare o facem
                        # Dribble sau Dribble Duel
                        else:
                            # suntem sub presiune, intram in duel cu adversarul
                            if closest_opponent_distance < 5.0:
                                self.state = STATE_DRIBBLE_DUEL
                                self.duel_frames = 60
                                target_y = self.get_evasive_target(target_x, target_y, message)
                                intention = self.prepare_kick(target_x, target_y, power = 0.8, action_type = STATE_DRIBBLE)
                            # suntem liberi, inaintam cu mingea
                            else:
                                self.state = STATE_DRIBBLE
                                target_y = self.get_evasive_target(target_x, target_y, message)
                                intention = self.prepare_kick(target_x, target_y, power = 0.9, action_type = STATE_DRIBBLE)
                                    
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

            # nu ne ferim de colegii nostri, doar de adversari (Bug FIX)
            if player_data["team"] == self.team:
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
        