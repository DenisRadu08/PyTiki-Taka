import multiprocessing
from engine import MatchEngine
from agent import PlayerAgent

def start_engine():
    engine = MatchEngine()
    engine.run()

def start_agent(agent_id):
    agent = PlayerAgent(agent_id)
    agent.run()

if __name__ == "__main__":
    multiprocessing.Process(target=start_engine).start()
    for i in range(1,3):
        multiprocessing.Process(target=start_agent, args=(i,)).start()

    