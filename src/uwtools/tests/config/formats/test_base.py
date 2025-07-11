"""
Tests for the uwtools.config.base module.
"""

import os
from copy import deepcopy
from datetime import datetime
from textwrap import dedent
from typing import cast
from unittest.mock import patch

import yaml
from pytest import fixture, mark, raises

from uwtools.config import tools
from uwtools.config.formats.base import Config
from uwtools.config.formats.yaml import YAMLConfig
from uwtools.config.support import depth
from uwtools.exceptions import UWConfigError
from uwtools.tests.support import fixture_path
from uwtools.utils.file import FORMAT, readable

# Fixtures


@fixture
def config(tmp_path):
    path = tmp_path / "config.yaml"
    data = {"foo": 42}
    path.write_text(yaml.dump(data))
    return ConcreteConfig(config=path)


# Helpers


class ConcreteConfig(Config):
    """
    Config subclass for testing purposes.
    """

    @classmethod
    def _dict_to_str(cls, cfg):
        pass

    @staticmethod
    def _get_depth_threshold():
        pass

    @staticmethod
    def _get_format():
        pass

    def _load(self, config_file):
        with readable(config_file) as f:
            return yaml.safe_load(f.read())

    def as_dict(self):
        return self.data

    def dump(self, path=None):
        pass

    @staticmethod
    def dump_dict(cfg, path=None):
        pass


# Tests


def test__characterize_values(config):
    values = {1: "", 2: None, 3: "{{ n }}", 4: {"a": 42}, 5: [{"b": 43}], 6: "string"}
    complete, template = config._characterize_values(values=values, parent="p")
    assert complete == ["  p1", "  p2", "  p4", "  p4.a", "  pb", "  p5", "  p6"]
    assert template == ["  p3: {{ n }}"]


def test__depth(config):
    assert config._depth == 1


def test__load_paths(config, tmp_path):
    paths = (tmp_path / fn for fn in ("f1", "f2"))
    for path in paths:
        path.write_text(yaml.dump({path.name: "defined"}))
    cfg = config._load_paths(config_files=paths)
    for path in paths:
        assert cfg[path.name] == "present"


def test__parse_include(config):
    """
    Test that non-YAML handles include tags properly.
    """
    del config["foo"]
    # Create a symlink for the include file:
    include_path = fixture_path("fruit_config.yaml")
    config.data.update(
        {
            "config": {
                "salad_include": f"!include [{include_path}]",
                "meat": "beef",
                "dressing": "poppyseed",
            }
        }
    )
    config._parse_include()
    assert config["fruit"] == "papaya"
    assert config["how_many"] == 17
    assert config["config"]["meat"] == "beef"
    assert len(config["config"]) == 2


@mark.parametrize("fmt", [FORMAT.nml, FORMAT.yaml])
def test_compare_config(fmt, logged, salad_base):
    """
    Compare two config objects.
    """
    cfgobj = tools.format_to_config(fmt)(fixture_path(f"simple.{fmt}"))
    if fmt == FORMAT.ini:
        salad_base["salad"]["how_many"] = "12"  # str "12" (not int 12) for ini
    assert cfgobj.compare_config(salad_base) is True
    # Expect no differences:
    assert not logged(".*")
    # Create differences in base dict:
    salad_base["salad"]["dressing"] = "italian"
    salad_base["salad"]["size"] = "large"
    del salad_base["salad"]["how_many"]
    assert not cfgobj.compare_config(salad_base)
    # Expect to see the following differences logged:
    expected = """
    ---------------------------------------------------------------------
    ↓ ? = info | -/+ = line unique to - or + file | blank = matching line
    ---------------------------------------------------------------------
      salad:
        base: kale
    -   dressing: balsamic
    ?             ^  ^ ^^^
    +   dressing: italian
    ?             ^^  ^ ^
        fruit: banana
    -   how_many: 12
    +   size: large
        vegetable: tomato
    """
    for line in dedent(expected).strip("\n").split("\n"):
        assert logged(line)


def test_compare_config_ini(logged, salad_base):
    """
    Compare two config objects.
    """
    cfgobj = tools.format_to_config("ini")(fixture_path("simple.ini"))
    salad_base["salad"]["how_many"] = "12"  # str "12" (not int 12) for ini
    assert cfgobj.compare_config(salad_base) is True
    # Expect no differences:
    assert not logged(".*", regex=True)
    # Create differences in base dict:
    salad_base["salad"]["dressing"] = "italian"
    salad_base["salad"]["size"] = "large"
    del salad_base["salad"]["how_many"]
    assert not cfgobj.compare_config(cfgobj.as_dict(), salad_base, header=False)
    # Expect to see the following differences logged:
    expected = """
      salad:
        base: kale
    -   dressing: italian
    ?             ^^   ^^
    +   dressing: balsamic
    ?             ^  +++ ^
        fruit: banana
    -   size: large
    +   how_many: '12'
        vegetable: tomato
    """
    for line in dedent(expected).strip("\n").split("\n"):
        assert logged(line)
    anomalous = """
    ---------------------------------------------------------------------
    ↓ ? = info | -/+ = line unique to - or + file | blank = matching line
    ---------------------------------------------------------------------
    """
    for line in dedent(anomalous).strip("\n").split("\n"):
        assert not logged(line)


def test_config_from_config(config):
    assert config.config_file.name == "config.yaml"
    assert ConcreteConfig(config).data == config.data


@mark.parametrize("f", [dict, ConcreteConfig])
def test_config_from_config_immutable(f):
    sub = {"shared": 1}
    original = {"foo": "bar", "baz": sub}
    config = f(deepcopy(original))
    c = ConcreteConfig(config)
    assert c.data == original
    assert config == original
    config["baz"]["shared"] = 2
    assert c.data == original


def test_config_from_file(config):
    assert config.config_file.name == "config.yaml"
    assert config.config_file.is_file()


def test_dereference(tmp_path):
    # Test demonstrates that:
    #   - Config dereferencing ignores environment variables.
    #   - Initially-unrenderable values do not cause errors.
    #   - Initially-unrenderable values may be rendered via iteration.
    #   - Finally-unrenderable values do not cause errors and are returned unmodified.
    #   - Tagged scalars in collections are handled correctly.
    yaml = """
a: !int '{{ b.c + 11 }}'
b:
  c: !int '{{ l | int + 11 }}'
d: '{{ X }}'
e:
  - !bool "False"
  - !datetime '{{ i }}'
  - !dict "{ b0: 0, b1: 1, b2: 2,}"
  - !dict "[ ['c0',0], ['c1',1], ['c2',2], ]"
  - !float '3.14'
  - !int '42'
  - !list "[ a0, a1, a2, ]"
f:
  f1: True
  f2: !float '3.14'
  f3: !dict "{ b0: 0, b1: 1, b2: 2,}"
  f4: !dict "[ ['c0',0], ['c1',1], ['c2',2], ]"
  f5: !int '42'
  f6: !list "[ 0, 1, 2, ]"
g: !bool '{{ f.f3 }}'
h: !bool 0
i: 2024-10-10 00:19:00
j: !dict "{ b0: 0, b1: 1, b2: 2,}"
k: !list "[ a0, a1, a2, ]"
l: "22"

""".strip()
    path = tmp_path / "config.yaml"
    path.write_text(yaml)
    config = YAMLConfig(path)
    with patch.dict(os.environ, {"N": "999"}, clear=True):
        retval = config.dereference()
    assert retval is config
    assert config == {
        "a": 44,
        "b": {"c": 33},
        "d": "{{ X }}",
        "e": [
            False,
            datetime.fromisoformat("2024-10-10 00:19:00"),
            {"b0": 0, "b1": 1, "b2": 2},
            {"c0": 0, "c1": 1, "c2": 2},
            3.14,
            42,
            ["a0", "a1", "a2"],
        ],
        "f": {
            "f1": True,
            "f2": 3.14,
            "f3": {"b0": 0, "b1": 1, "b2": 2},
            "f4": {"c0": 0, "c1": 1, "c2": 2},
            "f5": 42,
            "f6": [0, 1, 2],
        },
        "g": True,
        "h": False,
        "i": datetime.fromisoformat("2024-10-10 00:19:00"),
        "j": {"b0": 0, "b1": 1, "b2": 2},
        "k": ["a0", "a1", "a2"],
        "l": "22",
    }


def test_dereference_context_override(tmp_path, utc):
    yaml = "file: gfs.t{{ cycle.strftime('%H') }}z.atmanl.nc"
    path = tmp_path / "config.yaml"
    path.write_text(yaml)
    config = YAMLConfig(path)
    config.dereference(context={"cycle": utc(2024, 2, 12, 6)})
    assert config["file"] == "gfs.t06z.atmanl.nc"


@mark.parametrize("fmt2", [FORMAT.ini, FORMAT.sh])
def test_invalid_config(fmt2, tmp_path):
    """
    Test that invalid config files will error when attempting to dump.
    """
    fmt1 = FORMAT.yaml
    outfile = tmp_path / f"test_{fmt1}to{fmt2}_dump.{fmt2}"
    cfgin = tools.format_to_config(fmt1)(fixture_path("hello_workflow.yaml"))
    depthin = depth(cfgin.data)
    with raises(UWConfigError) as e:
        cast(Config, tools.format_to_config(fmt2)).dump_dict(cfg=cfgin.data, path=outfile)
    assert f"Cannot dump depth-{depthin} config to type-'{fmt2}' config" in str(e.value)


def test_update_from(config):
    """
    Test that a config object can be updated.
    """
    config.data.update({"a": "11", "b": "12", "c": "13"})
    assert config == {"foo": 42, "a": "11", "b": "12", "c": "13"}
