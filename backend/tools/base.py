from typing import Any
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, fields, replace
from anthropic.types.beta import BetaToolUnionParam


class BaseAnthropicTool(metaclass=ABCMeta):
    """Abstract base class for Anthropic-defined tools."""

    @abstractmethod
    def __call__(self, **kwargs) -> Any:
        """Execute the tool with the given arguments."""
        ...

    @abstractmethod
    def toParams(self) -> BetaToolUnionParam:
        """Return the API parameter representation of this tool."""
        raise NotImplementedError


@dataclass(kw_only=True, frozen=True)
class ToolResult:
    """Represents the result of a tool execution."""

    output: str | None = None
    error: str | None = None
    base64_image: str | None = None
    system: str | None = None

    def __bool__(self):
        """Return True if any field is set."""
        return any(getattr(self, field.name) for field in fields(self))

    def __add__(self, other: "ToolResult"):
        """Combine two ToolResults by concatenating their fields."""

        def combine(
            field: str | None, other_field: str | None, concatenate: bool = True
        ):
            if field and other_field:
                if concatenate:
                    return field + other_field
                raise ValueError("Cannot combine tool results")
            return field or other_field

        return ToolResult(
            output=combine(self.output, other.output),
            error=combine(self.error, other.error),
            base64_image=combine(self.base64_image, other.base64_image, False),
            system=combine(self.system, other.system),
        )

    def replace(self, **kwargs):
        """Return a new ToolResult with the given fields replaced."""
        return replace(self, **kwargs)


class CLIResult(ToolResult):
    """A ToolResult that can be rendered as CLI output."""


class ToolFailure(ToolResult):
    """A ToolResult that represents a failure."""


class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        self.message = message
