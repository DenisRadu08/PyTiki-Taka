import zmq
import time
import json
import math

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
        # Jucatori
        self.players = {}

    
    def run(self):
        while True:
            # Verificam daca sunt mesaje de la jucatori
            events = dict(self.poller.poll(timeout=10))
            # verificam daca un agent a trimis o cerere
            if self.router_socket in events:
                message = self.router_socket.recv_multipart()
                agent_identity, agent_message = message
                intention = json.loads(agent_message.decode('utf-8'))
                # adaugam jucatorul in dictionar daca nu exista
                if intention["agent_id"] not in self.players:
                    self.players[intention["agent_id"]] = {"x": 10 + intention["agent_id"], "y": 10 * intention["agent_id"]}
                print(f"Motorul valideaza actiunea '{intention['action']}' de la Agentul {intention['agent_id']}")
                # daca suntem in chase ball, mergem spre minge
                if intention["action"] == "chase ball":
                    player_x = self.players[intention["agent_id"]]["x"]
                    player_y = self.players[intention["agent_id"]]["y"]

                    ball_x = self.ball["x"]
                    ball_y = self.ball["y"]

                    diff_x = ball_x - player_x
                    diff_y = ball_y - player_y

                    distance = math.hypot(diff_x, diff_y)

                    if distance > 0:
                        self.players[intention["agent_id"]]["x"] += diff_x / distance
                        self.players[intention["agent_id"]]["y"] += diff_y / distance


                    
                reply_dict = {"status": "approved"}
                reply_bytes = json.dumps(reply_dict).encode('utf-8')
                self.router_socket.send_multipart([agent_identity, reply_bytes])
            # miscarea mingii
            if self.ball['x']<100 :
                self.ball['x'] += 1
            else:
                self.ball['x'] = 0
            # broadcast la starea mingii
            self.pub_socket.send_json(self.ball)


    