import numpy as np
from typing import List, Optional, Tuple, Dict, Any

class TreeNode:
    def __init__(
        self,
        feature: Optional[int] = None,
        threshold: Optional[float] = None,
        left: Optional['TreeNode'] = None,
        right: Optional['TreeNode'] = None,
        value: Optional[float] = None,
        gain: float = 0.0
    ):
        self.feature = feature
        self.threshold = threshold
        self.left = left
        self.right = right
        self.value = value  # Probability of class 1
        self.gain = gain

    @property
    def is_leaf(self) -> bool:
        return self.value is not None

class DecisionTree:
    def __init__(self, max_depth: int = 10, min_samples_split: int = 4, max_features: Optional[int] = None):
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.max_features = max_features
        self.root: Optional[TreeNode] = None

    def _gini(self, y: np.ndarray) -> float:
        if len(y) == 0:
            return 0.0
        p = np.mean(y)
        return 2.0 * p * (1.0 - p)

    def _best_split(self, X: np.ndarray, y: np.ndarray, feature_indices: np.ndarray) -> Tuple[Optional[int], Optional[float], float]:
        best_gain = -1.0
        best_feat = None
        best_thresh = None
        n = len(y)
        if n < self.min_samples_split:
            return None, None, 0.0

        current_gini = self._gini(y)

        for feat in feature_indices:
            vals = X[:, feat]
            # Select candidate percentiles/thresholds for speed and robustness
            thresholds = np.percentile(vals, np.linspace(10, 90, 9))
            for thresh in thresholds:
                left_mask = vals <= thresh
                n_left = np.sum(left_mask)
                n_right = n - n_left
                if n_left < 2 or n_right < 2:
                    continue

                gini_left = self._gini(y[left_mask])
                gini_right = self._gini(y[~left_mask])
                gain = current_gini - (n_left / n * gini_left + n_right / n * gini_right)

                if gain > best_gain:
                    best_gain = gain
                    best_feat = feat
                    best_thresh = float(thresh)

        return best_feat, best_thresh, max(0.0, best_gain)

    def _build_tree(self, X: np.ndarray, y: np.ndarray, depth: int = 0) -> TreeNode:
        p_val = float(np.mean(y)) if len(y) > 0 else 0.0
        if depth >= self.max_depth or len(y) < self.min_samples_split or p_val == 0.0 or p_val == 1.0:
            return TreeNode(value=p_val)

        n_features = X.shape[1]
        k = self.max_features or int(np.sqrt(n_features))
        feature_indices = np.random.choice(n_features, size=min(k, n_features), replace=False)

        feat, thresh, gain = self._best_split(X, y, feature_indices)
        if feat is None or gain <= 1e-7:
            return TreeNode(value=p_val)

        left_mask = X[:, feat] <= thresh
        left_node = self._build_tree(X[left_mask], y[left_mask], depth + 1)
        right_node = self._build_tree(X[~left_mask], y[~left_mask], depth + 1)
        return TreeNode(feature=feat, threshold=thresh, left=left_node, right=right_node, gain=gain)

    def fit(self, X: np.ndarray, y: np.ndarray):
        self.root = self._build_tree(X, y, depth=0)
        return self

    def _predict_row(self, node: TreeNode, x: np.ndarray) -> float:
        if node.is_leaf:
            return node.value
        if x[node.feature] <= node.threshold:
            return self._predict_row(node.left, x)
        return self._predict_row(node.right, x)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return np.array([self._predict_row(self.root, x) for x in X])

class RandomForestSurrogate:
    """
    Pure-Python / NumPy Random Forest ensemble classifier for flood inundation surrogate modeling.
    Guaranteed zero external C/DLL dependency, fully compatible with Windows security and Application Control policies.
    """
    def __init__(
        self,
        n_estimators: int = 50,
        max_depth: int = 10,
        min_samples_split: int = 4,
        max_features: Optional[int] = None,
        random_state: int = 42
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.max_features = max_features
        self.random_state = random_state
        self.trees: List[DecisionTree] = []
        self.feature_importances_: np.ndarray = np.array([])

    def fit(self, X: np.ndarray, y: np.ndarray):
        np.random.seed(self.random_state)
        n_samples, n_features = X.shape
        self.trees = []
        feature_gains = np.zeros(n_features)

        # Handle class balance via sample weighting/stratified bootstrap
        pos_idx = np.where(y == 1)[0]
        neg_idx = np.where(y == 0)[0]

        for _ in range(self.n_estimators):
            # Balanced bootstrap
            if len(pos_idx) > 0 and len(neg_idx) > 0:
                half = n_samples // 2
                boot_pos = np.random.choice(pos_idx, size=half, replace=True)
                boot_neg = np.random.choice(neg_idx, size=n_samples - half, replace=True)
                boot_idx = np.concatenate([boot_pos, boot_neg])
            else:
                boot_idx = np.random.choice(n_samples, size=n_samples, replace=True)

            tree = DecisionTree(
                max_depth=self.max_depth,
                min_samples_split=self.min_samples_split,
                max_features=self.max_features
            )
            tree.fit(X[boot_idx], y[boot_idx])
            self.trees.append(tree)

            # Accumulate feature gains
            def collect_gains(node: Optional[TreeNode]):
                if node and not node.is_leaf:
                    if node.feature is not None:
                        feature_gains[node.feature] += node.gain
                    collect_gains(node.left)
                    collect_gains(node.right)

            collect_gains(tree.root)

        total_gain = np.sum(feature_gains)
        if total_gain > 0:
            self.feature_importances_ = feature_gains / total_gain
        else:
            self.feature_importances_ = np.ones(n_features) / n_features

        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Returns array of shape (N, 2) where column 1 is probability of flood."""
        X = np.asarray(X)
        probs = np.zeros(len(X))
        for tree in self.trees:
            probs += tree.predict_proba(X)
        p1 = probs / len(self.trees)
        p0 = 1.0 - p1
        return np.column_stack([p0, p1])

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        probs = self.predict_proba(X)[:, 1]
        return (probs >= threshold).astype(int)
