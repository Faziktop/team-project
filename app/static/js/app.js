/**
 * Общие скрипты интерфейса. Вынесены из inline-обработчиков (onsubmit/onchange)
 * и inline-<script>, чтобы Content-Security-Policy мог запретить inline-JS
 * (script-src 'self'): любой внедрённый через XSS скрипт не выполнится.
 *
 * Разметка управляет поведением через data-атрибуты:
 *   <form data-confirm="Текст вопроса?">     — подтверждение перед отправкой
 *   <select data-autosubmit>                   — отправка формы при смене значения
 *   <div id="slots" data-quest-id=… data-api-url=… data-step2-url=…> — загрузка сеансов
 */
(function () {
  "use strict";

  // --- Подтверждение действий -------------------------------------------------
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    var message = form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      e.preventDefault();
    }
  });

  // --- Автоотправка формы при смене select ------------------------------------
  document.addEventListener("change", function (e) {
    var el = e.target;
    if (el instanceof HTMLSelectElement && el.hasAttribute("data-autosubmit") && el.form) {
      el.form.submit();
    }
  });

  // --- Выбор сеанса на странице квеста ----------------------------------------
  var slotsDiv = document.getElementById("slots");
  var picker = document.getElementById("date-picker");
  if (slotsDiv && picker) {
    var questId = slotsDiv.getAttribute("data-quest-id");
    var apiUrl = slotsDiv.getAttribute("data-api-url");
    var step2Template = slotsDiv.getAttribute("data-step2-url"); // содержит "0" вместо id

    var showMessage = function (text) {
      slotsDiv.textContent = "";
      var span = document.createElement("span");
      span.className = "qe-muted";
      span.textContent = text;
      slotsDiv.appendChild(span);
    };

    var loadSlots = function (dateStr) {
      if (!dateStr) return;
      showMessage("Загрузка…");
      var url = apiUrl + "?quest_id=" + encodeURIComponent(questId) +
        "&date_from=" + encodeURIComponent(dateStr) + "&date_to=" + encodeURIComponent(dateStr);
      fetch(url, { headers: { "Accept": "application/json" } })
        .then(function (res) {
          if (!res.ok) throw new Error("HTTP " + res.status);
          return res.json();
        })
        .then(function (data) {
          if (!data.length) {
            showMessage("На эту дату свободных сеансов нет");
            return;
          }
          slotsDiv.textContent = "";
          data.forEach(function (s) {
            var time = new Date(s.start_time);
            var hh = String(time.getHours()).padStart(2, "0");
            var mm = String(time.getMinutes()).padStart(2, "0");
            var a = document.createElement("a");
            a.href = step2Template.replace(/0$/, String(s.id));
            a.className = "qe-ticket qe-ticket-available";
            var icon = document.createElement("i");
            icon.className = "bi bi-ticket-perforated";
            a.appendChild(icon);
            // textContent, а не innerHTML: название комнаты задаёт администратор
            a.appendChild(document.createTextNode(" " + hh + ":" + mm + " · " + s.room));
            slotsDiv.appendChild(a);
          });
        })
        .catch(function () {
          showMessage("Не удалось загрузить сеансы. Попробуйте обновить страницу.");
        });
    };

    picker.addEventListener("change", function () { loadSlots(picker.value); });
    loadSlots(picker.value);
  }
})();
