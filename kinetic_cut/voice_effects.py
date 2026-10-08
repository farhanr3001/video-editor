"""Local voice treatments shared by cached preview audio and export."""
import math

NAMES = ('Chipmunk Voice', 'Deep Voice', 'Radio Voice', 'Walkie Talkie', 'Robot Voice', 'Megaphone')
PROCESSED_NAMES = frozenset(('Noise Clean', 'Voice Clarity', 'Low Cut', *NAMES))
# key, label, minimum, maximum, default, step
CONTROLS = {
    'Chipmunk Voice': (('semitones', 'Pitch (semitones)', 0, 18, 7, .1),),
    'Deep Voice': (('semitones', 'Pitch (semitones)', -18, 0, -7, .1),),
    'Radio Voice': (('low_cut', 'Low cut (Hz)', 100, 1500, 300, 10),
                    ('high_cut', 'High cut (Hz)', 1800, 8000, 3400, 50)),
    'Walkie Talkie': (('low_cut', 'Low cut (Hz)', 100, 1500, 450, 10),
                      ('high_cut', 'High cut (Hz)', 1800, 8000, 2800, 50),
                      ('drive', 'Distortion', 1, 8, 2.5, .1)),
    'Robot Voice': (('frequency', 'Robot frequency (Hz)', 20, 180, 55, 1),),
    'Megaphone': (('low_cut', 'Low cut (Hz)', 100, 1500, 500, 10),
                  ('high_cut', 'High cut (Hz)', 1800, 8000, 4200, 50),
                  ('drive', 'Distortion', 1, 8, 3, .1)),
}
DESCRIPTIONS = {
    'Chipmunk Voice': 'A bright squirrel/chipmunk voice. Raises pitch and vocal tone without speeding up the clip.',
    'Deep Voice': 'A low, larger-than-life voice. Lowers pitch and vocal tone without slowing down the clip.',
    'Radio Voice': 'Narrow-band radio speech with compression. Adjust the low and high frequency cutoffs.',
    'Walkie Talkie': 'Compressed, gritty two-way radio speech. Adjustable frequency range and distortion.',
    'Robot Voice': 'A metallic robot voice made with ring modulation. Frequency changes the robotic tone.',
    'Megaphone': 'A midrange-heavy loudspeaker voice with adjustable distortion and frequency range.',
}


def number(value, low, high, default):
    try: value = float(value)
    except (TypeError, ValueError): return default
    return min(high, max(low, value)) if math.isfinite(value) else default


def values(effect):
    return {key: number(effect.get(key, default), low, high, default)
            for key, _, low, high, default, _ in CONTROLS.get(effect.get('name'), ())}


def default_effect(name):
    return dict(name=name, enabled=True, amount=100., **values({'name': name}))


def filter_chain(effect):
    name = effect.get('name')
    if name not in NAMES or not effect.get('enabled', True): return ''
    strength = number(effect.get('amount', 100), 0, 100, 100) / 100
    if not strength: return ''
    settings = values(effect)
    if name in ('Chipmunk Voice', 'Deep Voice'):
        factor = 2 ** (settings['semitones'] * strength / 12)
        if abs(factor - 1) < .00001: return ''
        # Resampling shifts formants too, giving the familiar cartoon/deep tone;
        # tempo compensation keeps dialogue aligned with the original video.
        tempo = 1 / factor
        # Explicit float samples prevent atempo choosing integer arithmetic for
        # PCM preview and float arithmetic for the exported AAC mix.
        filters = [f'asetrate={48000 * factor:.6f}', 'aresample=48000:osf=flt']
        while tempo < .5: filters.append('atempo=0.5'); tempo /= .5
        while tempo > 2: filters.append('atempo=2'); tempo /= 2
        filters.append(f'atempo={tempo:.8f}')
        return ','.join(filters)
    if name == 'Robot Voice':
        # Keep both channels separate; t is seconds, so tone stays source-rate
        # independent. Strength zero is an exact bypass, not amplitude loss.
        return f"aeval=exprs='val(ch)*({1-strength:.6f}+{strength:.6f}*cos(2*PI*{settings['frequency']:.6f}*t))':c=same"
    low = 20 + (settings['low_cut'] - 20) * strength
    high = 22000 + (settings['high_cut'] - 22000) * strength
    filters = [f'highpass=f={low:.4f}', f'lowpass=f={high:.4f}']
    if name == 'Radio Voice':
        filters.append(f'acompressor=threshold=0.15:ratio={1+3*strength:.4f}:attack=5:release=80:makeup={1+.4*strength:.4f}')
    else:
        drive = 1 + (settings['drive'] - 1) * strength
        filters.extend([f'volume={drive:.6f}', 'asoftclip=type=tanh:threshold=0.5:output=0.8'])
        if name == 'Walkie Talkie': filters.append(f'acrusher=bits=7:mix={.35*strength:.6f}:mode=lin:aa=1')
    return ','.join(filters)
