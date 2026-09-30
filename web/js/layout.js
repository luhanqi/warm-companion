(function (global) {
  var ELDER_LINKS = [
    ["talk.html", "说话"],
    ["nostalgia.html", "怀旧"],
    ["memoir.html", "回忆录"],
    ["garden.html", "花园"],
    ["life.html", "生活"],
    ["paint.html", "作画"],
    ["profile.html", "资料"],
  ];
  var FAMILY_LINKS = [
    ["family.html", "周报"],
    ["care.html", "照料"],
    ["gift.html", "寄画"],
    ["observe.html", "观察台"],
  ];

  function pageName() {
    var name = (location.pathname.split("/").pop() || "login.html").split("?")[0];
    if (!name) name = "login.html";
    if (name.indexOf(".") < 0) name += ".html";
    return name;
  }

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderTopbar(user) {
    var family = user && user.role === "family";
    var current = pageName();
    var links = family ? FAMILY_LINKS.slice() : ELDER_LINKS.slice();
    var html =
      '<a href="' +
      (family ? "family.html" : "talk.html") +
      '" class="brand"><span class="brand-mark">暖</span><span>' +
      '<div class="brand-name">暖伴</div><div class="brand-sub">' +
      (family ? "家人照料 · 不含原文" : "会说话 · 会记住 · 能帮忙") +
      "</div></span></a><nav class=\"top-links\">";
    links.forEach(function (item) {
      html +=
        '<a href="' +
        item[0] +
        '" class="top-link' +
        (current === item[0] ? " active" : "") +
        '">' +
        item[1] +
        "</a>";
    });
    html += '<button type="button" class="top-link" data-logout>离开</button></nav>';
    var bar = document.getElementById("topbar");
    if (bar) bar.innerHTML = html;
    var btn = document.querySelector("[data-logout]");
    if (btn) {
      btn.addEventListener("click", function () {
        NB.logout().finally(function () {
          NB.writeAuth(null);
          location.href = "login.html";
        });
      });
    }
  }

  function requireRole(role) {
    return NB.fetchMe()
      .then(function (data) {
        var next = data;
        NB.writeAuth(next);
        if (role && next.role !== role) {
          location.replace(next.role === "family" ? "family.html" : "talk.html");
          return null;
        }
        renderTopbar(next);
        if (next.role === "elder" && NB.fetchConsentScopes) {
          return NB.fetchConsentScopes().then(function (payload) {
            NB.setConsentScopes(payload.scopes || {});
            return next;
          }).catch(function () { return next; });
        }
        return next;
      })
      .catch(function () {
        NB.writeAuth(null);
        location.replace("login.html?role=" + (role || "elder"));
        return null;
      });
  }

  function publicTopbar(sub, extra) {
    var bar = document.getElementById("topbar");
    if (!bar) return;
    bar.innerHTML =
      '<a href="login.html" class="brand"><span class="brand-mark">暖</span><span>' +
      '<div class="brand-name">暖伴</div><div class="brand-sub">' +
      esc(sub || "第四阶段") +
      "</div></span></a><nav class=\"top-links\">" +
      (extra === undefined ? '<a href="login.html" class="top-link">登录</a>' : extra) +
      "</nav>";
  }

  global.NBLayout = {
    esc: esc,
    pageName: pageName,
    renderTopbar: renderTopbar,
    requireRole: requireRole,
    publicTopbar: publicTopbar,
  };
})(window);
