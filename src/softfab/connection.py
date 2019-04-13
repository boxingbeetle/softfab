# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum


class ConnectionStatus(Enum):
    """Our perception of the status of a network connection."""

    UNKNOWN = 1
    """Insufficient data on current status, was connected before."""

    CONNECTED = 2
    """Recent message confirmed connection."""

    WARNING = 3
    """Assumed connected, but no recent messages."""

    LOST = 4
    """Currently not connected, was connected before."""

    NEW = 5
    """Was never connected."""
