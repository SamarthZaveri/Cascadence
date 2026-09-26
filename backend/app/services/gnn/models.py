import torch
from torch import nn
from torch_geometric.data import Data
from torch_geometric.nn import GATConv, GCNConv, SAGEConv

from app.services.gnn.graph_builder import NUM_FEATURES


class GCNRiskModel(nn.Module):
    """Two weighted GCN layers plus local features to retain the focal shock."""

    def __init__(self, hidden_channels: int = 32, in_channels: int = NUM_FEATURES):
        super().__init__()
        self.conv1 = GCNConv(in_channels, hidden_channels)
        self.conv2 = GCNConv(hidden_channels, hidden_channels)
        self.head = nn.Sequential(
            nn.Linear(hidden_channels + in_channels, hidden_channels),
            nn.ReLU(),
            nn.Linear(hidden_channels, 1),
        )

    def forward(self, data: Data) -> torch.Tensor:
        hidden = self.conv1(data.x, data.edge_index, data.edge_weight).relu()
        hidden = self.conv2(hidden, data.edge_index, data.edge_weight).relu()
        return self.head(torch.cat([hidden, data.x], dim=-1)).sigmoid().flatten()


class GATRiskModel(nn.Module):
    """Directed edge-aware attention; weights describe the model, not causal effects."""

    def __init__(self, hidden_channels: int = 32, in_channels: int | None = None):
        super().__init__()
        from app.services.gnn.features import EDGE_WIDTH, WIDTH

        width = WIDTH if in_channels is None else in_channels
        self.conv1 = GATConv(width, hidden_channels, heads=2, concat=False, edge_dim=EDGE_WIDTH)
        self.conv2 = GATConv(hidden_channels, hidden_channels, edge_dim=EDGE_WIDTH)
        self.head = nn.Linear(hidden_channels + width, 1)

    def forward(self, data: Data) -> torch.Tensor:
        h = self.conv1(data.x, data.edge_index, data.edge_attr).relu()
        h = self.conv2(h, data.edge_index, data.edge_attr).relu()
        return self.head(torch.cat([h, data.x], -1)).sigmoid().flatten()

    def attention_weights(self, data: Data):
        """First-layer incoming weights, including explicitly returned self-loops."""
        _, weights = self.conv1(
            data.x, data.edge_index, data.edge_attr, return_attention_weights=True
        )
        return weights


class GraphSAGERiskModel(nn.Module):
    """Inductive mean aggregation baseline; edge weights intentionally unused."""

    def __init__(self, hidden_channels: int = 32, in_channels: int | None = None):
        super().__init__()
        from app.services.gnn.features import WIDTH

        width = WIDTH if in_channels is None else in_channels
        self.conv1 = SAGEConv(width, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.head = nn.Linear(hidden_channels + width, 1)

    def forward(self, data: Data) -> torch.Tensor:
        h = self.conv1(data.x, data.edge_index).relu()
        h = self.conv2(h, data.edge_index).relu()
        return self.head(torch.cat([h, data.x], -1)).sigmoid().flatten()


class TemporalGNNRiskModel(nn.Module):
    """Shared spatial GCN + per-company GRU with explicitly aligned node identities."""

    def __init__(self, hidden_channels: int = 32, in_channels: int | None = None):
        super().__init__()
        from app.services.gnn.features import WIDTH

        width = WIDTH if in_channels is None else in_channels
        self.spatial = GCNConv(width, hidden_channels)
        self.gru = nn.GRUCell(hidden_channels + width, hidden_channels)
        self.head = nn.Linear(hidden_channels + width, 1)
        self.hidden_channels = hidden_channels

    def forward(self, data: Data | list[Data]) -> torch.Tensor:
        sequence = [data] if isinstance(data, Data) else data
        if not sequence:
            raise ValueError("Temporal model needs at least one snapshot")
        ids = sequence[-1].node_ids
        hidden = sequence[-1].x.new_zeros((len(ids), self.hidden_channels))
        for frame in sequence:
            if frame.node_ids != ids:
                raise ValueError("Temporal node identities are not aligned")
            spatial = self.spatial(frame.x, frame.edge_index, frame.edge_weight).relu()
            candidate = self.gru(torch.cat([spatial, frame.x], -1), hidden)
            hidden = torch.where(frame.node_present[:, None], candidate, hidden)
        return self.head(torch.cat([hidden, sequence[-1].x], -1)).sigmoid().flatten()


ARCHITECTURES = {
    "gcn": GCNRiskModel,
    "gat": GATRiskModel,
    "graphsage": GraphSAGERiskModel,
    "temporal": TemporalGNNRiskModel,
}


def create_model(architecture: str, hidden_channels: int = 32):
    from app.services.gnn.features import WIDTH

    if architecture not in ARCHITECTURES:
        raise ValueError("Unknown architecture")
    return ARCHITECTURES[architecture](hidden_channels=hidden_channels, in_channels=WIDTH)
