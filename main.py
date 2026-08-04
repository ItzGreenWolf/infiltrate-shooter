#!/usr/bin/env python3
"""
Infiltrate - 2D Top-Down Shooter
Ready-to-play. Zero coding required from the user.
Controls:
  WASD / Arrow Keys - Move
  Mouse - Aim
  Left Click - Shoot / Use
  1 - Pistol
  2 - Assault Rifle
  3 - Knife
  4 - Grenade
  5 - C4 (place) / F - Detonate all placed C4
  R - Restart current level (if dead)
  ESC - Quit
"""

import pygame
import math
import random
import sys
from pygame import mixer

# ==================== INIT ====================
pygame.init()

# Audio may fail on some systems / headless environments — fail gracefully
AUDIO_OK = True
try:
    mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
except pygame.error:
    AUDIO_OK = False
    print("Audio device not available — game will run silently.")

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Infiltrate - Clear the Building")
clock = pygame.time.Clock()

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (220, 50, 50)
DARK_RED = (140, 20, 20)
GREEN = (50, 200, 80)
DARK_GREEN = (20, 120, 40)
BLUE = (50, 100, 220)
YELLOW = (240, 220, 50)
ORANGE = (240, 140, 30)
GRAY = (80, 80, 90)
DARK_GRAY = (40, 40, 50)
LIGHT_GRAY = (160, 160, 170)
BROWN = (120, 80, 40)
FLOOR = (35, 38, 45)
WALL = (25, 28, 35)

# ==================== SOUND GENERATION ====================
class DummySound:
    def play(self): pass

def make_sound(frequency, duration_ms, volume=0.4, wave="square", noise=False):
    """Generate a simple procedural sound. Returns DummySound if audio unavailable."""
    if not AUDIO_OK:
        return DummySound()
    sample_rate = 22050
    n_samples = int(sample_rate * duration_ms / 1000)
    buf = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        if noise:
            val = random.randint(-32767, 32767) * volume
        else:
            if wave == "square":
                val = 32767 * volume if math.sin(2 * math.pi * frequency * t) > 0 else -32767 * volume
            elif wave == "saw":
                val = 32767 * volume * (2 * (t * frequency - math.floor(t * frequency + 0.5)))
            else:  # sine
                val = 32767 * volume * math.sin(2 * math.pi * frequency * t)
            # simple envelope
            env = 1.0
            if i < n_samples * 0.1:
                env = i / (n_samples * 0.1)
            elif i > n_samples * 0.7:
                env = 1.0 - (i - n_samples * 0.7) / (n_samples * 0.3)
            val *= env
        sample = int(max(-32767, min(32767, val)))
        buf += sample.to_bytes(2, "little", signed=True)
        buf += sample.to_bytes(2, "little", signed=True)  # stereo
    try:
        sound = mixer.Sound(buffer=bytes(buf))
        return sound
    except Exception:
        return DummySound()

# Pre-generate sounds
snd_pistol = make_sound(800, 80, 0.35, "square")
snd_assault = make_sound(600, 50, 0.25, "square")
snd_knife = make_sound(200, 60, 0.4, "saw")
snd_grenade_throw = make_sound(300, 100, 0.3, "sine")
snd_explosion = make_sound(60, 400, 0.5, noise=True)
snd_hit = make_sound(150, 40, 0.3, "square")
snd_player_hit = make_sound(120, 120, 0.45, "saw")
snd_enemy_die = make_sound(90, 200, 0.4, noise=True)
snd_level_complete = make_sound(440, 150, 0.35, "sine")
snd_empty = make_sound(100, 60, 0.2, "square")
snd_c4_place = make_sound(250, 80, 0.3, "sine")
snd_c4_beep = make_sound(900, 40, 0.25, "square")

# ==================== WEAPONS ====================
class Weapon:
    def __init__(self, name, damage, fire_rate, ammo, max_ammo, is_auto=False, is_melee=False, is_throwable=False, is_placeable=False):
        self.name = name
        self.damage = damage
        self.fire_rate = fire_rate  # ms between shots
        self.ammo = ammo
        self.max_ammo = max_ammo
        self.is_auto = is_auto
        self.is_melee = is_melee
        self.is_throwable = is_throwable
        self.is_placeable = is_placeable
        self.last_shot = 0

WEAPONS = {
    1: Weapon("Pistol", 25, 280, 48, 48, is_auto=False),
    2: Weapon("Assault Rifle", 14, 95, 120, 120, is_auto=True),
    3: Weapon("Knife", 55, 350, 999, 999, is_melee=True),
    4: Weapon("Grenade", 80, 600, 6, 6, is_throwable=True),
    5: Weapon("C4", 120, 400, 4, 4, is_placeable=True),
}

# ==================== ENTITIES ====================
class Bullet:
    def __init__(self, x, y, angle, speed, damage, owner="player", color=YELLOW):
        self.x = x
        self.y = y
        self.angle = angle
        self.speed = speed
        self.damage = damage
        self.owner = owner
        self.color = color
        self.radius = 4
        self.alive = True
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed

    def update(self, walls):
        self.x += self.vx
        self.y += self.vy
        # wall collision
        for w in walls:
            if w.collidepoint(self.x, self.y):
                self.alive = False
                return
        if self.x < 0 or self.x > SCREEN_WIDTH or self.y < 0 or self.y > SCREEN_HEIGHT:
            self.alive = False

    def draw(self, surface):
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.radius)

class Grenade:
    def __init__(self, x, y, angle, speed=7):
        self.x = x
        self.y = y
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.timer = 90  # frames until explode
        self.alive = True
        self.radius = 8
        self.exploded = False

    def update(self, walls):
        if self.exploded:
            return
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.97
        self.vy *= 0.97
        self.timer -= 1
        # simple bounce off walls
        for w in walls:
            if w.collidepoint(self.x, self.y):
                # rough bounce
                if abs(self.x - w.left) < 10 or abs(self.x - w.right) < 10:
                    self.vx *= -0.6
                if abs(self.y - w.top) < 10 or abs(self.y - w.bottom) < 10:
                    self.vy *= -0.6
                self.x += self.vx
                self.y += self.vy
        if self.timer <= 0:
            self.exploded = True
            self.alive = False

    def draw(self, surface):
        if not self.exploded:
            pygame.draw.circle(surface, DARK_GREEN, (int(self.x), int(self.y)), self.radius)
            pygame.draw.circle(surface, GREEN, (int(self.x), int(self.y)), self.radius - 2)

class C4Charge:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.alive = True
        self.beep_timer = 0
        self.radius = 10

    def update(self):
        self.beep_timer += 1
        if self.beep_timer % 40 == 0:
            snd_c4_beep.play()

    def draw(self, surface):
        pygame.draw.rect(surface, DARK_RED, (self.x - 8, self.y - 6, 16, 12))
        pygame.draw.rect(surface, RED, (self.x - 6, self.y - 4, 12, 8))
        # LED
        if (self.beep_timer // 20) % 2 == 0:
            pygame.draw.circle(surface, YELLOW, (int(self.x + 4), int(self.y - 2)), 2)

class Explosion:
    def __init__(self, x, y, radius=80, damage=80):
        self.x = x
        self.y = y
        self.max_radius = radius
        self.radius = 10
        self.damage = damage
        self.alive = True
        self.life = 20
        self.damaged = set()  # entities already hit

    def update(self):
        self.radius += (self.max_radius - self.radius) * 0.25
        self.life -= 1
        if self.life <= 0:
            self.alive = False

    def draw(self, surface):
        alpha = max(0, min(255, self.life * 12))
        # multiple rings
        for i, col in enumerate([(255, 180, 50), (255, 100, 30), (200, 50, 20)]):
            r = int(self.radius * (1 - i * 0.25))
            if r > 0:
                s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(s, (*col, alpha // (i + 1)), (r, r), r)
                surface.blit(s, (self.x - r, self.y - r))

class Enemy:
    def __init__(self, x, y, health=60, speed=1.4):
        self.x = x
        self.y = y
        self.health = health
        self.max_health = health
        self.speed = speed
        self.radius = 14
        self.alive = True
        self.angle = 0
        self.shoot_cooldown = random.randint(40, 90)
        self.color = RED
        self.hit_flash = 0

    def update(self, player, walls, bullets):
        if not self.alive:
            return
        # simple chase
        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            self.angle = math.atan2(dy, dx)
            # move if not too close
            if dist > 90:
                nx = self.x + math.cos(self.angle) * self.speed
                ny = self.y + math.sin(self.angle) * self.speed
                # wall check
                can_move = True
                for w in walls:
                    if w.collidepoint(nx, ny):
                        can_move = False
                        break
                if can_move:
                    self.x = nx
                    self.y = ny
            # shoot
            self.shoot_cooldown -= 1
            if self.shoot_cooldown <= 0 and dist < 420:
                self.shoot_cooldown = random.randint(50, 100)
                bullets.append(Bullet(self.x, self.y, self.angle, 7.5, 12, owner="enemy", color=ORANGE))
                snd_pistol.play()
        if self.hit_flash > 0:
            self.hit_flash -= 1

    def take_damage(self, dmg):
        self.health -= dmg
        self.hit_flash = 6
        snd_hit.play()
        if self.health <= 0:
            self.alive = False
            snd_enemy_die.play()

    def draw(self, surface):
        if not self.alive:
            return
        col = WHITE if self.hit_flash > 0 else self.color
        pygame.draw.circle(surface, col, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surface, DARK_RED, (int(self.x), int(self.y)), self.radius - 4)
        # facing direction
        ex = self.x + math.cos(self.angle) * 12
        ey = self.y + math.sin(self.angle) * 12
        pygame.draw.line(surface, WHITE, (self.x, self.y), (ex, ey), 3)
        # health bar
        if self.health < self.max_health:
            bw = 28
            pygame.draw.rect(surface, DARK_RED, (self.x - bw//2, self.y - 24, bw, 5))
            pygame.draw.rect(surface, GREEN, (self.x - bw//2, self.y - 24, int(bw * self.health / self.max_health), 5))

class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.radius = 13
        self.speed = 3.6
        self.health = 100
        self.max_health = 100
        self.angle = 0
        self.current_weapon = 1
        self.weapons = {k: Weapon(v.name, v.damage, v.fire_rate, v.ammo, v.max_ammo, v.is_auto, v.is_melee, v.is_throwable, v.is_placeable) for k, v in WEAPONS.items()}
        self.alive = True
        self.hit_flash = 0
        self.melee_active = 0  # frames remaining for knife swing

    def update(self, keys, walls):
        if not self.alive:
            return
        dx, dy = 0, 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx += 1
        if dx != 0 or dy != 0:
            length = math.hypot(dx, dy)
            dx /= length
            dy /= length
            nx = self.x + dx * self.speed
            ny = self.y + dy * self.speed
            # wall collision (simple circle vs rect)
            can_x = True
            can_y = True
            for w in walls:
                if w.collidepoint(nx, self.y):
                    can_x = False
                if w.collidepoint(self.x, ny):
                    can_y = False
            if can_x:
                self.x = nx
            if can_y:
                self.y = ny
        # keep in bounds
        self.x = max(self.radius, min(SCREEN_WIDTH - self.radius, self.x))
        self.y = max(self.radius, min(SCREEN_HEIGHT - self.radius, self.y))
        # aim
        mx, my = pygame.mouse.get_pos()
        self.angle = math.atan2(my - self.y, mx - self.x)
        if self.hit_flash > 0:
            self.hit_flash -= 1
        if self.melee_active > 0:
            self.melee_active -= 1

    def shoot(self, bullets, grenades, c4_list, current_time):
        if not self.alive:
            return
        w = self.weapons[self.current_weapon]
        if current_time - w.last_shot < w.fire_rate:
            return
        if w.ammo <= 0 and not w.is_melee:
            snd_empty.play()
            w.last_shot = current_time
            return

        if w.is_melee:
            # knife
            w.last_shot = current_time
            self.melee_active = 12
            snd_knife.play()
            # damage is handled in collision check
        elif w.is_throwable:
            # grenade
            w.ammo -= 1
            w.last_shot = current_time
            grenades.append(Grenade(self.x + math.cos(self.angle) * 20, self.y + math.sin(self.angle) * 20, self.angle, 8.5))
            snd_grenade_throw.play()
        elif w.is_placeable:
            # C4
            w.ammo -= 1
            w.last_shot = current_time
            c4_list.append(C4Charge(self.x + math.cos(self.angle) * 25, self.y + math.sin(self.angle) * 25))
            snd_c4_place.play()
        else:
            # guns
            w.ammo -= 1
            w.last_shot = current_time
            spread = 0.04 if self.current_weapon == 2 else 0.015
            ang = self.angle + random.uniform(-spread, spread)
            speed = 14 if self.current_weapon == 1 else 16
            bullets.append(Bullet(self.x + math.cos(self.angle) * 18, self.y + math.sin(self.angle) * 18, ang, speed, w.damage, owner="player"))
            if self.current_weapon == 1:
                snd_pistol.play()
            else:
                snd_assault.play()

    def take_damage(self, dmg):
        self.health -= dmg
        self.hit_flash = 8
        snd_player_hit.play()
        if self.health <= 0:
            self.health = 0
            self.alive = False

    def draw(self, surface):
        if not self.alive:
            return
        col = WHITE if self.hit_flash > 0 else BLUE
        pygame.draw.circle(surface, col, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surface, (30, 60, 160), (int(self.x), int(self.y)), self.radius - 4)
        # gun direction
        length = 18 if self.melee_active == 0 else 26
        gx = self.x + math.cos(self.angle) * length
        gy = self.y + math.sin(self.angle) * length
        pygame.draw.line(surface, LIGHT_GRAY, (self.x, self.y), (gx, gy), 4)
        if self.melee_active > 0:
            # knife arc indicator
            pygame.draw.circle(surface, (200, 200, 220), (int(gx), int(gy)), 6, 2)

# ==================== LEVELS ====================
def make_wall(x, y, w, h):
    return pygame.Rect(x, y, w, h)

def get_level(level_num):
    """Return walls, enemy list, player start for a level."""
    walls = []
    enemies = []
    # outer border always
    walls.append(make_wall(0, 0, SCREEN_WIDTH, 20))
    walls.append(make_wall(0, SCREEN_HEIGHT - 20, SCREEN_WIDTH, 20))
    walls.append(make_wall(0, 0, 20, SCREEN_HEIGHT))
    walls.append(make_wall(SCREEN_WIDTH - 20, 0, 20, SCREEN_HEIGHT))

    if level_num == 1:
        # simple open room
        walls.append(make_wall(300, 200, 40, 200))
        walls.append(make_wall(700, 300, 200, 40))
        walls.append(make_wall(500, 500, 40, 120))
        enemies = [
            Enemy(400, 150),
            Enemy(900, 200),
            Enemy(600, 450),
            Enemy(1000, 500),
        ]
        start = (100, 100)
    elif level_num == 2:
        # more cover
        walls.append(make_wall(200, 150, 30, 250))
        walls.append(make_wall(400, 100, 180, 30))
        walls.append(make_wall(550, 250, 30, 200))
        walls.append(make_wall(750, 180, 30, 280))
        walls.append(make_wall(300, 500, 250, 30))
        walls.append(make_wall(900, 400, 200, 30))
        enemies = [
            Enemy(350, 200, 70),
            Enemy(650, 150, 70),
            Enemy(850, 300, 70),
            Enemy(450, 400, 70),
            Enemy(1000, 550, 70),
            Enemy(200, 550, 70),
        ]
        start = (80, 350)
    elif level_num == 3:
        # corridor style
        walls.append(make_wall(150, 100, 30, 400))
        walls.append(make_wall(300, 200, 30, 350))
        walls.append(make_wall(450, 80, 30, 300))
        walls.append(make_wall(600, 250, 30, 350))
        walls.append(make_wall(750, 100, 30, 400))
        walls.append(make_wall(900, 200, 30, 350))
        walls.append(make_wall(200, 500, 600, 30))
        enemies = [
            Enemy(220, 180, 80, 1.5),
            Enemy(380, 300, 80, 1.5),
            Enemy(520, 150, 80, 1.5),
            Enemy(680, 400, 80, 1.5),
            Enemy(820, 250, 80, 1.5),
            Enemy(1050, 350, 80, 1.5),
            Enemy(400, 580, 80, 1.5),
            Enemy(700, 600, 80, 1.5),
        ]
        start = (80, 80)
    elif level_num == 4:
        # rooms
        walls.append(make_wall(250, 80, 30, 250))
        walls.append(make_wall(250, 400, 30, 200))
        walls.append(make_wall(450, 150, 200, 30))
        walls.append(make_wall(650, 150, 30, 300))
        walls.append(make_wall(400, 450, 300, 30))
        walls.append(make_wall(800, 100, 30, 250))
        walls.append(make_wall(800, 450, 30, 180))
        walls.append(make_wall(950, 300, 180, 30))
        enemies = [
            Enemy(180, 200, 90, 1.6),
            Enemy(350, 300, 90, 1.6),
            Enemy(550, 250, 90, 1.6),
            Enemy(500, 550, 90, 1.6),
            Enemy(750, 350, 90, 1.6),
            Enemy(900, 200, 90, 1.6),
            Enemy(1100, 400, 90, 1.6),
            Enemy(1000, 550, 90, 1.6),
            Enemy(300, 600, 90, 1.6),
        ]
        start = (100, 500)
    else:  # level 5
        # complex
        walls.append(make_wall(180, 100, 25, 200))
        walls.append(make_wall(180, 400, 25, 220))
        walls.append(make_wall(320, 80, 25, 180))
        walls.append(make_wall(320, 350, 25, 280))
        walls.append(make_wall(460, 150, 25, 250))
        walls.append(make_wall(460, 500, 25, 140))
        walls.append(make_wall(600, 80, 25, 300))
        walls.append(make_wall(600, 480, 25, 160))
        walls.append(make_wall(740, 120, 25, 220))
        walls.append(make_wall(740, 450, 25, 180))
        walls.append(make_wall(880, 80, 25, 280))
        walls.append(make_wall(880, 460, 25, 180))
        walls.append(make_wall(250, 300, 150, 25))
        walls.append(make_wall(550, 350, 120, 25))
        walls.append(make_wall(800, 280, 100, 25))
        enemies = [
            Enemy(250, 200, 100, 1.7),
            Enemy(400, 250, 100, 1.7),
            Enemy(550, 200, 100, 1.7),
            Enemy(700, 300, 100, 1.7),
            Enemy(850, 200, 100, 1.7),
            Enemy(1050, 250, 100, 1.7),
            Enemy(300, 500, 100, 1.7),
            Enemy(500, 550, 100, 1.7),
            Enemy(700, 520, 100, 1.7),
            Enemy(950, 550, 100, 1.7),
            Enemy(1100, 500, 100, 1.7),
            Enemy(150, 350, 100, 1.7),
        ]
        start = (80, 80)

    return walls, enemies, start

# ==================== GAME ====================
class Game:
    def __init__(self):
        self.level = 1
        self.max_level = 5
        self.state = "playing"  # playing, level_complete, game_over, victory
        self.reset_level()
        self.font = pygame.font.SysFont("consolas", 22)
        self.big_font = pygame.font.SysFont("consolas", 42, bold=True)
        self.med_font = pygame.font.SysFont("consolas", 28)

    def reset_level(self):
        walls, enemies, start = get_level(self.level)
        self.walls = walls
        self.enemies = enemies
        self.player = Player(*start)
        self.bullets = []
        self.grenades = []
        self.c4_list = []
        self.explosions = []
        self.state = "playing"
        self.complete_timer = 0

    def next_level(self):
        if self.level >= self.max_level:
            self.state = "victory"
        else:
            self.level += 1
            self.reset_level()

    def detonate_c4(self):
        for c4 in self.c4_list:
            if c4.alive:
                self.explosions.append(Explosion(c4.x, c4.y, 110, 120))
                c4.alive = False
                snd_explosion.play()
        self.c4_list = [c for c in self.c4_list if c.alive]

    def update(self):
        keys = pygame.key.get_pressed()
        current_time = pygame.time.get_ticks()
        mouse_pressed = pygame.mouse.get_pressed()[0]

        if self.state == "playing":
            self.player.update(keys, self.walls)

            # weapon switch
            for i in range(1, 6):
                if keys[pygame.K_1 + i - 1]:
                    self.player.current_weapon = i

            # shooting
            if mouse_pressed or (self.player.current_weapon == 3 and keys[pygame.K_SPACE]):
                self.player.shoot(self.bullets, self.grenades, self.c4_list, current_time)

            # F to detonate C4
            if keys[pygame.K_f]:
                self.detonate_c4()

            # update bullets
            for b in self.bullets[:]:
                b.update(self.walls)
                if not b.alive:
                    self.bullets.remove(b)
                    continue
                # hit player
                if b.owner == "enemy" and self.player.alive:
                    if math.hypot(b.x - self.player.x, b.y - self.player.y) < self.player.radius + b.radius:
                        self.player.take_damage(b.damage)
                        b.alive = False
                # hit enemies
                if b.owner == "player":
                    for e in self.enemies:
                        if e.alive and math.hypot(b.x - e.x, b.y - e.y) < e.radius + b.radius:
                            e.take_damage(b.damage)
                            b.alive = False
                            break

            # knife melee check
            if self.player.melee_active > 0:
                for e in self.enemies:
                    if e.alive:
                        dist = math.hypot(e.x - self.player.x, e.y - self.player.y)
                        if dist < 45:
                            e.take_damage(self.player.weapons[3].damage)
                            self.player.melee_active = 0  # one hit per swing

            # grenades
            for g in self.grenades[:]:
                g.update(self.walls)
                if g.exploded:
                    self.explosions.append(Explosion(g.x, g.y, 95, 80))
                    snd_explosion.play()
                    self.grenades.remove(g)

            # C4
            for c4 in self.c4_list:
                c4.update()

            # explosions
            for exp in self.explosions[:]:
                exp.update()
                if not exp.alive:
                    self.explosions.remove(exp)
                    continue
                # damage enemies
                for e in self.enemies:
                    if e.alive and id(e) not in exp.damaged:
                        if math.hypot(e.x - exp.x, e.y - exp.y) < exp.radius:
                            e.take_damage(exp.damage)
                            exp.damaged.add(id(e))
                # damage player
                if self.player.alive and id(self.player) not in exp.damaged:
                    if math.hypot(self.player.x - exp.x, self.player.y - exp.y) < exp.radius * 0.85:
                        self.player.take_damage(exp.damage // 2)
                        exp.damaged.add(id(self.player))

            # enemies
            for e in self.enemies:
                e.update(self.player, self.walls, self.bullets)

            # check level complete
            if all(not e.alive for e in self.enemies):
                self.state = "level_complete"
                self.complete_timer = 90
                snd_level_complete.play()

            if not self.player.alive:
                self.state = "game_over"

        elif self.state == "level_complete":
            self.complete_timer -= 1
            if self.complete_timer <= 0:
                # wait for key
                pass

    def draw(self):
        screen.fill(FLOOR)

        # walls
        for w in self.walls:
            pygame.draw.rect(screen, WALL, w)
            pygame.draw.rect(screen, (50, 55, 65), w, 2)

        # entities
        for c4 in self.c4_list:
            c4.draw(screen)
        for g in self.grenades:
            g.draw(screen)
        for b in self.bullets:
            b.draw(screen)
        for e in self.enemies:
            e.draw(screen)
        self.player.draw(screen)
        for exp in self.explosions:
            exp.draw(screen)

        # HUD
        self.draw_hud()

        if self.state == "level_complete":
            self.draw_center_text("LEVEL CLEARED", GREEN)
            self.draw_center_text("Press SPACE or ENTER to proceed to the next level", WHITE, 50)
        elif self.state == "game_over":
            self.draw_center_text("YOU DIED", RED)
            self.draw_center_text("Press R to restart level", WHITE, 50)
        elif self.state == "victory":
            self.draw_center_text("MISSION COMPLETE", GREEN)
            self.draw_center_text("All buildings infiltrated. Well done, operative.", WHITE, 50)
            self.draw_center_text("Press R to play again from Level 1", LIGHT_GRAY, 100)

    def draw_hud(self):
        # health
        pygame.draw.rect(screen, DARK_RED, (20, 20, 200, 18))
        pygame.draw.rect(screen, GREEN, (20, 20, int(200 * self.player.health / self.player.max_health), 18))
        pygame.draw.rect(screen, WHITE, (20, 20, 200, 18), 2)
        hp_text = self.font.render(f"HP {max(0, int(self.player.health))}", True, WHITE)
        screen.blit(hp_text, (25, 18))

        # weapon + ammo
        w = self.player.weapons[self.player.current_weapon]
        weapon_text = self.font.render(f"[{self.player.current_weapon}] {w.name}", True, YELLOW)
        screen.blit(weapon_text, (20, 48))
        if not w.is_melee:
            ammo_text = self.font.render(f"Ammo: {w.ammo}/{w.max_ammo}", True, LIGHT_GRAY)
            screen.blit(ammo_text, (20, 72))
        else:
            melee_text = self.font.render("MELEE", True, LIGHT_GRAY)
            screen.blit(melee_text, (20, 72))

        # level
        lvl_text = self.font.render(f"Level {self.level} / {self.max_level}", True, WHITE)
        screen.blit(lvl_text, (SCREEN_WIDTH - 160, 20))

        # enemies left
        alive = sum(1 for e in self.enemies if e.alive)
        en_text = self.font.render(f"Hostiles: {alive}", True, ORANGE)
        screen.blit(en_text, (SCREEN_WIDTH - 160, 48))

        # controls hint
        if self.level == 1 and self.state == "playing":
            hint = self.font.render("WASD move | Mouse aim + LMB shoot | 1-5 weapons | F detonate C4", True, (120, 120, 130))
            screen.blit(hint, (20, SCREEN_HEIGHT - 30))

    def draw_center_text(self, text, color, y_offset=0):
        surf = self.big_font.render(text, True, color)
        rect = surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + y_offset))
        # shadow
        shadow = self.big_font.render(text, True, BLACK)
        screen.blit(shadow, (rect.x + 2, rect.y + 2))
        screen.blit(surf, rect)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit()
            if self.state == "level_complete":
                if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    self.next_level()
            if self.state in ("game_over", "victory"):
                if event.key == pygame.K_r:
                    if self.state == "victory":
                        self.level = 1
                    self.reset_level()
            if event.key == pygame.K_f and self.state == "playing":
                self.detonate_c4()

def main():
    game = Game()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            game.handle_event(event)

        game.update()
        game.draw()
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
