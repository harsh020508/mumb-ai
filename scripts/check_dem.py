import os
import tifffile
import numpy as np

dems = r"C:\Users\Lucky\AppData\Local\Temp\opencode\dem"
for f in sorted(os.listdir(dems)):
    p = os.path.join(dems, f)
    if not f.endswith('.tif'):
        continue
    try:
        t = tifffile.TiffFile(p)
        arr = t.pages[0].asarray()
        tags = t.pages[0].tags
        print(f"{f}: shape={arr.shape} dtype={arr.dtype} "
              f"min={np.nanmin(arr):.1f} max={np.nanmax(arr):.1f} mean={np.nanmean(arr):.1f}")
        t.close()
    except Exception as e:
        print(f"{f}: ERROR {e}")
