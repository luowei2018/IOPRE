import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import math
from .network import MLP


def normalized_columns_initializer(weights, std=1.0):
    out = torch.randn(weights.size())
    out *= std / torch.sqrt(out.pow(2).sum(1, keepdim=True))
    return out


def weights_init(m):
    classname = m.__class__.__name__
    if classname.find('Conv') != -1:
        weight_shape = list(m.weight.data.size())
        fan_in = np.prod(weight_shape[1:4])
        fan_out = np.prod(weight_shape[2:4]) * weight_shape[0]
        w_bound = np.sqrt(6. / (fan_in + fan_out))
        m.weight.data.uniform_(-w_bound, w_bound)
        m.bias.data.fill_(0)
    elif classname.find('Linear') != -1:
        weight_shape = list(m.weight.data.size())
        fan_in = weight_shape[1]
        fan_out = weight_shape[0]
        w_bound = np.sqrt(6. / (fan_in + fan_out))
        m.weight.data.uniform_(-w_bound, w_bound)
        m.bias.data.fill_(0)

def gen_sineembed_for_position(pos_tensor, dim=128):  # [b, 3]
    scale = 2 * math.pi
    dim_t = torch.arange(dim, dtype=torch.float32, device=pos_tensor.device)
    dim_t = 10000 ** (2 * (dim_t // 2) / dim)
    s_embed = pos_tensor[:, 0] * scale
    x_embed = pos_tensor[:, 1] * scale
    y_embed = pos_tensor[:, 2] * scale
    pos_s = s_embed[:, None] / dim_t
    pos_x = x_embed[:, None] / dim_t
    pos_y = y_embed[:, None] / dim_t
    pos_s = torch.stack((pos_s[:, 0::2].sin(), pos_s[:, 1::2].cos()), dim=2).flatten(1)
    pos_x = torch.stack((pos_x[:, 0::2].sin(), pos_x[:, 1::2].cos()), dim=2).flatten(1)
    pos_y = torch.stack((pos_y[:, 0::2].sin(), pos_y[:, 1::2].cos()), dim=2).flatten(1)
    pos = torch.cat((pos_s, pos_x, pos_y), dim=1)
    return pos


'''
1. Parameter Initialization Enhancement: While the current initialization strategy is robust, introducing more sophisticated initializations based on the specific layers' roles could provide better convergence properties.
2. Layer Normalization: Including normalization techniques such as Layer Normalization after each MLP layer could help stabilize the learning process.
3. Use of Residual Connections: Incorporating residual connections might help with the gradient flow in deeper architectures, especially useful in sequential models like LSTM.
4. Refactoring MLP Usage: Instead of defining separate MLPs for different inputs, a more unified approach could be considered. This would streamline the architecture and potentially make it easier to manage and adapt.
5. Modular Design for Position Embedding: Enhancing the position embedding generation method to support varying dimensions seamlessly, making it more robust to input variations.
6. Enhancing LSTM Integration: Instead of a single LSTM cell, using an LSTM layer might better capture temporal dependencies when dealing with sequences of data.
7. Adding Dropout: Incorporating dropout layers could help prevent overfitting, especially given the model's complexity.
8. Improving Action and Value Heads: Considering separate processing paths for the actor and critic components post-LSTM processing might allow each to learn more effectively from the features relevant to their specific tasks.
'''
# class ActorCritic(nn.Module):
#     def __init__(self, input_dim=512, hidden_dim=256, num_actions=8):
#         super(ActorCritic, self).__init__()
#         self.input_dim = input_dim
#         self.hidden_dim = hidden_dim
#         self.num_actions = num_actions
#         self.pos_dim = 128

#         self.feat_mlp = MLP(input_dim=input_dim, hidden_dim=hidden_dim, output_dim=hidden_dim, num_layers=1)
#         self.bbox_mlp = MLP(input_dim=self.pos_dim * 3, hidden_dim=hidden_dim, output_dim=hidden_dim, num_layers=1)

#         self.mlp = MLP(input_dim=hidden_dim * 2, hidden_dim=hidden_dim, output_dim=hidden_dim, num_layers=2)

#         self.lstm = nn.LSTMCell(input_size=hidden_dim, hidden_size=hidden_dim)

#         self.critic_linear = nn.Linear(hidden_dim, 1)
#         self.actor_linear = nn.Linear(hidden_dim, num_actions)

#         self.apply(weights_init)
#         self.actor_linear.weight.data = normalized_columns_initializer(self.actor_linear.weight.data, 0.01)
#         self.actor_linear.bias.data.fill_(0)
#         self.critic_linear.weight.data = normalized_columns_initializer(self.critic_linear.weight.data, 1.0)
#         self.critic_linear.bias.data.fill_(0)

#         self.lstm.bias_ih.data.fill_(0)
#         self.lstm.bias_hh.data.fill_(0)

#         self.train()

#     def forward(self, inputs):
#         x, (hx, cx), trans_bbox = inputs

#         bbox_emb = gen_sineembed_for_position(trans_bbox, dim=self.pos_dim)
#         bbox_emb = self.bbox_mlp(bbox_emb)

#         x = self.feat_mlp(x)

#         x = torch.cat([x, bbox_emb], dim=1)

#         x = self.mlp(x)
#         hx, cx = self.lstm(x, (hx, cx))
#         x = hx
#         return self.critic_linear(x), self.actor_linear(x), (hx, cx)

import torch
import torch.nn as nn
import torch.nn.functional as F
from .network import MLP

class ActorCritic(nn.Module):
    def __init__(self, input_dim=512, hidden_dim=256, num_actions=8, pos_dim=128):
        super(ActorCritic, self).__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_actions = num_actions
        self.pos_dim = pos_dim

        # Feature extraction for main input and bounding box
        self.feat_mlp = MLP(input_dim=input_dim, hidden_dim=hidden_dim, output_dim=hidden_dim, num_layers=1)
        self.bbox_mlp = MLP(input_dim=self.pos_dim * 3, hidden_dim=hidden_dim, output_dim=hidden_dim, num_layers=1)

        # Shared MLP for concatenated features
        self.mlp = MLP(input_dim=hidden_dim * 2, hidden_dim=hidden_dim, output_dim=hidden_dim, num_layers=2)
        self.norm = nn.LayerNorm(hidden_dim)  # Adding normalization
        self.dropout = nn.Dropout(0.5)  # Adding dropout for regularization

        # Using LSTM layer for temporal dependencies
        self.lstm = nn.LSTM(input_size=hidden_dim, hidden_size=hidden_dim, batch_first=True)

        # Separate heads for actor and critic
        self.critic_linear = nn.Linear(hidden_dim, 1)
        self.actor_linear = nn.Linear(hidden_dim, num_actions)

        # Initialize weights and biases
        self.apply(weights_init)
        self.actor_linear.weight.data = normalized_columns_initializer(self.actor_linear.weight.data, 0.01)
        self.critic_linear.weight.data = normalized_columns_initializer(self.critic_linear.weight.data, 1.0)
        self.actor_linear.bias.data.fill_(0)
        self.critic_linear.bias.data.fill_(0)

        self.lstm.bias_ih_l0.data.fill_(0)
        self.lstm.bias_hh_l0.data.fill_(0)

        self.train()

    def forward(self, inputs):
        x, (hx, cx), trans_bbox = inputs

        # Embedding and MLP processing
        bbox_emb = gen_sineembed_for_position(trans_bbox, dim=self.pos_dim)
        bbox_emb = self.bbox_mlp(bbox_emb)
        x = self.feat_mlp(x)
        x = torch.cat([x, bbox_emb], dim=1)
        x = self.mlp(x)
        x = self.norm(x)  # Applying normalization
        x = self.dropout(x)  # Applying dropout

        # LSTM processing
        x, (hx, cx) = self.lstm(x, (hx, cx))
        x = x.squeeze(1)  # Assuming batch_first=True in LSTM
        return self.critic_linear(x), self.actor_linear(x), (hx, cx)


# def weighted_mean(tensor, dim=None, weights=None):
#     if weights is None:
#         out = torch.mean(tensor)
#     if dim is None:
#         out = torch.sum(tensor * weights)
#         out.div_(torch.sum(weights))
#     else:
#         mean_dim = torch.sum(tensor * weights, dim=dim)
#         mean_dim.div_(torch.sum(weights, dim=dim))
#         out = torch.mean(mean_dim)
#     return out

# def weighted_normalize(tensor, dim=None, weights=None, epsilon=1e-8):
#     mean = weighted_mean(tensor, dim=dim, weights=weights)
#     out = tensor * (1 if weights is None else weights) - mean
#     std = torch.sqrt(weighted_mean(out ** 2, dim=dim, weights=weights))
#     out.div_(std + epsilon)
#     return out

def weights_init(m):
    classname = m.__class__.__name__
    if classname.find('Conv') != -1 or classname.find('Linear') != -1:
        nn.init.kaiming_uniform_(m.weight, nonlinearity='relu')
        if m.bias is not None:
            m.bias.data.fill_(0.01)

def normalized_columns_initializer(weights, std=1.0):
    out = torch.randn(weights.size())
    out *= std / torch.sqrt(out.pow(2).sum(1, keepdim=True))
    return out

class SetCriterion(nn.Module):
    def __init__(self, gamma, gae_lambda, weight_dict, device):
        super().__init__()
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.weight_dict = weight_dict
        self.device = device

    def forward(self, R, rewards, values, log_probs, entropies):
        losses = {}

        policy_loss = 0
        value_loss = 0
        entropy_loss = 0
        gae = torch.zeros(1, 1).to(self.device)
        for i in reversed(range(len(rewards))):
            R = self.gamma * R + rewards[i]
            advantage = R - values[i]
            value_loss = value_loss + advantage.pow(2)

            # Generalized Advantage Estimation
            delta_t = rewards[i] + self.gamma * values[i + 1] - values[i]
            gae = gae * self.gamma * self.gae_lambda + delta_t

            policy_loss = policy_loss - log_probs[i] * gae.detach()

            entropy_loss = entropy_loss - entropies[i]

        losses['loss_policy'] = policy_loss
        losses['loss_value'] = value_loss
        losses['loss_entropy'] = entropy_loss
        return losses


def build_ActorCritic(args, device):
    model = ActorCritic(input_dim=args.input_dim, hidden_dim=args.hidden_dim, num_actions=args.num_actions)

    weight_dict = {"loss_policy": args.policy_weight,
                   "loss_value": args.value_weight,
                   "loss_entropy": args.entropy_weight}

    criterion = SetCriterion(gamma=args.gamma, gae_lambda=args.gae_lambda, weight_dict=weight_dict, device=device)
    return model, criterion