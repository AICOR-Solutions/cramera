"""
Variant selections made on a composed stage before it is read.
"""

from __future__ import annotations

from dataclasses import dataclass

from pxr import Usd

from cramera_usd.exceptions import VariantNotFound

# %% selection


@dataclass(frozen=True)
class VariantSelection:
    """
    A variant to select on the composed stage, in its session layer only.
    """

    prim_path: str
    """
    The prim holding the variant set.
    """

    variant_set: str
    """
    The name of the variant set.
    """

    variant: str
    """
    The variant to select.
    """

    def apply(self, stage: Usd.Stage) -> None:
        """
        Select the variant in the stage's current edit target.

        :param stage: The composed stage.
        :raises VariantNotFound: When the prim, the variant set or the variant does not
            exist.
        """
        prim = stage.GetPrimAtPath(self.prim_path)
        variant_sets = prim.GetVariantSets() if prim else None
        if (
            variant_sets is None
            or not variant_sets.HasVariantSet(self.variant_set)
            or self.variant
            not in variant_sets.GetVariantSet(self.variant_set).GetVariantNames()
        ):
            raise VariantNotFound(self.prim_path, self.variant_set, self.variant)
        variant_sets.GetVariantSet(self.variant_set).SetVariantSelection(self.variant)
