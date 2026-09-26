# cascadence Phase 4 model evaluation

Data basis: **synthetic_engineering_benchmark**.

Checkpoint selection uses validation Brier score. Test data never selects a model.
Scores are experimental indices; these metrics do not establish trading utility.

| Architecture | Ablation | Seed | Best epoch | Test precision | Recall | F1 | ROC AUC | PR AUC | Brier |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gcn | full | 42 | 80 | 0.9804 | 0.8333 | 0.9009 | 0.9514 | 0.9668 | 0.0776 |
| gcn | full | 43 | 80 | 0.9796 | 0.8000 | 0.8807 | 0.9528 | 0.9669 | 0.0798 |
| gcn | full | 44 | 80 | 0.9792 | 0.7833 | 0.8704 | 0.9525 | 0.9666 | 0.0816 |
| gat | full | 42 | 80 | 0.8980 | 0.7333 | 0.8073 | 0.9167 | 0.9273 | 0.1264 |
| gat | full | 43 | 62 | 0.9038 | 0.7833 | 0.8393 | 0.9136 | 0.9177 | 0.1220 |
| gat | full | 44 | 62 | 0.9000 | 0.7500 | 0.8182 | 0.9181 | 0.9228 | 0.1213 |
| graphsage | full | 42 | 66 | 0.9074 | 0.8167 | 0.8596 | 0.9350 | 0.9429 | 0.1028 |
| graphsage | full | 43 | 55 | 0.8909 | 0.8167 | 0.8522 | 0.9358 | 0.9425 | 0.1025 |
| graphsage | full | 44 | 68 | 0.9216 | 0.7833 | 0.8468 | 0.9436 | 0.9530 | 0.0961 |
| temporal | full | 42 | 79 | 0.9455 | 0.8667 | 0.9043 | 0.9850 | 0.9854 | 0.0565 |
| temporal | full | 43 | 64 | 0.9464 | 0.8833 | 0.9138 | 0.9864 | 0.9869 | 0.0519 |
| temporal | full | 44 | 72 | 0.9464 | 0.8833 | 0.9138 | 0.9861 | 0.9865 | 0.0532 |
| temporal | no_temporal | 42 | 80 | 0.9796 | 0.8000 | 0.8807 | 0.9417 | 0.9614 | 0.0822 |
| temporal | no_temporal | 43 | 80 | 0.9796 | 0.8000 | 0.8807 | 0.9458 | 0.9619 | 0.0833 |
| temporal | no_temporal | 44 | 80 | 0.9800 | 0.8167 | 0.8909 | 0.9467 | 0.9627 | 0.0805 |
| temporal | no_vision | 42 | 70 | 0.9464 | 0.8833 | 0.9138 | 0.9844 | 0.9849 | 0.0518 |
| temporal | no_vision | 43 | 72 | 0.9630 | 0.8667 | 0.9123 | 0.9839 | 0.9849 | 0.0560 |
| temporal | no_vision | 44 | 76 | 0.9818 | 0.9000 | 0.9391 | 0.9853 | 0.9862 | 0.0496 |
| temporal | no_news | 42 | 72 | 0.9298 | 0.8833 | 0.9060 | 0.9853 | 0.9857 | 0.0555 |
| temporal | no_news | 43 | 68 | 0.9455 | 0.8667 | 0.9043 | 0.9856 | 0.9863 | 0.0532 |
| temporal | no_news | 44 | 73 | 0.9630 | 0.8667 | 0.9123 | 0.9869 | 0.9873 | 0.0480 |

## Across-seed variation

| Architecture | Ablation | Mean test F1 ± SD | Mean test Brier ± SD |
|---|---|---:|---:|
| gat | full | 0.8216 ± 0.0133 | 0.1232 ± 0.0023 |
| gcn | full | 0.8840 ± 0.0127 | 0.0797 ± 0.0016 |
| graphsage | full | 0.8529 ± 0.0053 | 0.1005 ± 0.0031 |
| temporal | full | 0.9106 ± 0.0045 | 0.0539 ± 0.0019 |
| temporal | no_news | 0.9075 ± 0.0034 | 0.0522 ± 0.0031 |
| temporal | no_temporal | 0.8841 ± 0.0048 | 0.0820 ± 0.0012 |
| temporal | no_vision | 0.9217 ± 0.0123 | 0.0524 ± 0.0027 |
