"""Mega-Bug Modern — Entry point, main loop, game states, DPI setup."""
import sys
import random
import math
import ctypes
from enum import Enum, auto
from typing import List, Tuple, Optional

import pygame

from .settings import CFG, COL
from .engine import Maze, HeatMap, astar, Position
from .entities import Player, Bug, BugState, DIR_UP, DIR_DOWN, DIR_LEFT, DIR_RIGHT, DIR_NONE
from .renderer import Renderer
from .audio import AudioManager


# ── Windows High-DPI ──────────────────────────────────────────────
try:
    ctypes.windll.user32.SetProcessDPIAware()
except (AttributeError, OSError):
    pass  # Linux or older Windows


class GameState(Enum):
    MENU = auto()
    READY = auto()
    PLAYING = auto()
    PAUSED = auto()
    GAME_OVER = auto()
    LEVEL_TRANSITION = auto()
    CONFIRM_QUIT = auto()


class Game:
    def __init__(self):
        pygame.init()
        pygame.mixer.init(
            frequency=CFG.AUDIO_SAMPLE_RATE,
            size=-16,
            channels=CFG.AUDIO_CHANNELS,
            buffer=CFG.AUDIO_BUFFER,
        )
        self.screen = pygame.display.set_mode((CFG.WINDOW_W, CFG.WINDOW_H), pygame.RESIZABLE)
        pygame.display.set_caption("Mega-Bug")
        self.clock = pygame.time.Clock()
        self.renderer = Renderer(self.screen)
        self.audio = AudioManager()
        self.state = GameState.MENU
        self.level = 1
        self.lives = CFG.LIVES
        self.score = 0
        self.maze: Optional[Maze] = None
        self.player: Optional[Player] = None
        self.bugs: List[Bug] = []
        self.heat: Optional[HeatMap] = None
        self.show_debug = False
        self.show_full_map = False
        self.fullscreen = False
        self._prev_player_cell: Optional[Tuple[int, int]] = None
        self._level_transition_timer = 0.0
        self.visited: set = set()
        self._bugs_in_lens: set = set()  # track bugs currently visible in lens

    def _difficulty_params(self) -> dict:
        """Return difficulty-scaled parameters based on current level."""
        level = self.level
        # Bug count: 3 at level 1, +1 per level
        bug_count = 3 + (level - 1)
        # Bug speed: 2.5 at level 1, +0.15 per level, cap at 3.8 (player is 4.0)
        bug_speed = min(3.8, 2.5 + (level - 1) * 0.15)
        # Chase/scatter: more chase time, less scatter as levels progress
        chase_dur = min(12.0, 5.0 + level * 0.5)
        scatter_dur = max(2.0, 7.0 - level * 0.4)
        # Replan frequency: slower replans at low levels (easier to juke)
        replan_interval = max(1.0, 3.0 - (level - 1) * 0.2)
        # Prediction lookahead: 1 cell at low levels, up to 3
        predict_ahead = min(3, 1 + level // 3)
        return {
            "bug_count": bug_count,
            "bug_speed": bug_speed,
            "chase_dur": chase_dur,
            "scatter_dur": scatter_dur,
            "replan_interval": replan_interval,
            "predict_ahead": predict_ahead,
        }

    def _spawn_positions(self) -> Tuple[Position, List[Position]]:
        """Find a player start and spread-out bug spawns."""
        assert self.maze is not None
        floors = self.maze.floor_cells()
        player_pos = random.choice(floors)
        diff = self._difficulty_params()
        bug_count = diff["bug_count"]

        # Pick bugs spread apart using greedy farthest-point
        bug_spawns: List[Position] = []
        candidates = [p for p in floors if self.maze.distance(p, player_pos) >= 10]
        if not candidates:
            candidates = floors

        for _ in range(bug_count):
            if not candidates:
                break
            if not bug_spawns:
                # First bug: pick farthest from player
                best = max(candidates, key=lambda p: self.maze.distance(p, player_pos))
            else:
                # Subsequent: pick point farthest from all existing spawns
                def min_dist_to_existing(p: Position) -> float:
                    return min(self.maze.distance(p, s) for s in bug_spawns + [player_pos])
                best = max(candidates, key=min_dist_to_existing)
            bug_spawns.append(best)
            # Remove nearby candidates so next bug won't spawn adjacent
            candidates = [p for p in candidates if self.maze.distance(p, best) >= 6]

        return player_pos, bug_spawns

    def new_level(self) -> None:
        self.maze = Maze()
        self.heat = HeatMap()
        self.renderer.build_maze_surface(self.maze)
        player_pos, bug_spawns = self._spawn_positions()
        self.player = Player(*player_pos)
        diff = self._difficulty_params()
        self.bugs = [
            Bug(
                *b,
                bug_id=i,
                speed=diff["bug_speed"],
                chase_dur=diff["chase_dur"],
                scatter_dur=diff["scatter_dur"],
                replan_interval=diff["replan_interval"],
                predict_ahead=diff["predict_ahead"],
            )
            for i, b in enumerate(bug_spawns)
        ]
        self.state = GameState.READY
        self.visited = set()

    def restart(self) -> None:
        self.level = 1
        self.lives = CFG.LIVES
        self.score = 0
        self.new_level()

    def _handle_input(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        p = self.player
        if p:
            if self.state == GameState.READY:
                if any(keys[k] for k in (pygame.K_w, pygame.K_UP, pygame.K_s, pygame.K_DOWN,
                                         pygame.K_a, pygame.K_LEFT, pygame.K_d, pygame.K_RIGHT)):
                    self.state = GameState.PLAYING
            elif self.state == GameState.PLAYING:
                if keys[pygame.K_w] or keys[pygame.K_UP]:
                    p.request_turn(DIR_UP)
                elif keys[pygame.K_s] or keys[pygame.K_DOWN]:
                    p.request_turn(DIR_DOWN)
                elif keys[pygame.K_a] or keys[pygame.K_LEFT]:
                    p.request_turn(DIR_LEFT)
                elif keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                    p.request_turn(DIR_RIGHT)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if self.state in (GameState.PLAYING, GameState.PAUSED, GameState.READY,
                                  GameState.LEVEL_TRANSITION, GameState.MENU):
                    self._confirm_quit_return = self.state
                    self.state = GameState.CONFIRM_QUIT
                elif self.state == GameState.CONFIRM_QUIT:
                    # ESC cancels the dialog
                    self.state = self._confirm_quit_return
            if event.type == pygame.KEYDOWN and self.state == GameState.CONFIRM_QUIT:
                if event.key == pygame.K_y:
                    if self._confirm_quit_return == GameState.MENU:
                        pygame.quit()
                        sys.exit()
                    else:
                        self.level = 1
                        self.lives = CFG.LIVES
                        self.score = 0
                        self.state = GameState.MENU
                elif event.key == pygame.K_n:
                    self.state = self._confirm_quit_return
            if event.type == pygame.VIDEORESIZE:
                w, h = event.size
                self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
                self.renderer.screen = self.screen

            if event.type == pygame.KEYDOWN:
                p = self.player
                # Event-based movement backup
                if p and self.state == GameState.READY:
                    if event.key in (pygame.K_w, pygame.K_UP, pygame.K_s, pygame.K_DOWN,
                                     pygame.K_a, pygame.K_LEFT, pygame.K_d, pygame.K_RIGHT):
                        self.state = GameState.PLAYING
                elif p and self.state == GameState.PLAYING:
                    if event.key in (pygame.K_w, pygame.K_UP):
                        p.request_turn(DIR_UP)
                    elif event.key in (pygame.K_s, pygame.K_DOWN):
                        p.request_turn(DIR_DOWN)
                    elif event.key in (pygame.K_a, pygame.K_LEFT):
                        p.request_turn(DIR_LEFT)
                    elif event.key in (pygame.K_d, pygame.K_RIGHT):
                        p.request_turn(DIR_RIGHT)

                if event.key in (pygame.K_p, pygame.K_SPACE):
                    if self.state == GameState.PLAYING:
                        self.state = GameState.PAUSED
                    elif self.state == GameState.PAUSED:
                        self.state = GameState.PLAYING
                if event.key == pygame.K_r:
                    self.restart()
                if event.key == pygame.K_F3:
                    self.show_debug = not self.show_debug
                if event.key == pygame.K_TAB:
                    self.show_full_map = not self.show_full_map
                if event.key == pygame.K_F11:
                    self.fullscreen = not self.fullscreen
                    if self.fullscreen:
                        self._windowed_size = self.screen.get_size()
                        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        ww, wh = getattr(self, '_windowed_size', (CFG.WINDOW_W, CFG.WINDOW_H))
                        self.screen = pygame.display.set_mode((ww, wh), pygame.RESIZABLE)
                    self.renderer.screen = self.screen
                    if self.maze:
                        self.renderer.build_maze_surface(self.maze)
                if self.state == GameState.MENU and event.key == pygame.K_RETURN:
                    self.restart()
                if self.state == GameState.GAME_OVER and event.key == pygame.K_RETURN:
                    self.restart()

    def _update(self, dt: float) -> None:
        if self.state == GameState.READY:
            return
        if self.state not in (GameState.PLAYING, GameState.LEVEL_TRANSITION):
            return

        if self.state == GameState.LEVEL_TRANSITION:
            self._level_transition_timer -= dt
            if self._level_transition_timer <= 0:
                self.new_level()
            return

        p = self.player
        m = self.maze
        h = self.heat
        if p is None or m is None or h is None:
            return

        # Update player
        p.update(dt, m)
        if p.alive:
            h.add_heat(p.cell_x, p.cell_y)
        h.decay()

        # Track visited cells for trail rendering
        current_cell = (p.cell_x, p.cell_y)
        if p.alive and self._prev_player_cell != current_cell:
            self._prev_player_cell = current_cell
            self.visited.add(current_cell)

        # Dot collection
        if current_cell in m.dots:
            m.dots.remove(current_cell)
            self.score += 10
            self.audio.play_chomp()

        # Level clear
        if len(m.dots) == 0:
            self.audio.play_arpeggio()
            self.score += 100 * self.level  # bonus for clearing the level
            self._completed_level = self.level
            self.level += 1
            self.state = GameState.LEVEL_TRANSITION
            self._level_transition_timer = 2.0
            return

        # Update bugs (pass all other bugs for coordinated AI)
        for bug in self.bugs:
            other_bugs = [b for b in self.bugs if b is not bug]
            bug.update(dt, m, h, p, other_bugs)

        # Collision check
        for bug in self.bugs:
            dist = math.hypot(p.gx - bug.gx, p.gy - bug.gy)
            if dist < 0.7:
                self.lives -= 1
                if self.lives <= 0:
                    self.audio.play_crush()
                    self.state = GameState.GAME_OVER
                else:
                    # Respawn player away from bugs
                    floors = m.floor_cells()
                    safe = [f for f in floors if all(m.distance(f, b.pos) > 8 for b in self.bugs)]
                    if safe:
                        spawn = random.choice(safe)
                    else:
                        spawn = random.choice(floors)
                    p.gx = spawn[0] + 0.5
                    p.gy = spawn[1] + 0.5
                    p.cell_x = spawn[0]
                    p.cell_y = spawn[1]
                    p.facing = DIR_NONE
                    p.next_dir = None
                break

    def _draw_menu(self) -> None:
        self.screen.fill(COL.BG)
        font_big = pygame.font.SysFont("monospace", 48)
        font_small = pygame.font.SysFont("monospace", 24)
        title = font_big.render("MEGA-BUG", True, COL.WALL_CORE)
        sub = font_small.render("Press ENTER to Start", True, COL.TEXT)
        sw, sh = self.screen.get_size()
        self.screen.blit(title, (sw // 2 - title.get_width() // 2, sh // 3))
        self.screen.blit(sub, (sw // 2 - sub.get_width() // 2, sh // 3 + 100))

    def _draw_paused(self) -> None:
        self._draw_game()
        sw, sh = self.screen.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        font = pygame.font.SysFont("monospace", 48)
        text = font.render("PAUSED", True, COL.TEXT)
        self.screen.blit(text, (sw // 2 - text.get_width() // 2, sh // 2 - 24))

    def _draw_game_over(self) -> None:
        self._draw_game()
        sw, sh = self.screen.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))
        font_big = pygame.font.SysFont("monospace", 48)
        font_small = pygame.font.SysFont("monospace", 24)
        text = font_big.render("GAME OVER", True, COL.BUG_INTERCEPT)
        score_text = font_small.render(f"Score: {self.score}", True, COL.PLAYER)
        sub = font_small.render("Press ENTER to Restart", True, COL.TEXT)
        self.screen.blit(text, (sw // 2 - text.get_width() // 2, sh // 3))
        self.screen.blit(score_text, (sw // 2 - score_text.get_width() // 2, sh // 3 + 60))
        self.screen.blit(sub, (sw // 2 - sub.get_width() // 2, sh // 3 + 110))

    def _draw_level_transition(self) -> None:
        self._draw_game()
        sw, sh = self.screen.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 100))
        self.screen.blit(overlay, (0, 0))
        font = pygame.font.SysFont("monospace", 36)
        completed = getattr(self, '_completed_level', self.level - 1)
        text = font.render(f"LEVEL {completed} COMPLETE!", True, COL.DATA_CORE)
        self.screen.blit(text, (sw // 2 - text.get_width() // 2, sh // 2 - 18))

    def _draw_game(self) -> None:
        if self.maze and self.player and self.heat:
            visible_bugs = self.renderer.render_frame(
                self.maze,
                self.player,
                self.bugs,
                self.heat,
                visited=self.visited,
                show_debug=self.show_debug,
                show_full_map=self.show_full_map,
                level=self.level,
                lives=self.lives,
                score=self.score,
            )
            
            # Trigger warning when new bugs appear in lens
            visible_ids = {id(b) for b in visible_bugs}
            new_bugs = visible_ids - self._bugs_in_lens
            if new_bugs and self.state == GameState.PLAYING:
                self.audio.play_warning()
            self._bugs_in_lens = visible_ids

    def _draw_ready(self) -> None:
        self._draw_game()
        font = pygame.font.SysFont("monospace", 36)
        text = font.render("READY!", True, COL.TEXT)
        sw, sh = self.screen.get_size()
        self.screen.blit(text, (sw // 2 - text.get_width() // 2, sh // 8))

    def _draw_confirm_quit(self) -> None:
        # Draw whatever was underneath
        prev = self._confirm_quit_return
        if prev == GameState.MENU:
            self._draw_menu()
        elif prev in (GameState.PLAYING, GameState.READY, GameState.LEVEL_TRANSITION):
            self._draw_game()
        elif prev == GameState.PAUSED:
            self._draw_paused()
        else:
            self._draw_game()
        # Dark overlay
        sw, sh = self.screen.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        # Dialog text
        font_big = pygame.font.SysFont("arial,helvetica,sans-serif", 32, bold=True)
        font_sub = pygame.font.SysFont("arial,helvetica,sans-serif", 22)
        msg = "Return to menu?" if prev != GameState.MENU else "Quit Mega-Bug?"
        line1 = font_big.render(msg, True, COL.PLAYER)
        line2 = font_sub.render("Press  Y  to confirm     N  to cancel", True, COL.TEXT)
        self.screen.blit(line1, (sw // 2 - line1.get_width() // 2, sh // 2 - 40))
        self.screen.blit(line2, (sw // 2 - line2.get_width() // 2, sh // 2 + 10))

    def _draw(self) -> None:
        if self.state == GameState.MENU:
            self._draw_menu()
        elif self.state == GameState.READY:
            self._draw_ready()
        elif self.state == GameState.PAUSED:
            self._draw_paused()
        elif self.state == GameState.GAME_OVER:
            self._draw_game_over()
        elif self.state == GameState.LEVEL_TRANSITION:
            self._draw_level_transition()
        elif self.state == GameState.CONFIRM_QUIT:
            self._draw_confirm_quit()
        else:
            self._draw_game()
        pygame.display.flip()

    def run(self) -> None:
        while True:
            dt = self.clock.tick(CFG.FPS) / 1000.0
            dt = min(dt, 0.05)  # clamp to avoid big jumps
            self._handle_input(dt)
            self._update(dt)
            self._draw()


def main() -> None:
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
