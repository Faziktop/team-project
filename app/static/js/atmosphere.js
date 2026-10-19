/**
 * Атмосферные эффекты публичной витрины: фонарик курсора, скролл-ривил,
 * параллакс фото. Полностью отключаются при prefers-reduced-motion.
 */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // --- Фонарик курсора -----------------------------------------------------
  var flashlight = document.getElementById("qe-flashlight");
  if (flashlight && !reduceMotion && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    window.addEventListener("mousemove", function (e) {
      flashlight.style.setProperty("--mx", e.clientX + "px");
      flashlight.style.setProperty("--my", e.clientY + "px");
      flashlight.classList.add("qe-active");
    }, { passive: true });
    window.addEventListener("mouseleave", function () {
      flashlight.classList.remove("qe-active");
    });
  }

  // --- Скролл-ривил (появление элементов при прокрутке) --------------------
  // Элементы видны по умолчанию (см. CSS); скрываем их самостоятельно только
  // непосредственно перед постановкой на наблюдение — если что-то в этой
  // цепочке не сработает, контент просто останется видимым, а не пропадёт.
  var revealEls = document.querySelectorAll(".qe-reveal");
  if (revealEls.length && !reduceMotion && "IntersectionObserver" in window) {
    revealEls.forEach(function (el, i) {
      el.style.transitionDelay = (i % 6) * 0.08 + "s";
      el.classList.add("qe-reveal-pending");
    });
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.remove("qe-reveal-pending");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15, rootMargin: "0px 0px -40px 0px" });
    revealEls.forEach(function (el) { observer.observe(el); });
  }

  // --- Параллакс фото при скролле ------------------------------------------
  var parallaxEls = document.querySelectorAll("[data-parallax]");
  if (parallaxEls.length && !reduceMotion) {
    var ticking = false;
    function updateParallax() {
      var vh = window.innerHeight;
      parallaxEls.forEach(function (el) {
        var speed = parseFloat(el.getAttribute("data-parallax")) || 0.15;
        var rect = el.parentElement.getBoundingClientRect();
        var offset = (rect.top + rect.height / 2 - vh / 2) * speed;
        el.style.transform = "translate3d(0, " + offset.toFixed(1) + "px, 0)";
      });
      ticking = false;
    }
    window.addEventListener("scroll", function () {
      if (!ticking) {
        window.requestAnimationFrame(updateParallax);
        ticking = true;
      }
    }, { passive: true });
    updateParallax();
  }
})();
