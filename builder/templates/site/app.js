// Small, dependency-free behaviour for the website: mobile menu, fade-in on scroll, and forms.
(function () {
  var yr = document.getElementById("yr");
  if (yr) yr.textContent = new Date().getFullYear();

  var btn = document.querySelector(".menu-btn"), nav = document.getElementById("nav");
  if (btn && nav) {
    btn.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  var items = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { threshold: 0.12 });
    items.forEach(function (el) { io.observe(el); });
  } else {
    items.forEach(function (el) { el.classList.add("in"); });
  }

  // Forms: open the visitor's email app addressed to the site owner (no server needed).
  // To receive forms in a dashboard instead, set the form's action to a form service address.
  var form = document.getElementById("form");
  if (form) {
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var data = new FormData(form), lines = [];
      data.forEach(function (v, k) { lines.push(k + ": " + v); });
      var to = form.getAttribute("data-mail");
      var ok = document.getElementById("ok");
      if (to) {
        location.href = "mailto:" + to + "?subject=" + encodeURIComponent(form.getAttribute("data-subject") || "Website form") +
          "&body=" + encodeURIComponent(lines.join("\n"));
      }
      if (ok) { ok.hidden = false; ok.focus && ok.focus(); }
      form.reset();
    });
  }
})();
