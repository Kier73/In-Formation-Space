"""Handwritten rational networks used by the certificate experiment."""
from continuous_equivalence import layer


def fixtures():
    return {
        "identity": (layer([[1]], [0], "linear"),),
        "relu_identity": (layer([[1], [-1]], [0, 0], "relu"),
                          layer([[1, -1]], [0], "linear")),
        "zero": (layer([[0]], [0], "linear"),),
        "triangular_bump": (layer([[1], [1], [1]], [0, "-1/2", -1], "relu"),
                            layer([[1, -2, 1]], [0], "linear")),
        "rescaled_bump": (layer([[2], [1], [1]], [0, "-1/2", -1], "relu"),
                          layer([["1/2", -2, 1]], [0], "linear")),
    }
