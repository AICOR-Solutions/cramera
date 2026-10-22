"""
The circuit ``x ~ Uniform(0, 1)`` times ``color ~ {red: 0.7, blue: 0.3}``, built with
the installed circuit libraries.

It is built in the test process rather than kept as a file: the libraries key the
probabilities of symbolic values by Python's string hash, which differs between
processes, so a circuit file with a symbolic variable only reads back in the process
that wrote it.
"""

from __future__ import annotations

import json

from probabilistic_model.distributions.distributions import SymbolicDistribution
from probabilistic_model.distributions.uniform import UniformDistribution
from probabilistic_model.probabilistic_circuit.rx.probabilistic_circuit import (
    ProbabilisticCircuit,
    ProductUnit,
    leaf,
)
from probabilistic_model.utils import MissingDict
from random_events.interval import closed
from random_events.set import Set
from random_events.variable import Continuous, Symbolic

from cramera_protocol.models import ModelUpload

COLOR_PROBABILITIES = {"red": 0.7, "blue": 0.3}
"""
The prior probability of each color.
"""

NAME = "uniform_and_color.json"
"""
The name the circuit is uploaded under.
"""

# %% circuit


def uniform_and_color() -> ModelUpload:
    """
    :return: The circuit's JSON file as the panel uploads it.
    """
    circuit = ProbabilisticCircuit()
    x = Continuous("x")
    color = Symbolic("color", domain=Set.from_iterable(list(COLOR_PROBABILITIES)))
    probabilities = MissingDict(
        float, {hash(value): p for value, p in COLOR_PROBABILITIES.items()}
    )
    product = ProductUnit(probabilistic_circuit=circuit)
    product.add_subcircuit(
        leaf(
            UniformDistribution(variable=x, interval=closed(0, 1).simple_sets[0]),
            circuit,
        )
    )
    product.add_subcircuit(
        leaf(SymbolicDistribution(variable=color, probabilities=probabilities), circuit)
    )
    return ModelUpload(name=NAME, text=json.dumps(circuit.to_json()))
