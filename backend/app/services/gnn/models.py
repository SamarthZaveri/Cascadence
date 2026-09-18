import torch
from torch import nn
from torch_geometric.data import Data
from torch_geometric.nn import GCNConv

from app.services.gnn.graph_builder import NUM_FEATURES


class GCNRiskModel(nn.Module):
    """Two weighted GCN layers plus local features to retain the focal shock."""

    def __init__(self, hidden_channels: int = 32):
        super().__init__()
        self.conv1 = GCNConv(NUM_FEATURES, hidden_channels)
        self.conv2 = GCNConv(hidden_channels, hidden_channels)
        self.head = nn.Sequential(
            nn.Linear(hidden_channels + NUM_FEATURES, hidden_channels),
            nn.ReLU(),
            nn.Linear(hidden_channels, 1),
        )

    def forward(self, data: Data) -> torch.Tensor:
        hidden = self.conv1(data.x, data.edge_index, data.edge_weight).relu()
        hidden = self.conv2(hidden, data.edge_index, data.edge_weight).relu()
        return self.head(torch.cat([hidden, data.x], dim=-1)).sigmoid().flatten()
