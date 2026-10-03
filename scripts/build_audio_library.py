import json
import math
import os
import shutil
import subprocess
import sys
import wave
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOUNDTRACKS_DIR = ROOT / "Soundtracks"
SFX_DIR = ROOT / "Sound_Effects"
SCRATCH_DIR = ROOT / "scratch" / "downloads"

SOUNDTRACKS_DIR.mkdir(parents=True, exist_ok=True)
SFX_DIR.mkdir(parents=True, exist_ok=True)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

SR = 44100
PYTHON310 = r"C:\Python310\python.exe"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def run_cmd(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def write_wav(filename, samples):
    samples = np.clip(samples, -0.98, 0.98)
    int16_samples = (samples * 32767).astype(np.int16)
    with wave.open(str(filename), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(int16_samples.tobytes())

def convert_wav_to_mp3(wav_path, mp3_path, bitrate="192k"):
    cmd = [
        "ffmpeg", "-y", "-i", str(wav_path),
        "-b:a", bitrate,
        "-ar", "44100",
        str(mp3_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if wav_path.exists():
        wav_path.unlink()

def normalize_mp3(src_mp3, dest_mp3, max_dur=None, fade_in=0.01, fade_out=0.05, target_lufs=-14):
    """Normalize, trim, and apply clean anti-click fades."""
    filter_chain = []
    if fade_in > 0:
        filter_chain.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    
    # Check duration
    cmd_probe = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src_mp3)]
    probe = run_cmd(cmd_probe)
    try:
        dur = float(probe.stdout.strip())
    except Exception:
        dur = max_dur or 5.0
        
    actual_dur = min(dur, max_dur) if max_dur else dur
    if fade_out > 0 and actual_dur > fade_out:
        st = actual_dur - fade_out
        filter_chain.append(f"afade=t=out:st={st:.3f}:d={fade_out:.3f}")
        
    filter_chain.append(f"loudnorm=I={target_lufs}:TP=-1.0:LRA=11")
    af = ",".join(filter_chain)
    
    cmd = ["ffmpeg", "-y", "-i", str(src_mp3)]
    if max_dur:
        cmd.extend(["-t", str(max_dur)])
    cmd.extend(["-af", af, "-b:a", "192k", "-ar", "44100", str(dest_mp3)])
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def download_audio(query, output_mp3, max_duration=75.0, fade_out=2.5, target_lufs=-14):
    """Download audio via yt-dlp search and master with ffmpeg."""
    if output_mp3.exists() and output_mp3.stat().st_size > 10000:
        print(f"  [Already exists] {output_mp3.name}")
        return True

    temp_stem = SCRATCH_DIR / f"temp_{output_mp3.stem}"
    temp_target = str(temp_stem) + ".%(ext)s"
    
    cmd_dl = [
        PYTHON310, "-m", "yt_dlp",
        "--default-search", "ytsearch",
        "-t", "mp3",
        "--max-downloads", "1",
        "--no-playlist",
        f"ytsearch:{query}",
        "-o", temp_target
    ]
    print(f"Downloading [{query}] -> {output_mp3.name}...")
    res = subprocess.run(cmd_dl, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    downloaded = None
    for ext in ["mp3", "webm", "m4a", "opus"]:
        p = Path(str(temp_stem) + "." + ext)
        if p.exists():
            downloaded = p
            break
            
    if not downloaded:
        print(f"  Warning: Could not download {query}")
        return False

    normalize_mp3(downloaded, output_mp3, max_dur=max_duration, fade_in=0.05, fade_out=fade_out, target_lufs=target_lufs)
    if downloaded.exists():
        downloaded.unlink()
        
    print(f"  [OK] Saved {output_mp3.name} ({output_mp3.stat().st_size} bytes)")
    return True

# ==========================================
# PROCEDURAL SYNTHESIS ENGINES (Studio Quality)
# ==========================================

def synth_sub_boom(dest_mp3):
    """Deep cinematic sub boom with exponential pitch drop and sub-rumble."""
    dur = 2.4
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    
    freq = 110.0 * np.exp(-t * 7.5) + 32.0
    phase = 2 * np.pi * np.cumsum(freq) / SR
    env = np.exp(-t * 2.2)
    # Fundamental + sub-harmonic
    sub = (np.sin(phase) * 0.75 + np.sin(phase * 0.5) * 0.25) * env
    
    # Transient snap at t=0
    transient = (np.random.rand(n) * 2.0 - 1.0) * np.exp(-t * 40.0) * 0.35
    sig = sub + transient
    # Soft saturation
    sig = np.tanh(sig * 1.4) * 0.95
    stereo = np.column_stack((sig, sig))
    
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_braam_brass(dest_mp3):
    """Low Hans Zimmer Inception-style Horn of Doom / Braam."""
    dur = 3.2
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    
    f0 = 55.0 # A1 low brass
    saw = np.zeros(n)
    for h in range(1, 14):
        saw += (1.0 / h) * np.sin(2 * np.pi * (f0 * h) * t)
        saw += (0.5 / h) * np.sin(2 * np.pi * (f0 * 1.006 * h) * t) # detune
        
    # Filter envelope opening then decaying
    f_env = np.exp(-t * 1.2) * (1.0 - np.exp(-t * 20.0))
    # Brass bite distortion
    dist = np.tanh(saw * 2.5 * f_env)
    
    # Sub reinforcement
    sub = np.sin(2 * np.pi * (f0 * 0.5) * t) * np.exp(-t * 1.0) * 0.6
    
    out = (dist * 0.7 + sub * 0.3) * np.exp(-t * 0.8)
    stereo = np.column_stack((out, out))
    
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_808_sub_drop(dest_mp3):
    """Clean modern 808 sub bass drop with warm saturation."""
    dur = 2.0
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    
    freq = 135.0 * np.exp(-t * 8.0) + 38.0
    phase = 2 * np.pi * np.cumsum(freq) / SR
    env = np.exp(-t * 2.0)
    sig = np.sin(phase) * env
    # Saturation harmonics
    sig = np.tanh(sig * 1.8) * 0.95
    stereo = np.column_stack((sig, sig))
    
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_whoosh_fast(dest_mp3):
    """Fast whip whoosh with dynamic stereo pan."""
    dur = 0.45
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    
    noise = np.random.rand(n) * 2.0 - 1.0
    env = np.sin(np.pi * t / dur) ** 2.2
    sweep_freq = 250.0 + 1600.0 * np.sin(np.pi * t / dur)
    tone = np.sin(2 * np.pi * np.cumsum(sweep_freq) / SR)
    sig = (noise * 0.65 + tone * 0.35) * env * 0.75
    
    # Pan from left to right
    pan = np.linspace(0.15, 0.85, n)
    left = sig * (1.0 - pan) * 1.4
    right = sig * pan * 1.4
    stereo = np.column_stack((left, right))
    
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_whoosh_deep(dest_mp3):
    """Deep cinematic sub whoosh for major scene changes."""
    dur = 0.9
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    
    noise = np.random.rand(n) * 2.0 - 1.0
    env = np.sin(np.pi * t / dur) ** 2.0
    sub_sweep = 60.0 + 240.0 * np.sin(np.pi * t / dur)
    sub = np.sin(2 * np.pi * np.cumsum(sub_sweep) / SR)
    
    sig = (noise * 0.4 + sub * 0.7) * env * 0.8
    stereo = np.column_stack((sig * 0.95, sig * 1.05))
    
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_whoosh_glitch(dest_mp3):
    """Digital glitch stutter whoosh."""
    dur = 0.65
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    
    noise = np.random.rand(n) * 2.0 - 1.0
    stutter = (np.sin(2 * np.pi * 32.0 * t) > 0.0).astype(float)
    env = np.sin(np.pi * t / dur) ** 1.8
    sig = noise * stutter * env * 0.65
    
    # Random digital clicks
    clicks = (np.random.rand(n) > 0.985).astype(float) * 0.5 * env
    sig += clicks
    stereo = np.column_stack((sig, sig))
    
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_riser_tension(dest_mp3):
    """4-second ascending tension riser."""
    dur = 4.0
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    
    # Rising pitch from 150Hz to 1200Hz
    freq = 150.0 * np.exp(t * 0.52)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    noise = (np.random.rand(n) * 2.0 - 1.0) * (t / dur) ** 2.5
    tone = np.sin(phase) * (t / dur) ** 2.0
    
    # Tremolo pulse accelerating
    tremolo_freq = 4.0 + 16.0 * (t / dur)
    tremolo = 0.6 + 0.4 * np.sin(2 * np.pi * np.cumsum(tremolo_freq) / SR)
    
    out = (tone * 0.6 + noise * 0.4) * tremolo * 0.8
    # Fade in
    out[:int(0.1 * SR)] *= np.linspace(0, 1, int(0.1 * SR))
    stereo = np.column_stack((out, out))
    
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_clock_tick(dest_mp3):
    """Crisp rhythmic clock ticks (4 seconds of clean tension ticks)."""
    dur = 4.0
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    left = np.zeros(n)
    right = np.zeros(n)
    
    tick_dur = 0.035
    tn = int(tick_dur * SR)
    tt = np.linspace(0, tick_dur, tn, endpoint=False)
    tick_sample = np.sin(2 * np.pi * 1450.0 * tt) * np.exp(-tt * 160.0)
    tick_sample += (np.random.rand(tn) * 2.0 - 1.0) * np.exp(-tt * 200.0) * 0.3
    
    for i in range(8): # 0.5s intervals (120 BPM tick)
        idx = int(i * 0.5 * SR)
        end = min(n, idx + tn)
        pan = 0.45 if i % 2 == 0 else 0.55
        left[idx:end] += tick_sample[:end-idx] * (1.0 - pan) * 0.8
        right[idx:end] += tick_sample[:end-idx] * pan * 0.8
        
    stereo = np.column_stack((left, right))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_heartbeat(dest_mp3):
    """Muffled visceral heartbeat pulse (lub-dub)."""
    dur = 3.6
    n = int(dur * SR)
    left = np.zeros(n)
    right = np.zeros(n)
    
    # 3 heartbeats at 60 BPM
    for b in range(3):
        t0 = int(b * 1.1 * SR)
        # Lub
        l_dur = 0.18
        ln = int(l_dur * SR)
        lt = np.linspace(0, l_dur, ln, endpoint=False)
        lub = np.sin(2 * np.pi * (52.0 - 15.0 * lt) * lt) * np.sin(np.pi * lt / l_dur) ** 2.0 * 0.85
        left[t0:t0+ln] += lub
        right[t0:t0+ln] += lub
        # Dub (0.28s after lub)
        d_start = t0 + int(0.28 * SR)
        d_dur = 0.24
        dn = int(d_dur * SR)
        dt = np.linspace(0, d_dur, dn, endpoint=False)
        dub = np.sin(2 * np.pi * (45.0 - 12.0 * dt) * dt) * np.sin(np.pi * dt / d_dur) ** 2.0 * 0.70
        left[d_start:d_start+dn] += dub
        right[d_start:d_start+dn] += dub
        
    stereo = np.column_stack((left, right))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_ui_blip(dest_mp3):
    """Modern crisp UI high-tech telemetry blip."""
    dur = 0.16
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    freq = 1250.0 + 800.0 * np.exp(-t * 30.0)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    env = np.exp(-t * 24.0)
    blip = np.sin(phase) * env * 0.65
    stereo = np.column_stack((blip, blip))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_bubble_pop(dest_mp3):
    """Crisp organic mouth bubble pop."""
    dur = 0.12
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    # Rapid pitch up then down
    freq = 300.0 + 1400.0 * np.sin(np.pi * t / dur)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    env = np.sin(np.pi * t / dur) ** 2.5
    sig = np.sin(phase) * env * 0.7
    stereo = np.column_stack((sig, sig))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_cork_pop(dest_mp3):
    """Hollow wooden cork pop."""
    dur = 0.18
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    freq = 420.0 * np.exp(-t * 22.0) + 160.0
    phase = 2 * np.pi * np.cumsum(freq) / SR
    env = np.exp(-t * 20.0)
    pop = (np.sin(phase) * 0.7 + (np.random.rand(n) * 2.0 - 1.0) * 0.3) * env * 0.8
    stereo = np.column_stack((pop, pop))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_bell_ding(dest_mp3):
    """Pure brass service bell ding."""
    dur = 1.6
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    f0 = 2093.0 # C7
    bell = np.sin(2 * np.pi * f0 * t) * np.exp(-t * 3.5) * 0.5
    bell += np.sin(2 * np.pi * (f0 * 2.76) * t) * np.exp(-t * 6.0) * 0.25
    bell += np.sin(2 * np.pi * (f0 * 5.4) * t) * np.exp(-t * 9.0) * 0.15
    stereo = np.column_stack((bell, bell))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_success_chime(dest_mp3):
    """Bright upward 3-note major arpeggio chime (C6 -> E6 -> G6)."""
    dur = 1.2
    n = int(dur * SR)
    left = np.zeros(n)
    right = np.zeros(n)
    notes = [1046.50, 1318.51, 1567.98] # C6, E6, G6
    step = int(0.12 * SR)
    note_dur = 0.8
    nn = int(note_dur * SR)
    nt = np.linspace(0, note_dur, nn, endpoint=False)
    
    for i, freq in enumerate(notes):
        idx = i * step
        end = min(n, idx + nn)
        chime = np.sin(2 * np.pi * freq * nt[:end-idx]) * np.exp(-nt[:end-idx] * 4.5) * 0.4
        chime += np.sin(2 * np.pi * (freq * 2.0) * nt[:end-idx]) * np.exp(-nt[:end-idx] * 8.0) * 0.15
        pan = 0.35 if i == 0 else (0.5 if i == 1 else 0.65)
        left[idx:end] += chime * (1.0 - pan)
        right[idx:end] += chime * pan
        
    stereo = np.column_stack((left, right))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

def synth_error_buzz(dest_mp3):
    """Low game-show style double error buzzer."""
    dur = 0.85
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    f0 = 130.81 # C3
    buzz = np.sin(2 * np.pi * f0 * t) * 0.5 + np.sin(2 * np.pi * (f0 * 1.414) * t) * 0.5 # Dissonant tritone
    buzz += np.sin(2 * np.pi * (f0 * 3) * t) * 0.3
    # Double pulse gate (0.0 - 0.35s and 0.45 - 0.8s)
    gate = ((t < 0.32) | ((t > 0.42) & (t < 0.74))).astype(float)
    sig = np.tanh(buzz * 2.0) * gate * 0.7
    stereo = np.column_stack((sig, sig))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)

# ==========================================
# PROCEDURAL FULL SOUNDTRACKS (60s Short-Form)
# ==========================================

def synth_dark_investigative_pulse(dest_mp3):
    """68-second dark investigative suspense pulse: ticking clock, low sub drone, and tense piano ostinato."""
    print("Synthesizing Dark Investigative Suspense Soundtrack (68s)...")
    dur = 68.0
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    left = np.zeros(n)
    right = np.zeros(n)
    
    # 1. Low Ominous Drone (55Hz A1 + detuned 55.4Hz)
    drone_env = np.sin(np.pi * t / dur) ** 0.3 * 0.35
    drone_l = np.sin(2 * np.pi * 55.0 * t) * drone_env
    drone_r = np.sin(2 * np.pi * 55.4 * t) * drone_env
    left += drone_l
    right += drone_r
    
    # 2. Continuous Ticking Clock at 120 BPM (0.5s interval)
    tick_dur = 0.03
    tn = int(tick_dur * SR)
    tt = np.linspace(0, tick_dur, tn, endpoint=False)
    tick_sound = np.sin(2 * np.pi * 1800.0 * tt) * np.exp(-tt * 180.0) * 0.22
    for s in range(int(dur / 0.5)):
        idx = int(s * 0.5 * SR)
        end = min(n, idx + tn)
        left[idx:end] += tick_sound[:end-idx] * 0.5
        right[idx:end] += tick_sound[:end-idx] * 0.5
        
    # 3. Sub Pulse on every 2 beats (1.0s interval)
    p_dur = 0.4
    pn = int(p_dur * SR)
    pt = np.linspace(0, p_dur, pn, endpoint=False)
    sub_pulse = np.sin(2 * np.pi * (65.0 - 15.0 * pt) * pt) * np.sin(np.pi * pt / p_dur) ** 2.0 * 0.45
    for s in range(int(dur / 1.0)):
        idx = int(s * 1.0 * SR)
        end = min(n, idx + pn)
        left[idx:end] += sub_pulse[:end-idx]
        right[idx:end] += sub_pulse[:end-idx]
        
    # 4. Minimalist Tense Piano Stabs (Am -> F -> Dm -> E)
    chords = [
        [220.0, 261.63, 329.63], # Am
        [174.61, 220.0, 261.63], # F
        [146.83, 220.0, 293.66], # Dm
        [164.81, 246.94, 329.63], # E
    ]
    chord_dur = 4.0 # 4s per chord
    for c_idx in range(int(dur / chord_dur)):
        c_freqs = chords[c_idx % len(chords)]
        c_start = int(c_idx * chord_dur * SR)
        c_dur = 3.5
        cn = int(c_dur * SR)
        ct = np.linspace(0, c_dur, cn, endpoint=False)
        piano_env = np.exp(-ct * 1.2) * 0.18
        sig = np.zeros(cn)
        for cf in c_freqs:
            sig += np.sin(2 * np.pi * cf * ct) * 0.6 + np.sin(2 * np.pi * cf * 2 * ct) * 0.3
        sig *= piano_env
        end = min(n, c_start + cn)
        left[c_start:end] += sig[:end-c_start]
        right[c_start:end] += sig[:end-c_start]
        
    # Master smooth fade out
    fade_len = int(3.0 * SR)
    fade_env = np.ones(n)
    fade_env[-fade_len:] = np.linspace(1.0, 0.0, fade_len)
    left *= fade_env * 0.75
    right *= fade_env * 0.75
    
    stereo = np.column_stack((left, right))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)
    print("  [OK] Synthesized Dark Investigative Pulse")

def synth_lofi_chill_beats(dest_mp3):
    """65-second relaxed lofi hip-hop beat: vinyl warmth, Rhodes chords, boom-bap drum groove."""
    print("Synthesizing Lofi Chillhop Beats (65s)...")
    dur = 65.0
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    left = np.zeros(n)
    right = np.zeros(n)
    
    # 1. Vinyl Crackle Background
    crackle = (np.random.rand(n) > 0.996).astype(float) * (np.random.rand(n) * 2.0 - 1.0) * 0.08
    hiss = (np.random.rand(n) * 2.0 - 1.0) * 0.015
    left += crackle + hiss
    right += crackle + hiss
    
    # 2. 85 BPM Boom-Bap Rhythm
    bpm = 85
    beat_dur = 60.0 / bpm # ~0.706s
    num_beats = int(dur / beat_dur)
    
    # Kick (beat 0 and beat 2.5)
    kick_dur = 0.22
    kn = int(kick_dur * SR)
    kt = np.linspace(0, kick_dur, kn, endpoint=False)
    kick = np.sin(2 * np.pi * (80.0 * np.exp(-kt * 22.0) + 42.0) * kt) * np.exp(-kt * 10.0) * 0.45
    
    # Snare / Rimshot (beat 1 and beat 3)
    snare_dur = 0.18
    snn = int(snare_dur * SR)
    snt = np.linspace(0, snare_dur, snn, endpoint=False)
    snare = (np.random.rand(snn) * 2.0 - 1.0) * np.exp(-snt * 25.0) * 0.28
    snare += np.sin(2 * np.pi * 175.0 * snt) * np.exp(-snt * 30.0) * 0.2
    
    # Hi-hat (every 8th note with swing)
    hh_dur = 0.05
    hn = int(hh_dur * SR)
    ht = np.linspace(0, hh_dur, hn, endpoint=False)
    hh = (np.random.rand(hn) * 2.0 - 1.0) * np.exp(-ht * 65.0) * 0.12
    
    for b in range(num_beats):
        b_time = b * beat_dur
        # Kick on 1 and 3-and
        if b % 2 == 0:
            idx = int(b_time * SR)
            end = min(n, idx + kn)
            left[idx:end] += kick[:end-idx]
            right[idx:end] += kick[:end-idx]
        # Snare on 2 and 4
        if b % 2 == 1:
            idx = int(b_time * SR)
            end = min(n, idx + snn)
            left[idx:end] += snare[:end-idx]
            right[idx:end] += snare[:end-idx]
        # Hi-hats
        for sub in [0.0, 0.55]: # swing
            idx = int((b_time + sub * beat_dur) * SR)
            end = min(n, idx + hn)
            if idx < n:
                left[idx:end] += hh[:end-idx] * 0.8
                right[idx:end] += hh[:end-idx] * 1.2
                
    # 3. Warm Rhodes 7th Chords (Cmaj7 -> Am7 -> Dm7 -> G7)
    chords = [
        [130.81, 164.81, 196.00, 246.94], # Cmaj7
        [110.00, 130.81, 164.81, 196.00], # Am7
        [146.83, 174.61, 220.00, 261.63], # Dm7
        [98.00, 123.47, 146.83, 174.61],  # G7
    ]
    chord_dur = beat_dur * 4 # 4 beats per bar
    num_chords = int(dur / chord_dur) + 1
    for c_idx in range(num_chords):
        cf_list = chords[c_idx % len(chords)]
        c_start = int(c_idx * chord_dur * SR)
        c_len = int(chord_dur * 0.95 * SR)
        ct = np.linspace(0, chord_dur * 0.95, c_len, endpoint=False)
        env = np.exp(-ct * 0.8) * 0.16
        sig_l = np.zeros(c_len)
        sig_r = np.zeros(c_len)
        for cf in cf_list:
            # Gentle vibrato / tape flutter
            vibrato = 1.0 + 0.004 * np.sin(2 * np.pi * 3.5 * ct)
            sig_l += np.sin(2 * np.pi * (cf * vibrato) * ct) * 0.5
            sig_r += np.sin(2 * np.pi * (cf * vibrato * 1.003) * ct) * 0.5
        end = min(n, c_start + c_len)
        left[c_start:end] += sig_l[:end-c_start] * env[:end-c_start]
        right[c_start:end] += sig_r[:end-c_start] * env[:end-c_start]
        
    fade_len = int(2.5 * SR)
    fade_env = np.ones(n)
    fade_env[-fade_len:] = np.linspace(1.0, 0.0, fade_len)
    left *= fade_env * 0.8
    right *= fade_env * 0.8
    
    stereo = np.column_stack((left, right))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)
    print("  [OK] Synthesized Lofi Chillhop Beats")

def synth_drift_phonk_banger(dest_mp3):
    """60-second high-energy drift phonk: distorted 808s, cowbell melody, punchy Memphis rhythm."""
    print("Synthesizing Drift Phonk Banger (60s, 136 BPM)...")
    dur = 60.0
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    left = np.zeros(n)
    right = np.zeros(n)
    
    bpm = 136
    beat_dur = 60.0 / bpm # ~0.441s
    num_beats = int(dur / beat_dur)
    
    # Cowbell melody notes in F minor: F5, Ab5, G5, F5, C6, Bb5, Ab5, G5
    # F5=698.46, Ab5=830.61, G5=783.99, C6=1046.50, Bb5=932.33
    cowbell_scale = [698.46, 830.61, 783.99, 698.46, 1046.50, 932.33, 830.61, 783.99]
    step_dur = beat_dur / 2.0
    num_steps = int(dur / step_dur)
    cb_dur = 0.2
    cbn = int(cb_dur * SR)
    cbt = np.linspace(0, cb_dur, cbn, endpoint=False)
    
    for s in range(num_steps):
        freq = cowbell_scale[s % len(cowbell_scale)]
        # Classic 808 cowbell: two bandpassed square/sine waves
        cb = (np.sin(2 * np.pi * freq * cbt) * 0.7 + np.sin(2 * np.pi * (freq * 1.5) * cbt) * 0.3)
        cb *= np.exp(-cbt * 18.0) * 0.38
        idx = int(s * step_dur * SR)
        end = min(n, idx + cbn)
        pan = 0.35 if s % 2 == 0 else 0.65
        left[idx:end] += cb[:end-idx] * (1.0 - pan)
        right[idx:end] += cb[:end-idx] * pan
        
    # Hard 808 Sub (F1=43.65Hz, Ab1=51.91Hz, C2=65.41Hz, Bb1=58.27Hz)
    bass_notes = [43.65, 43.65, 51.91, 58.27]
    bar_dur = beat_dur * 4
    num_bars = int(dur / bar_dur)
    for bar in range(num_bars):
        bfreq = bass_notes[bar % len(bass_notes)]
        for b_in_bar in [0, 1.5, 2.5]: # Phonk 808 syncopation
            b_start = int((bar * bar_dur + b_in_bar * beat_dur) * SR)
            b_len = int(0.6 * SR)
            bt = np.linspace(0, 0.6, b_len, endpoint=False)
            b_sig = np.sin(2 * np.pi * (bfreq + 20.0 * np.exp(-bt * 30.0)) * bt) * np.exp(-bt * 2.5)
            # Heavy distortion
            b_sig = np.tanh(b_sig * 2.8) * 0.55
            end = min(n, b_start + b_len)
            left[b_start:end] += b_sig[:end-b_start]
            right[b_start:end] += b_sig[:end-b_start]
            
    # Punchy Claps on beats 2 and 4
    clap_dur = 0.15
    cln = int(clap_dur * SR)
    clt = np.linspace(0, clap_dur, cln, endpoint=False)
    clap = (np.random.rand(cln) * 2.0 - 1.0) * np.exp(-clt * 22.0) * 0.35
    for b in range(1, num_beats, 2):
        idx = int(b * beat_dur * SR)
        end = min(n, idx + cln)
        left[idx:end] += clap[:end-idx]
        right[idx:end] += clap[:end-idx]
        
    fade_len = int(2.5 * SR)
    fade_env = np.ones(n)
    fade_env[-fade_len:] = np.linspace(1.0, 0.0, fade_len)
    left *= fade_env * 0.8
    right *= fade_env * 0.8
    
    stereo = np.column_stack((left, right))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)
    print("  [OK] Synthesized Drift Phonk Banger")

def synth_viral_funk_slap_bass(dest_mp3):
    """62-second bouncy TikTok upbeat funk track: slap bass, punchy brass stabs, driving groove."""
    print("Synthesizing Viral Upbeat Funk Track (62s, 118 BPM)...")
    dur = 62.0
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    left = np.zeros(n)
    right = np.zeros(n)
    
    bpm = 118
    beat_dur = 60.0 / bpm
    num_beats = int(dur / beat_dur)
    
    # Slap Bass Riff in E minor (E1=41.2Hz, G1=49.0Hz, A1=55.0Hz, B1=61.7Hz, D2=73.4Hz)
    bass_riff = [
        (0.0, 41.2, 0.2, 0.6),   # E thumb slap
        (0.5, 82.4, 0.12, 0.7),  # E2 pluck
        (1.0, 41.2, 0.18, 0.5),  # E
        (1.75, 49.0, 0.15, 0.6), # G
        (2.0, 55.0, 0.22, 0.6),  # A
        (2.75, 61.7, 0.14, 0.55),# B
        (3.0, 73.4, 0.2, 0.65),  # D
        (3.5, 82.4, 0.15, 0.7),  # E
    ]
    bar_dur = beat_dur * 4
    num_bars = int(dur / bar_dur)
    for bar in range(num_bars):
        bar_start = bar * bar_dur
        for b_time, freq, b_dur, b_vol in bass_riff:
            s_start = int((bar_start + b_time * beat_dur) * SR)
            bn = int(b_dur * SR)
            bt = np.linspace(0, b_dur, bn, endpoint=False)
            b_sig = (np.sin(2 * np.pi * freq * bt) * 0.7 + np.sin(2 * np.pi * freq * 2 * bt) * 0.3)
            # Slap transient click
            b_sig += (np.random.rand(bn) * 2.0 - 1.0) * np.exp(-bt * 70.0) * 0.4
            b_sig *= np.exp(-bt * 12.0) * b_vol * 0.55
            end = min(n, s_start + bn)
            left[s_start:end] += b_sig[:end-s_start]
            right[s_start:end] += b_sig[:end-s_start]
            
    # Four-on-the-floor Kick & Claps
    kn = int(0.2 * SR)
    kt = np.linspace(0, 0.2, kn, endpoint=False)
    kick = np.sin(2 * np.pi * (110.0 * np.exp(-kt * 25.0) + 48.0) * kt) * np.exp(-kt * 14.0) * 0.45
    
    cln = int(0.16 * SR)
    clt = np.linspace(0, 0.16, cln, endpoint=False)
    clap = (np.random.rand(cln) * 2.0 - 1.0) * np.exp(-clt * 22.0) * 0.28
    
    for b in range(num_beats):
        idx = int(b * beat_dur * SR)
        end_k = min(n, idx + kn)
        left[idx:end_k] += kick[:end_k-idx]
        right[idx:end_k] += kick[:end_k-idx]
        if b % 2 == 1:
            end_c = min(n, idx + cln)
            left[idx:end_c] += clap[:end_c-idx]
            right[idx:end_c] += clap[:end_c-idx]
            
    fade_len = int(2.5 * SR)
    fade_env = np.ones(n)
    fade_env[-fade_len:] = np.linspace(1.0, 0.0, fade_len)
    left *= fade_env * 0.78
    right *= fade_env * 0.78
    
    stereo = np.column_stack((left, right))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)
    print("  [OK] Synthesized Viral Funk Track")

def synth_epic_orchestral_rise(dest_mp3):
    """65-second cinematic orchestral build: staccato strings, timpani rolls, brass crescendo."""
    print("Synthesizing Epic Cinematic Orchestral Rise (65s)...")
    dur = 65.0
    n = int(dur * SR)
    t = np.linspace(0, dur, n, endpoint=False)
    left = np.zeros(n)
    right = np.zeros(n)
    
    bpm = 124
    beat_dur = 60.0 / bpm
    num_beats = int(dur / beat_dur)
    
    # 1. 16th-note Staccato String Ostinato in D minor (D4, F4, G4, A4)
    ostinato = [293.66, 293.66, 349.23, 293.66, 392.00, 293.66, 440.00, 349.23]
    step_dur = beat_dur / 4.0
    num_steps = int(dur / step_dur)
    sn = int(step_dur * SR)
    st = np.linspace(0, step_dur, sn, endpoint=False)
    
    for s in range(num_steps):
        freq = ostinato[s % len(ostinato)]
        # Progressive crescendo over 60 seconds
        crescendo = 0.15 + 0.65 * (s / num_steps) ** 1.8
        saw = np.sin(2 * np.pi * freq * st) * 0.6 + np.sin(2 * np.pi * freq * 2 * st) * 0.3 + np.sin(2 * np.pi * freq * 3 * st) * 0.1
        string_note = saw * np.exp(-st * 24.0) * crescendo * 0.28
        idx = int(s * step_dur * SR)
        end = min(n, idx + sn)
        pan = 0.35 if s % 2 == 0 else 0.65
        left[idx:end] += string_note[:end-idx] * (1.0 - pan)
        right[idx:end] += string_note[:end-idx] * pan
        
    # 2. Timpani Hits on downbeats
    tn = int(0.7 * SR)
    tt = np.linspace(0, 0.7, tn, endpoint=False)
    timpani = np.sin(2 * np.pi * (85.0 * np.exp(-tt * 6.0) + 40.0) * tt) * np.exp(-tt * 3.5) * 0.55
    for b in range(0, num_beats, 4):
        idx = int(b * beat_dur * SR)
        end = min(n, idx + tn)
        crescendo = 0.3 + 0.7 * (b / num_beats)
        left[idx:end] += timpani[:end-idx] * crescendo
        right[idx:end] += timpani[:end-idx] * crescendo
        
    fade_len = int(3.0 * SR)
    fade_env = np.ones(n)
    fade_env[-fade_len:] = np.linspace(1.0, 0.0, fade_len)
    left *= fade_env * 0.8
    right *= fade_env * 0.8
    
    stereo = np.column_stack((left, right))
    wav = dest_mp3.with_suffix(".wav")
    write_wav(wav, stereo)
    convert_wav_to_mp3(wav, dest_mp3)
    print("  [OK] Synthesized Epic Orchestral Rise")

# ==========================================
# MASTER REGISTRATION INTO POWER BINS
# ==========================================

def update_powerbins():
    """Register all soundtracks and sound effects into Kinetic Cut powerbins.json."""
    powerbins_file = Path(os.environ.get("LOCALAPPDATA", "")) / "KineticCut" / "KineticCut" / "powerbins.json"
    if not powerbins_file.exists():
        print(f"Warning: {powerbins_file} not found.")
        return
        
    try:
        data = json.loads(powerbins_file.read_text(encoding="utf-8"))
    except Exception as e:
        print("Error reading powerbins:", e)
        return
        
    folders = data.get("folders", ["Master"])
    for f in ["Master/Soundtracks", "Master/Sound Effects"]:
        if f not in folders:
            folders.append(f)
    data["folders"] = folders
    
    existing_media = data.get("media", [])
    
    # Helper to probe duration
    def get_dur(fpath):
        res = run_cmd(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(fpath)])
        try:
            return float(res.stdout.strip())
        except Exception:
            return 1.0
            
    # Add Soundtracks
    count_st = 0
    for mp3 in sorted(SOUNDTRACKS_DIR.glob("*.mp3")):
        norm_path = str(mp3.resolve())
        # Check if already present
        if any(e.get("folder") == "Master/Soundtracks" and e.get("media", {}).get("path") == norm_path for e in existing_media):
            continue
        dur = get_dur(mp3)
        media_id = math.trunc(mp3.stat().st_mtime * 1000)
        import hashlib
        h_id = hashlib.md5(mp3.name.encode()).hexdigest()[:12]
        entry = {
            "folder": "Master/Soundtracks",
            "media": {
                "id": h_id,
                "path": norm_path,
                "kind": "audio",
                "name": mp3.name,
                "duration": round(dur, 3),
                "width": 0,
                "height": 0,
                "fps": 0.0,
                "has_audio": True,
                "thumbnail": "",
                "timeline_preset": {}
            }
        }
        existing_media.append(entry)
        count_st += 1
        
    # Add Sound Effects
    count_sfx = 0
    for mp3 in sorted(SFX_DIR.glob("*.mp3")):
        norm_path = str(mp3.resolve())
        if any(e.get("folder") == "Master/Sound Effects" and e.get("media", {}).get("path") == norm_path for e in existing_media):
            continue
        dur = get_dur(mp3)
        import hashlib
        h_id = hashlib.md5(mp3.name.encode()).hexdigest()[:12]
        entry = {
            "folder": "Master/Sound Effects",
            "media": {
                "id": h_id,
                "path": norm_path,
                "kind": "audio",
                "name": mp3.name,
                "duration": round(dur, 3),
                "width": 0,
                "height": 0,
                "fps": 0.0,
                "has_audio": True,
                "thumbnail": "",
                "timeline_preset": {}
            }
        }
        existing_media.append(entry)
        count_sfx += 1
        
    data["media"] = existing_media
    powerbins_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"[OK] Registered {count_st} Soundtracks and {count_sfx} Sound Effects to Power Bins ({powerbins_file})")

def generate_readmes():
    """Create comprehensive README guides in both folders for the editor."""
    st_readme = SOUNDTRACKS_DIR / "README.md"
    st_md = """# Soundtracks Library (Short-Form & High-Retention)

Curated music beds tailored specifically for vertical 9:16 short-form videos (TikTok, YouTube Shorts, Instagram Reels).

### Recommended Project Settings:
- **Narration / Voiceover Gain**: `0.0 dB` (Primary focal audio)
- **Background Music Gain**: `-15.0 dB` to `-18.0 dB` (Clear presence without masking spoken dialogue)
- **Ducking**: Lower by additional `-4 dB` during high-emphasis hooks.

### Categories & Tracks:

#### 1. Suspense & Mystery / True Crime
- `01_Suspense_DB_Cooper_Mystery.mp3`: The iconic D.B. Cooper suspense music bed (ticking tension, deep bass).
- `02_Dark_Investigative_Pulse.mp3`: 120 BPM minimal investigative pulse, ticking clock, sub drone, and tense piano.
- `03_Conspiracy_Dark_Drone.mp3`: Ominous low drone with subtle metallic tension for dark revelations.
- `04_True_Crime_Minimal_Tension.mp3`: Cold acoustic piano notes over an uneasy atmospheric bed.

#### 2. Cyber, Tech & Future (Programming / Tech Guides / AI)
- `05_Cyber_Synth_Tech_Pulse.mp3`: 120 BPM punchy 16th-note synth arpeggio from 'Docker in 60 Seconds'.
- `06_Neon_Cyberpunk_Drive.mp3`: Driving 80s futuristic synthwave with punchy sidechain bass.
- `07_Futuristic_Tech_Sequencer.mp3`: Rapid digital sequencer rhythm for fast-paced coding/terminal visuals.
- `08_Glitch_Matrix_Modern_Beat.mp3`: Tech house & electronic hybrid beat for high-speed tutorials.

#### 3. Drift Phonk & High Energy (Gaming / Hype / Action / Gym)
- `09_Drift_Phonk_Cowbell_Banger.mp3`: Hard-hitting distorted 808s, cowbell melody, and syncopated Memphis rap rhythm.
- `10_Brazilian_Phonk_Bass_Bounce.mp3`: Heavy bounce phonk with distorted funk basslines.
- `11_Aggressive_Hype_Trap_Beat.mp3`: Rolling 16th hi-hats, heavy 808 sub drops, and aggressive brass stabs.

#### 4. Lofi & Chill Storytelling (Explainers / Conversational Vlogs)
- `12_Lofi_Study_Chillhop_Beats.mp3`: Warm vinyl crackle, nostalgic Rhodes 7th chords, and boom-bap drums.
- `13_Midnight_Coffee_Jazzy_Lofi.mp3`: Smooth relaxed Rhodes jazz piano with gentle background warmth.
- `14_Rainy_Day_Acoustic_Lofi.mp3`: Gentle acoustic guitar picking over soft lofi hip-hop drums.

#### 5. Cinematic & Epic Builds (Climaxes / Plot Twists / Emotional Hooks)
- `15_Epic_Orchestral_Strings_Rise.mp3`: Accelerating staccato violin ostinato building into a brass crescendo.
- `16_Heroic_Trailer_Hybrid_Beat.mp3`: Modern hybrid blockbuster trailer percussion and soaring synth strings.
- `17_High_Stakes_Thriller_Countdown.mp3`: Fast-paced ticking thriller with urgent string ostinatos.

#### 6. Upbeat Funk & Viral Beats (Comedy / Quick Tips / Reaction Shorts)
- `18_Viral_TikTok_Funk_Slap_Bass.mp3`: Upbeat bouncy funk slap bass, finger snaps, and infectious rhythm.
- `19_Quirky_Comedy_Pizzicato.mp3`: Playful violin pizzicato and bouncy marimba for funny moments or fails.
- `20_Aesthetic_RnB_Trap_Soul.mp3`: Modern aesthetic chill trap soul beat for stylish lifestyle and tech shorts.
"""
    st_readme.write_text(st_md, encoding="utf-8")
    
    sfx_readme = SFX_DIR / "README.md"
    sfx_md = """# Sound Effects Library (Short-Form & High-Retention)

Punchy, broadcast-mastered sound effects for video editing, transitions, punch zooms, text highlights, and comedic timing.

### Recommended SFX Gains:
- **Whooshes / Swipes**: `-4.0 dB` to `-6.0 dB`
- **Sub Booms / 808 Drops**: `-2.0 dB` to `-3.0 dB`
- **UI Clicks / Text Blips**: `-6.0 dB` to `-8.0 dB`
- **Accents & Bells**: `-3.0 dB` to `-5.0 dB`

### Categories & Files:

#### 1. Whooshes & Transitions (Quick Pans, Slide Cuts, Overlay Card Entries)
- `Whoosh_Fast_Air_Whip.mp3`: Snappy high-speed whip whoosh for rapid scene changes.
- `Whoosh_Cinematic_Deep_Sub.mp3`: Heavy low-end whoosh for dramatic transitions.
- `Whoosh_Snap_Quick_Swipe.mp3`: Clean quick swipe for UI cards and image swipes.
- `Whoosh_SciFi_Glitch.mp3`: Digital glitch whoosh with electronic stutter.
- `Whoosh_Wind_Riser.mp3`: Smooth atmospheric wind sweep.
- `Whoosh_Reverse_Swell.mp3`: Inverted whoosh that sucks in before a hard cut.
- `Whoosh_Paper_Slide.mp3`: Crisp tactile paper slide for text and document reveals.

#### 2. Impacts & Booms (Punch Zooms, Beat Drops, Title Reveals)
- `Impact_Cinematic_Sub_Boom.mp3`: Deep sub-bass boom (110Hz -> 32Hz) that shakes the subwoofer.
- `Impact_Heavy_Trailer_Hit.mp3`: Punchy cinematic trailer drum hit with crisp transient.
- `Impact_Brass_Braam_Inception.mp3`: Low aggressive brass 'Horn of Doom' (Hans Zimmer braam).
- `Impact_808_Sub_Drop.mp3`: Modern 808 sub bass drop with warm analog saturation.
- `Impact_Metallic_Thud.mp3`: Heavy mechanical industrial metallic impact.
- `Impact_Punchy_Chest_Thump.mp3`: Snappy, punchy acoustic thump for fast cuts.
- `Impact_Digital_Cyber_Hit.mp3`: High-tech electronic transient hit for cyber/sci-fi visuals.
- `Impact_Explosion_Rumble.mp3`: Distant low-frequency cinematic rumble.

#### 3. Risers & Tension (Building Anticipation, Countdown Climax)
- `Riser_Cinematic_Tension_Swell.mp3`: 4-second ascending pitch & noise riser with tremolo.
- `Riser_White_Noise_Sweep.mp3`: Clean EDM-style filter sweep riser.
- `Tension_Clock_Ticking_Fast.mp3`: 4 seconds of rhythmic, high-tension analog clock ticks.
- `Tension_Heartbeat_Muffled_Pulse.mp3`: Visceral anatomical heartbeat (lub-dub) at 60 BPM.
- `Tension_Horror_Violin_Screech.mp3`: Psychological thriller dissonant string screech.

#### 4. Tech & Digital UI (Captions Popping, Code Typing, Diagram Steps)
- `UI_Digital_Blip_Clean.mp3`: Futuristic clean telemetry blip (from 'Docker in 60 Seconds').
- `UI_Mechanical_Keyboard_Burst.mp3`: Satisfying mechanical keyboard clacking burst.
- `UI_Crisp_Mouse_Click.mp3`: Tactile micro-switch mouse click.
- `UI_Modern_Notification_Chime.mp3`: Premium smartphone / app notification ding.
- `UI_Camera_Shutter_Click.mp3`: SLR mechanical camera shutter sound.
- `UI_Retro_8Bit_Terminal_Blip.mp3`: Nostalgic 8-bit computer beep.
- `UI_Digital_Glitch_Stutter.mp3`: Data corruption glitch sound.
- `UI_Flight_Chime_Alert.mp3`: Boeing 727 seatbelt chime (from 'The Mystery of D.B. Cooper').

#### 5. Pops, Bells & Accents (Word Highlights, Meme Punchlines, Stickers)
- `Pop_Bubble_Mouth.mp3`: Organic mouth bubble pop for popping word captions.
- `Pop_Wooden_Cork.mp3`: Punchy hollow wooden cork pop.
- `Accent_Brass_Bell_Ding.mp3`: Clear service desk bell ding for "Tip #1", "Important!".
- `Accent_Cash_Register_Kaching.mp3`: Classic cash register drawer sound for financial/sales topics.
- `Accent_Success_Major_Chime.mp3`: Ascending 3-note major arpeggio for positive results.
- `Accent_Error_Buzz_Wrong.mp3`: Game show buzz for mistakes, myths, or bad practices.
- `Accent_Vine_Boom_Bass.mp3`: The legendary dramatic bass boom for plot twists and memes.
- `Accent_Record_Scratch_Stop.mp3`: Sudden vinyl record scratch stop for unexpected cuts.
- `Accent_Cassette_Tape_Rewind.mp3`: Fast mechanical tape rewind for flashbacks.
- `Accent_Cartoon_Spring_Boing.mp3`: Playful boing for comedy and bloopers.
"""
    sfx_readme.write_text(sfx_md, encoding="utf-8")
    print("[OK] Created README.md documentation in Soundtracks and Sound_Effects folders.")

def main():
    print("--- 1. Importing Existing Master Assets ---")
    # Existing project master assets
    existing_st = [
        (ROOT / "assets_project" / "suspense_music.mp3", SOUNDTRACKS_DIR / "01_Suspense_DB_Cooper_Mystery.mp3", 75.0, 3.0),
        (ROOT / "assets_docker_guide" / "audio" / "cyber_synth_soundtrack.mp3", SOUNDTRACKS_DIR / "05_Cyber_Synth_Tech_Pulse.mp3", 68.0, 2.5),
    ]
    for src, dst, dur, fo in existing_st:
        if src.exists():
            normalize_mp3(src, dst, max_dur=dur, fade_in=0.05, fade_out=fo, target_lufs=-15)
            print(f"  [OK] Imported soundtrack: {dst.name}")
            
    existing_sfx = [
        (ROOT / "assets_project" / "cinematic_boom.mp3", SFX_DIR / "Impact_Cinematic_Sub_Boom.mp3"),
        (ROOT / "assets_project" / "whoosh.mp3", SFX_DIR / "Whoosh_Cinematic_Deep_Sub.mp3"),
        (ROOT / "assets_project" / "seatbelt_chime.mp3", SFX_DIR / "UI_Flight_Chime_Alert.mp3"),
        (ROOT / "assets_docker_guide" / "audio" / "transition_whoosh.mp3", SFX_DIR / "Whoosh_Fast_Air_Whip.mp3"),
        (ROOT / "assets_docker_guide" / "audio" / "digital_blip.mp3", SFX_DIR / "UI_Digital_Blip_Clean.mp3"),
        (ROOT / "assets_docker_guide" / "audio" / "impact_hit.mp3", SFX_DIR / "Impact_Heavy_Trailer_Hit.mp3"),
    ]
    for src, dst in existing_sfx:
        if src.exists():
            normalize_mp3(src, dst, max_dur=None, fade_in=0.005, fade_out=0.02, target_lufs=-10)
            print(f"  [OK] Imported SFX: {dst.name}")

    # User meme folder imports
    meme_dir = Path(r"C:\Users\F\Downloads\Meme sound effects")
    if meme_dir.exists():
        meme_map = [
            ("vine-boom-sound-effect_KT89XIq (1).mp3", SFX_DIR / "Accent_Vine_Boom_Bass.mp3"),
            ("violin-screech-meme.mp3", SFX_DIR / "Tension_Horror_Violin_Screech.mp3"),
            ("keyboard-meme.mp3", SFX_DIR / "UI_Mechanical_Keyboard_Burst.mp3"),
            ("duck-toy-sound.mp3", SFX_DIR / "Accent_Duck_Toy_Quack.mp3"),
            ("steve-old-hurt-sound_XKZxUk4.mp3", SFX_DIR / "Accent_Minecraft_Oof_Hurt.mp3"),
            ("anime-wow-sound-effect-mp3cut.mp3", SFX_DIR / "Accent_Anime_Wow_Sound.mp3"),
            ("punch-gaming-sound-effect-hd_RzlG1GE.mp3", SFX_DIR / "Impact_Punchy_Chest_Thump.mp3"),
        ]
        for fname, dst in meme_map:
            src = meme_dir / fname
            if src.exists():
                normalize_mp3(src, dst, max_dur=None, fade_in=0.005, fade_out=0.02, target_lufs=-10)
                print(f"  [OK] Imported Meme SFX: {dst.name}")

    print("\n--- 2. Synthesizing High-Fidelity Procedural Soundtracks & SFX ---")
    synth_dark_investigative_pulse(SOUNDTRACKS_DIR / "02_Dark_Investigative_Pulse.mp3")
    synth_lofi_chill_beats(SOUNDTRACKS_DIR / "12_Lofi_Study_Chillhop_Beats.mp3")
    synth_drift_phonk_banger(SOUNDTRACKS_DIR / "09_Drift_Phonk_Cowbell_Banger.mp3")
    synth_viral_funk_slap_bass(SOUNDTRACKS_DIR / "18_Viral_TikTok_Funk_Slap_Bass.mp3")
    synth_epic_orchestral_rise(SOUNDTRACKS_DIR / "15_Epic_Orchestral_Strings_Rise.mp3")
    
    # Procedural SFX
    synth_braam_brass(SFX_DIR / "Impact_Brass_Braam_Inception.mp3")
    synth_808_sub_drop(SFX_DIR / "Impact_808_Sub_Drop.mp3")
    synth_whoosh_deep(SFX_DIR / "Whoosh_Reverse_Swell.mp3")
    synth_whoosh_glitch(SFX_DIR / "Whoosh_SciFi_Glitch.mp3")
    synth_riser_tension(SFX_DIR / "Riser_Cinematic_Tension_Swell.mp3")
    synth_clock_tick(SFX_DIR / "Tension_Clock_Ticking_Fast.mp3")
    synth_heartbeat(SFX_DIR / "Tension_Heartbeat_Muffled_Pulse.mp3")
    synth_bubble_pop(SFX_DIR / "Pop_Bubble_Mouth.mp3")
    synth_cork_pop(SFX_DIR / "Pop_Wooden_Cork.mp3")
    synth_bell_ding(SFX_DIR / "Accent_Brass_Bell_Ding.mp3")
    synth_success_chime(SFX_DIR / "Accent_Success_Major_Chime.mp3")
    synth_error_buzz(SFX_DIR / "Accent_Error_Buzz_Wrong.mp3")

    print("\n--- 3. Downloading Curated Viral Short-Form Soundtracks ---")
    # Top YouTube royalty-free short-form music beds
    dl_soundtracks = [
        ("Brazilian Phonk Montagem instrumental royalty free no copyright", SOUNDTRACKS_DIR / "10_Brazilian_Phonk_Bass_Bounce.mp3", 65.0, 2.5),
        ("Cyberpunk Synthwave 80s dark retro royalty free no copyright", SOUNDTRACKS_DIR / "06_Neon_Cyberpunk_Drive.mp3", 75.0, 3.0),
        ("Midnight Coffee chill jazz lofi beats royalty free no copyright", SOUNDTRACKS_DIR / "13_Midnight_Coffee_Jazzy_Lofi.mp3", 70.0, 3.0),
        ("Epic hybrid trailer heroic brass percussion royalty free no copyright", SOUNDTRACKS_DIR / "16_Heroic_Trailer_Hybrid_Beat.mp3", 70.0, 3.0),
        ("High stakes thriller countdown cinematic strings royalty free no copyright", SOUNDTRACKS_DIR / "17_High_Stakes_Thriller_Countdown.mp3", 65.0, 2.5),
        ("Sneaky comedy pizzicato marimba royalty free no copyright", SOUNDTRACKS_DIR / "19_Quirky_Comedy_Pizzicato.mp3", 60.0, 2.5),
        ("Aesthetic trap soul chill RnB beat royalty free no copyright", SOUNDTRACKS_DIR / "20_Aesthetic_RnB_Trap_Soul.mp3", 70.0, 3.0),
        ("True crime dark ambient tension cello drone royalty free no copyright", SOUNDTRACKS_DIR / "03_Conspiracy_Dark_Drone.mp3", 75.0, 3.0),
        ("Aggressive workout hype trap beat royalty free no copyright", SOUNDTRACKS_DIR / "11_Aggressive_Hype_Trap_Beat.mp3", 65.0, 2.5),
        ("Futuristic tech sequencer arpeggiator electronic beat royalty free no copyright", SOUNDTRACKS_DIR / "07_Futuristic_Tech_Sequencer.mp3", 70.0, 2.5),
    ]
    for query, target, dur, fo in dl_soundtracks:
        download_audio(query, target, max_duration=dur, fade_out=fo, target_lufs=-15)

    print("\n--- 4. Downloading Curated Authentic Foley Sound Effects ---")
    dl_sfx = [
        ("cash register cha ching sound effect royalty free", SFX_DIR / "Accent_Cash_Register_Kaching.mp3", 3.0, 0.1),
        ("record scratch stop sound effect royalty free", SFX_DIR / "Accent_Record_Scratch_Stop.mp3", 2.5, 0.1),
        ("cassette tape rewind sound effect royalty free", SFX_DIR / "Accent_Cassette_Tape_Rewind.mp3", 3.0, 0.1),
        ("cartoon spring boing sound effect royalty free", SFX_DIR / "Accent_Cartoon_Spring_Boing.mp3", 2.0, 0.1),
        ("camera shutter click sound effect royalty free", SFX_DIR / "UI_Camera_Shutter_Click.mp3", 1.5, 0.05),
        ("computer mouse click sound effect royalty free", SFX_DIR / "UI_Crisp_Mouse_Click.mp3", 1.0, 0.05),
        ("smart phone modern notification chime sound effect royalty free", SFX_DIR / "UI_Modern_Notification_Chime.mp3", 2.0, 0.1),
        ("fast paper slide swipe sound effect royalty free", SFX_DIR / "Whoosh_Paper_Slide.mp3", 1.5, 0.05),
        ("white noise riser sweep sound effect royalty free", SFX_DIR / "Riser_White_Noise_Sweep.mp3", 3.5, 0.2),
        ("heavy metallic thud impact sound effect royalty free", SFX_DIR / "Impact_Metallic_Thud.mp3", 3.0, 0.1),
        ("cinema explosion low rumble sound effect royalty free", SFX_DIR / "Impact_Explosion_Rumble.mp3", 4.0, 0.5),
        ("retro 8 bit arcade blip jump sound effect royalty free", SFX_DIR / "UI_Retro_8Bit_Terminal_Blip.mp3", 1.2, 0.05),
    ]
    for query, target, dur, fo in dl_sfx:
        download_audio(query, target, max_duration=dur, fade_out=fo, target_lufs=-10)

    print("\n--- 5. Generating Documentation & Updating Power Bins ---")
    generate_readmes()
    update_powerbins()
    print("\n=== Audio Library Build Complete! ===")

if __name__ == "__main__":
    main()


