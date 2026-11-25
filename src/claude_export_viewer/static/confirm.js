/* The one confirmation box of the site, for every removal of a whole set (all the favorites of a
 * conversation, later its links and highlighted passages): CEV.confirm(text, onYes[, onNo]).
 * "Non", Escape or a click outside the box: nothing done. */
(function () {
  "use strict";
  window.CEV.confirm = function (text, onYes, onNo) {
    var box = document.createElement("dialog");
    box.className = "cev-confirm";
    // all inside an inner block: a click on the box itself is a click on the backdrop
    box.innerHTML = '<div class="cev-confirm-in"><p class="cev-confirm-text"></p><div class="cev-confirm-buttons">' +
      '<button type="button" class="cev-confirm-yes"></button><button type="button" class="cev-confirm-no"></button></div></div>';
    box.querySelector(".cev-confirm-text").textContent = text;
    box.querySelector(".cev-confirm-yes").textContent = CEV.t("web.confirm.yes");
    box.querySelector(".cev-confirm-no").textContent = CEV.t("web.confirm.no");
    var done = false;
    function close(yes) {
      if (done) { return; }
      done = true;
      box.close();
      box.remove();
      if (yes) { onYes(); } else if (onNo) { onNo(); }
    }
    box.addEventListener("click", function (e) {
      if (e.target.closest(".cev-confirm-yes")) { close(true); }
      else if (e.target.closest(".cev-confirm-no") || e.target === box) { close(false); }  // outside: the backdrop
    });
    box.addEventListener("cancel", function (e) { e.preventDefault(); close(false); });  // Escape
    document.body.appendChild(box);
    box.showModal();
    box.querySelector(".cev-confirm-no").focus();  // Enter does not remove by mistake
  };

  // The same box for a message (one button "OK") and for a text to type (OK / Annuler), instead of the
  // boxes of the browser (11/11, the charter). CEV.prompt gives a Promise of the text (null: cancelled).
  function box(html) {
    var b = document.createElement("dialog");
    b.className = "cev-confirm";
    b.innerHTML = '<div class="cev-confirm-in"><p class="cev-confirm-text"></p>' + html + "</div>";
    document.body.appendChild(b);
    return b;
  }
  window.CEV.alert = function (text) {
    var b = box('<div class="cev-confirm-buttons"><button type="button" class="cev-confirm-yes"></button></div>');
    b.querySelector(".cev-confirm-text").textContent = text;
    b.querySelector(".cev-confirm-yes").textContent = CEV.t("web.confirm.ok");
    var close = function () { b.close(); b.remove(); };
    b.addEventListener("click", function (e) { if (e.target.closest(".cev-confirm-yes") || e.target === b) { close(); } });
    b.addEventListener("cancel", function (e) { e.preventDefault(); close(); });
    b.showModal();
    b.querySelector(".cev-confirm-yes").focus();
  };
  // A question with several answers (21/11: the date of an import): done(index of the button), or done(null) for
  // Escape or a click outside; the last button gets the focus (the safe answer goes last).
  window.CEV.choose = function (text, labels, done) {
    var b = box('<div class="cev-confirm-buttons"></div>');
    b.querySelector(".cev-confirm-text").textContent = text;
    var row = b.querySelector(".cev-confirm-buttons"), over = false;
    labels.forEach(function (label, k) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = k === labels.length - 1 ? "cev-confirm-no" : "cev-confirm-yes";
      btn.textContent = label;
      btn.dataset.k = String(k);
      row.appendChild(btn);
    });
    var close = function (k) { if (over) { return; } over = true; b.close(); b.remove(); done(k); };
    b.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-k]");
      if (btn) { close(Number(btn.dataset.k)); } else if (e.target === b) { close(null); }
    });
    b.addEventListener("cancel", function (e) { e.preventDefault(); close(null); });
    b.showModal();
    row.lastChild.focus();
  };
  window.CEV.prompt = function (text, value) {
    return new Promise(function (resolve) {
      var b = box('<input type="text" class="cev-confirm-input" spellcheck="false"><div class="cev-confirm-buttons">' +
        '<button type="button" class="cev-confirm-yes"></button><button type="button" class="cev-confirm-no"></button></div>');
      var input = b.querySelector(".cev-confirm-input");
      b.querySelector(".cev-confirm-text").textContent = text;
      b.querySelector(".cev-confirm-yes").textContent = CEV.t("web.confirm.ok");
      b.querySelector(".cev-confirm-no").textContent = CEV.t("web.downloads.cancel");
      input.value = value || "";
      var done = false;
      var close = function (v) { if (done) { return; } done = true; b.close(); b.remove(); resolve(v); };
      b.addEventListener("click", function (e) {
        if (e.target.closest(".cev-confirm-yes")) { close(input.value.trim() || null); }
        else if (e.target.closest(".cev-confirm-no") || e.target === b) { close(null); }
      });
      input.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); close(input.value.trim() || null); } });
      b.addEventListener("cancel", function (e) { e.preventDefault(); close(null); });
      b.showModal();
      input.focus();
    });
  };
})();
