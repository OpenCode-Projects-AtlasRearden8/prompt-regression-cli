import re
from pathlib import Path

from .errors import TemplateError

_VERSION_RE = re.compile(r"^v(\d+)$")
_SUBSTITUTION_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_OPEN = "\x00PRO\x00"
_CLOSE = "\x00PRC\x00"


def discover_versions(variant_dir):
    directory = Path(variant_dir)
    if not directory.is_dir():
        raise TemplateError(f"Prompt variant directory not found: {directory}")
    versions = {}
    for entry in sorted(directory.iterdir()):
        if not entry.is_file():
            continue
        match = _VERSION_RE.match(entry.stem)
        if match:
            versions[int(match.group(1))] = entry
    if not versions:
        raise TemplateError(
            f"No versioned template files in {directory}. Name them v1.md, v2.md, ... "
            "(highest number is the latest version)"
        )
    return versions


def render_template(path, variables):
    text = path.read_text(encoding="utf-8")
    escaped = text.replace("{{", _OPEN).replace("}}", _CLOSE)
    missing = sorted(
        {match.group(1) for match in _SUBSTITUTION_RE.finditer(escaped) if match.group(1) not in variables}
    )
    if missing:
        provided = sorted(str(key) for key in variables)
        raise TemplateError(
            f"Template {path} uses variables that were not provided: "
            + ", ".join("{" + name + "}" for name in missing)
            + f" (case variables: {provided})"
        )

    def replace(match):
        return str(variables[match.group(1)])

    return _SUBSTITUTION_RE.sub(replace, escaped).replace(_OPEN, "{").replace(_CLOSE, "}")


class Variant:
    def __init__(self, name, directory):
        self.name = name
        self.directory = Path(directory)
        self.versions = discover_versions(self.directory)

    @property
    def latest(self):
        return max(self.versions)

    @property
    def initial(self):
        return min(self.versions)

    @property
    def version_ids(self):
        return [f"v{n}" for n in sorted(self.versions)]

    def resolve(self, version=None):
        if version is None:
            return self.latest
        version = int(str(version).lstrip("v"))
        if version not in self.versions:
            raise TemplateError(
                f"Variant '{self.name}' has no v{version}. (available: "
                + ", ".join(self.version_ids)
                + ")"
            )
        return version

    def render(self, version=None, variables=None):
        number = self.resolve(version)
        path = self.versions[number]
        return render_template(path, variables or {})
