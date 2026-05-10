"""Mega-Bug Modern — Procedural sound synthesis via pygame.sndarray + numpy."""
import math
import numpy as np
import pygame
from .settings import CFG


class AudioManager:
    """Generates and plays all game sounds procedurally."""

    def __init__(self):
        self.sample_rate = CFG.AUDIO_SAMPLE_RATE
        self.channels = CFG.AUDIO_CHANNELS
        self._last_step = 0
        self._step_phase = 0.0
        self._drone_phase = 0.0
        self._drone_note = 0
        self._buzz_phases: dict = {}

    def _generate_wave(
        self,
        duration: float,
        freq: float,
        wave_type: str = "sine",
        volume: float = 0.3,
    ) -> np.ndarray:
        """Generate a mono wave buffer."""
        samples = int(self.sample_rate * duration)
        t = np.linspace(0, duration, samples, endpoint=False)
        if wave_type == "sine":
            wave = np.sin(2 * np.pi * freq * t)
        elif wave_type == "saw":
            wave = 2 * (t * freq - np.floor(t * freq + 0.5))
        elif wave_type == "square":
            wave = np.sign(np.sin(2 * np.pi * freq * t))
        elif wave_type == "noise":
            wave = np.random.uniform(-1.0, 1.0, samples)
        else:
            wave = np.sin(2 * np.pi * freq * t)

        wave *= volume
        wave = np.clip(wave, -1.0, 1.0)

        # Simple low-pass-ish smoothing
        if wave_type != "noise":
            wave = np.convolve(wave, np.ones(4) / 4, mode="same")

        # Convert to 16-bit signed int
        wave_int = (wave * 32767).astype(np.int16)

        # Stereo if needed
        if self.channels == 2:
            wave_int = np.repeat(wave_int[:, np.newaxis], 2, axis=1)

        return wave_int

    def play_click(self) -> None:
        """Modern chomp: pitched ping with quick decay sweep."""
        samples = int(self.sample_rate * 0.06)
        t = np.linspace(0, 0.06, samples, endpoint=False)
        # Pitch sweep 800 -> 300 Hz
        freq = 800.0 - 500.0 * (t / 0.06)
        # Sine carrier with slight FM wobble
        wave = np.sin(2 * np.pi * freq * t) * (1.0 + 0.3 * np.sin(2 * np.pi * 60.0 * t))
        # Quick exponential decay envelope
        env = np.exp(-t * 40.0)
        wave = wave * env * 0.4
        wave = np.clip(wave, -1.0, 1.0)
        buf = (wave * 32767).astype(np.int16)
        if self.channels == 2:
            buf = np.repeat(buf[:, np.newaxis], 2, axis=1)
        snd = pygame.sndarray.make_sound(buf)
        snd.play()

    def play_bug_buzz(self, distance_ratio: float) -> None:
        """Filtered saw-tooth buzz; louder/sharper as bugs get closer."""
        if distance_ratio > 1.0:
            return
        vol = max(0.0, 0.2 * (1.0 - distance_ratio))
        freq = 300.0 + 400.0 * (1.0 - distance_ratio)
        buf = self._generate_wave(0.12, freq, "sine", vol)
        snd = pygame.sndarray.make_sound(buf)
        snd.play()

    def play_crush(self) -> None:
        """Sad descending tone for game over - like a defeated sigh."""
        sr = self.sample_rate
        dur = 0.8
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        
        # Descending sweep: 300 Hz → 100 Hz (sad trombone style)
        freq_sweep = np.linspace(300.0, 100.0, n)
        phase = np.cumsum(2.0 * np.pi * freq_sweep / sr)
        wave = np.sin(phase)
        
        # Add slight vibrato for organic feel
        vibrato = 1.0 + 0.02 * np.sin(2.0 * np.pi * 5.0 * t)
        wave = wave * vibrato
        
        # Smooth fade out envelope
        env = np.exp(-t * 2.5)
        wave = wave * env * 0.5
        wave = np.clip(wave, -1.0, 1.0)
        
        buf = (wave * 32767).astype(np.int16)
        if self.channels == 2:
            buf = np.repeat(buf[:, np.newaxis], 2, axis=1)
        snd = pygame.sndarray.make_sound(buf)
        snd.play()

    def play_arpeggio(self) -> None:
        """Triumphant arpeggio for level clear."""
        notes = [523.25, 659.25, 783.99, 1046.50]  # C5 E5 G5 C6
        full = []
        for n in notes:
            seg = self._generate_wave(0.12, n, "sine", 0.25)
            full.append(seg)
        combined = np.concatenate(full)
        snd = pygame.sndarray.make_sound(combined)
        snd.play()

    def play_warning(self) -> None:
        """Short ominous warning tone when near a spider.

        Low-frequency pulse with tremolo — creates tension without being
        too loud or distracting. Only plays if not already playing.
        """
        # Throttle: only play once per 0.3 seconds
        import time
        now = time.time()
        if hasattr(self, '_last_warning') and now - self._last_warning < 0.3:
            return
        self._last_warning = now

        sr = self.sample_rate
        dur = 0.2
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)

        # Sharp warning tone: 200 Hz with fast tremolo for urgency
        freq = 200.0
        tremolo = 0.6 + 0.4 * np.sin(2.0 * np.pi * 12.0 * t)  # 12 Hz tremolo
        wave = np.sin(2.0 * np.pi * freq * t) * tremolo

        # Add dissonance (tritone for tension)
        wave += 0.4 * np.sin(2.0 * np.pi * (freq * 1.4) * t) * tremolo

        # Quick fade in/out
        env = np.ones(n)
        fade = int(0.02 * sr)
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)

        wave = wave * env * 1.0
        wave = np.clip(wave, -1.0, 1.0)

        buf = (wave * 32767).astype(np.int16)
        if self.channels == 2:
            buf = np.repeat(buf[:, np.newaxis], 2, axis=1)
        snd = pygame.sndarray.make_sound(buf)
        snd.play()

    def play_chomp(self) -> None:
        """Retro arcade blip — a single clear descending note on each dot eaten.

        Consistent pitch every time: a short sine sweep that drops from
        420 Hz to 180 Hz, giving a satisfying 'bloop' pop.
        """
        start_freq = 420.0
        end_freq   = 180.0

        sr = self.sample_rate
        dur = 0.12
        n = int(sr * dur)
        t = np.linspace(0, dur, n, endpoint=False)

        # Frequency sweep: start_freq → end_freq over the note
        freq_sweep = np.linspace(start_freq, end_freq, n)
        phase = np.cumsum(2.0 * np.pi * freq_sweep / sr)
        wave = np.sin(phase)

        # Snappy envelope: instant attack, exponential decay
        env = np.exp(-t * 18.0)
        wave = wave * env * 0.5
        wave = np.clip(wave, -1.0, 1.0)

        buf = (wave * 32767).astype(np.int16)
        if self.channels == 2:
            buf = np.repeat(buf[:, np.newaxis], 2, axis=1)
        snd = pygame.sndarray.make_sound(buf)
        snd.play()
