"""以用户选定的设定图和视频抽帧为证据进行审查，不把失败当作通过。"""
import json
import subprocess
import tempfile
from pathlib import Path


def extract_frames(video, folder, prefix):
    info = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    duration = float(info.stdout.strip())
    if not 0 < duration < 3600:
        raise ValueError("视频时长无效")
    paths = []
    for i, point in enumerate((0, duration / 2, max(0, duration - 0.15))):
        target = Path(folder) / f"{prefix}_{i}.jpg"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", str(point), "-i", str(video),
             "-frames:v", "1", "-vf", "scale=768:-2", str(target)],
            capture_output=True, check=True, timeout=60,
        )
        if not target.is_file():
            raise ValueError("无法提取视频帧")
        paths.append(str(target))
    return paths


def parse_review(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    result = json.loads(text)
    if not isinstance(result, dict) or result.get("status") not in {"pass", "issue", "uncertain"}:
        raise ValueError("审查结果格式无效")
    issues = result.get("issues")
    if not isinstance(issues, list) or not all(isinstance(x, str) for x in issues):
        raise ValueError("审查问题列表无效")
    if result["status"] == "issue" and not issues:
        raise ValueError("审查缺少问题证据")
    if result["status"] == "pass" and issues:
        raise ValueError("通过状态与问题列表矛盾")
    return {"status": result["status"], "issues": issues,
            "suggestion": str(result.get("suggestion", ""))}


def review_clips(agent, data, clips):
    from models.vlm_client import VLM
    artifacts = agent._session_artifacts(data)
    segments = [s for ep in artifacts.get("storyboard", {}).get("episodes", [])
                for s in ep.get("segments", [])]
    by_id = {s["segment_id"]: s for s in segments}
    assets = artifacts.get("character_design", {})
    reports = []
    previous = None
    with tempfile.TemporaryDirectory(prefix="continuity-") as folder:
        for index, clip in enumerate(clips):
            agent._check_cancel()
            segment = by_id.get(clip["id"], {})
            row = {"id": clip["id"], "selected": clip.get("selected", "")}
            current = None
            try:
                if not row["selected"] or not Path(row["selected"]).is_file():
                    raise ValueError("没有可审查的视频")
                current = extract_frames(row["selected"], folder, str(index))
                refs = agent._get_segment_reference_assets(segment, assets)
                images = list(refs)
                labels = [f"角色或场景设定图 {i + 1}" for i in range(len(refs))]
                if previous and previous[0] == segment.get("episode_number", clip.get("episode", 1)):
                    images.append(previous[1])
                    labels.append("上一片段尾帧")
                images.extend(current)
                labels.extend(["当前片段首帧", "当前片段中帧", "当前片段尾帧"])
                prompt = agent._prompt("review", "continuity").format(
                    labels=json.dumps(labels, ensure_ascii=False),
                    segment=json.dumps(segment, ensure_ascii=False),
                    characters=agent._build_character_section(segment, assets),
                )
                model = agent._require_input(data, "vlm_model")
                text = VLM().query(prompt, image_paths=images, model=model,
                                   session_id=data["session_id"])
                row.update(parse_review(text))
            except Exception as exc:
                row.update(status="uncertain", issues=[f"未完成审查：{type(exc).__name__}"],
                           suggestion="检查视觉模型配置、视频文件和 ffmpeg 后重新审查。")
            agent._check_cancel()
            previous = (segment.get("episode_number", clip.get("episode", 1)), current[-1]) if current else None
            reports.append(row)
            agent._report_progress("一致性审查", f"已检查 {index + 1}/{len(clips)}", 100 * (index + 1) / max(1, len(clips)))
    return {"items": reports, "scope": "首/中/尾帧抽样及同集相邻片段衔接，非逐帧检测；结果需人工确认。"}
