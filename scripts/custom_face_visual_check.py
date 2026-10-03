"""Render representative Custom Face settings against a tracked local sample."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QImage
from kinetic_cut.custom_face import apply_custom_face, draw_guides
from kinetic_cut.vision_effects import mesh_data


def main():
    source, analysis, output = map(Path, sys.argv[1:4])
    output.mkdir(parents=True, exist_ok=True)
    mesh = mesh_data(analysis)[15]
    cases = {
        'eyes': {'morph': {'left_eye': 70, 'right_eye': 70}},
        'eye-spacing-wide': {'morph': {'eye_spacing': 100}},
        'eye-spacing-narrow': {'morph': {'eye_spacing': -100}},
        'nose': {'morph': {'nose_size': 140}},
        'mouth': {'morph': {'mouth_width': 90, 'mouth_height': 65}},
        'face': {'morph': {'face_width': -75, 'jaw_width': 50}},
        'skin': {'skin_color': '#df875f', 'skin_strength': 70},
    }
    for name, effect in cases.items():
        image = QImage(str(source)).convertToFormat(QImage.Format_RGBA8888)
        apply_custom_face(image, mesh, effect)
        if name == 'face':
            draw_guides(image,mesh)
        if not image.save(str(output/(name+'.png'))):
            raise RuntimeError('Could not write '+name)


if __name__=='__main__':
    main()
