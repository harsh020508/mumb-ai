import tifffile
import numpy as np
import os

for city in ['mumbai', 'delhi', 'kolkata', 'bangalore', 'jaipur']:
    p = f'data/{city}_dem.tif'
    t = tifffile.TiffFile(p)
    page = t.pages[0]
    arr = page.asarray()
    scale = page.tags.get(33550)
    tie = page.tags.get(33922)
    print(f'{city}: shape={arr.shape} dtype={arr.dtype}')
    if scale is not None:
        s = scale.value
        print(f'   ModelPixelScale={s}')
        px = s[0]
        tp = tie.value
        x0 = tp[3] - tp[0]*px
        y0 = tp[4] + tp[1]*px
        print(f'   Tiepoint={tp[:6]} -> origin=(lon {x0:.6f}, lat {y0:.6f})')
        print(f'   extent: lon {x0:.4f}..{x0+arr.shape[1]*px:.4f}, lat {y0-arr.shape[0]*px:.4f}..{y0:.4f}')
    else:
        print('   MISSING ModelPixelScaleTag!')
    print(f'   min={np.nanmin(arr):.1f} max={np.nanmax(arr):.1f}')
    t.close()
