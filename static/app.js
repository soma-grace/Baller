document.querySelectorAll("[data-chart-segments]").forEach((chart) => {
    const segments = JSON.parse(chart.dataset.chartSegments || "[]");
    if (segments.length) {
        const stops = segments
            .map(({ color, start, end }) => `${color} ${start}% ${end}%`)
            .join(", ");
        chart.style.background = `conic-gradient(${stops})`;
    }
});

const donut = document.querySelector("#donut");
const donutDateRow = document.querySelector("#donut-date-row");
const donutDate = document.querySelector("#donut-date");
if (donut instanceof HTMLElement && donutDateRow && donutDate instanceof HTMLInputElement) {
    const monthSegments = JSON.parse(donut.dataset.chartSegments || "[]");
    const daily = JSON.parse(donut.dataset.daily || "{}");
    const total = document.querySelector("#donut-total");
    const caption = document.querySelector("#donut-caption");
    const naira = (value) => `₦${Number(value).toLocaleString("en-NG", { maximumFractionDigits: 2 })}`;
    const paint = (segments) => {
        donut.style.background = segments.length
            ? `conic-gradient(${segments.map(({ color, start, end }) => `${color} ${start}% ${end}%`).join(", ")})`
            : "";
    };
    const showDay = () => {
        const items = daily[donutDate.value] || [];
        const sum = items.reduce((acc, item) => acc + Number(item.amount), 0);
        let cumulative = 0;
        paint(items.map((item) => {
            const start = (cumulative * 100) / sum;
            cumulative += Number(item.amount);
            return { color: item.color, start, end: (cumulative * 100) / sum };
        }));
        total.textContent = naira(sum);
        caption.textContent = donutDate.value === donut.dataset.today
            ? "Spent today"
            : `Spent on ${donutDate.value}`;
    };
    const openDay = () => {
        donutDateRow.hidden = false;
        donutDate.max = donut.dataset.today;
        if (!donutDate.value) donutDate.value = donut.dataset.today;
        showDay();
    };
    donut.addEventListener("click", openDay);
    donut.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openDay();
        }
    });
    donutDate.addEventListener("change", () => {
        if (!donutDate.value) donutDate.value = donut.dataset.today;
        showDay();
    });
    document.querySelector("#donut-reset")?.addEventListener("click", () => {
        donutDateRow.hidden = true;
        donutDate.value = donut.dataset.today;
        paint(monthSegments);
        total.textContent = donut.dataset.monthTotal;
        caption.textContent = "Total spent";
    });
}

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

const budgetForm = document.querySelector("#budget-form");
const budgetFields = document.querySelector("#budget-form-fields");

if (budgetForm instanceof HTMLElement && budgetFields instanceof HTMLFormElement) {
    const categoryInput = budgetFields.querySelector('select[name="category"]');
    const amountInput = budgetFields.querySelector('input[name="amount"]');
    const monthInput = budgetFields.querySelector('input[name="month"]');
    const title = document.querySelector("#budget-form-title");
    const submitLabel = document.querySelector("#budget-submit-label");
    const cancelButton = document.querySelector("#cancel-budget-edit");
    const resetBudgetForm = (showForm) => {
        budgetFields.reset();
        budgetFields.action = "/budgets";
        if (title) title.textContent = "Create a budget";
        if (submitLabel) submitLabel.textContent = "Save budget";
        if (cancelButton instanceof HTMLElement) cancelButton.hidden = true;
        budgetForm.hidden = !showForm;
    };

    document.querySelectorAll("[data-open-budget]").forEach((button) => {
        button.addEventListener("click", () => resetBudgetForm(true));
    });
    document.querySelectorAll("[data-close-budget]").forEach((button) => {
        button.addEventListener("click", () => resetBudgetForm(false));
    });

    document.querySelectorAll("[data-edit-budget]").forEach((button) => {
        button.addEventListener("click", () => {
            if (!(button instanceof HTMLElement)) {
                return;
            }
            const budgetId = button.dataset.budgetId;
            const amount = button.dataset.amount;
            const month = button.dataset.month;
            const category = button.dataset.category;
            if (!budgetId || !amount || !month ||
                !(categoryInput instanceof HTMLSelectElement) ||
                !(amountInput instanceof HTMLInputElement) ||
                !(monthInput instanceof HTMLInputElement)) {
                return;
            }

            budgetFields.action = `/budgets/${budgetId}/edit`;
            categoryInput.value = category || "";
            amountInput.value = amount;
            monthInput.value = month;

            if (title) title.textContent = "Edit budget";
            if (submitLabel) submitLabel.textContent = "Save changes";
            if (cancelButton instanceof HTMLElement) cancelButton.hidden = false;
            budgetForm.hidden = false;
            budgetForm.scrollIntoView({ behavior: "smooth", block: "start" });
        });
    });

    cancelButton?.addEventListener("click", () => {
        resetBudgetForm(false);
    });
}
