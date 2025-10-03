"""Compatibility wrapper for modpack routes during refactor.

We import the existing top-level modpack_routes and re-export its router to keep
behavior unchanged while organizing the routers package. Later we can inline the
implementation here and retire the top-level module.
"""

from .. import modpack_routes as _modpack

router = _modpack.router
