"""Runtime Settings Foundation (04): central typed registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SettingKind = Literal["int", "float", "bool", "enum", "str"]
NormalizationRule = Literal["strip", "lowercase"]


@dataclass(frozen=True)
class SettingSpec:
    key: str
    kind: SettingKind
    default: int | float | bool | str | None
    min: int | float | None = None
    max: int | float | None = None
    allowed_values: tuple[str, ...] | None = None
    normalize: tuple[NormalizationRule, ...] = tuple()
    allow_default_fallback: bool = True

    def __post_init__(self) -> None:
        if self.kind == "enum":
            if not self.allowed_values:
                raise ValueError(f"{self.key}: enum settings require non-empty allowed_values")
        elif self.allowed_values is not None:
            raise ValueError(f"{self.key}: allowed_values is only valid for enum settings")

        if self.allowed_values is not None:
            if any(not isinstance(value, str) or not value for value in self.allowed_values):
                raise ValueError(f"{self.key}: allowed_values must contain only non-empty strings")
            if len(set(self.allowed_values)) != len(self.allowed_values):
                raise ValueError(f"{self.key}: allowed_values must not contain duplicates")

        if self.normalize and self.kind not in ("str", "enum"):
            raise ValueError(f"{self.key}: normalize is only valid for str or enum settings")

        unknown_normalize = tuple(rule for rule in self.normalize if rule not in ("strip", "lowercase"))
        if unknown_normalize:
            raise ValueError(f"{self.key}: unsupported normalize rules: {unknown_normalize}")

        if self.kind not in ("int", "float"):
            if self.min is not None or self.max is not None:
                raise ValueError(f"{self.key}: min/max are only valid for int or float settings")
        else:
            if self.min is not None and isinstance(self.min, bool):
                raise ValueError(f"{self.key}: min must not be bool")
            if self.max is not None and isinstance(self.max, bool):
                raise ValueError(f"{self.key}: max must not be bool")
            if self.min is not None and self.max is not None and self.min > self.max:
                raise ValueError(f"{self.key}: min must be <= max")

        if not self.key:
            raise ValueError("SettingSpec.key must be non-empty")

        if self.default is not None:
            self._validate_default_type()
            self._validate_default_constraints()

    def _validate_default_type(self) -> None:
        if self.kind == "bool":
            if not isinstance(self.default, bool):
                raise ValueError(f"{self.key}: default must be bool")
            return

        if self.kind == "int":
            if isinstance(self.default, bool) or not isinstance(self.default, int):
                raise ValueError(f"{self.key}: default must be int (bool is not allowed)")
            return

        if self.kind == "float":
            if isinstance(self.default, bool) or not isinstance(self.default, (int, float)):
                raise ValueError(f"{self.key}: default must be float-compatible number (bool is not allowed)")
            return

        if self.kind == "str":
            if not isinstance(self.default, str):
                raise ValueError(f"{self.key}: default must be str")
            return

        if self.kind == "enum":
            if not isinstance(self.default, str):
                raise ValueError(f"{self.key}: enum default must be str")
            return

        raise ValueError(f"{self.key}: unsupported setting kind '{self.kind}'")

    def _validate_default_constraints(self) -> None:
        if self.kind in ("int", "float"):
            numeric_default: int | float
            if self.kind == "float":
                if isinstance(self.default, bool) or not isinstance(self.default, (int, float)):
                    raise ValueError(f"{self.key}: default must be numeric for bound checks")
                numeric_default = float(self.default)
            else:
                if isinstance(self.default, bool) or not isinstance(self.default, int):
                    raise ValueError(f"{self.key}: default must be numeric for bound checks")
                numeric_default = self.default
            if isinstance(numeric_default, bool) or not isinstance(numeric_default, (int, float)):
                raise ValueError(f"{self.key}: default must be numeric for bound checks")
            if self.min is not None and numeric_default < self.min:
                raise ValueError(f"{self.key}: default is below min")
            if self.max is not None and numeric_default > self.max:
                raise ValueError(f"{self.key}: default is above max")
            return

        if self.kind == "enum":
            allowed = self.allowed_values or tuple()
            normalized_default = self.default
            if isinstance(normalized_default, str):
                if "strip" in self.normalize:
                    normalized_default = normalized_default.strip()
                if "lowercase" in self.normalize:
                    normalized_default = normalized_default.lower()
            if normalized_default not in allowed:
                raise ValueError(f"{self.key}: enum default must be one of allowed_values after normalization")


RUNTIME_SETTINGS_FOUNDATION_REGISTRY: dict[str, SettingSpec] = {
    "analysis.max_files": SettingSpec(
        key="analysis.max_files",
        kind="int",
        default=50,
        min=1,
        max=5000,
    ),
    "analysis.score.threshold": SettingSpec(
        key="analysis.score.threshold",
        kind="float",
        default=0.5,
        min=0.0,
        max=1.0,
    ),
    "analysis.enabled": SettingSpec(
        key="analysis.enabled",
        kind="bool",
        default=True,
    ),
    "analysis.mode": SettingSpec(
        key="analysis.mode",
        kind="enum",
        default="standard",
        allowed_values=("fast", "standard", "deep"),
        normalize=("strip", "lowercase"),
    ),
    "analysis.note": SettingSpec(
        key="analysis.note",
        kind="str",
        default="",
        normalize=("strip",),
    ),
}
