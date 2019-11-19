# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
import logging

from softfab.version import VERSION


def initLogging(dbDir: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='* %(asctime)s %(levelname)-8s> %(message)s',
        filename=dbDir / 'cc-log.txt'
        )

    logging.info('> > Control Center startup, version %s', VERSION)
