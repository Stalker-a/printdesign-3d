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
const contactForm = document.querySelector("#contact-form");
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
      "Hello. Describe what you need to print or scan: a part, housing, fastener, prototype, or object for digitizing.",
  },
];

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

const addMessage = (role, text) => {
  if (!assistantChat) return;

  const message = document.createElement("article");
  message.className = `chat-message ${role === "user" ? "chat-message-user" : "chat-message-bot"}`;

  const roleLabel = document.createElement("span");
  roleLabel.className = "chat-role";
  roleLabel.textContent = role === "user" ? "Client" : "Forge AI";

  const content = document.createElement("p");
  content.textContent = text;

  message.append(roleLabel, content);
  assistantChat.appendChild(message);
  assistantChat.scrollTop = assistantChat.scrollHeight;
};

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
    const message = data.error || "Request failed.";
    throw new Error(message);
  }

  return data;
};

const formatAssistantError = (error) => {
  const rawMessage = String(error?.message || "").trim();

  if (!rawMessage) {
    return "AI server error. Check the model settings and try again.";
  }

  if (rawMessage.includes("memory layout cannot be allocated")) {
    return "Ollama cannot start the model because there is not enough available memory. Try a lighter model or free up RAM.";
  }

  if (rawMessage.includes("OPENAI_API_KEY")) {
    return "OpenAI key is not configured on the server.";
  }

  if (rawMessage.includes("HF_API_KEY")) {
    return "Hugging Face key is not configured on the server.";
  }

  if (rawMessage.includes("Ollama")) {
    return rawMessage;
  }

  return rawMessage;
};

const submitAssistantPrompt = async (prompt) => {
  const cleanPrompt = prompt.trim();
  if (!cleanPrompt) return;

  addMessage("user", cleanPrompt);
  chatHistory.push({ role: "user", content: cleanPrompt });

  try {
    const data = await postJson("/api/chat", {
      message: cleanPrompt,
      history: chatHistory.slice(-10),
    });

    const reply = data.reply || "No answer was received from the assistant.";
    addMessage("assistant", reply);
    chatHistory.push({ role: "assistant", content: reply });
  } catch (error) {
    addMessage("assistant", formatAssistantError(error));
  }
};

if (assistantForm && assistantInput) {
  assistantForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const prompt = assistantInput.value;
    assistantInput.value = "";
    await submitAssistantPrompt(prompt);
    assistantInput.focus();
  });
}

suggestionChips.forEach((chip) => {
  chip.addEventListener("click", async () => {
    const prompt = chip.dataset.prompt || chip.textContent || "";
    await submitAssistantPrompt(prompt);
  });
});

if (contactForm) {
  contactForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const formData = new FormData(contactForm);
    const payload = {
      name: String(formData.get("name") || "").trim(),
      contact: String(formData.get("contact") || "").trim(),
      task: String(formData.get("task") || "").trim(),
    };

    try {
      await postJson("/api/contact", payload);
      contactForm.reset();
    } catch (error) {
      // Intentionally silent to keep the UI clean.
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
