import zmq
import json
import math
from config import *
from agent import PlayerAgent
import time
import random

class GoalkeeperAgent(PlayerAgent):
    def __init__(self, agent_id, team_id):
        super().__init__(agent_id, team_id)
        self.last_target_y = 0.0
        self.catch_time = 0.0


    def run(self):
        # Inregistrare agenti
        intention = {
            "agent_id" : self.agent_id,
            "team_id" : self.team_id,
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
                    self.stun_frames = message["players"][str(self.agent_id)]["stun_frames"] # NOU

                # ---------------DEBUG CONSOLA-----------------
                # (MOMENTAN) print(f"Agentul {self.agent_id} (X: {self.x:.2f}, Y: {self.y:.2f}) vede mingea la Coordonatele {message['ball']['x']}, {message['ball']['y']}")
                # ---------------DEBUG CONSOLA-----------------


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

                    #==============================
                    #--------MEALY MACHINE---------
                    #==============================

                    # Logica pentru pozitionarea portarului
                    # identificam centrul portii noastre
                    if float(self.start_x) < 50.0:
                        goal_center_x, goal_center_y = 0.0, 50.0
                    else:
                        goal_center_x, goal_center_y = 100.0, 50.0
                    
                    # vectorul de la poarta catre minge
                    dx = message["ball"]["x"] - goal_center_x
                    dy = message["ball"]["y"] - goal_center_y

                    distance_goal_to_ball = math.hypot(dx, dy)

                    # daca distanta e mai mare decat raza noastra de 6 metri,
                    # portarul trebuie sa stea pe arc
                    if distance_goal_to_ball > 6.0:
                        target_x = goal_center_x + (dx / distance_goal_to_ball) * 6.0
                        target_y = goal_center_y + (dy / distance_goal_to_ball) * 6.0
                    else:
                        # mingea e foarte aproape
                        target_x = message["ball"]["x"]
                        target_y = message["ball"]["y"]

                    distance_agent_to_ball = self.calculate_distance(message['ball']['x'],message['ball']['y'])
                    
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

                    # TRANZITIA DUPA RESET / GK_CLEAR_BALL
                    elif self.state in [STATE_RESET, STATE_GK_CLEAR_BALL]:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # Portarul asteapta sa degajeze
                    elif self.state == STATE_GK_HOLD_BALL:

                        if time.time() - self.catch_time > 3.0:
                            self.state = STATE_GK_CLEAR_BALL

                            target_x_kick = 100.0 if self.start_x < 50 else 0.0
                            target_y_kick = random.uniform(20.0, 80.0)

                            intention = self.prepare_kick(target_x_kick, target_y_kick, power = 5.0, action_type = STATE_GK_CLEAR_BALL)
                            self.dealer_socket.send_json(intention)

                    # Portarul prinde mingea
                    elif str(message["possession"]) == str(self.agent_id) and distance_agent_to_ball < 2.0:
                        
                        # daca abia a prins mingea (nu e deja in asteptare)
                        if self.state != STATE_GK_HOLD_BALL:
                            self.state = STATE_GK_HOLD_BALL
                            self.catch_time = time.time() # pornim cronometrul
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }
                            self.dealer_socket.send_json(intention)
                        

                    # COMPORTAMENTUL DE BAZA: APARAREA
                    elif self.state in [STATE_IDLE, STATE_GK_DEFEND_GOAL]:
                        
                        # trimitem pe retea DOAR daca starea s-a schimbat,
                        # SAU daca mingea s-a miscat mai mult de 1.0 unitati
                        if self.state != STATE_GK_DEFEND_GOAL or abs(target_y - self.last_target_y) > 1.0:
                            self.state = STATE_GK_DEFEND_GOAL
                            self.last_target_y = target_y
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : target_x,
                                "target_y" : target_y
                            }
                            self.dealer_socket.send_json(intention)
                              

            # printam state-ul agentului (DEBUGGING)
            self.print_state(self.state)

            # verificam daca motorul ne-a raspuns
            if self.dealer_socket in events:
                reply_bytes = self.dealer_socket.recv()
                reply = json.loads(reply_bytes.decode('utf-8'))