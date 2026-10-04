const menuToggle = document.querySelector(".mobile-nav-toggle");
const navigation = document.querySelector("#site-navigation");

if (menuToggle && navigation) {
    document.documentElement.classList.add("has-mobile-nav");

    const closeMenu = () => {
        menuToggle.setAttribute("aria-expanded", "false");
        navigation.classList.remove("is-open");
    };

    menuToggle.addEventListener("click", () => {
        const isExpanded = menuToggle.getAttribute("aria-expanded") === "true";
        menuToggle.setAttribute("aria-expanded", String(!isExpanded));
        navigation.classList.toggle("is-open", !isExpanded);
    });

    navigation.addEventListener("click", (event) => {
        if (event.target instanceof Element && event.target.closest("a")) {
            closeMenu();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && menuToggle.getAttribute("aria-expanded") === "true") {
            closeMenu();
            menuToggle.focus();
        }
    });
}

const assistantForm = document.querySelector("[data-assistant-form]");

if (assistantForm instanceof HTMLFormElement) {
    const questionField = assistantForm.querySelector("[name='question']");
    const submitButton = assistantForm.querySelector("[data-assistant-submit]");
    const statusMessage = assistantForm.querySelector("[data-assistant-status]");
    const conversation = document.querySelector("[data-assistant-log]");

    const addAssistantMessage = (text, className) => {
        const message = document.createElement("p");
        message.className = `assistant-message ${className}`;
        message.textContent = text;
        conversation.append(message);
        message.scrollIntoView({ block: "nearest", behavior: "smooth" });
    };

    document.querySelectorAll("[data-assistant-prompt]").forEach((button) => {
        button.addEventListener("click", () => {
            questionField.value = button.dataset.assistantPrompt || "";
            questionField.focus();
        });
    });

    assistantForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const question = questionField.value.trim();
        if (!question || question.length > 1000) {
            statusMessage.textContent = "Escribe una pregunta de hasta 1000 caracteres.";
            return;
        }

        addAssistantMessage(question, "assistant-message-user");
        statusMessage.textContent = "Consultando el asistente…";
        submitButton.disabled = true;

        try {
            const response = await fetch(assistantForm.dataset.endpoint, {
                method: "POST",
                body: new FormData(assistantForm),
                headers: { Accept: "application/json" },
            });
            const payload = await response.json();
            if (typeof payload.answer === "string") {
                addAssistantMessage(
                    payload.answer,
                    payload.fallback ? "assistant-message-fallback" : "assistant-message-answer",
                );
            }
            if (response.ok && payload.success) {
                statusMessage.textContent = "Respuesta generada. Verifica que la información se ajuste a tu experiencia.";
                questionField.value = "";
            } else {
                statusMessage.textContent = payload.message || "No se pudo procesar la pregunta.";
            }
        } catch {
            statusMessage.textContent =
                "No se pudo conectar con el asistente. Las demás funciones de ConectaTalento siguen disponibles.";
        } finally {
            submitButton.disabled = false;
            questionField.focus();
        }
    });
}

const profileReviewForm = document.querySelector("[data-profile-review-form]");

if (profileReviewForm instanceof HTMLFormElement) {
    const submitButton = profileReviewForm.querySelector("[data-profile-review-submit]");
    const status = profileReviewForm.querySelector("[data-profile-review-status]");
    const result = profileReviewForm.querySelector("[data-profile-review-result]");

    profileReviewForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        submitButton.disabled = true;
        status.textContent = "Revisando tus antecedentes profesionales…";
        result.replaceChildren();

        try {
            const response = await fetch(profileReviewForm.dataset.endpoint, {
                method: "POST",
                body: new FormData(profileReviewForm),
                headers: { Accept: "application/json" },
            });
            const payload = await response.json();
            if (typeof payload.answer === "string") {
                const answer = document.createElement("p");
                answer.className = payload.fallback
                    ? "assistant-message assistant-message-fallback"
                    : "assistant-message assistant-message-answer";
                answer.textContent = payload.answer;
                result.append(answer);
            }
            status.textContent = response.ok && payload.success
                ? "Sugerencias generadas. Verifica que describan hechos reales."
                : payload.message || "No se pudo revisar el perfil.";
        } catch {
            status.textContent =
                "No se pudo conectar con el asistente. Las demás funciones siguen disponibles.";
        } finally {
            submitButton.disabled = false;
        }
    });
}

const interviewForm = document.querySelector("[data-interview-form]");

if (interviewForm instanceof HTMLFormElement) {
    const log = interviewForm.querySelector("[data-interview-log]");
    const status = interviewForm.querySelector("[data-interview-status]");
    const answerField = interviewForm.querySelector("[name='answer']");
    const questionButton = interviewForm.querySelector("[data-interview-question]");
    const feedbackButton = interviewForm.querySelector("[data-interview-feedback]");
    let requestInProgress = false;

    const appendInterviewMessage = (text, className) => {
        const message = document.createElement("p");
        message.className = `assistant-message ${className}`;
        message.textContent = text;
        log.append(message);
        message.scrollIntoView({ block: "nearest", behavior: "smooth" });
    };

    const requestInterviewHelp = async (mode) => {
        if (requestInProgress) {
            return;
        }
        const answer = answerField.value.trim();
        if (mode === "feedback" && !answer) {
            status.textContent = "Escribe primero tu respuesta.";
            answerField.focus();
            return;
        }

        const formData = new FormData(interviewForm);
        formData.set("mode", mode);
        formData.set("answer", answer);
        requestInProgress = true;
        questionButton.disabled = true;
        feedbackButton.disabled = true;
        status.textContent = mode === "question"
            ? "Preparando una pregunta…"
            : "Revisando tu respuesta…";

        try {
            const response = await fetch(interviewForm.dataset.endpoint, {
                method: "POST",
                body: formData,
                headers: { Accept: "application/json" },
            });
            const payload = await response.json();
            if (typeof payload.answer === "string") {
                appendInterviewMessage(
                    payload.answer,
                    payload.fallback ? "assistant-message-fallback" : "assistant-message-answer",
                );
            }
            status.textContent = response.ok && payload.success
                ? "Orientación generada. Usa solo ejemplos reales de tu experiencia."
                : payload.message || "No se pudo completar la práctica.";
        } catch {
            status.textContent = "No se pudo conectar con el asistente. Inténtalo nuevamente más tarde.";
        } finally {
            requestInProgress = false;
            questionButton.disabled = false;
            feedbackButton.disabled = false;
        }
    };

    questionButton.addEventListener("click", () => requestInterviewHelp("question"));
    feedbackButton.addEventListener("click", () => requestInterviewHelp("feedback"));
}

const companyReviewForm = document.querySelector("[data-company-review-form]");

if (companyReviewForm instanceof HTMLFormElement) {
    const submitButton = companyReviewForm.querySelector("[data-company-review-submit]");
    const status = companyReviewForm.querySelector("[data-company-review-status]");
    const result = companyReviewForm.querySelector("[data-company-review-result]");

    companyReviewForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        submitButton.disabled = true;
        status.textContent = "Preparando una guía basada en criterios laborales…";
        result.replaceChildren();

        try {
            const response = await fetch(companyReviewForm.dataset.endpoint, {
                method: "POST",
                body: new FormData(companyReviewForm),
                headers: { Accept: "application/json" },
            });
            const payload = await response.json();
            if (typeof payload.answer === "string") {
                const answer = document.createElement("p");
                answer.className = payload.fallback
                    ? "assistant-message assistant-message-fallback"
                    : "assistant-message assistant-message-answer";
                answer.textContent = payload.answer;
                result.append(answer);
            }
            status.textContent = response.ok && payload.success
                ? "Guía generada. Verifica cada dato con la persona."
                : payload.message || "No se pudo preparar la guía.";
        } catch {
            status.textContent =
                "No se pudo conectar con el asistente. Las demás funciones siguen disponibles.";
        } finally {
            submitButton.disabled = false;
        }
    });
}

const integrationPanel = document.querySelector("#php-integration");

if (integrationPanel) {
    const statusMessage = integrationPanel.querySelector("[data-integration-status]");
    const sectorList = integrationPanel.querySelector("[data-sector-list]");

    fetch(integrationPanel.dataset.endpoint || "/api/php/sectores")
        .then((response) => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then((payload) => {
            if (!payload.success || !Array.isArray(payload.sectores)) {
                throw new Error("Respuesta no válida del servicio PHP");
            }
            sectorList.replaceChildren();
            payload.sectores.forEach((item) => {
                const entry = document.createElement("li");
                entry.textContent = `${item.sector}: ${item.ofertas_activas} ofertas activas`;
                sectorList.append(entry);
            });
            statusMessage.textContent = payload.sectores.length
                ? "Datos obtenidos desde PHP y MySQL."
                : "No hay sectores con información.";
        })
        .catch(() => {
            statusMessage.textContent =
                "El servicio PHP/MySQL no está disponible. Inicia el módulo PHP para ver estas estadísticas.";
        });
}
