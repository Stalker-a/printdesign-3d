const navToggle = document.querySelector(".nav-toggle");
const navMenu = document.querySelector(".nav-menu");
const faqButtons = document.querySelectorAll(".faq-question");
const fadeTargets = document.querySelectorAll(
  ".service-card, .timeline-item, .case-card, .benefit-card, .contact-form, .panel-box, .assistant-card, .assistant-points article"
);
const assistantForm = document.querySelector("#assistant-form");
const assistantInput = document.querySelector("#assistant-input");
const assistantChat = document.querySelector("#assistant-chat");
const suggestionChips = document.querySelectorAll(".suggestion-chip");
const casesGrid = document.querySelector("#cases-grid");
const contactForm = document.querySelector("#contact-form");
const contactFileInput = document.querySelector("#contact-file");
const contactFileMeta = document.querySelector("#contact-file-meta");
const contactStatus = document.querySelector("#contact-status");
const contactSubmit = document.querySelector("#contact-submit");
const translateShell = document.querySelector(".translate-shell");
const translateTrigger = document.querySelector("#translate-trigger");
const translateTriggerLabel = document.querySelector(".translate-trigger-label");
const translateTriggerCode = document.querySelector(".translate-trigger-code");
const translateTriggerStatus = document.querySelector(".translate-trigger-status");
const translateQuick = document.querySelector("#translate-quick");
const translateMenu = document.querySelector("#translate-menu");

const quickLanguageStatus = "RU / EN / ZH / KZ";
const popularLanguages = [
  { value: "", label: "Russian", short: "RU" },
  { value: "en", label: "English", short: "EN" },
  { value: "zh-CN", label: "Chinese", short: "ZH" },
  { value: "kk", label: "Kazakh", short: "KZ" },
];

const chatHistory = [
  {
    role: "assistant",
    content:
      "Здравствуйте. Опишите, что нужно изготовить или отсканировать: деталь, корпус, крепление, прототип или объект для оцифровки.",
  },
];

const postJson = async (url, payload) => {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Не удалось выполнить запрос.");
  }

  return data;
};

const postForm = async (url, formData) => {
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Не удалось выполнить запрос.");
  }

  return data;
};

const sendAnalytics = (event, details = {}) => {
  const payload = JSON.stringify({
    event,
    details,
  });

  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/api/track", new Blob([payload], { type: "application/json" }));
      return;
    }
  } catch (error) {}

  fetch("/api/track", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: payload,
    keepalive: true,
  }).catch(() => {});
};

const reportLeadConversion = (leadId, hasFile) => {
  if (typeof window.gtag === "function") {
    window.gtag("event", "generate_lead", {
      event_category: "engagement",
      event_label: "contact_form",
      value: hasFile ? 2 : 1,
    });
  }

  if (Array.isArray(window.dataLayer)) {
    window.dataLayer.push({
      event: "lead_submitted",
      leadId,
      hasFile,
    });
  }
};

const formatBytes = (value) => {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 Б";
  }

  if (value < 1024) {
    return `${value} Б`;
  }

  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} КБ`;
  }

  return `${(value / (1024 * 1024)).toFixed(1)} МБ`;
};

const setContactStatus = (message = "", tone = "info") => {
  if (!contactStatus) return;

  const cleanMessage = String(message || "").trim();
  contactStatus.textContent = cleanMessage;
  contactStatus.className = "form-status";

  if (!cleanMessage) {
    return;
  }

  contactStatus.classList.add("is-visible");
  if (tone === "success") {
    contactStatus.classList.add("is-success");
  } else if (tone === "error") {
    contactStatus.classList.add("is-error");
  } else {
    contactStatus.classList.add("is-info");
  }
};

const syncContactFileMeta = () => {
  if (!contactFileMeta || !contactFileInput) return;

  const file = contactFileInput.files?.[0];
  if (!file) {
    contactFileMeta.textContent = "";
    return;
  }

  contactFileMeta.textContent = `Выбран файл: ${file.name} (${formatBytes(file.size)})`;
};

const formatContactError = (error) => {
  const rawMessage = String(error?.message || "").trim();
  if (!rawMessage) {
    return "Не удалось отправить заявку. Попробуйте еще раз.";
  }

  if (rawMessage.includes("слишком большой")) {
    return rawMessage;
  }

  if (rawMessage.includes("TELEGRAM_BOT_TOKEN") || rawMessage.includes("TELEGRAM_CHAT_ID")) {
    return "Форма приняла заявку, но Telegram на сервере пока не настроен. Проверьте переменные окружения.";
  }

  return rawMessage;
};

const formatAssistantError = (error) => {
  const rawMessage = String(error?.message || "").trim();

  if (!rawMessage) {
    return "Ошибка AI-сервера. Проверьте настройки модели и попробуйте снова.";
  }

  if (rawMessage.includes("memory layout cannot be allocated")) {
    return "Ollama не может запустить модель из-за нехватки памяти. Попробуйте более лёгкую модель или освободите RAM.";
  }

  if (rawMessage.includes("OPENAI_API_KEY")) {
    return "На сервере не настроен ключ OpenAI.";
  }

  if (rawMessage.includes("HF_API_KEY")) {
    return "На сервере не настроен ключ Hugging Face.";
  }

  if (rawMessage.includes("Ollama")) {
    return rawMessage;
  }

  return rawMessage;
};

const addMessage = (role, text) => {
  if (!assistantChat) return;

  const message = document.createElement("article");
  message.className = `chat-message ${role === "user" ? "chat-message-user" : "chat-message-bot"}`;

  const roleLabel = document.createElement("span");
  roleLabel.className = "chat-role";
  roleLabel.textContent = role === "user" ? "Клиент" : "3DD AI";

  const content = document.createElement("p");
  content.textContent = text;

  message.append(roleLabel, content);
  assistantChat.appendChild(message);
  assistantChat.scrollTop = assistantChat.scrollHeight;
};

const createCaseMetric = ({ label = "", value = "" }) => {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const description = document.createElement("dd");

  term.textContent = label;
  description.textContent = value;
  wrapper.append(term, description);
  return wrapper;
};

const createCaseCard = (item) => {
  const article = document.createElement("article");
  article.className = "case-card case-card-detailed";

  const content = document.createElement("div");
  content.className = "case-content";

  const topline = document.createElement("div");
  topline.className = "case-topline";

  const tag = document.createElement("span");
  tag.className = "case-tag";
  tag.textContent = item.tag || "Кейс";

  const status = document.createElement("span");
  status.className = "case-status";
  status.textContent = item.status || "Пример";

  topline.append(tag, status);

  const title = document.createElement("h3");
  title.textContent = item.title || "Без названия";

  const description = document.createElement("p");
  description.textContent = item.description || "";

  content.append(topline, title, description);

  if (Array.isArray(item.metrics) && item.metrics.length) {
    const metrics = document.createElement("dl");
    metrics.className = "case-metrics";
    item.metrics.forEach((metric) => metrics.appendChild(createCaseMetric(metric)));
    content.appendChild(metrics);
  }

  if (Array.isArray(item.bullets) && item.bullets.length) {
    const bullets = document.createElement("ul");
    bullets.className = "case-bullets";
    item.bullets.forEach((entry) => {
      const bullet = document.createElement("li");
      bullet.textContent = entry;
      bullets.appendChild(bullet);
    });
    content.appendChild(bullets);
  }

  article.appendChild(content);
  return article;
};

const renderCases = (items) => {
  if (!casesGrid) return;

  casesGrid.innerHTML = "";

  if (!Array.isArray(items) || !items.length) {
    return;
  }

  items.forEach((item) => {
    casesGrid.appendChild(createCaseCard(item));
  });
};

const loadCases = async () => {
  if (!casesGrid) return;

  try {
    const response = await fetch("content/cases.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("cases.json is unavailable");
    }

    const data = await response.json();
    renderCases(data);
  } catch (error) {
    renderCases([]);
  }
};

const submitAssistantPrompt = async (prompt, source = "form") => {
  const cleanPrompt = prompt.trim();
  if (!cleanPrompt) return;

  addMessage("user", cleanPrompt);
  chatHistory.push({ role: "user", content: cleanPrompt });
  sendAnalytics("assistant_prompt_client", {
    source,
    prompt_length: cleanPrompt.length,
  });

  try {
    const data = await postJson("/api/chat", {
      message: cleanPrompt,
      history: chatHistory.slice(-10),
    });

    const reply = data.reply || "Ассистент не вернул ответ.";
    addMessage("assistant", reply);
    chatHistory.push({ role: "assistant", content: reply });
  } catch (error) {
    addMessage("assistant", formatAssistantError(error));
  }
};

if (navToggle && navMenu) {
  navToggle.addEventListener("click", () => {
    const isOpen = navMenu.classList.toggle("is-open");
    navToggle.setAttribute("aria-expanded", String(isOpen));
  });

  navMenu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      navMenu.classList.remove("is-open");
      navToggle.setAttribute("aria-expanded", "false");
    });
  });
}

faqButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const item = button.closest(".faq-item");
    const isOpen = item.classList.toggle("is-open");
    button.setAttribute("aria-expanded", String(isOpen));
  });
});

if (assistantForm && assistantInput) {
  assistantForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const prompt = assistantInput.value;
    assistantInput.value = "";
    await submitAssistantPrompt(prompt, "form");
    assistantInput.focus();
  });
}

suggestionChips.forEach((chip) => {
  chip.addEventListener("click", async () => {
    const prompt = chip.dataset.prompt || chip.textContent || "";
    await submitAssistantPrompt(prompt, "chip");
  });
});

if (contactFileInput) {
  contactFileInput.addEventListener("change", syncContactFileMeta);
  syncContactFileMeta();
}

if (contactForm) {
  contactForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setContactStatus("Отправляем заявку...", "info");

    const formData = new FormData(contactForm);
    const contactValue = String(formData.get("contact") || "").trim();
    const taskValue = String(formData.get("task") || "").trim();
    const hasFile = Boolean(contactFileInput?.files?.[0]);

    if (!contactValue) {
      setContactStatus("Укажите телефон или Telegram для обратной связи.", "error");
      return;
    }

    if (!taskValue) {
      setContactStatus("Опишите задачу перед отправкой.", "error");
      return;
    }

    if (contactSubmit) {
      contactSubmit.disabled = true;
    }

    sendAnalytics("lead_submit_started", { has_file: hasFile });

    try {
      const data = await postForm("/api/contact", formData);
      contactForm.reset();
      syncContactFileMeta();
      setContactStatus(
        `Заявка отправлена${data.lead_id ? `, номер ${data.lead_id}` : ""}. Мы свяжемся с вами после первичной оценки.`,
        "success"
      );
      reportLeadConversion(data.lead_id || "", hasFile);
      sendAnalytics("lead_submit_client_success", {
        has_file: hasFile,
        lead_id: data.lead_id || "",
      });
    } catch (error) {
      setContactStatus(formatContactError(error), "error");
      sendAnalytics("lead_submit_failed", {
        has_file: hasFile,
      });
    } finally {
      if (contactSubmit) {
        contactSubmit.disabled = false;
      }
    }
  });
}

const dispatchChange = (element) => {
  element.dispatchEvent(new Event("change", { bubbles: true }));
};

const getGoogleCombo = () => document.querySelector(".goog-te-combo");

const getLanguageByValue = (value) =>
  popularLanguages.find((language) => language.value === value) || popularLanguages[0];

const getTranslateCookieValue = () => {
  const match = document.cookie.match(/(?:^|;\s*)googtrans=([^;]+)/);
  if (!match) return "";

  const decoded = decodeURIComponent(match[1]);
  const parts = decoded.split("/");
  return parts[2] || "";
};

const writeGoogleTranslateCookie = (value) => {
  const host = window.location.hostname;
  const encoded = encodeURIComponent(`/ru/${value}`);
  const cookies = [`googtrans=${encoded};path=/`];

  if (host && host !== "localhost") {
    cookies.push(`googtrans=${encoded};path=/;domain=${host}`);

    if (host.includes(".")) {
      cookies.push(`googtrans=${encoded};path=/;domain=.${host}`);
    }
  }

  cookies.forEach((cookie) => {
    document.cookie = cookie;
  });
};

const clearGoogleTranslateCookies = () => {
  const host = window.location.hostname;
  const cookies = [
    "googtrans=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/",
  ];

  if (host) {
    cookies.push(`googtrans=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;domain=${host}`);

    if (host.includes(".")) {
      cookies.push(`googtrans=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;domain=.${host}`);
    }
  }

  cookies.forEach((cookie) => {
    document.cookie = cookie;
  });
};

const setTranslateOpen = (isOpen) => {
  if (!translateShell || !translateTrigger || !translateMenu) return;

  translateShell.classList.toggle("is-open", isOpen);
  translateTrigger.setAttribute("aria-expanded", String(isOpen));
  translateMenu.hidden = !isOpen;
};

const syncTranslateUi = (value) => {
  const matchedLanguage = getLanguageByValue(value);

  if (translateTriggerLabel) {
    translateTriggerLabel.textContent = `Language: ${matchedLanguage.label}`;
  }

  if (translateTriggerCode) {
    translateTriggerCode.textContent = matchedLanguage.short;
  }

  if (translateTriggerStatus) {
    translateTriggerStatus.textContent = quickLanguageStatus;
  }

  if (translateMenu) {
    translateMenu.querySelectorAll(".translate-option").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.value === matchedLanguage.value);
    });
  }

  if (translateQuick) {
    translateQuick.querySelectorAll(".translate-quick-button").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.value === matchedLanguage.value);
    });
  }
};

const applyLanguage = (value) => {
  const matchedLanguage = getLanguageByValue(value);
  const combo = getGoogleCombo();

  if (matchedLanguage.value === "") {
    clearGoogleTranslateCookies();
  } else {
    writeGoogleTranslateCookie(matchedLanguage.value);
  }

  if (combo && matchedLanguage.value) {
    combo.value = matchedLanguage.value;
    dispatchChange(combo);
  }

  syncTranslateUi(matchedLanguage.value);
  setTranslateOpen(false);
  window.setTimeout(() => window.location.reload(), 120);
};

const createLanguageButton = (language, className) => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.dataset.value = language.value;
  button.textContent = className === "translate-option" ? language.label : language.short;
  button.title = language.label;
  button.addEventListener("click", () => applyLanguage(language.value));
  return button;
};

const buildTranslateMenu = () => {
  if (!translateMenu) return;

  if (translateQuick) {
    translateQuick.innerHTML = "";
    popularLanguages.forEach((language) => {
      translateQuick.appendChild(createLanguageButton(language, "translate-quick-button"));
    });
  }

  translateMenu.innerHTML = "";
  popularLanguages.forEach((language) => {
    translateMenu.appendChild(createLanguageButton(language, "translate-option"));
  });
};

if (translateTrigger && translateMenu) {
  buildTranslateMenu();
  syncTranslateUi(getTranslateCookieValue());

  translateTrigger.addEventListener("click", () => {
    setTranslateOpen(translateMenu.hidden);
  });

  document.addEventListener("click", (event) => {
    if (!translateShell) return;
    if (!translateShell.contains(event.target)) {
      setTranslateOpen(false);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setTranslateOpen(false);
    }
  });
}

if ("IntersectionObserver" in window) {
  fadeTargets.forEach((element) => element.classList.add("fade-in"));

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12 }
  );

  fadeTargets.forEach((element) => observer.observe(element));
}

loadCases();

sendAnalytics("page_view", {
  page: window.location.pathname,
  language: getTranslateCookieValue() || "ru",
});
