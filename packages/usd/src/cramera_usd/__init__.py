"""
Conversion of a composed USD stage, such as an Isaac Sim twin, into a cramera scene
bundle: one GLB per link with physically based materials, URDF models built from the
UsdPhysics joints, and the bundle's protocol documents.

Only the modules of :mod:`cramera_usd.stage` and :mod:`cramera_usd.audit` import
``pxr``; everything else works on the neutral description in :mod:`cramera_usd.scene`.
"""
