"""Dispensing artifacts as containers — build once when gated, vend many.

An artifact reference is a path on whichever machine ran that engine. An image
tag is not. This is how a composed run's output stops being local.
"""

from .docker import DispensedCopy, VendingError, available, stop
from .machine import StockItem, admitted, image_tag, package, packageable, vend

__all__ = ["DispensedCopy", "StockItem", "VendingError", "admitted",
           "available", "image_tag", "package", "packageable", "stop", "vend"]
