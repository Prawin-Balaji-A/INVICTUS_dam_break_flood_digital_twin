import rasterio
import numpy as np
from scipy.ndimage import distance_transform_edt

path = r"E:\dam\mettur_data\terrain\terrain.tif"

print("=" * 60)
print("FIXING METTUR DEM")
print("=" * 60)

with rasterio.open(path) as src:
    data = src.read(1).astype(np.float32)
    profile = src.profile

nodata = -32768.0

# Invalid pixels
invalid = (data == nodata) | (data <= 0)

print("Invalid pixels before:", int(np.sum(invalid)))

# Valid elevation pixels
valid = ~invalid

if not np.any(valid):
    raise RuntimeError("No valid elevation pixels found.")

# Find nearest valid pixel for every invalid pixel
indices = distance_transform_edt(
    invalid,
    return_distances=False,
    return_indices=True
)

fixed = data.copy()

fixed[invalid] = data[
    indices[0][invalid],
    indices[1][invalid]
]

# Write corrected terrain
profile.update(
    dtype="float32",
    nodata=nodata
)

with rasterio.open(path, "w", **profile) as dst:
    dst.write(fixed, 1)

print("Invalid pixels after:", int(np.sum((fixed == nodata) | (fixed <= 0))))
print("Minimum elevation:", float(np.min(fixed)))
print("Maximum elevation:", float(np.max(fixed)))

print("=" * 60)
print("METTUR DEM FIX COMPLETE")
print("=" * 60)