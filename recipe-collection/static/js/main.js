/**
 * Recipe Collection - Main Interactive Engine
 * Handles Themes, AJAX Favorites, Servings Scaler, Toasts, Shopping List
 */

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initUserDropdown();
  initMobileMenu();
  initFavorites();
  initServingsScaler();
  initGallery();
  initStarRating();
  initShareButton();
  initIngredientChecklist();
  initDropzone();
  initAutoDismissToasts();
});

/* ==================== 1. THEME SWITCHER ==================== */
function initTheme() {
  const toggleBtn = document.getElementById('themeToggleBtn');
  const storedTheme = localStorage.getItem('recipe_theme');
  const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  
  const currentTheme = storedTheme || (systemPrefersDark ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', currentTheme);
  updateThemeIcon(currentTheme);

  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const activeTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', activeTheme);
      localStorage.setItem('recipe_theme', activeTheme);
      updateThemeIcon(activeTheme);
      showToast(`Включена ${activeTheme === 'dark' ? 'тёмная' : 'светлая'} тема`, 'info');
    });
  }
}

function updateThemeIcon(theme) {
  const icon = document.querySelector('#themeToggleBtn i');
  if (icon) {
    icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
  }
}

/* ==================== 2. USER DROPDOWN & MOBILE MENU ==================== */
function initUserDropdown() {
  const dropdown = document.querySelector('.user-dropdown');
  const btn = document.querySelector('.user-profile-btn');

  if (btn && dropdown) {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    });

    document.addEventListener('click', () => {
      dropdown.classList.remove('open');
    });
  }
}

function initMobileMenu() {
  const toggle = document.querySelector('.mobile-toggle');
  const menu = document.querySelector('.nav-menu');

  if (toggle && menu) {
    toggle.addEventListener('click', () => {
      menu.classList.toggle('mobile-open');
    });
  }
}

/* ==================== 3. TOAST NOTIFICATIONS ==================== */
function showToast(message, type = 'info') {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  let icon = 'info-circle';
  if (type === 'success') icon = 'check-circle';
  if (type === 'error') icon = 'exclamation-circle';

  toast.innerHTML = `
    <i class="fas fa-${icon}"></i>
    <span>${message}</span>
    <button class="toast-close">&times;</button>
  `;

  container.appendChild(toast);

  toast.querySelector('.toast-close').addEventListener('click', () => {
    toast.remove();
  });

  setTimeout(() => {
    if (toast.parentElement) {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(40px)';
      setTimeout(() => toast.remove(), 300);
    }
  }, 4000);
}

function initAutoDismissToasts() {
  document.querySelectorAll('.toast').forEach(toast => {
    const closeBtn = toast.querySelector('.toast-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => toast.remove());
    }
    setTimeout(() => {
      if (toast.parentElement) {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(40px)';
        setTimeout(() => toast.remove(), 300);
      }
    }, 4500);
  });
}

/* ==================== 4. AJAX FAVORITES ==================== */
function initFavorites() {
  document.querySelectorAll('.fav-toggle-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();

      const recipeId = btn.dataset.recipeId;
      if (!recipeId) return;

      try {
        const response = await fetch(`/recipe/${recipeId}/favorite`, {
          method: 'POST',
          headers: {
            'X-Requested-With': 'XMLHttpRequest'
          }
        });

        if (response.redirected) {
          window.location.href = response.url;
          return;
        }

        const data = await response.json();
        if (data.status === 'success') {
          btn.classList.toggle('active', data.is_favorite);
          const icon = btn.querySelector('i');
          if (icon) {
            icon.className = data.is_favorite ? 'fas fa-heart' : 'far fa-heart';
          }
          const countSpan = btn.querySelector('.fav-count');
          if (countSpan) {
            countSpan.textContent = data.count;
          }

          // Update header count if present
          const headerBadge = document.querySelector('.favorites-badge-count');
          if (headerBadge) {
            let count = parseInt(headerBadge.textContent) || 0;
            count = data.is_favorite ? count + 1 : Math.max(0, count - 1);
            headerBadge.textContent = count;
          }

          showToast(data.message, data.is_favorite ? 'success' : 'info');
        }
      } catch (err) {
        console.error('Error toggling favorite:', err);
      }
    });
  });
}

/* ==================== 5. DYNAMIC SERVINGS SCALER ==================== */
function initServingsScaler() {
  const scalerContainer = document.querySelector('.servings-scaler');
  if (!scalerContainer) return;

  const baseServings = parseInt(scalerContainer.dataset.baseServings) || 4;
  let currentServings = baseServings;
  const display = scalerContainer.querySelector('.servings-display');
  const decreaseBtn = scalerContainer.querySelector('.scaler-decrease');
  const increaseBtn = scalerContainer.querySelector('.scaler-increase');

  function updateQuantities() {
    display.textContent = `${currentServings} ${getServingsNoun(currentServings)}`;
    const factor = currentServings / baseServings;

    document.querySelectorAll('.ingredient-amount').forEach(el => {
      const baseAmt = parseFloat(el.dataset.baseAmount);
      if (!isNaN(baseAmt)) {
        const scaledAmt = baseAmt * factor;
        el.textContent = formatQuantity(scaledAmt);
      }
    });
  }

  if (decreaseBtn) {
    decreaseBtn.addEventListener('click', () => {
      if (currentServings > 1) {
        currentServings--;
        updateQuantities();
      }
    });
  }

  if (increaseBtn) {
    increaseBtn.addEventListener('click', () => {
      if (currentServings < 24) {
        currentServings++;
        updateQuantities();
      }
    });
  }
}

function formatQuantity(num) {
  if (Math.abs(num - Math.round(num)) < 0.05) {
    return Math.round(num).toString();
  }
  return num.toFixed(1).replace('.0', '');
}

function getServingsNoun(number) {
  const n = Math.abs(number) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return 'порций';
  if (n1 > 1 && n1 < 5) return 'порции';
  if (n1 === 1) return 'порция';
  return 'порций';
}

/* ==================== 6. GALLERY THUMBNAILS ==================== */
function initGallery() {
  const mainImg = document.getElementById('galleryMainImage');
  const thumbs = document.querySelectorAll('.gallery-thumb');

  thumbs.forEach(thumb => {
    thumb.addEventListener('click', () => {
      thumbs.forEach(t => t.classList.remove('active'));
      thumb.classList.add('active');
      if (mainImg) {
        mainImg.src = thumb.dataset.fullSrc;
      }
    });
  });
}

/* ==================== 7. STAR RATING SELECTOR ==================== */
function initStarRating() {
  const container = document.querySelector('.star-rating-select');
  if (!container) return;

  const stars = container.querySelectorAll('.star');
  const input = document.getElementById('ratingInput');

  stars.forEach((star, idx) => {
    star.addEventListener('mouseenter', () => {
      stars.forEach((s, i) => {
        s.classList.toggle('hovered', i <= idx);
      });
    });

    star.addEventListener('mouseleave', () => {
      stars.forEach(s => s.classList.remove('hovered'));
    });

    star.addEventListener('click', () => {
      const val = idx + 1;
      if (input) input.value = val;
      stars.forEach((s, i) => {
        s.classList.toggle('selected', i < val);
      });
    });
  });
}

/* ==================== 8. SHARE RECIPE ==================== */
function initShareButton() {
  const shareBtn = document.getElementById('shareRecipeBtn');
  if (!shareBtn) return;

  shareBtn.addEventListener('click', async () => {
    const title = document.title;
    const url = window.location.href;

    if (navigator.share) {
      try {
        await navigator.share({ title, url });
        return;
      } catch (err) {
        // Fallback to clipboard
      }
    }

    try {
      await navigator.clipboard.writeText(url);
      showToast('Ссылка на рецепт скопирована в буфер обмена!', 'success');
    } catch (err) {
      showToast('Не удалось скопировать ссылку', 'error');
    }
  });
}

/* ==================== 9. INGREDIENT CHECKLIST ==================== */
function initIngredientChecklist() {
  document.querySelectorAll('.ingredient-checkbox').forEach(cb => {
    cb.addEventListener('change', () => {
      const item = cb.closest('.ingredient-item');
      if (item) {
        item.classList.toggle('checked', cb.checked);
      }
    });
  });

  // Add to Shopping List button
  const addToListBtn = document.getElementById('addIngredientsToShoppingList');
  if (addToListBtn) {
    addToListBtn.addEventListener('click', () => {
      const items = [];
      document.querySelectorAll('.ingredient-item').forEach(el => {
        const cb = el.querySelector('.ingredient-checkbox');
        // Add unchecked items (the ones user still needs to buy)
        if (!cb || !cb.checked) {
          const text = el.querySelector('.ingredient-text').textContent.trim();
          if (text) items.push(text);
        }
      });

      if (items.length === 0) {
        showToast('Все ингредиенты уже отмечены как имеющиеся!', 'info');
        return;
      }

      let currentList = [];
      try {
        currentList = JSON.parse(localStorage.getItem('recipe_shopping_list') || '[]');
      } catch (e) {
        currentList = [];
      }

      const recipeTitle = document.querySelector('.recipe-hero-title')?.textContent.trim() || 'Рецепт';
      items.forEach(text => {
        currentList.push({
          id: Date.now() + Math.random().toString(36).substr(2, 5),
          text: text,
          recipe: recipeTitle,
          done: false
        });
      });

      localStorage.setItem('recipe_shopping_list', JSON.stringify(currentList));
      showToast(`Добавлено ${items.length} ингредиентов в Список покупок!`, 'success');
    });
  }
}

/* ==================== 10. DRAG & DROP FILE UPLOAD ==================== */
function initDropzone() {
  const dropzone = document.getElementById('imageDropzone');
  const fileInput = document.getElementById('imageInput');
  const previewGrid = document.getElementById('dropzonePreviewGrid');

  if (!dropzone || !fileInput) return;

  ['dragenter', 'dragover'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
    });
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    if (dt && dt.files.length) {
      fileInput.files = dt.files;
      renderPreviews(dt.files);
    }
  });

  dropzone.addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) {
      renderPreviews(fileInput.files);
    }
  });

  function renderPreviews(files) {
    if (!previewGrid) return;
    previewGrid.innerHTML = '';
    Array.from(files).forEach(file => {
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const img = document.createElement('img');
          img.src = e.target.result;
          img.className = 'preview-thumbnail';
          previewGrid.appendChild(img);
        };
        reader.readAsDataURL(file);
      }
    });
  }
}
