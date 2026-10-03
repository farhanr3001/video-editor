import numpy as np
import subprocess
import wave
from pathlib import Path

OUT_DIR = Path("assets_docker_guide/audio")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SR = 44100

def write_wav(filename, samples):
    # samples: (N, 2) float in [-1, 1]
    samples = np.clip(samples, -0.98, 0.98)
    int16_samples = (samples * 32767).astype(np.int16)
    with wave.open(str(filename), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(int16_samples.tobytes())

def convert_to_mp3(wav_path, mp3_path):
    cmd = ["ffmpeg", "-y", "-i", str(wav_path), "-b:a", "192k", str(mp3_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wav_path.unlink()

def generate_soundtrack():
    print("Synthesizing Cyber Synth soundtrack (68s, 120 BPM)...")
    bpm = 120
    beat_dur = 60.0 / bpm  # 0.5s per beat
    duration = 68.0
    total_samples = int(duration * SR)
    t = np.linspace(0, duration, total_samples, endpoint=False)

    left = np.zeros(total_samples)
    right = np.zeros(total_samples)

    # 1. Bassline (16th note synth arpeggio in D minor: D2, F2, G2, A2, C3)
    # Notes: D2=73.42Hz, F2=87.31Hz, G2=98.00Hz, A2=110.00Hz, C3=130.81Hz
    notes = [73.42, 73.42, 87.31, 73.42, 98.00, 73.42, 110.00, 130.81]
    step_dur = beat_dur / 4.0  # 0.125s
    step_samples = int(step_dur * SR)
    num_steps = int(duration / step_dur)

    for i in range(num_steps):
        freq = notes[i % len(notes)]
        s_start = i * step_samples
        s_end = min(total_samples, s_start + step_samples)
        st = np.linspace(0, (s_end - s_start) / SR, s_end - s_start, endpoint=False)
        # Pluck envelope
        env = np.exp(-st * 18.0)
        # Sawtooth approx: fundamental + harmonics
        wave_sig = np.sin(2 * np.pi * freq * st) * 0.6 + np.sin(2 * np.pi * freq * 2 * st) * 0.3 + np.sin(2 * np.pi * freq * 3 * st) * 0.1
        bass_note = wave_sig * env * 0.35
        left[s_start:s_end] += bass_note
        right[s_start:s_end] += bass_note

    # 2. Kick Drum (on beats 1, 2, 3, 4 with punch)
    kick_samples = int(0.25 * SR)
    kt = np.linspace(0, 0.25, kick_samples, endpoint=False)
    # Pitch drop 150Hz -> 45Hz
    k_freq = 45.0 + 105.0 * np.exp(-kt * 30.0)
    k_phase = 2 * np.pi * np.cumsum(k_freq) / SR
    k_env = np.exp(-kt * 12.0)
    kick = np.sin(k_phase) * k_env * 0.55

    num_beats = int(duration / beat_dur)
    for b in range(num_beats):
        s_start = int(b * beat_dur * SR)
        s_end = min(total_samples, s_start + kick_samples)
        k_slice = kick[:s_end - s_start]
        left[s_start:s_end] += k_slice
        right[s_start:s_end] += k_slice

    # 3. Snare / Clap on beats 2 and 4 (beats 1, 3 in 0-indexed)
    snare_samples = int(0.2 * SR)
    snt = np.linspace(0, 0.2, snare_samples, endpoint=False)
    sn_noise = (np.random.rand(snare_samples) * 2.0 - 1.0) * np.exp(-snt * 16.0) * 0.35
    sn_tone = np.sin(2 * np.pi * 185.0 * snt) * np.exp(-snt * 22.0) * 0.3
    snare = sn_noise + sn_tone
    for b in range(1, num_beats, 2):
        s_start = int(b * beat_dur * SR)
        s_end = min(total_samples, s_start + snare_samples)
        sn_slice = snare[:s_end - s_start]
        left[s_start:s_end] += sn_slice
        right[s_start:s_end] += sn_slice

    # 4. Hi-Hats on 8th notes (alternating left/right stereo pan)
    hh_samples = int(0.06 * SR)
    hht = np.linspace(0, 0.06, hh_samples, endpoint=False)
    hh = (np.random.rand(hh_samples) * 2.0 - 1.0) * np.exp(-hht * 55.0) * 0.16
    eighth_dur = beat_dur / 2.0
    num_eighths = int(duration / eighth_dur)
    for e in range(num_eighths):
        s_start = int(e * eighth_dur * SR)
        s_end = min(total_samples, s_start + hh_samples)
        hh_slice = hh[:s_end - s_start]
        pan = 0.3 if e % 2 == 0 else 0.7
        left[s_start:s_end] += hh_slice * (1.0 - pan)
        right[s_start:s_end] += hh_slice * pan

    # 5. Cyber Synth Pad Chords (Dm -> Bb -> C -> Am)
    chords = [
        [146.83, 174.61, 220.00, 261.63], # Dm7 (D3, F3, A3, C4)
        [116.54, 146.83, 174.61, 233.08], # Bbmaj7 (Bb2, D3, F3, Bb3)
        [130.81, 164.81, 196.00, 261.63], # C (C3, E3, G3, C4)
        [110.00, 130.81, 164.81, 220.00], # Am7 (A2, C3, E3, A3)
    ]
    chord_dur = beat_dur * 8 # 4.0s per chord
    num_chords = int(duration / chord_dur) + 1
    for c_idx in range(num_chords):
        chord_freqs = chords[c_idx % len(chords)]
        c_start = int(c_idx * chord_dur * SR)
        c_end = min(total_samples, int((c_idx + 1) * chord_dur * SR))
        ct = np.linspace(0, (c_end - c_start) / SR, c_end - c_start, endpoint=False)
        # Gentle swell envelope
        c_env = np.sin(np.pi * ct / ((c_end - c_start) / SR)) ** 1.5 * 0.14
        c_sig_l = np.zeros_like(ct)
        c_sig_r = np.zeros_like(ct)
        for cf in chord_freqs:
            # Detuned stereo unison
            c_sig_l += np.sin(2 * np.pi * cf * ct) * 0.5 + np.sin(2 * np.pi * (cf * 1.004) * ct) * 0.5
            c_sig_r += np.sin(2 * np.pi * (cf * 0.996) * ct) * 0.5 + np.sin(2 * np.pi * cf * ct) * 0.5
        left[c_start:c_end] += c_sig_l * c_env
        right[c_start:c_end] += c_sig_r * c_env

    # Master volume and smooth fade out over last 2 seconds
    fade_len = int(2.5 * SR)
    fade_env = np.ones(total_samples)
    fade_env[-fade_len:] = np.linspace(1.0, 0.0, fade_len)

    left *= fade_env * 0.55
    right *= fade_env * 0.55

    stereo = np.column_stack((left, right))
    wav_out = OUT_DIR / "cyber_synth_soundtrack.wav"
    mp3_out = OUT_DIR / "cyber_synth_soundtrack.mp3"
    write_wav(wav_out, stereo)
    convert_to_mp3(wav_out, mp3_out)
    print("Generated cyber_synth_soundtrack.mp3")

def generate_sfx():
    print("Synthesizing SFX (whoosh, digital blip, impact hit)...")

    # 1. Transition Whoosh (0.6s)
    dur = 0.6
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    # Filtered noise with pitch swell
    noise = np.random.rand(n) * 2.0 - 1.0
    env = np.sin(np.pi * t / dur) ** 2.0
    sweep_freq = 200.0 + 1200.0 * np.sin(np.pi * t / dur)
    tone = np.sin(2 * np.pi * np.cumsum(sweep_freq) / SR)
    whoosh = (noise * 0.6 + tone * 0.4) * env * 0.5
    whoosh_stereo = np.column_stack((whoosh * 0.9, whoosh * 1.1))
    w_wav = OUT_DIR / "transition_whoosh.wav"
    w_mp3 = OUT_DIR / "transition_whoosh.mp3"
    write_wav(w_wav, whoosh_stereo)
    convert_to_mp3(w_wav, w_mp3)
    print("Generated transition_whoosh.mp3")

    # 2. Digital Blip (0.22s)
    dur = 0.22
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    blip_freq = 980.0 + 800.0 * np.exp(-t * 25.0)
    blip_phase = 2 * np.pi * np.cumsum(blip_freq) / SR
    blip_env = np.exp(-t * 18.0)
    blip = np.sin(blip_phase) * blip_env * 0.4
    blip_stereo = np.column_stack((blip, blip))
    b_wav = OUT_DIR / "digital_blip.wav"
    b_mp3 = OUT_DIR / "digital_blip.mp3"
    write_wav(b_wav, blip_stereo)
    convert_to_mp3(b_wav, b_mp3)
    print("Generated digital_blip.mp3")

    # 3. Impact Hit / Bass Stinger (1.2s)
    dur = 1.2
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    sub_freq = 90.0 * np.exp(-t * 8.0) + 40.0
    sub_phase = 2 * np.pi * np.cumsum(sub_freq) / SR
    sub_env = np.exp(-t * 4.0)
    sub = np.sin(sub_phase) * sub_env * 0.6
    transient = (np.random.rand(n) * 2.0 - 1.0) * np.exp(-t * 30.0) * 0.3
    hit = sub + transient
    hit_stereo = np.column_stack((hit, hit))
    h_wav = OUT_DIR / "impact_hit.wav"
    h_mp3 = OUT_DIR / "impact_hit.mp3"
    write_wav(h_wav, hit_stereo)
    convert_to_mp3(h_wav, h_mp3)
    print("Generated impact_hit.mp3")

if __name__ == "__main__":
    generate_soundtrack()
    generate_sfx()
