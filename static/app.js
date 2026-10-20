document.querySelectorAll("[data-chart-segments]").forEach((chart) => {
    const segments = JSON.parse(chart.dataset.chartSegments || "[]");
    if (segments.length) {
        const stops = segments
            .map(({ color, start, end }) => `${color} ${start}% ${end}%`)
            .join(", ");
        chart.style.background = `conic-gradient(${stops})`;
    }
});

document.querySelectorAll("[data-progress]").forEach((progress) => {
    const percentage = Number(progress.dataset.progress);
    if (Number.isFinite(percentage)) {
        progress.style.width = `${Math.max(0, Math.min(percentage, 100))}%`;
    }
});

document.querySelectorAll("[data-money-input]").forEach((input) => {
    input.addEventListener("input", () => {
        const cursor = input.selectionStart ?? input.value.length;
        const digitsBeforeCursor = input.value
            .slice(0, cursor)
            .replace(/\D/g, "").length;
        const cleaned = input.value.replace(/[^\d.]/g, "");
        const decimalIndex = cleaned.indexOf(".");
        const integerPart = decimalIndex === -1
            ? cleaned
            : cleaned.slice(0, decimalIndex);
        const decimalPart = decimalIndex === -1
            ? ""
            : `.${cleaned.slice(decimalIndex + 1).replace(/\./g, "").slice(0, 2)}`;
        const groupedInteger = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        const formatted = `${groupedInteger}${decimalPart}`;

        input.value = formatted;
        let newCursor = 0;
        let digitsSeen = 0;
        while (newCursor < formatted.length && digitsSeen < digitsBeforeCursor) {
            if (/\d/.test(formatted[newCursor])) {
                digitsSeen += 1;
            }
            newCursor += 1;
        }
        input.setSelectionRange(newCursor, newCursor);
    });
});
