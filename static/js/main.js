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
