"""Invented deterministic formats used for local SALVAGE golden tests."""
from .aster import AsterRecordsPlugin
from .crc_blocks import CRCBlocksPlugin
from .xidx import XIDXPlugin
from .lotus_wks import LotusWKSPlugin

__all__ = ["AsterRecordsPlugin", "CRCBlocksPlugin", "XIDXPlugin", "LotusWKSPlugin"]
