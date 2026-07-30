import type { VoicePracticeContext } from "@/types/voice-ledger";

export type ManualEntryForm = {
  practicedAt: string;
  title: string;
  context: VoicePracticeContext;
  sessionMinutes: string;
  summary: string;
  usefulExpressions: string[];
  stickingPoints: string[];
  corrections: string[];
  nextMission: string;
  selfNote: string;
};

export type VoiceSessionLogParseResult = {
  status: "ready" | "incomplete";
  draft: ManualEntryForm;
  missingFields: string[];
  warnings: string[];
};

type SessionLogLabel =
  | "テーマ"
  | "練習時間"
  | "今日の重点音"
  | "良かった点"
  | "最優先で直す点"
  | "聞き取りにくかった単語・表現"
  | "練習した自然な文"
  | "前回からの変化"
  | "次回の課題"
  | "5分宿題";

const labels: SessionLogLabel[] = [
  "テーマ",
  "練習時間",
  "今日の重点音",
  "良かった点",
  "最優先で直す点",
  "聞き取りにくかった単語・表現",
  "練習した自然な文",
  "前回からの変化",
  "次回の課題",
  "5分宿題"
];

const requiredLabels: SessionLogLabel[] = [
  "テーマ",
  "良かった点",
  "最優先で直す点",
  "次回の課題"
];

const optionalLabels: SessionLogLabel[] = labels.filter(
  (label) => !requiredLabels.includes(label) && label !== "練習時間"
);

const maxListItems = 5;

export const VOICE_SESSION_LOG_PROMPT = `今日のセッションを、会話の全文ではなく次の10項目だけで短くまとめてください。個人名、会社名、案件名、正確な業務数値は書かないでください。\n\n# YYYY-MM-DD\nテーマ:\n練習時間: 15\n今日の重点音:\n良かった点:\n最優先で直す点:\n聞き取りにくかった単語・表現:\n練習した自然な文:\n前回からの変化:\n次回の課題:\n5分宿題:`;

export function parseVoiceSessionLog(
  rawText: string,
  defaults: {
    practicedAt: string;
    context: VoicePracticeContext;
  }
): VoiceSessionLogParseResult {
  const values = collectLabelValues(rawText);
  const warnings: string[] = [];
  const missingFields = requiredLabels.filter(
    (label) => !hasValue(values[label])
  );
  const optionalMissing = optionalLabels.filter(
    (label) => values[label].length === 0
  );

  const parsedDate = findPracticeDate(rawText);
  let practicedAt = defaults.practicedAt;
  if (parsedDate.status === "valid") {
    practicedAt = parsedDate.value;
  } else if (parsedDate.status === "missing") {
    warnings.push("日付がないため、端末のローカル日付を使いました。");
  } else {
    warnings.push("日付が不正なため、端末のローカル日付を使いました。");
  }

  const sessionMinutes = parseSessionMinutes(values["練習時間"]);
  if (sessionMinutes.status === "invalid") {
    warnings.push("練習時間は正の整数ではないため、空欄にしました。");
  } else if (sessionMinutes.status === "missing") {
    warnings.push("練習時間が見つからないため、空欄にしました。");
  }

  if (optionalMissing.length > 0) {
    warnings.push(
      `任意項目が見つかりません: ${optionalMissing.join("、")}`
    );
  }

  const usefulExpressions = toList(values["練習した自然な文"]);
  const stickingPoints = toPrefixedList([
    ["重点音", values["今日の重点音"]],
    ["聞き取りにくかった表現", values["聞き取りにくかった単語・表現"]]
  ]);
  const corrections = toList(values["最優先で直す点"]);

  if (usefulExpressions.wasTruncated || stickingPoints.wasTruncated || corrections.wasTruncated) {
    warnings.push("詳細リストは最大5件まで保存します。");
  }

  return {
    status: missingFields.length === 0 ? "ready" : "incomplete",
    draft: {
      practicedAt,
      context: defaults.context,
      title: valueText(values["テーマ"]),
      sessionMinutes:
        sessionMinutes.status === "valid"
          ? String(sessionMinutes.value)
          : "",
      summary: joinNamedValues([
        ["良かった点", values["良かった点"]],
        ["最優先で直す点", values["最優先で直す点"]]
      ]),
      usefulExpressions: usefulExpressions.items,
      stickingPoints: stickingPoints.items,
      corrections: corrections.items,
      nextMission: joinNamedValues([
        ["次回の課題", values["次回の課題"]],
        ["5分宿題", values["5分宿題"]]
      ]),
      selfNote: valueText(values["前回からの変化"])
    },
    missingFields,
    warnings
  };
}

function collectLabelValues(rawText: string): Record<SessionLogLabel, string[]> {
  const values = createEmptyValues();
  let activeLabel: SessionLogLabel | null = null;

  for (const rawLine of rawText.replaceAll("\r\n", "\n").split("\n")) {
    const line = rawLine.trim();
    if (line.startsWith("```")) {
      continue;
    }
    if (!line) {
      activeLabel = null;
      continue;
    }

    const parsedLabel = parseLabelLine(line);
    if (parsedLabel) {
      activeLabel = parsedLabel.label;
      values[activeLabel].push(parsedLabel.value);
      continue;
    }

    if (isUnknownLabelLine(line)) {
      activeLabel = null;
      continue;
    }

    if (activeLabel) {
      values[activeLabel].push(line);
    }
  }

  return values;
}

function createEmptyValues(): Record<SessionLogLabel, string[]> {
  return labels.reduce<Record<SessionLogLabel, string[]>>(
    (values, label) => {
      values[label] = [];
      return values;
    },
    {} as Record<SessionLogLabel, string[]>
  );
}

function parseLabelLine(
  line: string
): { label: SessionLogLabel; value: string } | null {
  const content = stripMarkdownPrefix(line);
  const separatorIndex = findLabelSeparator(content);
  const rawLabel =
    separatorIndex === -1 ? content : content.slice(0, separatorIndex);
  const label = normalizeLabel(rawLabel);
  if (!label) {
    return null;
  }

  return {
    label,
    value:
      separatorIndex === -1
        ? ""
        : normalizeValue(content.slice(separatorIndex + 1))
  };
}

function stripMarkdownPrefix(value: string) {
  let normalized = value.trim();
  while (normalized.startsWith("#")) {
    normalized = normalized.slice(1).trimStart();
  }
  if (
    normalized.startsWith("- ") ||
    normalized.startsWith("* ") ||
    normalized.startsWith("+ ")
  ) {
    normalized = normalized.slice(2).trimStart();
  }
  return normalized;
}

function findLabelSeparator(value: string) {
  const ascii = value.indexOf(":");
  const fullWidth = value.indexOf("：");
  if (ascii === -1) {
    return fullWidth;
  }
  if (fullWidth === -1) {
    return ascii;
  }
  return Math.min(ascii, fullWidth);
}

function normalizeLabel(value: string): SessionLogLabel | null {
  let normalized = value.trim();
  if (normalized.startsWith("**") && normalized.endsWith("**")) {
    normalized = normalized.slice(2, -2).trim();
  }
  return labels.includes(normalized as SessionLogLabel)
    ? (normalized as SessionLogLabel)
    : null;
}

function isUnknownLabelLine(line: string) {
  const content = stripMarkdownPrefix(line);
  const separatorIndex = findLabelSeparator(content);
  if (separatorIndex === -1) {
    return false;
  }

  const candidate = content.slice(0, separatorIndex).trim();
  return (
    candidate.length > 0 &&
    candidate.length <= 40 &&
    ![...candidate].some((character) => character === " " || character === "\t")
  );
}

function normalizeValue(value: string) {
  const normalized = value.trim();
  if (!normalized || isEmptyMarker(normalized)) {
    return "";
  }
  return normalized;
}

function isEmptyMarker(value: string) {
  const normalized = value.toLocaleLowerCase();
  return normalized === "なし" || normalized === "特になし" || normalized === "n/a";
}

function findPracticeDate(rawText: string):
  | { status: "valid"; value: string }
  | { status: "missing" | "invalid" } {
  let foundHeading = false;
  for (const rawLine of rawText.replaceAll("\r\n", "\n").split("\n")) {
    const line = rawLine.trim();
    if (!line.startsWith("#")) {
      continue;
    }
    const value = stripMarkdownPrefix(line);
    if (isValidDate(value)) {
      return { status: "valid", value };
    }
    if (looksLikeDate(value)) {
      foundHeading = true;
    }
  }
  return { status: foundHeading ? "invalid" : "missing" };
}

function isValidDate(value: string) {
  const [year, month, day] = value.split("-");
  if (
    !year ||
    !month ||
    !day ||
    year.length !== 4 ||
    month.length !== 2 ||
    day.length !== 2 ||
    !isDigits(year) ||
    !isDigits(month) ||
    !isDigits(day)
  ) {
    return false;
  }

  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return (
    date.getFullYear() === Number(year) &&
    date.getMonth() === Number(month) - 1 &&
    date.getDate() === Number(day)
  );
}

function looksLikeDate(value: string) {
  const firstCharacter = value.trim()[0];
  return Boolean(firstCharacter && firstCharacter >= "0" && firstCharacter <= "9");
}

function isDigits(value: string) {
  return [...value].every((character) => character >= "0" && character <= "9");
}

function parseSessionMinutes(values: string[]):
  | { status: "valid"; value: number }
  | { status: "missing" | "invalid" } {
  const value = valueText(values);
  if (!value) {
    return { status: "missing" };
  }
  const minutes = Number(value);
  return Number.isInteger(minutes) && minutes > 0
    ? { status: "valid", value: minutes }
    : { status: "invalid" };
}

function hasValue(values: string[]) {
  return Boolean(valueText(values));
}

function valueText(values: string[]) {
  return values
    .map(normalizeValue)
    .filter(Boolean)
    .map(stripListMarker)
    .join("\n");
}

function joinNamedValues(values: Array<[string, string[]]>) {
  return values
    .map(([label, content]) => {
      const value = valueText(content);
      return value ? `${label}: ${value}` : "";
    })
    .filter(Boolean)
    .join("\n");
}

function toList(values: string[]) {
  const items = values
    .map(normalizeValue)
    .filter(Boolean)
    .map(stripListMarker);
  return {
    items: items.slice(0, maxListItems),
    wasTruncated: items.length > maxListItems
  };
}

function toPrefixedList(values: Array<[string, string[]]>) {
  const normalizedLists = values.map(([label, content]) => {
    const list = toList(content);
    return {
      items: list.items.map((value) => `${label}: ${value}`),
      wasTruncated: list.wasTruncated
    };
  });
  const items = normalizedLists.flatMap((list) => list.items);
  return {
    items: items.slice(0, maxListItems),
    wasTruncated:
      items.length > maxListItems ||
      normalizedLists.some((list) => list.wasTruncated)
  };
}

function stripListMarker(value: string) {
  return value.startsWith("- ") || value.startsWith("* ")
    ? value.slice(2).trim()
    : value;
}
