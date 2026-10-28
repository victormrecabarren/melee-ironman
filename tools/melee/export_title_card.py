"""Export unchanged US title-screen textures for the pre-match card.

GmTtAll.usd / TtlMoji_Top_joint, loaded by gmTitle_801A1AC0.
Only layout is adapted for the website; lettering is decoded from the disc.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from scene_assets import expose_roots, roots


def run(args):
    sys.path.insert(0, str(args.importer.resolve()))
    from importer.phases.parse.parse import parse_sections
    from importer.phases.describe.describe import describe_scene
    from PIL import Image

    data = (args.data / 'GmTtAll.usd').read_bytes()
    name = 'TtlMoji_Top_joint'
    options = {'game': 'SMASH_BROS', 'filepath': 'GmTtAll.usd', 'max_frame': 1600, 'section_names': []}
    sections = parse_sections(expose_roots(data, [(name, roots(data)[name] - 32, 'Joint')]), {name: 'Joint'}, options)
    scene = describe_scene(sections, options)
    images = {layer.image.image_id: layer.image for model in scene.models
              for mesh in model.meshes for layer in mesh.material.texture_layers}
    specs = [('title-logo', 6348, (448, 128)), ('title-melee', 11364, (176, 40)),
             ('title-symbol', 9960, (48, 44))]
    report = {'archive': 'GmTtAll.usd', 'sha256': hashlib.sha256(data).hexdigest(), 'root': name, 'textures': {}}
    args.output.mkdir(parents=True, exist_ok=True)
    for label, image_id, dimensions in specs:
        image = images[image_id]
        if (image.width, image.height) != dimensions:
            raise ValueError(f'Unexpected title texture size: {label}')
        pixels = Image.frombytes('RGBA', dimensions, image.pixels).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        pixels.save(args.output / (label + '.webp'), lossless=True)
        report['textures'][label] = {'imageId': image_id, 'dimensions': dimensions}
    (args.output / 'title-card-source.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['data', 'output', 'importer']:
        parser.add_argument('--' + key, type=Path, required=True)
    run(parser.parse_args())
