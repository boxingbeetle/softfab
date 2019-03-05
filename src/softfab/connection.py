# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum

class ConnectionStatus(Enum):
    UNKNOWN = 1
    CONNECTED = 2
    WARNING = 3
    LOST = 4
