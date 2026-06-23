import type { InterviewPracticeSession, ProgressRecord } from "@/types/speaking";

const STORAGE_KEY = "speaking-practice-progress";

export const defaultProgress: ProgressRecord = {
  completedCardIds: [],
  practiceDate: null,
  sentenceCount: 0,
  streakDots: [false, false, false, false, false, false, false],
  privacyNoticeAccepted: false,
  interviewSessions: []
};

function canUseStorage() {
  return typeof window !== "undefined" && Boolean(window.localStorage);
}

export function loadProgress(): ProgressRecord {
  if (!canUseStorage()) {
    return defaultProgress;
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return defaultProgress;
    }

    return {
      ...defaultProgress,
      ...JSON.parse(stored)
    };
  } catch {
    return defaultProgress;
  }
}

export function saveProgress(progress: ProgressRecord) {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
}

export function acceptPrivacyNotice(): ProgressRecord {
  const next = {
    ...loadProgress(),
    privacyNoticeAccepted: true
  };
  saveProgress(next);
  return next;
}

export function completeCard(cardId: string): ProgressRecord {
  const current = loadProgress();
  const today = new Date().toISOString().slice(0, 10);
  const completedCardIds = current.completedCardIds.includes(cardId)
    ? current.completedCardIds
    : [...current.completedCardIds, cardId];

  const next: ProgressRecord = {
    ...current,
    completedCardIds,
    practiceDate: today,
    sentenceCount: current.sentenceCount + 1,
    streakDots: [...current.streakDots.slice(1), true]
  };

  saveProgress(next);
  return next;
}

export function completeInterviewSession(
  session: InterviewPracticeSession
): ProgressRecord {
  const current = loadProgress();
  const today = new Date().toISOString().slice(0, 10);
  const existingSessions = current.interviewSessions.filter(
    (item) => item.id !== session.id
  );

  const next: ProgressRecord = {
    ...current,
    interviewSessions: [session, ...existingSessions].slice(0, 30),
    practiceDate: today,
    sentenceCount: current.sentenceCount + 1,
    streakDots: [...current.streakDots.slice(1), true]
  };

  saveProgress(next);
  return next;
}
