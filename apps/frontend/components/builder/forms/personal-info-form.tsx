'use client';

import React, { useRef, useState } from 'react';
import { Image as ImageIcon, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PersonalInfo } from '@/components/dashboard/resume-component';
import { useTranslations } from '@/lib/i18n';

interface PersonalInfoFormProps {
  data: PersonalInfo;
  onChange: (data: PersonalInfo) => void;
}

/** Max photo size before base64 encoding (the data URL is ~1.37x larger). */
const MAX_PHOTO_BYTES = 1.5 * 1024 * 1024;
const PHOTO_ACCEPTED = 'image/jpeg,image/jpg,image/png,image/webp';

export const PersonalInfoForm: React.FC<PersonalInfoFormProps> = ({ data, onChange }) => {
  const { t } = useTranslations();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);

  const handleChange = (field: keyof PersonalInfo, value: string) => {
    onChange({
      ...data,
      [field]: value,
    });
  };

  const handlePhotoSelected = (file: File | undefined) => {
    setPhotoError(null);
    if (!file) return;
    if (!PHOTO_ACCEPTED.includes(file.type)) {
      setPhotoError(t('builder.personalInfoForm.photo.errors.format'));
      return;
    }
    if (file.size > MAX_PHOTO_BYTES) {
      setPhotoError(t('builder.personalInfoForm.photo.errors.tooLarge'));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        onChange({ ...data, photo: reader.result });
      }
    };
    reader.onerror = () => setPhotoError(t('builder.personalInfoForm.photo.errors.read'));
    reader.readAsDataURL(file);
  };

  const handleRemovePhoto = () => {
    setPhotoError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    onChange({ ...data, photo: null });
  };

  return (
    <div className="space-y-4 border border-black p-6 bg-white shadow-sw-default">
      <h3 className="font-serif text-xl font-bold border-b border-black pb-2 mb-4">
        {t('builder.personalInfo')}
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label
            htmlFor="name"
            className="font-mono text-xs uppercase tracking-wider text-steel-grey"
          >
            {t('resume.personalInfo.name')}
          </Label>
          <Input
            id="name"
            value={data.name || ''}
            onChange={(e) => handleChange('name', e.target.value)}
            placeholder={t('builder.personalInfoForm.placeholders.name')}
            className="rounded-none border-black focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:border-blue-700 bg-transparent"
          />
        </div>
        <div className="space-y-2">
          <Label
            htmlFor="title"
            className="font-mono text-xs uppercase tracking-wider text-steel-grey"
          >
            {t('resume.personalInfo.title')}
          </Label>
          <Input
            id="title"
            value={data.title || ''}
            onChange={(e) => handleChange('title', e.target.value)}
            placeholder={t('builder.personalInfoForm.placeholders.title')}
            className="rounded-none border-black focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:border-blue-700 bg-transparent"
          />
        </div>
        <div className="space-y-2">
          <Label
            htmlFor="email"
            className="font-mono text-xs uppercase tracking-wider text-steel-grey"
          >
            {t('resume.personalInfo.email')}
          </Label>
          <Input
            id="email"
            type="email"
            value={data.email || ''}
            onChange={(e) => handleChange('email', e.target.value)}
            placeholder={t('builder.personalInfoForm.placeholders.email')}
            className="rounded-none border-black focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:border-blue-700 bg-transparent"
          />
        </div>
        <div className="space-y-2">
          <Label
            htmlFor="phone"
            className="font-mono text-xs uppercase tracking-wider text-steel-grey"
          >
            {t('resume.personalInfo.phone')}
          </Label>
          <Input
            id="phone"
            type="tel"
            value={data.phone || ''}
            onChange={(e) => handleChange('phone', e.target.value)}
            placeholder={t('builder.personalInfoForm.placeholders.phone')}
            className="rounded-none border-black focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:border-blue-700 bg-transparent"
          />
        </div>
        <div className="space-y-2">
          <Label
            htmlFor="location"
            className="font-mono text-xs uppercase tracking-wider text-steel-grey"
          >
            {t('resume.personalInfo.location')}
          </Label>
          <Input
            id="location"
            value={data.location || ''}
            onChange={(e) => handleChange('location', e.target.value)}
            placeholder={t('builder.personalInfoForm.placeholders.location')}
            className="rounded-none border-black focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:border-blue-700 bg-transparent"
          />
        </div>
        <div className="space-y-2">
          <Label
            htmlFor="website"
            className="font-mono text-xs uppercase tracking-wider text-steel-grey"
          >
            {t('resume.personalInfo.website')}
          </Label>
          <Input
            id="website"
            value={data.website || ''}
            onChange={(e) => handleChange('website', e.target.value)}
            placeholder={t('builder.personalInfoForm.placeholders.website')}
            className="rounded-none border-black focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:border-blue-700 bg-transparent"
          />
        </div>
        <div className="space-y-2">
          <Label
            htmlFor="linkedin"
            className="font-mono text-xs uppercase tracking-wider text-steel-grey"
          >
            {t('resume.personalInfo.linkedin')}
          </Label>
          <Input
            id="linkedin"
            value={data.linkedin || ''}
            onChange={(e) => handleChange('linkedin', e.target.value)}
            placeholder={t('builder.personalInfoForm.placeholders.linkedin')}
            className="rounded-none border-black focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:border-blue-700 bg-transparent"
          />
        </div>
        <div className="space-y-2">
          <Label
            htmlFor="github"
            className="font-mono text-xs uppercase tracking-wider text-steel-grey"
          >
            {t('resume.personalInfo.github')}
          </Label>
          <Input
            id="github"
            value={data.github || ''}
            onChange={(e) => handleChange('github', e.target.value)}
            placeholder={t('builder.personalInfoForm.placeholders.github')}
            className="rounded-none border-black focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:border-blue-700 bg-transparent"
          />
        </div>
      </div>

      {/* Profile photo (rendered when the template's photo setting is on) */}
      <div className="pt-2 border-t border-paper-tint space-y-2">
        <Label
          htmlFor="photo"
          className="font-mono text-xs uppercase tracking-wider text-steel-grey"
        >
          {t('builder.personalInfoForm.photo.label')}
        </Label>
        <p className="font-mono text-[11px] text-steel-grey">
          {t('builder.personalInfoForm.photo.hint')}
        </p>
        <div className="flex items-center gap-4">
          {data.photo ? (
            /* eslint-disable-next-line @next/next/no-img-element -- local data URL preview */
            <img
              src={data.photo}
              alt={t('builder.personalInfoForm.photo.previewAlt')}
              className="w-16 h-16 object-cover border border-black shrink-0"
            />
          ) : (
            <div className="w-16 h-16 border border-dashed border-steel-grey flex items-center justify-center shrink-0">
              <ImageIcon className="w-5 h-5 text-steel-grey" />
            </div>
          )}
          <input
            ref={fileInputRef}
            id="photo"
            type="file"
            accept={PHOTO_ACCEPTED}
            className="hidden"
            onChange={(e) => handlePhotoSelected(e.target.files?.[0])}
          />
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
            >
              <ImageIcon className="w-3.5 h-3.5" />
              {data.photo
                ? t('builder.personalInfoForm.photo.replace')
                : t('builder.personalInfoForm.photo.upload')}
            </Button>
            {data.photo && (
              <Button type="button" variant="outline" size="sm" onClick={handleRemovePhoto}>
                <Trash2 className="w-3.5 h-3.5" />
                {t('builder.personalInfoForm.photo.remove')}
              </Button>
            )}
          </div>
        </div>
        {photoError && <p className="font-mono text-xs text-red-600">{photoError}</p>}
      </div>
    </div>
  );
};
