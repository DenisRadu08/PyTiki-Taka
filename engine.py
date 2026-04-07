import zmq
import time
import json

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
        self.ball = {"x": 50, "y": 50}

    
    def run(self):
        while True:
            # Verificam daca sunt mesaje de la jucatori
            events = dict(self.poller.poll(timeout=10))
            # verificam daca un agent a trimis o cerere
            if self.router_socket in events:
                message = self.router_socket.recv_multipart()
                agent_identity, agent_message = message
                intention = json.loads(agent_message.decode('utf-8'))
                print(f"Motorul valideaza actiunea '{intention['action']}' de la Agentul {intention['agent_id']}")

            # broadcast la starea mingii
            self.pub_socket.send_json(self.ball)


    