/* A very long conversation shown in several pages (step 4 of the reading in pieces, 21/11): window.CEV_PARTS =
 * {map, pages, part} is written by the page of each part. A link #msg=<uuid> to a message that is not on this page
 * (favorites, notes, the search of the index) loads the map of the parts (<name>.parties.js, read only then) and goes
 * to the page holding that message, with the same link. */
(function () {
  "use strict";
  var conf = window.CEV_PARTS;
  if (!conf) { return; }
  function go() {
    var id = (location.hash.match(/^#msg=([\w-]+)$/) || [])[1];
    if (!id || document.querySelector('.message[data-uuid="' + id + '"]')) { return; }
    var jump = function () {
      var part = window.CEV_PART_OF && window.CEV_PART_OF[id];
      if (typeof part === "number" && part !== conf.part && conf.pages[part]) { location.replace(conf.pages[part] + location.hash); }
    };
    if (window.CEV_PART_OF) { jump(); return; }
    var s = document.createElement("script");
    s.src = conf.map;
    s.onload = jump;
    document.head.appendChild(s);
  }
  go();
  window.addEventListener("hashchange", go);
})();
