"""Read JSON-shaped input with the full Japanese path in every error."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Literal

from .errors import InputError
from .printed import Precision, Printed

Sign = Literal["nonnegative", "positive", "any"]
Key = str | int


class Reader:
    """A value and the path that reached it."""

    def __init__(self, value: Any, path: str = "") -> None:
        self.value = value
        self.path = path

    def _child(self, key: Key) -> Reader:
        if isinstance(key, int):
            return Reader(self.value[key], f"{self.path}[{key}]")
        return Reader(self.value[key], f"{self.path}.{key}" if self.path else key)

    def _has(self, key: Key) -> bool:
        if isinstance(key, int):
            return isinstance(self.value, list) and 0 <= key < len(self.value)
        return isinstance(self.value, dict) and key in self.value

    def at(self, *keys: Key) -> Reader:
        current = self
        for key in keys:
            if not current._has(key):
                missing = f"{current.path}[{key}]" if isinstance(key, int) else (
                    f"{current.path}.{key}" if current.path else key)
                raise InputError(f"入力項目がありません: {missing}")
            current = current._child(key)
        return current

    def optional(self, key: Key) -> Reader | None:
        """The item, or None when it is absent or null."""
        if not self._has(key):
            return None
        child = self._child(key)
        return None if child.is_null else child

    @property
    def is_null(self) -> bool:
        return self.value is None

    def error(self, message: str) -> InputError:
        return InputError(f"{self.path}: {message}")

    def number(self, *, sign: Sign = "nonnegative") -> float:
        if sign not in ("nonnegative", "positive", "any"):
            raise ValueError(f"unknown sign rule: {sign!r}")
        value = self.value
        if value is None:
            raise self.error("値が必要です")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise self.error(f"有限の数値が必要です（入力: {value!r}）")
        try:
            result = float(value)
        except OverflowError:
            raise self.error("有限の数値が必要です（大きすぎます）") from None
        if not math.isfinite(result):
            raise self.error(f"有限の数値が必要です（入力: {value!r}）")
        if sign == "positive" and result <= 0:
            raise self.error("正の数値が必要です")
        if sign == "nonnegative" and result < 0:
            raise self.error("0以上の数値が必要です")
        return result

    def printed(self, precision: Precision, *, sign: Sign = "nonnegative") -> Printed:
        """A number that must already be at the printed digits (decision 17)."""
        number = self.number(sign=sign)
        try:
            return precision.exact(number)
        except ValueError as exc:
            raise self.error(str(exc)) from None

    def integer(self, minimum: int, maximum: int) -> int:
        if type(self.value) is not int or not minimum <= self.value <= maximum:
            raise self.error(f"{minimum}～{maximum}の整数が必要です（入力: {self.value!r}）")
        return self.value

    def boolean(self) -> bool:
        if not isinstance(self.value, bool):
            raise self.error(f"true か false が必要です（入力: {self.value!r}）")
        return self.value

    def text(self) -> str:
        value = self.value
        if not isinstance(value, str) or not value.strip():
            raise self.error(f"空でない文字列が必要です（入力: {value!r}）")
        if value != value.strip():
            raise self.error(f"前後の空白を除いてください（入力: {value!r}）")
        return value

    def choice(self, options: Sequence[str]) -> str:
        value = self.text()
        if value not in options:
            listed = "".join(f"「{option}」" for option in options)
            raise self.error(f"{listed}のいずれかを選んでください（入力: {value!r}）")
        return value

    def items(self, *, minimum: int = 0, maximum: int | None = None) -> list[Reader]:
        if not isinstance(self.value, list):
            raise self.error("配列が必要です")
        count = len(self.value)
        if count < minimum or (maximum is not None and count > maximum):
            limit = f"{minimum}～{maximum}件" if maximum is not None else f"{minimum}件以上"
            raise self.error(f"{limit}の配列が必要です（{count}件）")
        return [self._child(index) for index in range(count)]

    def only(self, *allowed: str) -> Reader:
        """Reject keys the schema does not define, so a misspelt key is not ignored."""
        for key in self.mapping():
            if key not in allowed:
                raise self._child(key).error("未知の入力項目です")
        return self

    def mapping(self) -> dict[str, Any]:
        if not isinstance(self.value, dict):
            raise self.error("オブジェクトが必要です")
        return self.value
