'use client';

import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { ATSScore } from '@/components/common/resume_previewer_context';
import { useTranslations } from '@/lib/i18n';

interface ATSScoreCardProps {
  atsScore: ATSScore;
  /** Baseline (original resume) score for before/after comparison. */
  baseline?: ATSScore | null;
  /** Compact variant: hides recommendations/diagnostics (modals, banners). */
  compact?: boolean;
}

const SUB_SCORE_ORDER = [
  'keyword_match',
  'skills_coverage',
  'semantic_similarity',
  'experience_alignment',
  'education_match',
  'section_completeness',
  'formatting_quality',
  'impact_quality',
] as const;

const INTERPRETATION_CLASSES: Record<string, string> = {
  excellent: 'bg-green-100 text-green-800 border-green-700',
  strong: 'bg-blue-100 text-blue-800 border-blue-700',
  moderate: 'bg-yellow-100 text-yellow-800 border-yellow-700',
  weak: 'bg-orange-100 text-orange-800 border-orange-700',
  poor: 'bg-red-100 text-red-800 border-red-700',
};
function scoreColor(value: number): string {
  if (value >= 80) return 'text-green-700';
  if (value >= 60) return 'text-yellow-700';
  return 'text-red-700';
}

function barColor(value: number): string {
  if (value >= 80) return 'bg-green-600';
  if (value >= 60) return 'bg-yellow-500';
  return 'bg-red-500';
}

function clampWidth(value: number): number {
  return Number.isFinite(value) ? Math.min(Math.max(value, 0), 100) : 0;
}

function SubScoreRow({ label, value }: { label: string; value: number | undefined }) {
  if (value === undefined || !Number.isFinite(value)) return null;
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs font-mono uppercase tracking-wide text-ink-soft">{label}</span>
        <span className={`text-xs font-mono font-semibold tabular-nums ${scoreColor(value)}`}>
          {value.toFixed(0)}%
        </span>
      </div>
      <div className="w-full bg-paper-tint h-1.5">
        <div
          className={`h-1.5 transition-all duration-500 ${barColor(value)}`}
          style={{ width: `${clampWidth(value)}%` }}
        />
      </div>
    </div>
  );
}

function DeltaBadge({ delta }: { delta: number }) {
  const { t } = useTranslations();
  const deltaRounded = Math.round(delta * 10) / 10;
  const isUp = deltaRounded > 0.05;
  const isDown = deltaRounded < -0.05;
  const icon = isUp ? (
    <TrendingUp className="w-3.5 h-3.5" />
  ) : isDown ? (
    <TrendingDown className="w-3.5 h-3.5" />
  ) : (
    <Minus className="w-3.5 h-3.5" />
  );
  const tone = isUp
    ? 'bg-green-100 text-green-800 border-green-700'
    : isDown
      ? 'bg-red-100 text-red-800 border-red-700'
      : 'bg-paper-tint text-ink-soft border-steel-grey';
  return (
    <span
      className={`inline-flex items-center gap-1 border px-2 py-0.5 font-mono text-xs font-bold ${tone}`}
      title={t('atsCard.improvementLabel')}
    >
      {icon}
      {isUp ? '+' : ''}
      {deltaRounded.toFixed(1)}
    </span>
  );
}

export function ATSScoreCard({ atsScore, baseline, compact = false }: ATSScoreCardProps) {
  const { t } = useTranslations();
  const {
    overall_score,
    sub_scores,
    matched_keywords,
    missing_keywords,
    injectable_keywords,
    recommendations,
    interpretation,
  } = atsScore;

  const baselineOverall = baseline?.overall_score;
  const delta = typeof baselineOverall === 'number' ? overall_score - baselineOverall : undefined;

  const interpretationLabel =
    interpretation && interpretation in INTERPRETATION_CLASSES
      ? t(`atsCard.interpretations.${interpretation}`)
      : '';
  const interpretationClass = interpretation
    ? (INTERPRETATION_CLASSES[interpretation] ?? 'bg-paper-tint text-ink-soft border-steel-grey')
    : '';

  return (
    <div className="border-2 border-black bg-white shadow-sw-default p-5 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3 className="font-mono text-sm font-bold uppercase tracking-wider text-ink">
            {t('atsCard.title')}
          </h3>
          {interpretationLabel && (
            <span
              className={`inline-block mt-1 border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider ${interpretationClass}`}
            >
              {interpretationLabel}
            </span>
          )}
        </div>
        <div className="flex items-end gap-2">
          {delta !== undefined && <DeltaBadge delta={delta} />}
          <div className="flex items-end gap-1">
            <span
              className={`font-serif text-4xl font-bold tabular-nums ${scoreColor(overall_score)}`}
            >
              {overall_score.toFixed(1)}
            </span>
            <span className="font-mono text-xs text-steel-grey mb-1">/100</span>
          </div>
        </div>
      </div>

      {/* Overall bar */}
      <div className="w-full bg-paper-tint h-2">
        <div
          className={`h-2 transition-all duration-500 ${barColor(overall_score)}`}
          style={{ width: `${clampWidth(overall_score)}%` }}
        />
      </div>

      {/* Baseline comparison */}
      {baseline && (
        <div className="flex items-center justify-between border border-steel-grey bg-paper-tint px-3 py-2">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-soft">
            {t('atsCard.baselineLabel')}
          </span>
          <span className="font-mono text-sm font-bold tabular-nums text-ink-soft">
            {baselineOverall !== undefined ? baselineOverall.toFixed(1) : '—'}
            <span className="text-steel-grey"> /100</span>
          </span>
        </div>
      )}

      {/* Sub-score breakdown */}
      <div className="space-y-2.5">
        <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-steel-grey">
          {t('atsCard.subScoresLabel')}
        </p>
        {SUB_SCORE_ORDER.map((key) => (
          <SubScoreRow key={key} label={t(`atsCard.subScores.${key}`)} value={sub_scores?.[key]} />
        ))}
      </div>

      {compact ? null : (
        <>
          {/* Matched keywords */}
          {matched_keywords && matched_keywords.length > 0 && (
            <div>
              <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-steel-grey mb-1.5">
                {t('atsCard.matchedKeywordsLabel')}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {matched_keywords.map((kw, i) => (
                  <span
                    key={`matched-${i}-${kw}`}
                    className="text-xs bg-green-50 border border-green-700 text-green-800 px-2 py-0.5"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Missing keywords */}
          {missing_keywords.length > 0 && (
            <div>
              <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-steel-grey mb-1.5">
                {t('atsCard.missingKeywordsLabel')}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {missing_keywords.map((kw, i) => (
                  <span
                    key={`missing-${i}-${kw}`}
                    className="text-xs bg-red-50 border border-red-700 text-red-800 px-2 py-0.5"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Injectable keywords */}
          {injectable_keywords.length > 0 && (
            <div>
              <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-steel-grey mb-1.5">
                {t('atsCard.injectableKeywordsLabel')}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {injectable_keywords.map((kw, i) => (
                  <span
                    key={`injectable-${i}-${kw}`}
                    className="text-xs bg-blue-50 border border-blue-700 text-blue-800 px-2 py-0.5"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <div>
              <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-steel-grey mb-1.5">
                {t('atsCard.recommendationsLabel')}
              </p>
              <ul className="space-y-1.5">
                {recommendations.map((tip, i) => (
                  <li
                    key={`rec-${i}-${tip.slice(0, 30)}`}
                    className="flex gap-2 text-sm text-ink-soft"
                  >
                    <span className="text-blue-700 mt-0.5 shrink-0">•</span>
                    <span>{tip}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default ATSScoreCard;
