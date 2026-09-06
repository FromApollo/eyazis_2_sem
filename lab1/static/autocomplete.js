(function () {
  function debounce(fn, delay) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  function setupAutocomplete(input) {
    // Wrap the input so the suggestion dropdown can be positioned under it.
    const wrapper = document.createElement("div");
    wrapper.className = "position-relative";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const list = document.createElement("div");
    list.className = "list-group position-absolute w-100 shadow-sm";
    list.style.zIndex = 1050;
    list.style.display = "none";
    list.style.maxHeight = "240px";
    list.style.overflowY = "auto";
    wrapper.appendChild(list);

    function hide() {
      list.style.display = "none";
      list.innerHTML = "";
    }

    const fetchSuggestions = debounce(function () {
      const q = input.value.trim();
      if (q.length < 2) {
        hide();
        return;
      }
      fetch("/api/suggest?q=" + encodeURIComponent(q))
        .then((r) => (r.ok ? r.json() : []))
        .then((items) => {
          if (!items || !items.length) {
            hide();
            return;
          }
          list.innerHTML = "";
          items.forEach(function (text) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "list-group-item list-group-item-action py-1";
            btn.textContent = text;
            btn.addEventListener("mousedown", function (e) {
              // mousedown (not click) fires before the input's blur handler
              e.preventDefault();
              input.value = text;
              hide();
              if (input.form) {
                if (input.form.requestSubmit) input.form.requestSubmit();
                else input.form.submit();
              }
            });
            list.appendChild(btn);
          });
          list.style.display = "block";
        })
        .catch(() => hide());
    }, 200);

    input.addEventListener("input", fetchSuggestions);
    input.addEventListener("blur", function () {
      setTimeout(hide, 150);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") hide();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".js-search-input").forEach(setupAutocomplete);
  });
})();
