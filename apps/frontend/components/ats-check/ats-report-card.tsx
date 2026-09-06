'use client';

import React from 'react';
import { Check, X } from 'lucide-react';
import type { AtsScoreData, AtsScoreDetails } from '@/lib/api/ats-check';
import { useTranslations } from '@/lib/i18n';

const SUB_SCORE_ORDER = [
  'contact_info',
  'section_completeness',
  'formatting_quality',
  'impact_quality',
  'keyword_optimization',
  'readability_structure',
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

/** Contact-field checklist rendered from the engine's contact details. */
function ContactChecklist({ details }: { details: AtsScoreDetails | null }) {
  const { t } = useTranslations();
  const contact = details?.contact;
  if (!contact) return null;

  const entries: Array<[string, boolean]> = [
    ['email', contact.email],
    ['phone', contact.phone],
    ['link', contact.professional_link],
    ['location', contact.location],
    ['name', contact.name_line],
  ];

  return (
    <div>
      <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-steel-grey mb-1.5">
        {t('atsCheck.report.contactFieldsLabel')}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {entries.map(([key, present]) => (
          <span
            key={key}
            className={`inline-flex items-center gap-1 text-xs border px-2 py-0.5 ${
              present
                ? 'bg-green-50 border-green-700 text-green-800'
                : 'bg-red-50 border-red-700 text-red-800'
            }`}
          >
            {present ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
            {t(`atsCheck.report.contactFields.${key}`)}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Quick stats strip (words, bullets, dates, skills found). */
function QuickStats({ details }: { details: AtsScoreDetails | null }) {
  const { t } = useTranslations();
  if (!details) return null;
  const formatting = details.formatting;
  const impact = details.impact;
  const keywords = details.keywords;
  if (!formatting && !impact && !keywords) return null;

  const stats: Array<{ label: string; value: string | number }> = [];
  if (formatting) {
    stats.push({ label: t('atsCheck.report.words'), value: formatting.total_words });
    stats.push({ label: t('atsCheck.report.bullets'), value: formatting.bullet_lines });
    stats.push({ label: t('atsCheck.report.dateRanges'), value: formatting.date_ranges_found });
  }
  if (keywords) {
    stats.push({ label: t('atsCheck.report.skillsFound'), value: keywords.distinct_known_skills });
  }
  if (impact) {
    stats.push({ label: t('atsCheck.report.quantified'), value: impact.quantified_bullets });
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 border border-steel-grey divide-x divide-y sm:divide-y-0 divide-steel-grey">
      {stats.map((stat) => (
        <div key={stat.label} className="px-3 py-2 text-center">
          <p className="font-serif text-lg font-bold tabular-nums text-ink">{stat.value}</p>
          <p className="font-mono text-[9px] uppercase tracking-wider text-ink-soft">
            {stat.label}
          </p>
        </div>
      ))}
    </div>
  );
}

interface AtsReportCardProps {
  scoreData: AtsScoreData;
  /** Compact variant hides diagnostics (list rows, small panels). */
  compact?: boolean;
}

/**
 * Standalone ATS report card — renders the resume-only (no job description)
 * score produced by the backend's standalone engine.
 */
export function AtsReportCard({ scoreData, compact = false }: AtsReportCardProps) {
  const { t } = useTranslations();
  const { overall_score, sub_scores, recommendations, interpretation, details } = scoreData;

  const interpretationLabel =
    interpretation && interpretation in INTERPRETATION_CLASSES
      ? t(`atsCheck.report.interpretations.${interpretation}`)
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
            {t('atsCheck.report.title')}
          </h3>
          {interpretationLabel && (
            <span
              className={`inline-block mt-1 border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider ${interpretationClass}`}
            >
              {interpretationLabel}
            </span>
          )}
        </div>
        <div className="flex items-end gap-1">
          <span
            className={`font-serif text-4xl font-bold tabular-nums ${scoreColor(overall_score)}`}
          >
            {overall_score.toFixed(1)}
          </span>
          <span className="font-mono text-xs text-steel-grey mb-1">/100</span>
        </div>
      </div>

      {/* Overall bar */}
      <div className="w-full bg-paper-tint h-2">
        <div
          className={`h-2 transition-all duration-500 ${barColor(overall_score)}`}
          style={{ width: `${clampWidth(overall_score)}%` }}
        />
      </div>

      {/* Sub-score breakdown */}
      <div className="space-y-2.5">
        <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-steel-grey">
          {t('atsCheck.report.subScoresLabel')}
        </p>
        {SUB_SCORE_ORDER.map((key) => (
          <SubScoreRow
            key={key}
            label={t(`atsCheck.report.subScores.${key}`)}
            value={sub_scores?.[key]}
          />
        ))}
      </div>

      {compact ? null : (
        <>
          <QuickStats details={details} />
          <ContactChecklist details={details} />

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <div>
              <p className="font-mono text-[10px] font-bold uppercase tracking-wider text-steel-grey mb-1.5">
                {t('atsCheck.report.recommendationsLabel')}
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

export default AtsReportCard;
