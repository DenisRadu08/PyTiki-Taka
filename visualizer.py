from launcher import get_command
import pygame
import zmq
import json
import subprocess
import sys
import time
from config import STATUS_GOAL, STATUS_OUT, STATUS_MATCH_OVER, STATUS_PLAYING, STATUS_START_GAME, STATE_KICK
import math
import random

class GameVisualizer:
    def __init__(self):
        # pornim motorul grafic
        pygame.init()
        pygame.mixer.init() # Init audio mixer

        # ==========================================
        # AUDIO LOADING (Failsafe)
        # ==========================================
        self.sound_whistle = None
        try:
            self.sound_whistle = pygame.mixer.Sound("assets/sounds/whistle.mp3")
        except FileNotFoundError:
            print("WARNING: Nu am gasit assets/sounds/whistle.mp3 - Jucam fara sunet.")

        
        try:
            pygame.mixer.music.load("assets/sounds/crowd.mp3")
            pygame.mixer.music.set_volume(0.3) # Volum redus pt fundal
            pygame.mixer.music.play(-1) # -1 inseamna Loop Infinit
        except FileNotFoundError:
            print("WARNING: Nu am gasit assets/sounds/crowd.mp3 - Jucam in liniste.")
            
        self.sound_goal = None
        try:
            self.sound_goal = pygame.mixer.Sound("assets/sounds/goal.mp3")
        except FileNotFoundError:
            print("WARNING: Nu am gasit assets/sounds/goal.mp3")

        self.sound_gasp = None
        try:
            self.sound_gasp = pygame.mixer.Sound("assets/sounds/gasp.mp3")
        except FileNotFoundError:
            print("WARNING: Nu am gasit assets/sounds/gasp.mp3")

        self.sound_kick = None
        try:
            self.sound_kick = pygame.mixer.Sound("assets/sounds/kick.mp3")
        except FileNotFoundError:
            print("WARNING: Nu am gasit assets/sounds/kick.mp3")

        # Flag-uri pentru a preveni spam-ul audio (fluierat de 60 de ori pe secunda)
        self.match_over_whistle_played = False
        self.gasp_played_for_this_shot = False
        self.last_ball_speed = 0.0

        # =======================================================
        # SISTEM RESPONSIVE FULLSCREEN (Auto-Scalare)
        # =======================================================
        # 1. Obtinem rezolutia maxima a monitorului (ex: 1920x1080)
        info = pygame.display.Info()
        screen_w = info.current_w
        screen_h = info.current_h

        self.scale = screen_h / 840.0

        # definim dimensiunile de baza
        self.play_width = int(900 * self.scale)
        self.play_height = int(600 * self.scale)

       # margini uriase pentru tribune
        self.stadium_padding_x = (screen_w - self.play_width) // 2 
        self.stadium_padding_y = (screen_h - self.play_height) // 2

        # Marginea tehnica dintre tușa si inceputul tribunei
        self.margin_x = int(20 * self.scale) 
        self.margin_y = int(20 * self.scale)

        # 5. Activam FULLSCREEN!
        self.screen = pygame.display.set_mode((screen_w, screen_h), pygame.FULLSCREEN)

        # setam titlul ferestrei
        pygame.display.set_caption("PyTiki-Taka")

        # cream socket-ul
        self.context = zmq.Context()
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE,"")
        self.sub_socket.connect("tcp://localhost:5555")

        self.simulation_started = True
        # Lansam motorul imediat ce visualizer-ul se deshide
        print ("Lansam Match Engine-ul in fundal...")
        self.engine_process = subprocess.Popen(get_command("--engine"))

        # setam culorile
        self.GREEN = (34, 139, 34) # gazon
        self.DARK_GREEN = (28, 115, 28) # gazoninchis pentru dungi
        self.WHITE = (255, 255, 255) # minge
        self.RED = (220, 20, 60) # Echipa A
        self.BLUE = (30, 144, 255) # Echipa B
        self.BLACK = (0, 0, 0) # umbre, contururi

        # Culori pentru tribune (Gri beton/plastic)
        self.STAND_GRAY = (100, 100, 100)
        self.STAND_DARK = (60, 60, 60)
        
        # Culori pentru spectatori (un mix pestrit)
        self.FAN_COLORS = [
            (200, 50, 50), (50, 50, 200), (200, 200, 50), 
            (50, 200, 50), (200, 100, 50), (150, 150, 150)
        ]
        import random
        self.random_gen = random.Random(42)
        
        self.font = pygame. font.SysFont("Arial", int(48 * self.scale), bold = True)
        self.small_font = pygame.font.SysFont("Arial", int(18 * self.scale), bold=True)
        
        self.huge_font = pygame.font.SysFont("Arial", int(80 * self.scale), bold=True)
        
    
    def stop_engine(self):
        # Opreste curat procesele din fundal pentru a nu lasa zombi.
        if self.engine_process is not None:
            print("Curatam toate procesele din fundal...")
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.engine_process.pid)])
            self.engine_process = None

    def draw_pitch(self):
        # fundalul complet
        self.screen.fill(self.STAND_GRAY)

        # 2. Desenam gazonul central
        field_rect = pygame.Rect(
            self.stadium_padding_x - (self.margin_x * 2),  # <--- Dublat ca sa acopere sub poarta stanga
            self.stadium_padding_y - self.margin_y, 
            self.play_width + (4 * self.margin_x),         # <--- 4x ca sa acopere sub poarta dreapta
            self.play_height + (2 * self.margin_y)
        )
        pygame.draw.rect(self.screen, self.GREEN, field_rect)
        pygame.draw.rect(self.screen, self.BLACK, field_rect, 2)

        # 3. TRIBUNELE (Dinamice, acopera tot spatiul gol)
        fan_size = int(8 * self.scale)  # <--- Marit de la 3 la 8
        fan_spacing = int(fan_size * 3.5)  # <--- Spatiu marit intre fani pentru a fi mai putini.

        start_fans_x = self.stadium_padding_x - self.margin_x
        end_fans_x = field_rect.right
        start_fans_y = self.stadium_padding_y - self.margin_y
        end_fans_y = field_rect.bottom

        # --- Tribuna de Sus (Merge de la marginea stanga la marginea dreapta a ecranului) ---
        for row in range(int(120 * self.scale / fan_spacing)):  # <--- Folosim fan_spacing
            y_row = start_fans_y - (row * fan_spacing) - 20  # <--- Folosim fan_spacing
            pygame.draw.line(self.screen, self.STAND_DARK, (start_fans_x, y_row), (end_fans_x, y_row), 1)
            # Spectatorii tactical tactical.
            for x in range(start_fans_x, end_fans_x, fan_spacing):  # <--- Folosim fan_spacing
                if self.random_gen.random() > 0.6: # 70% ocuparetact tact tactical tact tacttacttacttact tactical.  # <--- Threshold marit de la 0.3 la 0.6 pentru mai putini fani.
                    color = self.random_gen.choice(self.FAN_COLORS)
                    pygame.draw.circle(self.screen, color, (x, y_row - fan_size), fan_size)

        # 4. Tribuna de Jos
        for row in range(int(120 * self.scale / fan_spacing)):  # <--- Folosim fan_spacing
            y_row = end_fans_y + 20 + (row * fan_spacing)  # <--- Folosim fan_spacing
            pygame.draw.line(self.screen, self.STAND_DARK, (start_fans_x, y_row), (end_fans_x, y_row), 1)
            for x in range(start_fans_x, end_fans_x, fan_spacing):  # <--- Folosim fan_spacing
                if self.random_gen.random() > 0.6:  # <--- Threshold marit de la 0.3 la 0.6.
                    color = self.random_gen.choice(self.FAN_COLORS)
                    pygame.draw.circle(self.screen, color, (x, y_row + fan_size), fan_size)

        self.random_gen.seed(42)

        # Calculam limitele peluzelor pentru a NU intra in colturile ocupate de tribune
        y_start_peluza = field_rect.top - 20
        y_end_peluza = field_rect.bottom + 20
        cols_left = int(int(280 * self.scale - self.margin_x) / fan_spacing)  # <--- Folosim fan_spacing



        for col in range(cols_left):
            x_col = start_fans_x - (col * fan_spacing) - 20  # <--- Folosim fan_spacing
            # Linie verticala tact tact tact tact tact tact tact tacttacttacttacttact tact tactics tacttacttacttacttact tact tactics bases tact tact tactics tactile based basics bases tactical tactile based bases basic tact tactile based basis basic tact basic specifically standard tactical base tactical basically standard bases basic standard standard standard standard specific generic generally purely standard strictly basic generic purely specific clearly basis based clearly generalized organizing central control organization generalized organization based centrally organized monolithic organization structured on generalized centrally organization based on strictly centralized controlled monolithic bureaucracy standardized uniform bureaucracy standardized administrative organization monolithic standardized administrative system centralized controlled monolithic bureaucracy standard uniform rules strictly clear and rigid bureaucracy strict fixed simplified standard clear rules explicitly predefined strict limited simplified straight straightforward simplified procedures direct strictly simple direct straightforward rules direct simple rigid administrative rules distinct set simplified straight straightforward standardized simple rigidly based specific limited defined simplified straightforward procedure direct straight streamlined rigid generalized bureaucracy standard clear strict standardized rules standard simplified procedure straightforward based strictly simplified rules specific set streamlined standardized procedures explicit limited distinct strictly straight simplified standard simple straightforward direct procedure clearly defined limited clear distinct clear strict simple straightforward standard strict direct specific set straightforward streamlined standardized rules direct clear simple straightforward specialized procedure.
            pygame.draw.line(self.screen, self.STAND_DARK, (x_col, 0), (x_col, self.screen.get_height()), 1)
            for y in range(0, self.screen.get_height(), fan_spacing):  # <--- Folosim fan_spacing
                if self.random_gen.random() > 0.6:  # <--- Threshold marit de la 0.3 la 0.6.
                    color = self.random_gen.choice(self.FAN_COLORS)
                    pygame.draw.circle(self.screen, color, (x_col - fan_size, y), fan_size)

        # Peluza din Dreapta
        for col in range(cols_left):
            x_col = end_fans_x + 20 + (col * fan_spacing)  # <--- Folosim fan_spacing
            pygame.draw.line(self.screen, self.STAND_DARK, (x_col, 0), (x_col, self.screen.get_height()), 1)
            for y in range(0, self.screen.get_height(), fan_spacing):  # <--- Folosim fan_spacing
                if self.random_gen.random() > 0.6:  # <--- Threshold marit de la 0.3 la 0.6.
                    color = self.random_gen.choice(self.FAN_COLORS)
                    pygame.draw.circle(self.screen, color, (x_col + fan_size, y), fan_size)
        # Resetam seed-ul la finalul fiecarui cadru ca spectatorii sa nu palpaie
        self.random_gen.seed(42)

        # 4. Dungile de gazon
        stripe_width = self.play_width // 10
        for i in range(10):
            if i % 2 == 0:
                rect = (self.stadium_padding_x + i * stripe_width, self.stadium_padding_y, stripe_width, self.play_height)
                pygame.draw.rect(self.screen, self.DARK_GREEN, rect)
                
        line_w = max(2, int(3 * self.scale))

       # 5. Liniile Albe (Folosim stadium_padding_x IN LOC DE margin_x)
        pitch_rect = (self.stadium_padding_x, self.stadium_padding_y, self.play_width, self.play_height)
        pygame.draw.rect(self.screen, self.WHITE, pitch_rect, line_w)

        mid_x = self.stadium_padding_x + self.play_width // 2
        mid_y = self.stadium_padding_y + self.play_height // 2
        
        pygame.draw.line(self.screen, self.WHITE, (mid_x, self.stadium_padding_y), (mid_x, self.stadium_padding_y + self.play_height), line_w)
        pygame.draw.circle(self.screen, self.WHITE, (mid_x, mid_y), int(70 * self.scale), line_w)
        pygame.draw.circle(self.screen, self.WHITE, (mid_x, mid_y), int(5 * self.scale))

       # Careul mare
        pen_w = int(110 * self.scale)
        pen_h = int(220 * self.scale)
        pen_y = self.stadium_padding_y + (self.play_height - pen_h) // 2

        pygame.draw.rect(self.screen, self.WHITE, (self.stadium_padding_x, pen_y, pen_w, pen_h), line_w)
        pygame.draw.circle(self.screen, self.WHITE, (self.stadium_padding_x + int(90 * self.scale), mid_y), int(4 * self.scale)) 
        
        pygame.draw.rect(self.screen, self.WHITE, (self.stadium_padding_x + self.play_width - pen_w, pen_y, pen_w, pen_h), line_w)
        pygame.draw.circle(self.screen, self.WHITE, (self.stadium_padding_x + self.play_width - int(90 * self.scale), mid_y), int(4 * self.scale))

        # Careul mic
        goal_box_w = int(30 * self.scale)
        goal_box_h = int(100 * self.scale)
        goal_box_y = self.stadium_padding_y + (self.play_height - goal_box_h) // 2
        
        pygame.draw.rect(self.screen, self.WHITE, (self.stadium_padding_x, goal_box_y, goal_box_w, goal_box_h), line_w)
        pygame.draw.rect(self.screen, self.WHITE, (self.stadium_padding_x + self.play_width - goal_box_w, goal_box_y, goal_box_w, goal_box_h), line_w)

        # Semicercurile
        pen_circle = int(50 * self.scale)
        
        bbox_x_left = self.stadium_padding_x + pen_w - pen_circle
        bbox_y_left = mid_y - pen_circle
        circle_left = pygame.Rect(bbox_x_left, bbox_y_left, 2 * pen_circle, 2 * pen_circle)
        pygame.draw.arc(self.screen, self.WHITE, circle_left, -math.pi / 2, math.pi / 2, line_w)

        bbox_x_right = self.stadium_padding_x + self.play_width - pen_w - pen_circle
        bbox_y_right = mid_y - pen_circle
        circle_right = pygame.Rect(bbox_x_right, bbox_y_right, 2 * pen_circle, 2 * pen_circle)
        pygame.draw.arc(self.screen, self.WHITE, circle_right, math.pi / 2, 3 * math.pi / 2, line_w)

        # ==============================================================================
        # 8. PORTILE SI PLASA (NET GRID)
        # ==============================================================================
        goal_w = int(self.play_width * 0.03)
        goal_h = int(self.play_height * 0.20)
        goal_y = self.stadium_padding_y + (self.play_height - goal_h) // 2
        net_space = int(5 * self.scale)

        # Plasa stanga
        for y in range(goal_y, goal_y + goal_h, net_space):
            pygame.draw.line(self.screen, self.WHITE, (self.stadium_padding_x - goal_w, y), (self.stadium_padding_x, y), 1)
        for x in range(self.stadium_padding_x - goal_w, self.stadium_padding_x, net_space):
            pygame.draw.line(self.screen, self.WHITE, (x, goal_y), (x, goal_y + goal_h), 1)

        # Plasa dreapta
        for y in range(goal_y, goal_y + goal_h, net_space):
            pygame.draw.line(self.screen, self.WHITE, (self.stadium_padding_x + self.play_width, y), (self.stadium_padding_x + self.play_width + goal_w, y), 1)
        for x in range(self.stadium_padding_x + self.play_width, self.stadium_padding_x + self.play_width + goal_w, net_space):
            pygame.draw.line(self.screen, self.WHITE, (x, goal_y), (x, goal_y + goal_h), 1)

        pygame.draw.rect(self.screen, self.WHITE, (self.stadium_padding_x - goal_w, goal_y, goal_w, goal_h), line_w)
        pygame.draw.rect(self.screen, self.WHITE, (self.stadium_padding_x + self.play_width, goal_y, goal_w, goal_h), line_w)

    def run(self):
        while True:
            # 1. Boilerplate Pygame (mecanismul de inchidere)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    # clean shutdown
                    self.stop_engine()
                    pygame.quit()
                    return # iesim din functie
                
                # Iesire rapida din FULLSCREEN cu tasta ESCAPE
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.stop_engine()
                        pygame.quit()
                        return
                
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mouse_pos = event.pos

                    # Cazul B: In timpul simularii (Butoanele mici)
                    if hasattr(self, 'btn_restart') and self.btn_restart.collidepoint(mouse_pos):
                        print("Restartam meciul...")
                        self.stop_engine()
                        time.sleep(0.5) # Asteptam 500ms ca Windows-ul sa elibereze porturile ZMQ
                        self.engine_process = subprocess.Popen(get_command("--engine"))
                            
                    elif hasattr(self, 'btn_quit') and self.btn_quit.collidepoint(mouse_pos):
                        print("Oprim jocul de tot...")
                        self.stop_engine()
                        pygame.quit()
                        return
                    
            
            # 2. desenam terenul
            self.draw_pitch()
            
            # simularea in desfasurare
            try:
                message = self.sub_socket.recv_json(flags=zmq.NOBLOCK)
                
                # Salvam datele ultimului cadru in instanta pentru a le putea desena constant
                self.last_message = message 
            except zmq.Again:
                # Daca inca nu am primit nimic (se incarca) sau motorul e intre cadre
                if not hasattr(self, 'last_message'):
                    pygame.display.flip()
                    continue
                message = self.last_message
            

            # =======================================================
            # SMART AUDIO TRIGGERS
            # =======================================================
            current_status = message.get("game_status")
            if not hasattr(self, 'last_status'):
                self.last_status = current_status

            # Daca jocul abia incepe SAU se reia dupa un gol -> Kickoff Whistle!
            if current_status == STATUS_PLAYING and self.last_status in [STATUS_START_GAME, STATUS_GOAL]:
                if self.sound_whistle:
                    self.sound_whistle.play()
                if self.sound_goal:
                    self.sound_goal.stop() # Oprim celebrarea golului cand se da fluierul de reluare
            
            # Daca meciul se termina (Fluier Final!)
            if current_status == STATUS_MATCH_OVER and not self.match_over_whistle_played:
                if self.sound_whistle:
                    self.sound_whistle.play()
                self.match_over_whistle_played = True
                
            # Daca s-a marcat un gol
            if current_status == STATUS_GOAL and self.last_status != STATUS_GOAL:
                if self.sound_goal:
                    self.sound_goal.play()
            
            # Logica de Fizica a mingii pentru KICK si GASP
            ball_vx = message["ball"]["velocity_x"]
            ball_vy = message["ball"]["velocity_y"]
            current_ball_speed = math.hypot(ball_vx, ball_vy)
            
            # Daca mingea prinde brusc viteza mare (Delta > 0.8), a fost lovita!
            if current_ball_speed - self.last_ball_speed > 0.8:
                
                # 1. Sunetul fizic de lovitura
                if self.sound_kick:
                    self.sound_kick.play()
                    
            self.last_ball_speed = current_ball_speed
            
                
            self.last_status = current_status


            # 4. Extragem X si Y pentru minge
            ball_x = self.stadium_padding_x + (message["ball"]["x"] * (self.play_width / 100.0))
            ball_y = self.stadium_padding_y + (message["ball"]["y"] * (self.play_height / 100.0))

            # 5. Parcurgem jucatorii (Desenam intai jucatorii ca mingea sa fie deasupra lor)
            for player_id, player_data in message["players"].items():
                
                draw_x = int(self.stadium_padding_x + (player_data["x"] * (self.play_width / 100.0)))
                draw_y = int(self.stadium_padding_y + (player_data["y"] * (self.play_height / 100.0)))
            
                team = player_data.get("team", "Unknown")
                if team == "A":
                    player_color = self.RED
                elif team == "B":
                    player_color = self.BLUE
                else:
                    player_color = (128, 128, 128)

                # scalam dimensiunea jucatorului
                p_radius = int(10 * self.scale)
                shadow_offset = max(1, int(4 * self.scale))
                
                # Umbra semi-transparenta
                shadow_surf = pygame.Surface((p_radius * 2, p_radius * 2), pygame.SRCALPHA)
                pygame.draw.circle(shadow_surf, (0, 0, 0, 100), (p_radius, p_radius), p_radius)
                self.screen.blit(shadow_surf, (draw_x - p_radius + shadow_offset, draw_y - p_radius + shadow_offset))

                # 2. Jucatorul
                pygame.draw.circle(self.screen, player_color, (draw_x, draw_y), p_radius)
                pygame.draw.circle(self.screen, self.WHITE, (draw_x, draw_y), p_radius, max(1, int(1 * self.scale)))


                # adaugare numar pe tricou
                number_str = int(player_id) % 100

                # Randam textul cu alb
                num_surf = self.small_font.render(str(number_str), True, self.WHITE)
                
                # Ca sa fim siguri ca numarul incape bine in cerc, il pozitionam fix in centru
                num_rect = num_surf.get_rect(center=(draw_x, draw_y))
                
                # Desenam numarul pe ecran
                self.screen.blit(num_surf, num_rect)

            # 6. Desenarea mingii
            b_radius = int(8 * self.scale)
            shadow_offset_b = max(1, int(6 * self.scale))
            
            # Umbra Mingii (mai departe de sol = impresia ca mingea sare)
            ball_shadow = pygame.Surface((b_radius * 2, b_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(ball_shadow, (0, 0, 0, 120), (b_radius, b_radius), b_radius)
            self.screen.blit(ball_shadow, (int(ball_x) - b_radius + shadow_offset_b, int(ball_y) - b_radius + shadow_offset_b))

            # Mingea in sine (Sfera 3D cu shading)
            pygame.draw.circle(self.screen, (240, 240, 240), (int(ball_x), int(ball_y)), b_radius) # Baza alba
            
            # Desenam modelul clasic de minge (Pentagon central + Linii)
            pentagon_radius = max(2, int(b_radius * 0.45))
            pentagon_points = []
            
            # Calculam matematic cele 5 colturi ale pentagonului
            for i in range(5):
                angle = i * (2 * math.pi / 5) - (math.pi / 2) 
                px = int(ball_x) + pentagon_radius * math.cos(angle)
                py = int(ball_y) + pentagon_radius * math.sin(angle)
                pentagon_points.append((px, py))
            
            if len(pentagon_points) >= 3:
                # 1. Desenam pentagonul negru in centru
                pygame.draw.polygon(self.screen, (30, 30, 30), pentagon_points)
                
                # 2. Desenam "cusaturile" care pleaca din colturi spre marginea mingii
                for px, py in pentagon_points:
                    dx = px - int(ball_x)
                    dy = py - int(ball_y)
                    dist = math.hypot(dx, dy)
                    if dist > 0:
                        edge_x = int(ball_x) + (dx / dist) * b_radius
                        edge_y = int(ball_y) + (dy / dist) * b_radius
                        pygame.draw.line(self.screen, (30, 30, 30), (px, py), (edge_x, edge_y), max(1, int(1 * self.scale)))
            # Contur fin pe exterior
            pygame.draw.circle(self.screen, self.BLACK, (int(ball_x), int(ball_y)), b_radius, max(1, int(1 * self.scale)))
            # Highlight de lumina subtil in stanga sus
            pygame.draw.arc(self.screen, self.WHITE, (int(ball_x)-b_radius, int(ball_y)-b_radius, b_radius*2, b_radius*2), math.pi/2, math.pi, max(1, int(1*self.scale)))


            # =======================================================
            # 8. CELEBRAREA GOLULUI
            # =======================================================
            if message.get("game_status") == STATUS_GOAL:
                text_goal = self.huge_font.render("GOOOOOAALLL!", True, self.BLACK)
                text_shadow = self.huge_font.render("GOOOOOAALLL!", True, self.WHITE)
                
                # Centram textul fix pe mijlocul ecranului
                center_pos = (self.screen.get_width() // 2, self.screen.get_height() // 2)
                
                # Desenam umbra intai (decalata putin jos si la dreapta pentru efect 3D)
                shadow_rect = text_shadow.get_rect(center=(center_pos[0] + 5, center_pos[1] + 5))
                self.screen.blit(text_shadow, shadow_rect)
                
                # Desenam textul alb principal
                goal_rect = text_goal.get_rect(center=center_pos)
                self.screen.blit(text_goal, goal_rect)
            
            # ========================================================

            # =======================================================
            # 9. ANUNTUL DE OUT
            # =======================================================
            elif message.get("game_status") == STATUS_OUT:
                text_out = self.font.render("OUT DE MARGINE", True, self.BLACK)
                text_shadow = self.font.render("OUT DE MARGINE", True, self.WHITE)
                
                # Pozitionam textul sus, pe centru (chiar deasupra liniei de margine de sus)
                out_pos = (self.screen.get_width() // 2, self.stadium_padding_y - int(10 * self.scale))
                
                # Desenam umbra (un decalaj mai fin decat la gol)
                shadow_rect = text_shadow.get_rect(center=(out_pos[0] + 3, out_pos[1] + 3))
                self.screen.blit(text_shadow, shadow_rect)
                
                # Desenam textul alb
                out_rect = text_out.get_rect(center=out_pos)
                self.screen.blit(text_out, out_rect)

            # ======================================================

            # =======================================================
            # 10. ECRANUL DE FINAL DE MECI (MATCH OVER)
            # =======================================================
            elif message.get("game_status") == STATUS_MATCH_OVER:
                # O folie semi-transparenta neagra peste tot ecranul
                overlay = pygame.Surface((self.screen.get_width(), self.screen.get_height()), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 180)) # 180 = Destul de intunecat pentru contrast
                self.screen.blit(overlay, (0, 0))

                # Text FULL TIME
                text_over = self.huge_font.render("FULL TIME", True, self.WHITE)
                over_rect = text_over.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 - int(50 * self.scale)))
                self.screen.blit(text_over, over_rect)

                # Scorul Final (folosind un auriu frumos)
                score_a = message.get("score_A", 0)
                score_b = message.get("score_B", 0)
                text_score = self.font.render(f"RED {score_a} - {score_b} BLUE", True, (255, 215, 0))
                score_rect = text_score.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + int(30 * self.scale)))
                self.screen.blit(text_score, score_rect)


            # =======================================================
            
            # =======================================================
            # EFECT DE NOAPTE (SPOTLIGHT PE GAZON)
            # =======================================================
            # Cream o umbra peste tot ecranul (opacitate 170 din 255)
            darkness = pygame.Surface((self.screen.get_width(), self.screen.get_height()), pygame.SRCALPHA)
            darkness.fill((0, 0, 0, 110)) 

            # Decupam o "gaura de lumina" perfect deasupra gazonului (Alpha 0)
            light_rect = pygame.Rect(
                self.stadium_padding_x - (self.margin_x * 2), # <--- Dublat (acopera poarta stanga)
                self.stadium_padding_y - self.margin_y, 
                self.play_width + (4 * self.margin_x),        # <--- 4x pentru a dubla pe ambele parti (acopera poarta dreapta)
                self.play_height + (2 * self.margin_y)
            )
            darkness.fill((255, 255, 255, 0), light_rect, special_flags=pygame.BLEND_RGBA_MIN)
            
            # Adaugam intunericul peste tribune si jucatori (gazonul ramane luminat prin gaura)
            self.screen.blit(darkness, (0, 0))

            # =======================================================
            # DESENAREA BUTOANELOR IN TIMPUL MECIULUI (Ghost HUD)
            # =======================================================
            screen_w = self.screen.get_width()

            # Dimensiunile butoanelor mici scalate
            s_btn_w = int(100 * self.scale)
            s_btn_h = int(18 * self.scale)
            pad = int(15 * self.scale)
            
            # 1. Definim zonele fizice ale butoanelor (pentru click si hover)
            self.btn_quit = pygame.Rect(screen_w - s_btn_w - pad, pad, s_btn_w, s_btn_h)
            self.btn_restart = pygame.Rect(screen_w - (2 * s_btn_w) - (2 * pad), pad, s_btn_w, s_btn_h)
            
            # 2. Citim pozitia curenta a mouse-ului
            mouse_pos = pygame.mouse.get_pos()
            
            # 3. Impachetam informatiile butoanelor intr-o lista pentru a scrie cod curat
            buttons_ui = [
                (self.btn_quit, self.RED, "QUIT", self.btn_quit.collidepoint(mouse_pos)),
                (self.btn_restart, self.BLUE, "RESTART", self.btn_restart.collidepoint(mouse_pos))
            ]

            # 4. Desenam fiecare buton in parte
            for rect, color, text, is_hovering in buttons_ui:
                # Daca mouse-ul e pe buton, alpha e 255 (100% vizibil)
                # Daca nu e pe buton, alpha e 40 (15% vizibil - aproape transparent)
                alpha = 255 if is_hovering else 40
                
                # Cream o "folie" transparenta de marimea butonului
                btn_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                
                # Desenam fundalul si conturul pe folie, aplicand valoarea alpha
                pygame.draw.rect(btn_surf, (*color, alpha), btn_surf.get_rect(), border_radius=6)
                pygame.draw.rect(btn_surf, (*self.WHITE, alpha), btn_surf.get_rect(), 2, border_radius=6)
                
                # Randam textul si ii setam aceeasi transparenta
                text_surf = self.small_font.render(text, True, self.WHITE)
                text_surf.set_alpha(alpha)
                
                # Lipim textul pe folie
                btn_surf.blit(text_surf, text_surf.get_rect(center=btn_surf.get_rect().center))
                
                # Lipim folia finala pe ecranul principal
                self.screen.blit(btn_surf, rect.topleft)

            # =======================================================
            # TABELA DE SCOR SI TIMP (HUD)
            # =======================================================
            # 1. Extragem datele (cu fallback la 0 in caz ca motorul de abia a pornit)
            score_a = message.get("score_A", 0)
            score_b = message.get("score_B", 0)
            v_time = message.get("time", 0.0)

            # 2. Convertim timpul din float in MM:SS
            mins = int(v_time)
            secs = int((v_time - mins) * 60)
            time_str = f"{mins:02d}:{secs:02d}"

            # 3. Definim latimile pentru fiecare segment din bara
            box_h = int(35 * self.scale)
            team_w = int(70 * self.scale)
            score_w = int(60 * self.scale)
            time_w = int(70 * self.scale)
            total_w = team_w + score_w + team_w + time_w

            # 4. Plasament: Stanga-Sus (cu o mica margine ca la TV)
            start_x = int(50 * self.scale)
            start_y = int(40 * self.scale)

            # 5. Umbra 3D sub intregul HUD
            shadow = pygame.Surface((total_w, box_h), pygame.SRCALPHA)
            shadow.fill((0, 0, 0, 120))
            self.screen.blit(shadow, (start_x + int(4 * self.scale), start_y + int(4 * self.scale)))

            # 6. Segmentul 1: RED (Fundal Rosu, Text Alb)
            rect_red = pygame.Rect(start_x, start_y, team_w, box_h)
            pygame.draw.rect(self.screen, self.RED, rect_red)
            text_red = self.small_font.render("RED", True, self.WHITE)
            self.screen.blit(text_red, text_red.get_rect(center=rect_red.center))

            # 7. Segmentul 2: SCOR (Fundal Alb, Text Negru)
            rect_score = pygame.Rect(start_x + team_w, start_y, score_w, box_h)
            pygame.draw.rect(self.screen, self.WHITE, rect_score)
            text_sc = self.small_font.render(f"{score_a} - {score_b}", True, self.BLACK)
            self.screen.blit(text_sc, text_sc.get_rect(center=rect_score.center))

            # 8. Segmentul 3: BLUE (Fundal Albastru, Text Alb)
            rect_blue = pygame.Rect(start_x + team_w + score_w, start_y, team_w, box_h)
            pygame.draw.rect(self.screen, self.BLUE, rect_blue)
            text_blue = self.small_font.render("BLUE", True, self.WHITE)
            self.screen.blit(text_blue, text_blue.get_rect(center=rect_blue.center))
            
            # 9. Segmentul 4: TIMP (Fundal Gri inchis, Text Auriu)
            rect_time = pygame.Rect(start_x + team_w + score_w + team_w, start_y, time_w, box_h)
            pygame.draw.rect(self.screen, (30, 30, 30), rect_time)
            text_time = self.small_font.render(time_str, True, (255, 215, 0))
            self.screen.blit(text_time, text_time.get_rect(center=rect_time.center))

            # 10. Contur fin alb in jurul intregului HUD pentru un aspect "sharp"
            pygame.draw.rect(self.screen, self.WHITE, (start_x, start_y, total_w, box_h), max(1, int(2 * self.scale)))

            # Actualizam ecranul
            pygame.display.flip()

if __name__ == "__main__":
    visualizer = GameVisualizer()
    visualizer.run()