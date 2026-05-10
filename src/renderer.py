"""Mega-Bug Modern — Neon-noir rendering, bloom, magnifying lens."""
import math
import pygame
import numpy as np
from typing import List, Tuple, Optional
from .settings import CFG, COL
from .engine import Maze, HeatMap
from .entities import Player, Bug, BugState, Direction


class Renderer:
    """Handles all drawing: maze, entities, bloom, lens, debug."""

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.maze_surf: Optional[pygame.Surface] = None
        self.bloom_surf: Optional[pygame.Surface] = None
        self.debug_surf: Optional[pygame.Surface] = None
        self.lens_mask: Optional[pygame.Surface] = None
        self._build_lens_mask()

    def _build_lens_mask(self) -> None:
        """Create a radial alpha mask for the lens."""
        size = CFG.LENS_RADIUS * 2
        self.lens_mask = pygame.Surface((size, size), pygame.SRCALPHA)
        self.lens_mask.fill((0, 0, 0, 0))
        cx = CFG.LENS_RADIUS
        for r in range(CFG.LENS_RADIUS, 0, -1):
            alpha = int(255 * (1.0 - (r / CFG.LENS_RADIUS) ** 2))
            pygame.draw.circle(self.lens_mask, (255, 255, 255, alpha), (cx, cx), r)

    def build_maze_surface(self, maze: Maze) -> None:
        """Pre-render static maze walls as ultra-dim blueprint lines."""
        mw = maze.w * CFG.CELL_SIZE
        mh = maze.h * CFG.CELL_SIZE
        self.maze_surf = pygame.Surface((mw, mh), pygame.SRCALPHA)
        self.maze_surf.fill((0, 0, 0, 0))

        cs = CFG.CELL_SIZE
        fill_color = (0, 40, 50, 255)
        wall_color = (0, 70, 80, 255)
        for y in range(maze.h):
            for x in range(maze.w):
                if maze.is_floor(x, y):
                    px = x * cs
                    py = y * cs
                    # Fill interior so maze structure is clear
                    pygame.draw.rect(self.maze_surf, fill_color, (px, py, cs, cs))
                    if maze.is_wall(x, y - 1):
                        pygame.draw.line(self.maze_surf, wall_color, (px, py), (px + cs, py), 3)
                    if maze.is_wall(x, y + 1):
                        pygame.draw.line(self.maze_surf, wall_color, (px, py + cs), (px + cs, py + cs), 3)
                    if maze.is_wall(x - 1, y):
                        pygame.draw.line(self.maze_surf, wall_color, (px, py), (px, py + cs), 3)
                    if maze.is_wall(x + 1, y):
                        pygame.draw.line(self.maze_surf, wall_color, (px + cs, py), (px + cs, py + cs), 3)

    def _gaussian_blur(self, surf: pygame.Surface, radius: int) -> pygame.Surface:
        """Approximate Gaussian blur using pygame's scale trick."""
        if radius <= 0:
            return surf.copy()
        w, h = surf.get_size()
        # Scale down
        small = pygame.transform.smoothscale(surf, (max(1, w // (radius + 1)), max(1, h // (radius + 1))))
        # Scale back up
        blurred = pygame.transform.smoothscale(small, (w, h))
        return blurred

    def _build_bloom(self, source: pygame.Surface) -> pygame.Surface:
        """3-pass additive bloom: thin core, mid haze, wide faint."""
        w, h = source.get_size()
        bloom = pygame.Surface((w, h), pygame.SRCALPHA)
        bloom.fill((0, 0, 0, 0))

        # Pass 1: core
        core = self._gaussian_blur(source, CFG.BLOOM_CORE_BLUR)
        core.set_alpha(CFG.BLOOM_CORE_ALPHA)
        bloom.blit(core, (0, 0))

        # Pass 2: mid
        mid = self._gaussian_blur(source, CFG.BLOOM_MID_BLUR)
        mid.set_alpha(CFG.BLOOM_MID_ALPHA)
        bloom.blit(mid, (0, 0))

        # Pass 3: haze
        haze = self._gaussian_blur(source, CFG.BLOOM_HAZE_BLUR)
        haze.set_alpha(CFG.BLOOM_HAZE_ALPHA)
        bloom.blit(haze, (0, 0))

        return bloom

    def draw_dots(self, target: pygame.Surface, maze: Maze) -> None:
        """Draw remaining dots."""
        for (x, y) in maze.dots:
            px = x * CFG.CELL_SIZE + CFG.CELL_SIZE // 2
            py = y * CFG.CELL_SIZE + CFG.CELL_SIZE // 2
            pygame.draw.circle(target, COL.DOT, (px, py), 3)

    def _draw_cockroach(
        self,
        target: pygame.Surface,
        cx: int,
        cy: int,
        size: int,
        color: Tuple[int, int, int],
        facing: Direction,
        walk_phase: float = 0.0,
    ) -> None:
        """Draw an 8-16-bit style cockroach with animated legs."""
        import math

        s = size * 5
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))

        body_color = color
        dark_color = (max(0, color[0] - 60), max(0, color[1] - 60), max(0, color[2] - 60))
        leg_color  = (max(0, color[0] - 40), max(0, color[1] - 40), max(0, color[2] - 40))
        eye_color  = (min(255, color[0] + 80), min(255, color[1] + 80), min(255, color[2] + 80))

        ox = s // 2  # origin
        oy = s // 2

        # body runs along X axis (facing RIGHT), centred at ox,oy
        body_l = size * 3 // 4    # half-length of body
        body_r = size * 5 // 12   # half-height (vertical radius — slim)

        # ── 6 Legs BEFORE body so body draws on top ──
        # 3 pairs spaced along body; each leg: shoulder → knee → toe
        # shoulder X positions (along body axis, centred at ox)
        shoulder_xs = [-body_l // 2, 0, body_l // 2 - 2]
        # knee extends sideways, toe points slightly backward
        upper = size * 5 // 8   # shoulder→knee length
        lower = size * 3 // 4   # knee→toe length

        for i, sx in enumerate(shoulder_xs):
            # forward-facing pairs angle slightly forward, back pair angles back
            lean = [0.2, 0.0, -0.2][i]  # forward lean angle (radians)
            swing = math.sin(walk_phase + i * math.pi / 1.5) * 0.28  # tripod gait

            # left leg (y negative = up on screen when facing right)
            kx = ox + sx - int(upper * math.sin(lean + swing))
            ky = oy - int(upper * math.cos(lean + swing))
            tx = kx - int(lower * math.sin(lean + swing * 0.5))
            ty = ky - int(lower * math.cos(lean + swing * 0.5) * 0.4)
            pygame.draw.line(surf, leg_color, (ox + sx, oy), (kx, ky), 2)
            pygame.draw.line(surf, leg_color, (kx, ky), (tx, ty), 2)

            # right leg (y positive = down)
            kx2 = ox + sx - int(upper * math.sin(lean - swing))
            ky2 = oy + int(upper * math.cos(lean - swing))
            tx2 = kx2 - int(lower * math.sin(lean - swing * 0.5))
            ty2 = ky2 + int(lower * math.cos(lean - swing * 0.5) * 0.4)
            pygame.draw.line(surf, leg_color, (ox + sx, oy), (kx2, ky2), 2)
            pygame.draw.line(surf, leg_color, (kx2, ky2), (tx2, ty2), 2)

        # ── Body (drawn on top of leg roots) ──
        # One large abdomen oval
        pygame.draw.ellipse(surf, body_color,
            (ox - body_l - 1, oy - body_r, body_l * 2 + 1, body_r * 2))
        pygame.draw.ellipse(surf, dark_color,
            (ox - body_l - 1, oy - body_r, body_l * 2 + 1, body_r * 2), 1)

        # Pronotum shield (slightly overlapping front of abdomen)
        pro_l = body_l * 2 // 5
        pro_r = body_r + 1
        pygame.draw.ellipse(surf, body_color,
            (ox + body_l // 6, oy - pro_r, pro_l, pro_r * 2))
        pygame.draw.ellipse(surf, dark_color,
            (ox + body_l // 6, oy - pro_r, pro_l, pro_r * 2), 1)

        # Shell ridges
        for rx in range(-body_l // 2, body_l // 2, max(3, body_l // 5)):
            pygame.draw.line(surf, dark_color,
                (ox + rx, oy - body_r + 1), (ox + rx, oy + body_r - 1), 1)

        # Head
        hx = ox + body_l - 2
        pygame.draw.ellipse(surf, body_color, (hx, oy - body_r // 2, body_r, body_r))
        pygame.draw.ellipse(surf, dark_color, (hx, oy - body_r // 2, body_r, body_r), 1)

        # Eyes
        pygame.draw.circle(surf, eye_color, (hx + body_r - 2, oy - 2), 1)
        pygame.draw.circle(surf, eye_color, (hx + body_r - 2, oy + 2), 1)

        # Antennae — short, animated wave
        aox = hx + body_r - 1
        ant_len = size * 3 // 8
        ant_wave = math.sin(walk_phase * 1.5) * 2.5
        # top antenna
        atx = aox + int(ant_len * 0.8)
        aty = oy - 2 - int(ant_len * 0.5) - int(ant_wave)
        pygame.draw.line(surf, leg_color, (aox, oy - 2), (atx, aty), 1)
        # bottom antenna
        abx = aox + int(ant_len * 0.8)
        aby = oy + 2 + int(ant_len * 0.5) + int(ant_wave)
        pygame.draw.line(surf, leg_color, (aox, oy + 2), (abx, aby), 1)

        # Rotate to facing direction
        rot = {(1,0): 0, (-1,0): 180, (0,-1): 90, (0,1): -90, (0,0): 0}.get(facing, 0)
        if rot:
            surf = pygame.transform.rotate(surf, rot)

        target.blit(surf, (cx - surf.get_width() // 2, cy - surf.get_height() // 2))

    def _draw_spider(self, target: pygame.Surface, cx: int, cy: int, size: int, color: Tuple[int, int, int]) -> None:
        """Draw an 8-16-bit style spider."""
        s = size * 3
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))

        body_color = color
        dark_color = (max(0, color[0] - 40), max(0, color[1] - 40), max(0, color[2] - 40))

        bx = s // 2
        by = s // 2
        body_r = size // 2

        # Body — round abdomen
        pygame.draw.circle(surf, body_color, (bx, by), body_r)
        pygame.draw.circle(surf, dark_color, (bx, by), body_r, 1)

        # Head — smaller circle in front
        head_r = body_r * 2 // 3
        pygame.draw.circle(surf, body_color, (bx + body_r // 2, by), head_r)
        pygame.draw.circle(surf, dark_color, (bx + body_r // 2, by), head_r, 1)

        # Eyes — multiple small dots
        eye = (min(255, color[0] + 50), min(255, color[1] + 50), min(255, color[2] + 50))
        eye_x = bx + body_r // 2 + head_r // 2
        pygame.draw.circle(surf, eye, (eye_x, by - 2), 1)
        pygame.draw.circle(surf, eye, (eye_x, by + 2), 1)
        pygame.draw.circle(surf, eye, (eye_x - 2, by - 1), 1)
        pygame.draw.circle(surf, eye, (eye_x - 2, by + 1), 1)

        # 8 legs radiating from body
        leg_color = dark_color
        import math
        for i in range(8):
            angle = (i * 45 - 90) * math.pi / 180  # spread around
            # Skip front angles to avoid overlap with head
            if i in [0, 7]:
                continue
            leg_len = size
            x1 = bx + int(body_r * 0.7 * math.cos(angle))
            y1 = by + int(body_r * 0.7 * math.sin(angle))
            x2 = bx + int(leg_len * math.cos(angle))
            y2 = by + int(leg_len * math.sin(angle))
            # Bent leg
            mid_x = (x1 + x2) // 2 + int(3 * math.cos(angle + math.pi / 2))
            mid_y = (y1 + y2) // 2 + int(3 * math.sin(angle + math.pi / 2))
            pygame.draw.line(surf, leg_color, (x1, y1), (mid_x, mid_y), 1)
            pygame.draw.line(surf, leg_color, (mid_x, mid_y), (x2, y2), 1)

        target.blit(surf, (cx - surf.get_width() // 2, cy - surf.get_height() // 2))

    def draw_entities(self, target: pygame.Surface, player: Player, bugs: List[Bug]) -> None:
        """Draw player and bugs — pixel-art cockroach for player."""
        px, py = player.pixel_pos
        size = max(6, CFG.CELL_SIZE // 2)
        self._draw_cockroach(
            target, int(px), int(py), size, COL.PLAYER, player.facing, player.walk_phase
        )

        for bug in bugs:
            bx, by = bug.pixel_pos
            color = {
                BugState.CHASE: COL.BUG_INTERCEPT,
                BugState.SCATTER: COL.BUG_WANDER,
            }[bug.state]
            self._draw_spider(target, int(bx), int(by), size, color)

    def render_lens(
        self,
        world: pygame.Surface,
        player: Player,
        bugs: List[Bug],
        overview_scale: float,
        ov_ox: int,
        ov_oy: int,
    ) -> List[Bug]:
        """True magnifying glass: capture from world, scale up, overlay on screen.
        
        Returns list of bugs visible in the lens.
        """
        px, py = int(player.pixel_pos[0]), int(player.pixel_pos[1])

        # Capture ~5 cells around player (2.5 cell radius) for tighter zoom
        capture_r = int(2.5 * CFG.CELL_SIZE)

        # Lens scales with the overview so magnification stays constant
        # regardless of window size. Lens is ~45% of the smaller overview dimension.
        world_w, world_h = world.get_size()
        overview_w = int(world_w * overview_scale)
        overview_h = int(world_h * overview_scale)
        lens_display = int(min(overview_w, overview_h) * 0.45)

        # Build padded capture (opaque black outside world edges)
        capture = pygame.Surface((capture_r * 2, capture_r * 2))
        capture.fill((5, 5, 15))  # match BG color

        world_rect = world.get_rect()
        src_x = px - capture_r
        src_y = py - capture_r
        copy_rect = pygame.Rect(src_x, src_y, capture_r * 2, capture_r * 2).clip(world_rect)

        if copy_rect.width > 0 and copy_rect.height > 0:
            offset_x = copy_rect.x - src_x
            offset_y = copy_rect.y - src_y
            capture.blit(world.subsurface(copy_rect), (offset_x, offset_y))

        # Scale up for magnification (nearest-neighbor for sharp pixels)
        zoomed = pygame.transform.scale(capture, (lens_display, lens_display))

        # Square lens (like original Mega-Bug)
        lens_img = pygame.Surface((lens_display, lens_display), pygame.SRCALPHA)
        lens_img.blit(zoomed, (0, 0))

        # Border
        border_color = COL.WALL_CORE
        pygame.draw.rect(lens_img, border_color, (0, 0, lens_display, lens_display), 4)
        pygame.draw.rect(lens_img, (255, 255, 255, 60), (2, 2, lens_display - 4, lens_display - 4), 1)

        # Position lens on screen (centered on player's overview position)
        player_screen_x = ov_ox + int(px * overview_scale)
        player_screen_y = ov_oy + int(py * overview_scale)
        lens_screen_x = player_screen_x - lens_display // 2
        lens_screen_y = player_screen_y - lens_display // 2

        self.screen.blit(lens_img, (lens_screen_x, lens_screen_y))

        # Check which bugs are in lens capture area
        visible_bugs = []
        for bug in bugs:
            bx, by = bug.pixel_pos
            if abs(bx - px) <= capture_r and abs(by - py) <= capture_r:
                visible_bugs.append(bug)
        
        return visible_bugs

    def render_debug(
        self,
        target: pygame.Surface,
        heat: HeatMap,
        bugs: List[Bug],
        maze: Maze,
    ) -> pygame.Surface:
        """Overlay heat map and A* paths."""
        debug = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        # Heat map
        for y in range(heat.h):
            for x in range(heat.w):
                v = heat.get(x, y)
                if v > 0.05:
                    px = x * CFG.CELL_SIZE
                    py = y * CFG.CELL_SIZE
                    alpha = int(min(255, v * 200))
                    pygame.draw.rect(
                        debug,
                        (COL.DEBUG_HEAT[0], COL.DEBUG_HEAT[1], COL.DEBUG_HEAT[2], alpha),
                        (px, py, CFG.CELL_SIZE, CFG.CELL_SIZE),
                    )
        # A* paths
        for bug in bugs:
            if bug.path:
                pts = [
                    (p[0] * CFG.CELL_SIZE + CFG.CELL_SIZE // 2, p[1] * CFG.CELL_SIZE + CFG.CELL_SIZE // 2)
                    for p in bug.path
                ]
                if len(pts) > 1:
                    pygame.draw.lines(debug, COL.DEBUG_ASTAR, False, pts, 2)
        target.blit(debug, (0, 0))
        return target

    def render_full_map(
        self,
        target: pygame.Surface,
        maze: Maze,
        player: Player,
        bugs: List[Bug],
    ) -> pygame.Surface:
        """Translucent full-map overlay."""
        mw = maze.w * CFG.CELL_SIZE
        mh = maze.h * CFG.CELL_SIZE
        if mw <= 0 or mh <= 0:
            return target
        tw, th = target.get_size()
        scale_x = tw / mw
        scale_y = th / mh
        scale = min(scale_x, scale_y) * 0.8

        map_surf = pygame.Surface((mw, mh), pygame.SRCALPHA)
        if self.maze_surf:
            map_surf.blit(self.maze_surf, (0, 0))
        self.draw_dots(map_surf, maze)
        self.draw_entities(map_surf, player, bugs)

        scaled = pygame.transform.smoothscale(
            map_surf,
            (int(mw * scale), int(mh * scale)),
        )
        scaled.set_alpha(180)

        ox = (tw - scaled.get_width()) // 2
        oy = (th - scaled.get_height()) // 2
        target.blit(scaled, (ox, oy))
        return target

    def render_frame(
        self,
        maze: Maze,
        player: Player,
        bugs: List[Bug],
        heat: HeatMap,
        visited: set = None,
        show_debug: bool = False,
        show_full_map: bool = False,
        level: int = 1,
        lives: int = 3,
        score: int = 0,
    ) -> List[Bug]:
        """Full render pipeline: tiny overview + magnifying lens.
        
        Returns list of bugs visible in the lens.
        """
        self.screen.fill(COL.BG)

        mw = maze.w * CFG.CELL_SIZE
        mh = maze.h * CFG.CELL_SIZE

        # 1. Build world at 1x (full resolution)
        world = pygame.Surface((mw, mh), pygame.SRCALPHA)
        world.fill((0, 0, 0, 0))

        if self.maze_surf:
            world.blit(self.maze_surf, (0, 0))

        # Visited trail (like original Mega-Bug)
        if visited:
            trail_color = (80, 50, 10, 80)
            cs = CFG.CELL_SIZE
            for (x, y) in visited:
                if maze.is_floor(x, y):
                    # Draw a small warm mark in the center of visited cells
                    cx = x * cs + cs // 2
                    cy = y * cs + cs // 2
                    r = cs // 4
                    pygame.draw.circle(world, trail_color, (cx, cy), r)

        self.draw_dots(world, maze)
        self.draw_entities(world, player, bugs)

        if show_debug:
            self.render_debug(world, heat, bugs, maze)

        sw, sh = self.screen.get_size()

        # 2. Overview: dynamically scale maze to fit window with margin
        margin_x = 40
        margin_y = 80  # space for HUD above
        avail_w = sw - margin_x * 2
        avail_h = sh - margin_y * 2
        overview_scale = min(avail_w / mw, avail_h / mh) * 0.95
        overview_w = int(mw * overview_scale)
        overview_h = int(mh * overview_scale)
        overview = pygame.transform.smoothscale(world, (overview_w, overview_h))

        ov_ox = (sw - overview_w) // 2
        ov_oy = (sh - overview_h) // 2 + 10  # slight nudge down
        self.screen.blit(overview, (ov_ox, ov_oy))

        # 3. Magnifying lens: capture from world, scale up, overlay
        visible_bugs = []
        if not show_full_map:
            visible_bugs = self.render_lens(world, player, bugs, overview_scale, ov_ox, ov_oy)

        # 4. Full map overlay
        if show_full_map:
            self.render_full_map(self.screen, maze, player, bugs)

        # HUD — three sections evenly spread across the maze width
        font = pygame.font.SysFont("arial,helvetica,sans-serif", 22, bold=True)
        t_score = font.render(f"Score: {score}", True, COL.PLAYER)
        t_level = font.render(f"Level: {level}", True, COL.PLAYER)
        t_lives = font.render(f"Lives: {lives}   Dots: {len(maze.dots)}", True, COL.PLAYER)
        hud_y = ov_oy - 34
        self.screen.blit(t_score, (ov_ox, hud_y))
        self.screen.blit(t_level, (ov_ox + (overview_w - t_level.get_width()) // 2, hud_y))
        self.screen.blit(t_lives, (ov_ox + overview_w - t_lives.get_width(), hud_y))
        
        return visible_bugs
