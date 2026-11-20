// AI Model Lab: finite read-only Pi tool budget.
// Controls Pi tools, NOT an OS filesystem sandbox.
export default function(pi) {
  const input = Number.parseInt(process.env.AI_LAB_TOOL_BUDGET || "24", 10);
  const limit = Number.isFinite(input) && input > 0 && input <= 500 ? input : 24;
  let admitted = 0, exhausted = false;
  pi.on("session_start", () => console.error(`[AI_LAB_GUARD] ready budget=${limit}`));
  pi.on("tool_call", (event) => {
    if (admitted >= limit) {
      return {block:true, reason:`AI Lab: достигнут лимит ${limit} вызовов; выдай итоговый отчёт.`};
    }
    admitted += 1;
  });
  pi.on("tool_execution_end", () => {
    if (!exhausted && admitted >= limit) {
      exhausted = true;
      pi.setActiveTools([]);
      console.error(`[AI_LAB_GUARD] exhausted at ${admitted} calls`);
    }
  });
  pi.on("context", event => {
    if (!exhausted) return;
    return {messages:[...event.messages, {role:"user", content:[{type:"text", text:
      "[AI Model Lab] Лимит инструментов достигнут. Инструменты недоступны. Немедленно выдай завершённый ответ на русском по проверенным фактам. Не придумывай пути, номера строк, API или связи. Отдельно отметь непроверенные части."}], timestamp:Date.now()}]};
  });
}
