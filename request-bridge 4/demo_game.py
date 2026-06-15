"""
demo_game.py — ordinary pygame script standing in for the teammate's game.
Demonstrates the full data contract:
  * reads the WHOLE workout plan from the dashboard (get_plan / get_session)
  * one encounter per prescribed exercise; reps map to enemy HP (1 rep = 1 hit)
  * clearing every encounter = one full workout = +1 level
  * reports live stats back, and saves the workout when finished
Shows its own FPS so you can confirm mirroring doesn't slow it down.
"""
import time, pygame
import request_bridge

pygame.init()
screen = pygame.display.set_mode((800, 500))
pygame.display.set_caption("ReQuest - pygame demo")
clock = pygame.time.Clock()
big = pygame.font.SysFont("monospace", 30, bold=True)
fnt = pygame.font.SysFont("monospace", 18)

def load_plan():
    p = request_bridge.get_plan()
    return p if p else [{"exercise": "Band pull-apart", "reps": 10, "sets": 3}]

plan = load_plan()
enc = 0                       # which exercise (encounter) we're on
set_in_enc = 0                # sets cleared in this encounter
enemy_hp = plan[0]["reps"]
reps_total = 0
level = 1
score = 0
flash = 0
px = 400
start = time.time()
msg_until = 0

def reset_workout():
    global plan, enc, set_in_enc, enemy_hp, reps_total, score, start
    plan = load_plan()
    enc = 0; set_in_enc = 0; enemy_hp = plan[0]["reps"]
    reps_total = 0; score = 0; start = time.time()

running = True
while running:
    cur = plan[min(enc, len(plan) - 1)]
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
        elif e.type == request_bridge.SESSION_EVENT:      # dashboard changed the plan
            reset_workout(); flash = 12
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_SPACE:
                enemy_hp -= 1; reps_total += 1; score += 10; flash = 6
                if enemy_hp <= 0:
                    set_in_enc += 1
                    if set_in_enc >= cur["sets"]:         # this exercise is done
                        enc += 1; set_in_enc = 0
                        if enc >= len(plan):              # whole workout finished
                            request_bridge.save_result(
                                reps_done=reps_total,
                                sets_done=sum(x["sets"] for x in plan),
                                level=level, score=score,
                                duration_s=round(time.time() - start, 1),
                                completed=True)
                            level += 1                    # 1 level == 1 full workout
                            msg_until = time.time() + 2.2
                            reset_workout(); flash = 12
                        else:
                            enemy_hp = plan[enc]["reps"]
                    else:
                        enemy_hp = cur["reps"]
            if e.key == pygame.K_LEFT:  px = max(60, px - 30)
            if e.key == pygame.K_RIGHT: px = min(740, px + 30)
            request_bridge.report(exercise=cur["exercise"], reps_done=reps_total,
                                  sets_done=set_in_enc, level=level, score=score)

    screen.fill((24, 20, 50) if not flash else (40, 30, 90))
    flash = max(0, flash - 1)
    pygame.draw.rect(screen, (220, 80, 110), (px - 60, 180, 120, 120), border_radius=14)
    if cur["reps"]:
        w = int(116 * enemy_hp / cur["reps"])
        pygame.draw.rect(screen, (255, 216, 107), (px - 58, 150, max(0, w), 12), border_radius=6)
    lines = [
        (big, cur["exercise"], 34),
        (fnt, f"Encounter {enc+1}/{len(plan)}   Set {set_in_enc+1}/{cur['sets']}   HP {max(0,enemy_hp)}/{cur['reps']}", 84),
        (fnt, f"Level {level} (= workout {level})   Total reps {reps_total}   Score {score}", 112),
        (fnt, f"FPS {int(clock.get_fps())}   ARROWS move   SPACE = one rep", 460),
    ]
    for f, txt, y in lines:
        screen.blit(f.render(txt, True, (235, 235, 250)), (40, y))
    if time.time() < msg_until:
        screen.blit(big.render("WORKOUT COMPLETE - saved! Next level...", True, (22, 196, 172)), (60, 320))
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
