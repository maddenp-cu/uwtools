"""
ESGGrid driver tests.
"""

from pathlib import Path
from unittest.mock import patch

import f90nml  # type: ignore[import-untyped]
from pytest import fixture

from uwtools.drivers.esg_grid import ESGGrid

# Fixtures


@fixture
def config(tmp_path):
    return {
        "esg_grid": {
            "execution": {
                "batchargs": {
                    "export": "NONE",
                    "nodes": 1,
                    "stdout": "/path/to/file",
                    "walltime": "00:02:00",
                },
                "executable": "/path/to/esg_grid",
            },
            "namelist": {
                "update_values": {
                    "regional_grid_nml": {
                        "delx": 0.11,
                        "dely": 0.11,
                        "lx": -214,
                        "ly": -128,
                        "pazi": 0.0,
                        "plat": 38.5,
                        "plon": -97.5,
                    }
                }
            },
            "rundir": str(tmp_path),
        },
        "platform": {
            "account": "me",
            "scheduler": "slurm",
        },
    }


@fixture
def driverobj(config):
    return ESGGrid(config=config, batch=True)


# Tests


def test_ESGGrid_driver_name(driverobj):
    assert driverobj.driver_name() == ESGGrid.driver_name() == "esg_grid"


def test_ESGGrid_namelist_file(driverobj, logged):
    dst = driverobj.rundir / "regional_grid.nml"
    assert not dst.is_file()
    path = Path(driverobj.namelist_file().ref)
    assert dst.is_file()
    assert logged(f"Wrote config to {path}")
    assert isinstance(f90nml.read(dst), f90nml.Namelist)


def test_ESGGrid_namelist_file_fails_validation(driverobj, logged):
    driverobj._config["namelist"]["update_values"]["regional_grid_nml"]["delx"] = "string"
    path = Path(driverobj.namelist_file().ref)
    assert not path.exists()
    assert logged(f"Failed to validate {path}")
    assert logged("  'string' is not of type 'number'")


def test_ESGGrid_namelist_file_missing_base_file(driverobj, logged):
    base_file = str(Path(driverobj.config["rundir"], "missing.nml"))
    driverobj._config["namelist"]["base_file"] = base_file
    path = Path(driverobj.namelist_file().ref)
    assert not path.exists()
    assert logged("missing.nml: Not ready [external asset]")


def test_ESGGrid_output(driverobj):
    assert driverobj.output["path"] == driverobj.rundir / "regional_grid.nc"


def test_ESGGrid_provisioned_rundir(driverobj, ready_task):
    with patch.multiple(
        driverobj,
        namelist_file=ready_task,
        runscript=ready_task,
    ) as mocks:
        driverobj.provisioned_rundir()
    for m in mocks:
        mocks[m].assert_called_once_with()
