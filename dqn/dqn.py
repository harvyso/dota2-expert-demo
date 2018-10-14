# Author: Mikita Sazanovich

import itertools
import os
import random
import sys
from collections import namedtuple, deque

import numpy as np
import tensorflow as tf

sys.path.append('../')

from dotaenv import DotaEnvironment

STATE_SPACE = 3
ACTION_SPACE = 16


class Estimator:
    """Q-Value estimation neural network.

    Used for both Q-Value estimation and the target network.
    """

    def __init__(self, scope="estimator", summaries_dir=None):
        self.scope = scope
        self.summary_writer = None
        with tf.variable_scope(scope):
            # Build the graph
            self._build_model()
            if summaries_dir:
                summary_dir = os.path.join(summaries_dir, "summaries_{}".format(scope))
                if not os.path.exists(summary_dir):
                    os.makedirs(summary_dir)
                self.summary_writer = tf.summary.FileWriter(summary_dir)

    def _build_model(self):
        # Input
        self.X = tf.placeholder(shape=[None, STATE_SPACE], dtype=tf.float32, name="X")
        # The TD value
        self.Y = tf.placeholder(shape=[None], dtype=tf.float32, name="Y")
        # Selected action index
        self.action_ind = tf.placeholder(shape=[None], dtype=tf.int32, name="actions")

        layer_shape = 16
        batch_size = tf.shape(self.X)[0]

        # in_layer = tf.Print(self.X, [self.X], message="input_layer", summarize=state_space)

        # Network
        fc1 = tf.layers.dense(inputs=self.X, units=layer_shape,
                              activation=tf.nn.relu)
        # fc1_print = tf.Print(fc1, [fc1], message="fc1", summarize=layer_shape)

        fc2 = tf.layers.dense(inputs=fc1, units=ACTION_SPACE, activation=None)
        # fc2_print = tf.Print(fc2, [fc2], message="fc2", summarize=action_space)

        self.predictions = fc2

        # Get the predictions for the chosen actions only
        gather_indices = tf.range(batch_size) * tf.shape(self.predictions)[1] + self.action_ind
        self.action_predictions = tf.gather(tf.reshape(self.predictions, [-1]), gather_indices)

        # Calculate the loss
        self.losses = tf.squared_difference(self.Y, self.action_predictions)
        self.loss = tf.reduce_mean(self.losses)

        # Optimizer
        self.optimizer = tf.train.RMSPropOptimizer(0.00025, 0.99, 0.0, 1e-6)
        self.train_op = self.optimizer.minimize(self.loss,
                                                global_step=tf.train.get_global_step())

        # Summaries for Tensorboard
        self.summaries = tf.summary.merge([
            tf.summary.scalar("loss", self.loss),
            tf.summary.histogram("loss_hist", self.losses),
            tf.summary.histogram("q_values_hist", self.predictions),
            tf.summary.scalar("max_q_value", tf.reduce_max(self.predictions))
        ])

    def predict(self, sess, X):
        feed_dict = {self.X: X}
        return sess.run(self.predictions, feed_dict=feed_dict)

    def update(self, sess, X, actions, targets):
        feed_dict = {self.X: X, self.Y: targets, self.action_ind: actions}
        summaries, global_step, _, loss = sess.run(
            [self.summaries, tf.train.get_global_step(), self.train_op, self.loss],
            feed_dict)
        if self.summary_writer:
            self.summary_writer.add_summary(summaries, global_step)
        return loss


GOAL = np.array([-1543.998535, -1407.998291])
Transition = namedtuple("Transition", ["state", "action", "reward", "next_state", "done"])


class ReplayBuffer:

    def __init__(self, replay_memory_size):
        # The replay memory
        self.replay_memory = deque(maxlen=replay_memory_size)

    def push(self, transition):
        if transition is None:
            return
        self.replay_memory.append(transition)

    def sample(self, batch_size):
        return random.sample(self.replay_memory, batch_size)


class TransitionBuilder:

    def __init__(self, discount_factor):
        self.discount_factor = discount_factor

    def build(self, state, action, reward, next_state, done):
        # Discard invalid transitions
        if len(state) == 0 or len(next_state) == 0:
            return None
        # Potential-based reward shaping
        potential = np.linalg.norm(np.array(state[:2]) - GOAL)
        next_potential = np.linalg.norm(np.array(next_state[:2]) - GOAL)
        reward += self.discount_factor * next_potential - potential
        return Transition(state, action, reward, next_state, done)


def copy_model_parameters(sess, estimator1, estimator2):
    """
    Copies the model parameters of one estimator to another.
    Args:
      sess: Tensorflow session instance
      estimator1: Estimator to copy the parameters from
      estimator2: Estimator to copy the parameters to
    """
    e1_params = [t for t in tf.trainable_variables() if t.name.startswith(estimator1.scope)]
    e1_params = sorted(e1_params, key=lambda v: v.name)
    e2_params = [t for t in tf.trainable_variables() if t.name.startswith(estimator2.scope)]
    e2_params = sorted(e2_params, key=lambda v: v.name)

    update_ops = []
    for e1_v, e2_v in zip(e1_params, e2_params):
        op = e2_v.assign(e1_v)
        update_ops.append(op)

    sess.run(update_ops)


def make_epsilon_greedy_policy(estimator, nA=ACTION_SPACE):
    """
    Creates an epsilon-greedy policy based on a given Q-function approximator and epsilon.
    Args:
        estimator: An estimator that returns q values for a given state
        nA: Number of actions in the environment.
    Returns:
        A function that takes the (sess, observation, epsilon) as an argument and returns
        the probabilities for each action in the form of a numpy array of length nA.
    """
    def policy_fn(sess, observation, epsilon):
        A = np.ones(nA, dtype=float) * epsilon / nA
        q_values = estimator.predict(sess, np.expand_dims(observation, 0))[0]
        best_action = np.argmax(q_values)
        A[best_action] += (1.0 - epsilon)
        return A
    return policy_fn


def deep_q_learning(sess,
                    env,
                    q_estimator,
                    target_estimator,
                    num_episodes,
                    experiment_dir,
                    replay_memory_size=500000,
                    replay_memory_init_size=500,
                    update_target_estimator_every=1000,
                    discount_factor=0.999,
                    epsilon_start=1.0,
                    epsilon_end=0.1,
                    epsilon_decay_steps=10000,
                    batch_size=32,
                    restore=True):

    reward_dir = os.path.join(experiment_dir, "rewards")
    if not os.path.exists(reward_dir):
        os.makedirs(reward_dir)
    reward_writer = tf.summary.FileWriter(reward_dir)

    transition_builder = TransitionBuilder(discount_factor=discount_factor)
    replay_buffer = ReplayBuffer(replay_memory_size)

    # Create directories for checkpoints and summaries
    checkpoint_dir = os.path.join(experiment_dir, "checkpoints")
    if not os.path.exists(checkpoint_dir):
        os.makedirs(checkpoint_dir)
    checkpoint_path = os.path.join(checkpoint_dir, "model")

    saver = tf.train.Saver()
    if restore:
        # Load a previous checkpoint if we find one
        latest_checkpoint = tf.train.latest_checkpoint(checkpoint_dir)
        if latest_checkpoint:
            print("Loading model checkpoint {}...\n".format(latest_checkpoint))
            saver.restore(sess, latest_checkpoint)

    total_t = sess.run(tf.train.get_global_step())

    # The epsilon decay schedule
    epsilons = np.linspace(epsilon_start, epsilon_end, epsilon_decay_steps)

    # The policy we're following
    policy = make_epsilon_greedy_policy(q_estimator, ACTION_SPACE)

    # Populate the replay memory with initial experience
    print("Populating replay memory...")
    state = env.reset()
    for i in range(replay_memory_init_size):
        action_probs = policy(sess, state, epsilons[min(total_t, epsilon_decay_steps-1)])
        action = np.random.choice(np.arange(len(action_probs)), p=action_probs)
        next_state, reward, done = env.execute(action=action)
        replay_buffer.push(
            transition_builder.build(state, action, reward, next_state, done))
        if done:
            state = env.reset()
        else:
            state = next_state
        print("Step {step} state: {state}, action: {action}.".format(step=i, rew=reward, action=action, state=state))

    for i_episode in range(num_episodes):

        episode_reward = 0
        multiplier = 1

        # Save the current checkpoint
        saver.save(tf.get_default_session(), checkpoint_path)

        # Reset the environment
        state = env.reset()
        loss = None

        # One step in the environment
        for t in itertools.count():

            # Epsilon for this time step
            epsilon = epsilons[min(total_t, epsilon_decay_steps-1)]

            # Maybe update the target estimator
            if total_t % update_target_estimator_every == 0:
                copy_model_parameters(sess, q_estimator, target_estimator)
                print("\nCopied model parameters to target network.")

            # Print out which step we're on, useful for debugging.
            print("\rStep {} ({}) @ Episode {}/{}, loss: {}".format(
                    t, total_t, i_episode + 1, num_episodes, loss), end="")
            sys.stdout.flush()

            # Take a step
            action_probs = policy(sess, state, epsilon)
            action = np.random.choice(np.arange(len(action_probs)), p=action_probs)
            next_state, reward, done = env.execute(action=action)

            episode_reward += reward * multiplier
            multiplier *= discount_factor

            # Save transition to replay memory
            replay_buffer.push(
                transition_builder.build(state, action, reward, next_state, done))

            # Sample a minibatch from the replay memory
            samples = replay_buffer.sample(batch_size)
            states_batch, action_batch, reward_batch, next_states_batch, done_batch = map(np.array, zip(*samples))

            # Calculate q values and targets (Double DQN)
            q_values_next = q_estimator.predict(sess, next_states_batch)

            best_actions = np.argmax(q_values_next, axis=1)
            q_values_next_target = target_estimator.predict(sess, next_states_batch)
            targets_batch = reward_batch + np.invert(done_batch).astype(np.float32) * \
                discount_factor * q_values_next_target[np.arange(batch_size), best_actions]

            # Perform gradient descent update
            states_batch = np.array(states_batch)
            loss = q_estimator.update(sess, states_batch, action_batch, targets_batch)

            state = next_state
            total_t += 1

            if done:
                print("Finished episode with reward", episode_reward)
                reward_writer.add_summary(
                    tf.Summary(value=[tf.Summary.Value(tag="rewards", simple_value=episode_reward)]),
                    total_t)
                break


def main():
    env = DotaEnvironment()

    tf.reset_default_graph()

    # Where we save our checkpoints and graphs
    experiment_dir = os.path.abspath("./experiments/")

    # Create a global step variable
    global_step = tf.Variable(0, name="global_step", trainable=False)

    # Create estimators
    q_estimator = Estimator(scope="q", summaries_dir=experiment_dir)
    target_estimator = Estimator(scope="target_q")

    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())

        deep_q_learning(
            sess=sess,
            env=env,
            q_estimator=q_estimator,
            target_estimator=target_estimator,
            experiment_dir=experiment_dir,
            num_episodes=200,
            restore=False)


if __name__ == "__main__":
    main()
