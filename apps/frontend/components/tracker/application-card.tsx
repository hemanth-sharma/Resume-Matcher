'use client';

import React from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import GripVertical from 'lucide-react/dist/esm/icons/grip-vertical';
import Layers from 'lucide-react/dist/esm/icons/layers';
import Gauge from 'lucide-react/dist/esm/icons/gauge';
import { Card } from '@/components/ui/card';
import { useTranslations } from '@/lib/i18n';
import type { Application } from '@/lib/api/tracker';

interface ApplicationCardProps {
  application: Application;
  selected: boolean;
  sharedResume: boolean;
  onToggleSelect: (id: string) => void;
  onOpen: (id: string) => void;
}

/** Color band for the ATS score chip, matching the score card palette. */
function atsChipClass(score: number): string {
  if (score >= 80) return 'bg-green-100 text-green-800 border-green-700';
  if (score >= 60) return 'bg-yellow-100 text-yellow-800 border-yellow-700';
  if (score >= 40) return 'bg-orange-100 text-orange-800 border-orange-700';
  return 'bg-red-100 text-red-800 border-red-700';
}

export function ApplicationCard({
  application,
  selected,
  sharedResume,
  onToggleSelect,
  onOpen,
}: ApplicationCardProps) {
  const { t } = useTranslations();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: application.application_id,
  });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const company = application.company?.trim();
  const role = application.role?.trim();

  return (
    <div ref={setNodeRef} style={style}>
      <Card
        variant="interactive"
        noPadding
        className={`p-3 ${selected ? 'ring-2 ring-primary' : ''}`}
      >
        <div className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(application.application_id)}
            onClick={(e) => e.stopPropagation()}
            aria-label={t('tracker.card.selectAria')}
            className="mt-1 h-4 w-4 shrink-0 rounded-none border-black accent-primary"
          />

          <button
            type="button"
            onClick={() => onOpen(application.application_id)}
            className="min-w-0 flex-1 text-left"
          >
            <p className="truncate text-sm font-semibold text-ink">
              {company || t('tracker.card.companyUnknown')}
            </p>
            <p className="truncate font-mono text-xs text-ink-soft">
              {role || t('tracker.card.roleUnknown')}
            </p>
            {application.applied_at && (
              <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-steel-grey">
                {new Date(application.applied_at).toLocaleDateString()}
              </p>
            )}
            <div className="mt-1 flex flex-wrap items-center gap-1">
              {typeof application.ats_score === 'number' &&
                Number.isFinite(application.ats_score) && (
                  <span
                    className={`inline-flex items-center gap-1 border px-1.5 py-0.5 font-mono text-[10px] font-bold tabular-nums ${atsChipClass(application.ats_score)}`}
                    title={t('tracker.card.atsScore')}
                  >
                    <Gauge className="h-3 w-3" />
                    {Math.round(application.ats_score)}
                  </span>
                )}
              {sharedResume && (
                <span className="inline-flex items-center gap-1 border border-black bg-paper-tint px-1 font-mono text-[10px] uppercase text-ink-soft">
                  <Layers className="h-3 w-3" />
                  {t('tracker.card.sharedResume')}
                </span>
              )}
            </div>
          </button>

          <button
            type="button"
            className="mt-0.5 shrink-0 cursor-grab text-steel-grey hover:text-ink active:cursor-grabbing"
            aria-label={t('tracker.card.dragAria')}
            {...attributes}
            {...listeners}
          >
            <GripVertical className="h-4 w-4" />
          </button>
        </div>
      </Card>
    </div>
  );
}
