# ==============================================================================
# File: analysis/calculators/hierarchical_risk_parity.py
# Monika Hierarchical Risk Parity (HRP) Multi-Asset Allocation Engine
# ==============================================================================

"""
Hierarchical Risk Parity (HRP) Multi-Asset Allocation Engine.

Implements Marcos López de Prado's HRP algorithm:
1. Tree Clustering based on correlation distance d_ij = sqrt(0.5 * (1 - rho_ij)).
2. Quasi-Diagonalization to reorder covariance matrix along hierarchical clusters.
3. Recursive Bisection based on cluster inverse-variance without matrix inversion.
Fully self-contained in pure NumPy/pandas without scipy dependencies.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger("TradingAgent.Calculators.HRP")


def correlation_distance_matrix(corr: np.ndarray) -> np.ndarray:
    """
    Computes distance matrix: d_ij = sqrt(0.5 * (1 - rho_ij)).
    d_ii = 0.0, d_ij in [0, 1].
    """
    d = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, 1.0))
    np.fill_diagonal(d, 0.0)
    return d


class _ClusterNode:
    def __init__(self, cluster_id: int, left: _ClusterNode | None = None, right: _ClusterNode | None = None, leaf_id: int | None = None):
        self.cluster_id = cluster_id
        self.left = left
        self.right = right
        self.leaf_id = leaf_id  # Index of original asset if leaf

    def is_leaf(self) -> bool:
        return self.left is None and self.right is None


def _hierarchical_linkage(dist_matrix: np.ndarray) -> _ClusterNode:
    """
    Performs agglomerative hierarchical clustering (average linkage)
    in pure NumPy. Returns the root _ClusterNode.
    """
    n = dist_matrix.shape[0]
    clusters: list[_ClusterNode] = [_ClusterNode(cluster_id=i, leaf_id=i) for i in range(n)]
    current_dist = dist_matrix.copy()
    node_id_counter = n

    while len(clusters) > 1:
        # Find minimum distance between distinct active clusters
        min_dist = np.inf
        best_i = -1
        best_j = -1
        k = len(clusters)

        for i in range(k):
            for j in range(i + 1, k):
                if current_dist[i, j] < min_dist:
                    min_dist = current_dist[i, j]
                    best_i, best_j = i, j

        # Create new merged node
        node_a = clusters[best_i]
        node_b = clusters[best_j]
        new_node = _ClusterNode(cluster_id=node_id_counter, left=node_a, right=node_b)
        node_id_counter += 1

        # Calculate average distance from new merged cluster to all other clusters
        new_dists = []
        for idx in range(k):
            if idx not in (best_i, best_j):
                avg_d = 0.5 * (current_dist[best_i, idx] + current_dist[best_j, idx])
                new_dists.append(avg_d)

        # Update clusters list: remove merged, append new
        new_clusters = [clusters[idx] for idx in range(k) if idx not in (best_i, best_j)]
        new_clusters.append(new_node)

        # Reconstruct distance matrix for remaining clusters
        rem_count = len(new_clusters)
        new_mat = np.zeros((rem_count, rem_count))

        # Copy over distances between unmerged clusters
        old_indices = [idx for idx in range(k) if idx not in (best_i, best_j)]
        for r_new, r_old in enumerate(old_indices):
            for c_new, c_old in enumerate(old_indices):
                new_mat[r_new, c_new] = current_dist[r_old, c_old]

        # Fill distances to the new merged cluster (last row/column)
        last_idx = rem_count - 1
        for idx, d_val in enumerate(new_dists):
            new_mat[idx, last_idx] = d_val
            new_mat[last_idx, idx] = d_val
        new_mat[last_idx, last_idx] = 0.0

        clusters = new_clusters
        current_dist = new_mat

    return clusters[0]


def _get_quasi_diag_order(node: _ClusterNode) -> list[int]:
    """In-order tree traversal to extract quasi-diagonalized leaf order."""
    if node.is_leaf():
        return [node.leaf_id]
    order = []
    if node.left:
        order.extend(_get_quasi_diag_order(node.left))
    if node.right:
        order.extend(_get_quasi_diag_order(node.right))
    return order


def _compute_cluster_variance(cov: np.ndarray, cluster_indices: list[int]) -> float:
    """Computes inverse-variance weighted variance of a sub-cluster."""
    sub_cov = cov[np.ix_(cluster_indices, cluster_indices)]
    inv_diag = 1.0 / np.diag(sub_cov)
    w = inv_diag / np.sum(inv_diag)
    var = float(np.dot(w.T, np.dot(sub_cov, w)))
    return max(var, 1e-12)


def compute_hrp_weights(returns_df: pd.DataFrame) -> pd.Series:
    """
    Computes optimal HRP portfolio weights from asset returns DataFrame.
    Guarantees sum(weights) == 1.0 and all weights > 0.
    """
    clean_df = returns_df.dropna(how="all")
    symbols = list(clean_df.columns)
    n = len(symbols)

    if n == 0:
        return pd.Series(dtype=np.float64)
    if n == 1:
        return pd.Series([1.0], index=symbols)

    corr = clean_df.corr().to_numpy(dtype=np.float64)
    cov = clean_df.cov().to_numpy(dtype=np.float64)

    # 1. Tree Clustering
    dist_mat = correlation_distance_matrix(corr)
    root = _hierarchical_linkage(dist_mat)

    # 2. Quasi-Diagonalization
    sorted_indices = _get_quasi_diag_order(root)

    # 3. Recursive Bisection
    weights = pd.Series(1.0, index=sorted_indices)
    clusters = [sorted_indices]

    while len(clusters) > 0:
        next_clusters = []
        for cluster in clusters:
            if len(cluster) > 1:
                mid = len(cluster) // 2
                c1 = cluster[:mid]
                c2 = cluster[mid:]

                var1 = _compute_cluster_variance(cov, c1)
                var2 = _compute_cluster_variance(cov, c2)

                # Allocation factor alpha
                alpha = 1.0 - (var1 / (var1 + var2))

                weights[c1] *= alpha
                weights[c2] *= (1.0 - alpha)

                if len(c1) > 1:
                    next_clusters.append(c1)
                if len(c2) > 1:
                    next_clusters.append(c2)

        clusters = next_clusters

    # Map back to original symbol names in original order
    out_weights = pd.Series(index=symbols, dtype=np.float64)
    for idx_num, sym in enumerate(symbols):
        out_weights[sym] = weights[idx_num]

    out_weights /= out_weights.sum()
    return out_weights
