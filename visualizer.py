import pygame
import zmq
import json

class GameVisualizer:
    def __init__(self):
        # pornim motorul grafic
        pygame.init()
        # cream fereastra
        self.screen = pygame.display.set_mode((800,600))
        # setam titlul ferestrei
        pygame.display.set_caption("PyTiki-Taka")
        # cream socket-ul
        self.context = zmq.Context()
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE,"")
        self.sub_socket.connect("tcp://localhost:5555")
        # setam culorile
        self.GREEN = (34, 139, 34) # gazon
        self.WHITE = (255, 255, 255) # minge
        self.RED = (255, 0, 0) # agent 1
        self.BLUE = (0, 0, 255) # agent 2

    def run(self):
        while True:
            # 1. Boilerplate Pygame (mecanismul de inchidere)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return # iesim din functie
            
            # 2. Vopsim fundalul in verde
            self.screen.fill(self.GREEN)

            # 3. Ascultam pe retea (blocant, asteptam cadrul)
            message = self.sub_socket.recv_json()

            # 4. Extragem X si Y pentru minge
            ball_x = message["ball"]["x"]
            ball_y = message["ball"]["y"]
            
            # 5. Scalare pentru a arata bine pe ecran
            ball_x *= 8
            ball_y *= 6

            # 6. Desenarea mingii
            pygame.draw.circle(self.screen, self.WHITE, (int(ball_x), int(ball_y)), 5)

            # 7. Parcurgem jucatorii
            for player_id, player_data in message["players"].items():
                player_data["x"] *= 8
                player_data["y"] *= 6
            
                # 8. Culoarea jucatorilor
                if player_id == "1":
                    player_color = self.RED
                else:
                    player_color = self.BLUE
            
                # 9. Desenam jucatorii
                pygame.draw.circle(self.screen, player_color, (int(player_data["x"]), int(player_data["y"])), 10)
            
            # 10. Actualizam ecranul
            pygame.display.flip()

if __name__ == "__main__":
    visualizer = GameVisualizer()
    visualizer.run()