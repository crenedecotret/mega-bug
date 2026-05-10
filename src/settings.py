"""Mega-Bug Modern — Configuration & Constants."""
from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class Colors:
    """Neon-Noir palette."""
    BG: Tuple[int, int, int] = (5, 5, 15)
    WALL_CORE: Tuple[int, int, int] = (0, 255, 255)
    WALL_MID: Tuple[int, int, int] = (0, 180, 200)
    WALL_HAZE: Tuple[int, int, int] = (0, 100, 120)
    PLAYER: Tuple[int, int, int] = (255, 200, 50)
    BUG_WANDER: Tuple[int, int, int] = (150, 50, 150)
    BUG_SCENT: Tuple[int, int, int] = (255, 50, 255)
    BUG_INTERCEPT: Tuple[int, int, int] = (255, 0, 80)
    DOT: Tuple[int, int, int] = (200, 220, 255)
    DATA_CORE: Tuple[int, int, int] = (0, 255, 128)
    DEBUG_ASTAR: Tuple[int, int, int] = (0, 255, 0)
    DEBUG_HEAT: Tuple[int, int, int] = (255, 100, 0)
    TEXT: Tuple[int, int, int] = (220, 220, 240)


@dataclass(frozen=True)
class Config:
    """Gameplay & engine constants."""
    # Grid
    GRID_W: int = 31
    GRID_H: int = 31

    # Window
    WINDOW_W: int = 1280
    WINDOW_H: int = 720
    FULLSCREEN: bool = False
    FPS: int = 60

    # Derived
    CELL_SIZE: int = 23  # min(1280, 720) // 31

    # Gameplay
    PLAYER_SPEED: float = 4.0          # cells per second
    BUG_SPEED: float = 3.2             # 0.8x player
    BUG_BASE_COUNT: int = 4
    LIVES: int = 3
    INPUT_BUFFER_SEC: float = 0.1
    SCENT_ADD: float = 1.0
    SCENT_DECAY: float = 1.0 / (60 * 8.0)
    PINCER_DISTANCE: int = 10
    PREDICT_AHEAD_SEC: float = 2.0
    HEAT_BLUR_RADIUS: int = 1

    # Visual
    LENS_RADIUS: int = 150
    BLOOM_PASSES: int = 3
    BLOOM_CORE_ALPHA: int = 180
    BLOOM_MID_ALPHA: int = 80
    BLOOM_HAZE_ALPHA: int = 30
    BLOOM_CORE_BLUR: int = 1
    BLOOM_MID_BLUR: int = 3
    BLOOM_HAZE_BLUR: int = 7
    CHROMATIC_OFFSET: float = 2.5

    # Audio
    AUDIO_SAMPLE_RATE: int = 44100
    AUDIO_CHANNELS: int = 2
    AUDIO_FORMAT: int = -16
    AUDIO_BUFFER: int = 512

    # Keybindings
    KEYS_UP: Tuple[int, ...] = (119, 273)      # w, up
    KEYS_DOWN: Tuple[int, ...] = (115, 274)    # s, down
    KEYS_LEFT: Tuple[int, ...] = (97, 276)     # a, left
    KEYS_RIGHT: Tuple[int, ...] = (100, 275)   # d, right
    KEY_PAUSE: int = 112                       # p
    KEY_RESTART: int = 114                     # r
    KEY_FULLMAP: int = 9                       # tab
    KEY_DEBUG: int = 282                       # f3
    KEY_FULLSCREEN: int = 292                  # f11

    @property
    def MAZE_PIXEL_W(self) -> int:
        return self.GRID_W * self.CELL_SIZE

    @property
    def MAZE_PIXEL_H(self) -> int:
        return self.GRID_H * self.CELL_SIZE


CFG = Config()
COL = Colors()
