"""无付费模型调用的行为测试。"""
import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from core.agents.video_agent import VideoDirectorAgent
from scenarios.continuity_film.agents import ContinuityVideoAgent
from scenarios.continuity_film.review import parse_review, review_clips, extract_frames
from scenarios.continuity_film.scheduler import provider_slot


def test_provider_limit_and_parallelism():
    lock = threading.Lock()
    active = peak = 0
    def task():
        nonlocal active, peak
        with provider_slot('test-provider', lambda: False):
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.03)
            with lock:
                active -= 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: task(), range(12)))
    assert peak == 2
    assert active == 0


def test_cancellation_releases_slot():
    with pytest.raises(RuntimeError):
        with provider_slot('cancel', lambda: True):
            pytest.fail('取消后不得调用模型')
    with provider_slot('cancel', lambda: False):
        pass


def test_only_failed_generation_is_retried(tmp_path):
    video = tmp_path / 'clip.mp4'
    video.write_bytes(b'video')
    agent = ContinuityVideoAgent()
    agent.stage_options = {'max_retries': 2, 'retry_delay_seconds': 0}
    with patch.object(VideoDirectorAgent, '_generate_one', side_effect=[('a', None), ('a', str(video))]) as generate:
        result = agent._generate_one('sid', 'a', 'prompt', 'ref', 'unknown-model')
    assert result == ('a', str(video))
    assert generate.call_count == 2
    with patch.object(VideoDirectorAgent, '_generate_one', return_value=('b', str(video))) as generate:
        agent._generate_one('sid', 'b', 'prompt', 'ref', 'unknown-model')
    assert generate.call_count == 1


def test_retry_budget_is_bounded():
    agent = ContinuityVideoAgent()
    agent.stage_options = {'max_retries': 1, 'retry_delay_seconds': 0}
    with patch.object(VideoDirectorAgent, '_generate_one', return_value=('a', None)) as generate:
        assert agent._generate_one('sid', 'a', 'prompt', 'ref', 'unknown-model') == ('a', None)
    assert generate.call_count == 2


@pytest.mark.parametrize('text', ['{}', 'not json', '{"status":"pass","issues":["变脸"]}',
                                 '{"status":"issue","issues":[]}'])
def test_malformed_review_never_passes(text):
    with pytest.raises((ValueError, TypeError)):
        parse_review(text)


def test_valid_review():
    assert parse_review('```json\n{"status":"pass","issues":[]}\n```')['status'] == 'pass'


def test_failed_retry_preserves_user_selection():
    agent = ContinuityVideoAgent()
    agent.outcomes = {'a': None}
    with patch.object(agent, '_list_versions', return_value=['old.mp4', 'new.mp4']):
        result = agent._build_payload('sid', [{'segment_id': 'a'}], [{'id': 'a', 'selected': 'old.mp4'}])
    clip = result['payload']['clips'][0]
    assert clip['selected'] == 'old.mp4'
    assert clip['last_attempt'] == 'failed'


@pytest.mark.asyncio
async def test_review_only_does_not_generate():
    agent = ContinuityVideoAgent()
    data = {'session_id': 'sid', '_session_artifacts': {'video_generation': {'clips': [{'id': 'a'}]}}}
    with patch.object(VideoDirectorAgent, 'process') as generate, patch(
        'scenarios.continuity_film.agents.review_clips', return_value={'items': []}):
        result = await agent.process(data, {'review_only': True})
    generate.assert_not_called()
    assert result['requires_intervention'] is True


@pytest.mark.asyncio
async def test_invalid_target_rejected():
    with pytest.raises(ValueError):
        await ContinuityVideoAgent().process({'session_id': 'sid'}, {'continuity_regenerate_clips': ['foreign']})


def test_missing_video_is_uncertain():
    agent = ContinuityVideoAgent()
    report = review_clips(agent, {'session_id': 'sid'}, [{'id': 'a', 'selected': ''}])
    assert report['items'][0]['status'] == 'uncertain'


def test_review_uses_selected_assets_and_neighbor(tmp_path):
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'video')
    agent = ContinuityVideoAgent()
    data = {'session_id': 'sid', 'vlm_model': 'test', '_session_artifacts': {
        'storyboard': {'episodes': [{'segments': [{'segment_id': 'a'}, {'segment_id': 'b'}]}]}}}
    with patch('scenarios.continuity_film.review.extract_frames', return_value=['first', 'middle', 'last']), \
         patch.object(agent, '_get_segment_reference_assets', return_value=['character.jpg']), \
         patch.object(agent, '_prompt', return_value='{labels} {segment} {characters}'), \
         patch('models.vlm_client.VLM.query', return_value=json.dumps({'status': 'issue', 'issues': ['服装变化'], 'suggestion': '恢复白衣'})) as query:
        report = review_clips(agent, data, [{'id': 'a', 'selected': str(video)}, {'id': 'b', 'selected': str(video)}])
    assert query.call_args_list[0].kwargs['image_paths'] == ['character.jpg', 'first', 'middle', 'last']
    assert query.call_args_list[1].kwargs['image_paths'] == ['character.jpg', 'last', 'first', 'middle', 'last']
    assert report['items'][1]['status'] == 'issue'


@pytest.mark.asyncio
async def test_targeted_repair_passes_only_selected_ids_and_feedback():
    agent = ContinuityVideoAgent()
    data = {'session_id': 'sid', '_session_artifacts': {
        'storyboard': {'episodes': [{'segments': [{'segment_id': 'a'}, {'segment_id': 'b'}]}]},
        'video_generation': {'clips': [], 'continuity_review': {'items': [
            {'id': 'a', 'status': 'issue', 'suggestion': '恢复白色外套'}]}}}}
    with patch.object(VideoDirectorAgent, 'process', return_value={'payload': {'clips': []}}) as generate, \
         patch('scenarios.continuity_film.agents.review_clips', return_value={'items': []}):
        await agent.process(data, {'continuity_regenerate_clips': ['a', 'a']})
    assert generate.call_args.args[1] == {'regenerate_clips': ['a']}
    assert agent.repairs == {'a': '恢复白色外套'}
    assert '恢复白色外套' in agent._assemble_prompt({'segment_id': 'a'}, '写实')
    assert '恢复白色外套' not in agent._assemble_prompt({'segment_id': 'b'}, '写实')


def test_model_failure_is_uncertain(tmp_path):
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'video')
    agent = ContinuityVideoAgent()
    with patch('scenarios.continuity_film.review.extract_frames', return_value=['first', 'middle', 'last']), \
         patch.object(agent, '_prompt', return_value='{labels} {segment} {characters}'), \
         patch('models.vlm_client.VLM.query', side_effect=RuntimeError('private provider details')):
        report = review_clips(agent, {'session_id': 'sid', 'vlm_model': 'test'}, [{'id': 'a', 'selected': str(video)}])
    assert report['items'][0]['status'] == 'uncertain'
    assert 'private provider details' not in str(report)


def test_scenario_prompt_formats():
    from pathlib import Path
    agent = ContinuityVideoAgent()
    agent.prompt_dirs = [str(Path(__file__).resolve().parents[1] / 'scenarios/continuity_film/prompts')]
    prompt = agent._prompt('review', 'continuity').format(labels='[]', segment='{}', characters='主角')
    assert '"status"' in prompt
    assert '主角' in prompt
