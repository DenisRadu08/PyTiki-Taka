import multiprocessing
from engine import MatchEngine
from agent import PlayerAgent
from gkagent import GoalkeeperAgent
from config import STARTING_POSITIONS

def start_engine():
    engine = MatchEngine()
    engine.run()

# Factory
def start_agent(agent_id_str):
    role = STARTING_POSITIONS[agent_id_str]["role"]
    team = STARTING_POSITIONS[agent_id_str]["team"]

    if role == "GK":
        agent = GoalkeeperAgent(agent_id = agent_id_str, team = team)
    else:
        agent = PlayerAgent(agent_id = agent_id_str, team = team)

    agent.run()


if __name__ == "__main__":
    processes = []

    # 1. Pornim motorul ca daemon
    p_engine = multiprocessing.Process(target=start_engine, daemon=True)
    processes.append(p_engine)
    p_engine.start()

    # 2. Pornim agentii ca daemoni
    for agent_id in STARTING_POSITIONS.keys():
        p_agent = multiprocessing.Process(target=start_agent, args=(agent_id,), daemon=True)
        processes.append(p_agent)
        p_agent.start()

    # 3. Tinem main.py in viata. (Daca main.py pica, toti daemonii mor odata cu el)
    for p in processes:
        p.join()