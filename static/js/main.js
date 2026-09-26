const integrationPanel = document.querySelector("#php-integration");

if (integrationPanel) {
    const statusMessage = integrationPanel.querySelector("[data-integration-status]");
    const sectorList = integrationPanel.querySelector("[data-sector-list]");

    fetch(integrationPanel.dataset.endpoint)
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
