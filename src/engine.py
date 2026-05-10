"""Mega-Bug Modern — Maze generation, pathfinding, heat map."""
import random
import heapq
from typing import Dict, List, Tuple, Optional, Set
from .settings import CFG


Position = Tuple[int, int]


class Maze:
    """31x31 recursive-backtracker maze with wall/floor grid."""

    def __init__(self, width: int = CFG.GRID_W, height: int = CFG.GRID_H):
        self.w = width
        self.h = height
        # grid[y][x]: True = wall, False = floor
        self.grid: List[List[bool]] = [[True for _ in range(width)] for _ in range(height)]
        self.dots: Set[Position] = set()
        self._generate()
        self._place_dots()

    def _generate(self) -> None:
        """Recursive Backtracker on odd coordinates with braiding for loops."""
        stack: List[Position] = []
        start = (1, 1)
        self.grid[start[1]][start[0]] = False
        stack.append(start)
        directions = [(0, -2), (0, 2), (-2, 0), (2, 0)]

        while stack:
            x, y = stack[-1]
            random.shuffle(directions)
            moved = False
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if 0 < nx < self.w - 1 and 0 < ny < self.h - 1 and self.grid[ny][nx]:
                    self.grid[ny][nx] = False
                    self.grid[y + dy // 2][x + dx // 2] = False
                    stack.append((nx, ny))
                    moved = True
                    break
            if not moved:
                stack.pop()

        # Braid: remove ~15% of walls between adjacent floor cells to create loops
        self._add_loops(ratio=0.15)

    def _add_loops(self, ratio: float = 0.15) -> None:
        """Remove walls to create evenly-distributed narrow alternate paths."""
        # Find walls between two floor cells (potential passages)
        candidates = []
        for y in range(1, self.h - 1):
            for x in range(1, self.w - 1):
                if self.grid[y][x]:
                    if not self.grid[y][x - 1] and not self.grid[y][x + 1]:
                        candidates.append((x, y))
                    elif not self.grid[y - 1][x] and not self.grid[y + 1][x]:
                        candidates.append((x, y))

        to_remove = int(len(candidates) * ratio)
        removed = 0
        removed_set = set()

        def _dist_to_removed(x, y):
            if not removed_set:
                return float('inf')
            return min(abs(x - rx) + abs(y - ry) for (rx, ry) in removed_set)

        while removed < to_remove and candidates:
            # Pick candidate farthest from existing openings for even spread
            best = max(candidates, key=lambda p: _dist_to_removed(p[0], p[1]))
            candidates.remove(best)
            x, y = best

            # Reject walls whose removal would create a 2x2 open block (double-wide)
            would_widen = False
            for dy in (-1, 0):
                for dx in (-1, 0):
                    bx, by = x + dx, y + dy
                    if 0 <= bx < self.w - 1 and 0 <= by < self.h - 1:
                        floors = sum(
                            1 for j in (0, 1) for i in (0, 1)
                            if not self.grid[by + j][bx + i]
                        )
                        if floors == 3:
                            would_widen = True
                            break
                if would_widen:
                    break
            if not would_widen:
                self.grid[y][x] = False
                removed_set.add(best)
                removed += 1

    def _place_dots(self) -> None:
        """Place pellets in every floor cell."""
        for y in range(self.h):
            for x in range(self.w):
                if not self.grid[y][x]:
                    self.dots.add((x, y))

    def is_wall(self, x: int, y: int) -> bool:
        if not (0 <= x < self.w and 0 <= y < self.h):
            return True
        return self.grid[y][x]

    def is_floor(self, x: int, y: int) -> bool:
        return not self.is_wall(x, y)

    def floor_cells(self) -> List[Position]:
        """Return all floor cell coordinates."""
        result = []
        for y in range(self.h):
            for x in range(self.w):
                if not self.grid[y][x]:
                    result.append((x, y))
        return result

    def neighbors(self, pos: Position) -> List[Position]:
        """Valid floor neighbors (cardinal)."""
        x, y = pos
        result = []
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            if self.is_floor(nx, ny):
                result.append((nx, ny))
        return result

    def distance(self, a: Position, b: Position) -> int:
        """Manhattan distance."""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])


def astar(maze: Maze, start: Position, goal: Position) -> Optional[List[Position]]:
    """A* pathfinding on the maze grid."""
    if maze.is_wall(*start) or maze.is_wall(*goal):
        return None
    if start == goal:
        return [start]

    open_set: List[Tuple[int, int, Position]] = []
    heapq.heappush(open_set, (0, 0, start))
    came_from: Dict[Position, Position] = {}
    g_score: Dict[Position, float] = {start: 0.0}
    counter = 1

    while open_set:
        _, _, current = heapq.heappop(open_set)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        for neighbor in maze.neighbors(current):
            tentative = g_score[current] + 1.0
            if neighbor not in g_score or tentative < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                f = tentative + maze.distance(neighbor, goal)
                heapq.heappush(open_set, (f, counter, neighbor))
                counter += 1
    return None


class HeatMap:
    """Scent/heat grid that decays over time."""

    def __init__(self, width: int = CFG.GRID_W, height: int = CFG.GRID_H):
        self.w = width
        self.h = height
        self.map: List[List[float]] = [[0.0 for _ in range(width)] for _ in range(height)]

    def add_heat(self, x: int, y: int, amount: float = CFG.SCENT_ADD) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.map[y][x] = min(1.0, self.map[y][x] + amount)

    def decay(self, rate: float = CFG.SCENT_DECAY) -> None:
        for y in range(self.h):
            for x in range(self.w):
                self.map[y][x] = max(0.0, self.map[y][x] - rate)

    def get(self, x: int, y: int) -> float:
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.map[y][x]
        return 0.0

    def max_heat_pos(self, center: Position, radius: int = 5) -> Optional[Position]:
        """Return the highest heat cell within radius of center."""
        cx, cy = center
        best: Optional[Position] = None
        best_val = -1.0
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.w and 0 <= ny < self.h:
                    v = self.map[ny][nx]
                    if v > best_val:
                        best_val = v
                        best = (nx, ny)
        return best if best_val > 0.01 else None

    def gradient_step(self, pos: Position) -> Optional[Position]:
        """Return the neighbor with highest heat (for simple scent follow)."""
        x, y = pos
        best: Optional[Position] = None
        best_val = self.get(x, y)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            v = self.get(nx, ny)
            if v > best_val:
                best_val = v
                best = (nx, ny)
        return best
