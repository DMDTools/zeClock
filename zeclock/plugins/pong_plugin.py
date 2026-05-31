"""PongPlugin - Animated Pong game on the DMD.

Two AI paddles play Pong with real scoring. Each paddle has human-like
imperfections: reaction delay, limited speed, and occasional misjudgment.
The ball speeds up after each rally. The game resets with a confetti
celebration after one side reaches 5 points.

The match persists across plugin activations — the clock only takes over
between points (during serve pause), so the game is never interrupted
mid-rally.
"""

import math
import random
import time
import logging
from typing import Optional, Tuple

from PIL import Image, ImageDraw

from .base import ClockPlugin
from .helpers import ConfettiAnimation, CONFETTI_COLORS_PARTY, CONFETTI_COLORS_WARM
from ..colors import COLOR_MAP

logger = logging.getLogger(__name__)


# Game constants (base values for 128x32, scaled at runtime)
PADDLE_WIDTH = 2
PADDLE_HEIGHT = 10
BALL_SIZE = 2
PADDLE_MARGIN = 4  # Distance from edge
NET_DOT_SIZE = 1
NET_GAP = 3
MAX_SCORE = 5  # Points to win a game


class PongPlugin(ClockPlugin):
    """Animated Pong game with real scoring and human-like AI.

    The match state (scores, ball, paddles) persists across activations.
    The plugin only yields back to the clock between points, never mid-rally.
    When a side reaches 5 points, a confetti celebration plays before reset.
    """

    # Class-level persistent game state (survives across activations)
    _left_score: int = 0
    _right_score: int = 0
    _rally_count: int = 0
    _ball_x: float = 64.0
    _ball_y: float = 16.0
    _ball_vx: float = 0.0
    _ball_vy: float = 0.0
    _left_paddle_y: float = 11.0
    _right_paddle_y: float = 11.0
    _serve_delay: int = 20
    _game_initialized: bool = False
    _celebrating: bool = False
    _celebration_start: float = 0.0
    _celebration_duration: float = 3.5
    _confetti_anim: Optional["ConfettiAnimation"] = None
    _last_scorer: str = ""  # "left" or "right" — serves toward the scorer
    _winner: str = ""  # "left" or "right" during match-win celebration

    @property
    def name(self) -> str:
        return "pong"

    @property
    def description(self) -> str:
        return "Pong game with real scoring and human-like AI"

    @property
    def frame_delay_ms(self) -> int:
        return 33  # ~30 FPS for smooth action

    async def initialize(self, config: dict) -> None:
        """Set up the Pong game state.

        Config keys:
            duration_seconds (int): Max display time per activation (default: 30)
            ball_speed (float): Initial ball speed multiplier (default: 1.0)
            color (tuple|str): Display color (default: orange)
        """
        self._helpers = config.get("_helpers")
        self._duration_seconds = config.get("duration_seconds", 30)
        self._ball_speed_mult = config.get("ball_speed", 1.0)
        self._color: Tuple[int, int, int] = (255, 128, 0)
        self._score_color: Tuple[int, int, int] = (255, 128, 0)
        self._ball_color: Tuple[int, int, int] = (255, 255, 255)
        self._paddle_color: Tuple[int, int, int] = (255, 128, 0)
        self._net_color: Tuple[int, int, int] = (60, 30, 0)

        # Parse color if provided
        color = config.get("color")
        if isinstance(color, str):
            resolved = COLOR_MAP.get(color)
            if resolved:
                self._color = resolved
                self._score_color = resolved
                self._paddle_color = resolved
                self._net_color = (
                    resolved[0] // 4,
                    resolved[1] // 4,
                    resolved[2] // 4,
                )
                self._ball_color = (255, 255, 255)

        self._frames_rendered = 0
        self._max_frames = int(self._duration_seconds * 1000 / self.frame_delay_ms)
        self._point_scored_this_activation = False

        # Display dimensions — get from helpers if available
        self._width = 128
        self._height = 32
        if self._helpers:
            self._width = self._helpers.width
            self._height = self._helpers.height

        # Scale factors
        self._scale_x = self._width / 128
        self._scale_y = self._height / 32
        self._paddle_width = max(2, int(PADDLE_WIDTH * self._scale_x))
        self._paddle_height = max(6, int(PADDLE_HEIGHT * self._scale_y))
        self._ball_size = max(2, int(BALL_SIZE * min(self._scale_x, self._scale_y)))
        self._paddle_margin = int(PADDLE_MARGIN * self._scale_x)

        # AI personality (randomized per game for variety)
        if not PongPlugin._game_initialized:
            self._new_ai_personalities()
            self._serve_new_ball()
            PongPlugin._game_initialized = True

        # AI internal state (per-activation, not persistent)
        self._left_target_y = PongPlugin._left_paddle_y
        self._right_target_y = PongPlugin._right_paddle_y
        self._left_last_react_time = 0.0
        self._right_last_react_time = 0.0

        # Score flash animation
        self._score_flash_until = 0.0

    def _new_ai_personalities(self) -> None:
        """Randomize AI personalities for a new game."""
        self._left_reaction_delay = random.uniform(0.4, 0.8)
        self._right_reaction_delay = random.uniform(0.4, 0.8)
        self._left_max_speed = random.uniform(1.2, 1.8)
        self._right_max_speed = random.uniform(1.2, 1.8)
        # Prediction error scales with display height so misses happen equally
        # on SD (32px) and HD (64px)
        self._left_error = random.uniform(3.0, 7.0) * self._scale_y
        self._right_error = random.uniform(3.0, 7.0) * self._scale_y

    def _serve_new_ball(self) -> None:
        """Reset ball to center, serving toward the last scorer's side."""
        PongPlugin._ball_x = self._width / 2.0
        PongPlugin._ball_y = self._height / 2.0

        angle = random.uniform(-math.pi / 5, math.pi / 5)
        # Serve toward the scorer: left scored → ball goes left (reward)
        if PongPlugin._last_scorer == "left":
            direction = -1
        elif PongPlugin._last_scorer == "right":
            direction = 1
        else:
            direction = random.choice([-1, 1])
        # Speed scales with display width to maintain same crossing time
        base_speed = 1.6 * self._ball_speed_mult * self._scale_x
        speed = base_speed * (1.0 + PongPlugin._rally_count * 0.05)
        PongPlugin._ball_vx = speed * direction * math.cos(angle)
        PongPlugin._ball_vy = speed * math.sin(angle) * self._scale_y
        PongPlugin._serve_delay = 20
        PongPlugin._rally_count = 0

    def _reset_game(self) -> None:
        """Reset scores and start a new game."""
        PongPlugin._left_score = 0
        PongPlugin._right_score = 0
        PongPlugin._rally_count = 0
        PongPlugin._celebrating = False
        PongPlugin._confetti_anim = None
        PongPlugin._last_scorer = ""
        PongPlugin._winner = ""
        self._new_ai_personalities()
        self._serve_new_ball()

    def _start_celebration(self, is_match_win: bool = False) -> None:
        """Start confetti celebration.

        Args:
            is_match_win: If True, big celebration (match over). If False, small point celebration.
        """
        PongPlugin._celebrating = True
        PongPlugin._celebration_start = time.time()

        confetti = ConfettiAnimation(self._width, self._height)

        if is_match_win:
            confetti.start(intensity="big", colors=CONFETTI_COLORS_PARTY)
            PongPlugin._celebration_duration = 3.5
        else:
            # Small point celebration — sparks from the scoring side
            scorer_x = (
                self._width * 0.2
                if PongPlugin._last_scorer == "left"
                else self._width * 0.8
            )
            confetti.start(
                intensity="small", colors=CONFETTI_COLORS_WARM, origin_x=scorer_x
            )
            PongPlugin._celebration_duration = 1.0

        PongPlugin._confetti_anim = confetti

    def _update_celebration(self) -> None:
        """Update confetti particle positions."""
        if PongPlugin._confetti_anim:
            PongPlugin._confetti_anim.update()

    def _predict_ball_y(self, target_x: float) -> float:
        """Predict where the ball will be at a given x position."""
        if PongPlugin._ball_vx == 0:
            return PongPlugin._ball_y

        dx = target_x - PongPlugin._ball_x
        if (dx > 0 and PongPlugin._ball_vx < 0) or (dx < 0 and PongPlugin._ball_vx > 0):
            return PongPlugin._ball_y

        t = dx / PongPlugin._ball_vx
        predicted_y = PongPlugin._ball_y + PongPlugin._ball_vy * t

        # Simulate wall bounces
        bounces = 0
        while (predicted_y < 0 or predicted_y > self._height) and bounces < 10:
            if predicted_y < 0:
                predicted_y = -predicted_y
            elif predicted_y > self._height:
                predicted_y = 2 * self._height - predicted_y
            bounces += 1

        return predicted_y

    def _update_paddles(self) -> None:
        """Move paddles with human-like AI."""
        now = time.time()

        # --- Left paddle AI ---
        if PongPlugin._ball_vx < 0:
            if now - self._left_last_react_time > self._left_reaction_delay:
                self._left_last_react_time = now
                paddle_x = self._paddle_margin + self._paddle_width
                predicted = self._predict_ball_y(paddle_x)
                error = random.uniform(-self._left_error, self._left_error)
                self._left_target_y = predicted + error - self._paddle_height / 2
        else:
            center = (self._height - self._paddle_height) / 2
            self._left_target_y += (center - self._left_target_y) * 0.01

        diff = self._left_target_y - PongPlugin._left_paddle_y
        max_move = self._left_max_speed * self._scale_y
        if PongPlugin._ball_vx < 0 and PongPlugin._ball_x > self._width * 0.55:
            max_move *= 0.2
        if abs(diff) > 1.5:
            PongPlugin._left_paddle_y += math.copysign(min(max_move, abs(diff)), diff)

        # --- Right paddle AI ---
        if PongPlugin._ball_vx > 0:
            if now - self._right_last_react_time > self._right_reaction_delay:
                self._right_last_react_time = now
                paddle_x = self._width - self._paddle_margin - self._paddle_width
                predicted = self._predict_ball_y(paddle_x)
                error = random.uniform(-self._right_error, self._right_error)
                self._right_target_y = predicted + error - self._paddle_height / 2
        else:
            center = (self._height - self._paddle_height) / 2
            self._right_target_y += (center - self._right_target_y) * 0.01

        diff = self._right_target_y - PongPlugin._right_paddle_y
        max_move = self._right_max_speed * self._scale_y
        if PongPlugin._ball_vx > 0 and PongPlugin._ball_x < self._width * 0.45:
            max_move *= 0.2
        if abs(diff) > 1.5:
            PongPlugin._right_paddle_y += math.copysign(min(max_move, abs(diff)), diff)

        # Clamp paddles
        PongPlugin._left_paddle_y = max(
            0, min(self._height - self._paddle_height, PongPlugin._left_paddle_y)
        )
        PongPlugin._right_paddle_y = max(
            0, min(self._height - self._paddle_height, PongPlugin._right_paddle_y)
        )

    def _update_physics(self) -> Optional[str]:
        """Update ball position and handle collisions."""
        if PongPlugin._serve_delay > 0:
            PongPlugin._serve_delay -= 1
            return None

        # Move ball
        PongPlugin._ball_x += PongPlugin._ball_vx
        PongPlugin._ball_y += PongPlugin._ball_vy

        # Bounce off top/bottom walls
        if PongPlugin._ball_y <= 0:
            PongPlugin._ball_y = 0
            PongPlugin._ball_vy = abs(PongPlugin._ball_vy)
        elif PongPlugin._ball_y >= self._height - self._ball_size:
            PongPlugin._ball_y = self._height - self._ball_size
            PongPlugin._ball_vy = -abs(PongPlugin._ball_vy)

        # Left paddle collision
        left_paddle_x = self._paddle_margin
        if (
            PongPlugin._ball_x <= left_paddle_x + self._paddle_width
            and PongPlugin._ball_x >= left_paddle_x - self._ball_size
            and PongPlugin._ball_vx < 0
        ):
            paddle_top = PongPlugin._left_paddle_y
            paddle_bottom = PongPlugin._left_paddle_y + self._paddle_height
            if (
                PongPlugin._ball_y + self._ball_size >= paddle_top
                and PongPlugin._ball_y <= paddle_bottom
            ):
                PongPlugin._ball_vx = abs(PongPlugin._ball_vx) * 1.03
                hit_pos = (
                    (PongPlugin._ball_y + self._ball_size / 2)
                    - (paddle_top + self._paddle_height / 2)
                ) / (self._paddle_height / 2)
                PongPlugin._ball_vy += hit_pos * 0.8 * self._scale_y
                PongPlugin._rally_count += 1

        # Right paddle collision
        right_paddle_x = self._width - self._paddle_margin - self._paddle_width
        if (
            PongPlugin._ball_x + self._ball_size >= right_paddle_x
            and PongPlugin._ball_x <= right_paddle_x + self._paddle_width
            and PongPlugin._ball_vx > 0
        ):
            paddle_top = PongPlugin._right_paddle_y
            paddle_bottom = PongPlugin._right_paddle_y + self._paddle_height
            if (
                PongPlugin._ball_y + self._ball_size >= paddle_top
                and PongPlugin._ball_y <= paddle_bottom
            ):
                PongPlugin._ball_vx = -abs(PongPlugin._ball_vx) * 1.03
                hit_pos = (
                    (PongPlugin._ball_y + self._ball_size / 2)
                    - (paddle_top + self._paddle_height / 2)
                ) / (self._paddle_height / 2)
                PongPlugin._ball_vy += hit_pos * 0.8 * self._scale_y
                PongPlugin._rally_count += 1

        # Clamp ball velocity
        max_speed = 3.5 * self._ball_speed_mult * max(self._scale_x, self._scale_y)
        speed = math.sqrt(PongPlugin._ball_vx**2 + PongPlugin._ball_vy**2)
        if speed > max_speed:
            PongPlugin._ball_vx = (PongPlugin._ball_vx / speed) * max_speed
            PongPlugin._ball_vy = (PongPlugin._ball_vy / speed) * max_speed

        # Score detection
        scored = None
        if PongPlugin._ball_x < -self._ball_size:
            scored = "right"
            PongPlugin._right_score += 1
            PongPlugin._last_scorer = "right"
            self._score_flash_until = time.time() + 0.8
            self._point_scored_this_activation = True
        elif PongPlugin._ball_x > self._width + self._ball_size:
            scored = "left"
            PongPlugin._left_score += 1
            PongPlugin._last_scorer = "left"
            self._score_flash_until = time.time() + 0.8
            self._point_scored_this_activation = True

        if scored:
            if (
                PongPlugin._left_score >= MAX_SCORE
                or PongPlugin._right_score >= MAX_SCORE
            ):
                PongPlugin._winner = (
                    "left" if PongPlugin._left_score >= MAX_SCORE else "right"
                )
                self._start_celebration(is_match_win=True)
                logger.info(
                    "[pong] Game over: %d - %d",
                    PongPlugin._left_score,
                    PongPlugin._right_score,
                )
            else:
                self._start_celebration(is_match_win=False)
                self._serve_new_ball()

        return scored

    def _render(self, width: int, height: int) -> Image.Image:
        """Render the current game state to a frame."""
        frame = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # Draw center net (dashed line)
        center_x = width // 2
        net_gap = max(3, int(NET_GAP * self._scale_y))
        for y in range(0, height, net_gap):
            for dy in range(NET_DOT_SIZE):
                py = y + dy
                if py < height:
                    frame.putpixel((center_x, py), self._net_color)

        # Draw paddles
        left_x = self._paddle_margin
        right_x = width - self._paddle_margin - self._paddle_width

        left_top = int(round(PongPlugin._left_paddle_y))
        right_top = int(round(PongPlugin._right_paddle_y))

        draw.rectangle(
            [
                left_x,
                left_top,
                left_x + self._paddle_width - 1,
                left_top + self._paddle_height - 1,
            ],
            fill=self._paddle_color,
        )
        draw.rectangle(
            [
                right_x,
                right_top,
                right_x + self._paddle_width - 1,
                right_top + self._paddle_height - 1,
            ],
            fill=self._paddle_color,
        )

        # Draw ball (blink during serve delay)
        if PongPlugin._serve_delay <= 0 or (PongPlugin._serve_delay % 6) < 3:
            ball_x = int(round(PongPlugin._ball_x))
            ball_y = int(round(PongPlugin._ball_y))
            draw.rectangle(
                [
                    ball_x,
                    ball_y,
                    ball_x + self._ball_size - 1,
                    ball_y + self._ball_size - 1,
                ],
                fill=self._ball_color,
            )

        # Draw confetti during celebration
        if PongPlugin._celebrating and PongPlugin._confetti_anim:
            PongPlugin._confetti_anim.draw(frame)

        # Draw score
        self._draw_score(frame, width, height)

        # Draw winner text during match-win celebration
        if PongPlugin._winner and PongPlugin._celebrating and self._helpers:
            # Blinking "P1 WINS" or "P2 WINS" centered on screen
            elapsed = time.time() - PongPlugin._celebration_start
            if int(elapsed * 4) % 2 == 0:  # Blink at 4Hz
                winner_text = "P1 WINS" if PongPlugin._winner == "left" else "P2 WINS"
                text_w = self._helpers.get_text_width(winner_text, "MENU")
                text_x = (width - text_w) // 2
                text_y = height // 2 - int(6 * self._scale_y)
                win_color = (0, 255, 100)  # Green for winner
                win_frame = self._helpers.render_text(
                    winner_text,
                    x=text_x,
                    y=text_y,
                    color=win_color,
                    font_name="MENU",
                )
                frame = self._helpers.composite_frames(frame, win_frame)

        return frame

    def _draw_score(self, frame: Image.Image, width: int, height: int) -> None:
        """Draw the score at the top of the screen."""
        if not self._helpers:
            return

        now = time.time()
        flashing = now < self._score_flash_until

        if flashing and (int(now * 8) % 2 == 0):
            color = (255, 255, 255)
        else:
            color = self._score_color

        left_str = str(PongPlugin._left_score)
        right_str = str(PongPlugin._right_score)

        quarter_x = width // 4
        score_y = int(2 * self._scale_y)

        left_frame = self._helpers.render_text(
            left_str,
            x=quarter_x - self._helpers.get_text_width(left_str, "MENU") // 2,
            y=score_y,
            color=color,
            font_name="MENU",
        )
        frame_result = self._helpers.composite_frames(frame, left_frame)

        right_frame = self._helpers.render_text(
            right_str,
            x=quarter_x * 3 - self._helpers.get_text_width(right_str, "MENU") // 2,
            y=score_y,
            color=color,
            font_name="MENU",
        )
        final = self._helpers.composite_frames(frame_result, right_frame)
        frame.paste(final)

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render the next Pong frame.

        Returns None (signals completion) only during serve pause after a
        point is scored, so the clock never interrupts mid-rally.
        """
        # Adapt to display size
        if width != self._width or height != self._height:
            self._width = width
            self._height = height
            self._scale_x = width / 128
            self._scale_y = height / 32
            self._paddle_width = max(2, int(PADDLE_WIDTH * self._scale_x))
            self._paddle_height = max(6, int(PADDLE_HEIGHT * self._scale_y))
            self._ball_size = max(2, int(BALL_SIZE * min(self._scale_x, self._scale_y)))
            self._paddle_margin = int(PADDLE_MARGIN * self._scale_x)

        if self._frames_rendered == 0:
            logger.info("[pong] Start rendering")

        # Handle celebration
        if PongPlugin._celebrating:
            self._update_celebration()
            elapsed = time.time() - PongPlugin._celebration_start
            if elapsed >= PongPlugin._celebration_duration:
                PongPlugin._celebrating = False
                PongPlugin._confetti_anim = None
                # If it was a match win, reset scores
                if (
                    PongPlugin._left_score >= MAX_SCORE
                    or PongPlugin._right_score >= MAX_SCORE
                ):
                    self._reset_game()
                    return None  # Yield to clock after match celebration
                else:
                    # Point celebration over — serve new ball already queued
                    pass
            frame = self._render(width, height)
            self._frames_rendered += 1
            return frame

        # If we've scored a point and celebration is over, yield to clock
        if (
            self._point_scored_this_activation
            and not PongPlugin._celebrating
            and PongPlugin._serve_delay > 10
            and self._frames_rendered > 20
        ):
            return None  # Clean break — clock takes over between points

        # Max duration reached — only yield during serve pause
        if self._frames_rendered >= self._max_frames and PongPlugin._serve_delay > 0:
            return None

        # Update game state
        self._update_paddles()
        self._update_physics()

        # Render
        frame = self._render(width, height)
        self._frames_rendered += 1
        return frame

    async def cleanup(self) -> None:
        """Minimal cleanup — game state persists on class for next activation."""
        self._frames_rendered = 0
        self._point_scored_this_activation = False
