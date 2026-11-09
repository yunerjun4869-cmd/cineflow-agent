"""在原视频 Agent 上叠加服务商限流、有限重试与一致性审查。"""
import asyncio
import copy
import os
import time

from core.agents.video_agent import VideoDirectorAgent
from .review import review_clips
from .scheduler import provider_slot


class ContinuityVideoAgent(VideoDirectorAgent):
    def __init__(self):
        super().__init__()
        self.name = "ContinuityVideo"
        self.outcomes = {}
        self.repairs = {}

    def _assemble_prompt(self, segment, style_prompt, character_artifact=None, video_data=None):
        prompt = super()._assemble_prompt(segment, style_prompt, character_artifact, video_data)
        suggestion = self.repairs.get(segment["segment_id"])
        if suggestion:
            prompt += "\n当前片段连续性修复要求（保持其他创作设定）：" + suggestion
        return prompt

    def _generate_one(self, *args, **kwargs):
        from models.config_model import resolve_provider, parse_api_model
        sid, segment_id, _, _, model = args[:5]
        provider = resolve_provider(model) or parse_api_model(model, "video")[0] or "unregistered"
        retries = min(3, max(0, int(self.stage_options.get("max_retries", 1))))
        delay = min(30, max(0, float(self.stage_options.get("retry_delay_seconds", 2))))
        cancelled = lambda: bool(self.cancellation_check and self.cancellation_check())
        result = (segment_id, None)
        for attempt in range(retries + 1):
            if cancelled():
                break
            with provider_slot(provider, cancelled):
                result = super()._generate_one(*args, **kwargs)
            if result[1] and os.path.isfile(result[1]) and os.path.getsize(result[1]) > 0:
                break
            result = (segment_id, None)
            if attempt < retries:
                self._report_progress("视频生成", f"{segment_id} 失败，准备第 {attempt + 1} 次重试", 5)
                deadline = time.monotonic() + delay * 2 ** attempt
                while time.monotonic() < deadline and not cancelled():
                    time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        self.outcomes[segment_id] = result[1]
        return result

    def _build_payload(self, sid, segments, video_clips=None):
        result = super()._build_payload(sid, segments, video_clips)
        previous = {c["id"]: c for c in (video_clips or [])}
        for clip in result["payload"]["clips"]:
            old = previous.get(clip["id"], {}).get("selected")
            generated = self.outcomes.get(clip["id"])
            # 未重生成或重生成失败时保留用户选择，不擅自切到磁盘最新版本。
            if not generated and old in clip["versions"]:
                clip["selected"] = old
            if clip["id"] in self.outcomes:
                clip["last_attempt"] = "done" if generated else "failed"
        return result

    async def process(self, input_data, intervention=None):
        data = self._merge_session_params(input_data)
        previous = self._session_artifact(data, "video_generation")
        segments = [s for ep in self._session_artifact(data, "storyboard").get("episodes", [])
                    for s in ep.get("segments", [])]
        known = {s["segment_id"] for s in segments}
        self.outcomes = {}
        self.repairs = {}
        intervention = copy.deepcopy(intervention or {})
        if "continuity_regenerate_clips" in intervention:
            intervention["regenerate_clips"] = intervention.pop("continuity_regenerate_clips")
        if "regenerate_clips" in intervention:
            ids = intervention["regenerate_clips"]
            if not isinstance(ids, list) or not all(isinstance(i, str) and i in known for i in ids):
                raise ValueError("待重生成片段不属于当前分镜")
            intervention["regenerate_clips"] = list(dict.fromkeys(ids))
            if not ids:
                raise ValueError("请选择待重生成片段")
            for row in previous.get("continuity_review", {}).get("items", []):
                if row["id"] in ids and row.get("status") == "issue":
                    self.repairs[row["id"]] = row.get("suggestion", "")
        if intervention.get("review_only"):
            if not previous.get("clips"):
                raise ValueError("请先生成视频片段")
            result = {"payload": copy.deepcopy(previous)}
        else:
            result = await super().process(data, intervention or None)
        self._check_cancel()
        result["payload"]["continuity_review"] = await asyncio.to_thread(
            review_clips, self, data, result["payload"].get("clips", []))
        # 生成或审查结束后，始终交由用户确认，不自动宣称可交付。
        result["requires_intervention"] = True
        result["stage_completed"] = False
        return result
