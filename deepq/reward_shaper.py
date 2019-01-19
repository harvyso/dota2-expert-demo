# Author: Mikita Sazanovich

import json
import math
import os
import pickle
from abc import ABC, abstractmethod

import numpy as np

from deepq.state_preprocessor import StatePreprocessor
from dotaenv.codes import SHAPER_STATE_PROJECT, SHAPER_STATE_DIM, STATE_DIM, \
    ACTIONS_TOTAL


class AbstractRewardShaper(ABC):

    @abstractmethod
    def __init__(self, replay_dir):
        self.replay_dir = replay_dir
        self.state_preprocessor = StatePreprocessor
        self.demos = []

    @abstractmethod
    def load(self):
        # Making the limiting of the number of replays deterministic
        demo_names = sorted(list(os.listdir(self.replay_dir)))
        for name in demo_names:
            dump_path = os.path.join(self.replay_dir, name)
            with open(dump_path, 'rb') as dump_file:
                dumped_replay = pickle.load(dump_file)
            demo = self.process_replay(dumped_replay)
            self.demos.append(demo)

    @abstractmethod
    def process_replay(self, dumped_replay):
        pass


class StatePotentialRewardShaper(AbstractRewardShaper):
    """
    Uses replays to parse demonstrated states and provides potentials based
    on them.
    """
    CLOSE_TO_STATE_EPS = 1e-1
    K = 100

    def __init__(self, replay_dir):
        super(StatePotentialRewardShaper, self).__init__(replay_dir)

    def load(self):
        super(StatePotentialRewardShaper, self).load()
        # Experimenting with the different number of replays
        replays_to_leave = 3
        self.demos = self.demos[:replays_to_leave]
        assert len(self.demos) == replays_to_leave

    def process_replay(self, replay):
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

        It represents the maximum completion of the episode across replays.
        """
        if len(state) < SHAPER_STATE_DIM:
            return 0.0
        max_potent = 0.0
        state = state[SHAPER_STATE_PROJECT]
        for demo in self.demos:
            for i in range(len(demo)):
                diff = np.linalg.norm(demo[i] - state)
                if diff < StatePotentialRewardShaper.CLOSE_TO_STATE_EPS:
                    max_potent = max(max_potent, StatePotentialRewardShaper.K * ((i + 1) / len(demo)))
        return max_potent


class ActionAdviceRewardShaper(AbstractRewardShaper):
    SIGMA = 0.2 * np.identity(STATE_DIM)
    SIGMA[0][0] = 1.0
    SIGMA[1][1] = 1.0
    SIGMA[2][2] = 1.0
    K = 10

    def __init__(self, replay_dir):
        super(ActionAdviceRewardShaper, self).__init__(replay_dir)

    def load(self):
        filepath = os.path.join(self.replay_dir, '3839916254_623964743.obs')
        file = open(filepath, 'r')
        lines = file.readlines()
        file.close()
        demo = self.process_replay(lines)
        self.demos.append(demo)
        print('Loaded {} action replays'.format(len(self.demos)))

    def process_replay(self, replay_lines):
        last_action = 0
        demo = []
        for line in replay_lines:
            state_action_pair = json.loads(line)
            state = state_action_pair['state']
            action = state_action_pair['action']
            if action > ACTIONS_TOTAL:
                continue
            vector_state = np.zeros(18, dtype=np.float32)
            vector_state[0] = last_action / (ACTIONS_TOTAL - 1.0)
            vector_state[1:12] = state['hero_info']
            vector_state[12:] = state['enemy_info']
            demo.append((vector_state, action))
            last_action = action
        return demo

    def get_action_potentials(self, states):
        potentials = np.zeros((len(states), ACTIONS_TOTAL), dtype=np.float32)
        for idx, state in enumerate(states):
            for demo in self.demos:
                for demo_state, demo_action in demo:
                    diff = state - demo_state
                    value = ActionAdviceRewardShaper.K * \
                            math.e ** (-1 / 2 * diff.dot(ActionAdviceRewardShaper.SIGMA).dot(diff))
                    potentials[idx][demo_action] = max(potentials[idx][demo_action], value)
        return potentials


def main():
    reward_shaper = ActionAdviceRewardShaper('../observations')
    reward_shaper.load()
    for demo in reward_shaper.demos:
        for (state, action) in demo:
            print(state, action)
            print('action potentials are:', reward_shaper.get_action_potentials([state]))
        print('Total number is', len(demo))


if __name__ == '__main__':
    main()
