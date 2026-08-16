from PIL import Image
import os

assets_dir = "frontend/assets"
cities = ["delhi", "bangalore", "mumbai", "kolkata", "jaipur"]

max_dim = 2800

for c in cities:
    path = os.path.join(assets_dir, f"{c}_tiles.png")
    if not os.path.exists(path):
        print(f"Skipping {path}, not found.")
        continue

    img = Image.open(path)
    w, h = img.size
    print(f"Processing {c}: original size {w}x{h}, file size {os.path.getsize(path)/1e6:.2f} MB")

    if w > max_dim or h > max_dim:
        scale = min(max_dim / w, max_dim / h)
        new_w, new_h = int(w * scale), int(h * scale)
        print(f"  Downscaling {c} to {new_w}x{new_h}...")
        resample_filter = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
        img_resized = img.resize((new_w, new_h), resample_filter)
        img_resized.save(path, optimize=True)
        print(f"  Saved {c}: new file size {os.path.getsize(path)/1e6:.2f} MB")
    else:
        print(f"  {c} is already within {max_dim}px limits.")

print("All tile images optimized successfully.")
