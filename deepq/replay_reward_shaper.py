# Author: Mikita Sazanovich

import os
import pickle
import numpy as np

from deepq.state_preprocessor import StatePreprocessor
from dotaenv.codes import SHAPER_STATE_PROJECT

EPS = 1e-1
K = 100


class ReplayRewardShaper:
    """
    Uses replays to parse demonstrated states and provides potentials based
    on them.
    """

    def __init__(self, replay_dir):
        self.replay_dir = replay_dir
        self.state_preprocessor = StatePreprocessor()
        self.demos = []

    def load(self):
        # Make replay selection deterministic
        demo_names = sorted(list(os.listdir(self.replay_dir)))
        for name in demo_names:
            dump_path = os.path.join(self.replay_dir, name)
            with open(dump_path, 'rb') as dump_file:
                replay = pickle.load(dump_file)
            demo = self.__process_replay(replay)
            self.demos.append(demo)
        assert len(self.demos) == 3

    def __process_replay(self, replay):
        demo = []
        for replay_step in replay:
            if len(replay_step) == 0:
                continue
            state = replay_step
            state_proj = state[SHAPER_STATE_PROJECT]
            state_proc = self.state_preprocessor.process(state_proj)
            if not demo or np.linalg.norm(demo[len(demo) - 1] - state_proc) > 0:
                demo.append(state_proc)
        return demo

    def get_state_potential(self, state):
        """ Returns the state potential that is a float from [0; K).

        It represents the completion of the demo episode.
        """
        if len(state) < len(SHAPER_STATE_PROJECT):
            return 0.0
        max_potent = 0.0
        state = state[SHAPER_STATE_PROJECT]
        for demo in self.demos:
            for i in range(len(demo)):
                diff = np.linalg.norm(demo[i] - state)
                if diff < EPS:
                    max_potent = max(max_potent, K*((i+1)/len(demo)))
        return max_potent


def main():
    replay_processor = ReplayRewardShaper('../replays')
    replay_processor.load()
    for demo in replay_processor.demos:
        last_state = demo[0]
        for state in demo:
            print('dst', np.linalg.norm(last_state - state))
            print(state)
            last_state = state


if __name__ == '__main__':
    main()
