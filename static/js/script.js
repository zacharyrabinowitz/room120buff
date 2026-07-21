document.addEventListener("DOMContentLoaded", () => {
  const toggleBtn = document.querySelector(".nav-toggle");
  const navList = document.querySelector(".nav-list");

  if (toggleBtn && navList) {
    toggleBtn.addEventListener("click", () => {
      const expanded = toggleBtn.getAttribute("aria-expanded") === "true";
      toggleBtn.setAttribute("aria-expanded", String(!expanded));
      navList.classList.toggle("open");
    });

    navList.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        navList.classList.remove("open");
        toggleBtn.setAttribute("aria-expanded", "false");
      });
    });
  }

  const yearEl = document.getElementById("year");
  if (yearEl) {
    yearEl.textContent = String(new Date().getFullYear());
  }

  const galleryOverlay = document.getElementById("gallery-overlay");
  const galleryImage = document.getElementById("gallery-image");
  const closeButton = document.getElementById("gallery-close");
  const galleryItems = document.querySelectorAll(".gallery-item");

  if (galleryOverlay && galleryImage && closeButton && galleryItems.length > 0) {
    const closeGallery = () => {
      galleryOverlay.classList.remove("open");
      galleryImage.removeAttribute("src");
    };

    galleryItems.forEach((item) => {
      item.addEventListener("click", (event) => {
        event.preventDefault();
        const img = item.querySelector("img");
        const src = item.getAttribute("href") || (img ? img.src : "");
        if (!src) {
          return;
        }
        galleryImage.src = src;
        galleryOverlay.classList.add("open");
      });
    });

    closeButton.addEventListener("click", closeGallery);

    galleryOverlay.addEventListener("click", (event) => {
      if (event.target === galleryOverlay) {
        closeGallery();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && galleryOverlay.classList.contains("open")) {
        closeGallery();
      }
    });
  }
});
