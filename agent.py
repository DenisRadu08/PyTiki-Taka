from config import STATE_IDLE
import zmq
import json
import math
from config import *

class PlayerAgent:
    def __init__(self, agent_id):
        self.x = agent_id * 10
        self.y = 50
        self.start_x = self.x
        self.start_y = self.y
        self.state = STATE_IDLE
        self.agent_id=agent_id
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

                
                # ---------------DEBUG CONSOLA-----------------
                # (MOMENTAN) print(f"Agentul {self.agent_id} (X: {self.x:.2f}, Y: {self.y:.2f}) vede mingea la Coordonatele {message['ball']['x']}, {message['ball']['y']}")
                # ---------------DEBUG CONSOLA-----------------

                # Verificam daca e gol si resetam pozitiile sau se joaca
                if message["game_status"] == STATUS_GOAL:
                    self.state = STATE_RESET
                    intention = {
                        "agent_id" : self.agent_id,
                        "action" : STATE_RESET
                    }
                    self.dealer_socket.send_json(intention)
                    print (f"S-a inscris golul! Agentul {self.agent_id} isi reseteaza pozitia")
                elif message["game_status"] == STATUS_OUT:
                    if self.agent_id == message["last_touch"]:
                        self.state = STATE_WAIT_THROW_IN
                    else:
                        self.state = STATE_DO_THROW_IN
                    intention = {
                        "agent_id" : self.agent_id,
                        "action" : self.state
                    }
                    self.dealer_socket.send_json(intention)
                    print (f"Out de margine! Agentul {self.agent_id} intra in starea {self.state}")
                else:

                    # daca agentul e aproape de minge, trimite intentia de a o urmari
                    # mealy machine
                    distance_from_ball = self.calculate_distance(message['ball']['x'],message['ball']['y'])
                    
                    # E IN IDLE SI E APROAPE DE MINGE=> TRECE IN CHASE
                    if self.state == STATE_IDLE and distance_from_ball < 20:
                        self.state = STATE_CHASE
                        # creez intentia
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : STATE_CHASE
                        }
                        # trimit intentia pe retea
                        self.dealer_socket.send_json(intention)
                        print(f"Agentul {self.agent_id} a intrat in starea {STATE_CHASE}")

                    # E IN CHASE SI FOARTE APROAPE DE MINGE => TRECE IN KICK
                    elif self.state == STATE_CHASE and distance_from_ball < 2:
                        self.state = STATE_KICK

                        # 1. Unde dam mingea?
                        if str(self.agent_id) == "1":
                            target_x = 100.0 # agentul 1 ataca dreapta
                        else:
                            target_x = 0.0 # agentul 2 ataca stanga
                        target_y = 50.0 # centrul portii pe verticala

                        # 2. Calculam diferentele si distanta
                        dx = target_x - self.x
                        dy = target_y - self.y
                        distance_to_target = math.hypot(dx, dy)

                        # 3. Normalizam si aplicam forta
                        power = 20.0
                        if distance_to_target > 0:
                            kick_vx = (dx/distance_to_target) * power
                            kick_vy = (dy/distance_to_target) * power
                        else:
                            kick_vx = 0
                            kick_vy = 0

                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : STATE_KICK,
                            "kick_vx" : kick_vx,
                            "kick_vy" : kick_vy
                        }
                        self.dealer_socket.send_json(intention)
                        print(f"Agentul {self.agent_id} a intrat in starea {STATE_KICK}")
                    
                    # E IN KICK, DUPA CE A SUTAT TRECE IN IDLE
                    elif self.state == STATE_KICK:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : STATE_IDLE
                        }
                        self.dealer_socket.send_json(intention)
                        print(f"Agentul {self.agent_id} a sutat si apoi a intrat in starea {STATE_IDLE}")
                    
                    # E IN CHASE SI RAMANE PREA DEPARTE => TRECE IN IDLE
                    elif self.state == STATE_CHASE and distance_from_ball>30:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : STATE_IDLE
                        }
                        self.dealer_socket.send_json(intention)
                        print(f"Agentul {self.agent_id} a intrat in starea {STATE_IDLE}")

                    # E IN RESET SI CAND AJUNGE PE POZITIA INITIALA => TRECE IN IDLE
                    elif self.state == STATE_RESET and self.calculate_distance(self.start_x, self.start_y) < 2.0:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : STATE_IDLE
                        }
                        self.dealer_socket.send_json(intention)
                        print(f"Agentul {self.agent_id} a ajuns pe pozitia initiala si intra in starea {STATE_IDLE}")
                    
                    #
                    #elif self.state == STATE_DO_THROW_IN and self.calculate_distance(message["ball"]["x"],message["ball"]["y"]) < 1.0:


            # verificam daca motorul ne-a raspuns
            if self.dealer_socket in events:
                reply_bytes = self.dealer_socket.recv()
                reply = json.loads(reply_bytes.decode('utf-8'))
                print(f"Agentul {self.agent_id} a primit raspunsul: {reply['status']}")
        
    # calculam distanta dintre agent si o tinta oarecare
    def calculate_distance(self, target_x, target_y):
        distance = math.sqrt((self.x-target_x)**2 + (self.y - target_y)**2)
        return distance

