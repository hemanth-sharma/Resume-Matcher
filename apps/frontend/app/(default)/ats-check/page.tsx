'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import FileUp from 'lucide-react/dist/esm/icons/file-up';
import FileText from 'lucide-react/dist/esm/icons/file-text';
import FolderInput from 'lucide-react/dist/esm/icons/folder-input';
import MousePointerClick from 'lucide-react/dist/esm/icons/mouse-pointer-click';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import { deleteAtsCheck, listAtsChecks, uploadAtsCheck, type AtsCheck } from '@/lib/api/ats-check';
import { useStatusCache } from '@/lib/context/status-cache';
import { useTranslations } from '@/lib/i18n';
import { AtsReportCard } from '@/components/ats-check/ats-report-card';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Button } from '@/components/ui/button';

const MAX_FILE_SIZE = 4 * 1024 * 1024; // 4MB — matches the backend cap

function scoreColorClass(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'text-ink-soft';
  }
  if (value >= 80) return 'text-green-700';
  if (value >= 60) return 'text-yellow-700';
  return 'text-red-700';
}

export default function AtsCheckPage() {
  const { t, locale } = useTranslations();
  const router = useRouter();
  const { status } = useStatusCache();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [checks, setChecks] = useState<AtsCheck[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [latestCheck, setLatestCheck] = useState<AtsCheck | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AtsCheck | null>(null);
  const loadErrorRef = useRef(false);

  const refreshChecks = useCallback(async () => {
    try {
      const data = await listAtsChecks();
      setChecks(data.checks);
      loadErrorRef.current = false;
    } catch (error) {
      if (!loadErrorRef.current) {
        loadErrorRef.current = true;
        console.error('Failed to load ATS checks:', error);
      }
    }
  }, []);

  useEffect(() => {
    void refreshChecks().finally(() => setIsLoading(false));
  }, [refreshChecks]);

  const handleFile = useCallback(
    async (file: File) => {
      setUploadError(null);
      if (file.type !== 'application/pdf' || !file.name.toLowerCase().endsWith('.pdf')) {
        setUploadError(t('atsCheck.errors.onlyPdf'));
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setUploadError(t('atsCheck.errors.tooLarge'));
        return;
      }
      setIsUploading(true);
      try {
        const record = await uploadAtsCheck(file, 'manual');
        setLatestCheck(record);
        await refreshChecks();
      } catch (error) {
        setUploadError(error instanceof Error ? error.message : t('atsCheck.errors.uploadFailed'));
      } finally {
        setIsUploading(false);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      }
    },
    [refreshChecks, t]
  );

  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setIsDragging(false);
      const file = event.dataTransfer.files?.[0];
      if (file) void handleFile(file);
    },
    [handleFile]
  );

  const onDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(true);
  }, []);

  const onDragLeave = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      await deleteAtsCheck(deleteTarget.id);
      if (latestCheck?.id === deleteTarget.id) {
        setLatestCheck(null);
      }
      setDeleteTarget(null);
      await refreshChecks();
    } catch (error) {
      console.error('Failed to delete ATS check:', error);
      setDeleteTarget(null);
    }
  }, [deleteTarget, latestCheck, refreshChecks]);

  const formatDate = useCallback(
    (iso: string) => {
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
    },
    [locale]
  );

  return (
    <main
      className="flex min-h-[100dvh] w-full flex-col bg-background px-4 py-6 md:px-8"
      style={{
        backgroundImage:
          'linear-gradient(rgba(29, 78, 216, 0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(29, 78, 216, 0.1) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }}
    >
      <div className="mx-auto flex w-full max-w-[76rem] flex-1 flex-col">
        <Link
          href="/dashboard"
          className="mb-3 inline-flex shrink-0 items-center gap-1 self-start font-mono text-xs uppercase text-ink-soft hover:text-primary"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('nav.backToDashboard')}
        </Link>

        {/* Header */}
        <div className="border border-black bg-background px-6 py-5 shadow-sw-lg md:px-8">
          <h1 className="font-serif text-3xl md:text-4xl text-black tracking-tight leading-[0.95] uppercase">
            {t('atsCheck.title')}
          </h1>
          <p className="mt-3 text-sm font-mono text-blue-700 uppercase tracking-wide font-bold">
            {'// '}
            {t('atsCheck.subtitle')}
          </p>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-5">
          {/* Upload zone */}
          <div className="lg:col-span-2">
            <div
              role="button"
              tabIndex={0}
              aria-label={t('atsCheck.uploadZone')}
              onClick={() => !isUploading && fileInputRef.current?.click()}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              onDrop={onDrop}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              className={`flex min-h-[16rem] cursor-pointer flex-col items-center justify-center gap-3 border-2 border-dashed p-6 text-center transition-colors ${
                isDragging
                  ? 'border-blue-700 bg-blue-50'
                  : 'border-steel-grey bg-white hover:border-black'
              } ${isUploading ? 'pointer-events-none opacity-70' : ''}`}
            >
              <FileUp className={`h-10 w-10 ${isDragging ? 'text-blue-700' : 'text-ink-soft'}`} />
              <p className="font-mono text-xs uppercase tracking-wide text-ink-soft">
                {isUploading ? t('atsCheck.uploading') : t('atsCheck.uploadZone')}
              </p>
              <p className="font-mono text-[10px] uppercase tracking-wider text-steel-grey">
                {t('atsCheck.onlyPdfHint')}
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void handleFile(file);
                }}
              />
            </div>

            {uploadError && (
              <div className="mt-3 flex items-start gap-2 border border-red-700 bg-red-50 px-3 py-2 text-sm text-red-800">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            {!uploadError && status && !status.llm_configured && (
              <p className="mt-3 font-mono text-[10px] uppercase tracking-wider text-ink-soft">
                {t('atsCheck.noLlmNeeded')}
              </p>
            )}
          </div>

          {/* Latest result */}
          <div className="lg:col-span-3">
            {latestCheck ? (
              latestCheck.status === 'ready' && latestCheck.score_data ? (
                <AtsReportCard scoreData={latestCheck.score_data} />
              ) : latestCheck.status === 'failed' ? (
                <div className="border-2 border-black bg-white p-5 shadow-sw-default">
                  <p className="flex items-center gap-2 font-mono text-sm font-bold uppercase text-red-700">
                    <AlertCircle className="h-4 w-4" />
                    {t('atsCheck.checkFailed')}
                  </p>
                  <p className="mt-2 text-sm text-ink-soft">
                    {latestCheck.error || t('atsCheck.errors.uploadFailed')}
                  </p>
                </div>
              ) : (
                <div className="border-2 border-black bg-white p-5 shadow-sw-default">
                  <p className="font-mono text-sm uppercase text-ink-soft">
                    {t('atsCheck.uploading')}
                  </p>
                </div>
              )
            ) : (
              <div className="flex h-full min-h-[16rem] flex-col items-center justify-center gap-3 border border-steel-grey bg-paper-tint p-6 text-center">
                <MousePointerClick className="h-8 w-8 text-steel-grey" />
                <p className="font-mono text-xs uppercase tracking-wide text-ink-soft">
                  {t('atsCheck.resultPlaceholder')}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* History */}
        <div className="mt-6 border border-black bg-background shadow-sw-lg">
          <div className="flex items-center justify-between border-b border-black px-6 py-3">
            <h2 className="font-mono text-sm font-bold uppercase tracking-wider text-ink">
              {t('atsCheck.historyTitle')}
            </h2>
            <span className="font-mono text-[10px] uppercase tracking-wider text-steel-grey">
              {checks.length} {checks.length === 1 ? t('atsCheck.entry') : t('atsCheck.entries')}
            </span>
          </div>

          {isLoading ? (
            <div className="px-6 py-8 text-center font-mono text-xs uppercase text-ink-soft">
              {t('common.loading')}
            </div>
          ) : checks.length === 0 ? (
            <div className="px-6 py-10 text-center">
              <FileText className="mx-auto h-8 w-8 text-steel-grey" />
              <p className="mt-2 font-mono text-xs uppercase tracking-wide text-ink-soft">
                {t('atsCheck.historyEmpty')}
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-steel-grey">
              {checks.map((check) => (
                <li
                  key={check.id}
                  className="group flex cursor-pointer items-center gap-3 px-4 py-3 transition-colors hover:bg-paper-tint sm:px-6"
                  onClick={() => router.push(`/ats-check/${check.id}`)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') router.push(`/ats-check/${check.id}`);
                  }}
                  tabIndex={0}
                  role="button"
                  aria-label={`${t('atsCheck.viewDetails')}: ${check.file_name}`}
                >
                  <span className="font-mono text-[10px] text-steel-grey tabular-nums w-8 shrink-0">
                    #{check.id}
                  </span>

                  <FileText className="h-4 w-4 shrink-0 text-ink-soft" />

                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-ink">{check.file_name}</p>
                    <p className="font-mono text-[10px] uppercase tracking-wider text-steel-grey">
                      {formatDate(check.created_at)}
                      {' · '}
                      {check.source === 'folder_watch'
                        ? t('atsCheck.sourceFolderWatch')
                        : t('atsCheck.sourceManual')}
                    </p>
                  </div>

                  {check.status === 'failed' ? (
                    <span className="shrink-0 border border-red-700 bg-red-50 px-2 py-0.5 font-mono text-[10px] font-bold uppercase text-red-800">
                      {t('atsCheck.failedBadge')}
                    </span>
                  ) : check.status === 'processing' ? (
                    <span className="shrink-0 border border-steel-grey bg-paper-tint px-2 py-0.5 font-mono text-[10px] font-bold uppercase text-ink-soft">
                      {t('atsCheck.pendingBadge')}
                    </span>
                  ) : (
                    <span
                      className={`shrink-0 font-serif text-2xl font-bold tabular-nums ${scoreColorClass(
                        check.overall_score
                      )}`}
                      title={t('atsCheck.scoreLabel')}
                    >
                      {check.overall_score?.toFixed(1) ?? '—'}
                    </span>
                  )}

                  <Button
                    variant="ghost"
                    size="icon"
                    className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
                    aria-label={t('atsCheck.delete')}
                    onClick={(event) => {
                      event.stopPropagation();
                      setDeleteTarget(check);
                    }}
                  >
                    <Trash2 className="h-4 w-4 text-ink-soft hover:text-destructive" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Folder-watcher hint */}
        <div className="mt-4 mb-6 flex items-start gap-2 border border-steel-grey bg-paper-tint px-4 py-3">
          <FolderInput className="mt-0.5 h-4 w-4 shrink-0 text-ink-soft" />
          <p className="text-xs text-ink-soft">{t('atsCheck.watcherHint')}</p>
        </div>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={t('atsCheck.deleteConfirmTitle')}
        description={t('atsCheck.deleteConfirmDescription')}
        confirmLabel={t('atsCheck.delete')}
        variant="danger"
        onConfirm={handleDelete}
      />
    </main>
  );
}
