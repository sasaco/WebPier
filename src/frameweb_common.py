"""Shared physical-action vectors for the directional FrameWeb adapters."""

from collections.abc import Iterable
import math

from .inputs import InputError


ActionKey = tuple[int, str, int, str]
ActionVector = dict[ActionKey, float]
NodeAction = tuple[int, float, float, float]
MemberAction = tuple[int, str, float]


def accumulate(vector: ActionVector, key: ActionKey, value: float) -> None:
    vector[key] = vector.get(key, 0) + value


def action_vector(
    nodes: Iterable[NodeAction], members: Iterable[MemberAction], spring: int,
) -> ActionVector:
    """Accumulate nodes then members, preserving row and component order."""
    vector: ActionVector = {}
    for identifier, *values in nodes:
        for axis, value in zip(("tx", "ty", "rz"), values, strict=True):
            accumulate(vector, (spring, "node", identifier, axis), value)
    for identifier, axis, value in members:
        accumulate(vector, (spring, "member", identifier, axis), value)
    return vector


def compare_vectors(
    actual: ActionVector, expected: ActionVector, path: str, message: str,
) -> None:
    for key in actual.keys() | expected.keys():
        a, e = actual.get(key, 0), expected.get(key, 0)
        if not math.isfinite(a) or abs(a - e) > 1e-10 + 1e-12 * max(abs(a), abs(e)):
            raise InputError(f"{path}: {message} ({key}: {a} != {e})")
