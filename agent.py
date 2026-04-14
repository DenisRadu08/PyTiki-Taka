import zmq
import json
import math

class PlayerAgent:
    def __init__(self, agent_id):
        self.x = agent_id * 10
        self.y = 50
        self.state = "IDLE"
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
                print(f"Agentul {self.agent_id} vede mingea la Coordonatele {message['x']}, {message['y']}")
                # daca agentul e aproape de minge, trimite intentia de a o urmari
                # mealy machine
                distance_from_ball = self.calculate_distance(message['x'],message['y'])
                if distance_from_ball < 20 and self.state == "IDLE":
                    intention = {
                        "agent_id" : self.agent_id,
                        "action" : "chase ball"
                    }
                    self.state = "CHASE"
                    print(f"Agentul {self.agent_id} a intrat in starea CHASE")
                    self.dealer_socket.send_json(intention)
                elif self.state == "CHASE" and distance_from_ball>30:
                    self.state = "IDLE"
                    print(f"Agentul {self.agent_id} a intrat in starea IDLE")
            # verificam daca motorul ne-a raspuns
            if self.dealer_socket in events:
                reply_bytes = self.dealer_socket.recv()
                reply = json.loads(reply_bytes.decode('utf-8'))
                print(f"Agentul {self.agent_id} a primit raspunsul: {reply['status']}")
        
    # calculam distanta dintre agent si minge
    def calculate_distance(self, ball_x, ball_y):
        distance = math.sqrt((self.x-ball_x)**2 + (self.y - ball_y)**2)
        return distance

