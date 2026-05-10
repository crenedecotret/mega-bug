"""Mega-Bug Modern — Player and Bug entities."""
import math
import random
from enum import Enum, auto
from typing import Optional, Tuple, List
from .settings import CFG
from .engine import Maze, HeatMap, astar, Position


Direction = Tuple[int, int]
DIR_NONE: Direction = (0, 0)
DIR_UP: Direction = (0, -1)
DIR_DOWN: Direction = (0, 1)
DIR_LEFT: Direction = (-1, 0)
DIR_RIGHT: Direction = (1, 0)


class Player:
    """Grid-snapped player with input buffering."""

    def __init__(self, x: int, y: int):
        self.gx = float(x) + 0.5
        self.gy = float(y) + 0.5
        self.cell_x = x
        self.cell_y = y
        self.facing: Direction = DIR_RIGHT
        self.next_dir: Optional[Direction] = None
        self.buffer_timer: float = 0.0
        self.alive = True
        self.dead_timer: float = 0.0
        self.walk_phase = 0.0  # continuous 0-2π for leg animation
        self._last_gx = self.gx
        self._last_gy = self.gy

    @property
    def pos(self) -> Position:
        return (int(math.floor(self.gx)), int(math.floor(self.gy)))

    @property
    def pixel_pos(self) -> Tuple[float, float]:
        return (
            self.gx * CFG.CELL_SIZE,
            self.gy * CFG.CELL_SIZE,
        )

    def request_turn(self, direction: Direction) -> None:
        """Buffer a turn request."""
        if direction != self.facing:
            self.next_dir = direction
            self.buffer_timer = CFG.INPUT_BUFFER_SEC

    def predict_pos(self, seconds: float) -> Position:
        """Predict grid position after `seconds` continuing current facing."""
        dx, dy = self.facing
        dist = CFG.PLAYER_SPEED * seconds
        return (
            int(math.floor(self.gx + dx * dist)),
            int(math.floor(self.gy + dy * dist)),
        )

    def update(self, dt: float, maze: Maze) -> None:
        if not self.alive:
            self.dead_timer += dt
            return

        # Decay buffer
        if self.buffer_timer > 0:
            self.buffer_timer -= dt
            if self.buffer_timer <= 0:
                self.buffer_timer = 0.0
                self.next_dir = None

        dx, dy = self.facing
        speed = CFG.PLAYER_SPEED * dt
        new_gx = self.gx + dx * speed
        new_gy = self.gy + dy * speed

        # Try buffered turn at intersection center
        if self.next_dir is not None:
            ndx, ndy = self.next_dir
            # Check if near center of current cell
            cx = self.cell_x + 0.5
            cy = self.cell_y + 0.5
            near_cx = abs(self.gx - cx) < 0.3
            near_cy = abs(self.gy - cy) < 0.3
            if near_cx and near_cy:
                # Is the new direction valid?
                nx = self.cell_x + ndx
                ny = self.cell_y + ndy
                if maze.is_floor(nx, ny):
                    self.facing = self.next_dir
                    self.next_dir = None
                    self.buffer_timer = 0.0
                    dx, dy = self.facing
                    new_gx = cx + dx * 0.5
                    new_gy = cy + dy * 0.5

        # Wall collision / snapping
        if maze.is_wall(int(math.floor(new_gx)), int(math.floor(new_gy))):
            # Snap to center and stop completely
            self.gx = self.cell_x + 0.5
            self.gy = self.cell_y + 0.5
            self.facing = DIR_NONE
            return

        self.gx = new_gx
        self.gy = new_gy
        self.cell_x = int(math.floor(self.gx))
        self.cell_y = int(math.floor(self.gy))

        # Animate legs based on distance traveled
        dist = math.hypot(self.gx - self._last_gx, self.gy - self._last_gy)
        self._last_gx = self.gx
        self._last_gy = self.gy
        if dist > 0.01:
            self.walk_phase = (self.walk_phase + dist * 4.0) % (2 * math.pi)


class BugPersonality(Enum):
    """Pac-Man style ghost personalities."""
    CHASER = 0      # Blinky: direct to player
    AMBUSHER = 1    # Pinky: ahead of player
    FLANKER = 2     # Inky: relative flank using other bug positions
    HEATER = 3      # Clyde: heat trail, scatter when far


class BugState(Enum):
    CHASE = auto()
    SCATTER = auto()


class Bug:
    """Bug with Pac-Man style personalities: chase/scatter cycle, unique targets."""

    def __init__(
        self,
        x: int,
        y: int,
        bug_id: int = 0,
        speed: float = 2.5,
        chase_dur: float = 5.0,
        scatter_dur: float = 7.0,
        replan_interval: float = 3.0,
        predict_ahead: int = 1,
    ):
        self.gx = float(x) + 0.5
        self.gy = float(y) + 0.5
        self.cell_x = x
        self.cell_y = y
        self.bug_id = bug_id
        self.speed = speed
        self.chase_dur = chase_dur
        self.scatter_dur = scatter_dur
        self.replan_interval = replan_interval
        self.predict_ahead = predict_ahead
        self.personality = BugPersonality(bug_id % 4)
        self.state = BugState.CHASE
        self.mode_timer = 0.0
        self.path: List[Position] = []
        self.path_index = 0
        self.replan_timer = 0.0
        self.stuck_timer = 0.0
        self.last_pos: Position = (x, y)
        self.last_target: Optional[Position] = None
        # Scatter corners (one per bug personality)
        self.scatter_target: Position = (1, 1)

    @property
    def pos(self) -> Position:
        return (int(math.floor(self.gx)), int(math.floor(self.gy)))

    @property
    def pixel_pos(self) -> Tuple[float, float]:
        return (self.gx * CFG.CELL_SIZE, self.gy * CFG.CELL_SIZE)

    def _distance_to(self, target: Position) -> float:
        return math.hypot(self.cell_x - target[0], self.cell_y - target[1])

    def _snap_to_center(self, cx: int, cy: int) -> None:
        self.gx = cx + 0.5
        self.gy = cy + 0.5
        self.cell_x = cx
        self.cell_y = cy

    def _step_along_path(self, dt: float, maze: Maze) -> None:
        if not self.path or self.path_index >= len(self.path):
            return

        # Skip waypoints that are our current cell (replan artifact)
        while self.path_index < len(self.path):
            wx, wy = self.path[self.path_index]
            if wx == self.cell_x and wy == self.cell_y:
                self.path_index += 1
            else:
                break

        if self.path_index >= len(self.path):
            self.path = []
            self.path_index = 0
            return

        # Current target cell center
        tx, ty = self.path[self.path_index]
        tcx = tx + 0.5
        tcy = ty + 0.5

        dx = tcx - self.gx
        dy = tcy - self.gy
        dist = math.hypot(dx, dy)
        speed = self.speed * dt

        if dist < speed:
            # Reached cell center — snap and advance
            self._snap_to_center(tx, ty)
            self.path_index += 1
            if self.path_index >= len(self.path):
                self.path = []
                self.path_index = 0
        else:
            # Move toward target cell center
            self.gx += dx / dist * speed
            self.gy += dy / dist * speed
            # Update cell from center position
            self.cell_x = int(math.floor(self.gx))
            self.cell_y = int(math.floor(self.gy))
            # If we somehow entered a wall, snap back
            if maze.is_wall(self.cell_x, self.cell_y):
                self._snap_to_center(self.cell_x, self.cell_y)

    def _pick_chase_target(self, maze: Maze, heat: HeatMap, player: Player, other_bugs: List["Bug"]) -> Position:
        """Return target tile based on bug personality."""
        px, py = player.cell_x, player.cell_y
        pf = player.facing
        w, h = maze.w, maze.h

        # Clamp helper
        def clamp(t: Position) -> Position:
            cx, cy = t
            cx = max(0, min(w - 1, cx))
            cy = max(0, min(h - 1, cy))
            if maze.is_wall(cx, cy):
                # find nearest floor
                floors = maze.neighbors((cx, cy))
                if floors:
                    return floors[0]
                return (px, py)
            return (cx, cy)

        if self.personality == BugPersonality.CHASER:
            # Blinky: direct chase to player
            return (px, py)

        elif self.personality == BugPersonality.AMBUSHER:
            # Pinky: ahead of player
            if pf != DIR_NONE and player.alive:
                # Look ahead along player's facing direction
                ahead = self.predict_ahead  # cells ahead
                tx = px + pf[0] * ahead
                ty = py + pf[1] * ahead
            else:
                tx, ty = px, py
            return clamp((tx, ty))

        elif self.personality == BugPersonality.FLANKER:
            # Inky: flank using another bug as reference
            # Target = player + (player - nearest_other_bug) * 0.5
            # This creates a pincer from the other side
            if other_bugs:
                nearest = min(other_bugs, key=lambda b: b._distance_to((px, py)))
                nx, ny = nearest.cell_x, nearest.cell_y
                tx = px + (px - nx)
                ty = py + (py - ny)
            else:
                tx, ty = px + 4, py  # default flank right
            return clamp((tx, ty))

        elif self.personality == BugPersonality.HEATER:
            # Clyde: follow heat, but target player directly if close
            dist = self._distance_to((px, py))
            if dist < 8.0:
                return (px, py)
            heat_goal = heat.max_heat_pos(self.pos, radius=12)
            if heat_goal and self._distance_to(heat_goal) < 20.0:
                return heat_goal
            return (px, py)

        return (px, py)

    def _set_scatter_corner(self, maze: Maze) -> None:
        """Assign each bug a different corner for scatter mode."""
        corners = [
            (1, 1),                    # top-left
            (maze.w - 2, 1),           # top-right
            (1, maze.h - 2),           # bottom-left
            (maze.w - 2, maze.h - 2),  # bottom-right
        ]
        idx = self.bug_id % len(corners)
        self.scatter_target = corners[idx]

    def _find_valid_target(self, maze: Maze, raw_target: Position) -> Position:
        """Ensure target is a valid floor cell."""
        if not maze.is_wall(*raw_target):
            return raw_target
        floors = maze.neighbors(raw_target)
        if floors:
            return floors[0]
        floors = maze.floor_cells()
        if floors:
            return min(floors, key=lambda p: maze.distance(p, raw_target))
        return (1, 1)

    def update(self, dt: float, maze: Maze, heat: HeatMap, player: Player, other_bugs: List["Bug"]) -> None:
        self.mode_timer -= dt
        self.replan_timer -= dt
        self.stuck_timer += dt

        # Toggle chase/scatter
        mode_changed = False
        if self.mode_timer <= 0:
            if self.state == BugState.CHASE:
                self.state = BugState.SCATTER
                self.mode_timer = self.scatter_dur
                self._set_scatter_corner(maze)
            else:
                self.state = BugState.CHASE
                self.mode_timer = self.chase_dur
            mode_changed = True
            self.path = []
            self.path_index = 0

        # Detect stuck (not moving for 1.0s)
        if self.pos != self.last_pos:
            self.stuck_timer = 0.0
            self.last_pos = self.pos
        elif self.stuck_timer > 1.0:
            self.path = []
            self.path_index = 0
            self.stuck_timer = 0.0

        # Determine current goal
        if self.state == BugState.SCATTER:
            goal = self.scatter_target
        else:
            goal = self._pick_chase_target(maze, heat, player, other_bugs)
        goal = self._find_valid_target(maze, goal)

        # Replan if:
        #  - mode just changed
        #  - no path or path exhausted
        #  - target moved by >2 cells from last_target
        #  - periodic replan (every 2.0s) as safety net
        #  - stuck
        target_changed = (self.last_target is None or
                          maze.distance(self.last_target, goal) > 2)
        need_replan = (
            mode_changed or
            not self.path or self.path_index >= len(self.path) or
            target_changed or
            self.replan_timer <= 0 or
            self.stuck_timer > 0.5
        )

        if need_replan:
            self.replan_timer = self.replan_interval
            self.last_target = goal
            # Use next intended cell as start, not current floor pos
            # This avoids backtracking when replanning mid-corridor
            start = self.pos
            if self.path and self.path_index < len(self.path):
                # If we have a path, try to keep forward momentum:
                # use the next waypoint we're heading to as start
                ahead = self.path[self.path_index]
                if ahead != start:
                    start = ahead

            self.path = astar(maze, start, goal) or []
            self.path_index = 0

            # Fallback: greedy neighbor step toward goal
            if not self.path:
                neighbors = maze.neighbors(start)
                if neighbors:
                    best = min(neighbors, key=lambda p: maze.distance(p, goal))
                    self.path = [best]
                    self.path_index = 0

        self._step_along_path(dt, maze)
