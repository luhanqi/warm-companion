(function (global) {
  var authState = null;
  var consentScopes = null;

  if (location.protocol === "file:") {
    var localPage = location.pathname.split("/").pop() || "login.html";
    location.replace("http://127.0.0.1:8002/" + localPage + location.search + location.hash);
    return;
  }

  function apiRoot() {
    return "";
  }

  function readAuth() {
    return authState;
  }

  function writeAuth(session) {
    authState = session || null;
  }

  function request(path, init, timeoutMs) {
    init = init || {};
    timeoutMs = timeoutMs || 8000;
    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort();
    }, timeoutMs);
    var headers = {};
    if (init.body && !(init.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    if (init.headers) {
      Object.keys(init.headers).forEach(function (key) {
        headers[key] = init.headers[key];
      });
    }
    return fetch(apiRoot() + path, {
      method: init.method || "GET",
      body: init.body,
      headers: headers,
      signal: controller.signal,
      credentials: "include",
    }).then(function (response) {
      if (!response.ok) {
        return response
          .json()
          .catch(function () {
            return {};
          })
          .then(function (body) {
            throw new Error(body.detail || "服务暂时没有响应，请稍后再试");
          });
      }
      return response.json();
    }).finally(function () {
      clearTimeout(timer);
    });
  }

  function streamChat(text, onEvent) {
    var headers = { "Content-Type": "application/json" };
    return fetch(apiRoot() + "/api/chat", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({ text: text }),
      credentials: "include",
    }).then(function (response) {
      if (!response.ok || !response.body) {
        throw new Error("暖伴这会儿接不上话，请再试一次");
      }
      var reader = response.body.getReader();
      var decoder = new TextDecoder("utf-8");
      var buffer = "";
      function pump() {
        return reader.read().then(function (result) {
          if (result.done) return;
          buffer += decoder.decode(result.value, { stream: true });
          var chunks = buffer.split("\n\n");
          buffer = chunks.pop() || "";
          chunks.forEach(function (chunk) {
            var line = chunk
              .split("\n")
              .filter(function (item) {
                return item.indexOf("data:") === 0;
              })
              .map(function (item) {
                return item.slice(5).trim();
              })
              .join("");
            if (line) onEvent(JSON.parse(line));
          });
          return pump();
        });
      }
      return pump();
    });
  }

  function uploadPhoto(file, caption) {
    var data = new FormData();
    data.append("file", file);
    data.append("caption", caption || "");
    return fetch(apiRoot() + "/api/photos", {
      method: "POST",
      body: data,
      credentials: "include",
    }).then(function (response) {
      if (!response.ok) throw new Error("照片没有传上去");
      return response.json();
    });
  }

  function uploadVoice(blob, transcript, durationMs, metrics) {
    metrics = metrics || {};
    var data = new FormData();
    data.append("file", blob, "conversation.webm");
    data.append("transcript", transcript || "");
    data.append("duration_ms", String(durationMs || 0));
    data.append("silence_ratio", String(metrics.silence_ratio || 0));
    data.append("pause_count", String(metrics.pause_count || 0));
    data.append("rms", String(metrics.rms || 0));
    data.append("peak", String(metrics.peak || 0));
    data.append("longest_pause_ms", String(metrics.longest_pause_ms || 0));
    data.append("speech_segments", String(metrics.speech_segments || 0));
    data.append("zero_crossing_rate", String(metrics.zero_crossing_rate || 0));
    data.append("response_latency_ms", String(metrics.response_latency_ms || 0));
    return request("/api/cognition/voice", { method: "POST", body: data }, 30000);
  }

  function fetchVoiceBlob(sessionId) {
    return fetch(apiRoot() + "/api/voice/" + sessionId, { credentials: "include" }).then(function (response) {
      if (!response.ok) throw new Error("录音暂时无法播放");
      return response.blob();
    });
  }

  function asset(url) {
    if (!url) return "";
    if (url.indexOf("http") === 0 || url.indexOf("blob:") === 0 || url.indexOf("data:") === 0) return url;
    return apiRoot() + url;
  }

  global.NB = {
    apiRoot: apiRoot,
    asset: asset,
    readAuth: readAuth,
    writeAuth: writeAuth,
    getConsentScopes: function () { return consentScopes || {}; },
    setConsentScopes: function (scopes) { consentScopes = scopes || {}; },
    request: request,
    streamChat: streamChat,
    pageCommand: function (page, text) {
      return request("/api/page-command", {
        method: "POST",
        body: JSON.stringify({ page: page, text: text }),
      }, 45000);
    },
    pageTalk: function (page, text, onEvent) {
      var headers = { "Content-Type": "application/json" };
      return fetch(apiRoot() + "/api/page-talk", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ page: page, text: text }),
        credentials: "include",
      }).then(function (response) {
        if (!response.ok || !response.body) {
          throw new Error("暖伴这会儿接不上话，请再试一次");
        }
        var reader = response.body.getReader();
        var decoder = new TextDecoder("utf-8");
        var buffer = "";
        function pump() {
          return reader.read().then(function (result) {
            if (result.done) return;
            buffer += decoder.decode(result.value, { stream: true });
            var chunks = buffer.split("\n\n");
            buffer = chunks.pop() || "";
            chunks.forEach(function (chunk) {
              var line = chunk
                .split("\n")
                .filter(function (item) {
                  return item.indexOf("data:") === 0;
                })
                .map(function (item) {
                  return item.slice(5).trim();
                })
                .join("");
              if (line) onEvent(JSON.parse(line));
            });
            return pump();
          });
        }
        return pump();
      });
    },
    uploadPhoto: uploadPhoto,
    uploadVoice: uploadVoice,
    fetchVoiceBlob: fetchVoiceBlob,
    synthesizeSpeech: function (text) {
      return fetch(apiRoot() + "/api/speech/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text }),
        credentials: "include",
      }).then(function (response) {
        if (!response.ok) throw new Error("个性音色暂时不可用");
        return response.blob();
      });
    },
    login: function (username, password) {
      return request("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: username, password: password }),
      });
    },
    register: function (username, password, role, elderUsername, linkCode) {
      return request("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          username: username,
          password: password,
          role: role,
          elder_username: elderUsername || "",
          link_code: linkCode || ""
        }),
      });
    },
    fetchFamilyLinkCode: function () {
      return request("/api/family/link-code");
    },
    rotateFamilyLinkCode: function () {
      return request("/api/family/link-code/rotate", { method: "POST" });
    },
    logout: function () {
      return request("/api/auth/logout", { method: "POST" }).catch(function () {
        return { ok: true };
      });
    },
    fetchMe: function () {
      return request("/api/auth/me").then(function (data) {
        writeAuth(data);
        return data;
      });
    },
    fetchSession: function () {
      return request("/api/session");
    },
    updateProfile: function (payload) {
      return request("/api/profile", { method: "PUT", body: JSON.stringify(payload) });
    },
    addPerson: function (payload) {
      return request("/api/people", { method: "POST", body: JSON.stringify(payload) });
    },
    deletePerson: function (id) {
      return request("/api/people/" + id, { method: "DELETE" });
    },
    updateFact: function (id, payload) {
      return request("/api/facts/" + id, { method: "PUT", body: JSON.stringify(payload) });
    },
    deleteFact: function (id) {
      return request("/api/facts/" + id, { method: "DELETE" });
    },
    playSong: function (songId) {
      return request("/api/heal/play", { method: "POST", body: JSON.stringify({ song_id: songId }) });
    },
    tellEra: function (year) {
      return request("/api/heal/era", { method: "POST", body: JSON.stringify({ year: year }) });
    },
    rememberStory: function (payload) {
      return request("/api/heal/remember", { method: "POST", body: JSON.stringify(payload) });
    },
    finishGame: function (game, score) {
      return request("/api/heal/game", { method: "POST", body: JSON.stringify({ game: game, score: score }) });
    },
    setMood: function (mood) {
      return request("/api/mood", { method: "POST", body: JSON.stringify({ mood: mood }) });
    },
    setConsent: function (share) {
      return request("/api/consent", { method: "POST", body: JSON.stringify({ share: share }) });
    },
    fetchConsentScopes: function () {
      return request("/api/consent/scopes").then(function (data) {
        consentScopes = data.scopes || {};
        return data;
      });
    },
    setConsentScope: function (scope, allowed) {
      return request("/api/consent/scopes", {
        method: "PUT",
        body: JSON.stringify({ scope: scope, allowed: allowed }),
      });
    },
    fetchCognitionTrend: function () {
      return request("/api/cognition/trends");
    },
    acknowledgeCognitionAlert: function (id) {
      return request("/api/cognition/alerts/" + id + "/ack", { method: "POST" });
    },
    fetchMemoryProjects: function () {
      return request("/api/memory-projects");
    },
    createMemoryProject: function (payload) {
      return request("/api/memory-projects", { method: "POST", body: JSON.stringify(payload) });
    },
    clearChapter: function (chapterKey) {
      return request("/api/chapters/" + encodeURIComponent(chapterKey), { method: "DELETE" });
    },
    fetchGarden: function () {
      return request("/api/garden");
    },
    saveGardenState: function (flowers) {
      return request("/api/garden/state", { method: "PUT", body: JSON.stringify({ flowers: flowers }) });
    },
    fetchPreferences: function () {
      return request("/api/preferences");
    },
    savePreference: function (key, value) {
      return request("/api/preferences", { method: "PUT", body: JSON.stringify({ key: key, value: value }) });
    },
    uploadProfilePhoto: function (file) {
      var data = new FormData();
      data.append("file", file);
      return request("/api/profile/photo", { method: "POST", body: data }, 30000);
    },
    uploadPersonPhoto: function (personId, file) {
      var data = new FormData();
      data.append("file", file);
      return request("/api/people/" + personId + "/photo", { method: "POST", body: data }, 30000);
    },
    fetchFamilyDigest: function () {
      return request("/api/family/digest");
    },
    fetchFamilyCare: function () {
      return request("/api/family/care");
    },
    saveFamilyNote: function (text) {
      return request("/api/family/note", { method: "POST", body: JSON.stringify({ text: text }) });
    },
    clearFamilyNote: function () {
      return request("/api/family/note", { method: "DELETE" });
    },
    fetchLife: function () {
      return request("/api/life");
    },
    fetchReminders: function () {
      return request("/api/reminders");
    },
    addReminder: function (payload) {
      return request("/api/reminders", { method: "POST", body: JSON.stringify(payload) });
    },
    deleteReminder: function (id) {
      return request("/api/reminders/" + id, { method: "DELETE" });
    },
    fetchObserve: function () {
      return request("/api/observe");
    },
    runObserveEval: function () {
      return request("/api/observe/eval", { method: "POST" });
    },
    fetchPaintStyles: function () {
      return request("/api/paint/styles");
    },
    fetchPaintings: function () {
      return request("/api/paintings");
    },
    paintScene: function (prompt, style, extra) {
      extra = extra || {};
      return request("/api/paint", {
        method: "POST",
        body: JSON.stringify({
          prompt: prompt,
          style: style,
          from_name: extra.from_name || "",
          dedication: extra.dedication || "",
        }),
      }, 120000);
    },
  };
})(window);
