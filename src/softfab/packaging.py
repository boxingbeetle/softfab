# SPDX-License-Identifier: BSD-3-Clause

from typing import Dict, Iterable, Optional

from packaging.requirements import Requirement

from softfab.compat import importlib_metadata

Distribution = importlib_metadata.Distribution

_distributionCache: Dict[str, Optional[Distribution]] = {}

def getDistribution(name: str) -> Optional[Distribution]:
    """Looks up the distribution info for the given package name.
    The lookup result is cached.
    If no distribution info was found, None is returned.
    """
    try:
        return _distributionCache[name]
    except KeyError:
        dist: Optional[Distribution]
        try:
            dist = Distribution.from_name(name)
        except importlib_metadata.PackageNotFoundError:
            dist = None
        _distributionCache[name] = dist
        return dist

def dependencies(name: str) -> Iterable[str]:
    """Return the names of all packages that the given package depends on,
    directly or indirectly.
    If metadata for any package is not available, its dependencies will
    not be in the output, but the name of the missing package will be.
    Requirements that depend on for example Python version or OS will be
    evaluated for the current process.
    """

    done = set()
    todo = {(name, None)}
    while todo:
        currPair = todo.pop()
        done.add(currPair)
        currName, currExtra = currPair

        dist = getDistribution(currName)
        if dist is None:
            continue

        env = dict(extra=currExtra)
        if dist.requires is not None:
            for reqStr in dist.requires:
                req = Requirement(reqStr)
                marker = req.marker
                if marker is None or marker.evaluate(environment=env):
                    newName = req.name
                    for newExtra in {None} | req.extras:
                        newPair = (newName, newExtra)
                        if newPair not in done:
                            todo.add(newPair)

    return {n for n, e in done if n != name}
