#!/usr/bin/env python3
"""Optional standalone derivative rebuild. Requires Pillow; does not install packages.
Existing originals are never modified. Rebuilding may vary bytes by Pillow/libwebp version;
regenerate the package manifest only after reviewing intentional changes.
"""
from pathlib import Path
import hashlib,json,sys
try:
    from PIL import Image
except ImportError:
    raise SystemExit('Pillow is required for this optional rebuild. Prebuilt WebP files already exist.')
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'data/assets.json').read_text())
for a in manifest['assets']:
    source=(root/a['source']).resolve();out=(root/a['file']).resolve()
    if not source.is_relative_to(root) or not out.is_relative_to(root):raise SystemExit('Unsafe path')
    with Image.open(source) as image:
        if a['width']>image.width:raise SystemExit('Upscaling is not allowed')
        result=image.resize((a['width'],a['height']),Image.Resampling.LANCZOS)
        tmp=out.with_name(out.name+'.tmp')
        result.save(tmp,format='WEBP',quality=93 if a['kind']=='character' else 91,method=6,exact=True)
        tmp.replace(out)
    a['bytes']=out.stat().st_size;a['sha256']=hashlib.sha256(out.read_bytes()).hexdigest()
(root/'data/assets.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Derivatives rebuilt. Review them and intentionally regenerate the bundle manifest before verifying a modified handoff.')
