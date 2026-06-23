import type {
  FocusSound,
  InterviewMaterials,
  InterviewPracticeReview
} from "@/types/speaking";

export const focusSounds: FocusSound[] = [
  "/h/",
  "/f/",
  "/v/",
  "/uː/",
  "/ʊ/",
  "/l/",
  "/r/",
  "/θ/",
  "/ð/"
];

export const defaultFocusSound: FocusSound = "/h/";

export const maxInterviewAudioBytes = 25 * 1024 * 1024;

export const minimumInterviewRecordingMs = 800;

export const audioConfig = {
  speechToTextProvider: "groq-whisper",
  speechToTextModel: "whisper-large-v3-turbo",
  textToSpeechProvider: "none",
  reviewMode: "transcript_based"
} as const;

const groqAudioMimeExtensions: Record<string, string> = {
  "audio/webm": "webm",
  "audio/mp4": "mp4",
  "audio/mpeg": "mpeg",
  "audio/mpga": "mpga",
  "audio/m4a": "m4a",
  "audio/ogg": "ogg",
  "audio/wav": "wav"
};

export const focusSoundCues: Record<FocusSound, string> = {
  "/h/": "Start with a light breath before the vowel. Do not use your lips or teeth.",
  "/f/": "Touch your upper teeth to your lower lip and let quiet air pass through.",
  "/v/": "Use the same lip shape as /f/, but add voice and vibration.",
  "/uː/": "Keep the vowel long and rounded, as in move or improve.",
  "/ʊ/": "Keep it short and relaxed, as in good or look.",
  "/l/": "Touch the tongue tip behind the upper teeth before releasing the vowel.",
  "/r/": "Keep the tongue back from the teeth and avoid adding an /l/ sound.",
  "/θ/": "Place the tongue lightly between the teeth and release quiet air.",
  "/ð/": "Use the same tongue position as /θ/, but add voice."
};

const focusWords: Record<FocusSound, string[]> = {
  "/h/": ["helped", "handle", "highlight"],
  "/f/": ["focused", "feedback", "faster"],
  "/v/": ["value", "review", "improve"],
  "/uː/": ["improve", "useful", "smooth"],
  "/ʊ/": ["good", "looked", "could"],
  "/l/": ["clear", "learned", "result"],
  "/r/": ["role", "result", "process"],
  "/θ/": ["think", "through", "method"],
  "/ð/": ["the", "that", "this"]
};

export function normalizeFocusSound(value: unknown): FocusSound {
  return focusSounds.includes(value as FocusSound)
    ? (value as FocusSound)
    : defaultFocusSound;
}

export function normalizeGroqSttModel(value: unknown) {
  return value === "whisper-large-v3" || value === "whisper-large-v3-turbo"
    ? value
    : audioConfig.speechToTextModel;
}

export function getBaseAudioMimeType(mimeType: string) {
  return mimeType.split(";")[0]?.trim().toLowerCase() ?? "";
}

export function inferGroqAudioExtension(mimeType: string, fileName?: string) {
  const extensionFromMimeType = groqAudioMimeExtensions[getBaseAudioMimeType(mimeType)];
  if (extensionFromMimeType) {
    return extensionFromMimeType;
  }

  const baseMimeFromName = fileName
    ? fileNameToAllowedMimeType(fileName)
    : null;
  return baseMimeFromName ? groqAudioMimeExtensions[baseMimeFromName] : null;
}

export function isSupportedGroqAudioType(mimeType: string, fileName?: string) {
  return Boolean(inferGroqAudioExtension(mimeType, fileName));
}

function fileNameToAllowedMimeType(fileName: string) {
  const extension = fileName.split(".").pop()?.trim().toLowerCase();
  if (!extension) {
    return null;
  }

  const matchingEntry = Object.entries(groqAudioMimeExtensions).find(
    ([, allowedExtension]) => allowedExtension === extension
  );
  return matchingEntry?.[0] ?? null;
}

export function buildPrivacyWarnings(workLog: string): string[] {
  const warnings: string[] = [];

  if (/\d/.test(workLog)) {
    warnings.push("Numbers are present. Mask sales, customer, or internal metrics before sharing.");
  }

  if (/[A-Z][A-Za-z0-9&., -]{2,}(Inc|Ltd|LLC|Corp|Company|Co\.|株式会社|有限会社)/.test(workLog)) {
    warnings.push("Company-like names may remain. Replace them with a generic label if needed.");
  }

  if (/(顧客|お客様|クライアント|案件名|社外秘|NDA|売上|粗利|利益|契約)/.test(workLog)) {
    warnings.push("Sensitive work terms are present. Abstract customer names, project names, and confidential numbers.");
  }

  return warnings;
}

export function buildLocalInterviewMaterials(input: {
  workLog: string;
  targetRole: string;
  focusSound: FocusSound;
}): InterviewMaterials {
  const topic = deriveTopic(input.workLog);
  const focusWord = focusWords[input.focusSound][0];
  const secondaryWord = focusWords[input.focusSound][1];
  const resultWord = focusWords[input.focusSound][2];
  const createdAt = new Date().toISOString();

  return {
    id: `interview-${Date.now()}`,
    createdAt,
    topic,
    focusSound: input.focusSound,
    summaryBullets: [
      "Turn the daily work note into one clear business improvement story.",
      `Lead with the result, then explain the action for a ${input.targetRole || "target role"} interview.`,
      "Keep names, customer details, and exact internal numbers abstract."
    ],
    answer30: `I noticed a workflow issue in my daily work. I ${focusWord} the team ${secondaryWord} the process and made the next step clearer. As a result, we could ${resultWord} the work and discuss the outcome with more confidence.`,
    answer30Ipa:
      "/aɪ ˈnoʊtɪst ə ˈwɝːkfloʊ ˈɪʃuː ɪn maɪ ˈdeɪli wɝːk. aɪ ... ðə tiːm ... ðə ˈprɑːses ænd meɪd ðə nekst step ˈklɪrər. æz ə rɪˈzʌlt, wi kʊd ... ðə wɝːk ænd dɪˈskʌs ði ˈaʊtkʌm wɪð mɔːr ˈkɑːnfədəns/",
    questions: [
      "What changed because of your action?",
      "How do you know the result was useful?",
      "Could anyone have done that with AI?"
    ],
    repairPhrases: [
      "Let me put it another way.",
      "Do you mean my role, or the result of the project?"
    ],
    pronunciationTip: focusSoundCues[input.focusSound],
    privacyWarnings: buildPrivacyWarnings(input.workLog)
  };
}

export function buildLocalInterviewReview(input: {
  focusSound: FocusSound;
  transcript?: string;
}): InterviewPracticeReview {
  const transcript = input.transcript?.trim();
  const hasTranscript = Boolean(transcript);

  return {
    positive: hasTranscript
      ? "You completed the answer and kept the core story moving."
      : "You completed the quiet review and kept the practice small enough to repeat.",
    fixPoints: [
      "Start with the result in the first sentence.",
      "Keep the middle sentence shorter so you can recover if you get interrupted."
    ],
    structureSuggestion:
      "Use this order next time: result first, one action, one business impact.",
    focusSoundNote: focusSoundCues[input.focusSound],
    nextFocus: input.focusSound
  };
}

export function buildTranscriptBasedInterviewReview(input: {
  focusSound: FocusSound;
  transcript: string;
  expectedAnswer?: string;
}): InterviewPracticeReview {
  const words = input.transcript.trim().split(/\s+/).filter(Boolean);
  const wordCount = words.length;
  const hasAction = /\b(tried|made|built|used|created|changed|improved|reviewed|helped|focused)\b/i.test(
    input.transcript
  );
  const hasResult = /\b(result|outcome|impact|clear|clearer|faster|improved|reduced|increased|confidence|useful)\b/i.test(
    input.transcript
  );
  const fixPoints: string[] = [];

  if (wordCount < 12) {
    fixPoints.push("Add one concrete action so the answer sounds complete.");
  } else if (wordCount > 95) {
    fixPoints.push("Shorten the middle of the answer so the main result lands sooner.");
  }

  if (!hasResult) {
    fixPoints.push("Name the result or business value in one short sentence.");
  }

  if (!hasAction) {
    fixPoints.push("Include one action verb so your contribution is easier to hear.");
  }

  if (fixPoints.length === 0) {
    fixPoints.push("Keep the result first, then add only one supporting detail.");
  }

  if (fixPoints.length === 1) {
    fixPoints.push("Use a repair phrase if the interviewer interrupts or asks for a shorter version.");
  }

  return {
    positive:
      "Whisper captured enough of your answer to review the interview message.",
    fixPoints: fixPoints.slice(0, 2),
    structureSuggestion:
      "For the next attempt, use this order: result, one action, one impact.",
    focusSoundNote: `${focusSoundCues[input.focusSound]} This is a lightweight focus-sound memo based on the transcript, not an acoustic measurement.`,
    nextFocus: input.focusSound
  };
}

function deriveTopic(workLog: string): string {
  const compact = workLog
    .replace(/\s+/g, " ")
    .replace(/[【】「」]/g, "")
    .trim();

  if (!compact) {
    return "Daily work improvement";
  }

  return compact.length > 42 ? `${compact.slice(0, 42)}...` : compact;
}
