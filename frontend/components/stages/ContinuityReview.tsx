'use client';

interface ReviewItem {
  id: string;
  selected: string;
  status: 'pass' | 'issue' | 'uncertain';
  issues: string[];
  suggestion: string;
}
interface Props {
  report?: { items: ReviewItem[]; scope: string };
  clips: { id: string; selected: string; last_attempt?: string }[];
  disabled: boolean;
  onIntervene: (data: Record<string, unknown>) => void;
}

export default function ContinuityReview({ report, clips, disabled, onIntervene }: Props) {
  if (!report) return null;
  const stale = report.items.some(row => clips.find(c => c.id === row.id)?.selected !== row.selected);
  const issues = report.items.filter(row => row.status === 'issue').map(row => row.id);
  const failed = clips.filter(c => c.last_attempt === 'failed' || !c.selected).map(c => c.id);
  const labels = { pass: '抽样通过', issue: '发现问题', uncertain: '待人工检查' };
  return (
    <section className="mb-6 p-4 border border-gray-200 rounded-xl bg-gray-50 space-y-3">
      <h3 className="font-semibold text-gray-900">跨镜头一致性审查</h3>
      <p className="text-xs text-gray-600">{report.scope}</p>
      {stale && <p className="text-sm font-medium">视频选择已变化，请先重新审查。</p>}
      <div className="flex flex-wrap gap-2">
        <button disabled={disabled} onClick={() => onIntervene({ review_only: true })}
          className="border rounded-lg px-3 py-2 text-sm disabled:opacity-40">重新审查</button>
        <button disabled={disabled || stale || !issues.length}
          onClick={() => onIntervene({ continuity_regenerate_clips: issues })}
          className="bg-gray-900 text-white rounded-lg px-3 py-2 text-sm disabled:opacity-40">
          只重生成问题片段（{issues.length}）
        </button>
        {!!failed.length && <button disabled={disabled}
          onClick={() => onIntervene({ continuity_regenerate_clips: failed })}
          className="border rounded-lg px-3 py-2 text-sm disabled:opacity-40">重试失败片段（{failed.length}）</button>}
      </div>
      <p className="text-xs text-gray-500">重新审查会调用视觉模型；重生成会调用视频模型并再次审查，可能产生费用。</p>
      {report.items.map(row => (
        <div key={row.id} className="bg-white border border-gray-200 rounded-lg p-3 text-sm">
          <p className="font-medium">{row.id} · {stale ? '结果待更新' : labels[row.status]}</p>
          {row.issues.map((issue, i) => <p className="mt-1 text-gray-700" key={i}>{issue}</p>)}
          {row.suggestion && <p className="mt-1 text-gray-600">建议：{row.suggestion}</p>}
        </div>
      ))}
    </section>
  );
}
