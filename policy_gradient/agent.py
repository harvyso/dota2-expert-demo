import logging
import pickle
import random

import numpy as np
from sklearn.preprocessing import OneHotEncoder

from policy_gradient.analyze_run import print_network_weights
from policy_gradient.network import Network
from policy_gradient.replay_buffer import ReplayBuffer

logger = logging.getLogger('DotaRL.PGAgent')
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

input_shape = 3
output_shape = 16


class PGAgent:
    """
    Policy gradient agent.
    """
    __slots__ = ('env',
                 'replay_buffer',
                 'network',
                 'episodes',
                 'discount',
                 'batch_size',
                 'eps_update',
                 'eps',
                 'rewards')

    def __init__(self, environment, episodes=100, batch_size=100, eps=0.7,
                 discount=0.99, eps_update=0.99):
        self.replay_buffer = ReplayBuffer()
        self.network = Network(input_shape=input_shape,
                               output_shape=output_shape,
                               restore=False)
        self.env = environment()
        self.episodes = episodes
        self.batch_size = batch_size
        self.eps = eps
        self.discount = discount
        self.eps_update = eps_update
        self.rewards = []

    def show_performance(self):
        self.eps = 0.05
        for episode in range(self.episodes):
            # sample data
            states, actions, rewards = self.sample_episode(batch_size=self.batch_size)
            rewards = np.array(rewards, dtype='float32')

            temp = 'Finished episode {ep} with total reward {rew}. eps={eps}'
            logger.debug(temp.format(ep=episode, rew=np.sum(rewards),
                                     eps=self.eps))

    def train(self):
        for episode in range(self.episodes):
            # sample data
            states, actions, rewards = self.sample_episode(batch_size=self.batch_size)
            rewards = np.array(rewards, dtype='float32')
            temp = 'Finished episode {ep} with total reward {rew}. eps={eps}'
            logger.debug(temp.format(ep=episode, rew=np.sum(rewards),
                                     eps=self.eps))

            self.rewards.extend(rewards)

            with open('saved_rewards', 'wb') as output_file:
                pickle.dump(obj=self.rewards, file=output_file)

            # Preprocess rewards
            disc_rewards = self.disc_rewards(rewards)
            norm_rewards = self.normalize_rewards(disc_rewards)

            # Extend replay buffer with sampled data
            self.replay_buffer.extend(zip(states, actions, norm_rewards))

            # Update the parameter for epsilon-greedy strategy
            self.eps *= self.eps_update

            # If there is enough data in replay buffer, train the model on it
            if len(self.replay_buffer) >= self.batch_size:
                for _ in range(10):
                    self.train_network(batch=self.replay_buffer.get_data(self.batch_size))

            print_network_weights(self.network)

        logger.debug('Finished training.')

    def sample_episode(self, batch_size):
        states = []
        actions = []
        rewards = []
        state = self.env.reset()
        for i in range(batch_size):
            action = self.get_action(state=state, eps=self.eps)
            state, terminal, reward = self.env.execute(action=action)
            if terminal:
                break
            logger.debug('Step {step} state: {state}, action: {action}.'.format(step=i, rew=reward, action=action, state=state[:3]))
            states.append(state)
            actions.append(action)
            rewards.append(reward)

        return states, actions, rewards

    def get_action(self, state, eps):
        """
        Get action by epsilon-greedy strategy.
        :param state: state
        :return: action
        """
        if random.uniform(0, 1) > eps:
            return self.network.predict(state=state)
        else:
            return random.randint(0, output_shape - 1)

    def disc_rewards(self, rewards):
        disc_rewards = np.zeros_like(rewards)
        cumulative = 0.0
        for i in reversed(range(len(rewards))):
            cumulative = cumulative * self.discount + rewards[i]
            disc_rewards[i] = cumulative
        return disc_rewards

    def normalize_rewards(self, rewards):
        norm_rewards = np.copy(rewards)
        mean = np.mean(norm_rewards)
        std = np.std(norm_rewards)
        norm_rewards -= mean
        if abs(std) > 1e-9:
            norm_rewards /= std
        return norm_rewards

    def train_on_replay(self, batch_size=500, epochs=25):
        self.replay_buffer.load_data()
        # states, actions, rewards = self.replay_buffer.get_data(batch_size=len(self.replay_buffer))
        # rewards = np.array(rewards, dtype='float32')

        # discount and normalize rewards
        # rewards = self.discount_rewards(rewards=rewards, gamma=self.discount)
        # rewards = self.normalize_rewards(rewards=rewards)
        # self.replay_buffer.extend(zip(states, actions, rewards))

        for epoch in range(epochs):
            i = 0
            while i < len(self.replay_buffer):
                batch = self.replay_buffer.get_batch(i, batch_size=batch_size)
                self.train_network(batch=batch)
                i += batch_size
            logger.debug('Training: epoch {epoch}.'.format(epoch=epoch))

    def train_network(self, batch):
        states, actions, rewards = batch
        states = np.array(states)

        enc = OneHotEncoder(n_values=output_shape)
        actions = np.array(actions).reshape(-1, 1)
        actions = enc.fit_transform(actions).toarray()

        rewards = np.array(rewards, dtype='float32')

        logger.debug('Training network on batch: states {s_shape}, actions {a_shape}, rewards {r_shape}.\n'
                     .format(s_shape=states.shape, a_shape=actions.shape, r_shape=rewards.shape))

        self.replay_buffer.save_data()
        self.network.train(states=states, actions=actions, rewards=rewards)
