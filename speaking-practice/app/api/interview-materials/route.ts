import { NextResponse } from "next/server";
import {
  buildLocalInterviewMaterials,
  buildPrivacyWarnings,
  focusSoundCues,
  normalizeFocusSound
} from "@/lib/interview";
import type { FocusSound, InterviewMaterials } from "@/types/speaking";

type InterviewMaterialsRequest = {
  workLog?: string;
  targetRole?: string;
  focusSound?: FocusSound;
};

export async function POST(request: Request) {
  const body = (await request.json()) as InterviewMaterialsRequest;
  const workLog = body.workLog?.trim() ?? "";
  const targetRole = body.targetRole?.trim() || "English interview";
  const focusSound = normalizeFocusSound(body.focusSound);

  if (!workLog) {
    return NextResponse.json(
      { error: "workLog is required" },
      { status: 400 }
    );
  }

  const localMaterials = buildLocalInterviewMaterials({
    workLog,
    targetRole,
    focusSound
  });

  if (!process.env.OPENAI_API_KEY) {
    return NextResponse.json(localMaterials);
  }

  try {
    const aiMaterials = await generateWithOpenAI({
      workLog,
      targetRole,
      focusSound
    });

    return NextResponse.json({
      ...aiMaterials,
      id: `interview-${Date.now()}`,
      createdAt: new Date().toISOString(),
      focusSound,
      pronunciationTip:
        aiMaterials.pronunciationTip || focusSoundCues[focusSound],
      privacyWarnings: buildPrivacyWarnings(workLog)
    });
  } catch {
    return NextResponse.json(localMaterials);
  }
}

async function generateWithOpenAI(input: {
  workLog: string;
  targetRole: string;
  focusSound: FocusSound;
}): Promise<Omit<InterviewMaterials, "id" | "createdAt" | "focusSound" | "privacyWarnings">> {
  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model: process.env.OPENAI_MODEL || "gpt-4.1-mini",
      input: buildPrompt(input)
    })
  });

  if (!response.ok) {
    throw new Error("OpenAI material generation failed");
  }

  const payload = (await response.json()) as unknown;
  const outputText = extractOutputText(payload);
  const materials = JSON.parse(outputText) as Omit<
    InterviewMaterials,
    "id" | "createdAt" | "focusSound" | "privacyWarnings"
  >;

  validateMaterials(materials);
  return materials;
}

function buildPrompt(input: {
  workLog: string;
  targetRole: string;
  focusSound: FocusSound;
}) {
  return `You convert Japanese work logs into English interview practice material.

Rules:
- Do not translate literally.
- Rebuild the story for a ${input.targetRole} interview.
- Keep the answer around 30 seconds.
- Lead with conclusion/result.
- Include action, result, and learning or business value.
- Avoid customer names, company names, project names, and exact confidential numbers.
- Include the focus sound ${input.focusSound} naturally.
- Return only valid JSON. Do not wrap it in Markdown.

JSON shape:
{
  "topic": "short topic",
  "summaryBullets": ["3 short bullets"],
  "answer30": "natural English answer",
  "answer30Ipa": "IPA for the answer",
  "questions": ["3 interview questions"],
  "repairPhrases": ["2 repair phrases"],
  "pronunciationTip": "one short tip for ${input.focusSound}"
}

Japanese work log:
${input.workLog}`;
}

function extractOutputText(payload: unknown): string {
  if (
    payload &&
    typeof payload === "object" &&
    "output_text" in payload &&
    typeof payload.output_text === "string"
  ) {
    return payload.output_text;
  }

  if (!payload || typeof payload !== "object" || !("output" in payload)) {
    throw new Error("Missing output text");
  }

  const output = (payload as { output?: unknown }).output;
  if (!Array.isArray(output)) {
    throw new Error("Missing output array");
  }

  for (const item of output) {
    if (!item || typeof item !== "object" || !("content" in item)) {
      continue;
    }

    const content = (item as { content?: unknown }).content;
    if (!Array.isArray(content)) {
      continue;
    }

    for (const contentItem of content) {
      if (
        contentItem &&
        typeof contentItem === "object" &&
        "text" in contentItem &&
        typeof contentItem.text === "string"
      ) {
        return contentItem.text;
      }
    }
  }

  throw new Error("No text content found");
}

function validateMaterials(
  materials: Omit<
    InterviewMaterials,
    "id" | "createdAt" | "focusSound" | "privacyWarnings"
  >
) {
  const requiredText = [
    materials.topic,
    materials.answer30,
    materials.answer30Ipa,
    materials.pronunciationTip
  ];

  if (requiredText.some((value) => typeof value !== "string" || !value.trim())) {
    throw new Error("Generated materials include blank required text");
  }

  if (materials.answer30.length > 900) {
    throw new Error("Generated answer is too long for the MVP");
  }

  if (
    !Array.isArray(materials.summaryBullets) ||
    materials.summaryBullets.length < 1 ||
    !Array.isArray(materials.questions) ||
    materials.questions.length !== 3 ||
    !Array.isArray(materials.repairPhrases) ||
    materials.repairPhrases.length !== 2
  ) {
    throw new Error("Generated materials do not match the required schema");
  }
}
