'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import FileText from 'lucide-react/dist/esm/icons/file-text';
import RefreshCw from 'lucide-react/dist/esm/icons/refresh-cw';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import { getAtsCheckDetail, type AtsCheck } from '@/lib/api/ats-check';
import { useTranslations } from '@/lib/i18n';
import { AtsReportCard } from '@/components/ats-check/ats-report-card';
import { Button } from '@/components/ui/button';

export default function AtsCheckDetailPage() {
  const { t, locale } = useTranslations();
  const params = useParams<{ id: string }>();
  const checkId = params?.id;

  const [check, setCheck] = useState<AtsCheck | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCheck = React.useCallback(async () => {
    if (!checkId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await getAtsCheckDetail(checkId);
      setCheck(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('errors.generic'));
    } finally {
      setIsLoading(false);
    }
  }, [checkId, t]);

  useEffect(() => {
    void loadCheck();
  }, [loadCheck]);

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return iso;
    }
  };

  return (
    <main
      className="flex min-h-[100dvh] w-full flex-col bg-background px-4 py-6 md:px-8"
      style={{
        backgroundImage:
          'linear-gradient(rgba(29, 78, 216, 0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(29, 78, 216, 0.1) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }}
    >
      <div className="mx-auto flex w-full max-w-[52rem] flex-1 flex-col">
        <div className="mb-3 flex items-center justify-between">
          <Link
            href="/ats-check"
            className="inline-flex shrink-0 items-center gap-1 font-mono text-xs uppercase text-ink-soft hover:text-primary"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            {t('atsCheck.backToChecks')}
          </Link>
          <Button variant="ghost" size="sm" onClick={() => void loadCheck()} disabled={isLoading}>
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            {t('common.refresh')}
          </Button>
        </div>

        {isLoading ? (
          <div className="flex min-h-[24rem] items-center justify-center border border-black bg-background shadow-sw-lg">
            <p className="font-mono text-xs uppercase tracking-wide text-ink-soft">
              {t('common.loading')}
            </p>
          </div>
        ) : error ? (
          <div className="flex min-h-[24rem] flex-col items-center justify-center gap-3 border border-black bg-background shadow-sw-lg">
            <AlertCircle className="h-8 w-8 text-destructive" />
            <p className="text-sm text-ink-soft">{error}</p>
            <Button variant="outline" size="sm" onClick={() => void loadCheck()}>
              {t('common.retry')}
            </Button>
          </div>
        ) : check ? (
          <>
            {/* File header */}
            <div className="border border-black bg-background px-6 py-4 shadow-sw-lg">
              <div className="flex flex-wrap items-center gap-3">
                <FileText className="h-5 w-5 shrink-0 text-ink-soft" />
                <h1 className="min-w-0 flex-1 truncate font-serif text-2xl text-black tracking-tight md:text-3xl">
                  {check.file_name}
                </h1>
                <span className="font-mono text-[10px] uppercase tracking-wider text-steel-grey">
                  #{check.id}
                </span>
              </div>
              <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-ink-soft">
                {formatDate(check.created_at)}
                {' · '}
                {check.source === 'folder_watch'
                  ? t('atsCheck.sourceFolderWatch')
                  : t('atsCheck.sourceManual')}
              </p>
            </div>

            {/* Report */}
            <div className="mt-4 mb-6">
              {check.status === 'ready' && check.score_data ? (
                <AtsReportCard scoreData={check.score_data} />
              ) : check.status === 'failed' ? (
                <div className="border-2 border-black bg-white p-5 shadow-sw-default">
                  <p className="flex items-center gap-2 font-mono text-sm font-bold uppercase text-red-700">
                    <AlertCircle className="h-4 w-4" />
                    {t('atsCheck.checkFailed')}
                  </p>
                  <p className="mt-2 text-sm text-ink-soft">
                    {check.error || t('atsCheck.errors.uploadFailed')}
                  </p>
                </div>
              ) : (
                <div className="border-2 border-black bg-white p-5 shadow-sw-default">
                  <p className="font-mono text-sm uppercase text-ink-soft">
                    {t('atsCheck.pendingBadge')}
                  </p>
                </div>
              )}
            </div>
          </>
        ) : null}
      </div>
    </main>
  );
}
