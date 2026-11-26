"""
Walk through the EQL demo on the Tracy episode in a headless Chrome and keep a
screenshot of every step and a video of the whole walk:

    python scripts/eql_demo_walkthrough.py [OUTPUT_DIRECTORY] [VIEWER_URL]

It needs a running viewer (``cramera --demo-scenes demo --port 8722``) and Playwright
(``pip install playwright``; ``python -m playwright install ffmpeg`` for the video).
"""
import os
import sys
from playwright.sync_api import sync_playwright
OUT = sys.argv[1] if len(sys.argv) > 1 else "eql_demo_walkthrough"
URL = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8722/"
SCENE = "tracy_shape_sorting"
os.makedirs(OUT, exist_ok=True)
step = [0]
def shot(pg, name):
    step[0] += 1; path = f"{OUT}/{step[0]:02d}_{name}.png"; pg.screenshot(path=path); print("shot", path)
def seek(pg, frame):
    pg.evaluate("""(f) => { const s=document.querySelector("input[type=range]"); s.value=f; s.dispatchEvent(new Event('input',{bubbles:true})); }""", frame)
    pg.wait_for_timeout(1500)
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    ctx = b.new_context(viewport={"width": 1600, "height": 1000}, record_video_dir=OUT, record_video_size={"width": 1600, "height": 1000})
    pg = ctx.new_page()
    errs = []; pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(f"{URL.rstrip('/')}/?scene={SCENE}"); pg.wait_for_timeout(8000)
    scope = pg.locator("select[aria-label='Query scope']"); box = pg.locator("textarea[aria-label='Query in the entity query language']")
    def ask(code, name, wait=4000):
        box.click(); box.fill(""); box.type(code, delay=35); pg.wait_for_timeout(600)
        pg.keyboard.press("Escape"); pg.keyboard.press("Control+Enter"); pg.wait_for_timeout(wait); shot(pg, name)
    scope.select_option("current_state"); pg.wait_for_timeout(800)
    ask("an(Arm)", "arms_highlighted", 8000)
    ask("a(Tracy)(left_arm=an(Arm)(end_effector=a(TracyLeftGripper)))", "nested_robot_pattern")
    raised = "piece = a(Body).from_(domain=scene_object)\npiece.where(piece.global_pose.z > 0.92)"
    seek(pg, 800); ask(raised, "frame800_nothing_raised")
    seek(pg, 1200); ask(raised, "frame1200_square_piece_raised")
    seek(pg, 2400); ask(raised, "frame2400_circle_piece_raised")
    seek(pg, 2000); ask(raised, "frame2000_square_piece_put_down")
    print("errors:", errs[:10]); ctx.close(); b.close()
