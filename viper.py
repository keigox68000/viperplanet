import pyxel
import random
from enum import Enum, auto
import math

# --- ゲーム設定 (GAME_CONFIG) ---
# ゲームのバランスに関わる数値をここに集約
GAME_CONFIG = {
    "screen": {"width": 480, "height": 360},
    "player": {"speed": 2.5},
    "slogger": {"speed": 5, "turn_dist": 140},
    "snake": {
        "columns": 5,
        "max_count": 12,
        "min_len": 6,
        "max_len": 15,
        "move_speed": 4,
        "pause_time": 20,  # 攻撃前の最小待機フレーム
        "max_wait_time": 75,  # 攻撃前の最大待機フレーム
        "base_venom_speed": 3.0,
        "venom_speed_increment": 0.25,
    },
    "scorpion": {
        "initial_speed": 0.4,
        "speed_increase_interval": 600,  # 10秒ごとに速度アップ
        "speed_increase_amount": 0.1,  # 速度の増加量
        "concurrency_increase_interval": 1200,  # 20秒ごとに出現数増加
        "blink_duration": 120,  # 点滅している時間
        "chase_interval": 40,  # 動きの方向を変える間隔
    },
    "obstacles": {
        "rock_min": 6,
        "rock_max": 8,
        "cactus_min": 8,
        "cactus_max": 12,
    },
    "particles": {"count": 25, "lifespan_min": 20, "lifespan_max": 40},
    "wave_start_duration": 120,  # WAVE開始メッセージの表示時間 (2秒)
}

# --- グローバル定数 ---
SPRITE_IMAGE_BANK = 0
TRANSPARENT_COLOR = 0
SNAKE_AREA_WIDTH = GAME_CONFIG["snake"]["columns"] * 16
FIELD_X_MIN = SNAKE_AREA_WIDTH
FIELD_X_MAX = GAME_CONFIG["screen"]["width"] - SNAKE_AREA_WIDTH

# --- スプライト定義 ---
SPRITES = {
    "PLAYER_1": {"u": 0, "v": 0, "w": 16, "h": 16},
    "PLAYER_2": {"u": 16, "v": 0, "w": 16, "h": 16},
    "PLAYER_CORPSE": {"u": 48, "v": 0, "w": 16, "h": 16},
    "SLOGGER": {"u": 16, "v": 96, "w": 16, "h": 16},
    "ROCK": {"u": 32, "v": 96, "w": 16, "h": 16},
    "CACTUS": {"u": 48, "v": 96, "w": 16, "h": 16},
    "SNAKE_HEAD": {"u": 0, "v": 80, "w": 16, "h": 16},
    "SNAKE_BODY": {"u": 0, "v": 96, "w": 16, "h": 16},
    "VENOM_1": {"u": 16, "v": 80, "w": 16, "h": 8},
    "VENOM_2": {"u": 16, "v": 88, "w": 16, "h": 8},
    "SCORPION_1": {"u": 32, "v": 80, "w": 16, "h": 16},
    "SCORPION_2": {"u": 48, "v": 80, "w": 16, "h": 16},
    "SCORPION_CORPSE": {"u": 64, "v": 80, "w": 16, "h": 16},
}


# --- 状態管理 ---
class GameState(Enum):
    PLAYING, GAME_OVER, WAVE_START = auto(), auto(), auto()


class SnakeState(Enum):
    INACTIVE, EXTENDING, PAUSING, RETRACTING, DYING = (
        auto(),
        auto(),
        auto(),
        auto(),
        auto(),
    )


class SloggerState(Enum):
    READY, ACTIVE = auto(), auto()


class ScorpionState(Enum):
    SPAWNING, ACTIVE, DEAD = auto(), auto(), auto()


# --- クラス定義 ---


class Particle:
    """パーティクルエフェクトを管理するクラス"""

    def __init__(self, x, y, color=None):
        self.x, self.y = x, y
        self.vx = random.uniform(-2.5, 2.5)
        self.vy = random.uniform(-2.5, 2.5)
        self.color = color if color is not None else random.randint(8, 15)
        self.lifespan = random.randint(
            GAME_CONFIG["particles"]["lifespan_min"],
            GAME_CONFIG["particles"]["lifespan_max"],
        )

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.lifespan -= 1

    def draw(self):
        pyxel.pset(self.x, self.y, self.color)


class Obstacle:
    """動かない障害物の基底クラス"""

    def __init__(self, x, y, sprite_key):
        self.sprite = SPRITES[sprite_key]
        self.x, self.y = x, y
        self.w, self.h = self.sprite["w"], self.sprite["h"]
        self.is_active = True

    def draw(self):
        if self.is_active:
            pyxel.blt(
                self.x,
                self.y,
                SPRITE_IMAGE_BANK,
                self.sprite["u"],
                self.sprite["v"],
                self.w,
                self.h,
                TRANSPARENT_COLOR,
            )

    def get_rect(self):
        return self.x, self.y, self.w, self.h


class Rock(Obstacle):
    def __init__(self, x, y):
        super().__init__(x, y, "ROCK")


class Cactus(Obstacle):
    def __init__(self, x, y):
        super().__init__(x, y, "CACTUS")

    def destroy(self):
        self.is_active = False


class Player:
    """プレイヤー「カエルくん」を管理するクラス"""

    def __init__(self):
        self.w, self.h = SPRITES["PLAYER_1"]["w"], SPRITES["PLAYER_1"]["h"]
        self.reset()

    def reset(self):
        self.x = GAME_CONFIG["screen"]["width"] / 2 - self.w / 2
        self.y = GAME_CONFIG["screen"]["height"] - self.h * 2
        self.speed = GAME_CONFIG["player"]["speed"]
        self.facing_direction = 1
        self.move_direction_x, self.move_direction_y = 1, 0
        self.is_alive = True
        self.anim_timer = 0

    def update(self, obstacles):
        if not self.is_alive:
            return
        dx, dy = 0, 0

        if pyxel.btn(pyxel.KEY_LEFT) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_LEFT):
            dx -= 1
        if pyxel.btn(pyxel.KEY_RIGHT) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_RIGHT):
            dx += 1
        if pyxel.btn(pyxel.KEY_UP) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_UP):
            dy -= 1
        if pyxel.btn(pyxel.KEY_DOWN) or pyxel.btn(pyxel.GAMEPAD1_BUTTON_DPAD_DOWN):
            dy += 1

        is_moving = dx != 0 or dy != 0
        self.anim_timer = self.anim_timer + 1 if is_moving else 0

        if is_moving:
            dist = (dx**2 + dy**2) ** 0.5
            move_x, move_y = (dx / dist) * self.speed, (dy / dist) * self.speed
            self.x += move_x
            for obstacle in obstacles:
                if check_collision_rect_vs_rect(self.get_rect(), obstacle.get_rect()):
                    self.x -= move_x
                    break
            self.y += move_y
            for obstacle in obstacles:
                if check_collision_rect_vs_rect(self.get_rect(), obstacle.get_rect()):
                    self.y -= move_y
                    break
            self.move_direction_x, self.move_direction_y = dx / dist, dy / dist
            if dx != 0:
                self.facing_direction = dx

        self.x = max(FIELD_X_MIN, min(self.x, FIELD_X_MAX - self.w))
        self.y = max(0, min(self.y, GAME_CONFIG["screen"]["height"] - self.h))

    def draw(self):
        if self.is_alive:
            sprite = (
                SPRITES["PLAYER_1"]
                if (self.anim_timer // 4) % 2 == 0
                else SPRITES["PLAYER_2"]
            )
            w_flip = sprite["w"] * -self.facing_direction
            pyxel.blt(
                self.x,
                self.y,
                SPRITE_IMAGE_BANK,
                sprite["u"],
                sprite["v"],
                w_flip,
                sprite["h"],
                TRANSPARENT_COLOR,
            )
        else:
            sprite = SPRITES["PLAYER_CORPSE"]
            w_flip = sprite["w"] * -self.facing_direction
            pyxel.blt(
                self.x,
                self.y,
                SPRITE_IMAGE_BANK,
                sprite["u"],
                sprite["v"],
                w_flip,
                sprite["h"],
                TRANSPARENT_COLOR,
            )

    def get_rect(self):
        return self.x, self.y, self.w, self.h


class Slogger:
    """武器「カエルスラッガー」を管理するクラス"""

    def __init__(self):
        self.sprite = SPRITES["SLOGGER"]
        self.w, self.h = self.sprite["w"], self.sprite["h"]
        self.state = SloggerState.READY
        self.angle = 0

    def fire(self, player):
        if self.state == SloggerState.READY:
            self.state = SloggerState.ACTIVE
            self.x, self.y = (
                player.x + player.w / 2 - self.w / 2,
                player.y + player.h / 2 - self.h / 2,
            )
            self.vx, self.vy = (
                GAME_CONFIG["slogger"]["speed"] * player.move_direction_x,
                GAME_CONFIG["slogger"]["speed"] * player.move_direction_y,
            )
            self.dist_traveled, self.turn_dist, self.angle = (
                0,
                GAME_CONFIG["slogger"]["turn_dist"],
                0,
            )

    def update(self, player, rocks, cacti, particle_list):
        if self.state != SloggerState.ACTIVE:
            return
        self.angle = (self.angle + 30) % 360

        slogger_center_x = self.x + self.w / 2
        slogger_center_y = self.y + self.h / 2

        for rock in rocks:
            if check_collision_rect_vs_rect(self.get_rect(), rock.get_rect()):
                for _ in range(GAME_CONFIG["particles"]["count"] // 4):
                    particle_list.append(
                        Particle(slogger_center_x, slogger_center_y, 7)
                    )
                self.bounce()
                break

        for cactus in cacti:
            if cactus.is_active and check_collision_rect_vs_rect(
                self.get_rect(), cactus.get_rect()
            ):
                for _ in range(GAME_CONFIG["particles"]["count"]):
                    particle_list.append(
                        Particle(cactus.x + cactus.w / 2, cactus.y + cactus.h / 2)
                    )
                cactus.destroy()
                self.deactivate()
                return

        if self.dist_traveled <= self.turn_dist:
            self.x, self.y = self.x + self.vx, self.y + self.vy
            self.dist_traveled += (self.vx**2 + self.vy**2) ** 0.5
        else:
            p_center_x, p_center_y = player.x + player.w / 2, player.y + player.h / 2
            s_center_x, s_center_y = self.x + self.w / 2, self.y + self.h / 2
            dx, dy = p_center_x - s_center_x, p_center_y - s_center_y
            dist = (dx**2 + dy**2) ** 0.5
            if dist < GAME_CONFIG["slogger"]["speed"]:
                self.deactivate()
            else:
                self.x, self.y = (
                    self.x + (dx / dist) * GAME_CONFIG["slogger"]["speed"],
                    self.y + (dy / dist) * GAME_CONFIG["slogger"]["speed"],
                )

        if self.x < -self.w - 32 or self.x > GAME_CONFIG["screen"]["width"] + 32:
            self.deactivate()

    def bounce(self):
        if self.dist_traveled <= self.turn_dist:
            self.dist_traveled = self.turn_dist + 1
            self.vx *= -1
            self.vy *= -1

    def draw(self):
        if self.state == SloggerState.ACTIVE:
            pyxel.blt(
                self.x,
                self.y,
                SPRITE_IMAGE_BANK,
                self.sprite["u"],
                self.sprite["v"],
                self.w,
                self.h,
                TRANSPARENT_COLOR,
                self.angle,
                1,
            )

    def get_rect(self):
        return self.x, self.y, self.w, self.h

    def deactivate(self):
        self.state = SloggerState.READY


class Venom:
    """ヘビが発射する毒を管理するクラス"""

    def __init__(self, x, y, direction, speed):
        self.x, self.y, self.direction = x, y, direction
        self.w, self.h = SPRITES["VENOM_1"]["w"], SPRITES["VENOM_1"]["h"]
        self.speed, self.is_active = speed, True

    def update(self):
        if not self.is_active:
            return
        self.x += self.speed * self.direction

        if self.direction > 0:
            if self.x + self.w >= FIELD_X_MAX:
                self.is_active = False
        else:
            if self.x - self.w <= FIELD_X_MIN:
                self.is_active = False

    def draw(self):
        if not self.is_active:
            return
        sprite_key = "VENOM_1" if (pyxel.frame_count // 4) % 2 == 0 else "VENOM_2"
        s = SPRITES[sprite_key]
        draw_w = s["w"] * self.direction
        pyxel.blt(
            self.x,
            self.y,
            SPRITE_IMAGE_BANK,
            s["u"],
            s["v"],
            draw_w,
            s["h"],
            TRANSPARENT_COLOR,
        )

    def get_rect(self):
        return (
            (self.x - self.w, self.y, self.w, self.h)
            if self.direction < 0
            else (self.x, self.y, self.w, self.h)
        )


class Snake:
    """敵であるヘビ一体を管理するクラス"""

    def __init__(self):
        self.state = SnakeState.INACTIVE
        self.sprite_head, self.sprite_body = (
            SPRITES["SNAKE_HEAD"],
            SPRITES["SNAKE_BODY"],
        )
        self.w, self.h = self.sprite_head["w"], self.sprite_head["h"]
        self.dying_speed = 2
        self.movement_timer = 0
        self.action_timer = 0

    def spawn(self, column_id):
        self.column_id, self.state = column_id, SnakeState.EXTENDING
        side, column_index = self.column_id
        self.direction, self.y_direction = side, random.choice([-1, 1])
        self.x = (
            column_index * self.w
            if self.direction == 1
            else GAME_CONFIG["screen"]["width"] - (column_index + 1) * self.w
        )
        self.head_y = (
            -self.h if self.y_direction == 1 else GAME_CONFIG["screen"]["height"]
        )
        self.max_length = random.randint(
            GAME_CONFIG["snake"]["min_len"], GAME_CONFIG["snake"]["max_len"]
        )
        self.speed = GAME_CONFIG["snake"]["move_speed"]
        self.body_parts = []

    def update(self, player, global_venom_list, venom_speed):
        if self.state == SnakeState.INACTIVE:
            return

        if self.state == SnakeState.DYING:
            self.action_timer += 1
            if self.action_timer >= self.dying_speed:
                self.action_timer = 0
                if self.body_parts:
                    self.body_parts.pop()
                else:
                    self.kill()
            return

        if self.state == SnakeState.PAUSING:
            self.action_timer += 1
            player_rect = player.get_rect()
            player_aligned = (
                player_rect[1] < self.head_y + self.h
                and player_rect[1] + player_rect[3] > self.head_y
            )
            fire_chance = 0.8 if player_aligned else 0.05
            if (
                self.action_timer > GAME_CONFIG["snake"]["pause_time"]
                and random.random() < fire_chance
            ):
                self.fire_and_retreat(global_venom_list, venom_speed)
            elif self.action_timer > GAME_CONFIG["snake"]["max_wait_time"]:
                self.fire_and_retreat(global_venom_list, venom_speed)
            return

        self.movement_timer += 1
        if self.movement_timer < self.speed:
            return
        self.movement_timer = 0

        if self.state == SnakeState.EXTENDING:
            if len(self.body_parts) < self.max_length:
                self.body_parts.append(self.head_y)
                self.head_y += self.h * self.y_direction
            else:
                self.state, self.action_timer = SnakeState.PAUSING, 0
        elif self.state == SnakeState.RETRACTING:
            if self.body_parts:
                self.head_y = self.body_parts.pop()
            else:
                self.head_y -= self.h * self.y_direction
                if (self.y_direction == 1 and self.head_y < -self.h) or (
                    self.y_direction == -1
                    and self.head_y > GAME_CONFIG["screen"]["height"]
                ):
                    self.kill()

    def fire_and_retreat(self, global_venom_list, venom_speed):
        venom_x = self.x + self.w if self.direction == 1 else self.x
        venom_y = self.head_y + (self.h - SPRITES["VENOM_1"]["h"]) / 2
        global_venom_list.append(Venom(venom_x, venom_y, self.direction, venom_speed))
        self.state = SnakeState.RETRACTING

    def draw(self):
        if self.state == SnakeState.INACTIVE:
            return
        w_flip, h_flip = self.w * -self.direction, self.h * -self.y_direction
        for y_pos in self.body_parts:
            pyxel.blt(
                self.x,
                y_pos,
                SPRITE_IMAGE_BANK,
                self.sprite_body["u"],
                self.sprite_body["v"],
                w_flip,
                h_flip,
                TRANSPARENT_COLOR,
            )
        if self.state != SnakeState.DYING:
            pyxel.blt(
                self.x,
                self.head_y,
                SPRITE_IMAGE_BANK,
                self.sprite_head["u"],
                self.sprite_head["v"],
                w_flip,
                h_flip,
                TRANSPARENT_COLOR,
            )

    def get_head_rect(self):
        return self.x, self.head_y, self.w, self.h

    def get_body_rects(self):
        return [(self.x, y, self.w, self.h) for y in self.body_parts]

    def head_shot(self):
        self.state, self.action_timer = SnakeState.DYING, 0

    def kill(self):
        self.state, self.column_id = SnakeState.INACTIVE, None


class Scorpion:
    """敵であるサソリを管理するクラス"""

    def __init__(self):
        self.w, self.h = 16, 16
        self.state = ScorpionState.DEAD
        self.x, self.y = -100, -100
        self.timer = 0
        self.facing_direction = 1
        self.move_dx, self.move_dy = 0, 0

    def spawn(self, obstacles):
        while True:
            self.x = random.randint(FIELD_X_MIN, FIELD_X_MAX - self.w)
            self.y = random.randint(16, GAME_CONFIG["screen"]["height"] - 16 - self.h)
            is_overlapping = False
            for obs in obstacles:
                if check_collision_rect_vs_rect(self.get_rect(), obs.get_rect()):
                    is_overlapping = True
                    break
            if not is_overlapping:
                break

        self.state = ScorpionState.SPAWNING
        self.timer = 0
        self.facing_direction = 1

    def update(self, player, obstacles, speed):
        if self.state == ScorpionState.DEAD:
            return

        self.timer += 1

        if self.state == ScorpionState.SPAWNING:
            if self.timer > GAME_CONFIG["scorpion"]["blink_duration"]:
                self.state = ScorpionState.ACTIVE
                self.timer = 0
            return

        if self.state == ScorpionState.ACTIVE:
            if self.timer % GAME_CONFIG["scorpion"]["chase_interval"] == 0:
                if random.random() < 0.75:
                    dx, dy = player.x - self.x, player.y - self.y
                else:
                    angle = random.uniform(0, 2 * math.pi)
                    dx, dy = math.cos(angle), math.sin(angle)

                dist = (dx**2 + dy**2) ** 0.5
                if dist > 0:
                    self.move_dx, self.move_dy = dx / dist, dy / dist
                    self.facing_direction = 1 if self.move_dx < 0 else -1

            new_x = self.x + self.move_dx * speed
            new_y = self.y + self.move_dy * speed

            original_x, original_y = self.x, self.y
            self.x = new_x
            for obs in obstacles:
                if check_collision_rect_vs_rect(self.get_rect(), obs.get_rect()):
                    self.x = original_x
                    break
            self.y = new_y
            for obs in obstacles:
                if check_collision_rect_vs_rect(self.get_rect(), obs.get_rect()):
                    self.y = original_y
                    break

            self.x = max(FIELD_X_MIN, min(self.x, FIELD_X_MAX - self.w))
            self.y = max(0, min(self.y, GAME_CONFIG["screen"]["height"] - self.h))

    def draw(self):
        if self.state == ScorpionState.DEAD:
            if self.x > -100:
                s = SPRITES["SCORPION_CORPSE"]
                pyxel.blt(
                    self.x,
                    self.y,
                    SPRITE_IMAGE_BANK,
                    s["u"],
                    s["v"],
                    s["w"] * self.facing_direction,
                    s["h"],
                    TRANSPARENT_COLOR,
                )
            return

        if self.state == ScorpionState.SPAWNING and (self.timer // 4) % 2 != 0:
            return

        sprite_key = "SCORPION_1" if (self.timer // 8) % 2 == 0 else "SCORPION_2"
        s = SPRITES[sprite_key]
        pyxel.blt(
            self.x,
            self.y,
            SPRITE_IMAGE_BANK,
            s["u"],
            s["v"],
            s["w"] * self.facing_direction,
            s["h"],
            TRANSPARENT_COLOR,
        )

    def die(self):
        self.state = ScorpionState.DEAD

    def get_rect(self):
        return self.x, self.y, self.w, self.h


class App:
    """ゲーム全体の管理クラス"""

    def __init__(self):
        pyxel.init(
            GAME_CONFIG["screen"]["width"],
            GAME_CONFIG["screen"]["height"],
            title="Snake World Proto",
            fps=60,
        )
        try:
            pyxel.load("my_resource.pyxres")
        except FileNotFoundError:
            print("エラー: 'my_resource.pyxres' が見つかりません。")
            pyxel.quit()
            return
        self.setup()
        pyxel.run(self.update, self.draw)

    def setup(self):
        self.player = Player()
        self.slogger = Slogger()
        self.snakes = [Snake() for _ in range(GAME_CONFIG["snake"]["max_count"])]
        self.active_scorpions = []
        self.scorpion_corpses = []
        self.rocks, self.cacti = [], []
        self.particles = []
        self.venoms = []
        self.game_state = GameState.PLAYING
        self.snake_spawn_timer = 0

        # WAVE & Scorpion Management
        self.wave = 0
        self.snakes_defeated_in_wave = 0
        self.snakes_to_defeat_for_next_wave = 0
        self.max_concurrent_snakes = 0
        self.current_venom_speed = 0
        self.wave_max_scorpions = 0
        self.current_scorpion_speed = 0
        self.scorpion_speed_timer = 0
        self.scorpion_concurrency_timer = 0
        self.wave_start_timer = 0
        self.start_new_wave()

    def start_new_wave(self):
        """新しいWAVEを開始する処理"""
        self.wave += 1
        self.game_state = GameState.WAVE_START
        self.wave_start_timer = GAME_CONFIG["wave_start_duration"]

        self.rocks.clear()
        self.cacti.clear()
        self.venoms.clear()
        self.particles.clear()
        self.scorpion_corpses.clear()
        self.active_scorpions.clear()

        for s in self.snakes:
            s.state = SnakeState.INACTIVE
        self.place_obstacles()

        # Snake difficulty
        self.snakes_defeated_in_wave = 0
        self.snakes_to_defeat_for_next_wave = 2 + self.wave
        self.max_concurrent_snakes = self.wave
        self.current_venom_speed = (
            GAME_CONFIG["snake"]["base_venom_speed"]
            + (self.wave - 1) * GAME_CONFIG["snake"]["venom_speed_increment"]
        )

        # Scorpion difficulty
        self.wave_max_scorpions = 1 + (self.wave - 1) // 3
        self.current_scorpion_speed = GAME_CONFIG["scorpion"]["initial_speed"]
        self.scorpion_speed_timer = 0
        self.scorpion_concurrency_timer = 0

    def place_obstacles(self):
        min_x = FIELD_X_MIN
        max_x = FIELD_X_MAX - 16
        min_y, max_y = 32, GAME_CONFIG["screen"]["height"] - 48

        for _ in range(
            random.randint(
                GAME_CONFIG["obstacles"]["rock_min"],
                GAME_CONFIG["obstacles"]["rock_max"],
            )
        ):
            for _ in range(100):
                x, y = (
                    random.randint(min_x // 16, max_x // 16) * 16,
                    random.randint(min_y // 16, max_y // 16) * 16,
                )
                new_rect = (x, y, 16, 16)
                if not any(
                    check_collision_rect_vs_rect(new_rect, r.get_rect())
                    for r in self.rocks
                ):
                    self.rocks.append(Rock(x, y))
                    break

        for _ in range(
            random.randint(
                GAME_CONFIG["obstacles"]["cactus_min"],
                GAME_CONFIG["obstacles"]["cactus_max"],
            )
        ):
            for _ in range(100):
                x, y = (
                    random.randint(min_x // 16, max_x // 16) * 16,
                    random.randint(min_y // 16, max_y // 16) * 16,
                )
                new_rect = (x, y, 16, 16)
                if not any(
                    check_collision_rect_vs_rect(new_rect, r.get_rect())
                    for r in self.rocks
                ) and not any(
                    check_collision_rect_vs_rect(new_rect, c.get_rect())
                    for c in self.cacti
                ):
                    self.cacti.append(Cactus(x, y))
                    break

    def update(self):
        if self.game_state == GameState.WAVE_START:
            self.wave_start_timer -= 1
            if self.wave_start_timer <= 0:
                self.game_state = GameState.PLAYING
        elif self.game_state == GameState.PLAYING:
            self.update_playing()
        elif self.game_state == GameState.GAME_OVER:
            if self.is_action_pressed():
                self.setup()

    def update_playing(self):
        player_movement_obstacles = self.rocks + [c for c in self.cacti if c.is_active]
        self.player.update(player_movement_obstacles)

        self.slogger.update(self.player, self.rocks, self.cacti, self.particles)
        if self.is_action_pressed():
            self.slogger.fire(self.player)

        self.spawn_snakes()
        for snake in self.snakes:
            snake.update(self.player, self.venoms, self.current_venom_speed)

        self.update_scorpions()

        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.lifespan > 0]

        for v in self.venoms:
            v.update()
        self.venoms = [v for v in self.venoms if v.is_active]

        self.check_collisions()

    def update_scorpions(self):
        # 時間経過で速度を上げる
        self.scorpion_speed_timer += 1
        if (
            self.scorpion_speed_timer
            >= GAME_CONFIG["scorpion"]["speed_increase_interval"]
        ):
            self.current_scorpion_speed += GAME_CONFIG["scorpion"][
                "speed_increase_amount"
            ]
            self.scorpion_speed_timer = 0

        # 時間経過でサソリをスポーンさせる
        self.scorpion_concurrency_timer += 1
        if (
            self.scorpion_concurrency_timer
            >= GAME_CONFIG["scorpion"]["concurrency_increase_interval"]
        ):
            self.scorpion_concurrency_timer = 0
            if len(self.active_scorpions) < self.wave_max_scorpions:
                new_scorpion = Scorpion()
                all_spawn_obstacles = (
                    self.rocks
                    + self.cacti
                    + self.scorpion_corpses
                    + self.active_scorpions
                )
                new_scorpion.spawn(all_spawn_obstacles)
                self.active_scorpions.append(new_scorpion)

        # アクティブなサソリを更新
        all_scorpion_obstacles = self.rocks + self.cacti + self.scorpion_corpses
        for scorp in self.active_scorpions:
            scorp.update(
                self.player, all_scorpion_obstacles, self.current_scorpion_speed
            )

    def is_action_pressed(self):
        return (
            pyxel.btnp(pyxel.KEY_CTRL)
            or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_A)
            or pyxel.btnp(pyxel.GAMEPAD1_BUTTON_B)
            or pyxel.btnp(pyxel.GAMEPAD2_BUTTON_A)
            or pyxel.btnp(pyxel.GAMEPAD2_BUTTON_B)
        )

    def spawn_snakes(self):
        self.snake_spawn_timer += 1
        if self.snake_spawn_timer <= 60:
            return
        self.snake_spawn_timer = 0

        active_snakes = len([s for s in self.snakes if s.state != SnakeState.INACTIVE])
        if active_snakes >= self.max_concurrent_snakes:
            return

        occupied_columns = {
            s.column_id for s in self.snakes if s.state != SnakeState.INACTIVE
        }
        all_columns = [
            (side, i)
            for side in [1, -1]
            for i in range(GAME_CONFIG["snake"]["columns"])
        ]
        available_columns = [c for c in all_columns if c not in occupied_columns]
        if not available_columns:
            return
        inactive_snake = next(
            (s for s in self.snakes if s.state == SnakeState.INACTIVE), None
        )
        if inactive_snake:
            inactive_snake.spawn(random.choice(available_columns))

    def check_collisions(self):
        self.check_player_collisions()
        self.check_slogger_collisions()
        self.check_venom_collisions()

    def check_player_collisions(self):
        if not self.player.is_alive:
            return
        player_rect = self.player.get_rect()

        for s in self.snakes:
            if s.state in [SnakeState.INACTIVE, SnakeState.DYING]:
                continue
            if check_collision_rect_vs_rect(player_rect, s.get_head_rect()):
                self.game_over()
                return
            for body_rect in s.get_body_rects():
                if check_collision_rect_vs_rect(player_rect, body_rect):
                    self.game_over()
                    return

        for v in self.venoms:
            if v.is_active and check_collision_rect_vs_rect(player_rect, v.get_rect()):
                self.game_over()
                return

        for scorp in self.active_scorpions:
            if scorp.state == ScorpionState.ACTIVE and check_collision_rect_vs_rect(
                player_rect, scorp.get_rect()
            ):
                self.game_over()
                return

        for corpse in self.scorpion_corpses:
            if check_collision_rect_vs_rect(player_rect, corpse.get_rect()):
                self.game_over()
                return

    def check_slogger_collisions(self):
        if self.slogger.state != SloggerState.ACTIVE:
            return
        slogger_rect = self.slogger.get_rect()

        for s in self.snakes:
            if s.state in [SnakeState.INACTIVE, SnakeState.DYING]:
                continue
            if check_collision_rect_vs_rect(slogger_rect, s.get_head_rect()):
                self.create_particle_burst(s.x + s.w / 2, s.head_y + s.h / 2)
                s.head_shot()
                self.slogger.deactivate()

                self.snakes_defeated_in_wave += 1
                if self.snakes_defeated_in_wave >= self.snakes_to_defeat_for_next_wave:
                    self.start_new_wave()
                return

            for body_rect in s.get_body_rects():
                if check_collision_rect_vs_rect(slogger_rect, body_rect):
                    self.slogger.bounce()
                    break

        scorpions_to_kill = []
        for scorp in self.active_scorpions:
            if scorp.state == ScorpionState.ACTIVE and check_collision_rect_vs_rect(
                slogger_rect, scorp.get_rect()
            ):
                self.create_particle_burst(scorp.x + scorp.w / 2, scorp.y + scorp.h / 2)
                scorp.die()
                scorpions_to_kill.append(scorp)
                self.slogger.deactivate()
                break

        if scorpions_to_kill:
            for scorp in scorpions_to_kill:
                self.active_scorpions.remove(scorp)
                self.scorpion_corpses.append(scorp)

    def check_venom_collisions(self):
        for v in self.venoms:
            if not v.is_active:
                continue
            venom_rect = v.get_rect()
            all_obstacles = self.rocks + [c for c in self.cacti if c.is_active]
            for obstacle in all_obstacles:
                if check_collision_rect_vs_rect(venom_rect, obstacle.get_rect()):
                    v.is_active = False
                    particle_x = v.get_rect()[0] + v.w / 2
                    particle_y = v.get_rect()[1] + v.h / 2
                    for _ in range(GAME_CONFIG["particles"]["count"] // 4):
                        self.particles.append(Particle(particle_x, particle_y, 7))
                    break

    def create_particle_burst(self, x, y):
        for _ in range(GAME_CONFIG["particles"]["count"]):
            self.particles.append(Particle(x, y))

    def game_over(self):
        if self.player.is_alive:
            self.player.is_alive = False
            self.game_state = GameState.GAME_OVER
            player_center_x = self.player.x + self.player.w / 2
            player_center_y = self.player.y + self.player.h / 2
            for _ in range(GAME_CONFIG["particles"]["count"]):
                self.particles.append(Particle(player_center_x, player_center_y, 7))

    def draw(self):
        pyxel.cls(0)
        self.player.draw()
        self.slogger.draw()
        for rock in self.rocks:
            rock.draw()
        for cactus in self.cacti:
            cactus.draw()
        for snake in self.snakes:
            snake.draw()
        for scorp in self.active_scorpions:
            scorp.draw()
        for corpse in self.scorpion_corpses:
            corpse.draw()
        for p in self.particles:
            p.draw()
        for v in self.venoms:
            v.draw()

        wave_text = f"WAVE {self.wave} ({self.snakes_defeated_in_wave}/{self.snakes_to_defeat_for_next_wave})"
        pyxel.text(
            GAME_CONFIG["screen"]["width"] - len(wave_text) * pyxel.FONT_WIDTH - 5,
            5,
            wave_text,
            7,
        )

        if self.game_state == GameState.WAVE_START:
            text = f"WAVE {self.wave}"
            x = (GAME_CONFIG["screen"]["width"] - len(text) * pyxel.FONT_WIDTH) / 2
            y = (GAME_CONFIG["screen"]["height"] - pyxel.FONT_HEIGHT) / 2
            pyxel.text(x, y, text, 7)
        elif self.game_state == GameState.GAME_OVER:
            text = "GAME OVER"
            x = GAME_CONFIG["screen"]["width"] / 2 - len(text) * pyxel.FONT_WIDTH / 2
            y = GAME_CONFIG["screen"]["height"] / 2 - pyxel.FONT_HEIGHT / 2
            pyxel.text(x, y, text, 7)


def check_collision_rect_vs_rect(rect1, rect2):
    """矩形同士の当たり判定を行うグローバル関数"""
    x1, y1, w1, h1 = rect1
    x2, y2, w2, h2 = rect2
    return x1 < x2 + w2 and x1 + w1 > x2 and y1 < y2 + h2 and y1 + h1 > y2


if __name__ == "__main__":
    App()
