# SPDX-License-Identifier: BSD-3-Clause

"""Fixture definitions for pytest."""

from pytest import fixture

from softfab.databases import reloadDatabases


class Databases:

    def __init__(self, dbDir):
        self.dbDir = dbDir
        self.reload()

    def reload(self):
        dbs = reloadDatabases(self.dbDir)
        for name, db in dbs.items():
            setattr(self, name, db)

@fixture
def databases(tmp_path):
    return Databases(tmp_path)
