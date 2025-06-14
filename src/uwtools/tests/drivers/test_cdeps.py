"""
CDEPS driver tests.
"""

from copy import deepcopy
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import f90nml  # type: ignore[import-untyped]
import iotaa
from pytest import fixture, mark

from uwtools.config.formats.nml import NMLConfig
from uwtools.drivers import cdeps
from uwtools.drivers.cdeps import CDEPS
from uwtools.tests.test_schemas import CDEPS_CONFIG

# Fixtures


@fixture
def driverobj(tmp_path, utc):
    return CDEPS(
        config={"cdeps": {**deepcopy(CDEPS_CONFIG), "rundir": str(tmp_path / "run")}}, cycle=utc()
    )


# Helpers


@iotaa.external
def ok():
    yield "ok"
    yield iotaa.asset(None, lambda: True)


# Tests


def test_CDEPS_atm(driverobj):
    with patch.object(CDEPS, "atm_nml", wraps=ok()) as atm_nml:
        with patch.object(CDEPS, "atm_stream", wraps=ok()) as atm_stream:
            driverobj.atm()
        atm_stream.assert_called_once_with()
    atm_nml.assert_called_once_with()


def test_CDEPS_driver_name(driverobj):
    assert driverobj.driver_name() == CDEPS.driver_name() == "cdeps"


@mark.parametrize("group", ["atm", "ocn"])
def test_CDEPS_nml(driverobj, group, logged):
    dst = driverobj.rundir / f"d{group}_in"
    assert not dst.is_file()
    del driverobj._config[f"{group}_in"]["base_file"]
    task = getattr(driverobj, f"{group}_nml")
    path = Path(task().ref)
    assert dst.is_file()
    assert logged(f"Wrote config to {path}")
    assert isinstance(f90nml.read(dst), f90nml.Namelist)


def test_CDEPS_ocn(driverobj):
    with patch.object(CDEPS, "ocn_nml", wraps=ok()) as ocn_nml:
        with patch.object(CDEPS, "ocn_stream", wraps=ok()) as ocn_stream:
            driverobj.ocn()
        ocn_stream.assert_called_once_with()
    ocn_nml.assert_called_once_with()


@mark.parametrize("group", ["atm", "ocn"])
def test_CDEPS_streams(driverobj, group):
    dst = driverobj.rundir / f"d{group}.streams"
    assert not dst.is_file()
    template = """
    {{ streams.stream01.dtlimit }}
    {{ streams.stream01.mapalgo }}
    {{ streams.stream01.readmode }}
    {{ " ".join(streams.stream01.stream_data_files) }}
    {{ " ".join(streams.stream01.stream_data_variables) }}
    {{ streams.stream01.stream_lev_dimname }}
    {{ streams.stream01.stream_mesh_file }}
    {{ streams.stream01.stream_offset }}
    {{ " ".join(streams.stream01.stream_vectors) }}
    {{ streams.stream01.taxmode }}
    {{ streams.stream01.tinterpalgo }}
    {{ streams.stream01.yearAlign }}
    {{ streams.stream01.yearFirst }}
    {{ streams.stream01.yearLast }}
    """
    template_file = driverobj.rundir.parent / "template.jinja2"
    template_file.write_text(dedent(template).strip())
    driverobj._config[f"{group}_streams"]["template_file"] = template_file
    task = getattr(driverobj, f"{group}_stream")
    path = Path(task().ref)
    assert dst.is_file()
    expected = """
    1.5
    string
    single
    string string
    string string
    string
    string
    1
    u v
    string
    string
    1
    1
    1
    """
    assert path.read_text().strip() == dedent(expected).strip()


def test_CDEPS__model_namelist_file(driverobj):
    group = "atm_in"
    path = Path("/path/to/some.nml")
    with patch.object(driverobj, "create_user_updated_config") as cuuc:
        driverobj._model_namelist_file(group=group, path=path)
        cuuc.assert_called_once_with(
            config_class=NMLConfig, config_values=driverobj.config[group], path=path
        )


def test_CDEPS__model_stream_file(driverobj):
    group = "atm_streams"
    path = Path("/path/to/some.streams")
    template_file = Path("/path/to/some.jinja2")
    with patch.object(cdeps, "_render") as render:
        driverobj._model_stream_file(group=group, path=path, template_file=template_file)
        render.assert_called_once_with(
            input_file=template_file,
            output_file=path,
            values_src=driverobj.config[group],
        )
