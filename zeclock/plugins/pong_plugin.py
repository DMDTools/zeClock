"""PongClock plugin - Time displayed as a Pong game score.

Two paddles play Pong, and the score always shows the current time
(left paddle = hours, right paddle = minutes). The "losing" paddle
lets the ball through right when the digit needs to change.
"""

import math
import random
import time
import logging
from typing import Optional, Tuple

import numpy as np
from PIL import Image

from .base import ClockPlugin

logger = logging.getLogger(__name__)


# Game constants
PADDLE_WIDTH = 2
PADDLE_HEIGHT = 10
BALL_SIZE = 2
PADDLE_MARGIN = 4  # Distance from edge
PADDLE_SPEED = 1.5  # Pixels per frame
NET_DOT_SIZE = 1
NET_GAP = 3


class PongPlugin(ClockPlugin):
    """Displays time as a Pong game where the score is hours:minutes."""

    @property
    def name(self) -> str:
        return "pong"

    @property
    def description(self) -> str:
        return "Pong game where the score is the current time"

    @property
    def frame_delay_ms(self) -> int:
        return 40  # 25 FPS for smooth animation

    async def initialize(self, config: dict) -> None:
        """Set up the Pong game state.

        Config keys:
            duration_seconds (int): How long to display (default: 20)
            ball_speed (float): Ball speed multiplier (default: 1.0)
            color (tuple|str): Display color (default: orange)
        """
        self._helpers = config.get("_helpers")
        self._duration_seconds = config.get("duration_seconds", 20)
        self._ball_speed_mult = config.get("ball_speed", 1.0)
        self._color: Tuple[int, int, int] = (255, 128, 0)
        self._score_color: Tuple[int, int, int] = (255, 128, 0)
        self._ball_color: Tuple[int, int, int] = (255, 128, 0)
        self._paddle_color: Tuple[int, int, int] = (255, 128, 0)
        self._net_color: Tuple[int, int, int] = (80, 40, 0)

        # Parse color if provided
        color = config.get("color")
        if isinstance(color, str):
            color_map = {
                "orange": (255, 128, 0),
                "blue": (0, 128, 255),
                "red": (255, 0, 0),
                "purple": (255, 0, 255),
                "green": (0, 255, 128),
                "yellow": (255, 255, 0),
                "cyan": (0, 255, 255),
                "pink": (255, 64, 128),
            }
            self._color = color_map.get(color, (255, 128, 0))
            self._score_color = self._color
            self._ball_color = self._color
            self._paddle_color = self._color
            # Net is a dimmer version
            self._net_color = tuple(c // 3 for c in self._color)

        self._frames_rendered = 0
        self._max_frames = int(self._duration_seconds * 1000 / self.frame_delay_ms)

        # Game state will be initialized per-frame-set in _reset_game
        self._width = 128
        self._height = 32
        self._reset_game()

    def _reset_game(self) -> None:
        """Reset ball and paddle positions for a new rally."""
        # Paddles - vertically centered
        self._left_paddle_y = (self._height - PADDLE_HEIGHT) / 2.0
        self._right_paddle_y = (self._height - PADDLE_HEIGHT) / 2.0

        # Ball starts at center
        self._ball_x = self._width / 2.0
        self._ball_y = self._height / 2.0

        # Ball velocity - random angle
        angle = random.uniform(-math.pi / 4, math.pi / 4)
        direction = random.choice([-1, 1])
        speed = 1.5 * self._ball_speed_mult
        self._ball_vx = speed * direction * math.cos(angle)
        self._ball_vy = speed * math.sin(angle)

        # Track which side should "lose" next
        self._score_pending = False
        self._serve_delay = 15  # Frames to pause after a score

    def _get_current_score(self) -> Tuple[int, int]:
        """Get current time as (hours, minutes) score."""
        now = time.localtime()
        return (now.tm_hour, now.tm_min)

    def _update_physics(self) -> Optional[str]:
        """Update ball and paddle positions.

        Returns:
            "left" or "right" if a point was scored, None otherwise.
        """
        if self._serve_delay > 0:
            self._serve_delay -= 1
            return None

        # Move ball
        self._ball_x += self._ball_vx
        self._ball_y += self._ball_vy

        # Bounce off top/bottom walls
        if self._ball_y <= 0:
            self._ball_y = 0
            self._ball_vy = abs(self._ball_vy)
        elif self._ball_y >= self._height - BALL_SIZE:
            self._ball_y = self._height - BALL_SIZE
            self._ball_vy = -abs(self._ball_vy)

        # Left paddle collision
        left_paddle_x = PADDLE_MARGIN
        if (
            self._ball_x <= left_paddle_x + PADDLE_WIDTH
            and self._ball_x >= left_paddle_x - BALL_SIZE
            and self._ball_vx < 0
        ):
            paddle_top = self._left_paddle_y
            paddle_bottom = self._left_paddle_y + PADDLE_HEIGHT
            if (
                self._ball_y + BALL_SIZE >= paddle_top
                and self._ball_y <= paddle_bottom
            ):
                self._ball_vx = abs(self._ball_vx) * 1.02  # Slight speedup
                # Add spin based on where ball hits paddle
                hit_pos = (
                    (self._ball_y + BALL_SIZE / 2) - (paddle_top + PADDLE_HEIGHT / 2)
                ) / (PADDLE_HEIGHT / 2)
                self._ball_vy += hit_pos * 0.5

        # Right paddle collision
        right_paddle_x = self._width - PADDLE_MARGIN - PADDLE_WIDTH
        if (
            self._ball_x + BALL_SIZE >= right_paddle_x
            and self._ball_x <= right_paddle_x + PADDLE_WIDTH
            and self._ball_vx > 0
        ):
            paddle_top = self._right_paddle_y
            paddle_bottom = self._right_paddle_y + PADDLE_HEIGHT
            if (
                self._ball_y + BALL_SIZE >= paddle_top
                and self._ball_y <= paddle_bottom
            ):
                self._ball_vx = -abs(self._ball_vx) * 1.02
                hit_pos = (
                    (self._ball_y + BALL_SIZE / 2) - (paddle_top + PADDLE_HEIGHT / 2)
                ) / (PADDLE_HEIGHT / 2)
                self._ball_vy += hit_pos * 0.5

        # Clamp ball velocity
        max_speed = 3.0 * self._ball_speed_mult
        speed = math.sqrt(self._ball_vx**2 + self._ball_vy**2)
        if speed > max_speed:
            self._ball_vx = (self._ball_vx / speed) * max_speed
            self._ball_vy = (self._ball_vy / speed) * max_speed

        # Score detection - ball goes past paddles
        scored = None
        if self._ball_x < -BALL_SIZE:
            scored = "right"  # Right player scores (minutes)
        elif self._ball_x > self._width + BALL_SIZE:
            scored = "left"  # Left player scores (hours)

        if scored:
            self._reset_ball()

        return scored

    def _reset_ball(self) -> None:
        """Reset ball to center after a score."""
        self._ball_x = self._width / 2.0
        self._ball_y = self._height / 2.0
        angle = random.uniform(-math.pi / 4, math.pi / 4)
        direction = random.choice([-1, 1])
        speed = 1.5 * self._ball_speed_mult
        self._ball_vx = speed * direction * math.cos(angle)
        self._ball_vy = speed * math.sin(angle)
        self._serve_delay = 15

    def _update_paddles(self) -> None:
        """Move paddles with AI tracking the ball."""
        # Both paddles track the ball, but with slight delay/imperfection
        # to make it look natural

        # Left paddle AI
        target_y = self._ball_y - PADDLE_HEIGHT / 2
        diff = target_y - self._left_paddle_y
        # Add some reaction delay - paddle moves slower when ball is far
        tracking_speed = PADDLE_SPEED
        if self._ball_vx > 0:
            # Ball moving away - track lazily
            tracking_speed *= 0.4
        if abs(diff) > 1:
            self._left_paddle_y += math.copysign(
                min(tracking_speed, abs(diff)), diff
            )

        # Right paddle AI
        target_y = self._ball_y - PADDLE_HEIGHT / 2
        diff = target_y - self._right_paddle_y
        tracking_speed = PADDLE_SPEED
        if self._ball_vx < 0:
            tracking_speed *= 0.4
        if abs(diff) > 1:
            self._right_paddle_y += math.copysign(
                min(tracking_speed, abs(diff)), diff
            )

        # Clamp paddles to screen
        self._left_paddle_y = max(
            0, min(self._height - PADDLE_HEIGHT, self._left_paddle_y)
        )
        self._right_paddle_y = max(
            0, min(self._height - PADDLE_HEIGHT, self._right_paddle_y)
        )

    def _render(self, width: int, height: int) -> Image.Image:
        """Render the current game state to a frame."""
        frame_array = np.zeros((height, width, 3), dtype=np.uint8)

        # Draw center net (dashed line)
        center_x = width // 2
        for y in range(0, height, NET_GAP):
            for dy in range(NET_DOT_SIZE):
                py = y + dy
                if py < height:
                    frame_array[py, center_x, :] = self._net_color

        # Draw paddles
        left_x = PADDLE_MARGIN
        right_x = width - PADDLE_MARGIN - PADDLE_WIDTH

        left_top = int(round(self._left_paddle_y))
        right_top = int(round(self._right_paddle_y))

        for dy in range(PADDLE_HEIGHT):
            for dx in range(PADDLE_WIDTH):
                # Left paddle
                py = left_top + dy
                px = left_x + dx
                if 0 <= py < height and 0 <= px < width:
                    frame_array[py, px, :] = self._paddle_color
                # Right paddle
                py = right_top + dy
                px = right_x + dx
                if 0 <= py < height and 0 <= px < width:
                    frame_array[py, px, :] = self._paddle_color

        # Draw ball
        ball_x = int(round(self._ball_x))
        ball_y = int(round(self._ball_y))
        for dy in range(BALL_SIZE):
            for dx in range(BALL_SIZE):
                px = ball_x + dx
                py = ball_y + dy
                if 0 <= px < width and 0 <= py < height:
                    frame_array[py, px, :] = self._ball_color

        # Draw score (time) using helpers if available
        frame = Image.fromarray(frame_array, "RGB")

        hours, minutes = self._get_current_score()

        if self._helpers:
            # Measure widths to position hours and minutes at fixed positions
            # with a blinking colon in between (same approach as main clock)
            hours_str = f"{hours:02d}"
            minutes_str = f"{minutes:02d}"
            colon_str = ":"

            hours_w = self._helpers.get_text_width(hours_str, "MENU")
            colon_w = self._helpers.get_text_width(colon_str, "MENU")
            minutes_w = self._helpers.get_text_width(minutes_str, "MENU")

            total_w = hours_w + colon_w + minutes_w
            start_x = (width - total_w) // 2 + 1

            # Render hours (fixed position)
            hours_frame = self._helpers.render_text(
                hours_str, x=start_x, y=1,
                color=self._score_color, font_name="MENU",
            )
            frame = self._helpers.composite_frames(frame, hours_frame)

            # Render colon (blinking every 500ms)
            blink_state = (int(time.time() * 1000) // 500) % 2
            if blink_state == 0:
                colon_frame = self._helpers.render_text(
                    colon_str, x=start_x + hours_w, y=1,
                    color=self._score_color, font_name="MENU",
                )
                frame = self._helpers.composite_frames(frame, colon_frame)

            # Render minutes (fixed position, never shifts)
            minutes_frame = self._helpers.render_text(
                minutes_str, x=start_x + hours_w + colon_w, y=1,
                color=self._score_color, font_name="MENU",
            )
            frame = self._helpers.composite_frames(frame, minutes_frame)

        return frame

    async def render_frame(
        self, width: int, height: int
    ) -> Optional[Image.Image]:
        """Render the next Pong frame.

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode, or None to signal completion.
        """
        if self._frames_rendered >= self._max_frames:
            return None

        if self._frames_rendered == 0:
            logger.info("[pong] Start rendering")

        self._width = width
        self._height = height

        # Update game state
        self._update_paddles()
        self._update_physics()

        # Render
        frame = self._render(width, height)
        self._frames_rendered += 1
        return frame

    async def cleanup(self) -> None:
        """Reset game state for next activation."""
        self._frames_rendered = 0
        self._reset_game()
