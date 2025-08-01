"""
Canonical strings used throughout uwtools.
"""

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class FORMAT:
    """
    A mapping from config format names to literal strings.
    """

    # Canonical strings:

    _atparse: str = "atparse"
    _fieldtable: str = "fieldtable"
    _ini: str = "ini"
    _jinja2: str = "jinja2"
    _nml: str = "nml"
    _sh: str = "sh"
    _xml: str = "xml"
    _yaml: str = "yaml"

    # Variants:

    atparse: str = _atparse
    bash: str = _sh
    cfg: str = _ini
    fieldtable: str = _fieldtable
    ini: str = _ini
    jinja2: str = _jinja2
    nml: str = _nml
    sh: str = _sh
    yaml: str = _yaml
    yml: str = _yaml

    @staticmethod
    def extensions() -> list[str]:
        """
        Return recognized filename extensions.
        """
        return [FORMAT.ini, FORMAT.nml, FORMAT.sh, FORMAT.yaml]

    @staticmethod
    def formats() -> dict[str, str]:
        """
        Return the recognized format names.
        """
        return {
            field.name: str(getattr(FORMAT, field.name))
            for field in fields(FORMAT)
            if not field.name.startswith("_")
        }


@dataclass(frozen=True)
class STR:
    """
    String lookup map.
    """

    account: str = "account"
    action: str = "action"
    basefile: str = "base_file"
    batch: str = "batch"
    batchargs: str = "batchargs"
    cdeps: str = "cdeps"
    cfgfile: str = "config_file"
    chgrescube: str = "chgres_cube"
    classname: str = "classname"
    compare: str = "compare"
    config: str = "config"
    copy: str = "copy"
    cycle: str = "cycle"
    database: str = "database"
    dryrun: str = "dry_run"
    env: str = "env"
    envcmds: str = "envcmds"
    esggrid: str = "esg_grid"
    executable: str = "executable"
    execute: str = "execute"
    execution: str = "execution"
    file: str = "file"
    filtertopo: str = "filter_topo"
    fmt1: str = "format1"
    fmt2: str = "format2"
    fs: str = "fs"
    fv3: str = "fv3"
    globalequivresol: str = "global_equiv_resol"
    graphfile: str = "graph_file"
    hardlink: str = "hardlink"
    help: str = "help"
    hsi: str = "hsi"
    htar: str = "htar"
    infile: str = "input_file"
    infmt: str = "input_format"
    ioda: str = "ioda"
    iterate: str = "iterate"
    jedi: str = "jedi"
    keypath: str = "key_path"
    keyvalpairs: str = "key_eq_val_pairs"
    leadtime: str = "leadtime"
    link: str = "link"
    makedirs: str = "makedirs"
    makehgrid: str = "make_hgrid"
    makesolomosaic: str = "make_solo_mosaic"
    mode: str = "mode"
    model: str = "model"
    module: str = "module"
    mpas: str = "mpas"
    mpasinit: str = "mpas_init"
    mpassit: str = "mpassit"
    mpiargs: str = "mpiargs"
    mpicmd: str = "mpicmd"
    namelist: str = "namelist"
    notready: str = "not-ready"
    orog: str = "orog"
    oroggsl: str = "orog_gsl"
    outfile: str = "output_file"
    outfmt: str = "output_format"
    path1: str = "path1"
    path2: str = "path2"
    platform: str = "platform"
    properties: str = "properties"
    quiet: str = "quiet"
    rate: str = "rate"
    ready: str = "ready"
    realize: str = "realize"
    render: str = "render"
    report: str = "report"
    rocoto: str = "rocoto"
    run: str = "run"
    rundir: str = "rundir"
    scheduler: str = "scheduler"
    schemafile: str = "schema_file"
    schism: str = "schism"
    searchpath: str = "search_path"
    sfcclimogen: str = "sfc_climo_gen"
    shave: str = "shave"
    showschema: str = "show_schema"
    stdout: str = "stdout"
    symlinkfallback: str = "symlink_fallback"
    targetdir: str = "target_dir"
    task: str = "task"
    tasks: str = "tasks"
    template: str = "template"
    threads: str = "threads"
    total: str = "total"
    translate: str = "translate"
    ungrib: str = "ungrib"
    updatefile: str = "update_file"
    updatefmt: str = "update_format"
    updatevalues: str = "update_values"
    upp: str = "upp"
    upp_assets: str = "upp_assets"
    url_scheme_file: str = "file"
    url_scheme_hsi: str = "hsi"
    url_scheme_htar: str = "htar"
    url_scheme_http: str = "http"
    url_scheme_https: str = "https"
    validate: str = "validate"
    valsfile: str = "values_file"
    valsfmt: str = "values_format"
    valsneeded: str = "values_needed"
    verbose: str = "verbose"
    version: str = "version"
    workflow: str = "workflow"
    ww3: str = "ww3"
