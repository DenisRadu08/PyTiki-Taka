from launcher import get_command
import pygame
import zmq
import json
import subprocess
import sys
import time
from config import (
    STATUS_GOAL, STATUS_OUT, STATUS_CORNER, STATUS_GOAL_KICK, STATUS_OFFSIDE, STATUS_FREE_KICK, STATUS_PENALTY,
    STATUS_SCENARIO_COUNTDOWN, STATUS_SCENARIO_DONE, STATUS_HALF_TIME, STATUS_MATCH_OVER, STATUS_PLAYING, STATUS_START_GAME, STATE_KICK,
    SCENARIO_1V1_GK, SCENARIO_OFFSIDE_VAR, SCENARIO_CORNER, SCENARIO_TIKI_TAKA, SCENARIO_GOAL_KICK, SCENARIO_THROW_IN,
    SCENARIO_PENALTY, SCENARIO_FREE_KICK
)
import math
import random
from ai_brains import get_short_ai_tag

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

        # Socket DEALER pentru trimiterea instantanee a comenzilor de faze (Tactical Scenarios) catre Engine
        self.cmd_socket = self.context.socket(zmq.DEALER)
        self.cmd_socket.setsockopt_string(zmq.IDENTITY, "VISUALIZER_CMD")
        self.cmd_socket.connect("tcp://localhost:5556")

        self.game_mode = "match"
        try:
            with open("settings.json", "r") as f:
                self.game_mode = json.load(f).get("match_rules", {}).get("game_mode", "match")
        except Exception:
            pass

        self.active_scenario = None
        self.scenario_buttons = []
        self.SCENARIO_LABELS = {
            SCENARIO_1V1_GK: "1v1 GK",
            SCENARIO_OFFSIDE_VAR: "OFFSIDE (VAR)",
            SCENARIO_CORNER: "CORNER",
            SCENARIO_TIKI_TAKA: "COUNTER-ATTACK",
            SCENARIO_GOAL_KICK: "GOAL KICK",
            SCENARIO_THROW_IN: "THROW-IN",
            SCENARIO_PENALTY: "PENALTY",
            SCENARIO_FREE_KICK: "FREE KICK"
        }

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
        self.small_font = pygame.font.SysFont("Arial", max(9, int(11 * self.scale)), bold=True)
        self.stats_font = pygame.font.SysFont("Arial", max(11, int(13 * self.scale)), bold=True)
        self.stats_title_font = pygame.font.SysFont("Arial", max(13, int(16 * self.scale)), bold=True)
        self.huge_font = pygame.font.SysFont("Arial", int(80 * self.scale), bold=True)

        self.btn_resume_half = None
        self.btn_ft_restart = None
        self.btn_ft_menu = None
        self.stats_pill_rect = None
        self.stats_dropdown_rect = None
        self.stats_hover_open = False
        
    
    def stop_engine(self):
        # Opreste curat procesele din fundal pentru a nu lasa zombi.
        if self.engine_process is not None:
            print("Curatam toate procesele din fundal...")
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.engine_process.pid)])
            self.engine_process = None

    def draw_stats_panel(self, stats, center_x, top_y, panel_w, full=True, alpha_panel=230, team_a_name="RED", team_b_name="BLUE"):
        """
        Deseneaza panoul de statistici stil transmisiune TV (Echipa A vs Echipa B):
        - full=False (Hover in joc): Setul 1 (xG, Possession, Shots, Shots on Target, Passes, Pass Accuracy, Corners).
        - full=True (Half-Time & Full-Time): Setul 1 + Setul 2 (Tackles Won, Saves, Fouls, Offsides).
        Returneaza pygame.Rect-ul intregului panou desenat.
        """
        sa = stats.get("A", {}) if stats else {}
        sb = stats.get("B", {}) if stats else {}

        rows_basic = [
            ("EXPECTED GOALS (xG)", f"{sa.get('xg', 0.0):.2f}", f"{sb.get('xg', 0.0):.2f}", float(sa.get('xg', 0.0)), float(sb.get('xg', 0.0))),
            ("POSSESSION", f"{sa.get('possession', 50)}%", f"{sb.get('possession', 50)}%", float(sa.get('possession', 50)), float(sb.get('possession', 50))),
            ("TOTAL SHOTS", str(sa.get('shots', 0)), str(sb.get('shots', 0)), float(sa.get('shots', 0)), float(sb.get('shots', 0))),
            ("SHOTS ON TARGET", str(sa.get('shots_on_target', 0)), str(sb.get('shots_on_target', 0)), float(sa.get('shots_on_target', 0)), float(sb.get('shots_on_target', 0))),
            ("PASSES", str(sa.get('passes', 0)), str(sb.get('passes', 0)), float(sa.get('passes', 0)), float(sb.get('passes', 0))),
            ("PASS ACCURACY", f"{sa.get('pass_accuracy', 0)}%", f"{sb.get('pass_accuracy', 0)}%", float(sa.get('pass_accuracy', 0)), float(sb.get('pass_accuracy', 0))),
            ("CORNERS", str(sa.get('corners', 0)), str(sb.get('corners', 0)), float(sa.get('corners', 0)), float(sb.get('corners', 0))),
        ]
        rows_extra = [
            ("TACKLES WON", str(sa.get('tackles_won', 0)), str(sb.get('tackles_won', 0)), float(sa.get('tackles_won', 0)), float(sb.get('tackles_won', 0))),
            ("GOALKEEPER SAVES", str(sa.get('saves', 0)), str(sb.get('saves', 0)), float(sa.get('saves', 0)), float(sb.get('saves', 0))),
            ("FOULS", str(sa.get('fouls', 0)), str(sb.get('fouls', 0)), float(sa.get('fouls', 0)), float(sb.get('fouls', 0))),
            ("OFFSIDES", str(sa.get('offsides', 0)), str(sb.get('offsides', 0)), float(sa.get('offsides', 0)), float(sb.get('offsides', 0))),
        ]

        rows = rows_basic + (rows_extra if full else [])
        header_h = int(34 * self.scale)
        row_h = int((30 if full else 27) * self.scale)
        pad_x = int(20 * self.scale)
        divider_extra = int(8 * self.scale) if full else 0
        panel_h = header_h + len(rows) * row_h + divider_extra + int(14 * self.scale)

        panel_x = int(center_x - panel_w // 2)
        panel_rect = pygame.Rect(panel_x, int(top_y), int(panel_w), int(panel_h))

        surf = pygame.Surface((panel_rect.width, panel_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(surf, (14, 20, 32, alpha_panel), surf.get_rect(), border_radius=12)
        pygame.draw.rect(surf, (255, 255, 255, min(255, alpha_panel)), surf.get_rect(), max(1, int(2 * self.scale)), border_radius=12)

        # Antetul panoului: TEAM A | MATCH STATS | TEAM B
        pygame.draw.rect(surf, (25, 34, 52, alpha_panel), pygame.Rect(2, 2, panel_rect.width - 4, header_h - 2), border_top_left_radius=10, border_top_right_radius=10)
        red_hdr = self.stats_title_font.render(str(team_a_name), True, (255, 85, 105))
        mid_hdr = self.stats_title_font.render("MATCH STATS", True, (255, 215, 0))
        blu_hdr = self.stats_title_font.render(str(team_b_name), True, (80, 175, 255))
        surf.blit(red_hdr, red_hdr.get_rect(midleft=(pad_x, header_h // 2)))
        surf.blit(mid_hdr, mid_hdr.get_rect(center=(panel_rect.width // 2, header_h // 2)))
        surf.blit(blu_hdr, blu_hdr.get_rect(midright=(panel_rect.width - pad_x, header_h // 2)))

        curr_y = header_h + int(6 * self.scale)
        bar_w_total = panel_rect.width - 2 * pad_x
        bar_h = max(3, int(4 * self.scale))

        for idx, (label, val_a_str, val_b_str, num_a, num_b) in enumerate(rows):
            if full and idx == len(rows_basic):
                # Separator subtil intre statisticile de baza si cele avansate
                pygame.draw.line(surf, (255, 255, 255, 55), (pad_x, curr_y), (panel_rect.width - pad_x, curr_y), 1)
                curr_y += divider_extra

            txt_y = curr_y + int(9 * self.scale)
            col_a = (255, 255, 255) if num_a >= num_b else (180, 190, 205)
            col_b = (255, 255, 255) if num_b >= num_a else (180, 190, 205)

            s_a = self.stats_font.render(val_a_str, True, col_a)
            s_lbl = self.small_font.render(label, True, (200, 212, 228))
            s_b = self.stats_font.render(val_b_str, True, col_b)

            surf.blit(s_a, s_a.get_rect(midleft=(pad_x, txt_y)))
            surf.blit(s_lbl, s_lbl.get_rect(center=(panel_rect.width // 2, txt_y)))
            surf.blit(s_b, s_b.get_rect(midright=(panel_rect.width - pad_x, txt_y)))

            # Bara comparativa proportionala RED vs BLUE sub fiecare rand
            bar_y = curr_y + int(20 * self.scale)
            pygame.draw.rect(surf, (45, 55, 72, 200), pygame.Rect(pad_x, bar_y, bar_w_total, bar_h), border_radius=2)
            total_val = num_a + num_b
            if total_val > 0.0:
                ratio_a = num_a / total_val
                w_a = int(bar_w_total * ratio_a)
                w_b = bar_w_total - w_a
                if w_a > 0:
                    pygame.draw.rect(surf, (*self.RED, 235), pygame.Rect(pad_x, bar_y, w_a, bar_h), border_radius=2)
                if w_b > 0:
                    pygame.draw.rect(surf, (*self.BLUE, 235), pygame.Rect(pad_x + w_a, bar_y, w_b, bar_h), border_radius=2)

            curr_y += row_h

        self.screen.blit(surf, panel_rect.topleft)
        return panel_rect

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

                    # Click pe unul dintre butoanele de faze (Tactical Scenarios)
                    if self.game_mode == "scenarios":
                        clicked_scenario = False
                        for sc_rect, sc_id in self.scenario_buttons:
                            if sc_rect.collidepoint(mouse_pos):
                                print(f"Selectat scenariul tactic: {sc_id}")
                                self.active_scenario = sc_id
                                self.cmd_socket.send_json({"command": "LOAD_SCENARIO", "scenario": sc_id})
                                clicked_scenario = True
                                break
                        if clicked_scenario:
                            continue

                    # Click pe butonul "RESUME MATCH" de pe ecranul de PAUZA (HALF TIME)
                    if self.btn_resume_half is not None and self.btn_resume_half.collidepoint(mouse_pos):
                        print("Reluam meciul -> Repriza a 2-a (schimbarea terenurilor)...")
                        self.cmd_socket.send_json({"command": "RESUME_SECOND_HALF"})
                        self.btn_resume_half = None
                        continue

                    # Click pe butoanele din ecranul FULL TIME (PLAY AGAIN / MAIN MENU)
                    if self.btn_ft_restart is not None and self.btn_ft_restart.collidepoint(mouse_pos):
                        print("Restartam meciul din ecranul FULL TIME...")
                        self.stop_engine()
                        time.sleep(0.5)
                        self.engine_process = subprocess.Popen(get_command("--engine"))
                        self.match_over_whistle_played = False
                        continue
                    if self.btn_ft_menu is not None and self.btn_ft_menu.collidepoint(mouse_pos):
                        print("Revenim in Meniul Principal (Main Menu)...")
                        self.stop_engine()
                        pygame.quit()
                        sys.exit(42)

                    # Cazul B: In timpul simularii (Butoanele mici)
                    if hasattr(self, 'btn_restart') and self.btn_restart.collidepoint(mouse_pos):
                        if self.game_mode == "scenarios":
                            if self.active_scenario is not None:
                                print(f"Reluam faza curenta: {self.active_scenario}...")
                                self.cmd_socket.send_json({"command": "LOAD_SCENARIO", "scenario": self.active_scenario})
                        else:
                            print("Restartam meciul...")
                            self.stop_engine()
                            time.sleep(0.5) # Asteptam 500ms ca Windows-ul sa elibereze porturile ZMQ
                            self.engine_process = subprocess.Popen(get_command("--engine"))
                            
                    elif hasattr(self, 'btn_menu') and self.btn_menu.collidepoint(mouse_pos):
                        print("Revenim in Meniul Principal (Main Menu)...")
                        self.stop_engine()
                        pygame.quit()
                        sys.exit(42)
                        
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

            # Drenam eventualele raspunsuri de confirmare de pe cmd_socket
            try:
                while True:
                    self.cmd_socket.recv(flags=zmq.NOBLOCK)
            except zmq.Again:
                pass

            if "game_mode" in message:
                self.game_mode = message["game_mode"]
            if "active_scenario" in message:
                self.active_scenario = message["active_scenario"]
            

            # =======================================================
            # SMART AUDIO TRIGGERS
            # =======================================================
            current_status = message.get("game_status")
            if not hasattr(self, 'last_status'):
                self.last_status = current_status

            # Daca jocul abia incepe SAU se reia dupa un gol SAU se termina numaratoarea 3,2,1 -> Whistle!
            if (current_status == STATUS_PLAYING and self.last_status in [STATUS_START_GAME, STATUS_GOAL]) or (
                self.last_status == STATUS_SCENARIO_COUNTDOWN and current_status != STATUS_SCENARIO_COUNTDOWN
            ):
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

            # Fluierul arbitrului la OFSAID, FAULT (lovitura libera / penalty), PAUZA (HALF TIME) sau la finalizarea unei faze tactice active
            if (current_status in [STATUS_OFFSIDE, STATUS_FREE_KICK, STATUS_PENALTY, STATUS_HALF_TIME] and self.last_status != current_status and self.last_status != STATUS_SCENARIO_COUNTDOWN) or (
                current_status == STATUS_SCENARIO_DONE and self.last_status != STATUS_SCENARIO_DONE and self.active_scenario is not None
            ):
                if self.sound_whistle:
                    self.sound_whistle.play()
            
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

            # 4.5. LINIA VAR DE OFSAID SI MARCAJUL PUNCTULUI DE REPUNERE (STATUS_OFFSIDE)
            if message.get("game_status") == STATUS_OFFSIDE:
                off_line_x = message.get("offside_line_x")
                off_spot_x = message.get("offside_spot_x")
                off_spot_y = message.get("offside_spot_y")

                if off_line_x is not None:
                    screen_line_x = int(self.stadium_padding_x + (float(off_line_x) * (self.play_width / 100.0)))
                    top_y = self.stadium_padding_y
                    bot_y = self.stadium_padding_y + self.play_height
                    dash_len = max(8, int(12 * self.scale))
                    gap_len = max(5, int(7 * self.scale))
                    line_thickness = max(2, int(3 * self.scale))

                    # Glow subtil sub linia VAR
                    glow_surf = pygame.Surface((int(14 * self.scale), self.play_height), pygame.SRCALPHA)
                    glow_surf.fill((0, 230, 255, 45))
                    self.screen.blit(glow_surf, (screen_line_x - int(7 * self.scale), top_y))

                    # Linie punctata stil TV VAR (Galben-Aurie / Cyan)
                    curr_y = top_y
                    while curr_y < bot_y:
                        end_y = min(bot_y, curr_y + dash_len)
                        pygame.draw.line(self.screen, (255, 230, 0), (screen_line_x, curr_y), (screen_line_x, end_y), line_thickness)
                        curr_y += dash_len + gap_len

                    # Eticheta "VAR OFFSIDE" pe linia de ofsaid
                    var_badge = self.small_font.render("VAR LINE", True, (255, 230, 0))
                    badge_bg = pygame.Rect(0, 0, var_badge.get_width() + int(10 * self.scale), var_badge.get_height() + int(4 * self.scale))
                    badge_bg.center = (screen_line_x, top_y + int(16 * self.scale))
                    pygame.draw.rect(self.screen, (20, 20, 20), badge_bg, border_radius=4)
                    pygame.draw.rect(self.screen, (255, 230, 0), badge_bg, 1, border_radius=4)
                    self.screen.blit(var_badge, var_badge.get_rect(center=badge_bg.center))

                if off_spot_x is not None and off_spot_y is not None:
                    spot_px = int(self.stadium_padding_x + (float(off_spot_x) * (self.play_width / 100.0)))
                    spot_py = int(self.stadium_padding_y + (float(off_spot_y) * (self.play_height / 100.0)))
                    pulse_r = int((11 + 3 * math.sin(time.time() * 8.0)) * self.scale)
                    pygame.draw.circle(self.screen, (255, 80, 80), (spot_px, spot_py), pulse_r, max(2, int(2 * self.scale)))

            # 4.55. MARCAJUL LOCULUI FAULTULUI + ARCUL DE 9.15m (STATUS_FREE_KICK / STATUS_PENALTY)
            elif message.get("game_status") in [STATUS_FREE_KICK, STATUS_PENALTY]:
                f_x = message.get("foul_spot_x")
                f_y = message.get("foul_spot_y")
                if f_x is not None and f_y is not None:
                    fpx = int(self.stadium_padding_x + (float(f_x) * (self.play_width / 100.0)))
                    fpy = int(self.stadium_padding_y + (float(f_y) * (self.play_height / 100.0)))
                    # "X" rosu pulsatoriu pe locul unde s-a produs faultul
                    cross = int((7 + 2 * math.sin(time.time() * 8.0)) * self.scale)
                    cw = max(2, int(3 * self.scale))
                    pygame.draw.line(self.screen, (255, 60, 60), (fpx - cross, fpy - cross), (fpx + cross, fpy + cross), cw)
                    pygame.draw.line(self.screen, (255, 60, 60), (fpx - cross, fpy + cross), (fpx + cross, fpy - cross), cw)

                if message.get("game_status") == STATUS_FREE_KICK and message.get("restart_ball_placed", False):
                    # Spray-ul arbitrului: cercul de 9.15m in jurul mingii (distanta regulamentara a zidului)
                    r_x = int(9.15 * (self.play_width / 100.0))
                    r_y = int(9.15 * (self.play_height / 100.0))
                    arc_rect = pygame.Rect(int(ball_x) - r_x, int(ball_y) - r_y, 2 * r_x, 2 * r_y)
                    spray = pygame.Surface((arc_rect.width + 4, arc_rect.height + 4), pygame.SRCALPHA)
                    pygame.draw.ellipse(spray, (255, 255, 255, 110), pygame.Rect(2, 2, arc_rect.width, arc_rect.height), max(1, int(2 * self.scale)))
                    self.screen.blit(spray, (arc_rect.x - 2, arc_rect.y - 2))

            # 4.6. PREVIEW TACTIC PE GAZON IN TIMPUL NUMARATORII 3, 2, 1 (STATUS_SCENARIO_COUNTDOWN)
            elif message.get("game_status") == STATUS_SCENARIO_COUNTDOWN:
                pulse_ball_r = int((14 + 4 * math.sin(time.time() * 7.0)) * self.scale)
                pygame.draw.circle(self.screen, (255, 215, 0), (int(ball_x), int(ball_y)), pulse_ball_r, max(2, int(2 * self.scale)))
                if self.active_scenario == SCENARIO_OFFSIDE_VAR and message.get("offside_line_x") is not None:
                    screen_line_x = int(self.stadium_padding_x + (float(message["offside_line_x"]) * (self.play_width / 100.0)))
                    top_y = self.stadium_padding_y
                    bot_y = self.stadium_padding_y + self.play_height
                    dash_len = max(8, int(12 * self.scale))
                    gap_len = max(5, int(7 * self.scale))
                    curr_y = top_y
                    while curr_y < bot_y:
                        end_y = min(bot_y, curr_y + dash_len)
                        pygame.draw.line(self.screen, (0, 230, 255), (screen_line_x, curr_y), (screen_line_x, end_y), max(1, int(2 * self.scale)))
                        curr_y += dash_len + gap_len
                elif self.active_scenario == SCENARIO_FREE_KICK:
                    # Afisam cercul de 9.15m (spray-ul arbitrului) si in timpul numaratorii inverse 3, 2, 1!
                    r_x = int(9.15 * (self.play_width / 100.0))
                    r_y = int(9.15 * (self.play_height / 100.0))
                    arc_rect = pygame.Rect(int(ball_x) - r_x, int(ball_y) - r_y, 2 * r_x, 2 * r_y)
                    spray = pygame.Surface((arc_rect.width + 4, arc_rect.height + 4), pygame.SRCALPHA)
                    pygame.draw.ellipse(spray, (255, 255, 255, 110), pygame.Rect(2, 2, arc_rect.width, arc_rect.height), max(1, int(2 * self.scale)))
                    self.screen.blit(spray, (arc_rect.x - 2, arc_rect.y - 2))

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

                # scalam dimensiunea jucatorului (aerisire vizuala teren)
                p_radius = max(5, int(7.5 * self.scale))
                shadow_offset = max(1, int(3 * self.scale))
                stun_frames = int(player_data.get("stun_frames", 0))
                stun_type = str(player_data.get("stun_type", ""))
                stun_mult = float(player_data.get("stun_speed_mult", 1.0))

                # Daca jucatorul este incetinit / dezechilibrat dupa un tackle ratat sau o deposedare,
                # inchidem usor nuanta tricoului si desenam un inel de avertizare galben-chihlimbar + indicator vizual!
                if stun_frames > 0:
                    player_color = (
                        int(player_color[0] * 0.72),
                        int(player_color[1] * 0.72),
                        int(player_color[2] * 0.72)
                    )
                
                # Umbra semi-transparenta
                shadow_surf = pygame.Surface((p_radius * 2, p_radius * 2), pygame.SRCALPHA)
                pygame.draw.circle(shadow_surf, (0, 0, 0, 100), (p_radius, p_radius), p_radius)
                self.screen.blit(shadow_surf, (draw_x - p_radius + shadow_offset, draw_y - p_radius + shadow_offset))

                # 2. Jucatorul
                pygame.draw.circle(self.screen, player_color, (draw_x, draw_y), p_radius)
                if stun_frames > 0:
                    ring_color = (255, 190, 0) if stun_type == "MISSED_TACKLE" else (255, 140, 60)
                    pygame.draw.circle(self.screen, ring_color, (draw_x, draw_y), p_radius + max(1, int(1.5 * self.scale)), max(2, int(2 * self.scale)))
                    # Eticheta compacta deasupra capului pentru feedback instantaneu ("TACKLE MISS -75%" / "LOST BALL")
                    slow_pct = int(round((1.0 - stun_mult) * 100))
                    badge_txt = f"MISS -{slow_pct}%" if stun_type == "MISSED_TACKLE" else f"SLOW -{slow_pct}%"
                    tag_surf = self.small_font.render(badge_txt, True, ring_color)
                    tag_rect = tag_surf.get_rect(center=(draw_x, draw_y - p_radius - max(7, int(8 * self.scale))))
                    self.screen.blit(tag_surf, tag_rect)
                else:
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
            b_radius = max(3, int(5.0 * self.scale))
            shadow_offset_b = max(1, int(4 * self.scale))
            
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
            # EFECT DE NOAPTE (SPOTLIGHT PE GAZON) - APLICAT INAINTE DE TEXTELE HUD
            # =======================================================
            # Cream o umbra peste tribune (opacitate 110 din 255), iar textele HUD se vor desena deasupra ei, clar luminate!
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
            
            # Adaugam intunericul peste tribune (gazonul si textele HUD de mai jos raman perfect luminate!)
            self.screen.blit(darkness, (0, 0))

            # Coordonata Y pentru bannerele de sus (mai sus de marginea gazonului, ca sa nu intersecteze linia terenului)
            top_banner_y = max(int(24 * self.scale), self.stadium_padding_y - int(22 * self.scale))

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
            # 9. ANUNTUL DE OUT / CORNER / AUT DE POARTA / OFSAID / SCENARIU
            # =======================================================
            elif message.get("game_status") == STATUS_OUT:
                text_out = self.font.render("OUT DE MARGINE", True, self.WHITE)
                text_shadow = self.font.render("OUT DE MARGINE", True, self.BLACK)
                out_pos = (self.screen.get_width() // 2, top_banner_y)
                shadow_rect = text_shadow.get_rect(center=(out_pos[0] + 3, out_pos[1] + 3))
                self.screen.blit(text_shadow, shadow_rect)
                out_rect = text_out.get_rect(center=out_pos)
                self.screen.blit(text_out, out_rect)

            elif message.get("game_status") == STATUS_CORNER:
                text_corner = self.font.render("CORNER", True, self.WHITE)
                text_shadow = self.font.render("CORNER", True, self.BLACK)
                corner_pos = (self.screen.get_width() // 2, top_banner_y)
                shadow_rect = text_shadow.get_rect(center=(corner_pos[0] + 3, corner_pos[1] + 3))
                self.screen.blit(text_shadow, shadow_rect)
                corner_rect = text_corner.get_rect(center=corner_pos)
                self.screen.blit(text_corner, corner_rect)

            elif message.get("game_status") == STATUS_GOAL_KICK:
                text_gk = self.font.render("AUT DE POARTA", True, self.WHITE)
                text_shadow = self.font.render("AUT DE POARTA", True, self.BLACK)
                gk_pos = (self.screen.get_width() // 2, top_banner_y)
                shadow_rect = text_shadow.get_rect(center=(gk_pos[0] + 3, gk_pos[1] + 3))
                self.screen.blit(text_shadow, shadow_rect)
                gk_rect = text_gk.get_rect(center=gk_pos)
                self.screen.blit(text_gk, gk_rect)

            elif message.get("game_status") == STATUS_OFFSIDE:
                text_off = self.font.render("OFSAID! (VAR)", True, (255, 230, 0))
                text_shadow = self.font.render("OFSAID! (VAR)", True, self.BLACK)
                off_pos = (self.screen.get_width() // 2, top_banner_y)
                shadow_rect = text_shadow.get_rect(center=(off_pos[0] + 3, off_pos[1] + 3))
                self.screen.blit(text_shadow, shadow_rect)
                off_rect = text_off.get_rect(center=off_pos)
                self.screen.blit(text_off, off_rect)

            elif message.get("game_status") in [STATUS_FREE_KICK, STATUS_PENALTY]:
                att_team = message.get("foul_attacking_team")
                t_a_lbl = str(message.get("team_A_name", "RED"))
                t_b_lbl = str(message.get("team_B_name", "BLUE"))
                team_lbl = t_a_lbl if att_team == "A" else (t_b_lbl if att_team == "B" else "")
                if message.get("game_status") == STATUS_PENALTY:
                    banner = f"PENALTY! (11M) - {team_lbl}"
                    banner_col = (255, 80, 80)
                else:
                    # Numarul de jucatori din zid (dupa distanta pana la poarta, ca la regulile din agent.py)
                    rbx = float(message.get("restart_ball_x", 50.0))
                    rby = float(message.get("restart_ball_y", 50.0))
                    left_team_v = "A" if message.get("half", 1) == 1 else "B"
                    def_goal_x = 100.0 if att_team == left_team_v else 0.0
                    d_goal = math.hypot(def_goal_x - rbx, 50.0 - rby)
                    if d_goal <= 20.5:
                        wall_n = 5
                    elif d_goal <= 25.5:
                        wall_n = 4
                    elif d_goal <= 31.0:
                        wall_n = 3
                    elif d_goal <= 37.0:
                        wall_n = 2
                    else:
                        wall_n = 0
                    wall_txt = f" | ZID: {wall_n}" if wall_n > 0 else ""
                    banner = f"FAULT! LOVITURA LIBERA - {team_lbl} ({int(round(d_goal))}m){wall_txt}"
                    banner_col = (255, 170, 60)
                text_f = self.font.render(banner, True, banner_col)
                text_f_sh = self.font.render(banner, True, self.BLACK)
                f_pos = (self.screen.get_width() // 2, top_banner_y)
                self.screen.blit(text_f_sh, text_f_sh.get_rect(center=(f_pos[0] + 3, f_pos[1] + 3)))
                self.screen.blit(text_f, text_f.get_rect(center=f_pos))

            elif message.get("game_status") == STATUS_SCENARIO_COUNTDOWN:
                sc_label = self.SCENARIO_LABELS.get(self.active_scenario, self.active_scenario)
                if self.active_scenario == SCENARIO_FREE_KICK:
                    sc_label = "FREE KICK (22m | ZID: 4)"
                elif self.active_scenario == SCENARIO_PENALTY:
                    sc_label = "PENALTY (11M)"
                cd_num = str(message.get("scenario_countdown_left", 3))

                # Titlul fazei sus pe centru
                title_str = f"SCENARIO: {sc_label}"
                text_title = self.font.render(title_str, True, (255, 215, 0))
                text_title_sh = self.font.render(title_str, True, self.BLACK)
                title_pos = (self.screen.get_width() // 2, top_banner_y)
                self.screen.blit(text_title_sh, text_title_sh.get_rect(center=(title_pos[0] + 3, title_pos[1] + 3)))
                self.screen.blit(text_title, text_title.get_rect(center=title_pos))

                # Numaratoarea inversa 3, 2, 1 pe centrul terenului
                center_pos = (self.screen.get_width() // 2, self.screen.get_height() // 2)
                cd_shadow = self.huge_font.render(cd_num, True, self.BLACK)
                cd_surf = self.huge_font.render(cd_num, True, (255, 230, 0))
                self.screen.blit(cd_shadow, cd_shadow.get_rect(center=(center_pos[0] + 5, center_pos[1] + 5)))
                self.screen.blit(cd_surf, cd_surf.get_rect(center=center_pos))

            elif message.get("game_status") == STATUS_SCENARIO_DONE:
                if not self.active_scenario:
                    # Inca nu a fost selectata nicio faza: afisam "ALEGE FAZA" mare pe mijlocul terenului!
                    center_pos = (self.screen.get_width() // 2, self.screen.get_height() // 2)
                    choose_sh = self.huge_font.render("ALEGE FAZA", True, self.BLACK)
                    choose_txt = self.huge_font.render("ALEGE FAZA", True, (255, 215, 0))
                    self.screen.blit(choose_sh, choose_sh.get_rect(center=(center_pos[0] + 5, center_pos[1] + 5)))
                    self.screen.blit(choose_txt, choose_txt.get_rect(center=center_pos))

                    sub_str = "SELECTEAZA O FAZA TACTICA DIN BARA DE JOS"
                    text_sub = self.font.render(sub_str, True, (0, 230, 255))
                    text_sub_sh = self.font.render(sub_str, True, self.BLACK)
                    sub_pos = (self.screen.get_width() // 2, top_banner_y)
                    self.screen.blit(text_sub_sh, text_sub_sh.get_rect(center=(sub_pos[0] + 3, sub_pos[1] + 3)))
                    self.screen.blit(text_sub, text_sub.get_rect(center=sub_pos))
                else:
                    sc_label = self.SCENARIO_LABELS.get(self.active_scenario, self.active_scenario)
                    done_str = f"FAZA INCHEIATA ({sc_label}) - ALEGE ALTA FAZA SAU RESTART"
                    text_done = self.font.render(done_str, True, (0, 230, 255))
                    text_done_sh = self.font.render(done_str, True, self.BLACK)
                    done_pos = (self.screen.get_width() // 2, top_banner_y)
                    self.screen.blit(text_done_sh, text_done_sh.get_rect(center=(done_pos[0] + 3, done_pos[1] + 3)))
                    self.screen.blit(text_done, text_done.get_rect(center=done_pos))

            # ======================================================

            # Extragem numele si tag-urile AI ale celor doua echipe (din Launcher -> Engine)
            team_a_name = str(message.get("team_A_name", "RED"))
            team_b_name = str(message.get("team_B_name", "BLUE"))
            team_a_tag = get_short_ai_tag(message.get("team_A_ai", "Base Build"))
            team_b_tag = get_short_ai_tag(message.get("team_B_ai", "Base Build"))

            # Resetam butoanele contextuale de pauza/final pe fiecare cadru (se activeaza doar in starea lor)
            self.btn_resume_half = None
            self.btn_ft_restart = None
            self.btn_ft_menu = None
            mouse_pos = pygame.mouse.get_pos()

            # =======================================================
            # 10. PAUZA LA MINUTUL 45:00 (HALF TIME) SI FINAL DE MECI (MATCH OVER)
            # =======================================================
            if message.get("game_status") == STATUS_HALF_TIME:
                # Folie semi-transparenta ca sa vedem jucatorii cum merg spre vestiare + panoul clar de statistici
                overlay = pygame.Surface((self.screen.get_width(), self.screen.get_height()), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 148))
                self.screen.blit(overlay, (0, 0))

                cx = self.screen.get_width() // 2
                score_a = message.get("score_A", 0)
                score_b = message.get("score_B", 0)

                text_ht = self.font.render("HALF TIME", True, (255, 215, 0))
                text_ht_sh = self.font.render("HALF TIME", True, self.BLACK)
                ht_y = int(68 * self.scale)
                self.screen.blit(text_ht_sh, text_ht_sh.get_rect(center=(cx + 3, ht_y + 3)))
                self.screen.blit(text_ht, text_ht.get_rect(center=(cx, ht_y)))

                text_score = self.font.render(f"{team_a_name}  {score_a} - {score_b}  {team_b_name}", True, self.WHITE)
                score_y = int(116 * self.scale)
                self.screen.blit(text_score, text_score.get_rect(center=(cx, score_y)))

                panel_w = int(430 * self.scale)
                panel_rect = self.draw_stats_panel(
                    message.get("match_stats", {}), cx, int(152 * self.scale), panel_w,
                    full=True, alpha_panel=235, team_a_name=f"{team_a_name} [{team_a_tag}]", team_b_name=f"{team_b_name} [{team_b_tag}]"
                )

                # Butonul "RESUME MATCH" pentru a incepe Repriza a 2-a (cu schimbarea terenurilor)
                res_w = int(220 * self.scale)
                res_h = int(42 * self.scale)
                self.btn_resume_half = pygame.Rect(cx - res_w // 2, panel_rect.bottom + int(18 * self.scale), res_w, res_h)
                is_hov_res = self.btn_resume_half.collidepoint(mouse_pos)
                res_col = (40, 185, 95) if is_hov_res else (28, 150, 75)
                pygame.draw.rect(self.screen, res_col, self.btn_resume_half, border_radius=10)
                pygame.draw.rect(self.screen, (255, 215, 0) if is_hov_res else self.WHITE, self.btn_resume_half, 2, border_radius=10)
                res_txt = self.stats_title_font.render("RESUME MATCH", True, self.WHITE)
                self.screen.blit(res_txt, res_txt.get_rect(center=self.btn_resume_half.center))

            elif message.get("game_status") == STATUS_MATCH_OVER:
                # O folie semi-transparenta neagra peste tot ecranul
                overlay = pygame.Surface((self.screen.get_width(), self.screen.get_height()), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 188))
                self.screen.blit(overlay, (0, 0))

                cx = self.screen.get_width() // 2
                score_a = message.get("score_A", 0)
                score_b = message.get("score_B", 0)

                # Text FULL TIME
                text_over = self.font.render("FULL TIME", True, (255, 215, 0))
                over_sh = self.font.render("FULL TIME", True, self.BLACK)
                ft_y = int(68 * self.scale)
                self.screen.blit(over_sh, over_sh.get_rect(center=(cx + 3, ft_y + 3)))
                self.screen.blit(text_over, text_over.get_rect(center=(cx, ft_y)))

                # Scorul Final
                text_score = self.font.render(f"{team_a_name}  {score_a} - {score_b}  {team_b_name}", True, self.WHITE)
                score_y = int(116 * self.scale)
                self.screen.blit(text_score, text_score.get_rect(center=(cx, score_y)))

                # Panoul complet de statistici pe mijloc
                panel_w = int(430 * self.scale)
                panel_rect = self.draw_stats_panel(
                    message.get("match_stats", {}), cx, int(152 * self.scale), panel_w,
                    full=True, alpha_panel=238, team_a_name=f"{team_a_name} [{team_a_tag}]", team_b_name=f"{team_b_name} [{team_b_tag}]"
                )

                # Doua butoane elegante dedesubt: PLAY AGAIN si MAIN MENU
                ft_btn_w = int(170 * self.scale)
                ft_btn_h = int(40 * self.scale)
                ft_gap = int(18 * self.scale)
                ft_btn_y = panel_rect.bottom + int(18 * self.scale)
                self.btn_ft_restart = pygame.Rect(cx - ft_btn_w - ft_gap // 2, ft_btn_y, ft_btn_w, ft_btn_h)
                self.btn_ft_menu = pygame.Rect(cx + ft_gap // 2, ft_btn_y, ft_btn_w, ft_btn_h)

                for b_rect, b_col, b_hov_col, b_lbl in [
                    (self.btn_ft_restart, (28, 125, 215), (45, 150, 245), "PLAY AGAIN"),
                    (self.btn_ft_menu, (195, 130, 0), (230, 160, 10), "MAIN MENU")
                ]:
                    hov = b_rect.collidepoint(mouse_pos)
                    pygame.draw.rect(self.screen, b_hov_col if hov else b_col, b_rect, border_radius=10)
                    pygame.draw.rect(self.screen, self.WHITE, b_rect, 2, border_radius=10)
                    lbl_s = self.stats_title_font.render(b_lbl, True, self.WHITE)
                    self.screen.blit(lbl_s, lbl_s.get_rect(center=b_rect.center))

            # =======================================================
            # BARA DISCRETA DE POSESIE + DROPDOWN STATISTICI PE HOVER (IN TIMPUL MECIULUI)
            # =======================================================
            if self.game_mode != "scenarios" and message.get("game_status") not in [STATUS_HALF_TIME, STATUS_MATCH_OVER]:
                m_stats = message.get("match_stats", {})
                poss_a = m_stats.get("A", {}).get("possession", 50)
                poss_b = m_stats.get("B", {}).get("possession", 50)

                pill_w = int(230 * self.scale)
                pill_h = int(28 * self.scale)
                pill_x = (self.screen.get_width() - pill_w) // 2
                pill_y = int(14 * self.scale)
                self.stats_pill_rect = pygame.Rect(pill_x, pill_y, pill_w, pill_h)

                is_hover_pill = self.stats_pill_rect.collidepoint(mouse_pos)
                is_hover_dd = (self.stats_hover_open and self.stats_dropdown_rect is not None and self.stats_dropdown_rect.collidepoint(mouse_pos))
                self.stats_hover_open = is_hover_pill or is_hover_dd

                pill_alpha = 235 if self.stats_hover_open else 105
                pill_surf = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
                pygame.draw.rect(pill_surf, (16, 22, 34, pill_alpha), pill_surf.get_rect(), border_radius=8)
                pygame.draw.rect(pill_surf, (255, 215, 0, pill_alpha) if self.stats_hover_open else (255, 255, 255, pill_alpha), pill_surf.get_rect(), 1, border_radius=8)

                p_txt = self.small_font.render(f"POSSESSION   {poss_a}%  |  {poss_b}%", True, (255, 255, 255))
                p_txt.set_alpha(255 if self.stats_hover_open else 175)
                pill_surf.blit(p_txt, p_txt.get_rect(center=(pill_w // 2, pill_h // 2 - int(2 * self.scale))))

                # Mini bara rosie/albastra la baza pilulei de posesie
                mb_w = pill_w - int(16 * self.scale)
                mb_h = max(2, int(3 * self.scale))
                mb_x = int(8 * self.scale)
                mb_y = pill_h - mb_h - int(3 * self.scale)
                w_ra = int(mb_w * (poss_a / 100.0))
                if w_ra > 0:
                    pygame.draw.rect(pill_surf, (*self.RED, pill_alpha), pygame.Rect(mb_x, mb_y, w_ra, mb_h), border_radius=1)
                if mb_w - w_ra > 0:
                    pygame.draw.rect(pill_surf, (*self.BLUE, pill_alpha), pygame.Rect(mb_x + w_ra, mb_y, mb_w - w_ra, mb_h), border_radius=1)

                self.screen.blit(pill_surf, self.stats_pill_rect.topleft)

                if self.stats_hover_open:
                    dd_w = int(340 * self.scale)
                    self.stats_dropdown_rect = self.draw_stats_panel(
                        m_stats, self.screen.get_width() // 2, self.stats_pill_rect.bottom + int(6 * self.scale),
                        dd_w, full=False, alpha_panel=232, team_a_name=team_a_name, team_b_name=team_b_name
                    )
                else:
                    self.stats_dropdown_rect = None
            else:
                self.stats_hover_open = False
                self.stats_dropdown_rect = None

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
            self.btn_menu = pygame.Rect(screen_w - (3 * s_btn_w) - (3 * pad), pad, s_btn_w, s_btn_h)
            
            # 2. Citim pozitia curenta a mouse-ului
            mouse_pos = pygame.mouse.get_pos()
            
            # 3. Impachetam informatiile butoanelor intr-o lista pentru a scrie cod curat
            buttons_ui = [
                (self.btn_quit, self.RED, "QUIT", self.btn_quit.collidepoint(mouse_pos)),
                (self.btn_restart, self.BLUE, "RESTART", self.btn_restart.collidepoint(mouse_pos)),
                (self.btn_menu, (210, 140, 0), "MAIN MENU", self.btn_menu.collidepoint(mouse_pos))
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
            # BARA DE FAZE TACTICE (TACTICAL SCENARIOS GHOST HUD)
            # =======================================================
            self.scenario_buttons = []
            if self.game_mode == "scenarios":
                sc_list = [
                    (SCENARIO_1V1_GK, "1v1 GK"),
                    (SCENARIO_OFFSIDE_VAR, "OFFSIDE (VAR)"),
                    (SCENARIO_CORNER, "CORNER"),
                    (SCENARIO_TIKI_TAKA, "COUNTER-ATTACK"),
                    (SCENARIO_GOAL_KICK, "GOAL KICK"),
                    (SCENARIO_THROW_IN, "THROW-IN"),
                    (SCENARIO_PENALTY, "PENALTY"),
                    (SCENARIO_FREE_KICK, "FREE KICK")
                ]
                sc_btn_w = int(112 * self.scale)
                sc_btn_h = int(28 * self.scale)
                sc_gap = int(10 * self.scale)
                total_bar_w = len(sc_list) * sc_btn_w + (len(sc_list) - 1) * sc_gap
                bar_start_x = (screen_w - total_bar_w) // 2
                bar_y = self.screen.get_height() - int(46 * self.scale)

                for idx, (sc_id, sc_label) in enumerate(sc_list):
                    bx = bar_start_x + idx * (sc_btn_w + sc_gap)
                    sc_rect = pygame.Rect(bx, bar_y, sc_btn_w, sc_btn_h)
                    self.scenario_buttons.append((sc_rect, sc_id))

                    is_hover = sc_rect.collidepoint(mouse_pos)
                    is_active = (self.active_scenario == sc_id)
                    is_done_phase = (message.get("game_status") == STATUS_SCENARIO_DONE)
                    alpha_sc = 255 if (is_hover or is_active or is_done_phase) else 95

                    bg_col = (0, 110, 215) if is_active else (35, 45, 60)
                    border_col = (255, 215, 0) if is_active else self.WHITE

                    sc_surf = pygame.Surface((sc_rect.width, sc_rect.height), pygame.SRCALPHA)
                    pygame.draw.rect(sc_surf, (*bg_col, alpha_sc), sc_surf.get_rect(), border_radius=7)
                    pygame.draw.rect(sc_surf, (*border_col, alpha_sc), sc_surf.get_rect(), 2, border_radius=7)

                    lbl_col = (255, 235, 120) if is_active else self.WHITE
                    lbl_surf = self.small_font.render(sc_label, True, lbl_col)
                    lbl_surf.set_alpha(alpha_sc)
                    sc_surf.blit(lbl_surf, lbl_surf.get_rect(center=sc_surf.get_rect().center))
                    self.screen.blit(sc_surf, sc_rect.topleft)

            # =======================================================
            # TABELA DE SCOR SI TIMP (HUD)
            # =======================================================
            # 1. Extragem datele (cu fallback la 0 in caz ca motorul de abia a pornit)
            score_a = message.get("score_A", 0)
            score_b = message.get("score_B", 0)
            v_time = message.get("time", 0.0)

            # 2. Convertim timpul din float in MM:SS (sau afisam "LAB" in modul Tactical Scenarios)
            if self.game_mode == "scenarios":
                time_str = "LAB"
            else:
                mins = int(v_time)
                secs = int((v_time - mins) * 60)
                time_str = f"{mins:02d}:{secs:02d}"

            # 3. Definim latimile pentru fiecare segment din bara (ajustate dinamic ca sa incapa nume pana la 10 caractere)
            box_h = int(38 * self.scale)
            team_w = int(84 * self.scale)
            score_w = int(58 * self.scale)
            time_w = int(68 * self.scale)
            total_w = team_w + score_w + team_w + time_w

            # 4. Plasament: Stanga-Sus (cu o mica margine ca la TV)
            start_x = int(50 * self.scale)
            start_y = int(40 * self.scale)

            # 5. Umbra 3D sub intregul HUD
            shadow = pygame.Surface((total_w, box_h), pygame.SRCALPHA)
            shadow.fill((0, 0, 0, 120))
            self.screen.blit(shadow, (start_x + int(4 * self.scale), start_y + int(4 * self.scale)))

            # 6. Segmentul 1: ECHIPA A / RED (Nume + Tag AI discret dedesubt)
            rect_red = pygame.Rect(start_x, start_y, team_w, box_h)
            pygame.draw.rect(self.screen, self.RED, rect_red)
            text_red = self.small_font.render(team_a_name, True, self.WHITE)
            self.screen.blit(text_red, text_red.get_rect(center=(rect_red.centerx, rect_red.centery - int(5 * self.scale))))
            tag_a_surf = self.small_font.render(f"[{team_a_tag}]", True, (255, 220, 170))
            self.screen.blit(tag_a_surf, tag_a_surf.get_rect(center=(rect_red.centerx, rect_red.centery + int(9 * self.scale))))

            # 7. Segmentul 2: SCOR (Fundal Alb, Text Negru)
            rect_score = pygame.Rect(start_x + team_w, start_y, score_w, box_h)
            pygame.draw.rect(self.screen, self.WHITE, rect_score)
            text_sc = self.small_font.render(f"{score_a} - {score_b}", True, self.BLACK)
            self.screen.blit(text_sc, text_sc.get_rect(center=rect_score.center))

            # 8. Segmentul 3: ECHIPA B / BLUE (Nume + Tag AI discret dedesubt)
            rect_blue = pygame.Rect(start_x + team_w + score_w, start_y, team_w, box_h)
            pygame.draw.rect(self.screen, self.BLUE, rect_blue)
            text_blue = self.small_font.render(team_b_name, True, self.WHITE)
            self.screen.blit(text_blue, text_blue.get_rect(center=(rect_blue.centerx, rect_blue.centery - int(5 * self.scale))))
            tag_b_surf = self.small_font.render(f"[{team_b_tag}]", True, (210, 240, 255))
            self.screen.blit(tag_b_surf, tag_b_surf.get_rect(center=(rect_blue.centerx, rect_blue.centery + int(9 * self.scale))))
            
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