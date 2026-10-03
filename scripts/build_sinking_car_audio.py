import os
import math
import wave
import struct
import numpy as np
import subprocess

ASSETS_DIR = r"c:\Users\F\Documents\AI Projects\video-editor\build\sinking_car_assets"
os.makedirs(ASSETS_DIR, exist_ok=True)

SAMPLE_RATE = 44100

def write_wav(path, samples):
    # Ensure float in -1.0 to 1.0, convert to int16
    samples = np.clip(samples, -1.0, 1.0)
    int_samples = (samples * 32767).astype(np.int16)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(int_samples.tobytes())
    print("Wrote audio:", path)

# 1. Suspenseful Background Soundtrack (57 seconds)
def generate_suspense_soundtrack():
    duration = 57.0
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    audio = np.zeros_like(t)
    
    # A. Deep Sub Bass Drone (45 Hz with gentle modulation)
    sub = 0.28 * np.sin(2 * np.pi * 45 * t + 0.5 * np.sin(2 * np.pi * 0.2 * t))
    
    # B. Atmospheric high suspense pad (minor dissonance 220Hz + 225Hz + 440Hz + 444Hz)
    high_pad = (
        0.06 * np.sin(2 * np.pi * 220 * t) +
        0.06 * np.sin(2 * np.pi * 224.5 * t) +
        0.04 * np.sin(2 * np.pi * 440 * t) +
        0.03 * np.sin(2 * np.pi * 659.25 * t) # E5 minor 5th
    )
    # Slow tremolo on high pad
    tremolo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.35 * t)
    high_pad *= tremolo
    
    # C. Tension Heartbeat Pulses (starts at 1 pulse/sec = 60 bpm, speeds up to 85 bpm after 25s)
    heartbeat = np.zeros_like(t)
    # Generate beat times
    current_time = 0.5
    while current_time < duration:
        rate = 1.0 if current_time < 25.0 else 0.75 # faster after 25s
        # Double thump: lub-dub
        idx1 = int(current_time * SAMPLE_RATE)
        idx2 = int((current_time + 0.14) * SAMPLE_RATE)
        
        # 55 Hz decaying pulse
        for idx in [idx1, idx2]:
            pulse_len = int(0.18 * SAMPLE_RATE)
            if idx + pulse_len < len(heartbeat):
                pt = np.linspace(0, 0.18, pulse_len, endpoint=False)
                pulse = np.sin(2 * np.pi * 55 * pt) * np.exp(-pt * 20.0)
                heartbeat[idx:idx+pulse_len] += 0.25 * pulse
        current_time += rate
        
    # D. Tension Riser from 32s to 43s (rising sine sweep)
    riser = np.zeros_like(t)
    r_start, r_end = 32.0, 43.0
    r_mask = (t >= r_start) & (t <= r_end)
    rt = (t[r_mask] - r_start) / (r_end - r_start)
    # Frequency ramps from 150Hz to 600Hz
    phase = 2 * np.pi * (150 * rt + 0.5 * (600 - 150) * rt**2) * (r_end - r_start) / len(rt)
    # Envelope ramps up
    riser[r_mask] = 0.15 * (rt**1.5) * np.sin(phase)
    
    # E. Combine & overall envelope (fade in 1.5s, fade out 2.5s)
    fade_in = np.minimum(1.0, t / 1.5)
    fade_out = np.minimum(1.0, (duration - t) / 2.5)
    env = fade_in * fade_out
    
    audio = (sub + high_pad + heartbeat + riser) * env
    
    # Master volume: around -14 dB so dialogue is loud and crisp
    audio *= 0.45
    
    wav_path = os.path.join(ASSETS_DIR, "suspense_soundtrack.wav")
    write_wav(wav_path, audio)
    
    # Convert to mp3 using ffmpeg
    mp3_path = os.path.join(ASSETS_DIR, "suspense_soundtrack.mp3")
    subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-b:a", "192k", mp3_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Soundtrack MP3 ready:", mp3_path)

# 2. Sound Effects (SFX)
def generate_sfx():
    # A. Water Plunge (0.0s)
    dur = 2.5
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    # Low frequency rumble + noise burst
    noise = np.random.uniform(-1, 1, len(t))
    decay = np.exp(-t * 2.5)
    rumble = np.sin(2 * np.pi * 50 * t) * np.exp(-t * 1.5)
    splash = (0.4 * noise * decay + 0.6 * rumble) * 0.6
    write_wav(os.path.join(ASSETS_DIR, "sfx_water_plunge.wav"), splash)
    
    # B. Warning Alarm Triple Chime (1.2s)
    dur = 1.2
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    alarm = np.zeros_like(t)
    for i in range(3):
        st = i * 0.35
        idx = int(st * SAMPLE_RATE)
        plen = int(0.25 * SAMPLE_RATE)
        pt = np.linspace(0, 0.25, plen, endpoint=False)
        chime = (0.5 * np.sin(2 * np.pi * 880 * pt) + 0.5 * np.sin(2 * np.pi * 1175 * pt)) * np.exp(-pt * 12.0)
        alarm[idx:idx+plen] += chime * 0.35
    write_wav(os.path.join(ASSETS_DIR, "sfx_alarm_chime.wav"), alarm)
    
    # C. Door Mistake Error Buzzer (8.2s)
    dur = 0.8
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    # Low discordant square-ish buzzer + thud
    thud = np.sin(2 * np.pi * 60 * t) * np.exp(-t * 8.0)
    buzz = 0.3 * np.sign(np.sin(2 * np.pi * 140 * t)) * np.exp(-t * 4.0)
    err = (0.6 * thud + 0.4 * buzz) * 0.45
    write_wav(os.path.join(ASSETS_DIR, "sfx_door_error.wav"), err)
    
    # D. Seatbelt Buckle Click (19.3s)
    dur = 0.35
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    # High crisp transient click + mechanical clunk
    click = np.random.uniform(-1, 1, len(t)) * np.exp(-t * 80.0)
    clunk = np.sin(2 * np.pi * 320 * t) * np.exp(-t * 30.0)
    seatbelt = (0.6 * click + 0.5 * clunk) * 0.5
    write_wav(os.path.join(ASSETS_DIR, "sfx_seatbelt_click.wav"), seatbelt)
    
    # E. Electric Window Motor (27.2s)
    dur = 1.8
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    motor = (
        0.3 * np.sin(2 * np.pi * 120 * t) +
        0.2 * np.sin(2 * np.pi * 240 * t) +
        0.1 * np.random.uniform(-1, 1, len(t))
    )
    env = np.sin(np.pi * (t / dur))
    write_wav(os.path.join(ASSETS_DIR, "sfx_window_motor.wav"), motor * env * 0.3)
    
    # F. Glass Shatter Explosive Crack (41.5s)
    dur = 1.6
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    # Sharp high-frequency transient + granular scatter
    crack = np.random.uniform(-1, 1, len(t)) * np.exp(-t * 15.0)
    ring = np.sin(2 * np.pi * 3200 * t) * np.exp(-t * 8.0) * 0.3
    shatter = (0.7 * crack + 0.3 * ring) * 0.55
    write_wav(os.path.join(ASSETS_DIR, "sfx_glass_shatter.wav"), shatter)
    
    # G. Water Rush / Bubble Surge (44.0s)
    dur = 2.0
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    noise = np.random.uniform(-1, 1, len(t))
    # Low-pass filter approximation with cumulative sum / smoothing
    bubble = np.sin(2 * np.pi * 80 * t + 4.0 * np.sin(2 * np.pi * 5.0 * t))
    env = np.minimum(t / 0.3, 1.0) * np.exp(-(t - 0.3) * 1.5)
    rush = (0.4 * noise + 0.6 * bubble) * env * 0.4
    write_wav(os.path.join(ASSETS_DIR, "sfx_water_rush.wav"), rush)
    
    # H. Surface Whoosh / Takeaway Swell (52.0s)
    dur = 2.2
    t = np.linspace(0, dur, int(SAMPLE_RATE * dur), endpoint=False)
    whoosh = np.random.uniform(-1, 1, len(t)) * np.sin(np.pi * (t / dur))**2
    sine_chord = 0.3 * (np.sin(2 * np.pi * 440 * t) + np.sin(2 * np.pi * 554.37 * t)) * (t / dur) * np.exp(-t * 1.2)
    swell = (0.5 * whoosh + 0.5 * sine_chord) * 0.4
    write_wav(os.path.join(ASSETS_DIR, "sfx_surface_whoosh.wav"), swell)

generate_suspense_soundtrack()
generate_sfx()
print("All audio generated successfully!")
