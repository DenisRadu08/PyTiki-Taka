from config import STATE_KICK
from config import STATE_CHASE
from config import STATE_IDLE
import zmq
import json
import math
import random
from config import *

class PlayerAgent:
    def __init__(self, agent_id, team):
        self.x = 0.0
        self.y = 0.0
        self.start_x = self.x
        self.start_y = self.y
        self.state = STATE_IDLE
        self.agent_id=agent_id
        self.team = team
        self.last_logged_state = None
        self.stun_frames = 0
        self.duel_frames = 0
        self.ignore_ball_frames = 0
        self.deadlock_frames = 0
        self.attack_high_x = None
        self.give_and_go_x = None
        self.give_and_go_y = None
        self.last_passer_id = None
        self.one_two_window_frames = 0
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

    def get_restart_position(self, ball_x, ball_y, has_restart):
        """
        Calculam pozitia tactica ideala pentru faza fixa de AUT DE MARGINE:
        - Fiecare jucator primeste o pozitie UNICA si aerisita, eliminand suprapunerea (clumping)
        - Echipa care bate (has_restart = True): triunghi scurt pe margine, optiune in adancime, pivot central si rest defense
        - Echipa care apara (has_restart = False): marcaj individual pe optiuni (goal-side) si bloc compact
        """
        attack_dir = 1.0 if float(self.start_x) < 50.0 else -1.0
        is_ball_top = (ball_y < 50.0)

        def inward_y(offset):
            # offset pozitiv fata de tusa pe care se bate autul
            return offset if is_ball_top else (100.0 - offset)

        try:
            player_num = int(self.agent_id) % 100
        except ValueError:
            player_num = 10

        # Identificam daca jucatorul provine natural de pe flancul autului
        is_flank_player = (self.start_y < 35.0) if is_ball_top else (self.start_y > 65.0)
        is_central_player = (35.0 <= self.start_y <= 65.0)

        if has_restart:
            # ----------------------------------------------------
            # ECHIPA IN ATAC (ARE AUTUL) - SPATIERE TACTICA AERISITA
            # ----------------------------------------------------
            if player_num in [11, 9] and is_flank_player:
                # 1. Extrema de pe banda autului: sprijin scurt pe linie la 5 metri
                tx = ball_x + attack_dir * 5.0
                ty = inward_y(6.0)
            elif player_num in [8, 6, 107, 106] and is_flank_player:
                # 2. Mijlocasul de pe banda: optiune diagonala in interior (varf de triunghi)
                tx = ball_x - attack_dir * 3.5
                ty = inward_y(19.0)
            elif player_num in [5, 2, 105, 102] and is_flank_player:
                # 3. Fundasul lateral de pe banda autului: siguranta in spate pentru repunere
                tx = ball_x - attack_dir * 11.0
                ty = inward_y(8.0)
            elif player_num in [10, 110, 111]:
                # 4. Atacantul central: atac pe culoar in adancime
                tx = ball_x + attack_dir * 15.0
                ty = inward_y(15.0)
            elif player_num in [7]:
                # 5. Mijlocasul central: pivot pentru schimbarea directiei
                tx = ball_x - attack_dir * 5.0
                ty = inward_y(38.0)
            elif player_num in [3, 4, 103, 104]:
                # 6. Fundasii centrali: siguranta defensiva la mijloc (rest defense)
                cb_offset_y = 42.0 if player_num in [3, 103] else 58.0
                tx = ball_x - attack_dir * 18.0
                ty = cb_offset_y
            else:
                # 7. Jucatorii de pe flancul opus: tin latimea si adancimea terenului pe partea opusa
                tx = ball_x + (attack_dir * 4.0 if player_num in [9, 11] else -attack_dir * 6.0)
                ty = inward_y(65.0 if is_central_player else 80.0)
        else:
            # ----------------------------------------------------
            # ECHIPA IN APARARE - MARCAJ INDIVIDUAL STRANS SI AERISIT
            # ----------------------------------------------------
            if player_num in [11, 9] and is_flank_player:
                # Marcaj pe extrema care cere scurt (intre ea si poarta)
                tx = ball_x + attack_dir * 3.0
                ty = inward_y(8.0)
            elif player_num in [8, 6, 107, 106] and is_flank_player:
                # Marcaj pe mijlocasul din diagonala
                tx = ball_x - attack_dir * 1.5
                ty = inward_y(21.0)
            elif player_num in [5, 2, 105, 102] and is_flank_player:
                # Blocaj pe flanc in spatele aruncatorului
                tx = ball_x - attack_dir * 8.0
                ty = inward_y(10.0)
            elif player_num in [10, 110, 111]:
                # Atacantul advers ramane avansat pentru contraatac
                tx = 50.0 + attack_dir * 4.0
                ty = inward_y(30.0)
            elif player_num in [7]:
                # Ecran central la mijloc
                tx = ball_x - attack_dir * 3.5
                ty = inward_y(36.0)
            elif player_num in [3, 4, 103, 104]:
                # Fundasii centrali acopera axul central
                cb_def_y = 44.0 if player_num in [3, 103] else 56.0
                tx = ball_x - attack_dir * 14.0
                ty = cb_def_y
            else:
                # Acoperire pe flancul opus
                tx = ball_x - attack_dir * 8.0
                ty = inward_y(68.0 if is_central_player else 82.0)

        # ramanem pe teren
        tx = max(4.0, min(96.0, tx))
        ty = max(4.0, min(96.0, ty))
        return tx, ty

    def get_corner_position(self, ball_x, ball_y, has_restart):
        """
        Pozitionare tactica la corner:
        - in atac (has_restart = True): 1-2 fundasi raman la mijloc, restul echipei aglomereaza careul de 16m
        - in aparare (has_restart = False): toata echipa se strange in propriul careu in fata portii
        """
        attack_dir = 1.0 if float(self.start_x) < 50.0 else -1.0
        own_goal_x = 0.0 if attack_dir > 0 else 100.0
        target_goal_x = 100.0 if attack_dir > 0 else 0.0

        try:
            player_num = int(self.agent_id) % 100
        except ValueError:
            player_num = 5

        if has_restart:
            # Fiecare rol primeste o pozitie UNICA in careu / la mijloc (fara suprapunere!)
            if player_num == 2:
                tx = 50.0 - attack_dir * 6.0
                ty = 72.0
            elif player_num == 3:
                tx = 50.0 - attack_dir * 6.0
                ty = 28.0
            elif player_num == 4:
                # Prima bara (6m)
                tx = target_goal_x - attack_dir * 6.5
                ty = 43.0 if ball_y < 50.0 else 57.0
            elif player_num == 5:
                # Marginea careului lateral-apropiat (optiune corner scurt)
                tx = target_goal_x - attack_dir * 13.0
                ty = 22.0 if ball_y < 50.0 else 78.0
            elif player_num == 6:
                # Semicercul de 16m (dreapta)
                tx = target_goal_x - attack_dir * 18.0
                ty = 58.0
            elif player_num == 7:
                # Semicercul de 16m (stanga)
                tx = target_goal_x - attack_dir * 18.0
                ty = 42.0
            elif player_num == 8:
                # Punctul cu var (11m)
                tx = target_goal_x - attack_dir * 11.5
                ty = 48.0
            elif player_num == 9:
                # Bara a doua (9m)
                tx = target_goal_x - attack_dir * 8.5
                ty = 57.5 if ball_y < 50.0 else 42.5
            elif player_num == 10:
                # Atacant central (8m pe centru)
                tx = target_goal_x - attack_dir * 8.0
                ty = 50.0
            else:
                # Extrema opusa (13m la coltul lung)
                tx = target_goal_x - attack_dir * 12.5
                ty = 63.0 if ball_y < 50.0 else 37.0
        else:
            # Apararea la corner: fiecare aparator are un post unic in careu sau la respingere
            if player_num == 2:
                tx = own_goal_x + attack_dir * 5.5
                ty = 43.5 if ball_y < 50.0 else 56.5
            elif player_num == 3:
                tx = own_goal_x + attack_dir * 6.5
                ty = 48.5
            elif player_num == 4:
                tx = own_goal_x + attack_dir * 6.5
                ty = 52.5
            elif player_num == 5:
                tx = own_goal_x + attack_dir * 8.0
                ty = 56.5 if ball_y < 50.0 else 43.5
            elif player_num == 6:
                tx = own_goal_x + attack_dir * 11.0
                ty = 45.0
            elif player_num == 7:
                tx = own_goal_x + attack_dir * 11.0
                ty = 55.0
            elif player_num == 8:
                tx = own_goal_x + attack_dir * 15.5
                ty = 43.0 if ball_y < 50.0 else 57.0
            elif player_num == 9:
                tx = own_goal_x + attack_dir * 17.5
                ty = 50.0
            elif player_num == 10:
                # Varful ramane avansat pentru contraatac
                tx = own_goal_x + attack_dir * 38.0
                ty = 50.0
            else:
                tx = own_goal_x + attack_dir * 26.0
                ty = 34.0 if ball_y < 50.0 else 66.0

        tx = max(3.0, min(97.0, tx))
        ty = max(3.0, min(97.0, ty))
        return tx, ty

    def get_goal_kick_position(self, ball_x, ball_y, has_restart):
        """
        Pozitionare tactica la aut de poarta:
        - echipa portarului: fundasii centrali deschid careul de 16m pentru constructie scurta,
          fundasii laterali urca pe tusa, mijlocasii si atacantii urca progresiv.
        - echipa adversa: bloc de pressing avansat/mediu esalonat pe mai multe linii (nu gard plat).
        """
        attack_dir = 1.0 if float(self.start_x) < 50.0 else -1.0
        own_goal_x = 0.0 if attack_dir > 0 else 100.0

        try:
            player_num = int(self.agent_id) % 100
        except ValueError:
            player_num = 10

        if has_restart:
            # Echipa noastra are aut de poarta (deschidem jocul scurt sau lung):
            if player_num in [3, 103]:
                # Fundas central 1 (deschide careul dreapta)
                tx = own_goal_x + attack_dir * 14.0
                ty = 65.0
            elif player_num in [4, 104]:
                # Fundas central 2 (deschide careul stanga)
                tx = own_goal_x + attack_dir * 14.0
                ty = 35.0
            elif player_num in [2, 102]:
                # Fundas dreapta urca pe banda
                tx = own_goal_x + attack_dir * 28.0
                ty = 88.0
            elif player_num in [5, 105]:
                # Fundas stanga urca pe banda
                tx = own_goal_x + attack_dir * 28.0
                ty = 12.0
            elif player_num == 7:
                # Mijlocas central defensiv (solutie centrala)
                tx = own_goal_x + attack_dir * 36.0
                ty = 50.0
            elif player_num in [6, 106]:
                # Mijlocas dreapta
                tx = own_goal_x + attack_dir * 42.0
                ty = 75.0
            elif player_num in [8, 107]:
                # Mijlocas stanga
                tx = own_goal_x + attack_dir * 42.0
                ty = 25.0
            elif player_num in [9, 108]:
                # Extrema dreapta sus
                tx = own_goal_x + attack_dir * 58.0
                ty = 75.0
            elif player_num in [11, 109]:
                # Extrema stanga sus
                tx = own_goal_x + attack_dir * 58.0
                ty = 25.0
            else:
                # Atacant central (10, 110, 111)
                tx = own_goal_x + attack_dir * 62.0
                ty = 50.0
        else:
            # Adversarii au aut de poarta - bloc de pressing esalonat:
            if player_num in [10, 11, 9, 110, 111]:
                # Atacantii preseaza la marginea careului de 16m
                tx = own_goal_x + attack_dir * 78.0
                ty = self.start_y
            elif player_num in [6, 7, 8, 106, 107, 108, 109]:
                # Mijlocasii se asaza la 10m dupa mijlocul terenului
                tx = own_goal_x + attack_dir * 56.0
                ty = self.start_y
            else:
                # Linia defensiva se asaza la 35m de propria poarta
                tx = own_goal_x + attack_dir * 35.0
                ty = self.start_y

        tx = max(4.0, min(96.0, tx))
        ty = max(4.0, min(96.0, ty))
        return tx, ty

    def calculate_pass_intercept(self, ball_x, ball_y, vx, vy):
        """
        Calculeaza punctul optim de intalnire / atacare a mingii in zbor
        pe baza proiectiei geometrice pe traiectoria mingii.
        """
        ball_speed = math.hypot(vx, vy)
        if ball_speed < 0.15:
            return ball_x, ball_y
        nx = vx / ball_speed
        ny = vy / ball_speed
        dx = self.x - ball_x
        dy = self.y - ball_y
        proj = dx * nx + dy * ny
        if proj > 0.0:
            # Mingea vine spre noi: taiem calea direct pe linia pasei
            lead_along_line = max(0.0, proj * 0.72)
            intercept_x = ball_x + nx * lead_along_line
            intercept_y = ball_y + ny * lead_along_line
        else:
            # Mingea ne-a depasit sau merge in fata: urmarim punctul unde se opreste
            dist = math.hypot(dx, dy)
            t_intercept = min(14.0, dist / (ball_speed + 0.85))
            intercept_x = ball_x + vx * t_intercept
            intercept_y = ball_y + vy * t_intercept
        intercept_x = max(2.0, min(98.0, intercept_x))
        intercept_y = max(2.0, min(98.0, intercept_y))
        return intercept_x, intercept_y

    def find_open_support_spot(self, base_tx, base_ty, ball_x, ball_y, attack_dir, message):
        """
        Demarcare inteligenta din umbra de marcaj ("cover shadow"):
        Daca un adversar blocheaza linia de pasa dintre minge si pozitia noastra tinta
        sau sta prea aproape de noi, cautam o fereastra de pasa libera (venire la primire,
        atacarea spatiului in adancime sau deschidere laterala).
        """
        def evaluate_spot(cx, cy):
            cx = max(3.0, min(97.0, cx))
            cy = max(3.0, min(97.0, cy))
            dx_b = cx - ball_x
            dy_b = cy - ball_y
            dist_b = math.hypot(dx_b, dy_b)
            if dist_b < 0.1:
                return -999.0, False
            nx_b = dx_b / dist_b
            ny_b = dy_b / dist_b

            min_opp_dist = 99.0
            lane_blocked = False
            for opp_id, opp_data in message["players"].items():
                if opp_data["team"] != self.team and opp_data["stun_frames"] == 0:
                    d_opp = math.hypot(opp_data["x"] - cx, opp_data["y"] - cy)
                    if d_opp < min_opp_dist:
                        min_opp_dist = d_opp
                    # Verificam daca adversarul se afla pe linia de pasa dintre minge si (cx, cy)
                    dx_o = opp_data["x"] - ball_x
                    dy_o = opp_data["y"] - ball_y
                    proj = dx_o * nx_b + dy_o * ny_b
                    if 0.5 < proj < dist_b - 0.3:
                        perp = abs(dx_o * ny_b - dy_o * nx_b)
                        if perp < 1.35 + proj * 0.08:
                            lane_blocked = True

            min_team_dist = 99.0
            for tm_id, tm_data in message["players"].items():
                if tm_data["team"] == self.team and str(tm_id) != str(self.agent_id) and tm_data["stun_frames"] == 0:
                    if str(tm_id) == str(message.get("possession")):
                        continue
                    d_tm = math.hypot(tm_data["x"] - cx, tm_data["y"] - cy)
                    if d_tm < min_team_dist:
                        min_team_dist = d_tm

            score = 0.0
            if not lane_blocked:
                score += 85.0
            score += min(min_opp_dist, 9.0) * 6.5
            if min_team_dist < 6.0:
                score -= (6.0 - min_team_dist) * 10.0
            # Preferam o distanta optima de combinatie (10m - 16m) fata de purtatorul mingii
            score -= abs(dist_b - 13.0) * 1.4
            # Continuitate fina fata de pozitia de baza si pozitia curenta (fara tremurat)
            score -= math.hypot(cx - base_tx, cy - base_ty) * 1.2
            score -= math.hypot(cx - self.x, cy - self.y) * 0.35
            return score, (not lane_blocked and min_opp_dist >= 3.8)

        base_score, is_clean = evaluate_spot(base_tx, base_ty)
        if is_clean:
            return max(3.0, min(97.0, base_tx)), max(3.0, min(97.0, base_ty))

        # Testam variante de demarcare: venire la pasa (check-in), plecare in adancime, demarcare laterala
        candidates = [
            (base_tx, base_ty),
            (base_tx - attack_dir * 4.5, base_ty - 4.5),  # venire la pasa stanga/sus
            (base_tx - attack_dir * 4.5, base_ty + 4.5),  # venire la pasa dreapta/jos
            (base_tx - attack_dir * 5.5, base_ty),        # venire scurta la primire
            (base_tx + attack_dir * 5.5, base_ty - 4.0),  # sprint pe culoar in adancime
            (base_tx + attack_dir * 5.5, base_ty + 4.0),  # sprint pe culoar in adancime
            (base_tx, base_ty - 6.5),                     # iesire laterala din umbra de marcaj
            (base_tx, base_ty + 6.5),                     # iesire laterala din umbra de marcaj
        ]

        best_x, best_y = base_tx, base_ty
        best_score = base_score
        for cx, cy in candidates[1:]:
            sc, _ = evaluate_spot(cx, cy)
            if sc > best_score:
                best_score = sc
                best_x = max(3.0, min(97.0, cx))
                best_y = max(3.0, min(97.0, cy))

        return best_x, best_y

    def compute_attack_support_target(self, message):
        """
        Sistem dinamic de sustinere a atacului (Tiki-Taka & Combinatii in Fotbalul Real):
        1. Mentine linia ofensiva (effective_ball_x) astfel incat la o pasa scurta inapoi echipa NU da inapoi in cascada!
        2. Dupa o pasa data (ignore_ball_frames > 0), pasatorul face sprint "Un-Doi" (Give-and-Go) pe spatiu liber!
        3. Cand varful (10) sau o extrema (9/11) are mingea, colegii ataca diagonalele, half-space-ul si flancurile!
        """
        attack_dir = 1.0 if float(self.start_x) < 50.0 else -1.0
        opponent_goal_x = 100.0 if attack_dir > 0 else 0.0
        ball_x = message["ball"]["x"]
        ball_y = message["ball"]["y"]

        # Linia progresiva a atacului: impiedica retragerea in bloc cand se joaca o pasa de sprijin in spate
        if self.attack_high_x is None:
            effective_ball_x = ball_x
        elif attack_dir > 0:
            effective_ball_x = max(ball_x, min(self.attack_high_x, ball_x + 9.0))
        else:
            effective_ball_x = min(ball_x, max(self.attack_high_x, ball_x - 9.0))

        dist_ball_to_opp_goal = abs(opponent_goal_x - effective_ball_x)

        try:
            player_num = int(self.agent_id) % 100
        except ValueError:
            player_num = 10

        # Identificam ce numar/rol are colegul care detine sau primeste mingea
        poss_num = None
        active_carrier_id = message.get("possession") or message.get("intended_receiver")
        if active_carrier_id is not None and str(active_carrier_id) in message["players"]:
            if message["players"][str(active_carrier_id)]["team"] == self.team:
                try:
                    poss_num = int(active_carrier_id) % 100
                except ValueError:
                    poss_num = None

        # =========================================================================
        # 0. SPRINT "UN-DOI" (GIVE-AND-GO): Daca tocmai am pasat, atacam spatiul in fata!
        # =========================================================================
        if self.ignore_ball_frames > 0 and player_num not in [3, 4] and self.give_and_go_x is not None and self.give_and_go_y is not None:
            target_x, target_y = self.give_and_go_x, self.give_and_go_y
        
        # =========================================================================
        # 1. ATACANTII SI EXTREMELE (9, 10, 11): Demarcari in diagonala, sprijin si atacarea careului
        # =========================================================================
        elif player_num == 10:
            # Varful central (10):
            if poss_num in [9, 11, 2, 5]:
                # Mingea e pe flanc la extrema/fundas lateral -> Varful ataca agresiv zona de 9-11m din fata portii!
                target_x = effective_ball_x + attack_dir * 9.5
                target_y = 50.0 + (ball_y - 50.0) * 0.30
            elif dist_ball_to_opp_goal > 38.0:
                # Mingea e la constructie la mijloc/fundasi -> Varful VINE LA PASA intre linii (sprijin la 10.5m)!
                target_x = effective_ball_x + attack_dir * 10.5
                target_y = 50.0 + (ball_y - 50.0) * 0.45
            else:
                # In treimea adversa -> Varful ataca adancimea spre punctul cu var
                target_x = effective_ball_x + attack_dir * 12.0
                target_y = 50.0 + (ball_y - 50.0) * 0.25

            if attack_dir > 0:
                target_x = max(46.0, min(91.5, target_x))
            else:
                target_x = min(54.0, max(8.5, target_x))

        elif player_num in [9, 11]:
            # Extremele: 9 (dreapta/jos y > 50), 11 (stanga/sus y < 50)
            is_right_wing = (player_num == 9)
            is_ball_my_side = (ball_y >= 48.0) if is_right_wing else (ball_y <= 52.0)

            if poss_num == 10:
                # VARFUL (10) ARE MINGEA! Extremele NU stau izolate pe tusa miscandu-se doar pe OY,
                # ci taie in diagonala spre careu si spre varf pentru combinatii rapide si 1-2!
                if is_ball_my_side:
                    target_x = effective_ball_x + attack_dir * 9.5
                    target_y = min(72.0, max(58.0, ball_y + 12.0)) if is_right_wing else max(28.0, min(42.0, ball_y - 12.0))
                else:
                    target_x = effective_ball_x + attack_dir * 12.0
                    target_y = 63.0 if is_right_wing else 37.0
            elif is_ball_my_side:
                # Mingea e pe flancul meu (la mijlocas/fundas) -> Sprint rapid pe flanc in adancime, apoi taiere spre careu!
                target_x = effective_ball_x + attack_dir * 12.5
                if dist_ball_to_opp_goal > 24.0:
                    target_y = 79.0 if is_right_wing else 21.0
                else:
                    target_y = 64.0 if is_right_wing else 36.0
            else:
                # Mingea e pe flancul opus -> Extrema opusa strange in interior la bara a doua / half-space!
                target_x = effective_ball_x + attack_dir * 11.5
                target_y = 62.0 if is_right_wing else 38.0

            if attack_dir > 0:
                target_x = max(45.0, min(92.0, target_x))
            else:
                target_x = min(55.0, max(8.0, target_x))

        # =========================================================================
        # 2. MIJLOCASII (6, 7, 8): Urari in half-space, combinatii 1-2 cu varful si acoperire
        # =========================================================================
        elif player_num in [6, 7, 8]:
            if player_num == 7:
                # Mijlocasul central (Pivot Tiki-Taka): vine aproape in sprijin (6.5m in spatele liniei mingii)
                target_x = effective_ball_x - attack_dir * 6.5
                target_y = 50.0 + (ball_y - 50.0) * 0.45
                if attack_dir > 0:
                    target_x = max(26.0, min(78.0, target_x))
                else:
                    target_x = min(74.0, max(22.0, target_x))
            else:
                # Interii ofensivi: 6 (dreapta y > 50), 8 (stanga y < 50)
                is_right_mid = (player_num == 6)
                is_ball_my_side = (ball_y >= 50.0) if is_right_mid else (ball_y < 50.0)

                if poss_num in [9, 10, 11]:
                    # Un atacant are mingea! Interul NU ramane in spate, ci URCA in fata mingii (+4.5m..+6.5m)
                    # in half-space pentru a oferi optiune de pasa inainte / un-doi (1-2) sau sut!
                    if is_ball_my_side:
                        target_x = effective_ball_x + attack_dir * 4.5
                        if is_right_mid:
                            target_y = ball_y - 10.5 if ball_y > 66.0 else min(76.0, ball_y + 10.5)
                        else:
                            target_y = ball_y + 10.5 if ball_y < 34.0 else max(24.0, ball_y - 10.5)
                    else:
                        # Interul de pe partea opusa ataca central-ofensiv careul advers (+6.5m)!
                        target_x = effective_ball_x + attack_dir * 6.5
                        target_y = 56.0 if is_right_mid else 44.0
                else:
                    # Mingea e la fundasi sau la alt mijlocas -> Interii se demarca intre linii in fata mingii!
                    if is_ball_my_side:
                        target_x = effective_ball_x + attack_dir * 6.0
                        target_y = min(78.0, max(58.0, ball_y + 10.0)) if is_right_mid else max(22.0, min(42.0, ball_y - 10.0))
                    else:
                        target_x = effective_ball_x + attack_dir * 8.0
                        target_y = 60.0 if is_right_mid else 40.0

                if attack_dir > 0:
                    target_x = max(30.0, min(87.0, target_x))
                else:
                    target_x = min(70.0, max(13.0, target_x))

        # =========================================================================
        # 3. FUNDASII (2, 3, 4, 5): Sprint pe flanc (Overlap) pentru fundasii laterali + Rest Defense
        # =========================================================================
        else:
            if player_num in [3, 4]:
                # Fundasii centrali asigura echilibrul la mijloc (rest defense)
                base_line = 38.0 if attack_dir > 0 else 62.0
                target_x = base_line + (effective_ball_x - 50.0) * 0.35
                if attack_dir > 0:
                    target_x = min(52.0, max(18.0, target_x))
                else:
                    target_x = max(48.0, min(82.0, target_x))
                target_y = self.start_y
            else:
                # Fundasii laterali: 2 (dreapta y > 50), 5 (stanga y < 50)
                is_right_fb = (player_num == 2)
                is_ball_my_flank = (ball_y >= 46.0) if is_right_fb else (ball_y <= 54.0)

                if is_ball_my_flank:
                    # Sprint ofensiv pe flanc (Overlap rapid pe tusa!)
                    target_x = effective_ball_x + attack_dir * 3.5
                    target_y = 88.0 if is_right_fb else 12.0
                else:
                    # Sustinere echilibrata cand mingea e pe flancul opus
                    target_x = effective_ball_x - attack_dir * 7.0
                    target_y = 80.0 if is_right_fb else 20.0

                if attack_dir > 0:
                    target_x = min(83.0, max(24.0, target_x))
                else:
                    target_x = max(17.0, min(76.0, target_x))

        # Cautam un culoar de pasa liber (iesire din umbra de marcaj a adversarului)
        target_x, target_y = self.find_open_support_spot(target_x, target_y, ball_x, ball_y, attack_dir, message)
        target_y = self.get_evasive_target(target_x, target_y, message)
        target_x = max(3.0, min(97.0, target_x))
        target_y = max(3.0, min(97.0, target_y))
        return target_x, target_y

    def run(self):
        # Inregistrare agenti
        intention = {
            "agent_id" : self.agent_id,
            "team" : self.team,
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
                    self.stun_frames = message["players"][str(self.agent_id)]["stun_frames"]
                

                # ---------------DEBUG CONSOLA-----------------
                # (MOMENTAN) print(f"Agentul {self.agent_id} (X: {self.x:.2f}, Y: {self.y:.2f}) vede mingea la Coordonatele {message['ball']['x']}, {message['ball']['y']}")
                # ---------------DEBUG CONSOLA-----------------
                
                # verificam cine incepe de la mijloc
                is_opponent_kickoff = (str(self.team) != str(message.get("kickoff_team")) and message["ball"]["x"] == 50.0 and message["ball"]["y"] == 50.0)

                # Verificam cine are posesia
                team_in_possession = None
                possessor_state = None
                is_gk_protected = False

                # cineva are mingea la picior acum?
                if message["possession"] is not None:
                    possessor_id = str(message["possession"])
                    team_in_possession = message["players"][possessor_id]["team"]
                    possessor_state = message["players"][possessor_id]["state"]
                    # verificam daca mingea e prinsa de portar
                    is_gk_protected = (possessor_state in [STATE_GK_HOLD_BALL, STATE_GK_CLEAR_BALL])
                
                # mingea este in aer/libera, cine a atins-o ultimul?
                elif message.get("last_touch") is not None:
                    last_touch_id = str(message["last_touch"])

                    # ne asiguram ca jucatorul inca exista in mintea serverului
                    if last_touch_id in message["players"]:
                        team_in_possession = message["players"][last_touch_id]["team"]

                # DACA O PASA ESTE IN TRANZIT CATRE UN COECHIPIER, POSESIA RAMANE LA ECHIPA NOASTRA!
                if message["possession"] is None and message.get("intended_receiver") is not None:
                    receiver_id = str(message["intended_receiver"])
                    if receiver_id in message["players"] and message["players"][receiver_id]["team"] == self.team:
                        team_in_possession = self.team

                # verdict: este echipa noastra in atac?
                we_have_possession = (team_in_possession == self.team)

                # Memorarea pasatorului pentru combinatii "Un-Doi" (1-2 Wall Pass) cu fereastra scurta de timp
                if str(message.get("intended_receiver")) == str(self.agent_id) and message.get("last_touch") is not None:
                    if str(message["last_touch"]) != str(self.agent_id):
                        self.last_passer_id = str(message["last_touch"])
                        self.one_two_window_frames = 25
                elif not we_have_possession:
                    self.last_passer_id = None
                    self.one_two_window_frames = 0
                elif self.one_two_window_frames > 0:
                    self.one_two_window_frames -= 1
                    if self.one_two_window_frames == 0:
                        self.last_passer_id = None

                # Mentinerea liniei progresive a atacului (impiedica retragerea in cascada la o pasa scurta in spate)
                attack_dir_global = 1.0 if float(self.start_x) < 50.0 else -1.0
                curr_bx = message["ball"]["x"]
                if not we_have_possession or message["game_status"] != STATUS_PLAYING:
                    self.attack_high_x = curr_bx
                else:
                    if self.attack_high_x is None:
                        self.attack_high_x = curr_bx
                    elif (curr_bx - self.attack_high_x) * attack_dir_global > 0:
                        self.attack_high_x = curr_bx
                    else:
                        # Scadere foarte lenta spre minge ca jucatorii din fata sa ramana avansati pentru combinatii
                        self.attack_high_x = self.attack_high_x * 0.985 + curr_bx * 0.015

                        
                # Calculam cel mai apropiat jucator activ (folosind punctul de repunere daca suntem in faza fixa)
                is_dead_ball_status = message["game_status"] in [STATUS_OUT, STATUS_CORNER, STATUS_GOAL_KICK]
                ref_ball_x = message.get("restart_ball_x", message["ball"]["x"]) if is_dead_ball_status else message["ball"]["x"]
                ref_ball_y = message.get("restart_ball_y", message["ball"]["y"]) if is_dead_ball_status else message["ball"]["y"]

                distance_agent_to_ball = self.calculate_distance(ref_ball_x, ref_ball_y)
                am_i_closest_to_ball = True

                # verific sa nu fiu pe jos
                if self.stun_frames > 0:
                    am_i_closest_to_ball = False
                else:
                    for player_id, player_data in message["players"].items():
                        if player_data["team"] == self.team and str(player_id) != str(self.agent_id) and player_data["stun_frames"] == 0:
                            # Portarul nu executa faze fixe de camp (out / corner)
                            if player_data.get("role") == "GK" or str(player_id) in ["1", "101"]:
                                continue
                            dist = math.hypot(player_data["x"] - ref_ball_x, player_data["y"] - ref_ball_y)
                            # daca un coleg valabil e mai aproape decat mine
                            if dist < distance_agent_to_ball:
                                am_i_closest_to_ball = False
                                break

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
                    if self.state not in [STATE_DO_THROW_IN, STATE_WAIT_THROW_IN]: 

                        # aflam echipa care a atins ultima mingea
                        last_touch_id = str(message["last_touch"])
                        last_touch_team = message["players"][last_touch_id]["team"]

                        # executam autul doar daca echipa noastra a primit aut...
                        # ...si suntem cel mai aproape de minge
                        if self.team != last_touch_team and am_i_closest_to_ball == True:
                            self.state = STATE_DO_THROW_IN
                        else:
                            # toti ceilalti asteapta sa se bata aut
                            self.state = STATE_WAIT_THROW_IN

                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }

                        # cei care asteapta se aseaza tactic: echipa care repune urca,
                        # echipa care apara se retrage dar acopera mingea
                        if self.state == STATE_WAIT_THROW_IN:
                            my_team_has_restart = (self.team != last_touch_team)
                            intention["target_x"], intention["target_y"] = self.get_restart_position(
                                ref_ball_x, ref_ball_y, my_team_has_restart)

                        self.dealer_socket.send_json(intention)
                    
                    # 2. Executia (se verifica fiecare cadru cat timp e aut)
                    # E IN DO_THROW_IN SI AJUNGE LA MINGE
                    if self.state == STATE_DO_THROW_IN and self.calculate_distance(message["ball"]["x"],message["ball"]["y"]) < 2.5:
                        if message.get("restart_ready", False) and message.get("restart_ball_placed", True):
                            # cautam cel mai apropiat coechipier pentru o repunere sigura
                            best_target_x, best_target_y = 50.0, 50.0
                            best_target_id = None
                            min_dist = 999.0

                            for player_id, player_data in message["players"].items():
                                # trebuie sa fie in echipa mea, sa nu fiu eu, si sa nu fie pe jos
                                if player_data["team"] == self.team and str(player_id) != str(self.agent_id) and player_data["stun_frames"] == 0:
                                    dist = math.hypot(player_data["x"] - self.x, player_data["y"] - self.y)
                                    if dist < min_dist:
                                        min_dist = dist
                                        best_target_x = player_data["x"]
                                        best_target_y = player_data["y"]
                                        best_target_id = player_id
                            
                            # aruncam mingea (pasa catre coechipierul de sprijin)
                            intention = self.prepare_kick(best_target_x, best_target_y, power = 2.0, action_type = STATE_PASS)
                            if best_target_id is not None:
                                intention["target_agent_id"] = str(best_target_id)
                            self.dealer_socket.send_json(intention)
                            self.state = STATE_IDLE # am aruncat mingea!
                
                # ===================================
                # CORNER (CORNER KICK)
                # ===================================
                elif message["game_status"] == STATUS_CORNER:
                    last_touch_id = str(message["last_touch"]) if message.get("last_touch") is not None else None
                    last_touch_team = message["players"][last_touch_id]["team"] if (last_touch_id and last_touch_id in message["players"]) else ("B" if ref_ball_x < 50.0 else "A")
                    
                    # Echipa care bate este echipa opusa celei care a scos mingea pe linia de fund
                    attacking_team = "B" if last_touch_team == "A" else "A"
                    my_team_has_restart = (self.team == attacking_team)

                    # 1. Atribuirea rolurilor la intrarea in faza fixa
                    if self.state not in [STATE_DO_CORNER, STATE_WAIT_CORNER]:
                        if my_team_has_restart and am_i_closest_to_ball:
                            self.state = STATE_DO_CORNER
                        else:
                            self.state = STATE_WAIT_CORNER

                        intention = {
                            "agent_id": self.agent_id,
                            "action": self.state
                        }

                        if self.state == STATE_WAIT_CORNER:
                            intention["target_x"], intention["target_y"] = self.get_corner_position(
                                ref_ball_x, ref_ball_y, my_team_has_restart)

                        self.dealer_socket.send_json(intention)

                    # 2. Executia cornerului de catre executant
                    if self.state == STATE_DO_CORNER and self.calculate_distance(message["ball"]["x"], message["ball"]["y"]) < 2.5:
                        # Server Authority: Asteptam ca arbitrul sa fluiere permisiunea (restart_ready == True)
                        if message.get("restart_ready", False) and message.get("restart_ball_placed", True):
                            # Identificam cel mai bun coechipier plasat in careu
                            target_goal_x = 100.0 if float(self.start_x) < 50.0 else 0.0
                            penalty_spot_x = target_goal_x - (12.0 if float(self.start_x) < 50.0 else -12.0)
                            penalty_spot_y = 50.0

                            best_target_x = penalty_spot_x
                            best_target_y = penalty_spot_y
                            best_target_id = None
                            min_dist = 999.0

                            for p_id, p_data in message["players"].items():
                                if p_data["team"] == self.team and str(p_id) != str(self.agent_id) and p_data["stun_frames"] == 0:
                                    d = math.hypot(p_data["x"] - penalty_spot_x, p_data["y"] - penalty_spot_y)
                                    if d < min_dist:
                                        min_dist = d
                                        best_target_x = p_data["x"]
                                        best_target_y = p_data["y"]
                                        best_target_id = p_id

                            # Centram cu forta calibrata in careu (fara rachete care ies pe partea cealalta)
                            intention = self.prepare_kick(best_target_x, best_target_y, power = 2.6, action_type = STATE_PASS)
                            if best_target_id is not None:
                                intention["target_agent_id"] = str(best_target_id)
                            self.dealer_socket.send_json(intention)
                            self.state = STATE_IDLE

                # ===================================
                # AUT DE POARTA (GOAL KICK)
                # ===================================
                elif message["game_status"] == STATUS_GOAL_KICK:
                    # Echipa care bate este cea in a carei jumatate e mingea (poarta protejata)
                    team_awarded = "A" if ref_ball_x < 50.0 else "B"
                    my_team_has_restart = (self.team == team_awarded)

                    # Jucatorii de camp se aseaza tactic la autul de poarta (portarul executa)
                    if self.state != STATE_WAIT_GOAL_KICK:
                        self.state = STATE_WAIT_GOAL_KICK
                        intention = {
                            "agent_id": self.agent_id,
                            "action": self.state
                        }
                        intention["target_x"], intention["target_y"] = self.get_goal_kick_position(
                            ref_ball_x, ref_ball_y, my_team_has_restart)
                        self.dealer_socket.send_json(intention)
                
                # ===================================
                # JOCUL ESTE IN DESFASURARE (PLAYING)
                # ===================================
                else:

                    # ===============================
                    # -------- MEALY MACHINE --------
                    # ===============================
                    
                    distance_agent_to_ball = self.calculate_distance(message['ball']['x'],message['ball']['y'])
                    
                    # --- Senzor de deadlock ---
                    # numaram cati jucatori (aliati sau inamici) sunt lipiti de minge
                    players_near_ball = 0
                    for player_id, player_data in message["players"].items():
                        if player_data["stun_frames"] == 0:
                            dist_agent_to_ball = math.hypot(player_data["x"] - message["ball"]["x"], player_data["y"] - message["ball"]["y"])
                            if dist_agent_to_ball < 2.5: # raza gramezii
                                players_near_ball += 1

                    # daca sunt in gramada (eu si inca cineva) si stam asa
                    if distance_agent_to_ball < 2.5 and players_near_ball >= 2:
                        self.deadlock_frames += 1
                    else:
                        self.deadlock_frames = 0
                    

                    # --- SCORUL PENTRU PRESSING (ANTI-SWARM: MAX 1-2 JUCATORI) ---
                    # aflam X-ul portii pe care o aparam
                    own_goal_x = 0.0 if float(self.start_x) < 50.0 else 100.0
                    distance_ball_to_own_goal = abs(message["ball"]["x"] - own_goal_x)

                    # distanta ideala este cu 4 metri mai aproape de poarta,
                    # dar niciodata mai putin de 0 metri
                    ideal_distance = max(0.0, distance_ball_to_own_goal - 4.0)

                    # punctul ideal X: la 4 metri in fata adversarului (goal-side)
                    ideal_x = abs(ideal_distance - own_goal_x)
                    ideal_y = message["ball"]["y"]
                    if self.stun_frames > 0:
                        my_pressing_score = -999.0 # daca suntem pe jos
                    else:
                        # punctaj in functie de pozitia fata de punctul ideal
                        my_pressing_score = 100.0 - math.hypot(self.x - ideal_x, self.y - ideal_y)

                    # Numaram cati coechipieri au un scor de pressing mai bun decat noi
                    better_teammates_count = 0
                    for player_id, player_data in message["players"].items():
                        if player_data["team"] == self.team and str(player_id) != str(self.agent_id):
                            if player_data["stun_frames"] > 0:
                                continue
                            if player_data.get("role") == "GK" or str(player_id) in ["1", "101"]:
                                continue

                            teammate_pressing_score = 100.0 - math.hypot(player_data["x"] - ideal_x, player_data["y"] - ideal_y)

                            if teammate_pressing_score > my_pressing_score:
                                better_teammates_count += 1
                    
                    # Permitem STRICT 1 jucator principal de pressing (sau al 2-lea pentru dublaj doar daca e deja foarte aproape < 8.0m)
                    if self.stun_frames > 0:
                        is_primary_chaser = False
                        is_secondary_chaser = False
                    else:
                        is_primary_chaser = (better_teammates_count == 0)
                        is_secondary_chaser = (better_teammates_count == 1 and distance_agent_to_ball < 8.0)

                    can_i_press = is_primary_chaser or (is_secondary_chaser and not we_have_possession and message["possession"] is not None)

                    # unde avanseaza agentii
                    if float(self.start_x) < 50.0:
                        target_x = 100.0 # agentii din stanga ataca dreapta
                    else:
                        target_x = 0.0 # agentii din dreapta ataca stanga

                    # agentii alearga 80% pe linia lor dar 20% spre poarta
                    center_of_goal = 50.0
                    target_y = random.uniform((((0.8 * self.y) + (0.2 * center_of_goal)) - 2), (((0.8 * self.y) + (0.2 * center_of_goal)) + 2))
                    distance_agent_to_opponent_goal = self.calculate_distance(target_x, target_y)
                    
                    # GUARD CLAUSE pentru stun
                    if self.stun_frames > 0:
                        pass

                    # E IN FAZA FIXA SI A FOST EXECUTATA => TRECE IN IDLE 
                    elif self.state in [STATE_DO_THROW_IN, STATE_WAIT_THROW_IN, STATE_DO_CORNER, STATE_WAIT_CORNER, STATE_DO_GOAL_KICK, STATE_WAIT_GOAL_KICK]:
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

                    # TRANZITIA DUPA PASA
                    # DUPA CE A PASAT, TRECE DIRECT IN SPRINT DE SUSTINERE / UN-DOI (1-2)
                    elif self.state == STATE_PASS:
                        self.state = STATE_ATTACK_SUPPORT
                        sup_x, sup_y = self.compute_attack_support_target(message)
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state,
                            "target_x" : sup_x,
                            "target_y" : sup_y
                        }
                        self.dealer_socket.send_json(intention)

                    # TRANZITIA DUPA DRIBBLE DUEL
                    # in functie de duel_frames
                    elif self.state == STATE_DRIBBLE_DUEL:
                        if self.duel_frames == 0:
                            self.state = STATE_IDLE
                        else:
                            self.duel_frames -= 1
                        
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

                    # SUSTINERE ATAC (JOCUL FARA MINGE - DEMARCARI, FLANCURI, 1-2 SI COMBINATII)
                    elif self.state == STATE_ATTACK_SUPPORT:
                        sup_x, sup_y = self.compute_attack_support_target(message)
                          
                        # Daca avem posesia mingii (am primit pasa sau recuperat), intram in CONTROL_BALL
                        if message["possession"] == str(self.agent_id):
                            self.state = STATE_CONTROL_BALL
                            intention = self.prepare_kick(target_x, target_y, power = 0.1, action_type = STATE_CONTROL_BALL)

                        # DACA SUNT DESTINATARUL UNEI PASE IN DESFASURARE (inclusiv 1-2 un-doi rapid!), ATAC IMEDIAT MINGEA!
                        elif str(message.get("intended_receiver")) == str(self.agent_id) and not is_opponent_kickoff:
                            self.ignore_ball_frames = 0
                            self.state = STATE_CHASE
                            ix, iy = self.calculate_pass_intercept(message["ball"]["x"], message["ball"]["y"], message["ball"]["velocity_x"], message["ball"]["velocity_y"])
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : ix,
                                "target_y" : iy
                            }

                        # abia am pasat, facem sprint "Un-Doi" (Give-and-Go) pe spatiu liber
                        elif self.ignore_ball_frames > 0:
                            self.ignore_ball_frames -= 1
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : sup_x,
                                "target_y" : sup_y
                            }

                        # daca mingea e libera in aer si sunt cel mai aproape (DOAR 1 jucator ca sa evitam swarm)
                        elif message["possession"] is None and am_i_closest_to_ball == True and not is_opponent_kickoff:
                            self.state = STATE_CHASE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }

                        # mingea ajunge la adversari => intram in IDLE
                        elif self.ignore_ball_frames == 0 and we_have_possession == False:
                            self.state = STATE_IDLE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }
                        
                        # mingea e libera langa noi si suntem cel mai apropiat => intram in CHASE
                        elif distance_agent_to_ball < 9.0 and message["possession"] is None and am_i_closest_to_ball and not is_gk_protected and not is_opponent_kickoff:
                            self.state = STATE_CHASE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }


                        # continuam demarcarea inteligenta in atac
                        else:
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : sup_x,
                                "target_y" : sup_y
                            }
                        
                        self.dealer_socket.send_json(intention)
                    
                    # SUSTINEREA APARARII SI MARCAJ HIBRID ZONAL-OM
                    elif self.state == STATE_DEFEND_SUPPORT:

                        # Daca am recuperat mingea, intram in CONTROL_BALL
                        if message["possession"] == str(self.agent_id):
                            self.state = STATE_CONTROL_BALL
                            intention = self.prepare_kick(target_x, target_y, power = 0.1, action_type = STATE_CONTROL_BALL)

                        # Daca o pasa ne este adresata noua, atacam mingea
                        elif str(message.get("intended_receiver")) == str(self.agent_id) and not is_opponent_kickoff:
                            self.state = STATE_CHASE
                            ix, iy = self.calculate_pass_intercept(message["ball"]["x"], message["ball"]["y"], message["ball"]["velocity_x"], message["ball"]["velocity_y"])
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : ix,
                                "target_y" : iy
                            }

                        # daca mingea e libera, o recupereaza DOAR cel mai apropiat (anti-swarm)
                        elif message["possession"] is None and (am_i_closest_to_ball == True or (distance_agent_to_ball < 14.0 and is_primary_chaser)) and not is_opponent_kickoff:
                            self.state = STATE_CHASE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }

                        # adversarul are mingea la picior si eu sunt desemnat sa fac pressing (max 1-2 jucatori)
                        elif message["possession"] is not None and not we_have_possession and can_i_press and distance_agent_to_ball < 24.0 and not is_gk_protected and not is_opponent_kickoff:
                            self.state = STATE_CHASE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            } 


                        # un coleg a recuperat mingea
                        elif we_have_possession == True:
                            self.state = STATE_IDLE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }
                        
                        # mingea e la adversari: pozitionare defensiva + MARCAJ HIBRID ZONAL-OM (cu perna de 3.8m)
                        else:
                            self.state = STATE_DEFEND_SUPPORT
                            attack_dir = 1.0 if float(self.start_x) < 50.0 else -1.0
                            own_goal_x = 0.0 if attack_dir > 0 else 100.0
                            ball_x = message["ball"]["x"]
                            ball_y = message["ball"]["y"]
                            try:
                                p_num = int(self.agent_id) % 100
                            except ValueError:
                                p_num = 10

                            # 1. Calculam ancora zonala de baza
                            if p_num in [9, 10, 11]:
                                # Atacantii raman la mijloc pentru contraatac
                                zone_x = 47.0 if attack_dir > 0 else 53.0
                                zone_y = self.start_y + (ball_y - 50.0) * 0.3
                            elif p_num in [6, 7, 8]:
                                # Mijlocasii formeaza blocul median
                                zone_x = 29.0 + (ball_x - 50.0) * 0.28 if attack_dir > 0 else 71.0 + (ball_x - 50.0) * 0.28
                                zone_y = 0.55 * self.start_y + 0.45 * ball_y
                            else:
                                # Fundasii protejeaza linia careului
                                zone_x = 16.5 + (ball_x - 50.0) * 0.16 if attack_dir > 0 else 83.5 + (ball_x - 50.0) * 0.16
                                zone_y = 0.72 * self.start_y + 0.28 * ball_y

                            target_x, target_y = zone_x, zone_y

                            # 2. Marcaj hibrid Zonal-Om pentru fundasi si mijlocasi (2..8):
                            # Cautam un adversar fara minge intrat in zona noastra de responsabilitate (raza 14m)
                            if p_num in [2, 3, 4, 5, 6, 7, 8]:
                                best_mark_opp = None
                                best_mark_dist = 14.0
                                poss_id = str(message.get("possession"))

                                for opp_id, opp_data in message["players"].items():
                                    if opp_data["team"] != self.team and opp_data["stun_frames"] == 0:
                                        if str(opp_id) == poss_id:
                                            continue
                                        if opp_data.get("role") == "GK" or str(opp_id) in ["1", "101"]:
                                            continue
                                        dist_to_zone = math.hypot(opp_data["x"] - zone_x, opp_data["y"] - zone_y)
                                        if dist_to_zone < best_mark_dist:
                                            best_mark_dist = dist_to_zone
                                            best_mark_opp = opp_data

                                if best_mark_opp is not None:
                                    # Ne asezam "goal-side" (intre adversar si poarta noastra) la o distanta echilibrata de 3.8m
                                    # Astfel inchidem culoarul si stam aproape de om, dar lasam spatiu de joc (nu sufocam atacul!)
                                    dx_goal = own_goal_x - best_mark_opp["x"]
                                    dy_goal = 50.0 - best_mark_opp["y"]
                                    d_goal = math.hypot(dx_goal, dy_goal)
                                    if d_goal > 0.1:
                                        mark_x = best_mark_opp["x"] + (dx_goal / d_goal) * 3.8
                                        mark_y = best_mark_opp["y"] + (dy_goal / d_goal) * 3.8
                                    else:
                                        mark_x, mark_y = zone_x, zone_y

                                    # Combinam 65% marcajul la om cu 35% pozitia zonala pentru a nu fi trasi complet din formatie
                                    target_x = 0.65 * mark_x + 0.35 * zone_x
                                    target_y = 0.65 * mark_y + 0.35 * zone_y

                            target_x = max(4.0, min(96.0, target_x))
                            target_y = max(4.0, min(96.0, target_y))
                            target_y = self.get_evasive_target(target_x, target_y, message)
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : target_x,
                                "target_y" : target_y
                            }
                        
                        self.dealer_socket.send_json(intention)

                    # RENUNTAREA LA URMARIRE 1 (ANTI-SWARM: iesire imediata din CHASE daca alt coleg a preluat pressingul!)
                    elif self.state == STATE_CHASE and str(message.get("intended_receiver")) != str(self.agent_id) and message["possession"] != str(self.agent_id) and (
                        distance_agent_to_ball > 26.0
                        or (not we_have_possession and message["possession"] is not None and not can_i_press)
                        or (message["possession"] is None and not am_i_closest_to_ball and not is_primary_chaser)
                    ):
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # E IN CHASE SI ESTE DESTINATARUL PASEI => ACTUALIZAM PUNCTUL DE INTERCEPTIE PE MASURA CE MINGEA ZBOARA
                    elif self.state == STATE_CHASE and str(message.get("intended_receiver")) == str(self.agent_id) and distance_agent_to_ball >= 2.0:
                        ix, iy = self.calculate_pass_intercept(message["ball"]["x"], message["ball"]["y"], message["ball"]["velocity_x"], message["ball"]["velocity_y"])
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state,
                            "target_x" : ix,
                            "target_y" : iy
                        }
                        self.dealer_socket.send_json(intention)

                    # RENUNTAREA LA URMARIRE 2
                    # E IN CHASE DAR UN COECHIPIER AJUNGE LA MINGE => TRECE IN IDLE
                    elif self.state == STATE_CHASE and we_have_possession == True and message["possession"] != str(self.agent_id) and message["possession"] is not None:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # RENUNTAREA LA URMARIRE 3
                    # E IN CHASE DAR PORTARUL PRINDE MINGEA => TRECE IN IDLE
                    elif self.state == STATE_CHASE and is_gk_protected:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # E IN CHASE SI A PRIMIT PASA SAU A AJUNS LA MINGE LIBERA => intra in CONTROL_BALL
                    elif self.state == STATE_CHASE and ((message["possession"] == str(self.agent_id) and str(message.get("last_touch")) != str(self.agent_id)) or (distance_agent_to_ball < 2.0 and message["possession"] is None)):
                        self.state = STATE_CONTROL_BALL
                        intention = self.prepare_kick(target_x, target_y, power = 0.1, action_type = STATE_CONTROL_BALL)
                        self.dealer_socket.send_json(intention)

                    # CONTINUAREA URMARIRII MINGII (CHASE ACTIV)
                    # Oricine este in CHASE si nu are posesia continua sa alerge direct spre minge
                    elif self.state == STATE_CHASE and message["possession"] != str(self.agent_id):
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)

                    # GANDIREA FARA MINGE
                    elif self.state == STATE_IDLE:
                        # daca avem posesia mingii, intram direct in CONTROL_BALL
                        if message["possession"] == str(self.agent_id):
                            self.state = STATE_CONTROL_BALL
                            intention = self.prepare_kick(target_x, target_y, power = 0.1, action_type = STATE_CONTROL_BALL)
                        # daca suntem destinatarul unei pase in desfasurare, atacam direct mingea!
                        elif str(message.get("intended_receiver")) == str(self.agent_id) and not is_opponent_kickoff:
                            self.state = STATE_CHASE
                            ix, iy = self.calculate_pass_intercept(message["ball"]["x"], message["ball"]["y"], message["ball"]["velocity_x"], message["ball"]["velocity_y"])
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : ix,
                                "target_y" : iy
                            }
                        # echipa are posesia => sustine atacul
                        elif we_have_possession == True:
                            self.state = STATE_ATTACK_SUPPORT
                            sup_x, sup_y = self.compute_attack_support_target(message)
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : sup_x,
                                "target_y" : sup_y
                            }
                        # echipa nu are posesia si suntem desemnati pentru pressing (max 1-2 jucatori) => intra in CHASE
                        elif we_have_possession == False and distance_agent_to_ball < 24.0 and can_i_press and not is_gk_protected and not is_opponent_kickoff:
                            self.state = STATE_CHASE
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state
                            }
                        # nu are posesia si e departe de minge => sustine apararea
                        else:
                            self.state = STATE_DEFEND_SUPPORT
                            target_x = 0.7 * self.start_x + 0.3 * message["ball"]["x"]
                            target_y = 0.7 * self.start_y + 0.3 * message["ball"]["y"]
                            intention = {
                                "agent_id" : self.agent_id,
                                "action" : self.state,
                                "target_x" : target_x,
                                "target_y" : target_y
                            }
                        # trimit intentia pe retea
                        self.dealer_socket.send_json(intention)

                    # rezolvarea blocajului
                    # daca a stat blocat 1.5 secunde (45 cadre)
                    elif self.deadlock_frames > 45:
                        self.deadlock_frames = 0
                        # resetam starea pentru a regandi tactica
                        self.state = STATE_IDLE

                        # alege o directie aleatorie scurta (degajare din gramada)
                        poke_x = message["ball"]["x"] + random.uniform(-15.0, 15.0)
                        poke_y = message["ball"]["y"] + random.uniform(-15.0, 15.0)

                        # fortam o pasa slaba/ciupire, ignorand limita fizica de 2.0
                        intention = self.prepare_kick(poke_x, poke_y, power = 1.5, action_type = STATE_KICK)
                        self.dealer_socket.send_json(intention)

                    # A FURAT CINEVA MINGEA
                    elif self.state == STATE_CONTROL_BALL and message["possession"] not in [None, str(self.agent_id)]:
                        self.state = STATE_IDLE
                        intention = {
                            "agent_id" : self.agent_id,
                            "action" : self.state
                        }
                        self.dealer_socket.send_json(intention)
                
                    # AVEM POSESIA -> DECIDEM CE FACEM CU MINGEA
                    elif message["possession"] == str(self.agent_id):

                        # =====================================
                        # CALCULAM CEA MAI BUNA OPTIUNE DE PASA
                        # ------- SI SCORUL PENTRU PASA -------
                        # =====================================
                         
                        # ==== COEFICIENTI PENTRU PASA =====
                        closest_opponent_distance = 100
                        # Raza de pericol a primitorului de lungimea pasei
                        pressure_radius_coef = 0.15
                        # Scorul pentru cea mai buna pasa
                        best_pass_score = -999
                        # Punct optim pentru pasa
                        optimal_point_for_pass = 12
                        # Coeficient de severitate
                        severity_short_pass = 2.0
                        severity_long_pass = 0.5
                        # Pentru siguranta
                        best_pass_target_id = None
                        best_pass_target_distance = 0.0
                        best_pass_target_x = 0.0
                        best_pass_target_y = 0.0
                        best_pass_lead_distance = 0.0
                        best_pass_is_true_tap_in = False
                        # ==================================
            
                        for player_id, player_data in message["players"].items():
                
                            # verificam sa nu fie el insusi
                            if str(player_id) == str(self.agent_id):
                                continue
                            # daca e coechipier
                            if player_data["team"] == self.team:

                                # nu pasam cu portarul
                                if float(player_data["start_x"]) in [2.0, 98.0]:
                                    continue

                                # proiectia in viitor si evaluarea combinatiilor
                                # aflam directia atacului
                                attack_direction = 1.0 if float(self.start_x) < 50.0 else -1.0
                                dx_progress_raw = (player_data["x"] - self.x) * attack_direction
                                
                                # este o pasa ofensiva in fata sau o combinatie pe linie/diagonala?
                                is_forward_pass = (dx_progress_raw > 1.5)
                                is_lateral_combo = (-2.0 <= dx_progress_raw <= 1.5)

                                try:
                                    rec_num = int(player_id) % 100
                                except ValueError:
                                    rec_num = 10
                                
                                # Jucatorii ofensivi care ataca spatiul (atacanti, extreme, interi 6/8 si fundasi laterali 2/5 in urcare)
                                is_attacking_runner = rec_num in [9, 10, 11, 6, 8, 2, 5]
                                is_rec_in_attacking_half = (attack_direction == 1.0 and player_data["x"] > 46.0) or (attack_direction == -1.0 and player_data["x"] < 54.0)

                                # Verificam daca primitorul are spatiu liber in fata pentru pasa pe pozitie viitoare (pe alergare)
                                rec_space_ahead = 99.0
                                for o_id, o_data in message["players"].items():
                                    if o_data["team"] != self.team and o_data["stun_frames"] == 0:
                                        d_rec_o = math.hypot(o_data["x"] - (player_data["x"] + attack_direction * 1.5), o_data["y"] - player_data["y"])
                                        if d_rec_o < rec_space_ahead:
                                            rec_space_ahead = d_rec_o

                                # Daca pasam in fata sau in diagonala catre un coleg lansat in jumatatea adversa cu spatiu in fata (> 3.2m),
                                # ii dam pasa masurata pe alergare (1.4m in directia portii/alergarii); altfel pasam STRICT LA PICIOR (0.0m)!
                                if (is_forward_pass or is_lateral_combo) and is_attacking_runner and is_rec_in_attacking_half and rec_space_ahead > 3.2:
                                    lead_distance = 1.4
                                else:
                                    lead_distance = 0.0

                                # punctul tinta real in care vrem sa trimitem mingea
                                target_pass_x = player_data["x"] + (lead_distance * attack_direction)
                                # Daca extrema taie spre careu in ultima treime, orientam usor pasa spre interiorul careului
                                if lead_distance > 0.0 and rec_num in [9, 11] and ((attack_direction > 0 and target_pass_x > 68.0) or (attack_direction < 0 and target_pass_x < 32.0)):
                                    target_pass_y = player_data["y"] + (-0.6 if player_data["y"] > 55.0 else (0.6 if player_data["y"] < 45.0 else 0.0))
                                else:
                                    target_pass_y = player_data["y"]

                                # limitare ca sa nu dam pase afara din teren
                                target_pass_x = max(2.0, min(98.0, target_pass_x))
                                target_pass_y = max(2.0, min(98.0, target_pass_y))
                                
                                # Scor initial pentru pasa
                                current_pass_score = 110
                                closest_opponent_to_receiver = 100
                                is_pass_lane_blocked = False

                                # Verificam culoarul de pasa
                                dx_pass = target_pass_x - self.x
                                dy_pass = target_pass_y - self.y

                                distance_agent_to_pass_point = math.hypot(dx_pass, dy_pass)

                                if distance_agent_to_pass_point > 0.01:
                                    nx_pass = dx_pass / distance_agent_to_pass_point
                                    ny_pass = dy_pass / distance_agent_to_pass_point
                                else:
                                    nx_pass, ny_pass = 1.0,  0.0
                                
                                
                                # bucla pentru a afla cel mai apropiat adversar de coechipierul caruia vrem sa ii pasam
                                for opponent_id, opponent_data in message["players"].items():
                                    
                                    if opponent_data["stun_frames"] > 0:
                                        continue

                                    if opponent_data["team"] != self.team:
                                        # ne intereseaza adversarii apropiati de locul unde va ajunge mingea
                                        distance_opponent_to_target =  math.hypot(opponent_data["x"] - target_pass_x, opponent_data["y"] - target_pass_y)
                                        if distance_opponent_to_target < closest_opponent_to_receiver:
                                            closest_opponent_to_receiver = distance_opponent_to_target
                                            closest_opponent_to_receiver_id = opponent_id
                                    
                                    # vectorul de la noi la adversar
                                    dx_pass_opp = opponent_data["x"] - self.x
                                    dy_pass_opp = opponent_data["y"] - self.y

                                    # produsul scalar
                                    # cat a inaintat mingea pana in dreptul adversarului
                                    d_pass_length = (dx_pass_opp * nx_pass) + (dy_pass_opp * ny_pass)

                                    # verificam daca adversarul e in fata noastra si intre noi si coechipier
                                    if 0 < d_pass_length < distance_agent_to_pass_point:

                                        # produs vectorial
                                        # distanta laterala fata de traiectorie
                                        d_pass_perpendicular = abs((dx_pass_opp * ny_pass) - (dy_pass_opp * nx_pass))

                                        # latimea conului de blocaj
                                        starting_distance_width = 1.2
                                        distance_width_coefficient = 0.09
                                        cone_width = starting_distance_width + (d_pass_length * distance_width_coefficient)

                                        # daca e in interiorul conului, blocheaza culoarul
                                        if d_pass_perpendicular < cone_width:
                                            is_pass_lane_blocked = True
                                            # Penalizare severa: stop la pase trimise direct in corpul adversarilor!
                                            # Daca e direct pe traiectorie (< 1.1m) sau in con, scorul scade dramatic sub 0
                                            penalty_for_blocking = 350 if d_pass_perpendicular < 1.1 else 240
                                            current_pass_score -= penalty_for_blocking


                                # cat de departe e coechipierul fata de "punctul optim de pasa"
                                deviation = abs(distance_agent_to_pass_point - optimal_point_for_pass)
                                
                                # raza de presiune: mai toleranta in treimea adversa pentru a permite pase la varf
                                is_in_final_third = (attack_direction == 1.0 and target_pass_x > 68.0) or (attack_direction == -1.0 and target_pass_x < 32.0)
                                pressure_radius = 1.6 if is_in_final_third else min(3.0, distance_agent_to_pass_point * pressure_radius_coef)
                        
                                # daca adversarul e prea aproape de coechipier
                                if closest_opponent_to_receiver < 1.4:
                                    current_pass_score -= 150 # primitor marcat foarte strans (om la om)
                                elif closest_opponent_to_receiver < pressure_radius:
                                    current_pass_score -= (60 if is_in_final_third else 100)

                                # coechipierul e prea aproape => creste severitatea penalizarii
                                if distance_agent_to_pass_point < optimal_point_for_pass:    
                                    pass_penalty = (deviation ** 2) * severity_short_pass
                                else:
                                    pass_penalty = deviation * severity_long_pass
                                current_pass_score -= pass_penalty
                        
                                # EVALUAREA DIRECTIEI: COMBINATII INAINTE / DIAGONALA / UN-DOI (1-2) VS PASA INAPOI
                                is_agent_in_attacking_half = (attack_direction == 1.0 and self.x > 50.0) or (attack_direction == -1.0 and self.x < 50.0)
                                opp_goal_x = 100.0 if attack_direction > 0 else 0.0
                                my_dist_to_goal_center = math.hypot(opp_goal_x - self.x, 50.0 - self.y)
                                rec_dist_to_goal_center = math.hypot(opp_goal_x - target_pass_x, 50.0 - target_pass_y)

                                # Este o pasa de gol / cutback (coechipier in ultima treime, mai bine pozitionat spre centrul portii si liber)?
                                is_better_shooting_spot = is_in_final_third and not is_pass_lane_blocked and (rec_dist_to_goal_center < my_dist_to_goal_center - 2.0 or (rec_dist_to_goal_center < 15.0 and abs(target_pass_y - 50.0) < abs(self.y - 50.0) - 4.0))

                                # Este un "tap-in" autentic cu poarta goala (coleg singur in 11m central, mult mai aproape de poarta decat noi)?
                                is_candidate_true_tap_in = (
                                    not is_pass_lane_blocked
                                    and rec_dist_to_goal_center <= 11.5
                                    and abs(target_pass_y - 50.0) <= 10.0
                                    and closest_opponent_to_receiver > 3.6
                                    and (my_dist_to_goal_center > rec_dist_to_goal_center + 3.5 or abs(self.y - 50.0) > 12.0)
                                )

                                # 1. BONUS "UN-DOI" NATURAL (NEFORTAT):
                                # Doar daca fereastra de 1-2 e activa, culoarul e 100% liber, colegul e complet demarcat (> 4.0m de adversar),
                                # SI noi NU suntem deja in pozitie buna de sut la marginea/interiorul careului (my_dist_to_goal_center > 19.5)!
                                is_one_two_return = (
                                    self.one_two_window_frames > 0
                                    and self.last_passer_id is not None
                                    and str(player_id) == str(self.last_passer_id)
                                    and not is_pass_lane_blocked
                                    and dx_progress_raw >= 1.0
                                    and closest_opponent_to_receiver > 4.0
                                    and (my_dist_to_goal_center > 19.5 or rec_dist_to_goal_center < my_dist_to_goal_center - 4.0)
                                )
                                if is_one_two_return:
                                    current_pass_score += 24

                                # 2. BONUS DEMARCARE ACTIVA / COMBINATIE TIKI-TAKA: coleg in ATTACK_SUPPORT bine demarcat si cu culoar liber
                                if not is_pass_lane_blocked and player_data.get("state") == STATE_ATTACK_SUPPORT and closest_opponent_to_receiver > 3.5 and 7.0 <= distance_agent_to_pass_point <= 20.0 and dx_progress_raw >= -1.0:
                                    current_pass_score += 18

                                if is_forward_pass or is_better_shooting_spot:
                                    # Pasa progresiva spre poarta adversa sau pasa decisiva in careu:
                                    if is_in_final_third:
                                        current_pass_score += 110
                                        # BONUS PASA DECISIVA / EXTRA-PASS: coechipier liber si mai bine plasat pentru finalizare!
                                        if is_better_shooting_spot and closest_opponent_to_receiver > 3.0:
                                            current_pass_score += 55
                                    else:
                                        current_pass_score += 60
                                elif is_lateral_combo:
                                    # Pasa de combinatie pe linie / diagonala scurta (schimbare de flanc sau deschidere in half-space):
                                    if is_in_final_third:
                                        current_pass_score += 55
                                    elif is_agent_in_attacking_half:
                                        current_pass_score += 35
                                    else:
                                        current_pass_score += 15
                                else:
                                    # Pasa inapoi (dx_progress_raw < -2.0): penalizare severa daca suntem in atac,
                                    # astfel incat varful/mijlocasii sa combine in fata sau sa avanseze, si sa paseze in spate DOAR la nevoie!
                                    if is_in_final_third:
                                        current_pass_score -= 130
                                    elif is_agent_in_attacking_half:
                                        current_pass_score -= 75
                                    else:
                                        current_pass_score -= 15
                                
                                if current_pass_score > best_pass_score:
                                    best_pass_target_id = player_id
                                    best_pass_target_distance = distance_agent_to_pass_point
                                    best_pass_target_x = target_pass_x
                                    best_pass_target_y = target_pass_y
                                    best_pass_score = current_pass_score
                                    best_pass_lead_distance = lead_distance
                                    best_pass_is_true_tap_in = is_candidate_true_tap_in
                            
                            # daca e adversar 
                            else:
                                # daca adversarul e pe jos, mergem mai departe
                                if player_data["stun_frames"] > 0:
                                    continue
                                distance_agent_to_opponent = self.calculate_distance(player_data["x"], player_data["y"])
                                if distance_agent_to_opponent < closest_opponent_distance:
                                    closest_opponent_distance = distance_agent_to_opponent
                                    closest_opponent_id = player_id

                        # ===============================
                        # CALCULAM SCORUL PENTRU DRIBLING
                        # ===============================
                        base_dribble_score = 65.0
                        dribble_multiplier = 6.5

                        # Calculam cati metri de culoar liber avem IN FATA spre poarta adversa
                        attack_dir_drib = 1.0 if float(self.start_x) < 50.0 else -1.0
                        open_space_ahead = 30.0
                        for opp_id, opp_data in message["players"].items():
                            if opp_data["team"] != self.team and opp_data["stun_frames"] == 0:
                                dx_f = (opp_data["x"] - self.x) * attack_dir_drib
                                dy_f = abs(opp_data["y"] - self.y)
                                # Adversar aflat in conul nostru de avansare
                                if dx_f > -1.0 and dy_f < 6.0:
                                    dist_f = math.hypot(max(0.0, dx_f), dy_f)
                                    if dist_f < open_space_ahead:
                                        open_space_ahead = dist_f

                        # Daca avem spatiu liber in fata (> 9m), incurajam jucatorul sa avanseze cu mingea la picior
                        # in loc sa dea pase scurte/inutile de la 35-40m!
                        open_lane_bonus = min(55.0, max(0.0, (open_space_ahead - 7.5) * 4.5)) if closest_opponent_distance > 3.8 else 0.0
                        dribble_score = base_dribble_score + min(85.0, closest_opponent_distance * dribble_multiplier) + open_lane_bonus

                        # ==========================
                        # CALCULAM SCORUL PENTRU SUT
                        # ==========================
                        goal_x = 100.0 if float(self.start_x) < 50.0 else 0.0
                        goal_y = random.uniform(42.0, 58.0)

                        # Folosim distanta reala pana la CENTRUL portii si unghiul lateral pentru decizia de sut
                        dist_to_goal_center = math.hypot(goal_x - self.x, 50.0 - self.y)
                        lateral_offset = abs(self.y - 50.0)

                        dx_shot = goal_x - self.x
                        dy_shot = goal_y - self.y
                        distance_ball_to_goal = math.hypot(dx_shot, dy_shot)

                        # normalizarea vectorului de sut
                        if distance_ball_to_goal > 0.01:
                            nx_shot = dx_shot / distance_ball_to_goal
                            ny_shot = dy_shot / distance_ball_to_goal
                        else:
                            nx_shot, ny_shot = 1.0, 0.0
                        
                        # Verificam culoarul de sut
                        has_shot_blocker = False
                        shot_blocking_penalty = 0.0
                        for opponent_id, opponent_data in message["players"].items():
                            # ignoram portarul (portarul sta pe linia portii)
                            if opponent_data["start_x"] in [0, 100, 2.0, 98.0] or opponent_data.get("role") == "GK":
                                continue
                            if opponent_data["team"] != self.team and opponent_data["stun_frames"] == 0:

                                # vectorul de la noi la adversar
                                dx_opp = opponent_data["x"] - self.x
                                dy_opp = opponent_data["y"] - self.y

                                # produsul scalar: cat a inaintat pe axa spre poarta
                                d_length = (dx_opp * nx_shot) + (dy_opp * ny_shot)

                                # verificam daca adversarul e in fata noastra si intre noi si poarta
                                if 0 < d_length < distance_ball_to_goal:

                                    # distanta laterala fata de traiectoria sutului
                                    d_perpendicular = abs((dx_opp * ny_shot) - (dy_opp * nx_shot))

                                    # latimea conului de blocaj la sut (con realist pentru blocaj direct)
                                    starting_distance_width = 0.95
                                    distance_width_coefficient = 0.065
                                    cone_width = starting_distance_width + (d_length * distance_width_coefficient)

                                    # daca e in interiorul conului, blocheaza traiectoria directa a sutului
                                    if d_perpendicular < cone_width:
                                        has_shot_blocker = True
                                        penalty_block = 50.0 if dist_to_goal_center <= 16.5 else 90.0
                                        shot_blocking_penalty = max(shot_blocking_penalty, penalty_block)

                        # Penalizare pentru unghi inchis (cand jucatorul e prea in lateral fata de barele portii 41..59)
                        angle_penalty = max(0.0, (lateral_offset - 9.0) * 4.2)

                        # Scor fotbalistic realist si curajos pentru sut:
                        # 1. In careu (<= 16.5m de centrul portii): zona principala de finalizare
                        if dist_to_goal_center <= 16.5:
                            kick_score = 215.0 + (16.5 - dist_to_goal_center) * 5.5 - shot_blocking_penalty - angle_penalty
                        # 2. Marginea careului si semidistanta (16.5m - 24.5m): sut periculos daca avem culoar si unghi bun!
                        elif dist_to_goal_center <= 24.5:
                            kick_score = 182.0 - ((dist_to_goal_center - 16.5) * 6.5) - shot_blocking_penalty - angle_penalty
                        # 3. Peste 24.5m: construim faza prin pase sau dribling (fara rachete de la 35m)
                        else:
                            kick_score = -500.0

                        # DECIZIA: SUT VS PASA VS DRIBLING
                        # - Sub 11.0m central sau sub 18.5m singur cu portarul (fara blocaj pe traiectorie si unghi bun <= 13.5m) -> SUT HOTARAT!
                        # - Daca insa un coleg are un "tap-in" autentic cu poarta goala mult mai aproape de poarta, pasam decisiv!
                        is_point_blank = (dist_to_goal_center <= 11.0 and lateral_offset <= 10.0 and not has_shot_blocker)
                        is_clean_one_on_one = (dist_to_goal_center <= 18.5 and lateral_offset <= 13.5 and not has_shot_blocker)
                        is_best_action_shot = (kick_score > best_pass_score and kick_score > dribble_score)

                        if (is_point_blank or is_clean_one_on_one or is_best_action_shot) and not best_pass_is_true_tap_in and dist_to_goal_center <= 24.5:
                            self.state = STATE_KICK
                            self.last_passer_id = None
                            self.one_two_window_frames = 0

                            # ================================================================
                            # DISPERSIE SI PRECIZIE REALISTA A SUTULUI (MISSES -> GOAL KICK)
                            # ================================================================
                            aim_corner_y = random.choice([random.uniform(42.5, 46.5), random.uniform(53.5, 57.5)])
                            
                            if dist_to_goal_center <= 11.5:
                                error_std = 1.25
                            elif dist_to_goal_center <= 17.5:
                                error_std = 2.2
                            else:
                                error_std = 3.2

                            if closest_opponent_distance < 3.0:
                                error_std += 1.5

                            actual_shot_y = aim_corner_y + random.gauss(0.0, error_std)

                            # Putere echilibrata: suturi ferme, dar umane si parabile (2.4 - 3.3)
                            shot_power = min(SHOT_POWER_MAX, max(SHOT_POWER_MIN, 2.35 + (dist_to_goal_center * 0.04)))

                            intention = self.prepare_kick(goal_x, actual_shot_y, power = shot_power, action_type = STATE_KICK)

                        # Pasa
                        elif best_pass_score > dribble_score and best_pass_score > kick_score and best_pass_score > 20.0:
                            self.state = STATE_PASS
                            self.ignore_ball_frames = 26

                            # Pregatim tinta de sprint "Un-Doi" (Give-and-Go): dupa ce pasam, atacam spatiul in fata!
                            attack_dir_pass = 1.0 if float(self.start_x) < 50.0 else -1.0
                            gg_x = self.x + attack_dir_pass * 13.0
                            if attack_dir_pass > 0:
                                self.give_and_go_x = min(92.0, max(25.0, gg_x))
                            else:
                                self.give_and_go_x = max(8.0, min(75.0, gg_x))
                            # Ne deschidem usor in diagonala fata de colegul caruia i-am pasat pentru a crea unghi de 1-2
                            y_shift = -5.5 if best_pass_target_y > self.y else 5.5
                            self.give_and_go_y = max(10.0, min(90.0, self.y + y_shift))
                            
                            # Calibrarea fizica exacta a fortei pasei (compensarea frecarii 0.95/tick):
                            # Cu frecarea 0.95, mingea parcurge distanta D = 20 * (V_initial - V_sosire).
                            # Vrem ca mingea sa ajunga la coechipier cu o viteza ideala de preluare (~0.75 u/tick),
                            # nici prea tare pentru pasele scurte, nici prea slaba pentru pasele lungi!
                            if best_pass_lead_distance > 0.0:
                                pass_power = min(max(0.72 + best_pass_target_distance * 0.048, 1.05), 2.85)
                            else:
                                pass_power = min(max(0.78 + best_pass_target_distance * 0.052, 1.10), 3.05)
                            
                            final_target_x = best_pass_target_x
                            final_target_y = best_pass_target_y
                            intention = self.prepare_kick(final_target_x, final_target_y, power = pass_power, action_type = STATE_PASS)
                            if best_pass_target_id is not None:
                                intention["target_agent_id"] = str(best_pass_target_id)
                                
                        # Am decis sa pastram mingea: Dribling cursiv in spatiu liber sau Dribling sub presiune
                        else:
                            # In careu la sub 13m sub presiune stransa, fara optiune buna de pasa: trage la poarta!
                            if dist_to_goal_center <= 13.0 and lateral_offset <= 12.0 and closest_opponent_distance < 2.3 and best_pass_score < 130.0:
                                self.state = STATE_KICK
                                aim_corner_y = random.choice([random.uniform(43.0, 47.0), random.uniform(53.0, 57.0)])
                                actual_shot_y = aim_corner_y + random.gauss(0.0, 2.0)
                                shot_power = min(SHOT_POWER_MAX, max(SHOT_POWER_MIN, 2.4 + (dist_to_goal_center * 0.03)))
                                intention = self.prepare_kick(goal_x, actual_shot_y, power = shot_power, action_type = STATE_KICK)
                            # Sub presiune in teren deschis: protectia mingii si fentare rapida (duel scurt 15 cadre = 0.5s)
                            elif closest_opponent_distance < 2.5:
                                self.state = STATE_DRIBBLE_DUEL
                                self.duel_frames = 15
                                target_y = self.get_evasive_target(target_x, target_y, message)
                                intention = self.prepare_kick(target_x, target_y, power = 0.55, action_type = STATE_DRIBBLE)
                            # Liber: conducerea mingii lina si lipita de picior (0.72 < 0.85 viteza de alergare)
                            else:
                                self.state = STATE_DRIBBLE
                                target_y = self.get_evasive_target(target_x, target_y, message)
                                intention = self.prepare_kick(target_x, target_y, power = 0.72, action_type = STATE_DRIBBLE)
                                    
                        # print(f"Sut: {kick_score}, Pasa: {best_pass_score}, Dribbling: {dribble_score}")
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
        
    # EVITAREA OBSTACOLELOR
    def get_evasive_target(self, target_x, target_y, message):
        # cat de departe se uita in fata
        radar_scan_distance = 3.0
        # cat de lata e banda noastra de alergare
        avoidance_lane_width = 1.5 
        # cat ocolim oponentul
        avoid_opponent = 3.0

        for player_id, player_data in message["players"].items():
            # ne evitam pe noi insine
            if str(player_id) == str(self.agent_id):
                continue

            # nu ne ferim de colegii nostri, doar de adversari (Bug FIX)
            if player_data["team"] == self.team:
                continue

            # daca el are mingea, nu il ocolim (pentru a permite deposedarile)
            if str(player_id) == str(message.get("possession")):
                continue

            distance_agent_to_obstacle = self.calculate_distance(player_data["x"], player_data["y"])

            # e prea aproape? (< 3.0m)
            if distance_agent_to_obstacle < radar_scan_distance:
                # e in fata mea?
                is_in_front = False
                # alergam spre dreapta
                if target_x > self.x and player_data["x"] > self.x:
                    is_in_front = True
                # alergam spre stanga
                elif target_x < self.x and player_data["x"] < self.x:
                    is_in_front = True
                                        
                if is_in_front:
                    # ne blocheaza banda de alergare?
                    if abs(player_data["y"] - self.y) < avoidance_lane_width:
                        # ocolim adversarul
                        if player_data["y"] > self.y:
                            target_y = max(self.y - avoid_opponent, 0.1)
                        else:
                            target_y = min(self.y + avoid_opponent, 99.9)
                        # am gasit si ocolit obstacolul, iesim din bucla
                        break
        return target_y
        