"""Curated GEOS responsibilities; these are hints, not inferred build dependencies."""

from geos_agents.models import RepositorySpec


def _repo(
    name: str,
    description: str,
    domains: tuple[str, ...],
    related: tuple[str, ...] = (),
    aliases: tuple[str, ...] = (),
    languages: tuple[str, ...] = ("Fortran", "CMake"),
) -> RepositorySpec:
    url = f"https://github.com/GEOS-ESM/{name}"
    return RepositorySpec(
        name=name,
        remote=url + ".git",
        description=description,
        domains=domains,
        related=related,
        aliases=aliases,
        languages=languages,
        source_url=url,
    )


CATALOG: tuple[RepositorySpec, ...] = (
    _repo(
        "GEOSgcm",
        "GEOS GCM fixture, mepo assembly and top-level build",
        ("fixture", "build", "initialization", "cmake", "mepo"),
        ("GEOSgcm_GridComp", "MAPL", "ESMA_cmake", "GEOSgcm_App"),
    ),
    _repo(
        "GEOSgcm_GridComp",
        "GEOS atmosphere/physics component hierarchy",
        ("physics", "atmosphere", "tendencies", "surface", "iau"),
        ("FVdycoreCubed_GridComp", "MAPL", "GEOSchem_GridComp", "GEOSradiation_GridComp"),
    ),
    _repo(
        "FVdycoreCubed_GridComp",
        "MAPL/ESMF wrapper for the cubed-sphere dynamical core",
        ("dynamics", "fv3", "wrapper", "halo", "mpi"),
        ("GFDL_atmos_cubed_sphere", "MAPL"),
    ),
    _repo(
        "GFDL_atmos_cubed_sphere",
        "GEOS fork of the GFDL finite-volume dynamical core",
        ("dynamics", "fv3", "epv", "d-grid", "advection", "cuda", "gpu", "winds"),
        ("FVdycoreCubed_GridComp",),
        ("fvdycore", "GEOSfvdycore"),
    ),
    _repo(
        "MAPL",
        "ESMF component support, fields, I/O, profiling and testing",
        ("mapl", "esmf", "io", "i/o", "history", "extdata", "profiling", "fields", "restart"),
        ("ESMA_cmake",),
    ),
    _repo(
        "ESMA_cmake",
        "Shared CMake macros and build conventions",
        ("cmake", "build", "compiler", "link", "ctest"),
        (),
        ("cmake",),
        ("CMake",),
    ),
    _repo(
        "ESMA_env",
        "GEOS site and compiler environment setup",
        ("environment", "modules", "compiler", "build"),
        (),
        ("env",),
        ("Shell",),
    ),
    _repo(
        "GMAO_Shared",
        "Shared GEOS infrastructure and utilities",
        ("shared", "utilities", "initialization"),
        ("GEOS_Util",),
    ),
    _repo(
        "GEOS_Util",
        "GEOS processing and experiment utilities",
        ("utilities", "postprocessing", "analysis"),
    ),
    _repo(
        "GEOSgcm_App",
        "GEOS GCM application and experiment setup",
        ("application", "experiment", "setup", "run", "initialization"),
        ("GEOSgcm", "MAPL"),
    ),
    _repo(
        "GEOSchem_GridComp",
        "Atmospheric chemistry component integration",
        ("chemistry", "aerosol", "tracer"),
        ("GEOSgcm_GridComp", "MAPL"),
    ),
    _repo(
        "GEOSradiation_GridComp",
        "GEOS atmospheric radiation components",
        ("radiation", "radiative", "rrtmgp"),
        ("GEOSgcm_GridComp", "MAPL"),
    ),
    _repo(
        "GEOS_OceanGridComp",
        "GEOS ocean component integration",
        ("ocean", "mom", "coupling"),
        ("GEOSgcm_GridComp", "MAPL"),
    ),
)


def resolve(name: str) -> RepositorySpec:
    """Resolve a canonical repository name or documented alias, case-insensitively."""
    for spec in CATALOG:
        if name.casefold() in {s.casefold() for s in (spec.name, *spec.aliases)}:
            return spec
    raise ValueError(f"Unknown GEOS repository: {name}")
