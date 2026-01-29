export function formatDateToText(dateStr: string) {
    if (!dateStr) return "";

    let day, month;

    // Вариант 1: "08.03.2026" (из fmt_date/local)
    if (dateStr.includes('.')) {
        const parts = dateStr.split('.');
        day = parseInt(parts[0], 10);
        month = parseInt(parts[1], 10);
    }
    // Вариант 2: "2026-03-08" (из date)
    else if (dateStr.includes('-')) {
        const parts = dateStr.split('-');
        day = parseInt(parts[2], 10);
        month = parseInt(parts[1], 10);
    } else {
        return dateStr;
    }

    const months = ["", "ЯНВАРЯ", "ФЕВРАЛЯ", "МАРТА", "АПРЕЛЯ", "МАЯ", "ИЮНЯ", "ИЮЛЯ", "АВГУСТА", "СЕНТЯБРЯ", "ОКТЯБРЯ", "НОЯБРЯ", "ДЕКАБРЯ"];
    return `${day} ${months[month] || ""}`;
}