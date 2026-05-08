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
        agent = GoalkeeperAgent(agent_id = agent_id_str, team_id = team)
    else:
        agent = PlayerAgent(agent_id = agent_id_str, team_id = team)

    agent.run()


if __name__ == "__main__":
    multiprocessing.Process(target=start_engine).start()
    for agent_id in STARTING_POSITIONS.keys():
        multiprocessing.Process(target=start_agent, args=(agent_id,)).start()

    