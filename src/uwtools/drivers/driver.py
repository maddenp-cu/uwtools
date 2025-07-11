"""
Abstract classes for component drivers.
"""

from __future__ import annotations

import json
import re
import stat
from abc import ABC, abstractmethod
from copy import deepcopy
from functools import partial
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Any, Union

from iotaa import asset, external, task, tasks

from uwtools.config.formats.yaml import YAMLConfig
from uwtools.config.tools import walk_key_path
from uwtools.config.validator import (
    bundle,
    internal_schema_file,
    validate,
    validate_external,
    validate_internal,
)
from uwtools.exceptions import UWConfigError, UWNotImplementedError
from uwtools.logging import log
from uwtools.scheduler import JobScheduler
from uwtools.strings import STR
from uwtools.utils.file import writable
from uwtools.utils.processing import run_shell_cmd

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from uwtools.config.formats.base import Config
    from uwtools.config.support import YAMLKey

# NB: Class docstrings are programmatically defined.


class Assets(ABC):
    """
    An abstract class to provision assets for component drivers.
    """

    def __init__(
        self,
        cycle: datetime | None = None,
        leadtime: timedelta | None = None,
        config: dict | str | Path | YAMLConfig | None = None,
        key_path: list[YAMLKey] | None = None,
        schema_file: Path | None = None,
        controller: list[YAMLKey] | None = None,
    ) -> None:
        config_copy = YAMLConfig(config)
        config_copy.dereference(
            context={
                **({STR.cycle: cycle} if cycle else {}),
                **({STR.leadtime: leadtime} if leadtime is not None else {}),
                **config_copy.data,
            }
        )
        self._config_full: dict = config_copy.data
        self._config_intermediate, _ = walk_key_path(self._config_full, key_path or [])
        try:
            self._config: dict = self._config_intermediate[self.driver_name()]
        except KeyError as e:
            msg = "Required '%s' block missing in config" % self.driver_name()
            raise UWConfigError(msg) from e
        self._delegate(controller, STR.rundir)
        self.schema_file = schema_file
        self._validate()

    def __repr__(self) -> str:
        cycle = self._cycle.strftime("%Y-%m-%dT%H:%M") if hasattr(self, "_cycle") else None
        leadtime = None
        if hasattr(self, "_leadtime"):
            h, r = divmod(self._leadtime.total_seconds(), 3600)
            m, s = divmod(r, 60)
            leadtime = "%02d:%02d:%02d" % (h, m, s)
        return " ".join(filter(None, [str(self), cycle, leadtime, "in", self.config[STR.rundir]]))

    def __str__(self) -> str:
        return self.driver_name()

    @property
    def config(self) -> dict:
        """
        A copy of the driver-specific config.
        """
        return deepcopy(self._config)

    @property
    def config_full(self) -> dict:
        """
        A copy of the original input config, dereferenced.
        """
        return deepcopy(self._config_full)

    @staticmethod
    def create_user_updated_config(
        config_class: type[Config], config_values: dict, path: Path, schema: dict | None = None
    ) -> None:
        """
        Create a config from a base file, user-provided values, or a combination of the two.

        :param config_class: The Config subclass matching the config type.
        :param config_values: The configuration object to update base values with.
        :param path: Path to dump file to.
        :param schema: Schema to validate final config against.
        """
        user_values = config_values.get(STR.updatevalues, {})
        if base_file := config_values.get(STR.basefile):
            cfgobj = config_class(base_file)
            cfgobj.update_from(user_values)
            cfgobj.dereference()
            config = cfgobj.data
            dump = partial(cfgobj.dump, path)
        else:
            config = user_values
            dump = partial(config_class.dump_dict, config, path)
        if validate(schema=schema or {"type": "object"}, desc="user-updated config", config=config):
            dump()
            log.debug("Wrote config to %s", path)
        else:
            log.debug("Failed to validate %s", path)

    @classmethod
    @abstractmethod
    def driver_name(cls) -> str:
        """
        The name of this driver.
        """

    def namelist_schema(
        self, config_keys: list[YAMLKey] | None = None, schema_keys: list[str] | None = None
    ) -> dict:
        """
        Return the (sub)schema for validating the driver's namelist content.

        :param config_keys: Keys leading to the namelist block in the driver config.
        :param schema_keys: Keys leading to the namelist-validating (sub)schema.
        """
        schema: dict = {"type": "object"}
        nmlcfg = self.config
        for config_key in config_keys or [STR.namelist]:
            nmlcfg = nmlcfg[config_key]
        if nmlcfg.get(STR.validate, True):
            schema_file = self.schema_file or internal_schema_file(schema_name=self._schema_name())
            schema = bundle(json.loads(schema_file.read_text()))
            for schema_key in schema_keys or [
                STR.properties,
                self.driver_name(),
                STR.properties,
                STR.namelist,
                STR.properties,
                STR.updatevalues,
            ]:
                schema = schema[schema_key]
        return schema

    @property
    def rundir(self) -> Path:
        """
        The path to the component's run directory.
        """
        return Path(self.config[STR.rundir]).absolute()

    @classmethod
    def schema(cls) -> dict:
        """
        Return the driver's internal schema.
        """
        path = internal_schema_file(schema_name=cls._schema_name())
        return bundle(json.loads(path.read_text()))

    def taskname(self, suffix: str | None = None) -> str:
        """
        Return a common tag for task-related log messages.

        :param suffix: Log-string suffix.
        """
        cycle = getattr(self, "_cycle", None)
        leadtime = getattr(self, "_leadtime", None)
        timestr = (
            (cycle + leadtime).strftime("%Y%m%d %H:%M:%S")
            if cycle and leadtime is not None
            else cycle.strftime("%Y%m%d %HZ")
            if cycle
            else None
        )
        return " ".join(filter(None, [timestr, self.driver_name(), suffix]))

    # Workflow tasks

    @external
    def validate(self):
        """
        Validate the UW driver config.
        """
        yield self.taskname("valid schema")
        yield asset(None, lambda: True)

    # Private helper methods

    def _delegate(self, controller: list[YAMLKey] | None, config_key: str) -> None:
        """
        Selectively delegate config to controller.

        :param controller: Key(s) leading to block in config controlling run-time values.
        :param config_key: Name of config item to delegate to controller.
        """
        if controller:
            val = self._config_intermediate[controller[0]]
            for key in controller[1:]:
                val = val[key]
            self._config[config_key] = val[config_key]

    @classmethod
    def _schema_name(cls) -> str:
        """
        Return the filename stem for this driver's schema file.
        """
        return cls.driver_name().replace("_", "-")

    def _validate(self) -> None:
        """
        Perform all necessary schema validation.

        :raises: UWConfigError if config fails validation.
        """
        kwargs: dict = {
            "config_data": self._config_intermediate,
            "desc": "%s config" % self.driver_name(),
        }
        if self.schema_file:
            validate_external(schema_file=self.schema_file, **kwargs)
        else:
            validate_internal(schema_name=self._schema_name(), **kwargs)


class AssetsCycleBased(Assets):
    """
    An abstract class to provision assets for cycle-based components.
    """

    def __init__(
        self,
        cycle: datetime,
        config: dict | str | YAMLConfig | Path | None = None,
        key_path: list[YAMLKey] | None = None,
        schema_file: Path | None = None,
        controller: list[YAMLKey] | None = None,
    ):
        super().__init__(
            cycle=cycle,
            config=config,
            key_path=key_path,
            schema_file=schema_file,
            controller=controller,
        )
        self._cycle = cycle

    @property
    def cycle(self):
        """
        The cycle.
        """
        return self._cycle


class AssetsCycleLeadtimeBased(Assets):
    """
    An abstract class to provision assets for cycle-and-leadtime-based components.
    """

    def __init__(
        self,
        cycle: datetime,
        leadtime: timedelta,
        config: dict | str | YAMLConfig | Path | None = None,
        key_path: list[YAMLKey] | None = None,
        schema_file: Path | None = None,
        controller: list[YAMLKey] | None = None,
    ):
        super().__init__(
            cycle=cycle,
            leadtime=leadtime,
            config=config,
            key_path=key_path,
            schema_file=schema_file,
            controller=controller,
        )
        self._cycle = cycle
        self._leadtime = leadtime

    @property
    def cycle(self):
        """
        The cycle.
        """
        return self._cycle

    @property
    def leadtime(self):
        """
        The leadtime.
        """
        return self._leadtime


class AssetsTimeInvariant(Assets):
    """
    An abstract class to provision assets for time-invariant components.
    """

    def __init__(
        self,
        config: dict | str | YAMLConfig | Path | None = None,
        key_path: list[YAMLKey] | None = None,
        schema_file: Path | None = None,
        controller: list[YAMLKey] | None = None,
    ):
        super().__init__(
            config=config,
            key_path=key_path,
            schema_file=schema_file,
            controller=controller,
        )


class Driver(Assets):
    """
    An abstract class for standalone component drivers.
    """

    def __init__(
        self,
        cycle: datetime | None = None,
        leadtime: timedelta | None = None,
        config: dict | str | YAMLConfig | Path | None = None,
        key_path: list[YAMLKey] | None = None,
        batch: bool = False,
        schema_file: Path | None = None,
        controller: list[YAMLKey] | None = None,
    ):
        super().__init__(
            cycle=cycle,
            leadtime=leadtime,
            config=config,
            key_path=key_path,
            schema_file=schema_file,
            controller=controller,
        )
        self._batch = batch
        self._delegate(controller, STR.execution)

    # Workflow tasks

    @tasks
    @abstractmethod
    def provisioned_rundir(self):
        """
        Run directory provisioned with all required content.
        """

    @tasks
    def run(self):
        """
        A run.
        """
        yield self.taskname(STR.run)
        yield self._run_via_batch_submission() if self._batch else self._run_via_local_execution()

    @task
    def runscript(self):
        """
        The runscript.
        """
        path = self._runscript_path
        yield self.taskname(path.name)
        yield asset(path, path.is_file)
        yield None
        self._write_runscript(path)

    @external
    def show_output(self):
        """
        Show the output to be created by this component.
        """
        yield self.taskname("expected output")
        try:
            print(json.dumps(self.output, indent=2, sort_keys=True))
        except UWConfigError as e:
            log.error(e)
        yield asset(None, lambda: True)

    @task
    def _run_via_batch_submission(self):
        """
        A run executed via the batch system.
        """
        yield self.taskname("run via batch submission")
        path = Path("%s.submit" % self._runscript_path)
        yield asset(path, path.is_file)
        yield self.provisioned_rundir()
        self._scheduler.submit_job(runscript=self._runscript_path, submit_file=path)

    @task
    def _run_via_local_execution(self):
        """
        A run executed directly on the local system.
        """
        yield self.taskname("run via local execution")
        path = self.rundir / self._runscript_done_file
        yield asset(path, path.is_file)
        yield self.provisioned_rundir()
        cmd = "{x} >{x}.out 2>&1".format(x=self._runscript_path)
        run_shell_cmd(cmd=cmd, cwd=self.rundir, log_output=True)

    # Public methods

    @property
    def output(self) -> dict[str, Path] | dict[str, list[Path]]:
        """
        Returns a description of the file(s) created when this component runs.
        """
        msg = "The output() method is not yet implemented for this driver"
        raise UWNotImplementedError(msg)

    # Private methods

    @property
    def _run_resources(self) -> dict[str, Any]:
        """
        The platform configuration data.
        """
        if not (platform := self._config_intermediate.get("platform")):
            msg = "Required 'platform' block missing in config"
            raise UWConfigError(msg)
        threads = self.config.get(STR.execution, {}).get(STR.threads)
        return {
            STR.account: platform[STR.account],
            STR.rundir: self.rundir,
            STR.scheduler: platform[STR.scheduler],
            STR.stdout: "%s.out" % self._runscript_path.name,  # config may override
            **({STR.threads: threads} if threads else {}),
            **self.config.get(STR.execution, {}).get(STR.batchargs, {}),
        }

    @property
    def _runcmd(self) -> str:
        """
        The full command-line component invocation.
        """
        execution = self.config.get(STR.execution, {})
        mpiargs = execution.get(STR.mpiargs, [])
        components = [
            execution.get(STR.mpicmd),  # MPI run program
            *[str(x) for x in mpiargs],  # MPI arguments
            execution[STR.executable],  # component executable name
        ]
        return " ".join(filter(None, components))

    def _runscript(
        self,
        execution: list[str],
        envcmds: list[str] | None = None,
        envvars: dict[str, str] | None = None,
        scheduler: JobScheduler | None = None,
    ) -> str:
        """
        Return a driver runscript.

        :param execution: Statements to execute.
        :param envcmds: Shell commands to set up runtime environment.
        :param envvars: Environment variables to set in runtime environment.
        :param scheduler: A job-scheduler object.
        """
        # Render script sections into a template, remove any extraneous newlines related to elided
        # sections, then return the resulting string.
        template = """
        #!/bin/bash

        {directives}

        {envcmds}

        {envvars}

        {execution}
        """
        directives = scheduler.directives if scheduler else ""
        initcmds = scheduler.initcmds if scheduler else []
        rs = dedent(template).format(
            directives="\n".join(directives),
            envcmds="\n".join(envcmds or []),
            envvars="\n".join([f"export {k}={v}" for k, v in (envvars or {}).items()]),
            execution="\n".join([*initcmds, *execution]),
        )
        return re.sub(r"\n\n\n+", "\n\n", rs.strip())

    @property
    def _runscript_done_file(self):
        """
        The path to the done file produced by the successful completion of a run script.
        """
        return f"{self._runscript_path.name}.done"

    @property
    def _runscript_path(self) -> Path:
        """
        The path to the runscript.
        """
        return self.rundir / f"runscript.{self.driver_name()}"

    @property
    def _scheduler(self) -> JobScheduler:
        """
        The job scheduler specified by the platform information.
        """
        return JobScheduler.get_scheduler(self._run_resources)

    def _validate(self) -> None:
        """
        Perform all necessary schema validation.

        :raises: UWConfigError if config fails validation.
        """
        Assets._validate(self)  # noqa: SLF001
        validate_internal(
            schema_name=STR.platform,
            desc="platform config",
            config_data=self._config_intermediate,
        )

    def _write_runscript(self, path: Path, envvars: dict[str, str] | None = None) -> None:
        """
        Write the runscript.
        """
        envvars = envvars or {}
        threads = self.config.get(STR.execution, {}).get(STR.threads)
        if threads and "OMP_NUM_THREADS" not in envvars:
            msg = "Config specified threads but driver does not set OMP_NUM_THREADS"
            raise UWConfigError(msg)
        rs = self._runscript(
            envcmds=self.config.get(STR.execution, {}).get(STR.envcmds, []),
            envvars=envvars,
            execution=[
                "time %s" % self._runcmd,
                "test $? -eq 0 && touch %s" % self._runscript_done_file,
            ],
            scheduler=self._scheduler if self._batch else None,
        )
        with writable(path) as f:
            print(rs, file=f)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)


class DriverCycleBased(Driver):
    """
    An abstract class for standalone cycle-based component drivers.
    """

    def __init__(
        self,
        cycle: datetime,
        config: dict | str | YAMLConfig | Path | None = None,
        key_path: list[YAMLKey] | None = None,
        batch: bool = False,
        schema_file: Path | None = None,
        controller: list[YAMLKey] | None = None,
    ):
        super().__init__(
            cycle=cycle,
            config=config,
            key_path=key_path,
            batch=batch,
            schema_file=schema_file,
            controller=controller,
        )
        self._cycle = cycle

    @property
    def cycle(self):
        """
        The cycle.
        """
        return self._cycle


class DriverCycleLeadtimeBased(Driver):
    """
    An abstract class for standalone cycle-and-leadtime-based component drivers.
    """

    def __init__(
        self,
        cycle: datetime,
        leadtime: timedelta,
        config: dict | str | YAMLConfig | Path | None = None,
        key_path: list[YAMLKey] | None = None,
        batch: bool = False,
        schema_file: Path | None = None,
        controller: list[YAMLKey] | None = None,
    ):
        super().__init__(
            cycle=cycle,
            leadtime=leadtime,
            config=config,
            key_path=key_path,
            batch=batch,
            schema_file=schema_file,
            controller=controller,
        )
        self._cycle = cycle
        self._leadtime = leadtime

    @property
    def cycle(self):
        """
        The cycle.
        """
        return self._cycle

    @property
    def leadtime(self):
        """
        The leadtime.
        """
        return self._leadtime


class DriverTimeInvariant(Driver):
    """
    An abstract class for standalone time-invariant component drivers.
    """

    def __init__(
        self,
        config: dict | str | YAMLConfig | Path | None = None,
        key_path: list[YAMLKey] | None = None,
        batch: bool = False,
        schema_file: Path | None = None,
        controller: list[YAMLKey] | None = None,
    ):
        super().__init__(
            config=config,
            key_path=key_path,
            batch=batch,
            schema_file=schema_file,
            controller=controller,
        )


DriverT = Union[type[Assets], type[Driver]]


def _add_docstring(class_: type, omit: list[str] | None = None) -> None:
    """
    Dynamically add docstring to a driver class.

    :param class_: The class to add the docstring to.
    :param omit: Parameters to omit from the docstring.
    """
    base = """
    A driver.

    :param cycle: The cycle.
    :param leadtime: The leadtime.
    :param config: Path to config file (read stdin if missing or None).
    :param key_path: Keys of keys to driver config block.
    :param batch: Run component via the batch system?
    :param schema_file: Path to schema file to use to validate an external driver.
    :param controller: Key(s) leading to block in config controlling run-time values.
    """
    class_.__doc__ = "\n".join(
        line
        for line in dedent(base).strip().split("\n")
        if not any(line.startswith(f":param {o}:") for o in omit or [])
    )


_add_docstring(Assets, omit=[STR.batch])
_add_docstring(AssetsCycleBased, omit=[STR.batch, STR.leadtime])
_add_docstring(AssetsCycleLeadtimeBased, omit=[STR.batch])
_add_docstring(AssetsTimeInvariant, omit=[STR.batch, STR.cycle, STR.leadtime])
_add_docstring(Driver)
_add_docstring(DriverCycleBased, omit=[STR.leadtime])
_add_docstring(DriverCycleLeadtimeBased)
_add_docstring(DriverTimeInvariant, omit=[STR.cycle, STR.leadtime])
