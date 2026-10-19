/**
 * Recipe Collection - Step-by-Step Cooking Mode Engine
 * Dedicated distraction-free cooking assistant with progress tracking and Web Audio chime timer.
 */

document.addEventListener('DOMContentLoaded', () => {
  initCookingMode();
});

function initCookingMode() {
  const steps = document.querySelectorAll('.cooking-step-container');
  if (!steps.length) return;

  let currentStepIdx = 0;
  const totalSteps = steps.length;
  const progressFill = document.querySelector('.cooking-progress-fill');
  const prevBtn = document.getElementById('cookPrevBtn');
  const nextBtn = document.getElementById('cookNextBtn');
  const currentStepNum = document.getElementById('cookStepNum');

  // Timer elements
  let timerInterval = null;
  let remainingSeconds = 0;
  let isTimerRunning = false;
  const timerClock = document.getElementById('timerClock');
  const timerToggleBtn = document.getElementById('timerToggleBtn');
  const timerResetBtn = document.getElementById('timerResetBtn');

  function showStep(index) {
    steps.forEach((step, idx) => {
      step.style.display = idx === index ? 'block' : 'none';
    });

    currentStepIdx = index;
    if (currentStepNum) currentStepNum.textContent = index + 1;
    if (progressFill) {
      progressFill.style.width = `${((index + 1) / totalSteps) * 100}%`;
    }

    if (prevBtn) {
      prevBtn.disabled = index === 0;
      prevBtn.style.opacity = index === 0 ? '0.4' : '1';
    }

    if (nextBtn) {
      if (index === totalSteps - 1) {
        nextBtn.innerHTML = '<i class="fas fa-check"></i> Завершить';
        nextBtn.classList.remove('btn-primary');
        nextBtn.classList.add('btn-success');
      } else {
        nextBtn.innerHTML = 'Далее <i class="fas fa-arrow-right"></i>';
        nextBtn.classList.remove('btn-success');
        nextBtn.classList.add('btn-primary');
      }
    }

    // Initialize timer for current step if present
    clearInterval(timerInterval);
    isTimerRunning = false;
    const currentStepEl = steps[index];
    const detectedSeconds = parseInt(currentStepEl.dataset.timerSeconds) || 0;
    const timerWidget = document.querySelector('.cooking-timer-widget');

    if (detectedSeconds > 0) {
      if (timerWidget) timerWidget.style.display = 'flex';
      remainingSeconds = detectedSeconds;
      updateTimerDisplay();
      if (timerToggleBtn) {
        timerToggleBtn.innerHTML = '<i class="fas fa-play"></i> Старт';
      }
    } else {
      if (timerWidget) timerWidget.style.display = 'none';
    }
  }

  function updateTimerDisplay() {
    if (!timerClock) return;
    const m = Math.floor(remainingSeconds / 60);
    const s = remainingSeconds % 60;
    timerClock.textContent = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }

  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      if (currentStepIdx > 0) showStep(currentStepIdx - 1);
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      if (currentStepIdx < totalSteps - 1) {
        showStep(currentStepIdx + 1);
      } else {
        // Completed
        playChime();
        alert('🎉 Поздравляем! Вы завершили приготовление блюда. Приятного аппетита!');
        window.history.back();
      }
    });
  }

  // Keyboard Navigation: Arrow Left/Right
  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' && currentStepIdx < totalSteps - 1) {
      showStep(currentStepIdx + 1);
    } else if (e.key === 'ArrowLeft' && currentStepIdx > 0) {
      showStep(currentStepIdx - 1);
    }
  });

  // Timer controls
  if (timerToggleBtn) {
    timerToggleBtn.addEventListener('click', () => {
      if (isTimerRunning) {
        clearInterval(timerInterval);
        isTimerRunning = false;
        timerToggleBtn.innerHTML = '<i class="fas fa-play"></i> Продолжить';
      } else {
        isTimerRunning = true;
        timerToggleBtn.innerHTML = '<i class="fas fa-pause"></i> Пауза';
        timerInterval = setInterval(() => {
          if (remainingSeconds > 0) {
            remainingSeconds--;
            updateTimerDisplay();
          } else {
            clearInterval(timerInterval);
            isTimerRunning = false;
            playChime();
            timerToggleBtn.innerHTML = '<i class="fas fa-redo"></i> Готово!';
            timerClock.style.color = '#EF4444';
            setTimeout(() => {
              if (timerClock) timerClock.style.color = '';
            }, 5000);
          }
        }, 1000);
      }
    });
  }

  if (timerResetBtn) {
    timerResetBtn.addEventListener('click', () => {
      clearInterval(timerInterval);
      isTimerRunning = false;
      const currentStepEl = steps[currentStepIdx];
      remainingSeconds = parseInt(currentStepEl.dataset.timerSeconds) || 0;
      updateTimerDisplay();
      if (timerToggleBtn) timerToggleBtn.innerHTML = '<i class="fas fa-play"></i> Старт';
    });
  }

  // Initial step display
  showStep(0);
}

/**
 * Web Audio API synthesized culinary bell chime.
 * Crisp, pleasant chime sound without any external audio file dependencies.
 */
function playChime() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();

    // Notes of a pleasant major chime (C5, G5, C6)
    const freqs = [523.25, 783.99, 1046.50];
    freqs.forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, ctx.currentTime + idx * 0.12);

      gain.gain.setValueAtTime(0.001, ctx.currentTime + idx * 0.12);
      gain.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + idx * 0.12 + 0.04);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + idx * 0.12 + 1.2);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(ctx.currentTime + idx * 0.12);
      osc.stop(ctx.currentTime + idx * 0.12 + 1.3);
    });
  } catch (err) {
    console.warn('Audio chime unsupported or blocked:', err);
  }
}
