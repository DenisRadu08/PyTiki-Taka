import zmq
import json
import math
from config import STATE_IDLE, STATE_CHASE

class PlayerAgent:
    def __init__(self, agent_id):
        self.x = agent_id * 10
        self.y = 50
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

                # daca agentul e aproape de minge, trimite intentia de a o urmari
                # mealy machine
                distance_from_ball = self.calculate_distance(message['ball']['x'],message['ball']['y'])
                if distance_from_ball < 20 and self.state == STATE_IDLE:
                    # creez intentia
                    intention = {
                        "agent_id" : self.agent_id,
                        "action" : STATE_CHASE
                    }
                    self.state = STATE_CHASE
                    # trimit intentia pe retea
                    self.dealer_socket.send_json(intention)
                    print(f"Agentul {self.agent_id} a intrat in starea {STATE_CHASE}")
                elif self.state == STATE_CHASE and distance_from_ball>30:
                    self.state = STATE_IDLE
                    intention = {
                        "agent_id" : self.agent_id,
                        "action" : STATE_IDLE
                    }
                    self.dealer_socket.send_json(intention)
                    print(f"Agentul {self.agent_id} a intrat in starea {STATE_IDLE}")
            # verificam daca motorul ne-a raspuns
            if self.dealer_socket in events:
                reply_bytes = self.dealer_socket.recv()
                reply = json.loads(reply_bytes.decode('utf-8'))
                print(f"Agentul {self.agent_id} a primit raspunsul: {reply['status']}")
        
    # calculam distanta dintre agent si minge
    def calculate_distance(self, ball_x, ball_y):
        distance = math.sqrt((self.x-ball_x)**2 + (self.y - ball_y)**2)
        return distance

