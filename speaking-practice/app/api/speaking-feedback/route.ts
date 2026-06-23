import { NextResponse } from "next/server";
import {
  audioConfig,
  buildTranscriptBasedInterviewReview,
  inferGroqAudioExtension,
  isSupportedGroqAudioType,
  maxInterviewAudioBytes,
  minimumInterviewRecordingMs,
  normalizeFocusSound,
  normalizeGroqSttModel
} from "@/lib/interview";
import type { FeedbackResult, SttErrorCode } from "@/types/speaking";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const formData = await request.formData();
  const focusSound = normalizeFocusSound(formData.get("focusSound"));
  const isInterviewReview = formData.get("mode") === "interview";

  if (!isInterviewReview) {
    const feedback: FeedbackResult = {
      transcript: "I like chicken rice please",
      correction: "I would like chicken rice, please.",
      positive: "Nice speaking!",
      nextAction: "Say it once more",
      clarity: "clear",
      transcriptSource: "mock",
      reviewMode: "sentence_mock",
      sttStatus: "success"
    };

    return NextResponse.json(feedback);
  }

  const audio = formData.get("audio");
  if (!(audio instanceof Blob)) {
    return sttError("missing_audio", "No recording was received.", 400);
  }

  const durationMs = Number(formData.get("durationMs") ?? 0);
  if (!Number.isFinite(durationMs) || durationMs < minimumInterviewRecordingMs) {
    return sttError(
      "too_short",
      "録音が短すぎました。もう一度録音するか、今日はquiet modeで完了してください。",
      400
    );
  }

  if (audio.size === 0) {
    return sttError(
      "empty_audio",
      "録音が空でした。もう一度録音するか、今日はquiet modeで完了してください。",
      400
    );
  }

  if (audio.size > maxInterviewAudioBytes) {
    return sttError(
      "too_large",
      "録音が25MBを超えています。短く録音し直すか、今日はquiet modeで完了してください。",
      413
    );
  }

  const providedAudioType = getString(formData.get("audioType"));
  const audioType = audio.type || providedAudioType;
  if (!isSupportedGroqAudioType(audioType)) {
    return sttError(
      "unsupported_format",
      "このブラウザの録音形式はMVP対象外です。Chrome/Edgeで録音するか、今日はquiet modeで完了してください。",
      400
    );
  }

  if (!process.env.GROQ_API_KEY) {
    return sttError(
      "not_configured",
      "録音レビューはまだ設定されていません。GROQ_API_KEYを設定するか、quiet modeを使ってください。",
      503
    );
  }

  try {
    const audioName = getAudioFileName(audio, audioType);
    const transcript = await transcribeWithGroq({
      audio,
      audioName,
      answer30: getString(formData.get("answer30"))
    });
    const review = buildTranscriptBasedInterviewReview({
      focusSound,
      transcript,
      expectedAnswer: getString(formData.get("answer30"))
    });

    const feedback: FeedbackResult = {
      transcript,
      correction: "Use the transcript to tighten the result, action, and impact.",
      positive: review.positive,
      nextAction: "Review one point, then save the session.",
      clarity: "clear",
      transcriptSource: "groq_whisper",
      reviewMode: audioConfig.reviewMode,
      sttStatus: "success",
      review
    };

    return NextResponse.json(feedback);
  } catch {
    return sttError(
      "failed",
      "Whisper文字起こしに失敗しました。音声は保存していません。もう一度録音してください。",
      502
    );
  }
}

async function transcribeWithGroq(input: {
  audio: Blob;
  audioName: string;
  answer30: string;
}) {
  const groqFormData = new FormData();
  groqFormData.append("file", input.audio, input.audioName);
  groqFormData.append(
    "model",
    normalizeGroqSttModel(process.env.GROQ_STT_MODEL)
  );
  groqFormData.append("language", "en");
  groqFormData.append("response_format", "json");
  groqFormData.append("temperature", "0");

  const prompt = buildGroqPrompt(input.answer30);
  if (prompt) {
    groqFormData.append("prompt", prompt);
  }

  const response = await fetch(
    "https://api.groq.com/openai/v1/audio/transcriptions",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.GROQ_API_KEY}`
      },
      body: groqFormData
    }
  );

  if (!response.ok) {
    throw new Error("Groq transcription failed");
  }

  const payload = (await response.json()) as { text?: unknown };
  const transcript = typeof payload.text === "string" ? payload.text.trim() : "";
  if (!transcript) {
    throw new Error("Groq transcription was empty");
  }

  return transcript;
}

function buildGroqPrompt(answer30: string) {
  const compactAnswer = answer30.replace(/\s+/g, " ").trim();
  if (!compactAnswer) {
    return "English interview answer about work improvement.";
  }

  return `English interview answer. Expected topic: ${compactAnswer.slice(0, 180)}`;
}

function getAudioFileName(audio: Blob, audioType: string) {
  const extensionFromType = inferGroqAudioExtension(audioType);
  if (extensionFromType) {
    return `interview-practice.${extensionFromType}`;
  }

  const namedAudio = audio as Blob & { name?: string };
  if (namedAudio.name) {
    return namedAudio.name;
  }

  return "interview-practice.webm";
}

function getString(value: FormDataEntryValue | null) {
  return typeof value === "string" ? value : "";
}

function sttError(code: SttErrorCode, nextAction: string, status: number) {
  const feedback: FeedbackResult = {
    transcript: "",
    correction: "",
    positive: "",
    nextAction,
    clarity: "unclear",
    transcriptSource: "none",
    reviewMode: audioConfig.reviewMode,
    sttStatus: code,
    sttErrorCode: code
  };

  return NextResponse.json(feedback, { status });
}
