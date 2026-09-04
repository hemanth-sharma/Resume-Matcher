import React from 'react';
import {
  ResumeSingleColumn,
  ResumeTwoColumn,
  ResumeModern,
  ResumeModernTwoColumn,
  ResumeLatex,
  ResumeClean,
  ResumeVivid,
} from '@/components/resume';
import {
  type TemplateSettings,
  type TemplateType,
  DEFAULT_TEMPLATE_SETTINGS,
  settingsToCssVars,
} from '@/lib/types/template-settings';
import baseStyles from '@/components/resume/styles/_base.module.css';

export interface PersonalInfo {
  name?: string;
  title?: string;
  email?: string;
  phone?: string;
  location?: string;
  website?: string;
  linkedin?: string;
  github?: string;
  /** Optional profile photo (data URL) rendered when the photo setting is on. */
  photo?: string | null;
}

export interface Experience {
  id: number;
  title?: string;
  company?: string;
  location?: string;
  years?: string;
  description?: string[];
  descriptionStyles?: ('bullet' | 'plain')[];
}

export interface Education {
  id: number;
  institution?: string;
  degree?: string;
  years?: string;
  description?: string;
}

export interface Project {
  id: number;
  name?: string;
  role?: string;
  years?: string;
  github?: string;
  website?: string;
  description?: string[];
  descriptionStyles?: ('bullet' | 'plain')[];
}

export interface AdditionalInfo {
  technicalSkills?: string[];
  languages?: string[];
  certificationsTraining?: string[];
  awards?: string[];
}

export interface AdditionalSectionLabels {
  technicalSkills: string;
  languages: string;
  certifications: string;
  awards: string;
}

export interface ResumeSectionHeadings {
  summary: string;
  experience: string;
  education: string;
  projects: string;
  certifications: string;
  skills: string;
  languages: string;
  awards: string;
  links: string;
}

export interface ResumeFallbackLabels {
  name: string;
}

// Section Type for dynamic sections
export type SectionType = 'personalInfo' | 'text' | 'itemList' | 'stringList';

// Section Metadata for dynamic section management
export interface SectionMeta {
  id: string; // Unique identifier (e.g., "summary", "custom_1")
  key: string; // Data key (matches ResumeData field or customSections key)
  displayName: string; // User-visible name
  sectionType: SectionType; // Type of section
  isDefault: boolean; // True for built-in sections
  isVisible: boolean; // Whether to show in resume
  order: number; // Display order (0 = first after personalInfo)
}

// Generic item for custom item-based sections
export interface CustomSectionItem {
  id: number;
  title?: string; // Primary title
  subtitle?: string; // Secondary info (company, institution, etc.)
  location?: string;
  years?: string;
  description?: string[];
  descriptionStyles?: ('bullet' | 'plain')[];
}

// Custom section data container
export interface CustomSection {
  sectionType: SectionType;
  items?: CustomSectionItem[]; // For itemList type
  strings?: string[]; // For stringList type
  text?: string; // For text type
}

export interface ResumeData {
  personalInfo?: PersonalInfo;
  summary?: string;
  workExperience?: Experience[];
  education?: Education[];
  personalProjects?: Project[];
  additional?: AdditionalInfo;
  // NEW: Section metadata and custom sections
  sectionMeta?: SectionMeta[];
  customSections?: Record<string, CustomSection>;
}

interface ResumeProps {
  resumeData: ResumeData;
  template?: TemplateType;
  settings?: TemplateSettings;
  additionalSectionLabels?: Partial<AdditionalSectionLabels>;
  sectionHeadings?: Partial<ResumeSectionHeadings>;
  fallbackLabels?: Partial<ResumeFallbackLabels>;
  /**
   * Content locale ("zh" | "ja" | "ko" | ...). Orders the CJK font fallback
   * stack so a shared codepoint resolves to the right regional face.
   */
  locale?: string;
}

/**
 * Resume Component
 *
 * Main wrapper component that delegates rendering to template-specific components.
 * Applies CSS custom properties from settings for consistent styling.
 *
 * Templates:
 * - swiss-single: Traditional single-column layout (default)
 * - swiss-two-column: Two-column layout with experience sidebar
 * - modern: Single-column with user-selectable accent colors
 * - modern-two-column: Two-column layout with modern colorful accents
 */
const Resume: React.FC<ResumeProps> = ({
  resumeData,
  template = 'swiss-single',
  settings,
  additionalSectionLabels,
  sectionHeadings,
  fallbackLabels,
  locale,
}) => {
  // Merge provided settings with defaults
  const mergedSettings: TemplateSettings = {
    ...DEFAULT_TEMPLATE_SETTINGS,
    ...settings,
    margins: { ...DEFAULT_TEMPLATE_SETTINGS.margins, ...settings?.margins },
    spacing: { ...DEFAULT_TEMPLATE_SETTINGS.spacing, ...settings?.spacing },
    fontSize: { ...DEFAULT_TEMPLATE_SETTINGS.fontSize, ...settings?.fontSize },
  };

  // If template is provided as prop but not in settings, use the prop
  if (template && !settings?.template) {
    mergedSettings.template = template;
  }

  // Convert settings to CSS variables
  const cssVars = settingsToCssVars(mergedSettings, locale);

  // One-page mode: tighten spacing/line-height beyond compact mode. Content
  // condensation happens at tailoring time (one_page flag on the improve
  // request); this keeps the layout tight so the trimmed content fits.
  const effectiveSettings: TemplateSettings = mergedSettings.onePage
    ? {
        ...mergedSettings,
        compactMode: true,
        spacing: {
          section: Math.min(
            mergedSettings.spacing.section,
            2
          ) as TemplateSettings['spacing']['section'],
          item: Math.min(mergedSettings.spacing.item, 2) as TemplateSettings['spacing']['item'],
          lineHeight: Math.min(
            mergedSettings.spacing.lineHeight,
            2
          ) as TemplateSettings['spacing']['lineHeight'],
        },
      }
    : mergedSettings;

  const showPhoto = effectiveSettings.showPhoto && Boolean(resumeData.personalInfo?.photo);

  return (
    <div
      className={`${baseStyles['resume-body']} bg-white text-black w-full mx-auto resume-template-${effectiveSettings.template}${effectiveSettings.onePage ? ' resume-one-page' : ''}`}
      style={cssVars}
    >
      {effectiveSettings.template === 'swiss-single' && (
        <ResumeSingleColumn
          data={resumeData}
          showContactIcons={effectiveSettings.showContactIcons}
          showPhoto={showPhoto}
          additionalSectionLabels={additionalSectionLabels}
        />
      )}
      {effectiveSettings.template === 'swiss-two-column' && (
        <ResumeTwoColumn
          data={resumeData}
          showContactIcons={effectiveSettings.showContactIcons}
          showPhoto={showPhoto}
          sectionHeadings={sectionHeadings}
        />
      )}
      {effectiveSettings.template === 'modern' && (
        <ResumeModern
          data={resumeData}
          showContactIcons={effectiveSettings.showContactIcons}
          showPhoto={showPhoto}
          additionalSectionLabels={additionalSectionLabels}
        />
      )}
      {effectiveSettings.template === 'modern-two-column' && (
        <ResumeModernTwoColumn
          data={resumeData}
          showContactIcons={effectiveSettings.showContactIcons}
          showPhoto={showPhoto}
          sectionHeadings={sectionHeadings}
          fallbackLabels={fallbackLabels}
        />
      )}
      {effectiveSettings.template === 'latex' && (
        <ResumeLatex
          data={resumeData}
          showContactIcons={effectiveSettings.showContactIcons}
          showPhoto={showPhoto}
          additionalSectionLabels={additionalSectionLabels}
        />
      )}
      {effectiveSettings.template === 'clean' && (
        <ResumeClean
          data={resumeData}
          showContactIcons={effectiveSettings.showContactIcons}
          showPhoto={showPhoto}
          additionalSectionLabels={additionalSectionLabels}
        />
      )}
      {effectiveSettings.template === 'vivid' && (
        <ResumeVivid
          data={resumeData}
          showContactIcons={effectiveSettings.showContactIcons}
          showPhoto={showPhoto}
          sectionHeadings={sectionHeadings}
          fallbackLabels={fallbackLabels}
        />
      )}
    </div>
  );
};

export default Resume;
