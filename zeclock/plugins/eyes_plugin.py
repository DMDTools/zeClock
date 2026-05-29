"""EyesClock plugin - Animated robot eyes tracking a buzzing fly.

Inspired by FluxGarage RoboEyes and sofianhw/RoboEyes.
Two expressive eyes track a small fly/mosquito buzzing around the screen.
The eyes follow it, occasionally blink, and react when the fly gets close.
"""

import math
import random
import time
import logging
from typing import Optional, Tuple

from PIL import Image, ImageDraw

from .base import ClockPlugin
from ..colors import COLOR_MAP

logger = logging.getLogger(__name__)


# Eye geometry constants (for 128x32 display)
EYE_WIDTH = 20
EYE_HEIGHT = 20
EYE_SPACING = 16  # Gap between the two eyes
EYE_BORDER_RADIUS = 6
PUPIL_RADIUS = 4
PUPIL_MAX_OFFSET_X = 5
PUPIL_MAX_OFFSET_Y = 4

# Animation timing
BLINK_INTERVAL_MIN = 2.5  # Seconds between blinks
BLINK_INTERVAL_MAX = 5.0
BLINK_DURATION = 0.15  # Seconds for a full blink (close + open)
BLINK_DURATION_SLOW = 0.4  # Slow sleepy blink
WINK_DURATION = 0.2  # One-eye wink
LOOK_TRANSITION_SPEED = 0.2  # Interpolation factor per frame (0-1)

# Fly constants
FLY_SIZE = 3  # Pixels
FLY_WING_SIZE = 2
FLY_SPEED_MIN = 1.0
FLY_SPEED_MAX = 3.0
FLY_DIRECTION_CHANGE_MIN = 0.3  # Seconds between direction changes
FLY_DIRECTION_CHANGE_MAX = 1.5
FLY_BUZZ_AMPLITUDE = 1.5  # Pixels of random jitter
FLY_LANDING_CHANCE = 0.03  # Chance per direction change to land on screen edge
FLY_LANDING_DURATION_MIN = 1.0
FLY_LANDING_DURATION_MAX = 2.5
FLY_CLOSE_DISTANCE = 25  # Pixels - triggers annoyed squint
FLY_CROSS_EYE_DISTANCE = 20  # Pixels - starts progressive cross-eye effect

# Expression timing
EXPRESSION_DURATION_MIN = 1.5
EXPRESSION_DURATION_MAX = 3.0


class Expression:
    """Eye expression states driven by fly behavior."""

    NORMAL = "normal"
    ANNOYED = "annoyed"  # Fly is close - squint + eyebrows
    SURPRISED = "surprised"  # Fly suddenly appears nearby - wide eyes
    SLEEPY = "sleepy"  # Fly is far/resting - droopy eyes
    HAPPY = "happy"  # Fly just left the face area - relief
    WINK = "wink"  # Occasional playful wink
    FOCUSED = "focused"  # Fly landed - squinting like about to smash it


class FlyState:
    """Fly behavior states."""

    FLYING = "flying"
    LANDING = "landing"  # Resting on edge of screen
    BUZZING_CLOSE = "buzzing_close"  # Buzzing near the eyes (annoying)


class EyesPlugin(ClockPlugin):
    """Displays animated robot eyes tracking a buzzing fly."""

    @property
    def name(self) -> str:
        return "eyes"

    @property
    def description(self) -> str:
        return "Animated robot eyes tracking a buzzing fly"

    @property
    def frame_delay_ms(self) -> int:
        return 40  # 25 FPS for smooth animation

    async def initialize(self, config: dict) -> None:
        """Set up the eyes and fly animation state.

        Config keys:
            duration_seconds (int): How long to display (default: 20)
            color (str): Eye color name (default: cyan)
            show_time (bool): Whether to show time below eyes (default: True)
        """
        self._helpers = config.get("_helpers")
        self._duration_seconds = config.get("duration_seconds", 20)
        self._show_time = config.get("show_time", True)

        # Colors
        self._eye_color: Tuple[int, int, int] = (0, 255, 255)  # Cyan default
        self._pupil_color: Tuple[int, int, int] = (0, 0, 0)
        self._outline_color: Tuple[int, int, int] = (0, 180, 180)
        self._time_color: Tuple[int, int, int] = (0, 255, 255)
        self._fly_color: Tuple[int, int, int] = (200, 200, 100)
        self._fly_wing_color: Tuple[int, int, int] = (150, 150, 150)

        color = config.get("color")
        if isinstance(color, str):
            resolved = COLOR_MAP.get(color)
            if resolved:
                self._eye_color = resolved
                self._outline_color = (
                    resolved[0] * 2 // 3,
                    resolved[1] * 2 // 3,
                    resolved[2] * 2 // 3,
                )
                self._time_color = resolved

        self._frames_rendered = 0
        self._max_frames = int(self._duration_seconds * 1000 / self.frame_delay_ms)

        # Display dimensions (will be set on first render)
        self._width = 128
        self._height = 32

        # Eye animation state
        self._current_pupil_x = 0.0  # Current pupil offset (-1 to 1)
        self._current_pupil_y = 0.0
        self._target_pupil_x = 0.0
        self._target_pupil_y = 0.0

        # Blink state
        self._blink_progress = 0.0  # 0 = open, 1 = fully closed
        self._is_blinking = False
        self._next_blink_time = time.time() + random.uniform(
            BLINK_INTERVAL_MIN, BLINK_INTERVAL_MAX
        )
        self._blink_start_time = 0.0

        # Eye squish (reaction to fly being close)
        self._eye_squish = 0.0  # 0 = normal, positive = annoyed squint
        self._cross_eye_amount = 0.0  # 0 = normal, 1 = fully cross-eyed

        # Expression state
        self._expression = Expression.NORMAL
        self._expression_end_time = 0.0
        self._eye_height_mult = 1.0  # Animated eye height multiplier
        self._target_eye_height_mult = 1.0
        self._wink_eye = "none"  # "left", "right", or "none"
        self._wink_progress = 0.0
        self._wink_start_time = 0.0
        self._fly_was_close = False  # Track if fly was close last frame
        self._fly_close_start_time = 0.0  # When fly first got close
        self._last_surprise_time = 0.0  # Cooldown for surprise

        # Fly state
        self._fly_x = random.uniform(5, 123)
        self._fly_y = random.uniform(2, 29)
        self._fly_vx = random.uniform(-2, 2)
        self._fly_vy = random.uniform(-1, 1)
        self._fly_state = FlyState.FLYING
        self._fly_wing_frame = 0  # For wing animation
        self._next_direction_change = time.time() + random.uniform(
            FLY_DIRECTION_CHANGE_MIN, FLY_DIRECTION_CHANGE_MAX
        )
        self._landing_end_time = 0.0

        # Eye center positions (calculated during render)
        self._left_eye_cx = 0.0
        self._left_eye_cy = 0.0
        self._right_eye_cx = 0.0
        self._right_eye_cy = 0.0

    def _update_fly(self) -> None:
        """Update fly position and behavior."""
        now = time.time()

        if self._fly_state == FlyState.LANDING:
            # Fly is resting - check if it should take off
            if now >= self._landing_end_time:
                self._fly_state = FlyState.FLYING
                # Take off with some speed away from edge
                self._fly_vx = random.uniform(1.0, 2.5) * (
                    1 if self._fly_x < self._width / 2 else -1
                )
                self._fly_vy = random.uniform(-1.5, 1.5)
            return

        # Direction changes
        if now >= self._next_direction_change:
            self._next_direction_change = now + random.uniform(
                FLY_DIRECTION_CHANGE_MIN, FLY_DIRECTION_CHANGE_MAX
            )

            # Chance to land on screen edge or on the nose
            if random.random() < FLY_LANDING_CHANCE:
                self._fly_state = FlyState.LANDING
                self._landing_end_time = now + random.uniform(
                    FLY_LANDING_DURATION_MIN, FLY_LANDING_DURATION_MAX
                )
                # Move to nearest edge
                edge = random.choice(["left", "right", "top", "bottom"])
                if edge == "left":
                    self._fly_x = 1
                    self._fly_y = random.uniform(2, self._height - 3)
                elif edge == "right":
                    self._fly_x = self._width - 2
                    self._fly_y = random.uniform(2, self._height - 3)
                elif edge == "top":
                    self._fly_x = random.uniform(5, self._width - 5)
                    self._fly_y = 1
                else:
                    self._fly_x = random.uniform(5, self._width - 5)
                    self._fly_y = self._height - 2
                self._fly_vx = 0
                self._fly_vy = 0
                return

            # Chance to land on the "nose" (below the eyes, on the clock area)
            if random.random() < 0.07:
                self._fly_state = FlyState.LANDING
                self._landing_end_time = now + random.uniform(2.0, 4.0)
                # Land between the eyes but lower — just below the eyes, above the clock
                nose_x = (self._left_eye_cx + self._right_eye_cx) / 2
                nose_y = (
                    (self._left_eye_cy + self._right_eye_cy) / 2 + EYE_HEIGHT // 2 - 1
                )
                self._fly_x = nose_x
                self._fly_y = nose_y
                self._fly_vx = 0
                self._fly_vy = 0
                return

            # New random direction with speed variation
            speed = random.uniform(FLY_SPEED_MIN, FLY_SPEED_MAX)
            angle = random.uniform(0, 2 * math.pi)
            self._fly_vx = speed * math.cos(angle)
            self._fly_vy = speed * math.sin(angle)

            # Occasionally buzz close to the eyes
            if random.random() < 0.25:
                # Aim toward the eye area
                eye_center_x = self._width / 2
                eye_center_y = self._height / 2 - 4
                dx = eye_center_x - self._fly_x
                dy = eye_center_y - self._fly_y
                dist = math.sqrt(dx * dx + dy * dy) or 1
                self._fly_vx = (dx / dist) * speed
                self._fly_vy = (dy / dist) * speed

        # Move fly
        self._fly_x += self._fly_vx
        self._fly_y += self._fly_vy

        # Add buzz jitter
        self._fly_x += random.uniform(-FLY_BUZZ_AMPLITUDE, FLY_BUZZ_AMPLITUDE)
        self._fly_y += random.uniform(
            -FLY_BUZZ_AMPLITUDE * 0.5, FLY_BUZZ_AMPLITUDE * 0.5
        )

        # Bounce off screen edges - use full display area
        if self._fly_x < 1:
            self._fly_x = 1
            self._fly_vx = abs(self._fly_vx)
        elif self._fly_x > self._width - 2:
            self._fly_x = self._width - 2
            self._fly_vx = -abs(self._fly_vx)

        if self._fly_y < 1:
            self._fly_y = 1
            self._fly_vy = abs(self._fly_vy)
        elif self._fly_y > self._height - 2:
            self._fly_y = self._height - 2
            self._fly_vy = -abs(self._fly_vy)

        # Animate wings
        self._fly_wing_frame = (self._fly_wing_frame + 1) % 4

    def _calculate_gaze_from_fly(self) -> Tuple[float, float]:
        """Calculate normalized pupil offset to look at the fly.

        Returns:
            (x_offset, y_offset) normalized to -1..1 range.
        """
        # Calculate center of both eyes
        eyes_center_x = (self._left_eye_cx + self._right_eye_cx) / 2
        eyes_center_y = (self._left_eye_cy + self._right_eye_cy) / 2

        # Direction from eyes to fly
        dx = self._fly_x - eyes_center_x
        dy = self._fly_y - eyes_center_y

        # Normalize to -1..1 range based on screen dimensions
        norm_x = max(-1.0, min(1.0, dx / (self._width * 0.4)))
        norm_y = max(-1.0, min(1.0, dy / (self._height * 0.3)))

        return norm_x, norm_y

    def _get_fly_distance_to_eyes(self) -> float:
        """Get distance from fly to the center of the eyes."""
        eyes_center_x = (self._left_eye_cx + self._right_eye_cx) / 2
        eyes_center_y = (self._left_eye_cy + self._right_eye_cy) / 2
        dx = self._fly_x - eyes_center_x
        dy = self._fly_y - eyes_center_y
        return math.sqrt(dx * dx + dy * dy)

    def _update_expression(self, fly_dist: float) -> None:
        """Update eye expression based on fly behavior."""
        now = time.time()
        fly_is_close = fly_dist < FLY_CLOSE_DISTANCE

        # Detect transitions
        fly_just_arrived = fly_is_close and not self._fly_was_close
        fly_just_left = not fly_is_close and self._fly_was_close

        # Surprise: fly suddenly appears near the eyes (with cooldown)
        if fly_just_arrived and (now - self._last_surprise_time) > 4.0:
            self._expression = Expression.SURPRISED
            self._expression_end_time = now + 0.6
            self._last_surprise_time = now
            # Trigger a quick startled blink
            if not self._is_blinking:
                self._is_blinking = True
                self._blink_start_time = now

        # Happy/relief: fly just left the face area
        elif fly_just_left and self._expression == Expression.ANNOYED:
            self._expression = Expression.HAPPY
            self._expression_end_time = now + random.uniform(1.0, 2.0)

        # Annoyed: fly has been close for a while
        elif fly_is_close and (now - self._fly_close_start_time) > 0.5:
            self._expression = Expression.ANNOYED

        # Focused: fly just landed - squint like about to smash it
        elif self._fly_state == FlyState.LANDING and self._expression not in (
            Expression.FOCUSED,
        ):
            self._expression = Expression.FOCUSED
            self._expression_end_time = self._landing_end_time + 0.5

        # Sleepy: fly is far away and has been resting a while
        elif (
            self._fly_state == FlyState.LANDING
            and fly_dist > 40
            and self._expression == Expression.FOCUSED
            and random.random() < 0.01
        ):
            self._expression = Expression.SLEEPY
            self._expression_end_time = now + random.uniform(
                EXPRESSION_DURATION_MIN, EXPRESSION_DURATION_MAX
            )

        # Wink: occasional playful wink when fly is at medium distance
        elif (
            self._expression == Expression.NORMAL
            and 30 < fly_dist < 50
            and random.random() < 0.003
            and self._wink_eye == "none"
        ):
            self._expression = Expression.WINK
            self._wink_eye = random.choice(["left", "right"])
            self._wink_start_time = now
            self._expression_end_time = now + WINK_DURATION

        # Return to normal when expression expires
        if now >= self._expression_end_time and self._expression not in (
            Expression.NORMAL,
            Expression.ANNOYED,
            Expression.FOCUSED,
        ):
            self._expression = Expression.NORMAL
            self._wink_eye = "none"

        # Clear focused when fly takes off
        if (
            self._fly_state != FlyState.LANDING
            and self._expression == Expression.FOCUSED
        ):
            self._expression = Expression.NORMAL

        # If fly moves away, clear annoyed
        if not fly_is_close and self._expression == Expression.ANNOYED:
            self._expression = Expression.NORMAL

        # Track fly proximity state
        if fly_is_close and not self._fly_was_close:
            self._fly_close_start_time = now
        self._fly_was_close = fly_is_close

        # Animate eye height multiplier based on expression
        if self._expression == Expression.SURPRISED:
            self._target_eye_height_mult = 1.2  # Wide open
        elif self._expression == Expression.SLEEPY:
            self._target_eye_height_mult = 0.55  # Droopy
        elif self._expression == Expression.HAPPY:
            self._target_eye_height_mult = 0.75  # Squinty smile
        elif self._expression == Expression.FOCUSED:
            self._target_eye_height_mult = 0.5  # Tight squint - ready to strike
        else:
            self._target_eye_height_mult = 1.0

        # Smooth transition
        self._eye_height_mult += (
            self._target_eye_height_mult - self._eye_height_mult
        ) * 0.12

        # Update wink progress
        if self._wink_eye != "none":
            elapsed = now - self._wink_start_time
            half = WINK_DURATION / 2.0
            if elapsed < half:
                self._wink_progress = elapsed / half
            elif elapsed < WINK_DURATION:
                self._wink_progress = 1.0 - (elapsed - half) / half
            else:
                self._wink_progress = 0.0
                self._wink_eye = "none"

    def _update_animation(self) -> None:
        """Update all animation states for the current frame."""
        now = time.time()

        # Update fly
        self._update_fly()

        # Calculate gaze target from fly position
        if self._fly_state == FlyState.LANDING:
            target_x, target_y = self._calculate_gaze_from_fly()
            self._target_pupil_x = target_x
            self._target_pupil_y = target_y
        else:
            self._target_pupil_x, self._target_pupil_y = self._calculate_gaze_from_fly()

        # Check if fly is close (triggers reaction)
        fly_dist = self._get_fly_distance_to_eyes()
        if fly_dist < FLY_CLOSE_DISTANCE:
            target_squish = 0.3 * (1.0 - fly_dist / FLY_CLOSE_DISTANCE)
            self._eye_squish += (target_squish - self._eye_squish) * 0.15
        else:
            self._eye_squish = max(0.0, self._eye_squish - 0.02)

        # Progressive cross-eye - extra strong when fly is on the nose
        if fly_dist < FLY_CROSS_EYE_DISTANCE:
            # 0 at the edge, 1 when fly is right between the eyes
            target_cross = 1.0 - (fly_dist / FLY_CROSS_EYE_DISTANCE)
            # Boost to full cross-eye when fly is landed on the nose (very close)
            if self._fly_state == FlyState.LANDING and fly_dist < 8:
                target_cross = 1.0
            self._cross_eye_amount += (target_cross - self._cross_eye_amount) * 0.25
        else:
            self._cross_eye_amount = max(0.0, self._cross_eye_amount - 0.05)

        # Update expression
        self._update_expression(fly_dist)

        # Smooth interpolation toward target
        speed = LOOK_TRANSITION_SPEED
        if self._fly_state != FlyState.LANDING:
            speed = 0.25
        self._current_pupil_x += (self._target_pupil_x - self._current_pupil_x) * speed
        self._current_pupil_y += (self._target_pupil_y - self._current_pupil_y) * speed

        # Update blink - sleepy mode uses slower blinks
        if not self._is_blinking and now >= self._next_blink_time:
            self._is_blinking = True
            self._blink_start_time = now

        if self._is_blinking:
            duration = (
                BLINK_DURATION_SLOW
                if self._expression == Expression.SLEEPY
                else BLINK_DURATION
            )
            elapsed = now - self._blink_start_time
            half_duration = duration / 2.0
            if elapsed < half_duration:
                self._blink_progress = elapsed / half_duration
            elif elapsed < duration:
                self._blink_progress = 1.0 - (elapsed - half_duration) / half_duration
            else:
                self._blink_progress = 0.0
                self._is_blinking = False
                # Sleepy = blink more often
                if self._expression == Expression.SLEEPY:
                    self._next_blink_time = now + random.uniform(1.0, 2.5)
                else:
                    self._next_blink_time = now + random.uniform(
                        BLINK_INTERVAL_MIN, BLINK_INTERVAL_MAX
                    )

    def _draw_fly(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw the fly/mosquito at its current position."""
        if self._fly_state == FlyState.LANDING:
            # Draw fly at rest (wings folded)
            fx = int(self._fly_x)
            fy = int(self._fly_y)
            # Body
            draw.ellipse(
                [fx - 1, fy - 1, fx + 1, fy + 1],
                fill=self._fly_color,
            )
            # Folded wings (small lines)
            draw.line([(fx - 1, fy - 1), (fx - 2, fy - 2)], fill=self._fly_wing_color)
            draw.line([(fx + 1, fy - 1), (fx + 2, fy - 2)], fill=self._fly_wing_color)
        else:
            # Draw fly in flight with animated wings
            fx = int(self._fly_x)
            fy = int(self._fly_y)

            # Body (small dot)
            draw.point((fx, fy), fill=self._fly_color)
            if FLY_SIZE > 2:
                draw.point((fx + 1, fy), fill=self._fly_color)

            # Animated wings - flap up/down
            wing_up = self._fly_wing_frame < 2
            if wing_up:
                # Wings up
                draw.point((fx - 1, fy - 1), fill=self._fly_wing_color)
                draw.point((fx + 1, fy - 1), fill=self._fly_wing_color)
            else:
                # Wings down/out
                draw.point((fx - 1, fy), fill=self._fly_wing_color)
                draw.point((fx + 1, fy), fill=self._fly_wing_color)

    def _draw_eye(
        self,
        draw: ImageDraw.ImageDraw,
        center_x: int,
        center_y: int,
        pupil_offset_x: float,
        pupil_offset_y: float,
        blink_progress: float,
        is_left: bool,
    ) -> None:
        """Draw a single eye with the current animation state."""
        eye_w = EYE_WIDTH
        eye_h = int(EYE_HEIGHT * self._eye_height_mult)

        # Apply annoyed squint on top of expression
        if self._eye_squish > 0:
            eye_h = int(eye_h * (1.0 - self._eye_squish))

        # Wink: close only one eye
        effective_blink = blink_progress
        if self._wink_eye != "none":
            if (self._wink_eye == "left" and is_left) or (
                self._wink_eye == "right" and not is_left
            ):
                effective_blink = max(effective_blink, self._wink_progress)

        # Apply blink (reduce height)
        visible_height = int(eye_h * (1.0 - effective_blink))
        if visible_height < 2:
            # Eye is closed - just draw a line
            draw.line(
                [
                    (center_x - eye_w // 2, center_y),
                    (center_x + eye_w // 2, center_y),
                ],
                fill=self._outline_color,
                width=2,
            )
            return

        # Eye outline (rounded rectangle)
        left = center_x - eye_w // 2
        top = center_y - visible_height // 2
        right = center_x + eye_w // 2
        bottom = center_y + visible_height // 2

        # Draw eye (filled rounded rectangle)
        radius = min(EYE_BORDER_RADIUS, visible_height // 2)
        draw.rounded_rectangle(
            [left, top, right, bottom],
            radius=radius,
            fill=self._eye_color,
            outline=self._outline_color,
        )

        # Pupil offset - progressive cross-eye when fly is near the "nose"
        px_offset = pupil_offset_x
        if self._cross_eye_amount > 0.01:
            cross_target = 0.9 if is_left else -0.9
            px_offset = (
                pupil_offset_x * (1.0 - self._cross_eye_amount)
                + cross_target * self._cross_eye_amount
            )

        # Pupil size varies with expression
        pupil_r = PUPIL_RADIUS
        if self._expression == Expression.SURPRISED:
            pupil_r = PUPIL_RADIUS - 1  # Smaller pupil = startled
        elif self._expression == Expression.SLEEPY:
            pupil_r = PUPIL_RADIUS + 1  # Larger pupil = relaxed

        # Draw pupil
        pupil_x = center_x + int(px_offset * PUPIL_MAX_OFFSET_X)
        pupil_y = center_y + int(pupil_offset_y * PUPIL_MAX_OFFSET_Y)

        # Clamp pupil within eye bounds
        pupil_x = max(left + pupil_r + 2, min(right - pupil_r - 2, pupil_x))
        pupil_y = max(top + pupil_r + 1, min(bottom - pupil_r - 1, pupil_y))

        draw.ellipse(
            [
                pupil_x - pupil_r,
                pupil_y - pupil_r,
                pupil_x + pupil_r,
                pupil_y + pupil_r,
            ],
            fill=self._pupil_color,
        )

        # Draw highlight (small white dot on pupil)
        highlight_x = pupil_x - 1
        highlight_y = pupil_y - 1
        draw.ellipse(
            [highlight_x, highlight_y, highlight_x + 2, highlight_y + 2],
            fill=(255, 255, 255),
        )

        # Expression-specific decorations
        if self._expression == Expression.FOCUSED:
            # Intense focused eyebrows - both angled sharply down toward center
            if is_left:
                draw.line(
                    [(left - 1, top - 4), (right + 1, top - 1)],
                    fill=self._outline_color,
                    width=2,
                )
            else:
                draw.line(
                    [(left - 1, top - 1), (right + 1, top - 4)],
                    fill=self._outline_color,
                    width=2,
                )
        elif self._expression == Expression.ANNOYED or self._eye_squish > 0.15:
            # Angry eyebrows
            if is_left:
                draw.line(
                    [(left, top - 2), (right, top - 3)],
                    fill=self._outline_color,
                    width=1,
                )
            else:
                draw.line(
                    [(left, top - 3), (right, top - 2)],
                    fill=self._outline_color,
                    width=1,
                )
        elif self._expression == Expression.HAPPY:
            # Curved bottom = smile shape
            draw.arc(
                [left + 3, bottom - 4, right - 3, bottom + 3],
                start=0,
                end=180,
                fill=self._outline_color,
            )
        elif self._expression == Expression.SURPRISED:
            # Raised eyebrows (arched lines above eyes)
            draw.arc(
                [left + 2, top - 5, right - 2, top + 2],
                start=180,
                end=0,
                fill=self._outline_color,
            )

    def _render(self, width: int, height: int) -> Image.Image:
        """Render the current animation state to a frame."""
        frame = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # Calculate eye positions
        eyes_y_offset = -4 if self._show_time else 0
        center_y = height // 2 + eyes_y_offset

        total_eye_width = EYE_WIDTH * 2 + EYE_SPACING
        left_eye_x = (width - total_eye_width) // 2 + EYE_WIDTH // 2
        right_eye_x = left_eye_x + EYE_WIDTH + EYE_SPACING

        # Store eye centers for gaze calculation
        self._left_eye_cx = left_eye_x
        self._left_eye_cy = center_y
        self._right_eye_cx = right_eye_x
        self._right_eye_cy = center_y

        # Draw the fly always in front of the eyes
        # Draw both eyes
        self._draw_eye(
            draw,
            left_eye_x,
            center_y,
            self._current_pupil_x,
            self._current_pupil_y,
            self._blink_progress,
            is_left=True,
        )
        self._draw_eye(
            draw,
            right_eye_x,
            center_y,
            self._current_pupil_x,
            self._current_pupil_y,
            self._blink_progress,
            is_left=False,
        )

        # Fly always on top
        self._draw_fly(draw)

        # Draw time below the eyes
        if self._show_time and self._helpers:
            now = time.localtime()
            hours_str = f"{now.tm_hour:02d}"
            minutes_str = f"{now.tm_min:02d}"
            colon_str = ":"

            hours_w = self._helpers.get_text_width(hours_str, "SYSTEM")
            colon_w = self._helpers.get_text_width(colon_str, "SYSTEM")
            minutes_w = self._helpers.get_text_width(minutes_str, "SYSTEM")

            total_w = hours_w + colon_w + minutes_w
            start_x = (width - total_w) // 2

            time_y = height - 8  # Bottom of display

            # Render hours
            hours_frame = self._helpers.render_text(
                hours_str,
                x=start_x,
                y=time_y,
                color=self._time_color,
                font_name="SYSTEM",
            )
            frame = self._helpers.composite_frames(frame, hours_frame)

            # Render blinking colon
            blink_state = (int(time.time() * 1000) // 500) % 2
            if blink_state == 0:
                colon_frame = self._helpers.render_text(
                    colon_str,
                    x=start_x + hours_w,
                    y=time_y,
                    color=self._time_color,
                    font_name="SYSTEM",
                )
                frame = self._helpers.composite_frames(frame, colon_frame)

            # Render minutes
            minutes_frame = self._helpers.render_text(
                minutes_str,
                x=start_x + hours_w + colon_w,
                y=time_y,
                color=self._time_color,
                font_name="SYSTEM",
            )
            frame = self._helpers.composite_frames(frame, minutes_frame)

        return frame

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render the next eyes animation frame.

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode, or None to signal completion.
        """
        if self._frames_rendered >= self._max_frames:
            return None

        if self._frames_rendered == 0:
            logger.info("[eyes] Start rendering")
            self._width = width
            self._height = height

        # Update animation state
        self._update_animation()

        # Render
        frame = self._render(width, height)
        self._frames_rendered += 1
        return frame

    async def cleanup(self) -> None:
        """Reset animation state for next activation."""
        self._frames_rendered = 0
