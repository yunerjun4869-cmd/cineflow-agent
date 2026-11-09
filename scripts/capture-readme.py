"""仅用于文档截图：实际组件 + 标明来源的演示数据，不调用模型。"""
import json
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/images'
BASE = 'http://localhost:3036'
brief = '为一款奶油白随行杯准备面向美国年轻通勤者的竖屏商品短片。围绕“从出门到办公桌”安排镜头，主角一直穿米色外套，杯身颜色和外形保持一致。先给我脚本和分镜，确认后再生成。'
scenarios = json.load(urlopen('http://127.0.0.1:8036/api/scenarios'))
scenario = next(s for s in scenarios['scenarios'] if s['id'] == 'continuity_film')
stages = scenario['stages']
clips = [{'id': f'seg_01_0{i}', 'name': name, 'episode': 1, 'index': i,
          'description': desc, 'selected': f'demo/seg_01_0{i}.mp4' if i < 3 else '', 'versions': [], 'status': 'done' if i < 3 else 'failed', 'duration': 5}
         for i, name, desc in [(1, '出门 · 奶油白随行杯', '早晨，主角将奶油白杯子放进通勤包。'),
                              (2, '通勤 · 地铁入口', '主角穿米色外套，拿着同一只杯子走入地铁。'),
                              (3, '办公 · 桌面特写', '杯子放在办公桌上，镜头缓缓靠近。')]]
report = {'scope': '演示数据｜以下问题与结论仅用于展示操作方式，未调用真实模型。', 'items': [
    {'id': 'seg_01_01', 'selected': 'demo/seg_01_01.mp4', 'status': 'pass', 'issues': [], 'suggestion': '首段与设定一致；仍需人工检查完整视频。'},
    {'id': 'seg_01_02', 'selected': 'demo/seg_01_02.mp4', 'status': 'issue', 'issues': ['片段中帧：杯身由奶油白变成深灰，与商品参考图不一致。'], 'suggestion': '保持奶油白杯身、黑色杯盖和相同外形，只调整当前通勤片段。'},
    {'id': 'seg_01_03', 'selected': '', 'status': 'uncertain', 'issues': ['片段尚未生成成功，暂时无法检查。'], 'suggestion': '只重试这个片段，完成后再检查它与上一段是否接得上。'}]}
artifact = {'session_id': 'cineflow-screenshot-demo', 'clips': clips, 'continuity_review': report}
state = {'session_id': 'cineflow-screenshot-demo', 'scenario': 'continuity_film', 'stages': stages,
         'current_stage': 'video_generation', 'status': {s['id']: ('waiting' if s['id']=='video_generation' else 'pending') for s in stages},
         'meta': {'idea': '演示项目｜随行杯 · 从出门到办公桌', 'scenario': 'continuity_film', 'video_ratio': '9:16', 'episodes': 1},
         'artifacts': {'video_generation': artifact}, 'error': None}
with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 760}, device_scale_factor=1.5)
    page.add_init_script("localStorage.setItem('sfa.scenario','continuity_film')")
    page.goto(BASE, wait_until='networkidle')
    page.locator('textarea').first.fill(brief)
    page.screenshot(path=str(OUT/'workspace.png'))
    # 截图使用实际 React 组件和明确标记的演示响应，不触发生成、也不写入用户会话。
    def demo_route(route):
        if '/artifact/' in route.request.url:
            key = route.request.url.rsplit('/',1)[-1]
            route.fulfill(json={'artifact': artifact if key=='video_generation' else {}})
        else:
            route.fulfill(json=state)
    page.route('**/api/project/cineflow-screenshot-demo/**', demo_route)
    page.goto(BASE+'/?session=cineflow-screenshot-demo&stage=video_generation', wait_until='networkidle')
    page.get_by_text('跨镜头一致性审查', exact=True).wait_for()
    page.locator('section').filter(has=page.get_by_text('跨镜头一致性审查', exact=True)).screenshot(path=str(OUT/'continuity-review.png'))
    cover = browser.new_page(viewport={'width':1600,'height':820}, device_scale_factor=1)
    cover.set_content('<html><head><style>body{margin:0}svg{display:block}</style></head><body>' + (OUT/'cineflow-cover.svg').read_text() + '</body></html>')
    cover.screenshot(path=str(OUT/'cineflow-cover.png'))
    print('已保存封面、工作台与演示审查面板截图')
    browser.close()
