"""Settings definitions shared by runtime assignments and saved-profile loading.

Models prepare a complete candidate before publishing it. They do not construct
widgets, emit signals, access hardware, or write back recovery defaults.
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import logging
import math
import re
from typing import Any, Callable, ClassVar, Generic, Mapping, TypeVar, cast

from PyQt6.QtGui import QIntValidator


logger = logging.getLogger(__name__)
_INTEGER = re.compile(r"[+-]?\d+\Z")
T = TypeVar("T")
Number = TypeVar("Number", int, float)
E = TypeVar("E", bound=Enum)


def _qt_int_limits() -> tuple[int, int]:
    # Qt exposes these through documented validator defaults, rather than
    # numeric-limit constants in PyQt. Retain only the numbers, not a QObject.
    validator = QIntValidator()
    return validator.bottom(), validator.top()


QT_INT_MIN, QT_INT_MAX = _qt_int_limits()


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not (
        isinstance(value, int)
        or isinstance(value, str) and _INTEGER.fullmatch(value)
    ):
        raise ValueError("must be an integer")
    return int(value)


class SettingsValueError(ValueError):
    """An assignment is invalid; keys identifies a dependent recovery group."""

    def __init__(self, message: str, *, keys: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.keys = keys


@dataclass(frozen=True)
class Setting(Generic[T], ABC):
    """A definition's default and value contract, independent of its editor."""

    default: T

    def coerce(self, value: Any) -> T:
        try:
            return self._coerce(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise SettingsValueError(str(error)) from error

    @abstractmethod
    def _coerce(self, value: Any) -> T:
        """Decode and validate one complete value."""


@dataclass(frozen=True)
class NumericSetting(Setting[Number], ABC):
    minimum: Number
    maximum: Number

    def _coerce(self, value: Any) -> Number:
        result = self._number(value)
        if result < self.minimum:
            raise ValueError(f"must be at least {self.minimum}")
        if result > self.maximum:
            raise ValueError(f"must be at most {self.maximum}")
        return result

    @abstractmethod
    def _number(self, value: Any) -> Number:
        """Decode a number before checking this setting's range."""


@dataclass(frozen=True)
class IntSetting(NumericSetting[int]):
    minimum: int = QT_INT_MIN
    maximum: int = QT_INT_MAX

    def __post_init__(self) -> None:
        if not QT_INT_MIN <= self.minimum <= self.maximum <= QT_INT_MAX:
            raise ValueError("integer setting bounds must fit Qt's integer range")

    def _number(self, value: Any) -> int:
        return _integer(value)


@dataclass(frozen=True)
class FloatSetting(NumericSetting[float]):
    minimum: float = -math.inf
    maximum: float = math.inf

    def _number(self, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError("must be numeric")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("must be finite")
        return result


@dataclass(frozen=True)
class ChoiceSetting(Setting[int]):
    """Labels define a stored integer index, without a second set of bounds."""

    labels: tuple[str, ...]

    def _coerce(self, value: Any) -> int:
        result = _integer(value)
        if not 0 <= result < len(self.labels):
            raise ValueError("is not a supported choice")
        return result


class BoolSetting(Setting[bool]):
    def _coerce(self, value: Any) -> bool:
        if isinstance(value, str) and value.lower() in ("true", "false", "0", "1"):
            return value.lower() in ("true", "1")
        if isinstance(value, (bool, int)) and value in (False, True):
            return bool(value)
        raise ValueError("must be a boolean")


@dataclass(frozen=True)
class ValueSetting(Setting[T]):
    """Plain values infer their type from the default; structures may decode."""

    decode: Callable[[Any], T] | None = None

    def _coerce(self, value: Any) -> T:
        if self.decode is not None:
            value = self.decode(value)
        if not isinstance(value, type(self.default)):
            raise ValueError(f"must be {type(self.default).__name__}")
        return cast(T, value)


@dataclass(frozen=True, init=False)
class EnumSetting(Setting[int]):
    """Use Qt's actual enum values while retaining the saved integer format."""

    enum_type: type[Enum]
    labels: tuple[str, ...]

    def __init__(self, default: E, *, labels: Mapping[E, str] | None = None) -> None:
        members = tuple(type(default))
        object.__setattr__(self, "default", int(default.value))
        object.__setattr__(self, "enum_type", type(default))
        object.__setattr__(self, "labels", tuple(
            labels.get(member, member.name) if labels is not None else member.name
            for member in members
        ))

    @property
    def members(self) -> tuple[Enum, ...]:
        return tuple(self.enum_type)

    @property
    def values(self) -> tuple[int, ...]:
        return tuple(int(member.value) for member in self.members)

    def _coerce(self, value: Any) -> int:
        if isinstance(value, self.enum_type):
            value = value.value
        result = _integer(value)
        if result not in self.values:
            raise ValueError(f"is not a known {self.enum_type.__name__} value")
        return result


class SettingsModel:
    fields: ClassVar[dict[str, Setting[Any]]] = {}

    def __init__(self) -> None:
        self._values = {key: field.coerce(deepcopy(field.default)) for key, field in self.fields.items()}
        self.validate(self._values)

    def get(self, key: str) -> Any:
        # Mutable values must not offer a route around assignment validation.
        return deepcopy(self._values[key])

    def validate(self, values: Mapping[str, Any]) -> None:
        """Override for relationships that must hold for a complete candidate."""

    def update(self, values: Mapping[str, Any]) -> None:
        candidate = deepcopy(self._values)
        for key, value in values.items():
            try:
                candidate[key] = self.fields[key].coerce(value)
            except SettingsValueError as error:
                raise SettingsValueError(f"{key}: {error}", keys=(key,)) from error
        self.validate(candidate)
        self._values = candidate

    def set(self, key: str, value: Any) -> Any:
        self.update({key: value})
        return self.get(key)

    def restore(self, settings: Any) -> frozenset[str]:
        """Load fields without rewriting the store; report those recovered."""
        candidate = {}
        recovered: set[str] = set()
        for key, field in self.fields.items():
            try:
                candidate[key] = field.coerce(settings.value(key, deepcopy(field.default)))
            except SettingsValueError as error:
                logger.warning("Ignoring invalid setting %s/%s: %s; using default",
                               settings.group(), key, error)
                candidate[key] = field.coerce(deepcopy(field.default))
                recovered.add(key)
        # A domain invariant can identify the related fields that need recovery.
        # Defaults themselves must form a valid candidate (checked at creation).
        while True:
            try:
                self.validate(candidate)
                break
            except SettingsValueError as error:
                keys = error.keys or tuple(self.fields)
                if any(key not in self.fields for key in keys) or set(keys) <= recovered:
                    raise
                logger.warning("Ignoring invalid settings %s/%s: %s; using defaults",
                               settings.group(), ",".join(keys), error)
                for key in keys:
                    candidate[key] = self.fields[key].coerce(deepcopy(self.fields[key].default))
                recovered.update(keys)
        self._values = candidate
        return frozenset(recovered)

    def save(self, settings: Any) -> None:
        """Update owned keys only; unknown keys and their Qt values stay intact."""
        for key, value in self._values.items():
            settings.setValue(key, deepcopy(value))
