from config import STATUS_MATCH_OVER
import zmq
import time
import json
import math
from config import *
import random

class MatchEngine:
    def __init__(self, headless=False, match_duration_seconds=None, team_a_name="RED", team_b_name="BLUE", team_a_ai="Base Build", team_b_ai="Base Build"):
        self.headless = bool(headless)
        self.sim_time = 0.0
        if not self.headless:
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
        else:
            self.context = None
            self.pub_socket = None
            self.router_socket = None
            self.poller = None
        # Mingea
        self.ball = {
            "x": 50.0,
            "y": 50.0,
            "velocity_x": 0.0,
            "velocity_y": 0.0
            }
        # Status joc
        self.game_status = STATUS_START_GAME 
        # Jucatori
        self.players = {}
        # Ultimul jucator care a atins mingea (pentru OUT/CORNER)
        self.last_touch = None
        # Echipa care a lovit mingea cel mai recent si actiunea executata (KICK, PASS, DRIBBLE)
        self.kicking_team = None
        self.kick_action = None
        # Cine are posesiea mingii
        self.possession = None
        # Destinatarul pasei in desfasurare
        self.intended_receiver = None
        # Echipa care incepe de la mijloc
        self.kickoff_team = random.choice(["A", "B"])
        self.first_half_kickoff_team = self.kickoff_team
        self.kickoff_pending = False
        # Repriza curenta (1 = 0..45 min, 2 = 45..90 min cu terenurile schimbate)
        self.half = 1
        self.halftime_start_time = None
        self.second_half_wait_start = None
        self.paused_real_seconds = 0.0
        # Goluri
        self.score_A = 0
        self.score_B = 0
        # Timp si setari implicite
        self.start_time = None
        self.match_duration_real_seconds = float(match_duration_seconds) if match_duration_seconds is not None else 180.0 # 3 minute
        # Controlul fluierului arbitrului la faze fixe (OUT, CORNER, GOAL_KICK)
        self.restart_ready = True
        self.restart_start_time = None
        self.restart_ball_placed = True
        self.restart_ball_x = 50.0
        self.restart_ball_y = 50.0
        self.goal_time = None
        self.goal_ball_centered = True
        # Sistemul Arbitru FIFA + VAR pentru Ofsaid
        self.offside_pending = False
        self.offside_receiver_id = None
        self.offside_line_x = None
        self.offside_spot_x = 50.0
        self.offside_spot_y = 50.0
        self.offside_defending_team = None
        # Sistemul Arbitru FIFA pentru Faulturi, Lovituri Libere Directe si Penalty-uri (11m)
        self.foul_spot_x = 50.0
        self.foul_spot_y = 50.0
        self.foul_attacking_team = None
        self.foul_defending_team = None
        self.foul_cooldown_frames = 0
        self.last_set_piece_status = None
        # Statistici in timp real ale meciului (pentru HUD, Pauza, Final si evaluare ML)
        self.stats = {
            "A": {
                "xg": 0.0, "possession_ticks": 0, "shots": 0, "shots_on_target": 0,
                "passes": 0, "passes_completed": 0, "corners": 0, "tackles_won": 0,
                "saves": 0, "fouls": 0, "offsides": 0
            },
            "B": {
                "xg": 0.0, "possession_ticks": 0, "shots": 0, "shots_on_target": 0,
                "passes": 0, "passes_completed": 0, "corners": 0, "tackles_won": 0,
                "saves": 0, "fouls": 0, "offsides": 0
            }
        }
        self.pass_in_flight_team = None
        self.pass_in_flight_sender = None
        # Modul de joc ("match" = 90 min, "scenarios" = Tactical Scenarios Lab)
        self.game_mode = "match"
        self.active_scenario = None
        self.scenario_countdown_start = None
        self.scenario_countdown_left = 3
        self.scenario_post_status = STATUS_PLAYING
        self.initial_scenario_loaded = False
        self.scenario_play_start = None
        self.scenario_end_timer = None
        self.scenario_phase_step = 0

        # Nume echipe si AI Build-uri selectate din Launcher
        self.team_A_name = str(team_a_name)
        self.team_B_name = str(team_b_name)
        self.team_A_ai = str(team_a_ai)
        self.team_B_ai = str(team_b_ai)

        if not self.headless:
            # Citim settings.json (bridge-ul catre Launcher)
            try:
                with open("settings.json", "r") as f:
                    settings = json.load(f)
                    match_rules = settings.get("match_rules", {})
                    teams_cfg = settings.get("teams", {})

                    # Suprascriem varibilele daca exista in fisier
                    if "match_duration_real_seconds" in match_rules:
                        self.match_duration_real_seconds = float(match_rules["match_duration_real_seconds"])
                    if "game_mode" in match_rules:
                        self.game_mode = str(match_rules["game_mode"])
                    if "A" in teams_cfg:
                        self.team_A_name = (str(teams_cfg["A"].get("name", "RED")).strip()[:10].upper()) or "RED"
                        self.team_A_ai = str(teams_cfg["A"].get("ai_build", "Base Build"))
                    if "B" in teams_cfg:
                        self.team_B_name = (str(teams_cfg["B"].get("name", "BLUE")).strip()[:10].upper()) or "BLUE"
                        self.team_B_ai = str(teams_cfg["B"].get("ai_build", "Base Build"))
                    
                    self._log(f"Setari incarcate din JSON: Mod={self.game_mode}, Timp={self.match_duration_real_seconds}s, {self.team_A_name} [{self.team_A_ai}] vs {self.team_B_name} [{self.team_B_ai}]")
            except FileNotFoundError:
                self._log("Nu s-a gasit settings.json. Folosim setarile implicite.")

    def _now(self):
        """Returneaza timpul virtual (in modul headless 1:1) sau timpul real (in meciul live)."""
        return self.sim_time if self.headless else time.time()

    def _log(self, msg):
        """Afiseaza mesaje in consola doar in modul live (fara spam in workerii de antrenare)."""
        if not self.headless:
            print(msg)

    def register_all_players_headless(self):
        """Inregistreaza toti cei 22 de jucatori direct la pozitiile lor de Kick-Off (fara drumul din tunel)."""
        self.players = {}
        for pid, cfg in STARTING_POSITIONS.items():
            pdata = {
                "start_x": float(cfg["x"]),
                "start_y": float(cfg["y"]),
                "x": float(cfg["x"]),
                "y": float(cfg["y"]),
                "state": STATE_IDLE,
                "stun_frames": 0,
                "stun_speed_mult": 1.0,
                "stun_type": "",
                "team": cfg["team"],
                "role": cfg.get("role", "FIELD"),
            }
            kx, ky = self.get_kickoff_setup_pos(pid, pdata)
            pdata["x"] = float(kx)
            pdata["y"] = float(ky)
            self.players[str(pid)] = pdata

    def reset_positions_for_second_half_headless(self):
        """Aseaza toti cei 22 de jucatori direct la pozitiile oglindite de Kick-Off pentru Repriza a 2-a."""
        for pid, pdata in self.players.items():
            kx, ky = self.get_kickoff_setup_pos(pid, pdata)
            pdata["x"] = float(kx)
            pdata["y"] = float(ky)
            pdata["state"] = STATE_IDLE
            pdata["stun_frames"] = 0
            pdata["stun_speed_mult"] = 1.0
            pdata["stun_type"] = ""
            pdata.pop("target_x", None)
            pdata.pop("target_y", None)

    
    def process_intention(self, intention):
        """Proceseaza intentia unui agent (identic in modul live ZeroMQ si in modul headless 1:1)."""
        # extragem ID-ul ca string curat
        agent_id_str = str(intention["agent_id"])
        # adaugam jucatorul in dictionar daca nu exista
        if agent_id_str not in self.players:
            if agent_id_str == "1":  
                tunnel_x = 45      
                tunnel_y = 100  
            else:
                tunnel_x = 55
                tunnel_y = 100     

            player_team = STARTING_POSITIONS.get(agent_id_str, {}).get("team")
            if not player_team:
                player_team = intention.get("team", "A" if int(agent_id_str) < 100 else "B")

            self.players[agent_id_str] = {
                "start_x" : STARTING_POSITIONS[agent_id_str]["x"],
                "start_y" : STARTING_POSITIONS[agent_id_str]["y"],
                "x" : tunnel_x, 
                "y" : tunnel_y, 
                "state" : STATE_IDLE,
                "stun_frames" : 0,
                "stun_speed_mult" : 1.0,
                "stun_type" : "",
                "team" : player_team,
                "role" : STARTING_POSITIONS.get(agent_id_str, {}).get("role", "FIELD")
            }

        # Cat timp suntem in numaratoarea inversa 3, 2, 1 sau faza s-a incheiat, jucatorii raman pe loc
        if self.game_status in [STATUS_SCENARIO_COUNTDOWN, STATUS_SCENARIO_DONE]:
            return

        if str(intention["action"]) in [STATE_KICK, STATE_DRIBBLE, STATE_PASS, STATE_CONTROL_BALL, STATE_GK_CLEAR_BALL] and self.players[agent_id_str]["stun_frames"] == 0: 
            if self.game_status in [STATUS_PLAYING, STATUS_OUT, STATUS_CORNER, STATUS_GOAL_KICK, STATUS_OFFSIDE, STATUS_FREE_KICK, STATUS_PENALTY]: 

                # Nu permitem executia sutului daca arbitrul inca tine faza blocata pentru asezarea echipelor
                if self.game_status in [STATUS_OUT, STATUS_CORNER, STATUS_GOAL_KICK, STATUS_OFFSIDE, STATUS_FREE_KICK, STATUS_PENALTY] and (not self.restart_ready or not self.restart_ball_placed):
                    pass
                else:
                    # extragem pozitia reala a jucatorului din mintea Serverului
                    server_player_x = self.players[agent_id_str]["x"]
                    server_player_y = self.players[agent_id_str]["y"]

                    # calculam distanta absoluta pana la minge
                    distance_to_ball = self.calculate_distance(server_player_x, server_player_y, self.ball["x"], self.ball["y"])

                    # permitem sutul doar daca agentul e fizic langa minge (2.5m in joc deschis, 5.0m la faze fixe)
                    max_kick_dist = 2.5 if self.game_status == STATUS_PLAYING else 5.0
                    if distance_to_ball < max_kick_dist:
                        prev_status = self.game_status
                        if self.game_status in [STATUS_FREE_KICK, STATUS_PENALTY, STATUS_CORNER, STATUS_OUT, STATUS_GOAL_KICK, STATUS_OFFSIDE]:
                            self.last_set_piece_status = self.game_status
                        else:
                            self.last_set_piece_status = None
                        self.ball["velocity_x"] = float(intention["kick_vx"])
                        self.ball["velocity_y"] = float(intention["kick_vy"])
                        self.last_touch = intention["agent_id"] 
                        self.possession = agent_id_str
                        self.kicking_team = self.players[agent_id_str]["team"]
                        self.kick_action = str(intention["action"])
                        self.offside_pending = False

                        # --- INREGISTRARE STATISTICI (SUTURI, xG, PASE) ---
                        k_team = self.kicking_team
                        if k_team in self.stats:
                            if self.kick_action == STATE_KICK:
                                self.pass_in_flight_team = None
                                self.pass_in_flight_sender = None
                                self.stats[k_team]["shots"] += 1
                                # Verificam geometric daca sutul este cadrat PE POARTA (41.0 <= y <= 59.0)
                                left_team_s = "A" if self.half == 1 else "B"
                                t_goal_x = 100.0 if k_team == left_team_s else 0.0
                                vx_s = self.ball["velocity_x"]
                                vy_s = self.ball["velocity_y"]
                                if (t_goal_x == 100.0 and vx_s > 0.05) or (t_goal_x == 0.0 and vx_s < -0.05):
                                    t_hit = (t_goal_x - self.ball["x"]) / vx_s
                                    if t_hit > 0:
                                        y_hit = self.ball["y"] + vy_s * t_hit
                                        if 41.0 <= y_hit <= 59.0:
                                            self.stats[k_team]["shots_on_target"] += 1
                                # Calculam Expected Goals (xG) realist pe baza modelului logistic
                                self.stats[k_team]["xg"] += self.compute_shot_xg(k_team, server_player_x, server_player_y, prev_status)
                            elif self.kick_action == STATE_PASS:
                                # Daca tocmai am preluat o pasa a colegului si pasam din prima, o contorizam ca reusita
                                if self.pass_in_flight_team == k_team and self.pass_in_flight_sender != agent_id_str:
                                    self.stats[k_team]["passes_completed"] += 1
                                self.stats[k_team]["passes"] += 1
                                self.pass_in_flight_team = k_team
                                self.pass_in_flight_sender = agent_id_str
                            elif self.kick_action in [STATE_CONTROL_BALL, STATE_DRIBBLE]:
                                if self.pass_in_flight_team == k_team and self.pass_in_flight_sender != agent_id_str:
                                    self.stats[k_team]["passes_completed"] += 1
                                    self.pass_in_flight_team = None
                                    self.pass_in_flight_sender = None
                            else:
                                self.pass_in_flight_team = None
                                self.pass_in_flight_sender = None
                        if self.kickoff_pending and str(intention["action"]) in [STATE_PASS, STATE_KICK]:
                            self.kickoff_pending = False

                        if "target_agent_id" in intention and intention["target_agent_id"] is not None:
                            self.intended_receiver = str(intention["target_agent_id"])
                        elif str(intention["action"]) in [STATE_KICK, STATE_DRIBBLE, STATE_GK_CLEAR_BALL, STATE_CONTROL_BALL]:
                            self.intended_receiver = None

                        # VERIFICARE ARBITRU FIFA OFSAID IN MOMENTUL PASEI (doar in joc deschis STATUS_PLAYING)
                        if self.game_status == STATUS_PLAYING and self.kick_action == STATE_PASS and self.intended_receiver in self.players:
                            rec_data = self.players[self.intended_receiver]
                            if rec_data.get("team") == self.kicking_team and self.intended_receiver != agent_id_str:
                                def_team = "B" if self.kicking_team == "A" else "A"
                                def_line_x = self.get_second_last_defender_x(def_team)
                                rec_x = rec_data["x"]
                                rec_y = rec_data["y"]
                                left_team_now = "A" if self.half == 1 else "B"
                                is_offside_now = False
                                if self.kicking_team == left_team_now:
                                    # Echipa care ataca spre dreapta (x = 100)
                                    if rec_x > 50.0 and rec_x > (self.ball["x"] + 0.4) and rec_x > (def_line_x + 0.55):
                                        is_offside_now = True
                                else:
                                    # Echipa care ataca spre stanga (x = 0)
                                    if rec_x < 50.0 and rec_x < (self.ball["x"] - 0.4) and rec_x < (def_line_x - 0.55):
                                        is_offside_now = True

                                if is_offside_now:
                                    self.offside_pending = True
                                    self.offside_receiver_id = self.intended_receiver
                                    self.offside_line_x = def_line_x
                                    self.offside_spot_x = max(6.0, min(94.0, rec_x))
                                    self.offside_spot_y = max(6.0, min(94.0, rec_y))
                                    self.offside_defending_team = def_team
                    else:
                        # printam tentativa de "frauda" pentru debug
                        self._log(f"Motorul a respins sutul agentului {agent_id_str}. Era la {distance_to_ball:.2f} distanta de minge!")

        # actualizam starea jucatorului
        self.players[str(intention["agent_id"])]["state"] = intention["action"]

        # salvam destinatia DOAR daca agentul ne-a trimis-o
        if "target_x" in intention and "target_y" in intention:
            self.players[agent_id_str]["target_x"] = float(intention["target_x"]) 
            self.players[agent_id_str]["target_y"] = float(intention["target_y"])
        elif intention["action"] in [STATE_CHASE, STATE_DRIBBLE, STATE_DRIBBLE_DUEL]:
            self.players[agent_id_str].pop("target_x", None)
            self.players[agent_id_str].pop("target_y", None)


    def step_tick(self):
        """Executa exact un pas fizic si tactic al meciului (0.05s) si returneaza game_state."""
        # miscarea agentilor (suspendata in timpul numaratorii inverse 3, 2, 1 sau cand faza e gata)
        for player_id, player_data in self.players.items():
            if self.game_status in [STATUS_SCENARIO_COUNTDOWN, STATUS_SCENARIO_DONE]:
                break

            # La PAUZA (min 45:00) si la FINALUL MECIULUI (min 90:00), toti jucatorii ies de pe teren catre tunelul vestiarelor!
            if self.game_status in [STATUS_HALF_TIME, STATUS_MATCH_OVER]:
                tunnel_x = 45.0 if player_data.get("team") == "A" else 55.0
                self.move_player_towards(player_data, tunnel_x, 100.0, speed = 0.58)
                continue

            # Penalizare de viteza (dezechilibrare) dupa tackle ratat sau deposedare:
            # Jucatorul NU mai ingheata pe loc! Continua sa alerge, dar incetinit proportional cu unghiul interventiei
            # (-75% din spate -> 0.25x, -60% din fata -> 0.40x, -40% din lateral -> 0.60x).
            if player_data["stun_frames"] > 0:
                player_data["stun_frames"] -= 1
                speed_mult = float(player_data.get("stun_speed_mult", 0.35))
                if player_data["stun_frames"] == 0:
                    player_data["stun_speed_mult"] = 1.0
                    player_data["stun_type"] = ""
            else:
                speed_mult = 1.0

            # daca suntem in CHASE, fugim direct spre minge (viteza calibrata realist: 0.56 u/tick = ~16.8 m/s in joc)
            if player_data["state"] in [STATE_CHASE, STATE_DRIBBLE, STATE_DRIBBLE_DUEL]:
                if player_data["state"] == STATE_CHASE and str(player_id) == str(self.intended_receiver) and "target_x" in player_data and "target_y" in player_data:
                    self.move_player_towards(player_data, player_data["target_x"], player_data["target_y"], speed = 0.56 * speed_mult)
                else:
                    self.move_player_towards(player_data, self.ball["x"], self.ball["y"], speed = 0.56 * speed_mult)
            
            # daca suntem in RESET, ne intoarcem la pozitia de incepere de pe teren (executantul merge la centrul terenului)
            elif player_data["state"] == STATE_RESET:
                kx, ky = self.get_kickoff_setup_pos(player_id, player_data)
                self.move_player_towards(player_data, kx, ky, speed = 0.48)
            
            # daca suntem in DO_THROW_IN, DO_CORNER, DO_GOAL_KICK, DO_FREE_KICK sau DO_PENALTY, merge spre a bate faza fixa
            elif player_data["state"] in [STATE_DO_THROW_IN, STATE_DO_CORNER, STATE_DO_GOAL_KICK, STATE_DO_FREE_KICK, STATE_DO_PENALTY]:
                tx_take = self.restart_ball_x if not self.restart_ball_placed else self.ball["x"]
                ty_take = self.restart_ball_y if not self.restart_ball_placed else self.ball["y"]
                self.move_player_towards(player_data, tx_take, ty_take, speed = TAKER_POSITIONING_SPEED)

            # daca suntem in WAIT_THROW_IN, WAIT_CORNER, WAIT_GOAL_KICK, WAIT_FREE_KICK sau WAIT_PENALTY, ne asezam spre tinta primita de la agent
            elif player_data["state"] in [STATE_WAIT_THROW_IN, STATE_WAIT_CORNER, STATE_WAIT_GOAL_KICK, STATE_WAIT_FREE_KICK, STATE_WAIT_PENALTY]:
                if "target_x" in player_data and "target_y" in player_data:
                    self.move_player_towards(player_data, player_data["target_x"], player_data["target_y"], speed = WAIT_POSITIONING_SPEED)

            # daca suntem in DEFEND_GOAL, portarul plonjeaza rapid catre tinta
            elif player_data["state"] == STATE_GK_DEFEND_GOAL:
                if "target_x" in player_data and "target_y" in player_data:
                    self.move_player_towards(player_data, player_data["target_x"], player_data["target_y"], speed = GK_DIVE_SPEED)

            # daca suntem in ATTACK_SUPORT, agentul se demarca / sustine ofensiva (0.54 speed)
            elif player_data["state"] == STATE_ATTACK_SUPPORT:
                if "target_x" in player_data and "target_y" in player_data:
                    self.move_player_towards(player_data, player_data["target_x"], player_data["target_y"], speed = 0.54 * speed_mult)
            
            # daca suntem in DEFEND_SUPPORT, agentul se pozitioneaza rapid si compact in aparare (0.52 speed)
            elif player_data["state"] == STATE_DEFEND_SUPPORT:
                if "target_x" in player_data and "target_y" in player_data:
                    self.move_player_towards(player_data, player_data["target_x"], player_data["target_y"], speed = 0.52 * speed_mult)
                

        if self.game_status == STATUS_GOAL and not self.goal_ball_centered:
            if self.goal_time is not None and (self._now() - self.goal_time) < GOAL_CELEBRATION_SECONDS:
                self.ball["velocity_x"] *= 0.78
                self.ball["velocity_y"] *= 0.78
                if self.ball["x"] < 50.0:
                    self.ball["x"] = max(-2.6, min(-0.4, self.ball["x"]))
                else:
                    self.ball["x"] = min(102.6, max(100.4, self.ball["x"]))
                self.ball["y"] = max(41.5, min(58.5, self.ball["y"]))
            else:
                if self.game_mode == "scenarios":
                    self.goal_ball_centered = True
                    self.game_status = STATUS_SCENARIO_DONE
                    self.ball["velocity_x"] = 0.0
                    self.ball["velocity_y"] = 0.0
                else:
                    self.ball["velocity_x"] = 0.0
                    self.ball["velocity_y"] = 0.0
                    self.ball["x"] = 50.0
                    self.ball["y"] = 50.0
                    self.goal_ball_centered = True

        if self.game_status == STATUS_SCENARIO_COUNTDOWN:
            self.ball["velocity_x"] = 0.0
            self.ball["velocity_y"] = 0.0
            elapsed_cd = self._now() - (self.scenario_countdown_start or self._now())
            self.scenario_countdown_left = max(1, int(math.ceil(SCENARIO_COUNTDOWN_SECONDS - elapsed_cd)))
            if elapsed_cd >= SCENARIO_COUNTDOWN_SECONDS:
                self.game_status = self.scenario_post_status
                self.scenario_play_start = self._now()
                self.scenario_end_timer = None
                self.scenario_phase_step = 0
                if self.start_time is None:
                    self.start_time = self._now()

        if self.game_status == STATUS_SCENARIO_DONE:
            self.ball["velocity_x"] *= 0.80
            self.ball["velocity_y"] *= 0.80
            if abs(self.ball["velocity_x"]) < 0.05:
                self.ball["velocity_x"] = 0.0
            if abs(self.ball["velocity_y"]) < 0.05:
                self.ball["velocity_y"] = 0.0

        if self.game_status in [STATUS_START_GAME, STATUS_GOAL]:
            if self.game_mode == "scenarios" and len(self.players) >= NUM_OF_PLAYERS and not self.initial_scenario_loaded:
                self.initial_scenario_loaded = True
                # Asezam jucatorii pe pozitiile de baza si asteptam ca utilizatorul sa aleaga o faza ("ALEGE O FAZA")
                for pid, pdata in self.players.items():
                    pdata["x"] = float(pdata["start_x"])
                    pdata["y"] = float(pdata["start_y"])
                    pdata["state"] = STATE_IDLE
                    pdata["stun_frames"] = 0
                self.ball["x"] = 50.0
                self.ball["y"] = 50.0
                self.ball["velocity_x"] = 0.0
                self.ball["velocity_y"] = 0.0
                self.active_scenario = None
                self.game_status = STATUS_SCENARIO_DONE
            elif self.game_mode != "scenarios" and self.goal_ball_centered and self.are_players_ready():
                left_team_now = "A" if self.half == 1 else "B"
                taker_id = "10" if self.kickoff_team == "A" else "110"
                if taker_id in self.players:
                    self.players[taker_id]["x"] = 49.6 if self.kickoff_team == left_team_now else 50.4
                    self.players[taker_id]["y"] = 50.0
                self.possession = taker_id
                self.last_touch = taker_id
                self.kicking_team = self.kickoff_team
                self.kickoff_pending = True
                self.game_status = STATUS_PLAYING
                
                # pornim ceasul la primul fluier de start; la repriza a 2-a reluam ceasul de la exact 45:00!
                if self.start_time is None:
                    self.start_time = self._now()
                elif self.second_half_wait_start is not None:
                    self.paused_real_seconds += (self._now() - self.second_half_wait_start)
                    self.second_half_wait_start = None

        # =====================================================================
        # PAUZA DE LA MINUTUL 45:00 (HALF TIME) -> ASTEAPTA BUTONUL "RESUME MATCH"!
        # =====================================================================
        if self.game_status == STATUS_HALF_TIME:
            self.ball["velocity_x"] *= 0.80
            self.ball["velocity_y"] *= 0.80

        if self.game_status in [STATUS_OUT, STATUS_CORNER, STATUS_GOAL_KICK, STATUS_OFFSIDE, STATUS_FREE_KICK, STATUS_PENALTY]:
            # 0. Rulare vizuala slow-motion a mingii (sau afisare linia VAR la OFSAID / marcaj FAULT) inainte de asezarea pe punct
            if not self.restart_ball_placed:
                if self.game_status == STATUS_OFFSIDE:
                    hold_duration = OFFSIDE_HOLD_SECONDS
                elif self.game_status in [STATUS_FREE_KICK, STATUS_PENALTY]:
                    hold_duration = FOUL_HOLD_SECONDS
                else:
                    hold_duration = OUT_OF_PLAY_ROLL_SECONDS
                if self.restart_start_time is not None and (self._now() - self.restart_start_time) < hold_duration:
                    self.ball["velocity_x"] *= 0.85
                    self.ball["velocity_y"] *= 0.85
                    self.ball["x"] = max(-3.5, min(103.5, self.ball["x"]))
                    self.ball["y"] = max(-2.8, min(102.8, self.ball["y"]))
                else:
                    # In modul TACTICAL SCENARIOS, daca mingea a iesit in afara terenului (aut/corner/aut de poarta),
                    # faza curenta s-a incheiat — dar la OFSAID, FREE_KICK sau PENALTY asezam mingea ca sa vedem executia!
                    if self.game_mode == "scenarios" and self.game_status not in [STATUS_OFFSIDE, STATUS_FREE_KICK, STATUS_PENALTY]:
                        self.ball["velocity_x"] = 0.0
                        self.ball["velocity_y"] = 0.0
                        self.game_status = STATUS_SCENARIO_DONE
                    else:
                        self.ball["velocity_x"] = 0.0
                        self.ball["velocity_y"] = 0.0
                        self.ball["x"] = self.restart_ball_x
                        self.ball["y"] = self.restart_ball_y
                        self.restart_ball_placed = True
            # fluier dinamic pentru asezarea echipelor inainte de executie (doar dupa ce mingea a fost asezata pe punct)
            if self.restart_ball_placed and not self.restart_ready:
                if self.restart_start_time is not None:
                    elapsed = self._now() - self.restart_start_time
                    # 1. Timp minim de asezare tactica (4.2s la lovituri libere / penalty ca zidul sa fie complet aliniat!)
                    min_prep_time = 4.2 if self.game_status in [STATUS_FREE_KICK, STATUS_PENALTY] else RESTART_PREPARE_MIN_SECONDS
                    if elapsed >= min_prep_time:
                        # 2. Verificam daca executantul a ajuns la minge
                        taker_at_ball = False
                        for p_id, p in self.players.items():
                            if p["state"] in [STATE_DO_THROW_IN, STATE_DO_CORNER, STATE_DO_GOAL_KICK, STATE_DO_FREE_KICK, STATE_DO_PENALTY]:
                                if self.calculate_distance(p["x"], p["y"], self.ball["x"], self.ball["y"]) < 2.5:
                                    taker_at_ball = True
                                    break
                        # Daca executantul este la minge SAU a trecut timpul maxim de siguranta (5.5s)
                        if taker_at_ball or elapsed >= RESTART_PREPARE_MAX_SECONDS:
                            self.restart_ready = True
                else:
                    self.restart_ready = True

            # cand mingea prinde viteza dupa executie, jocul revine in desfasurare
            if self.restart_ball_placed and self.restart_ready and (self.ball["velocity_x"] != 0.0 or self.ball["velocity_y"] != 0.0):
                self.game_status = STATUS_PLAYING
                self.restart_ready = True
                self.offside_pending = False
                if self.game_mode == "scenarios":
                    self.scenario_play_start = self._now()
                    # La scenariul OFFSIDE (VAR), dupa ce fundasul executa lovitura libera indirecta, lasam 3.0s sa vedem repunerea
                    if self.active_scenario == SCENARIO_OFFSIDE_VAR:
                        self.scenario_phase_step = 1
                        self.scenario_end_timer = self._now() + 3.0

        # =====================================================================
        # VERIFICARE FINALIZARE FAZA IN MODUL "TACTICAL SCENARIOS"
        # =====================================================================
        if self.game_mode == "scenarios" and self.game_status == STATUS_PLAYING:
            now_sc = self._now()
            att_poss = (self.possession is not None and self.players.get(str(self.possession), {}).get("team") == "A")
            def_poss = (self.possession is not None and self.players.get(str(self.possession), {}).get("team") == "B")

            # Daca Echipa A recupereaza mingea inapoi inainte sa expire cele 3.8 secunde, ANULAM cronometrul de oprire
            # ca sa lasam faza de recuperare / gegenpressing sa continue!
            if att_poss and self.scenario_end_timer is not None and not (self.active_scenario == SCENARIO_OFFSIDE_VAR and self.scenario_phase_step == 1):
                self.scenario_end_timer = None

            if self.scenario_end_timer is not None:
                if now_sc >= self.scenario_end_timer:
                    self.game_status = STATUS_SCENARIO_DONE
                    self.possession = None
                    self.intended_receiver = None
            else:
                # 1. Daca echipa din aparare (B) recupereaza mingea:
                # Lasam 3.8 secunde (aprox 3-4s) ca sa vedem daca Echipa A reuseste o recuperare sau daca B scapa pe contraatac!
                if def_poss:
                    if self.active_scenario == SCENARIO_1V1_GK:
                        self.scenario_end_timer = now_sc + 2.2
                    elif self.active_scenario != SCENARIO_OFFSIDE_VAR:
                        self.scenario_end_timer = now_sc + 3.8

                # 2. La 1v1 GK sau PENALTY: daca atacantul a sutat la poarta si mingea s-a oprit complet
                if self.active_scenario in [SCENARIO_1V1_GK, SCENARIO_PENALTY] and self.kick_action == STATE_KICK:
                    if math.hypot(self.ball["velocity_x"], self.ball["velocity_y"]) < 0.20:
                        self.scenario_end_timer = now_sc + 1.5

                # 3. La GOAL KICK: daca Echipa A a iesit cu succes din pressing si a urcat in jumatatea adversa (x > 55)
                if self.active_scenario == SCENARIO_GOAL_KICK and self.ball["x"] > 55.0:
                    self.scenario_end_timer = now_sc + 2.0

                # 4. Durata maxima a fazei active (suficient timp pentru combinatii si faza a doua la noul ritm realist)
                max_play_map = {
                    SCENARIO_1V1_GK: 10.5,
                    SCENARIO_PENALTY: 8.5,
                    SCENARIO_FREE_KICK: 12.5,
                    SCENARIO_CORNER: 13.5,
                    SCENARIO_GOAL_KICK: 13.5,
                    SCENARIO_THROW_IN: 13.0,
                    SCENARIO_TIKI_TAKA: 15.0,
                    SCENARIO_OFFSIDE_VAR: 14.0,
                }
                max_dur = max_play_map.get(self.active_scenario, 13.0)
                if self.scenario_play_start is not None and (now_sc - self.scenario_play_start) >= max_dur:
                    self.game_status = STATUS_SCENARIO_DONE
                    self.possession = None
                    self.intended_receiver = None

        # Decrementam cooldown-ul dintre faulturi pentru a pastra fluenta jocului
        if self.foul_cooldown_frames > 0:
            self.foul_cooldown_frames -= 1

        # ===========================================
        # --------- SISTEMUL ANTI-COLLIDE -----------
        # ===========================================
        player_items = list(self.players.items())
        n_players = len(player_items)
        collision_diameter = PLAYER_COLLISION_DIAMETER
        tackle_reach = 2.05  # Raza reala la care un aparator poate intinde piciorul la minge pentru tackle
        tackle_reach_sq = tackle_reach * tackle_reach

        # parcurgem fiecare pereche unica
        for i in range(n_players):
            p1_id, p1 = player_items[i]
            for j in range(i + 1, n_players):
                p2_id, p2 = player_items[j]

                dx_raw = p1["x"] - p2["x"]
                dy_raw = p1["y"] - p2["y"]
                d2 = dx_raw * dx_raw + dy_raw * dy_raw
                if d2 >= tackle_reach_sq:
                    continue

                # calculam distanta dintre ei
                dist = math.sqrt(d2)

                # evitam impartirea la zero daca sunt spawnati fix in acelasi pixel
                if dist == 0:
                    p1["x"] += 0.1
                    dist = 0.1

                # 1. Separarea fizica a corpurilor daca au intrat unul in altul (< 1.4m)
                if dist < collision_diameter:
                    # calculam suprapunerea
                    overlap = collision_diameter - dist

                    # directia in care ii impingem
                    dx = (p1["x"] - p2["x"]) / dist
                    dy = (p1["y"] - p2["y"]) / dist

                    # vector perpendicular (tangential) pentru a devia usor jucatorii si a evita blocarea "frunte in frunte"
                    tx = -dy
                    ty = dx

                    # fiecare e impins jumatate de distanta + o usoara alunecare laterala organica
                    push_back = overlap / 2.0
                    slide = push_back * 0.35

                    # aplicam forta de respingere cu separare curata
                    p1["x"] += (dx * push_back) + (tx * slide)
                    p1["y"] += (dy * push_back) + (ty * slide)

                    p2["x"] -= (dx * push_back) + (tx * slide)
                    p2["y"] -= (dy * push_back) + (ty * slide)

                # Guard Clause pentru ca coechipierii sa nu incerce sa faca tackle intre ei
                if p1["team"] == p2["team"]:
                    continue

                # 2. MECANICA DE TACKLE SI INTERCEPTIE LA PICIOR (in raza de actiune de 2.05m):
                # Proportionala cu pozitionarea aparatorului (fata > lateral > spate) si cu aglomerarea defensiva!
                if dist < tackle_reach and self.possession in [p1_id, p2_id] and p1["stun_frames"] == 0 and p2["stun_frames"] == 0:

                    if self.possession == p1_id:
                        attacker_id, attacker, defender_id, defender = p1_id, p1, p2_id, p2
                    else:
                        attacker_id, attacker, defender_id, defender = p2_id, p2, p1_id, p1

                    def_dist_to_ball = self.calculate_distance(defender["x"], defender["y"], self.ball["x"], self.ball["y"])
                    is_active_defender = defender["state"] in [STATE_CHASE, STATE_DEFEND_SUPPORT, STATE_IDLE]

                    # Deposedarea poate avea loc daca aparatorul este in raza mingii (< 2.35m) si atacantul nu este portarul cu mingea in brate
                    if is_active_defender and def_dist_to_ball < 2.35 and attacker["state"] not in [STATE_GK_HOLD_BALL, STATE_GK_CLEAR_BALL]:
                        # Calculam cati aparatori aditionali inconjoara purtatorul mingii (pe o raza de 3.8m)
                        # Daca atacantul intra intre 2-3 adversari, sansa de deposedare creste simtitor!
                        extra_defenders = 0
                        for other_id, other_p in self.players.items():
                            if other_id != defender_id and other_p.get("team") == defender.get("team") and other_p.get("stun_frames", 0) == 0:
                                if self.calculate_distance(other_p["x"], other_p["y"], attacker["x"], attacker["y"]) < 3.8:
                                    extra_defenders += 1
                        crowding_bonus = min(0.28, extra_defenders * 0.13)

                        # viteza mingii pentru a vedea directia de atac
                        vx = self.ball["velocity_x"]
                        vy = self.ball["velocity_y"]
                        speed = math.hypot(vx, vy)

                        if speed > 0.22:
                            # directia mingii pe axe
                            nx_ball = vx / speed
                            ny_ball = vy / speed

                            # vectorul de impact fata de atacant
                            impact_dx = defender["x"] - attacker["x"]
                            impact_dy = defender["y"] - attacker["y"]
                            dist_impact = math.hypot(impact_dx, impact_dy)

                            if dist_impact > 0:
                                # directia aparatorului pe axe
                                nx_def = impact_dx / dist_impact
                                ny_def = impact_dy / dist_impact

                                # aplicam produsul scalar (1.0 = direct in fata, 0.0 = lateral, -1.0 = direct in spate)
                                dot_product = (nx_ball * nx_def) + (ny_ball * ny_def)

                                # Daca aparatorul e doar in DEFEND_SUPPORT (nu face CHASE activ), intervine doar daca atacantul vine spre el sau pe langa el
                                if defender["state"] != STATE_CHASE and dot_product < -0.15:
                                    continue

                                # Sansa de deposedare calibrata proportional cu pozitia aparatorului:
                                # 1. Aparator plasat IN FATA (dot > 0.35): 60% - 82% sansa de recuperare!
                                if dot_product > 0.35:
                                    tackle_chance = 0.48 + dot_product * 0.34 + crowding_bonus
                                # 2. Aparator plasat IN LATERAL / UMAR LA UMAR (-0.25 <= dot <= 0.35): 38% - 56% sansa!
                                elif dot_product >= -0.25:
                                    tackle_chance = 0.44 + dot_product * 0.32 + crowding_bonus
                                # 3. Aparator care vine DIN SPATE (dot < -0.25): 16% - 30% sansa!
                                else:
                                    tackle_chance = max(0.16, 0.36 + dot_product * 0.22) + crowding_bonus * 0.6

                                # TACKLE REUSIT => ATTACKER DEZECHILIBRAT (-65% viteza) & DEFENDER PREIA CONTROLUL MINGII
                                if random.random() < tackle_chance:
                                    attacker["stun_frames"] = random.randint(16, 24)
                                    attacker["stun_speed_mult"] = 0.35
                                    attacker["stun_type"] = "DISPOSSESSED"

                                    # rezolvarea suprapunerii -> knockback
                                    attacker["x"] -= nx_def * 1.5
                                    attacker["y"] -= ny_def * 1.5

                                    # Aparatorul preia mingea la picior (fara ricoseu haotic in spate!)
                                    self.ball["x"] = defender["x"]
                                    self.ball["y"] = defender["y"]
                                    self.ball["velocity_x"] = 0.0
                                    self.ball["velocity_y"] = 0.0
                                    self.last_touch = defender_id
                                    self.possession = defender_id
                                    self.intended_receiver = None
                                    self.kicking_team = defender.get("team")
                                    self.kick_action = None
                                    self.pass_in_flight_team = None
                                    if defender.get("team") in self.stats:
                                        self.stats[defender.get("team")]["tackles_won"] += 1
                                    self._log(f"Agentul {defender_id} a reusit tackle (sansa {int(min(0.95, tackle_chance)*100)}%)")
                                
                                # TACKLE RATAT => DEFENDER INCETINIT PROPORTIONAL CU UNGHIUL (NU INGHETAT!)
                                else:
                                    # 1. Tackle ratat din fata (fentat pe directie): -60% viteza (0.40x), risc minim de fault (1.0%)
                                    if dot_product > 0.5:
                                        stun = random.randint(18, 25)
                                        slow_mult = 0.40
                                        foul_prob = 0.010
                                    
                                    # 2. Tackle ratat din lateral / umar la umar: -40% viteza (0.60x), risc mic de fault (2.5%)
                                    elif dot_product >= -0.5:
                                        stun = random.randint(12, 18)
                                        slow_mult = 0.60
                                        foul_prob = 0.025

                                    # 3. Tackle ratat din spate (alunecare in gol): -75% viteza (0.25x), risc mai ridicat de fault (8.0%)
                                    else:
                                        stun = random.randint(25, 34)
                                        slow_mult = 0.25
                                        foul_prob = 0.080

                                    # Verificam daca interventia ratata a produs FAULT (doar in joc deschis si cu cooldown intre faulturi!)
                                    if self.game_status == STATUS_PLAYING and self.game_mode != "scenarios" and self.foul_cooldown_frames == 0 and random.random() < foul_prob:
                                        self.trigger_foul(attacker_id, attacker, defender_id, defender)
                                        break

                                    defender["stun_frames"] = stun
                                    defender["stun_speed_mult"] = slow_mult
                                    defender["stun_type"] = "MISSED_TACKLE"
                                    defender["x"] += nx_def * 0.85
                                    defender["y"] += ny_def * 0.85
                                    self._log(f"Agentul {defender_id} NU a reusit tackle (viteza redusa la {int(slow_mult*100)}%)")
                        else:
                            # Atacantul sta pe loc / controleaza scurt mingea (speed <= 0.22) => deposedare din presiune imediata
                            impact_dx = defender["x"] - attacker["x"]
                            impact_dy = defender["y"] - attacker["y"]
                            dist_impact = math.hypot(impact_dx, impact_dy)
                            if dist_impact > 0:
                                nx_def = impact_dx / dist_impact
                                ny_def = impact_dy / dist_impact
                            else:
                                nx_def, ny_def = 1.0, 0.0

                            tackle_chance = 0.62 + crowding_bonus
                            if random.random() < tackle_chance:
                                attacker["stun_frames"] = random.randint(15, 22)
                                attacker["stun_speed_mult"] = 0.35
                                attacker["stun_type"] = "DISPOSSESSED"
                                self.possession = defender_id
                                self.last_touch = defender_id
                                attacker["x"] -= nx_def * 1.5
                                attacker["y"] -= ny_def * 1.5
                                self.ball["x"] = defender["x"]
                                self.ball["y"] = defender["y"]
                                self.ball["velocity_x"] = 0.0
                                self.ball["velocity_y"] = 0.0
                                self.intended_receiver = None
                                self.kicking_team = defender.get("team")
                                self.kick_action = None
                                self.pass_in_flight_team = None
                                if defender.get("team") in self.stats:
                                    self.stats[defender.get("team")]["tackles_won"] += 1
                                self._log(f"Agentul {defender_id} a deposedat atacantul oprit din cursa")
                            else:
                                if self.game_status == STATUS_PLAYING and self.game_mode != "scenarios" and self.foul_cooldown_frames == 0 and random.random() < 0.022:
                                    self.trigger_foul(attacker_id, attacker, defender_id, defender)
                                    break
                                defender["stun_frames"] = random.randint(14, 20)
                                defender["stun_speed_mult"] = 0.45
                                defender["stun_type"] = "MISSED_TACKLE"
                                defender["x"] += nx_def * 0.8
                                defender["y"] += ny_def * 0.8
                                self._log(f"Agentul {defender_id} a faultat usor sau a fost fentat")

        # ==================================================
        # ------------ SISTEMUL ANTI-COLLIDE ---------------
        # ==================================================



        # miscarea mingii
        # 1. aplicam viteza
        self.ball['x'] += self.ball['velocity_x']
        self.ball['y'] += self.ball['velocity_y']
        # 2. aplicam frecarea
        self.ball['velocity_x'] *= 0.95
        self.ball['velocity_y'] *= 0.95

        # Daca o pasa s-a oprit / a pierdut elanul (viteza sub 0.18), mingea devine libera pentru oricine
        ball_current_speed = math.hypot(self.ball['velocity_x'], self.ball['velocity_y'])
        if self.intended_receiver is not None and ball_current_speed < 0.18:
            self.intended_receiver = None
            self.offside_pending = False

        # ==================================================
        # VERIFICARE ACTIVARE OFSAID (ARBITRU + VAR)
        # ==================================================
        if self.game_status == STATUS_PLAYING and self.offside_pending and self.offside_receiver_id in self.players:
            off_rec = self.players[self.offside_receiver_id]
            dist_off_rec = self.calculate_distance(off_rec["x"], off_rec["y"], self.ball["x"], self.ball["y"])
            if dist_off_rec < 3.2:
                self._log(f"OFSAID! Jucatorul {self.offside_receiver_id} a fost surprins in afara jocului (Linia VAR: {self.offside_line_x:.1f}m)!")
                off_team_stat = off_rec.get("team")
                if off_team_stat in self.stats:
                    self.stats[off_team_stat]["offsides"] += 1
                self.pass_in_flight_team = None
                self.game_status = STATUS_OFFSIDE
                self.offside_pending = False
                self.possession = None
                self.intended_receiver = None
                self.last_touch = self.offside_receiver_id
                self.restart_ready = False
                self.restart_ball_placed = False
                self.restart_start_time = self._now()
                self.restart_ball_x = self.offside_spot_x
                self.restart_ball_y = self.offside_spot_y
                self.ball["velocity_x"] *= 0.22
                self.ball["velocity_y"] *= 0.22

        # verificam daca mingea e libera sau in posesia cuiva
        if self.possession is not None:
            possessor_data = self.players[self.possession]
            # Daca posesorul este portarul care tine mingea, mingea ramane lipita de el
            if possessor_data.get("role") == "GK" and possessor_data.get("state") in [STATE_GK_HOLD_BALL, STATE_GK_DEFEND_GOAL]:
                offset_x = 0.5 if possessor_data["x"] < 50.0 else -0.5
                self.ball["x"] = possessor_data["x"] + offset_x
                self.ball["y"] = possessor_data["y"]
                self.ball["velocity_x"] = 0.0
                self.ball["velocity_y"] = 0.0
            else:
                distance_possessor_to_ball = self.calculate_distance(possessor_data["x"], possessor_data["y"], self.ball["x"], self.ball["y"])
                if distance_possessor_to_ball > 3.0:
                    self.possession = None

        # ==================================================
        # ------ SISTEMUL ANTI-COLLIDE JUCATOR-MINGE -------
        # ==================================================

        for player_id, player_data in self.players.items():
            
            # Daca jucatorul abia a ratat un tackle sau a fost depasit in dribling (stun_frames > 0),
            # nu blocheaza driblingul scurt al purtatorului de minge (STATE_DRIBBLE / STATE_CONTROL_BALL),
            # DAR poate bloca / intercepta pasele sau suturile trimise direct prin el!
            if player_data["stun_frames"] > 0 and self.kick_action in [STATE_DRIBBLE, STATE_CONTROL_BALL]:
                continue

            is_gk = (player_data.get("role") == "GK" or player_id in ["1", "101"])
            if self.game_status != STATUS_PLAYING:
                break
            collision_radius = GK_SAVE_RADIUS if is_gk else OUTFIELD_BALL_RADIUS

            distance_to_ball = self.calculate_distance(player_data["x"], player_data["y"], self.ball["x"], self.ball["y"])

            # pragul de coliziune
            if distance_to_ball < collision_radius and player_id != self.possession:
                
                dx = self.ball["x"] - player_data["x"]
                dy = self.ball["y"] - player_data["y"]

                dot_product = dx * self.ball["velocity_x"] + dy * self.ball["velocity_y"]

                # mingea se indreapta spre jucator
                if dot_product < 0:
                    
                    # calculam viteza mingii inainte de impact
                    ball_speed = math.hypot(self.ball["velocity_x"], self.ball["velocity_y"])

                    # ========================================================
                    # INTERVENTIE PORTAR (SPECIALIZATA PENTRU REALISM FOTBAL)
                    # ========================================================
                    if is_gk:
                        # Daca sutul este bine plasat la distanta de centrul portarului (> 1.42m) si puternic (>= 2.15),
                        # mingea poate trece pe sub / pe langa varful manusilor direct in plasa (30% sansa de gol la colt)!
                        if self.kick_action == STATE_KICK and ball_speed >= 2.15 and distance_to_ball > 1.42:
                            if random.random() < 0.30:
                                continue

                        self.offside_pending = False
                        self.pass_in_flight_team = None
                        gk_team = player_data.get("team")
                        # Contorizam parada portarului daca a oprit un sut advers
                        if gk_team in self.stats and self.kicking_team is not None and self.kicking_team != gk_team:
                            if self.kick_action == STATE_KICK or ball_speed >= 1.25:
                                self.stats[gk_team]["saves"] += 1
                        # 1. Prindere sigura daca mingea e usoara/medie SAU vine fix in corpul portarului (< 0.95m)
                        if ball_speed < GK_CATCH_SPEED_THRESHOLD or distance_to_ball < 0.95:
                            self.ball["velocity_x"] = 0.0
                            self.ball["velocity_y"] = 0.0
                            self.ball["x"] = player_data["x"] + (0.5 if player_data["x"] < 50.0 else -0.5)
                            self.ball["y"] = player_data["y"]
                            self.last_touch = player_id
                            self.possession = player_id
                            self.intended_receiver = None
                            self._log(f"Portarul {player_id} a retinut mingea sigur in brate!")
                            break

                        # 2. Sut tare -> Portarul intervine (50% Corner, 30% Rebound, 20% Prindere)
                        save_roll = random.random()
                        if save_roll < GK_PARRY_CORNER_CHANCE:
                            # DEVIERE IN CORNER: Portarul impinge mingea peste linia de fund, pe langa bara sau peste transversala
                            self.last_touch = player_id
                            self.possession = None
                            self.intended_receiver = None

                            deflection_side = -1.0 if self.ball["y"] < 50.0 else 1.0
                            vy_push = deflection_side * random.uniform(1.3, 2.3)
                            
                            left_team_gk = "A" if self.half == 1 else "B"
                            if player_data["team"] == left_team_gk:
                                # Apara poarta din stanga (x <= 0). Mingea e deviata spre x <= 0
                                self.ball["velocity_x"] = random.uniform(-2.2, -1.3)
                                self.ball["velocity_y"] = vy_push
                            else:
                                # Apara poarta din dreapta (x >= 100). Mingea e deviata spre x >= 100
                                self.ball["velocity_x"] = random.uniform(1.3, 2.2)
                                self.ball["velocity_y"] = vy_push

                            self._log(f"Parada spectaculoasa a portarului {player_id}! Mingea este deviata in CORNER!")
                            break

                        elif save_roll < (GK_PARRY_CORNER_CHANCE + GK_PARRY_REBOUND_CHANCE):
                            # RESPINGERE IN FATA PORTII (REBOUND): mingea este blocata si sare in careu
                            self.last_touch = player_id
                            self.possession = None
                            self.intended_receiver = None

                            left_team_gk = "A" if self.half == 1 else "B"
                            if player_data["team"] == left_team_gk:
                                self.ball["velocity_x"] = random.uniform(0.6, 1.2)  # sare inapoi spre teren
                            else:
                                self.ball["velocity_x"] = random.uniform(-1.2, -0.6)

                            self.ball["velocity_y"] = random.uniform(-0.8, 0.8)
                            self._log(f"Reflex excelent al portarului {player_id}! Respingere in fata portii (rebound)!")
                            break

                        else:
                            # PRINDERE LA SUT TARE
                            self.ball["velocity_x"] = 0.0
                            self.ball["velocity_y"] = 0.0
                            self.ball["x"] = player_data["x"] + (0.5 if player_data["x"] < 50.0 else -0.5)
                            self.ball["y"] = player_data["y"]
                            self.last_touch = player_id
                            self.possession = player_id
                            self.intended_receiver = None
                            self._log(f"Portarul {player_id} retine un sut puternic!")
                            break

                    # ========================================================
                    # INTERVENTIE JUCATOR DE CAMP
                    # ========================================================
                    else:
                        player_team = player_data.get("team")
                        kicker_team = self.kicking_team or (self.players[str(self.last_touch)]["team"] if str(self.last_touch) in self.players else None)
                        is_teammate = (player_team is not None and kicker_team is not None and player_team == kicker_team)
                        is_intended_receiver = (self.intended_receiver is not None and str(player_id) == str(self.intended_receiver))

                        # 1. Preluare curata pentru coechipier sau destinatar:
                        # O pasa sau minge trimisa de un coechipier NU ricoseaza NICIODATA, indiferent de forta!
                        if is_teammate or is_intended_receiver:
                            if self.pass_in_flight_team == player_team and str(player_id) != self.pass_in_flight_sender and player_team in self.stats:
                                self.stats[player_team]["passes_completed"] += 1
                            self.pass_in_flight_team = None
                            self.pass_in_flight_sender = None
                            self.ball["velocity_x"] = 0.0
                            self.ball["velocity_y"] = 0.0
                            self.last_touch = player_id
                            self.possession = player_id
                            self.intended_receiver = None
                            self.kicking_team = player_team
                            self.kick_action = None
                            break # oprim cautarea ca sa nu loveasca 2 jucatori in aceeasi milisecunda

                        # 2. Interventie adversar:
                        else:
                            # Daca sutul provine dintr-o LOVITURA LIBERA DIRECTA (STATUS_FREE_KICK),
                            # mingea este lovita cu efect PESTE ZID (traiectorie inalta in primii 11.5m),
                            # deci zidul blocheaza mingea doar daca trece foarte aproape de centrul unui jucator (< 0.62m) si nu sare peste!
                            if self.last_set_piece_status == STATUS_FREE_KICK and self.kick_action == STATE_KICK:
                                dist_from_fk = self.calculate_distance(player_data["x"], player_data["y"], self.restart_ball_x, self.restart_ball_y)
                                if dist_from_fk < 11.5 and (distance_to_ball > 0.62 or random.random() < 0.65):
                                    continue

                            self.offside_pending = False
                            self.pass_in_flight_team = None
                            self.pass_in_flight_sender = None
                            # A. Blocaj defensiv la SUT puternic pe poarta (STATE_KICK, viteza >= 2.2) => Ricoseu / Deviere
                            if self.kick_action == STATE_KICK and ball_speed >= 2.2:
                                self.ball["velocity_x"] *= random.uniform(-0.5, 0.3)
                                # deviem mingea random, inspre margine
                                deflection_y = random.choice([-1, 1])
                                self.ball["velocity_y"] = deflection_y * random.uniform(ball_speed * 0.8, ball_speed * 1.5)
                                self.last_touch = player_id
                                self.possession = None
                                self.intended_receiver = None
                                self.kicking_team = player_team
                                self.kick_action = None
                                break
                            # B. Interceptie curata de catre adversar (pasa, degajare, minge libera)
                            else:
                                self.ball["velocity_x"] = 0.0
                                self.ball["velocity_y"] = 0.0
                                self.last_touch = player_id
                                self.possession = player_id
                                self.intended_receiver = None
                                self.kicking_team = player_team
                                self.kick_action = None
                                break

        # ==================================================
        # ------ SISTEMUL ANTI-COLLIDE JUCATOR-MINGE -------
        # ==================================================

        # ==================================================
        # VERIFICAREA IESIRII DIN TEREN (DOAR IN TIMPUL JOCULUI ACTIV)
        # ==================================================
        if self.game_status == STATUS_PLAYING:
            # Contorizam posesia reala pe fiecare tick de joc activ
            if self.possession in self.players:
                p_t = self.players[self.possession].get("team")
                if p_t in self.stats:
                    self.stats[p_t]["possession_ticks"] += 1
            elif self.kicking_team in self.stats:
                self.stats[self.kicking_team]["possession_ticks"] += 1

            left_team = "A" if self.half == 1 else "B"
            right_team = "B" if self.half == 1 else "A"

            # GOL in poarta din STANGA (x <= 0) -> marcheaza right_team!
            if self.ball['x'] <= 0:
                self.offside_pending = False
                if self.ball['y'] >= 41.0 and self.ball['y'] <= 59.0:
                    self._log("GOAL!!! GOAL!!! GOAL!!!")
                    self.game_status = STATUS_GOAL
                    self.possession = None
                    self.intended_receiver = None
                    self.goal_time = self._now()
                    self.goal_ball_centered = False
                    # Lasam mingea sa intre si sa se opreasca in plasa portii pentru 3.5 secunde
                    self.ball['velocity_x'] = max(-0.45, self.ball['velocity_x'] * 0.35)
                    self.ball['velocity_y'] *= 0.25
                    self.kickoff_team = left_team
                    if right_team == "B":
                        self.score_B += 1
                    else:
                        self.score_A += 1
                else:
                    # Mingea a iesit in spatele portii din STANGA (aparata de left_team)
                    last_touch_team = self.players[str(self.last_touch)]["team"] if str(self.last_touch) in self.players else right_team
                    self.possession = None
                    self.intended_receiver = None
                    self.ball['velocity_x'] *= 0.35
                    self.ball['velocity_y'] *= 0.35
                    self.restart_ready = False
                    self.restart_ball_placed = False
                    self.restart_start_time = self._now()
                    
                    if last_touch_team == left_team:
                        # Echipa care apara stanga a atins ultima -> CORNER pentru right_team
                        self._log(f"CORNER pentru Echipa {right_team}!")
                        self.pass_in_flight_team = None
                        if right_team in self.stats:
                            self.stats[right_team]["corners"] += 1
                        self.game_status = STATUS_CORNER
                        self.restart_ball_x = 1.0
                        self.restart_ball_y = 1.0 if self.ball['y'] < 50.0 else 99.0
                    else:
                        # Adversarul a scos-o -> AUT DE POARTA pentru left_team
                        self._log(f"AUT DE POARTA pentru Echipa {left_team}!")
                        self.game_status = STATUS_GOAL_KICK
                        self.restart_ball_x = 6.0
                        self.restart_ball_y = 50.0

            # GOL in poarta din DREAPTA (x >= 100) -> marcheaza left_team!
            elif self.ball['x'] >= 100:
                self.offside_pending = False
                if self.ball['y'] >= 41.0 and self.ball['y'] <= 59.0:
                    self._log("GOAL!!! GOAL!!! GOAL!!!")
                    self.game_status = STATUS_GOAL
                    self.possession = None
                    self.intended_receiver = None
                    self.goal_time = self._now()
                    self.goal_ball_centered = False
                    # Lasam mingea sa intre si sa se opreasca in plasa portii pentru 3.5 secunde
                    self.ball['velocity_x'] = min(0.45, self.ball['velocity_x'] * 0.35)
                    self.ball['velocity_y'] *= 0.25
                    self.kickoff_team = right_team
                    if left_team == "A":
                        self.score_A += 1
                    else:
                        self.score_B += 1
                else:
                    # Mingea a iesit in spatele portii din DREAPTA (aparata de right_team)
                    last_touch_team = self.players[str(self.last_touch)]["team"] if str(self.last_touch) in self.players else left_team
                    self.possession = None
                    self.intended_receiver = None
                    self.ball['velocity_x'] *= 0.35
                    self.ball['velocity_y'] *= 0.35
                    self.restart_ready = False
                    self.restart_ball_placed = False
                    self.restart_start_time = self._now()
                    
                    if last_touch_team == right_team:
                        # Echipa care apara dreapta a atins ultima -> CORNER pentru left_team
                        self._log(f"CORNER pentru Echipa {left_team}!")
                        self.pass_in_flight_team = None
                        if left_team in self.stats:
                            self.stats[left_team]["corners"] += 1
                        self.game_status = STATUS_CORNER
                        self.restart_ball_x = 99.0
                        self.restart_ball_y = 1.0 if self.ball['y'] < 50.0 else 99.0
                    else:
                        # Adversarul a scos-o -> AUT DE POARTA pentru right_team
                        self._log(f"AUT DE POARTA pentru Echipa {right_team}!")
                        self.game_status = STATUS_GOAL_KICK
                        self.restart_ball_x = 94.0
                        self.restart_ball_y = 50.0

            # AUT DE MARGINE (SUS: y <= 0)
            elif self.ball['y'] <= 0:
                self._log("Out de margine!")     
                self.offside_pending = False
                self.game_status = STATUS_OUT
                self.restart_ready = False
                self.restart_ball_placed = False
                self.restart_start_time = self._now()
                self.possession = None
                self.intended_receiver = None
                self.restart_ball_x = max(2.0, min(98.0, self.ball['x']))
                self.restart_ball_y = 1.0
                self.ball['velocity_x'] *= 0.35
                self.ball['velocity_y'] *= 0.35

            # AUT DE MARGINE (JOS: y >= 100)
            elif self.ball['y'] >= 100:
                self._log("Out de margine!")       
                self.offside_pending = False
                self.game_status = STATUS_OUT
                self.restart_ready = False
                self.restart_ball_placed = False
                self.restart_start_time = self._now()
                self.possession = None
                self.intended_receiver = None
                self.restart_ball_x = max(2.0, min(98.0, self.ball['x']))
                self.restart_ball_y = 99.0
                self.ball['velocity_x'] *= 0.35
                self.ball['velocity_y'] *= 0.35

        # calculam timpul virtual curent (inghetat la 45:00 pe durata pauzei si a intrarii in Repriza a 2-a)
        virtual_minutes = 0.0
        if self.start_time is not None:
            if self.game_status == STATUS_HALF_TIME or self.second_half_wait_start is not None:
                virtual_minutes = 45.0
            else:
                real_elapsed = max(0.0, (self._now() - self.start_time) - self.paused_real_seconds)
                virtual_minutes = (real_elapsed / self.match_duration_real_seconds) * 90.0
                if self.half == 1 and virtual_minutes > 45.0:
                    virtual_minutes = 45.0
                elif virtual_minutes > 90.0:
                    virtual_minutes = 90.0

        # ==================================================
        # --------- LOGICA DE HALF TIME (MIN 45:00) --------
        # ==================================================
        if self.game_mode != "scenarios" and self.half == 1 and virtual_minutes >= 45.0 and self.game_status == STATUS_PLAYING:
            self._log("HALF TIME! Fluier de pauza la minutul 45:00. Jucatorii merg spre vestiare.")
            self.game_status = STATUS_HALF_TIME
            self.halftime_start_time = self._now()
            self.possession = None
            self.intended_receiver = None
            self.offside_pending = False
            self.kickoff_pending = False
            self.ball['velocity_x'] *= 0.2
            self.ball['velocity_y'] *= 0.2
        
        # ==================================================
        # -------------- LOGICA DE MATCH OVER --------------
        # ==================================================
        # Daca timpul a atins 90 minute (si nu suntem in modul Tactical Scenarios sau deja in match over)
        if self.game_mode != "scenarios" and self.half == 2 and virtual_minutes >= 90.0 and self.game_status != STATUS_MATCH_OVER:
            self._log("MATCH OVER! Fluier final. Jucatorii merg la vestiare, statisticile ingheata.")
            self.game_status = STATUS_MATCH_OVER
            self.possession = None
            self.intended_receiver = None
            self.offside_pending = False
            self.kickoff_pending = False
            self.pass_in_flight_team = None
            self.pass_in_flight_sender = None

        if self.game_status == STATUS_MATCH_OVER:
            # Oprim complet mingea la finalul meciului
            self.ball['velocity_x'] *= 0.80
            self.ball['velocity_y'] *= 0.80
            if abs(self.ball['velocity_x']) < 0.02:
                self.ball['velocity_x'] = 0.0
            if abs(self.ball['velocity_y']) < 0.02:
                self.ball['velocity_y'] = 0.0

        # broadcast al jocului
        # dupa ce am facut update-ul agentilor
        game_state = {
            "ball" : self.ball,
            "players" : self.players,
            "game_status" : self.game_status,
            "half" : self.half,
            "last_touch" : self.last_touch,
            "possession" : self.possession,
            "kickoff_team" : self.kickoff_team,
            "kickoff_pending" : self.kickoff_pending,
            "intended_receiver" : self.intended_receiver,
            "score_A" : self.score_A,
            "score_B" : self.score_B,
            "time" : virtual_minutes,
            "restart_ready" : self.restart_ready,
            "restart_ball_placed" : self.restart_ball_placed,
            "restart_ball_x" : self.restart_ball_x,
            "restart_ball_y" : self.restart_ball_y,
            "offside_line_x" : self.offside_line_x,
            "offside_spot_x" : self.offside_spot_x,
            "offside_spot_y" : self.offside_spot_y,
            "offside_defending_team" : self.offside_defending_team,
            "foul_spot_x" : self.foul_spot_x,
            "foul_spot_y" : self.foul_spot_y,
            "foul_attacking_team" : self.foul_attacking_team,
            "foul_defending_team" : self.foul_defending_team,
            "match_stats" : (None if self.headless else self.get_stats_summary()),
            "team_A_name" : self.team_A_name,
            "team_B_name" : self.team_B_name,
            "team_A_ai" : self.team_A_ai,
            "team_B_ai" : self.team_B_ai,
            "game_mode" : self.game_mode,
            "active_scenario" : self.active_scenario,
            "scenario_countdown_left" : self.scenario_countdown_left,
            "sim_time" : self._now()
        }
        
        

        return game_state

    def run(self):
        # 1. BUCLA PRINCIPALA A JOCULUI (Tine serverul viu la infinit)
        while True:
            # BUCLA SECUNDARA DE DRENARE A COZII
            while True:
                # Verificam daca sunt mesaje de la jucatori
                events = dict(self.poller.poll(timeout=0))
                # verificam daca un agent a trimis o cerere
                if self.router_socket in events:
                    message = self.router_socket.recv_multipart()
                    agent_identity, agent_message = message
                    intention = json.loads(agent_message.decode('utf-8'))

                    # Comanda directa de la Visualizer pentru incarcarea instantanee a unei faze (Tactical Scenarios)
                    if intention.get("command") == "LOAD_SCENARIO":
                        sc_name = str(intention.get("scenario", SCENARIO_1V1_GK))
                        self.load_scenario(sc_name)
                        reply_bytes = json.dumps({"status": "scenario_loaded", "scenario": sc_name}).encode('utf-8')
                        self.router_socket.send_multipart([agent_identity, reply_bytes])
                        continue

                    # Comanda de la butonul "RESUME MATCH" din ecranul de pauza (HALF TIME -> Repriza a 2-a)
                    if intention.get("command") == "RESUME_SECOND_HALF":
                        if self.game_status == STATUS_HALF_TIME:
                            self.start_second_half()
                        reply_bytes = json.dumps({"status": "second_half_started"}).encode('utf-8')
                        self.router_socket.send_multipart([agent_identity, reply_bytes])
                        continue

                    self.process_intention(intention)
                    reply_bytes = json.dumps({"status": "approved"}).encode('utf-8')
                    self.router_socket.send_multipart([agent_identity, reply_bytes])
                else:
                    break

            game_state = self.step_tick()
            self.pub_socket.send_json(game_state)
            # delay pentru a limita FPS-ul
            time.sleep(0.05)

    def load_scenario(self, scenario_name):
        """
        Plaseaza instantaneu toti cei 22 de jucatori si mingea intr-o faza "mid-match" (Tactical Scenarios)
        si porneste numaratoarea inversa 3, 2, 1 inainte de fluierul arbitrului.
        """
        self._log(f"Incarcam faza tactica: {scenario_name} (3, 2, 1...)")
        self.active_scenario = scenario_name
        self.scenario_countdown_start = self._now()
        self.scenario_countdown_left = 3
        self.scenario_play_start = None
        self.scenario_end_timer = None
        self.scenario_phase_step = 0
        self.game_status = STATUS_SCENARIO_COUNTDOWN
        self.offside_pending = False
        self.offside_receiver_id = None
        self.offside_line_x = None
        self.intended_receiver = None
        self.kick_action = None
        self.kickoff_pending = False
        self.goal_ball_centered = True
        self.restart_ready = True
        self.restart_ball_placed = True
        self.ball["velocity_x"] = 0.0
        self.ball["velocity_y"] = 0.0

        # Resetam intai toti jucatorii la pozitiile de baza si curatam starile/stun-ul
        for pid, pdata in self.players.items():
            pdata["x"] = float(pdata["start_x"])
            pdata["y"] = float(pdata["start_y"])
            pdata["state"] = STATE_IDLE
            pdata["stun_frames"] = 0
            pdata.pop("target_x", None)
            pdata.pop("target_y", None)

        def set_pos(pid, x, y):
            if str(pid) in self.players:
                self.players[str(pid)]["x"] = float(x)
                self.players[str(pid)]["y"] = float(y)

        # =====================================================================
        # 1. 1v1 GK: Atacantul (#10) scapa singur cu portarul (#101) de la 21m
        # =====================================================================
        if scenario_name == SCENARIO_1V1_GK:
            self.scenario_post_status = STATUS_PLAYING
            y_var = random.uniform(47.0, 53.0)
            set_pos("1", 4.0, 50.0)
            set_pos("2", 42.0, 86.0)
            set_pos("3", 38.0, 62.0)
            set_pos("4", 38.0, 38.0)
            set_pos("5", 42.0, 14.0)
            set_pos("6", 62.0, 72.0)
            set_pos("7", 56.0, 50.0)
            set_pos("8", 62.0, 28.0)
            set_pos("9", 71.0, 76.0)
            set_pos("11", 71.0, 24.0)
            set_pos("10", 79.0, y_var)  # Varful #10 singur cu portarul!

            set_pos("101", 97.5, 50.0)  # Portarul advers pe linia portii
            set_pos("102", 69.0, 84.0)
            set_pos("103", 67.5, 62.0)  # Fundasii centrali batuti in viteza, urmaresc din spate
            set_pos("104", 67.5, 38.0)
            set_pos("105", 69.0, 16.0)
            set_pos("106", 54.0, 65.0)
            set_pos("107", 54.0, 35.0)
            set_pos("108", 48.0, 78.0)
            set_pos("109", 48.0, 22.0)
            set_pos("110", 42.0, 60.0)
            set_pos("111", 42.0, 40.0)

            self.ball["x"] = 79.4
            self.ball["y"] = y_var
            self.possession = "10"
            self.last_touch = "10"
            self.kicking_team = "A"

        # =====================================================================
        # 2. OFFSIDE (VAR): Pasatorul (#8) la mijlocul terenului (x = 48.0, y = 52.0),
        #    blocat frontal de #106/#107 pe dreapta, dar cu un CULOAR DIAGONAL PERFECT LIBER
        #    catre varful (#10) la (66.5, 34.0), aflat clar in OFSAID fata de linia 62.0!
        # =====================================================================
        elif scenario_name == SCENARIO_OFFSIDE_VAR:
            self.scenario_post_status = STATUS_PLAYING
            set_pos("1", 4.0, 50.0)
            set_pos("2", 26.0, 84.0)
            set_pos("3", 24.0, 60.0)
            set_pos("4", 24.0, 38.0)
            set_pos("5", 26.0, 14.0)
            set_pos("6", 35.0, 74.0)
            set_pos("7", 34.0, 52.0)
            set_pos("8", 48.0, 52.0)   # #8 are mingea la mijloc si culoar diagonal 100% liber spre #10!
            set_pos("9", 38.0, 86.0)
            set_pos("11", 37.0, 14.0)
            set_pos("10", 66.5, 34.0)  # #10 este complet demarcat pe culoar, cu 4.5m in OFSAID fata de linia 62.0!

            set_pos("101", 97.5, 50.0)
            # Linia defensiva adversa la Offside Trap (x = 62.0), cu spatiu larg intre #103 (y=58) si #104 (y=18)
            set_pos("102", 62.0, 82.0)
            set_pos("103", 62.0, 58.0)
            set_pos("104", 62.0, 18.0)
            set_pos("105", 62.0, 8.0)
            # Mijlocasii #106 si #107 inchid avansarea lui #8 pe centru-dreapta (y=55..66), lasand culoarul spre #10 (y=34) complet liber!
            set_pos("106", 54.5, 55.5)
            set_pos("107", 53.5, 66.0)
            set_pos("108", 47.0, 78.0)
            set_pos("109", 44.0, 14.0)
            set_pos("110", 38.0, 62.0)
            set_pos("111", 38.0, 26.0)

            self.ball["x"] = 48.4
            self.ball["y"] = 52.0
            self.possession = "8"
            self.last_touch = "8"
            self.kicking_team = "A"
            self.offside_line_x = 62.0

        # =====================================================================
        # 3. CORNER: Corner ofensiv pentru Echipa Rosii (A) cu jucatorii in careu
        # =====================================================================
        elif scenario_name == SCENARIO_CORNER:
            self.scenario_post_status = STATUS_CORNER
            set_pos("1", 4.0, 50.0)
            set_pos("2", 52.0, 68.0)
            set_pos("3", 52.0, 32.0)
            set_pos("4", 90.5, 39.0)    # Ataca coltul scurt (near post) cu culoar deschis
            set_pos("5", 88.0, 18.0)    # Optiune de corner scurt / diagonala
            set_pos("6", 81.5, 48.0)    # Marginea careului central (18m) pentru sut
            set_pos("7", 82.5, 32.0)    # Marginea careului stanga-centru (16m)
            set_pos("8", 88.0, 46.5)    # Punctul cu var (11m)
            set_pos("9", 90.5, 59.0)    # Coltul lung (far post)
            set_pos("10", 91.0, 51.5)   # Central in fata portii (9m)
            set_pos("11", 98.2, 2.0)    # #11 executa cornerul de la fanionul (99, 1)

            set_pos("101", 98.0, 50.0)
            # Aparatorii stau goal-side (intre atacanti si poarta, la x=93..95.5) ca sa apere poarta fara a bloca centrarea
            set_pos("102", 95.5, 55.0)
            set_pos("103", 94.0, 51.0)
            set_pos("104", 93.5, 46.0)
            set_pos("105", 95.5, 43.0)
            set_pos("106", 86.0, 52.0)
            set_pos("107", 93.0, 41.0)
            set_pos("108", 93.0, 59.0)
            set_pos("109", 84.5, 38.0)
            set_pos("110", 72.0, 44.0)
            set_pos("111", 72.0, 56.0)

            self.ball["x"] = 99.0
            self.ball["y"] = 1.0
            self.restart_ball_x = 99.0
            self.restart_ball_y = 1.0
            self.restart_ball_placed = True
            self.restart_ready = True
            self.possession = None
            self.last_touch = "103"    # Ultima atingere B -> Corner pentru A!
            self.kicking_team = "A"

        # =====================================================================
        # 4. COUNTER-ATTACK: Contraatac fulgerator (5 atacanti raspanditi natural vs 2 fundasi)
        # =====================================================================
        elif scenario_name == SCENARIO_TIKI_TAKA:
            self.scenario_post_status = STATUS_PLAYING
            jx = lambda v: v + random.uniform(-1.4, 1.4)
            jy = lambda v: v + random.uniform(-1.8, 1.8)
            set_pos("1", 4.0, 50.0)
            set_pos("2", jx(37.0), jy(83.0))
            set_pos("3", jx(31.0), jy(59.0))
            set_pos("4", jx(34.5), jy(35.0))
            set_pos("5", jx(41.0), jy(16.0))
            set_pos("7", jx(46.5), jy(52.0))
            # Cei 5 jucatori de atac lansati asimetric pe contraatac:
            set_pos("6", jx(53.5), jy(64.0))   # Interul #6 vine din spate pe centru-dreapta
            b_x, b_y = jx(56.5), jy(43.0)
            set_pos("8", b_x, b_y)             # #8 conduce contraatacul cu mingea la picior
            set_pos("9", jx(61.0), jy(77.0))   # Extrema dreapta #9 urca larg pe flanc
            set_pos("11", jx(65.5), jy(22.0))  # Extrema stanga #11 sprinteaza mai avansat in stanga
            set_pos("10", jx(67.0), jy(53.0))  # Varful #10 ataca spatiul central (onside!)

            set_pos("101", 97.5, 50.0)
            # Doar 2 fundasi adversi (#103, #104) surprinsi asimetric in spate!
            set_pos("103", jx(75.0), jy(56.0))
            set_pos("104", jx(72.5), jy(37.5))
            # Restul echipei B a fost surprinsa in jumatatea adversa si alearga inapoi dezordonat
            set_pos("102", jx(49.0), jy(86.0))
            set_pos("105", jx(52.5), jy(13.0))
            set_pos("106", jx(44.5), jy(68.0))
            set_pos("107", jx(47.0), jy(31.0))
            set_pos("108", jx(39.0), jy(79.0))
            set_pos("109", jx(42.5), jy(19.0))
            set_pos("110", jx(35.0), jy(55.0))
            set_pos("111", jx(37.5), jy(41.0))

            self.ball["x"] = b_x + 0.4
            self.ball["y"] = b_y
            self.possession = "8"
            self.last_touch = "8"
            self.kicking_team = "A"

        # =====================================================================
        # 5. GOAL KICK: Constructie de la portar sub pressing avansat
        # =====================================================================
        elif scenario_name == SCENARIO_GOAL_KICK:
            self.scenario_post_status = STATUS_GOAL_KICK
            set_pos("1", 5.2, 50.0)
            set_pos("3", 14.0, 65.0)
            set_pos("4", 14.0, 35.0)
            set_pos("2", 28.0, 88.0)
            set_pos("5", 28.0, 12.0)
            set_pos("7", 36.0, 50.0)
            set_pos("6", 42.0, 75.0)
            set_pos("8", 42.0, 25.0)
            set_pos("9", 58.0, 75.0)
            set_pos("10", 62.0, 50.0)
            set_pos("11", 58.0, 25.0)

            set_pos("101", 98.0, 50.0)
            set_pos("102", 65.0, 85.0)
            set_pos("103", 65.0, 60.0)
            set_pos("104", 65.0, 40.0)
            set_pos("105", 65.0, 15.0)
            set_pos("106", 44.0, 65.0)
            set_pos("107", 44.0, 35.0)
            set_pos("108", 44.0, 80.0)
            set_pos("109", 44.0, 20.0)
            set_pos("110", 22.0, 62.0)
            set_pos("111", 22.0, 38.0)

            self.ball["x"] = 6.0
            self.ball["y"] = 50.0
            self.restart_ball_x = 6.0
            self.restart_ball_y = 50.0
            self.restart_ball_placed = True
            self.restart_ready = True
            self.possession = None
            self.last_touch = "110"    # Ultima atingere B -> Aut de poarta pentru A!
            self.kicking_team = "A"

        # =====================================================================
        # 6. THROW-IN: Aut de margine ofensiv in treimea adversa
        # =====================================================================
        elif scenario_name == SCENARIO_THROW_IN:
            self.scenario_post_status = STATUS_OUT
            set_pos("1", 4.0, 50.0)
            set_pos("2", 48.0, 72.0)
            set_pos("3", 45.0, 52.0)
            set_pos("4", 45.0, 32.0)
            set_pos("5", 68.0, 1.5)    # #5 bate autul de margine de la (68, 1)
            set_pos("6", 64.0, 55.0)
            set_pos("7", 60.0, 28.0)
            set_pos("8", 63.0, 13.0)   # #8 vine scurt la aut
            set_pos("9", 76.0, 68.0)
            set_pos("10", 77.0, 32.0)  # #10 ataca spatiul central-stanga
            set_pos("11", 74.0, 11.0)  # #11 optiune pe tusa

            set_pos("101", 98.0, 50.0)
            set_pos("102", 82.0, 72.0)
            set_pos("103", 80.0, 48.0)
            set_pos("104", 79.0, 32.0)
            set_pos("105", 76.0, 13.0)
            set_pos("106", 68.0, 48.0)
            set_pos("107", 65.0, 16.0)
            set_pos("108", 64.0, 68.0)
            set_pos("109", 62.0, 28.0)
            set_pos("110", 52.0, 55.0)
            set_pos("111", 52.0, 35.0)

            self.ball["x"] = 68.0
            self.ball["y"] = 1.0
            self.restart_ball_x = 68.0
            self.restart_ball_y = 1.0
            self.restart_ball_placed = True
            self.restart_ready = True
            self.possession = None
            self.last_touch = "105"    # Ultima atingere B -> Aut pentru A!
            self.kicking_team = "A"

        # =====================================================================
        # 7. PENALTY (11M): Lovitura de la 11m pentru Echipa Rosii (#10 vs #101)
        # =====================================================================
        elif scenario_name == SCENARIO_PENALTY:
            self.scenario_post_status = STATUS_PENALTY
            self.foul_attacking_team = "A"
            self.foul_defending_team = "B"
            self.foul_spot_x = 90.0
            self.foul_spot_y = 50.0

            set_pos("1", 4.0, 50.0)
            set_pos("2", 52.0, 72.0)
            set_pos("3", 50.0, 55.0)
            set_pos("4", 50.0, 45.0)
            set_pos("5", 52.0, 28.0)
            # Jucatorii de camp aliniati regulamentar in afara careului de 16m si a semicercului (x < 85.0)
            set_pos("6", 83.5, 65.0)
            set_pos("7", 79.5, 52.0)
            set_pos("8", 82.0, 40.0)
            set_pos("9", 85.0, 72.0)
            set_pos("11", 85.0, 28.0)
            set_pos("10", 88.2, 50.0)   # #10 pregatit la punctul cu var (90, 50)!

            set_pos("101", 98.5, 50.0)  # Portarul #101 pe linia portii!
            set_pos("102", 84.5, 69.0)
            set_pos("103", 82.5, 58.0)
            set_pos("104", 82.5, 42.0)
            set_pos("105", 84.5, 31.0)
            set_pos("106", 80.0, 55.0)
            set_pos("107", 80.0, 45.0)
            set_pos("108", 76.0, 68.0)
            set_pos("109", 76.0, 32.0)
            set_pos("110", 62.0, 58.0)
            set_pos("111", 62.0, 42.0)

            self.ball["x"] = 90.0
            self.ball["y"] = 50.0
            self.restart_ball_x = 90.0
            self.restart_ball_y = 50.0
            self.restart_ball_placed = True
            self.restart_ready = True
            self.possession = None
            self.last_touch = "103"
            self.kicking_team = "A"

        # =====================================================================
        # 8. FREE KICK (ZID): Lovitura libera directa de la ~21m cu ZID de 4 jucatori!
        # =====================================================================
        elif scenario_name == SCENARIO_FREE_KICK:
            self.scenario_post_status = STATUS_FREE_KICK
            self.foul_attacking_team = "A"
            self.foul_defending_team = "B"
            fk_x, fk_y = 79.5, 41.0
            self.foul_spot_x = fk_x
            self.foul_spot_y = fk_y

            set_pos("1", 4.0, 50.0)
            set_pos("2", 52.0, 76.0)
            set_pos("3", 46.0, 58.0)
            set_pos("4", 46.0, 42.0)
            set_pos("5", 55.0, 20.0)
            set_pos("7", 75.0, 50.5)    # #7 optiune de pasa scurta langa executant
            set_pos("6", 83.5, 62.0)    # #6 la marginea careului
            set_pos("8", fk_x - 1.5, fk_y - 0.5)  # #8 executa lovitura libera!
            set_pos("9", 86.5, 67.0)    # #9 ataca coltul lung
            set_pos("10", 86.5, 54.0)   # #10 pe linia careului pentru rebound / deviere
            set_pos("11", 85.0, 26.0)   # #11 deschis in stanga

            # Calculam pozitia exacta a ZIDULUI de 4 jucatori (#106, #107, #108, #109) la 9.15m de minge spre poarta (100, 50)
            dx_g = 100.0 - fk_x
            dy_g = 50.0 - fk_y
            d_g = math.hypot(dx_g, dy_g)
            ux, uy = dx_g / d_g, dy_g / d_g
            px, py = -uy, ux
            wall_cx = fk_x + ux * 9.15
            wall_cy = fk_y + uy * 9.15 - 0.6  # protejeaza coltul scurt
            wall_ids = ["106", "107", "108", "109"]
            for idx, wid in enumerate(wall_ids):
                off = (idx - (len(wall_ids) - 1) / 2.0) * 1.48
                set_pos(wid, wall_cx + px * off, wall_cy + py * off)

            set_pos("101", 98.2, 52.2)  # Portarul #101 acopera coltul lung!
            set_pos("102", 88.5, 68.0)
            set_pos("103", 88.5, 58.0)
            set_pos("104", 88.5, 51.0)
            set_pos("105", 87.5, 30.0)
            set_pos("110", 62.0, 56.0)
            set_pos("111", 62.0, 40.0)

            self.ball["x"] = fk_x
            self.ball["y"] = fk_y
            self.restart_ball_x = fk_x
            self.restart_ball_y = fk_y
            self.restart_ball_placed = True
            self.restart_ready = True
            self.possession = None
            self.last_touch = "106"
            self.kicking_team = "A"

    def trigger_foul(self, attacker_id, attacker, defender_id, defender):
        """
        Arbitrul fluiera FAULT!
        - Daca faultul este in interiorul careului de 16m advers -> PENALTY (STATUS_PENALTY, 11m).
        - Daca faultul este in afara careului -> LOVITURA LIBERA DIRECTA (STATUS_FREE_KICK, cu ZID).
        """
        foul_x = max(3.0, min(97.0, float(attacker["x"])))
        foul_y = max(4.0, min(96.0, float(attacker["y"])))
        att_team = str(attacker.get("team", "A"))
        def_team = str(defender.get("team", "B"))

        self.foul_spot_x = foul_x
        self.foul_spot_y = foul_y
        self.foul_attacking_team = att_team
        self.foul_defending_team = def_team
        self.pass_in_flight_team = None
        if def_team in self.stats:
            self.stats[def_team]["fouls"] += 1
        self.foul_cooldown_frames = 320  # Cooldown (~16s) pentru a mentine fluenta jocului
        self.offside_pending = False
        self.possession = None
        self.intended_receiver = None
        self.last_touch = str(defender_id)
        self.restart_ready = False
        self.restart_ball_placed = False
        self.restart_start_time = self._now()
        self.ball["velocity_x"] *= 0.20
        self.ball["velocity_y"] *= 0.20

        # Curatam stun-ul ca toti jucatorii sa se poata aseza in zid / careu
        for p in self.players.values():
            p["stun_frames"] = 0
            p["stun_speed_mult"] = 1.0
            p["stun_type"] = ""

        # Verificam daca faultul s-a produs in careul mare al echipei care se apara (coordonate careu: X<=12.5 sau X>=87.5, 31.5<=Y<=68.5)
        left_team_f = "A" if self.half == 1 else "B"
        right_team_f = "B" if self.half == 1 else "A"
        is_penalty = (
            (att_team == left_team_f and foul_x >= 87.5 and 31.5 <= foul_y <= 68.5)
            or (att_team == right_team_f and foul_x <= 12.5 and 31.5 <= foul_y <= 68.5)
        )

        if is_penalty:
            self.game_status = STATUS_PENALTY
            self.restart_ball_x = 90.0 if att_team == left_team_f else 10.0
            self.restart_ball_y = 50.0
            self._log(f"PENALTY pentru Echipa {att_team}! Fault comis de #{defender_id} asupra lui #{attacker_id} in careu!")
        else:
            self.game_status = STATUS_FREE_KICK
            self.restart_ball_x = foul_x
            self.restart_ball_y = foul_y
            self._log(f"FAULT! Lovitura libera directa pentru Echipa {att_team} la ({foul_x:.1f}, {foul_y:.1f})!")

    def get_second_last_defender_x(self, defending_team):
        # Returneaza coordonata X a penultimului aparator (inclusiv portarul) conform regulii FIFA de ofsaid
        right_team = "B" if self.half == 1 else "A"
        def_xs = [p["x"] for p in self.players.values() if p.get("team") == defending_team]
        if len(def_xs) < 2:
            return 85.0 if defending_team == right_team else 15.0
        if defending_team == right_team:
            # Echipa care apara poarta din dreapta (x = 100) -> sortam descrescator
            def_xs.sort(reverse=True)
            return def_xs[1]
        else:
            # Echipa care apara poarta din stanga (x = 0) -> sortam crescator
            def_xs.sort()
            return def_xs[1]

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

    def get_kickoff_setup_pos(self, player_id, player_data):
        """
        Calculeaza pozitia de asezare pentru lovitura de incepere (Kick-Off):
        - Un singur jucator din echipa care are lovitura de incepere (#10 pentru A, #110 pentru B)
          merge direct pe centrul terenului (50, 50) langa minge!
        - Mijlocasul central (#7 pentru A, #106 pentru B) se asaza in spatele cercului central
          pregatit sa primeasca pasa inapoi!
        - Toti ceilalti jucatori merg pe pozitiile lor de start, in propria jumatate.
        """
        pid = str(player_id)
        left_team = "A" if self.half == 1 else "B"
        ko_is_left = (self.kickoff_team == left_team)
        if self.kickoff_team == "A":
            if pid == "10":
                return (49.6 if ko_is_left else 50.4), 50.0
            elif pid == "7":
                return (37.0 if ko_is_left else 63.0), 50.0
        elif self.kickoff_team == "B":
            if pid == "110":
                return (49.6 if ko_is_left else 50.4), 50.0
            elif pid == "106":
                return (37.0 if ko_is_left else 63.0), (48.0 if ko_is_left else 52.0)
        return float(player_data["start_x"]), float(player_data["start_y"])

    def are_players_ready(self):
        # daca nu avem destui jucatori conectati, nu suntem gata
        if len(self.players) < NUM_OF_PLAYERS:
            return False

        taker_id = "10" if self.kickoff_team == "A" else "110"
        # verificam fizic fiecare jucator fata de pozitia sa de Kick-Off
        for pid, p in self.players.items():
            kx, ky = self.get_kickoff_setup_pos(pid, p)
            dx = p["x"] - kx
            dy = p["y"] - ky

            distance = math.hypot(dx, dy)

            # Executantul loviturii de incepere trebuie sa ajunga chiar langa minge la centru (< 2.5m, dupa ce s-a apropiat la < 0.8m)
            threshold = 2.5 if str(pid) == taker_id else 5.0
            if distance >= threshold:
                return False

        # toti sunt la pozitiile lor!
        return True
    
    # calculam distanta dintre doua puncte oarecare pe server
    def calculate_distance(self, x1, y1, x2, y2):
        distance = math.sqrt((x1 - x2)**2 + (y1 - y2)**2)
        return distance

    def start_second_half(self):
        """
        Porneste Repriza a 2-a la apasarea butonului 'RESUME MATCH' din pauza (HALF TIME):
        Oglindeste terenurile, acorda kick-off echipei opuse si reia ceasul de la 45:00.
        """
        if self.halftime_start_time is not None:
            self.paused_real_seconds += (self._now() - self.halftime_start_time)
            self.halftime_start_time = None
        self.second_half_wait_start = self._now()
        self.half = 2
        for pdata in self.players.values():
            pdata["start_x"] = 100.0 - float(pdata["start_x"])
            pdata["start_y"] = 100.0 - float(pdata["start_y"])
            pdata["state"] = STATE_IDLE
            pdata["stun_frames"] = 0
            pdata["stun_speed_mult"] = 1.0
            pdata["stun_type"] = ""
        self.kickoff_team = "B" if self.first_half_kickoff_team == "A" else "A"
        self.ball["x"] = 50.0
        self.ball["y"] = 50.0
        self.ball["velocity_x"] = 0.0
        self.ball["velocity_y"] = 0.0
        self.possession = None
        self.intended_receiver = None
        self.offside_pending = False
        self.pass_in_flight_team = None
        self.goal_ball_centered = True
        self.game_status = STATUS_START_GAME
        self._log(f"INCEPE REPRIZA A 2-A! Terenurile au fost schimbate. Lovitura de incepere: Echipa {self.kickoff_team}.")

    def compute_shot_xg(self, team, sx, sy, set_piece_status=None):
        """
        Calculeaza Expected Goals (xG) realist (model logistic stil Opta / StatsBomb):
        - Penalty (11m): 0.78 xG.
        - Joc deschis / Lovitura libera: functie de distanta pana la centrul portii,
          unghiul vizibil dintre bare (41..59), numarul de blocatori din conul de sut si 1v1.
        """
        if set_piece_status == STATUS_PENALTY:
            return 0.80

        left_team_xg = "A" if self.half == 1 else "B"
        goal_x = 100.0 if team == left_team_xg else 0.0
        dist = math.hypot(goal_x - sx, 50.0 - sy)

        # Unghiul vizibil dintre cele doua bare ale portii (y = 41.0 si y = 59.0)
        v1x, v1y = goal_x - sx, 41.0 - sy
        v2x, v2y = goal_x - sx, 59.0 - sy
        n1 = max(1e-6, math.hypot(v1x, v1y))
        n2 = max(1e-6, math.hypot(v2x, v2y))
        cos_a = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (n1 * n2)))
        angle_rad = math.acos(cos_a)

        # Numaram aparatorii adversi (fara portar) aflati in conul de blocaj spre poarta
        dx_g = goal_x - sx
        dy_g = 50.0 - sy
        d_g = max(1e-6, dist)
        nx_g, ny_g = dx_g / d_g, dy_g / d_g
        blockers = 0
        for pid, pdata in self.players.items():
            if pdata.get("team") == team:
                continue
            if pdata.get("role") == "GK" or str(pid) in ["1", "101"]:
                continue
            dx_o = pdata["x"] - sx
            dy_o = pdata["y"] - sy
            proj = dx_o * nx_g + dy_o * ny_g
            if 0.3 < proj < d_g:
                perp = abs(dx_o * ny_g - dy_o * nx_g)
                if perp < (1.15 + proj * 0.075):
                    blockers += 1

        # Model logistic calibrat pe rata reala de conversie a simulatorului nostru (poarta 18u, suturi 10..25m):
        # 8m 1v1 -> ~0.78 | 12m 1v1 -> ~0.58 | 15m 1 blocker -> ~0.27 | 18-21m liber -> ~0.18-0.32 | FK 21m -> ~0.15
        is_one_on_one = (blockers == 0 and dist <= 20.0 and set_piece_status != STATUS_FREE_KICK)
        z = -0.75 - 0.095 * dist + 1.45 * angle_rad - 0.40 * blockers + (0.35 if is_one_on_one else 0.0)
        if set_piece_status == STATUS_FREE_KICK:
            z -= 0.25
        xg = 1.0 / (1.0 + math.exp(-z))
        return max(0.03, min(0.92, xg))

    def get_stats_summary(self):
        """
        Returneaza dictionarul curat de statistici pentru HUD, Pauza, Final si ML.
        """
        sa = self.stats["A"]
        sb = self.stats["B"]
        tot_poss = sa["possession_ticks"] + sb["possession_ticks"]
        if tot_poss > 0:
            poss_a = int(round((sa["possession_ticks"] / tot_poss) * 100.0))
            poss_b = 100 - poss_a
        else:
            poss_a, poss_b = 50, 50

        acc_a = int(round((sa["passes_completed"] / sa["passes"]) * 100.0)) if sa["passes"] > 0 else 0
        acc_b = int(round((sb["passes_completed"] / sb["passes"]) * 100.0)) if sb["passes"] > 0 else 0

        return {
            "A": {
                "xg": round(sa["xg"], 2),
                "possession": poss_a,
                "shots": sa["shots"],
                "shots_on_target": sa["shots_on_target"],
                "passes": sa["passes"],
                "passes_completed": sa["passes_completed"],
                "pass_accuracy": acc_a,
                "corners": sa["corners"],
                "tackles_won": sa["tackles_won"],
                "saves": sa["saves"],
                "fouls": sa["fouls"],
                "offsides": sa["offsides"]
            },
            "B": {
                "xg": round(sb["xg"], 2),
                "possession": poss_b,
                "shots": sb["shots"],
                "shots_on_target": sb["shots_on_target"],
                "passes": sb["passes"],
                "passes_completed": sb["passes_completed"],
                "pass_accuracy": acc_b,
                "corners": sb["corners"],
                "tackles_won": sb["tackles_won"],
                "saves": sb["saves"],
                "fouls": sb["fouls"],
                "offsides": sb["offsides"]
            }
        }
             
    