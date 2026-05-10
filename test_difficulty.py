"""Test suite for Mega-Bug Modern difficulty scaling."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import sys
sys.path.insert(0, os.path.dirname(__file__))

import pygame
pygame.init()
pygame.mixer.init()

from src.main import Game


def test_difficulty_scaling():
    """Verify difficulty params scale correctly across levels."""
    game = Game()

    levels = [1, 2, 3, 5, 10, 15, 20]
    results = []

    for level in levels:
        game.level = level
        diff = game._difficulty_params()
        results.append((level, diff))

    # Assertions
    print("=" * 60)
    print("DIFFICULTY SCALING TEST RESULTS")
    print("=" * 60)

    all_pass = True

    for level, diff in results:
        print(f"\nLevel {level}:")
        print(f"  Bug count:     {diff['bug_count']}")
        print(f"  Bug speed:     {diff['bug_speed']:.2f}")
        print(f"  Chase dur:     {diff['chase_dur']:.1f}s")
        print(f"  Scatter dur:   {diff['scatter_dur']:.1f}s")
        print(f"  Replan:        {diff['replan_interval']:.1f}s")
        print(f"  Predict ahead: {diff['predict_ahead']} cells")

        # Check bug count: 3 at level 1, +1 per level
        expected_count = 3 + (level - 1)
        if diff['bug_count'] != expected_count:
            print(f"  FAIL: bug_count should be {expected_count}, got {diff['bug_count']}")
            all_pass = False

        # Check speed caps at 3.8
        expected_speed = min(3.8, 2.5 + (level - 1) * 0.15)
        if abs(diff['bug_speed'] - expected_speed) > 0.001:
            print(f"  FAIL: bug_speed should be {expected_speed:.2f}, got {diff['bug_speed']:.2f}")
            all_pass = False

        # Check chase caps at 12
        if diff['chase_dur'] > 12.0:
            print(f"  FAIL: chase_dur should not exceed 12.0")
            all_pass = False

        # Check scatter floors at 2
        if diff['scatter_dur'] < 2.0:
            print(f"  FAIL: scatter_dur should not go below 2.0")
            all_pass = False

        # Check replan floors at 1
        if diff['replan_interval'] < 1.0:
            print(f"  FAIL: replan_interval should not go below 1.0")
            all_pass = False

        # Check predict caps at 3
        if diff['predict_ahead'] > 3:
            print(f"  FAIL: predict_ahead should not exceed 3")
            all_pass = False

    # Monotonic checks
    print("\n" + "=" * 60)
    print("MONOTONIC CHECKS")
    print("=" * 60)

    counts = [r['bug_count'] for _, r in results]
    speeds = [r['bug_speed'] for _, r in results]
    chases = [r['chase_dur'] for _, r in results]
    scatters = [r['scatter_dur'] for _, r in results]
    replans = [r['replan_interval'] for _, r in results]
    predicts = [r['predict_ahead'] for _, r in results]

    # Bug count should be non-decreasing
    for i in range(len(counts) - 1):
        if counts[i] > counts[i + 1]:
            print(f"FAIL: bug_count decreased from L{levels[i]} ({counts[i]}) to L{levels[i+1]} ({counts[i+1]})")
            all_pass = False

    # Speed should be non-decreasing
    for i in range(len(speeds) - 1):
        if speeds[i] > speeds[i + 1] + 0.001:
            print(f"FAIL: bug_speed decreased from L{levels[i]} ({speeds[i]:.2f}) to L{levels[i+1]} ({speeds[i+1]:.2f})")
            all_pass = False

    # Chase should be non-decreasing
    for i in range(len(chases) - 1):
        if chases[i] > chases[i + 1] + 0.001:
            print(f"FAIL: chase_dur decreased from L{levels[i]} ({chases[i]:.1f}) to L{levels[i+1]} ({chases[i+1]:.1f})")
            all_pass = False

    # Scatter should be non-increasing
    for i in range(len(scatters) - 1):
        if scatters[i] < scatters[i + 1] - 0.001:
            print(f"FAIL: scatter_dur increased from L{levels[i]} ({scatters[i]:.1f}) to L{levels[i+1]} ({scatters[i+1]:.1f})")
            all_pass = False

    # Replan should be non-increasing
    for i in range(len(replans) - 1):
        if replans[i] < replans[i + 1] - 0.001:
            print(f"FAIL: replan_interval increased from L{levels[i]} ({replans[i]:.1f}) to L{levels[i+1]} ({replans[i+1]:.1f})")
            all_pass = False

    # Predict should be non-decreasing
    for i in range(len(predicts) - 1):
        if predicts[i] > predicts[i + 1]:
            print(f"FAIL: predict_ahead decreased from L{levels[i]} ({predicts[i]}) to L{levels[i+1]} ({predicts[i+1]})")
            all_pass = False

    if all_pass:
        print("\n*** ALL TESTS PASSED ***")
    else:
        print("\n*** SOME TESTS FAILED ***")
        sys.exit(1)

    # Spawn check: verify actual bug count matches expected
    print("\n" + "=" * 60)
    print("SPAWN CHECKS")
    print("=" * 60)
    for level in [1, 3, 5, 10]:
        game.level = level
        game.new_level()
        expected = 3 + (level - 1)
        actual = len(game.bugs)
        status = "PASS" if actual == expected else "FAIL"
        print(f"  Level {level}: spawned {actual} bugs (expected {expected}) [{status}]")
        if actual != expected:
            all_pass = False

    # Verify bug speed and AI params are set on instances
    bug = game.bugs[0]
    print(f"\n  Sample bug params (level 10):")
    print(f"    speed: {bug.speed:.2f}")
    print(f"    chase_dur: {bug.chase_dur:.1f}s")
    print(f"    scatter_dur: {bug.scatter_dur:.1f}s")
    print(f"    replan_interval: {bug.replan_interval:.1f}s")
    print(f"    predict_ahead: {bug.predict_ahead}")

    if all_pass:
        print("\n*** ALL SPAWN CHECKS PASSED ***")
    else:
        print("\n*** SOME SPAWN CHECKS FAILED ***")
        sys.exit(1)

    pygame.quit()
    return True


if __name__ == "__main__":
    test_difficulty_scaling()
