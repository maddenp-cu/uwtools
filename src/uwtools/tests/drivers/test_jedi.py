"""
JEDI driver tests.
"""

from pathlib import Path
from unittest.mock import call, patch

import iotaa
import yaml
from pytest import fixture, raises

from uwtools.config.formats.yaml import YAMLConfig
from uwtools.drivers import jedi, jedi_base
from uwtools.drivers.jedi import JEDI
from uwtools.exceptions import UWNotImplementedError

# Fixtures


@fixture
def config(tmp_path):
    base_file = tmp_path / "base.yaml"
    base_file.write_text("foo: bar")
    return {
        "jedi": {
            "execution": {
                "batchargs": {
                    "export": "NONE",
                    "nodes": 1,
                    "stdout": "/path/to/file",
                    "walltime": "00:02:00",
                },
                "envcmds": [
                    "module load some-module",
                    "module load jedi-module",
                ],
                "executable": "/path/to/qg_forecast.x",
                "mpiargs": ["--export=ALL", "--ntasks $SLURM_CPUS_ON_NODE"],
                "mpicmd": "srun",
            },
            "configuration_file": {
                "base_file": str(base_file),
                "update_values": {"baz": "qux"},
            },
            "files_to_copy": {
                "foo": "/path/to/foo",
                "bar/baz": "/path/to/baz",
            },
            "files_to_link": {
                "foo": "/path/to/foo",
                "bar/baz": "/path/to/baz",
            },
            "rundir": str(tmp_path),
        },
        "platform": {
            "account": "me",
            "scheduler": "slurm",
        },
    }


@fixture
def cycle(utc):
    return utc(2024, 2, 1, 18)


@fixture
def driverobj(config, cycle):
    return JEDI(config=config, cycle=cycle, batch=True)


# Tests


def test_JEDI_configuration_file(driverobj):
    basecfg = {"foo": "bar"}
    base_file = Path(driverobj.config["configuration_file"]["base_file"])
    base_file.write_text(yaml.dump(basecfg))
    cfgfile = Path(driverobj.config["rundir"], "jedi.yaml")
    assert not cfgfile.is_file()
    driverobj.configuration_file()
    assert cfgfile.is_file()
    newcfg = YAMLConfig(config=cfgfile)
    assert newcfg == {**basecfg, "baz": "qux"}


def test_JEDI_configuration_file_missing_base_file(driverobj, logged):
    base_file = Path(driverobj.config["rundir"], "missing")
    driverobj._config["configuration_file"]["base_file"] = base_file
    cfgfile = Path(driverobj.config["rundir"], "jedi.yaml")
    assert not cfgfile.is_file()
    driverobj.configuration_file()
    assert not cfgfile.is_file()
    assert logged(f"{base_file}: Not ready [external asset]")


def test_JEDI_driver_name(driverobj):
    assert driverobj.driver_name() == JEDI.driver_name() == "jedi"


def test_JEDI_files_copied(driverobj):
    with patch.object(jedi_base, "filecopy", wraps=jedi_base.filecopy) as filecopy:
        driverobj._config["rundir"] = "/path/to/run"
        driverobj.files_copied()
        assert filecopy.call_count == 2
        assert (
            call(src=Path("/path/to/baz"), dst=Path("/path/to/run/bar/baz"))
            in filecopy.call_args_list
        )
        assert (
            call(src=Path("/path/to/foo"), dst=Path("/path/to/run/foo")) in filecopy.call_args_list
        )


def test_JEDI_files_linked(driverobj):
    with patch.object(jedi_base, "symlink", wraps=jedi_base.symlink) as symlink:
        driverobj._config["rundir"] = "/path/to/run"
        driverobj.files_linked()
        assert symlink.call_count == 2
        assert (
            call(target=Path("/path/to/baz"), linkname=Path("/path/to/run/bar/baz"))
            in symlink.call_args_list
        )
        assert (
            call(target=Path("/path/to/foo"), linkname=Path("/path/to/run/foo"))
            in symlink.call_args_list
        )


def test_JEDI_output(driverobj):
    with raises(UWNotImplementedError) as e:
        assert driverobj.output
    assert str(e.value) == "The output() method is not yet implemented for this driver"


def test_JEDI_provisioned_rundir(driverobj, ready_task):
    with patch.multiple(
        driverobj,
        configuration_file=ready_task,
        files_copied=ready_task,
        files_linked=ready_task,
        runscript=ready_task,
        validate_only=ready_task,
    ) as mocks:
        driverobj.provisioned_rundir()
    for m in mocks:
        mocks[m].assert_called_once_with()


def test_JEDI_taskname(driverobj):
    assert driverobj.taskname("foo") == "20240201 18Z jedi foo"


def test_JEDI_validate_only(driverobj, logged):
    @iotaa.external
    def file(path: Path):
        yield "Mocked file task for %s" % path
        yield iotaa.asset(path, lambda: True)

    with patch.object(jedi, "file", file), patch.object(jedi, "run_shell_cmd") as run_shell_cmd:
        run_shell_cmd.return_value = (True, None)
        driverobj.validate_only()
        cfgfile = Path(driverobj.config["rundir"], "jedi.yaml")
        cmds = [
            "module load some-module",
            "module load jedi-module",
            "time %s --validate-only %s 2>&1"
            % (driverobj.config["execution"]["executable"], cfgfile),
        ]
        run_shell_cmd.assert_called_once_with(" && ".join(cmds))
    assert logged("Config is valid")


def test_JEDI__config_fn(driverobj):
    assert driverobj._config_fn == "jedi.yaml"


def test_JEDI__runcmd(driverobj):
    executable = driverobj.config["execution"]["executable"]
    config = driverobj.rundir / driverobj._config_fn
    assert (
        driverobj._runcmd == f"srun --export=ALL --ntasks $SLURM_CPUS_ON_NODE {executable} {config}"
    )
