import multiprocessing
import json
from engine import MatchEngine
from agent import PlayerAgent
from gkagent import GoalkeeperAgent
from config import STARTING_POSITIONS
from ai_brains import BASE_BUILD_NAME

def start_engine():
    engine = MatchEngine()
    engine.run()

# Factory
def start_agent(agent_id_str, ai_build=BASE_BUILD_NAME):
    role = STARTING_POSITIONS[agent_id_str]["role"]
    team = STARTING_POSITIONS[agent_id_str]["team"]

    if role == "GK":
        agent = GoalkeeperAgent(agent_id = agent_id_str, team = team)
    else:
        agent = PlayerAgent(agent_id = agent_id_str, team = team, ai_build = ai_build)

    agent.run()

def run_game():
    # Citim ce AI build a fost selectat pentru fiecare echipa in Launcher (settings.json)
    team_ai_map = {"A": BASE_BUILD_NAME, "B": BASE_BUILD_NAME}
    try:
        with open("settings.json", "r") as f:
            teams_cfg = json.load(f).get("teams", {})
            team_ai_map["A"] = str(teams_cfg.get("A", {}).get("ai_build", BASE_BUILD_NAME))
            team_ai_map["B"] = str(teams_cfg.get("B", {}).get("ai_build", BASE_BUILD_NAME))
    except Exception:
        pass

    processes = []

    # 1. Pornim motorul ca daemon
    p_engine = multiprocessing.Process(target=start_engine, daemon=True)
    processes.append(p_engine)
    p_engine.start()

    # 2. Pornim agentii ca daemoni (fiecare cu AI build-ul echipei sale!)
    for agent_id in STARTING_POSITIONS.keys():
        team = STARTING_POSITIONS[agent_id]["team"]
        p_agent = multiprocessing.Process(target=start_agent, args=(agent_id, team_ai_map.get(team, BASE_BUILD_NAME)), daemon=True)
        processes.append(p_agent)
        p_agent.start()

    # 3. Tinem main.py in viata. (Daca main.py pica, toti daemonii mor odata cu el)
    for p in processes:
        p.join()

if __name__ == "__main__":
    run_game()