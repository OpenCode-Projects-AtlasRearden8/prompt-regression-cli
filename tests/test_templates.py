import pytest

from prompt_regression_cli.errors import TemplateError
from prompt_regression_cli.templates import Variant, discover_versions, render_template


def make_variant(tmp_path, files):
    directory = tmp_path / "prompts" / "demo"
    directory.mkdir(parents=True)
    for name, content in files.items():
        (directory / name).write_text(content, encoding="utf-8")
    return directory


class TestDiscoverVersions:
    def test_picks_numbered_files(self, tmp_path):
        directory = make_variant(tmp_path, {"v1.md": "one", "v2.md": "two", "notes.md": "not a version"})
        versions = discover_versions(directory)
        assert sorted(versions) == [1, 2]
        assert versions[2].name == "v2.md"

    def test_ten_beats_two(self, tmp_path):
        directory = make_variant(tmp_path, {"v2.md": "two", "v10.md": "ten"})
        versions = discover_versions(directory)
        assert sorted(versions) == [2, 10]

    def test_no_versions_raises(self, tmp_path):
        directory = make_variant(tmp_path, {"draft.md": "x"})
        with pytest.raises(TemplateError, match="No versioned template"):
            discover_versions(directory)

    def test_missing_dir_raises(self, tmp_path):
        with pytest.raises(TemplateError, match="not found"):
            discover_versions(tmp_path / "nope")


class TestRenderTemplate:
    def test_substitutes_variables(self, tmp_path):
        directory = make_variant(tmp_path, {"v1.md": "Hello {name}, re: {issue}."})
        text = render_template(directory / "v1.md", {"name": "Sam", "issue": "the clip"})
        assert text == "Hello Sam, re: the clip."

    def test_missing_variable_raises_and_lists_all(self, tmp_path):
        directory = make_variant(tmp_path, {"v1.md": "{{name}} and {job}"})
        with pytest.raises(TemplateError, match="\\{job\\}"):
            render_template(directory / "v1.md", {"name": "Sam"})

    def test_literal_braces_survive(self, tmp_path):
        directory = make_variant(tmp_path, {"v1.md": 'Answer with JSON like {"ok": true}.'})
        text = render_template(directory / "v1.md", {"name": "x"})
        assert text == 'Answer with JSON like {"ok": true}.'

    def test_escaped_and_real_mixed(self, tmp_path):
        directory = make_variant(tmp_path, {"v1.md": "{name} -> {{literal}}"})
        text = render_template(directory / "v1.md", {"name": "Sam"})
        assert text == "Sam -> {literal}"

    def test_non_string_variable_is_stringified(self, tmp_path):
        directory = make_variant(tmp_path, {"v1.md": "count {n}"})
        assert render_template(directory / "v1.md", {"n": 3}) == "count 3"


class TestVariant:
    def test_latest_and_resolve(self, tmp_path):
        directory = make_variant(tmp_path, {"v1.md": "one", "v2.md": "two"})
        variant = Variant("demo", directory)
        assert variant.latest == 2
        assert variant.initial == 1
        assert variant.version_ids == ["v1", "v2"]

    def test_render_defaults_to_latest(self, tmp_path):
        directory = make_variant(tmp_path, {"v1.md": "one {x}", "v3.md": "three {x}"})
        variant = Variant("demo", directory)
        assert variant.render(variables={"x": 1}) == "three 1"
        assert variant.render(version="v1", variables={"x": 9}) == "one 9"

    def test_render_unknown_version(self, tmp_path):
        directory = make_variant(tmp_path, {"v1.md": "one {x}"})
        variant = Variant("demo", directory)
        with pytest.raises(TemplateError, match="no v5"):
            variant.render(version=5, variables={"x": 1})
