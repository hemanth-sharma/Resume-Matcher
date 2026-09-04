import React from 'react';
import type { PersonalInfo } from '@/components/dashboard/resume-component';

interface ResumePhotoProps {
  personalInfo?: PersonalInfo;
  showPhoto?: boolean;
  /** Tailwind classes controlling size/shape; defaults to a 3rem square. */
  className?: string;
}

/**
 * Profile photo rendered in resume headers when the photo setting is enabled
 * and the resume carries a photo (data URL). Renders nothing otherwise, so
 * templates can drop it in unconditionally.
 */
export const ResumePhoto: React.FC<ResumePhotoProps> = ({
  personalInfo,
  showPhoto,
  className = 'w-12 h-12',
}) => {
  const photo = personalInfo?.photo;
  if (!showPhoto || !photo || typeof photo !== 'string') {
    return null;
  }

  return (
    /* eslint-disable-next-line @next/next/no-img-element -- data URL, no optimizer */
    <img
      src={photo}
      alt={personalInfo?.name || 'Profile photo'}
      className={`${className} shrink-0 object-cover border`}
      style={{ borderColor: 'var(--resume-border-primary, #000)' }}
    />
  );
};

export default ResumePhoto;
