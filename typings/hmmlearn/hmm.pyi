from typing import Any

class GaussianHMM:
    def __init__(
        self,
        n_components: int = ...,
        covariance_type: str = ...,
        n_iter: int = ...,
        random_state: Any = ...,
    ) -> None: ...
    transmat_: Any
    means_: Any
    def fit(self, X: Any, lengths: Any = ...) -> Any: ...
    def predict(self, X: Any, lengths: Any = ...) -> Any: ...
    def predict_proba(self, X: Any, lengths: Any = ...) -> Any: ...
