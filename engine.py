import zmq
import time
import json
import math
from config import *

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
        # Jucatori
        self.players = {}
        # Ultimul jucator care a atins mingea (pentru OUT/CORNER)
        self.last_touch = None

    
    def run(self):
        while True:
            # Verificam daca sunt mesaje de la jucatori
            events = dict(self.poller.poll(timeout=10))
            # verificam daca un agent a trimis o cerere
            if self.router_socket in events:
                message = self.router_socket.recv_multipart()
                agent_identity, agent_message = message
                intention = json.loads(agent_message.decode('utf-8'))

                # extragem ID-ul ca string curat
                agent_id_str = str(intention["agent_id"])
                # adaugam jucatorul in dictionar daca nu exista
                if agent_id_str not in self.players:
                    self.players[agent_id_str] = {
                        "start_x" : STARTING_POSITIONS[agent_id_str]["x"],
                        "start_y" : STARTING_POSITIONS[agent_id_str]["y"],
                        "x" : STARTING_POSITIONS[agent_id_str]["x"],
                        "y" : STARTING_POSITIONS[agent_id_str]["y"],
                        "state" : STATE_IDLE
                    }
                if str(intention["action"]) in [STATE_KICK, STATE_DRIBBLE]: 
                    self.ball["velocity_x"] = float(intention["kick_vx"])
                    self.ball["velocity_y"] = float(intention["kick_vy"])
                    self.last_touch = intention["agent_id"] 
                # actualizam starea jucatorului
                self.players[str(intention["agent_id"])]["state"] = intention["action"]
                print(f"Motorul valideaza actiunea '{intention['action']}' de la Agentul {intention['agent_id']}")
                reply_dict = {"status": "approved"}
                reply_bytes = json.dumps(reply_dict).encode('utf-8')
                self.router_socket.send_multipart([agent_identity, reply_bytes])

            # miscarea agentilor
            for player_id, player_data in self.players.items():
                # daca suntem in CHASE, fugim spre minge (1.5 speed)
                if player_data["state"] == STATE_CHASE:
                    self.move_player_towards(player_data, self.ball["x"], self.ball["y"], speed = 1.5)
                
                # daca suntem in RESET, ne intoarcem la pozitia initiala de pe teren (1.0 speed)
                elif player_data["state"] == STATE_RESET:
                    self.move_player_towards(player_data, player_data["start_x"], player_data["start_y"], speed = 1.0)
                
                # daca suntem in DO_THROW_IN, merge usor spre a bate out-ul (0.5 speed)
                elif player_data["state"] == STATE_DO_THROW_IN:
                    self.move_player_towards(player_data, self.ball["x"], self.ball["y"], speed = 0.5)

            

            # miscarea mingii
            # 1. aplicam viteza
            self.ball['x'] += self.ball['velocity_x']
            self.ball['y'] += self.ball['velocity_y']
            # 2. aplicam frecarea
            self.ball['velocity_x'] *= 0.95
            self.ball['velocity_y'] *= 0.95

            # broadcast al jocului
            game_state = {
                "ball" : self.ball,
                "players" : self.players,
                "game_status" : STATUS_PLAYING,
                "last_touch" : self.last_touch 
            }

            # OUT + GOAL?
            if self.ball['x'] <= 0:
                if self.ball['y'] >= 40 and self.ball['y'] <=60:
                    print("GOAL!!! GOAL!!! GOAL!!!")
                    game_state['game_status'] = STATUS_GOAL
                    self.ball['x'] = 50
                    self.ball['y'] = 50
                    self.ball['velocity_x'] = 0
                    self.ball['velocity_y'] = 0
                else:
                    self.ball['velocity_x'] *= -1
                    
                    self.ball['x'] = 0
            if self.ball['x'] >= 100:
                if self.ball['y'] >= 40 and self.ball['y'] <=60:
                    print("GOAL!!! GOAL!!! GOAL!!!")
                    game_state['game_status'] = STATUS_GOAL
                    self.ball['x'] = 50
                    self.ball['y'] = 50

                    self.ball['velocity_x'] = 0
                    self.ball['velocity_y'] = 0
                else:
                    self.ball['velocity_x'] *= -1
                    self.ball['x'] = 100
            if self.ball['y'] <= 0:
                # pentru a avea o singura data print-ul
                if self.ball['velocity_y'] != 0:   
                    print("Out de margine!")     
                game_state['game_status'] = STATUS_OUT
                self.ball['y'] = 0
                self.ball['velocity_x'] = 0
                self.ball['velocity_y'] = 0
            if self.ball['y'] >= 100:
                # pentru a avea o singura data print-ul
                if self.ball['velocity_y'] != 0:    
                    print("Out de margine!")       
                game_state['game_status'] = STATUS_OUT
                self.ball['y'] = 100
                self.ball['velocity_x'] = 0
                self.ball['velocity_y'] = 0


            
            

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
             
    