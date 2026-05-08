import zmq
import json
import math
import random
from config import *

class PlayerAgent:
    def __init__(self, agent_id, team_id):
        self.x = 0.0
        self.y = 0.0
        self.start_x = self.x
        self.start_y = self.y
        self.state = STATE_IDLE
        self.agent_id=agent_id
        self.team_id = team_id
        self.last_logged_state = None
        self.stun_frames = 0
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

                    # daca agentul e aproape de minge, trimite intentia de a o urmari
                    # mealy machine
                    distance_agent_to_ball = self.calculate_distance(message['ball']['x'],message['ball']['y'])
                    # unde dam mingea
                    if float(self.start_x) < 50.0:
                        target_x = 100.0 # agentii din stanga ataca dreapta
                    else:
                        target_x = 0.0 # agentii din dreapta ataca stanga
                    target_y = random.uniform(41.0,59.0) # pe poarta
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
                    
                    # TRANZITIA DUPA DRIBBLING
                    # E IN DRIBBLING, DUPA CE IMPINGE MINGEA MAI IN FATA, FUGE DUPA EA
                    elif self.state == STATE_DRIBBLE:
                        self.state = STATE_CHASE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # RENUNTAREA LA URMARIRE
                    # E IN CHASE SI RAMANE PREA DEPARTE => TRECE IN IDLE
                    elif self.state == STATE_CHASE and distance_agent_to_ball>30:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : STATE_IDLE
                        }
                        self.dealer_socket.send_json(intention)

                    # DECLANSAREA URMARIRII
                    # E IN IDLE SI E APROAPE DE MINGE=> TRECE IN CHASE
                    elif self.state == STATE_IDLE and distance_agent_to_ball < 20:
                        self.state = STATE_CHASE
                        # creez intentia
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : STATE_CHASE
                        }
                        # trimit intentia pe retea
                        self.dealer_socket.send_json(intention)

                    # EXECUTIA SUTULUI
                    # E IN CHASE SI FOARTE APROAPE DE MINGE SI APROAPE DE POARTA SI ARE POSESIA => TRECE IN KICK (cu power mare)
                    elif self.state == STATE_CHASE and distance_agent_to_ball < 2 and distance_agent_to_opponent_goal <= 20.0 and message["possession"] in [None, str(self.agent_id)]:
                        self.state = STATE_KICK
                        intention = self.prepare_kick(target_x, target_y, power = 1.5)
                        self.dealer_socket.send_json(intention)
                    
                    # DRIBBLING
                    # E IN CHASE SI FOARTE APROAPE DE MINGE, DAR DEPARTE DE POARTA SI ARE POSESIA MINGII => TRECE IN DRIBBLE (cu power mic)
                    elif self.state == STATE_CHASE and distance_agent_to_ball < 2 and distance_agent_to_opponent_goal > 20.0 and message["possession"] in [None, str(self.agent_id)]:
                        self.state = STATE_DRIBBLE
                        intention = self.prepare_kick(target_x, target_y, power = 1.0, action_type = STATE_DRIBBLE)
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
        
