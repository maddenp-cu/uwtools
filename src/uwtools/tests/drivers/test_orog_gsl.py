"""
orog_gsl driver tests.
"""

from pathlib import Path
from unittest.mock import patch

from pytest import fixture

from uwtools.drivers.orog_gsl import OrogGSL

# Fixtures


@fixture
def config(tmp_path):
    afile = tmp_path / "afile"
    afile.touch()
    return {
        "orog_gsl": {
            "config": {
                "halo": 4,
                "input_grid_file": str(afile),
                "resolution": 403,
                "tile": 7,
                "topo_data_2p5m": str(afile),
                "topo_data_30s": str(afile),
            },
            "execution": {
                "batchargs": {
                    "walltime": "00:01:00",
                },
                "executable": "/path/to/orog_gsl",
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
    return OrogGSL(config=config, batch=True)


# Tests


def test_OrogGSL_driver_name(driverobj):
    assert driverobj.driver_name() == OrogGSL.driver_name() == "orog_gsl"


def test_OrogGSL_input_config_file(driverobj):
    driverobj.input_config_file()
    inputs = [str(driverobj.config["config"][k]) for k in ("tile", "resolution", "halo")]
    content = Path(driverobj._input_config_path).read_text().strip().split("\n")
    assert len(content) == 3
    assert content == inputs


def test_OrogGSL_input_grid_file(driverobj):
    path = Path(driverobj.config["rundir"], "C403_grid.tile7.halo4.nc")
    assert not path.is_file()
    driverobj.input_grid_file()
    assert path.is_symlink()


def test_OrogGSL_output(driverobj):
    outfile = lambda x: driverobj.rundir / f"C403_oro_data_{x}.tile7.halo4.nc"
    assert driverobj.output == {"ls": outfile("ls"), "ss": outfile("ss")}


def test_OrogGSL_provisioned_rundir(driverobj, ready_task):
    with patch.multiple(
        driverobj,
        input_config_file=ready_task,
        input_grid_file=ready_task,
        runscript=ready_task,
        topo_data_2p5m=ready_task,
        topo_data_30s=ready_task,
    ) as mocks:
        driverobj.provisioned_rundir()
    for m in mocks:
        mocks[m].assert_called_once_with()


def test_OrogGSL_topo_data_2p5m(driverobj):
    path = Path(driverobj.config["rundir"], "geo_em.d01.lat-lon.2.5m.HGT_M.nc")
    assert not path.is_file()
    driverobj.topo_data_2p5m()
    assert path.is_symlink()


def test_OrogGSL_topo_data_3os(driverobj):
    path = Path(driverobj.config["rundir"], "HGT.Beljaars_filtered.lat-lon.30s_res.nc")
    assert not path.is_file()
    driverobj.topo_data_30s()
    assert path.is_symlink()


def test_OrogGSL__runcmd(driverobj):
    assert driverobj._runcmd == "%s < %s" % (
        driverobj.config["execution"]["executable"],
        driverobj._input_config_path.name,
    )
