(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.PronunciationLab = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const FOCUS_POSITIONS = new Set(["initial", "vowel", "final", "whole"]);
  const HARD_UNABLE_REASONS = new Set([
    "empty_transcript",
    "non_english_transcript",
    "too_short",
    "transcript_too_different"
  ]);

  const LESSONS = [
    {
      id: "h-he-fee-001",
      category: "H/F/V",
      focusSound: "/h/",
      contrastSound: "/f/",
      focusSoundPosition: "initial",
      targetWord: "he",
      targetWordIPA: "/hiː/",
      contrastWord: "fee",
      contrastWordIPA: "/fiː/",
      targetSentence: "He is here.",
      targetSentenceIPA: "/hiː ɪz hɪr/",
      focusToken: "he",
      focusTokenIPA: "/hiː/",
      focusTokenIndex: 0,
      chunkedSentence: [
        { text: "He is", ipa: "/hiː ɪz/" },
        { text: "here", ipa: "/hɪr/" }
      ],
      commonMishearings: [
        {
          heard: "fee",
          heardIPA: "/fiː/",
          feedback: "唇や歯でこすらず、母音の前に軽く息を出しましょう。"
        }
      ],
      airCue: "喉を強くこすらず、母音の前に軽く息を出す",
      mouthCue: "唇や歯で音を作らない",
      nextDrill: "he /hiː/ を3回、その後に文全体を1回読む"
    },
    {
      id: "f-fee-he-002",
      category: "H/F/V",
      focusSound: "/f/",
      contrastSound: "/h/",
      focusSoundPosition: "initial",
      targetWord: "fee",
      targetWordIPA: "/fiː/",
      contrastWord: "he",
      contrastWordIPA: "/hiː/",
      targetSentence: "The fee is five dollars.",
      targetSentenceIPA: "/ðə fiː ɪz faɪv ˈdɑːlərz/",
      focusToken: "fee",
      focusTokenIPA: "/fiː/",
      focusTokenIndex: 1,
      chunkedSentence: [
        { text: "The fee is", ipa: "/ðə fiː ɪz/" },
        { text: "five dollars", ipa: "/faɪv ˈdɑːlərz/" }
      ],
      commonMishearings: [
        {
          heard: "he",
          heardIPA: "/hiː/",
          feedback: "上の歯を下唇に軽く当て、声を出さずに息を通しましょう。"
        }
      ],
      mouthCue: "上の歯を下唇に軽く当てる",
      airCue: "/f/ は声なし",
      nextDrill: "fee /fiː/ を3回、その後に文全体を1回読む"
    },
    {
      id: "v-very-berry-003",
      category: "H/F/V",
      focusSound: "/v/",
      contrastSound: "/b/",
      focusSoundPosition: "initial",
      targetWord: "very",
      targetWordIPA: "/ˈveri/",
      contrastWord: "berry",
      contrastWordIPA: "/ˈberi/",
      targetSentence: "It is very good.",
      targetSentenceIPA: "/ɪt ɪz ˈveri ɡʊd/",
      focusToken: "very",
      focusTokenIPA: "/ˈveri/",
      focusTokenIndex: 2,
      chunkedSentence: [
        { text: "It is very", ipa: "/ɪt ɪz ˈveri/" },
        { text: "good", ipa: "/ɡʊd/" }
      ],
      commonMishearings: [
        {
          heard: "berry",
          heardIPA: "/ˈberi/",
          feedback: "上の歯を下唇に軽く当て、声を出しながら息を通しましょう。"
        }
      ],
      mouthCue: "上の歯を下唇に軽く当てる",
      airCue: "/v/ は声あり",
      nextDrill: "very /ˈveri/ を3回、その後に文全体を1回読む"
    },
    {
      id: "uw-luke-look-004",
      category: "U/OO",
      focusSound: "/uː/",
      contrastSound: "/ʊ/",
      focusSoundPosition: "vowel",
      targetWord: "Luke",
      targetWordIPA: "/luːk/",
      contrastWord: "look",
      contrastWordIPA: "/lʊk/",
      targetSentence: "Luke is in the pool.",
      targetSentenceIPA: "/luːk ɪz ɪn ðə puːl/",
      focusToken: "luke",
      focusTokenIPA: "/luːk/",
      focusTokenIndex: 0,
      commonMishearings: [
        {
          heard: "look",
          heardIPA: "/lʊk/",
          feedback: "短く切らず、/uː/ を長めに保ちましょう。"
        }
      ],
      mouthCue: "唇を丸める",
      durationCue: "短く切らず、長めに保つ",
      nextDrill: "Luke /luːk/ を3回、その後に文全体を1回読む"
    },
    {
      id: "uh-look-luke-005",
      category: "U/OO",
      focusSound: "/ʊ/",
      contrastSound: "/uː/",
      focusSoundPosition: "vowel",
      targetWord: "look",
      targetWordIPA: "/lʊk/",
      contrastWord: "Luke",
      contrastWordIPA: "/luːk/",
      targetSentence: "Look at the book.",
      targetSentenceIPA: "/lʊk ət ðə bʊk/",
      focusToken: "look",
      focusTokenIPA: "/lʊk/",
      focusTokenIndex: 0,
      commonMishearings: [
        {
          heard: "luke",
          heardIPA: "/luːk/",
          feedback: "伸ばさず短く、力を入れすぎない音にしましょう。"
        }
      ],
      mouthCue: "力を入れすぎず、唇を丸めすぎない",
      durationCue: "伸ばさず短く出す",
      nextDrill: "look /lʊk/ を3回、その後に文全体を1回読む"
    },
    {
      id: "uw-pool-pull-006",
      category: "U/OO",
      focusSound: "/uː/",
      contrastSound: "/ʊ/",
      focusSoundPosition: "vowel",
      targetWord: "pool",
      targetWordIPA: "/puːl/",
      contrastWord: "pull",
      contrastWordIPA: "/pʊl/",
      targetSentence: "The pool is clean.",
      targetSentenceIPA: "/ðə puːl ɪz kliːn/",
      focusToken: "pool",
      focusTokenIPA: "/puːl/",
      focusTokenIndex: 1,
      commonMishearings: [
        {
          heard: "pull",
          heardIPA: "/pʊl/",
          feedback: "/uː/ を短く切らず、長めに保ちましょう。"
        }
      ],
      mouthCue: "唇を丸める",
      durationCue: "短く切らず、長めに保つ",
      nextDrill: "pool /puːl/ を3回、その後に文全体を1回読む"
    },
    {
      id: "uh-pull-pool-007",
      category: "U/OO",
      focusSound: "/ʊ/",
      contrastSound: "/uː/",
      focusSoundPosition: "vowel",
      targetWord: "pull",
      targetWordIPA: "/pʊl/",
      contrastWord: "pool",
      contrastWordIPA: "/puːl/",
      targetSentence: "Pull the door.",
      targetSentenceIPA: "/pʊl ðə dɔːr/",
      focusToken: "pull",
      focusTokenIPA: "/pʊl/",
      focusTokenIndex: 0,
      commonMishearings: [
        {
          heard: "pool",
          heardIPA: "/puːl/",
          feedback: "長く伸ばさず、短く止める意識で読みましょう。"
        }
      ],
      mouthCue: "力を入れすぎず、唇を丸めすぎない",
      durationCue: "伸ばさず短く出す",
      nextDrill: "pull /pʊl/ を3回、その後に文全体を1回読む"
    },
    {
      id: "diphthong-ai-right-008",
      category: "二重母音",
      focusSound: "/aɪ/",
      focusSoundPosition: "vowel",
      targetWord: "right",
      targetWordIPA: "/raɪt/",
      targetSentence: "I turned right.",
      targetSentenceIPA: "/aɪ tɝːnd raɪt/",
      focusToken: "right",
      focusTokenIPA: "/raɪt/",
      focusTokenIndex: 2,
      movementCue: "最初の母音から最後の母音へ一息で動かす",
      nextDrill: "right /raɪt/ を3回、その後に文全体を1回読む"
    },
    {
      id: "diphthong-ei-day-009",
      category: "二重母音",
      focusSound: "/eɪ/",
      focusSoundPosition: "vowel",
      targetWord: "day",
      targetWordIPA: "/deɪ/",
      targetSentence: "Have a nice day.",
      targetSentenceIPA: "/hæv ə naɪs deɪ/",
      focusToken: "day",
      focusTokenIPA: "/deɪ/",
      focusTokenIndex: 3,
      movementCue: "最初の母音から最後の母音へ一息で動かす",
      nextDrill: "day /deɪ/ を3回、その後に文全体を1回読む"
    },
    {
      id: "diphthong-ou-go-010",
      category: "二重母音",
      focusSound: "/oʊ/",
      focusSoundPosition: "vowel",
      targetWord: "go",
      targetWordIPA: "/ɡoʊ/",
      targetSentence: "Go home.",
      targetSentenceIPA: "/ɡoʊ hoʊm/",
      focusToken: "go",
      focusTokenIPA: "/ɡoʊ/",
      focusTokenIndex: 0,
      movementCue: "最初の母音から最後の母音へ一息で動かす",
      nextDrill: "go /ɡoʊ/ を3回、その後に文全体を1回読む"
    },
    {
      id: "diphthong-au-now-011",
      category: "二重母音",
      focusSound: "/aʊ/",
      focusSoundPosition: "vowel",
      targetWord: "now",
      targetWordIPA: "/naʊ/",
      targetSentence: "Do it now.",
      targetSentenceIPA: "/duː ɪt naʊ/",
      focusToken: "now",
      focusTokenIPA: "/naʊ/",
      focusTokenIndex: 2,
      movementCue: "最初の母音から最後の母音へ一息で動かす",
      nextDrill: "now /naʊ/ を3回、その後に文全体を1回読む"
    },
    {
      id: "diphthong-oi-boy-012",
      category: "二重母音",
      focusSound: "/ɔɪ/",
      focusSoundPosition: "vowel",
      targetWord: "boy",
      targetWordIPA: "/bɔɪ/",
      targetSentence: "The boy is here.",
      targetSentenceIPA: "/ðə bɔɪ ɪz hɪr/",
      focusToken: "boy",
      focusTokenIPA: "/bɔɪ/",
      focusTokenIndex: 1,
      movementCue: "最初の母音から最後の母音へ一息で動かす",
      nextDrill: "boy /bɔɪ/ を3回、その後に文全体を1回読む"
    },
    {
      id: "r-l-right-light-013",
      category: "R/L",
      focusSound: "/r/",
      contrastSound: "/l/",
      focusSoundPosition: "initial",
      targetWord: "right",
      targetWordIPA: "/raɪt/",
      contrastWord: "light",
      contrastWordIPA: "/laɪt/",
      targetSentence: "I turned right at the light.",
      targetSentenceIPA: "/aɪ tɝːnd raɪt ət ðə laɪt/",
      focusToken: "right",
      focusTokenIPA: "/raɪt/",
      focusTokenIndex: 2,
      chunkedSentence: [
        { text: "I turned right", ipa: "/aɪ tɝːnd raɪt/" },
        { text: "at the light", ipa: "/ət ðə laɪt/" }
      ],
      commonMishearings: [
        {
          heard: "light",
          heardIPA: "/laɪt/",
          feedback: "舌先を上あごにつけず、舌を少し後ろへ引きましょう。"
        }
      ],
      tongueCue: "舌先を上あごにつけない",
      mouthCue: "唇を少し丸めてもよいが、日本語の「う」を足さない",
      airCue: "息を止めずに軽く流す",
      nextDrill: "right /raɪt/ を3回、その後に文全体を1回読む"
    },
    {
      id: "l-r-light-right-014",
      category: "R/L",
      focusSound: "/l/",
      contrastSound: "/r/",
      focusSoundPosition: "initial",
      targetWord: "light",
      targetWordIPA: "/laɪt/",
      contrastWord: "right",
      contrastWordIPA: "/raɪt/",
      targetSentence: "The light is on.",
      targetSentenceIPA: "/ðə laɪt ɪz ɑːn/",
      focusToken: "light",
      focusTokenIPA: "/laɪt/",
      focusTokenIndex: 1,
      commonMishearings: [
        {
          heard: "right",
          heardIPA: "/raɪt/",
          feedback: "舌先を上の歯ぐきに軽く当ててから離しましょう。"
        }
      ],
      tongueCue: "舌先を上の歯ぐきに軽く当てる",
      nextDrill: "light /laɪt/ を3回、その後に文全体を1回読む"
    },
    {
      id: "theta-think-sink-015",
      category: "TH",
      focusSound: "/θ/",
      contrastSound: "/s/",
      focusSoundPosition: "initial",
      targetWord: "think",
      targetWordIPA: "/θɪŋk/",
      contrastWord: "sink",
      contrastWordIPA: "/sɪŋk/",
      targetSentence: "I think so.",
      targetSentenceIPA: "/aɪ θɪŋk soʊ/",
      focusToken: "think",
      focusTokenIPA: "/θɪŋk/",
      focusTokenIndex: 1,
      commonMishearings: [
        {
          heard: "sink",
          heardIPA: "/sɪŋk/",
          feedback: "舌先を前歯の近くに軽く出し、強く噛まずに息を通しましょう。"
        }
      ],
      tongueCue: "舌先を前歯の近くに軽く出し、強く噛まない",
      airCue: "声を出さずに息だけを通す",
      nextDrill: "think /θɪŋk/ を3回、その後に文全体を1回読む"
    },
    {
      id: "eth-this-dis-016",
      category: "TH",
      focusSound: "/ð/",
      contrastSound: "/d/",
      focusSoundPosition: "initial",
      targetWord: "this",
      targetWordIPA: "/ðɪs/",
      contrastWord: "dis",
      contrastWordIPA: "/dɪs/",
      targetSentence: "This is mine.",
      targetSentenceIPA: "/ðɪs ɪz maɪn/",
      focusToken: "this",
      focusTokenIPA: "/ðɪs/",
      focusTokenIndex: 0,
      commonMishearings: [
        {
          heard: "dis",
          heardIPA: "/dɪs/",
          feedback: "舌先を前歯の近くに軽く出し、強く噛まずに声を出しましょう。"
        }
      ],
      tongueCue: "舌先を前歯の近くに軽く出し、強く噛まない",
      airCue: "声を出しながら息を通す",
      nextDrill: "this /ðɪs/ を3回、その後に文全体を1回読む"
    }
  ];

  function normalizeText(text) {
    return String(text || "")
      .toLowerCase()
      .replace(/[.?!,]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function normalizeToTokens(text) {
    const normalized = normalizeText(text);
    return normalized ? normalized.split(" ") : [];
  }

  function normalizeToken(text) {
    return normalizeText(text);
  }

  function hasEnglishLetters(text) {
    return /[a-z]/i.test(String(text || ""));
  }

  function getTargetTokens(lesson) {
    return normalizeToTokens(lesson.targetSentence);
  }

  function validateLesson(lesson) {
    const requiredFields = [
      "id",
      "category",
      "focusSound",
      "targetWord",
      "targetWordIPA",
      "targetSentence",
      "targetSentenceIPA",
      "focusToken",
      "focusTokenIPA",
      "focusTokenIndex"
    ];
    const missingFields = requiredFields.filter((field) => lesson[field] === undefined || lesson[field] === "");
    if (missingFields.length) {
      return { ok: false, reason: "missing_fields", detail: missingFields.join(", ") };
    }
    if (lesson.focusSoundPosition && !FOCUS_POSITIONS.has(lesson.focusSoundPosition)) {
      return { ok: false, reason: "invalid_focus_sound_position", detail: lesson.focusSoundPosition };
    }
    const targetTokens = getTargetTokens(lesson);
    const expectedFocusToken = normalizeToken(lesson.focusToken);
    if (targetTokens[lesson.focusTokenIndex] !== expectedFocusToken) {
      return {
        ok: false,
        reason: "focus_token_index_mismatch",
        detail: `expected ${expectedFocusToken} at ${lesson.focusTokenIndex}`
      };
    }
    if (lesson.commonMishearings) {
      const invalid = lesson.commonMishearings.find((item) => !item.heard || !item.heardIPA || !item.feedback);
      if (invalid) {
        return { ok: false, reason: "invalid_common_mishearings", detail: lesson.id };
      }
    }
    return { ok: true };
  }

  function getCuePriorityField(focusSound) {
    if (focusSound === "/h/") return "airCue";
    if (focusSound === "/f/" || focusSound === "/v/") return "mouthCue";
    if (focusSound === "/uː/" || focusSound === "/ʊ/") return "durationCue";
    if (["/aɪ/", "/eɪ/", "/oʊ/", "/aʊ/", "/ɔɪ/"].includes(focusSound)) return "movementCue";
    if (["/r/", "/l/", "/θ/", "/ð/"].includes(focusSound)) return "tongueCue";
    return "mouthCue";
  }

  function getPrimaryCue(lesson) {
    const priorityField = getCuePriorityField(lesson.focusSound);
    return (
      lesson[priorityField] ||
      lesson.mouthCue ||
      lesson.tongueCue ||
      lesson.airCue ||
      lesson.durationCue ||
      lesson.movementCue ||
      "重点語をゆっくり1回だけ読み直しましょう。"
    );
  }

  function isTranscriptTooDifferent(lesson, userTokens, focusTokenAtIndex) {
    const targetTokens = getTargetTokens(lesson);
    const focusToken = normalizeToken(lesson.focusToken);
    const heardTokens = (lesson.commonMishearings || []).map((item) => normalizeToken(item.heard));
    if (focusTokenAtIndex === focusToken || heardTokens.includes(focusTokenAtIndex)) {
      return false;
    }
    const targetSet = new Set(targetTokens);
    const overlap = userTokens.filter((token) => targetSet.has(token)).length;
    const overlapRatio = overlap / Math.max(targetTokens.length, 1);
    return userTokens.length > 2 && overlapRatio < 0.35;
  }

  function getUnableReason(lesson, userTranscript, userTokens) {
    if (!String(userTranscript || "").trim()) return "empty_transcript";
    if (!hasEnglishLetters(userTranscript)) return "non_english_transcript";
    if (userTokens.length <= lesson.focusTokenIndex) return "too_short";
    if (isTranscriptTooDifferent(lesson, userTokens, userTokens[lesson.focusTokenIndex])) {
      return "transcript_too_different";
    }
    return null;
  }

  function getUnableReasonLabel(reason) {
    const labels = {
      empty_transcript: "文字起こしが空です",
      non_english_transcript: "英語として判定しにくい文字起こしです",
      too_short: "文字起こしが重点語の位置まで届いていません",
      transcript_too_different: "文全体が目標文と大きく異なります",
      focus_token_missing: "重点語が文字起こしに含まれていません"
    };
    return labels[reason] || "判定に必要な情報が足りません";
  }

  function judgeTranscript(lesson, userTranscript) {
    const validation = validateLesson(lesson);
    if (!validation.ok) {
      return {
        status: "data_error",
        title: "教材データエラー",
        message: validation.detail,
        score: null,
        scoreNote: "",
        improvement: "教材データを確認してください。",
        reason: validation.reason,
        userTokens: []
      };
    }

    const userTokens = normalizeToTokens(userTranscript);
    const unableReason = getUnableReason(lesson, userTranscript, userTokens);
    const primaryCue = getPrimaryCue(lesson);

    if (unableReason && HARD_UNABLE_REASONS.has(unableReason)) {
      return {
        status: "unable",
        reason: unableReason,
        title: "判定できません",
        message: getUnableReasonLabel(unableReason),
        score: null,
        scoreNote: "",
        improvement: primaryCue,
        userTokens
      };
    }

    const focusTokenAtIndex = userTokens[lesson.focusTokenIndex];
    const focusToken = normalizeToken(lesson.focusToken);
    const mishearing = (lesson.commonMishearings || []).find((item) => {
      return focusTokenAtIndex === normalizeToken(item.heard);
    });

    if (mishearing) {
      return {
        status: "common_mishearing",
        title: "目標音チェック",
        message: `${lesson.focusToken} ${lesson.focusTokenIPA} が ${mishearing.heard} ${mishearing.heardIPA} に聞こえた可能性があります`,
        score: 62,
        scoreNote: "文字起こしベースの推定",
        improvement: mishearing.feedback || primaryCue,
        heard: mishearing,
        userTokens
      };
    }

    if (focusTokenAtIndex === focusToken) {
      return {
        status: "focus_match",
        title: "目標音チェック",
        message: `${lesson.focusToken} ${lesson.focusTokenIPA} の ${lesson.focusSound} は再現できている可能性があります`,
        score: 92,
        scoreNote: "文字起こしベースの推定",
        improvement: primaryCue,
        userTokens
      };
    }

    return {
      status: "focus_token_missing",
      reason: "focus_token_missing",
      title: "重点語チェック",
      message: getUnableReasonLabel("focus_token_missing"),
      score: null,
      scoreNote: "",
      improvement: primaryCue,
      userTokens
    };
  }

  function getCategoryList(lessons) {
    return [...new Set(lessons.map((lesson) => lesson.category))];
  }

  function getValidatedLessons() {
    return LESSONS.filter((lesson) => validateLesson(lesson).ok);
  }

  function initApp() {
    const rootEl = document.querySelector("[data-pronunciation-app]");
    if (!rootEl) return;

    const lessons = getValidatedLessons();
    const state = {
      category: "H/F/V",
      lessonId: lessons[0].id
    };

    const els = {
      categoryTabs: rootEl.querySelector("[data-category-tabs]"),
      lessonList: rootEl.querySelector("[data-lesson-list]"),
      lessonTitle: rootEl.querySelector("[data-lesson-title]"),
      focusSound: rootEl.querySelector("[data-focus-sound]"),
      targetWord: rootEl.querySelector("[data-target-word]"),
      targetWordIPA: rootEl.querySelector("[data-target-word-ipa]"),
      contrast: rootEl.querySelector("[data-contrast]"),
      targetSentence: rootEl.querySelector("[data-target-sentence]"),
      targetSentenceIPA: rootEl.querySelector("[data-target-sentence-ipa]"),
      chunks: rootEl.querySelector("[data-chunks]"),
      cues: rootEl.querySelector("[data-cues]"),
      transcript: rootEl.querySelector("[data-transcript]"),
      judgeButton: rootEl.querySelector("[data-judge]"),
      sampleButtons: rootEl.querySelector("[data-samples]"),
      result: rootEl.querySelector("[data-result]"),
      resultTitle: rootEl.querySelector("[data-result-title]"),
      resultMessage: rootEl.querySelector("[data-result-message]"),
      resultScore: rootEl.querySelector("[data-result-score]"),
      resultNote: rootEl.querySelector("[data-result-note]"),
      improvement: rootEl.querySelector("[data-improvement]"),
      tokenLine: rootEl.querySelector("[data-token-line]"),
      nextDrill: rootEl.querySelector("[data-next-drill]")
    };

    function currentLesson() {
      return lessons.find((lesson) => lesson.id === state.lessonId) || lessons[0];
    }

    function renderCategoryTabs() {
      els.categoryTabs.innerHTML = getCategoryList(lessons)
        .map((category) => {
          const selected = category === state.category ? "true" : "false";
          return `<button type="button" class="tab-button" aria-pressed="${selected}" data-category="${category}">${category}</button>`;
        })
        .join("");
    }

    function renderLessonList() {
      const categoryLessons = lessons.filter((lesson) => lesson.category === state.category);
      if (!categoryLessons.some((lesson) => lesson.id === state.lessonId)) {
        state.lessonId = categoryLessons[0].id;
      }
      els.lessonList.innerHTML = categoryLessons
        .map((lesson) => {
          const selected = lesson.id === state.lessonId ? "true" : "false";
          return `
            <button type="button" class="lesson-button" aria-pressed="${selected}" data-lesson-id="${lesson.id}">
              <span>${lesson.targetWord}</span>
              <strong>${lesson.targetWordIPA}</strong>
            </button>
          `;
        })
        .join("");
    }

    function renderLesson() {
      const lesson = currentLesson();
      els.lessonTitle.textContent = `${lesson.category} / ${lesson.targetWord}`;
      els.focusSound.textContent = lesson.focusSound;
      els.targetWord.textContent = lesson.targetWord;
      els.targetWordIPA.textContent = lesson.targetWordIPA;
      els.contrast.innerHTML = lesson.contrastWord
        ? `<span>対比</span><strong>${lesson.contrastWord}</strong><em>${lesson.contrastWordIPA}</em>`
        : `<span>重点</span><strong>${lesson.focusToken}</strong><em>${lesson.focusTokenIPA}</em>`;
      els.targetSentence.textContent = lesson.targetSentence;
      els.targetSentenceIPA.textContent = lesson.targetSentenceIPA;
      els.chunks.innerHTML = (lesson.chunkedSentence || [{ text: lesson.targetSentence, ipa: lesson.targetSentenceIPA }])
        .map((chunk) => `<div class="chunk"><span>${chunk.text}</span><strong>${chunk.ipa}</strong></div>`)
        .join("");
      const cueRows = [
        ["口", lesson.mouthCue],
        ["舌", lesson.tongueCue],
        ["息", lesson.airCue],
        ["長さ", lesson.durationCue],
        ["動き", lesson.movementCue]
      ].filter((row) => row[1]);
      els.cues.innerHTML = cueRows.map((row) => `<li><span>${row[0]}</span>${row[1]}</li>`).join("");
      els.transcript.value = lesson.targetSentence;
      els.nextDrill.textContent = lesson.nextDrill || `${lesson.focusToken} ${lesson.focusTokenIPA} を3回読む`;
      renderResult(judgeTranscript(lesson, els.transcript.value));
      renderSampleButtons(lesson);
    }

    function renderSampleButtons(lesson) {
      const samples = [
        { label: "成功例", value: lesson.targetSentence },
        { label: "短すぎる例", value: lesson.focusTokenIndex > 0 ? "I" : "" }
      ];
      const firstMishearing = lesson.commonMishearings && lesson.commonMishearings[0];
      if (firstMishearing) {
        const targetTokens = getTargetTokens(lesson);
        const replaced = targetTokens.slice();
        replaced[lesson.focusTokenIndex] = firstMishearing.heard;
        samples.splice(1, 0, { label: "聞こえ方例", value: replaced.join(" ") });
      }
      els.sampleButtons.innerHTML = samples
        .map((sample) => `<button type="button" class="sample-button" data-sample="${sample.value}">${sample.label}</button>`)
        .join("");
    }

    function renderResult(result) {
      els.result.dataset.status = result.status;
      els.resultTitle.textContent = result.title;
      els.resultMessage.textContent = result.message;
      els.resultScore.textContent = result.score === null ? "判定できません" : `${result.score}%`;
      els.resultNote.textContent = result.scoreNote || (result.status === "unable" ? result.message : "文字起こしの重点位置を確認してください");
      els.improvement.textContent = result.improvement;
      els.tokenLine.textContent = result.userTokens.length
        ? `tokens: ${result.userTokens.map((token, index) => (index === currentLesson().focusTokenIndex ? `[${token}]` : token)).join(" ")}`
        : "tokens: なし";
    }

    function renderAll() {
      renderCategoryTabs();
      renderLessonList();
      renderLesson();
    }

    els.categoryTabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-category]");
      if (!button) return;
      state.category = button.dataset.category;
      renderAll();
    });

    els.lessonList.addEventListener("click", (event) => {
      const button = event.target.closest("[data-lesson-id]");
      if (!button) return;
      state.lessonId = button.dataset.lessonId;
      renderLessonList();
      renderLesson();
    });

    els.judgeButton.addEventListener("click", () => {
      renderResult(judgeTranscript(currentLesson(), els.transcript.value));
    });

    els.transcript.addEventListener("input", () => {
      renderResult(judgeTranscript(currentLesson(), els.transcript.value));
    });

    els.sampleButtons.addEventListener("click", (event) => {
      const button = event.target.closest("[data-sample]");
      if (!button) return;
      els.transcript.value = button.dataset.sample;
      renderResult(judgeTranscript(currentLesson(), els.transcript.value));
    });

    renderAll();
  }

  return {
    LESSONS,
    HARD_UNABLE_REASONS,
    normalizeText,
    normalizeToTokens,
    normalizeToken,
    validateLesson,
    getCuePriorityField,
    getPrimaryCue,
    judgeTranscript,
    getUnableReasonLabel,
    initApp
  };
});

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", function () {
    window.PronunciationLab.initApp();
  });
}
