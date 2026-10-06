"""Machine-readable diagnostics emitted by the patch validator."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: str = "error"
    element_id: str | None = None
    path: str | None = None


@dataclass
class ValidationReport:
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def errors(self) -> list[Diagnostic]:
        return [item for item in self.diagnostics if item.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [item for item in self.diagnostics if item.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, code: str, message: str, *, severity: str = "error", element_id: str | None = None, path: str | None = None) -> None:
        self.diagnostics.append(Diagnostic(code, message, severity, element_id, path))
