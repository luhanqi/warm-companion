(function (global) {
  function createHoldTalk(onSend, isBusy) {
    var state = "idle";
    var liveText = "";
    var hint = "";
    var startY = 0;
    var stopListen = null;
    var liveRef = "";
    var listeners = [];
    var pressTimer = null;
    var holdMode = false;

    function busy() {
      return typeof isBusy === "function" ? isBusy() : Boolean(isBusy);
    }

    function label() {
      if (state === "holding") return "松开发送";
      if (state === "cancel") return "松开取消";
      if (state === "listening") return "说完点这里";
      if (state === "thinking" || busy()) return "暖伴在听";
      return "点一下说话";
    }

    function notify() {
      listeners.forEach(function (fn) {
        fn({ state: state, liveText: liveText, hint: hint, label: label() });
      });
    }

    function startMic() {
      NBSpeech.stopSpeaking();
      liveRef = "";
      liveText = "";
      hint = "我在听。您说，说完再点一下。";
      if (!NBSpeech.canListen()) {
        hint = "这台浏览器不支持语音，请用文字";
        notify();
        return false;
      }
      stopListen = NBSpeech.startListening({
        onText: function (text) {
          liveRef = text;
          liveText = text;
          hint = "";
          notify();
        },
        onError: function (message) {
          if (state === "listening" || state === "holding") {
            hint = message;
            notify();
          }
        },
        onAudio: function (blob, durationMs, metrics, transcript) {
          if (global.NB && NB.uploadVoice && transcript) {
            NB.uploadVoice(blob, transcript, durationMs, metrics).catch(function () {});
          }
        },
      });
      return true;
    }

    function finish(send) {
      var text = (liveRef || "").trim();
      if (stopListen) stopListen(send && Boolean(text), text);
      stopListen = null;
      holdMode = false;
      state = "idle";
      if (send && text) {
        hint = "";
        liveText = "";
        liveRef = "";
        notify();
        onSend(text);
        return;
      }
      if (send) {
        hint = "我没听清。请再点一下，说完后再点一下发送。";
      } else {
        hint = "";
      }
      liveText = "";
      liveRef = "";
      notify();
    }

    function bindButton(button) {
      button.addEventListener("pointerdown", function (event) {
        if (busy()) return;
        event.preventDefault();
        button.setPointerCapture(event.pointerId);
        startY = event.clientY;
        if (state === "listening") return;
        pressTimer = setTimeout(function () {
          pressTimer = null;
          holdMode = true;
          if (startMic()) state = "holding";
          else {
            holdMode = false;
            state = "idle";
          }
          notify();
        }, 480);
      });
      button.addEventListener("pointermove", function (event) {
        if (state !== "holding" && state !== "cancel") return;
        state = startY - event.clientY > 70 ? "cancel" : "holding";
        notify();
      });
      function release() {
        if (pressTimer) {
          clearTimeout(pressTimer);
          pressTimer = null;
          if (state === "idle") {
            if (startMic()) state = "listening";
            notify();
          } else if (state === "listening") {
            finish(true);
          }
          return;
        }
        if (holdMode && (state === "holding" || state === "cancel")) {
          finish(state === "holding");
          return;
        }
        if (state === "listening") finish(true);
      }
      button.addEventListener("pointerup", release);
      button.addEventListener("pointercancel", function () {
        if (pressTimer) {
          clearTimeout(pressTimer);
          pressTimer = null;
        }
        if (state === "holding" || state === "cancel" || state === "listening") finish(false);
      });
    }

    return {
      bindButton: bindButton,
      abort: function () {
        if (pressTimer) {
          clearTimeout(pressTimer);
          pressTimer = null;
        }
        if (state === "listening" || state === "holding" || state === "cancel") finish(false);
      },
      onChange: function (fn) {
        listeners.push(fn);
      },
      snapshot: function () {
        return { state: state, liveText: liveText, hint: hint, label: label() };
      },
    };
  }

  var MIC_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.9V21h2v-3.1A7 7 0 0 0 19 11h-2z"/></svg>';
  var KEY_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 6h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2zm2 3h2v2H6V9zm3 0h2v2H9V9zm3 0h2v2h-2V9zm3 0h3v2h-3V9zM6 13h5v2H6v-2zm6 0h6v2h-6v-2z"/></svg>';
  var UP_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M7.4 15.4 12 10.8l4.6 4.6L18 14l-6-6-6 6z"/></svg>';
  var DOWN_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M7.4 8.6 12 13.2l4.6-4.6L18 10l-6 6-6-6z"/></svg>';

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function streamIntoPanel(page, text, panel) {
    var spoken = "";
    var pending = "";
    var talker = page && NB.pageTalk ? function (onEvent) {
      return NB.pageTalk(page, text, onEvent);
    } : function (onEvent) {
      return NB.streamChat(text, onEvent);
    };
    talker(function (event) {
      if (event.type === "token") {
        pending += event.text;
        panel.append(event.text);
        NBSpeech.splitSentences(pending.slice(spoken.length)).ready.forEach(function (sentence) {
          spoken += sentence;
          NBSpeech.speak(sentence, 0.82);
        });
      }
      if (event.type === "done") {
        var rest = pending.slice(spoken.length).trim();
        if (rest) NBSpeech.speak(rest, 0.82);
        panel.reply(pending || "我在。", { speak: false });
      }
      if (event.type === "error") {
        panel.reply(event.message || "这一句没有发出去", { speak: true });
      }
    }).catch(function (err) {
      panel.reply((err && err.message) || "这一句没有发出去", { speak: true });
    });
  }

  function renderDock(container, onSend, options) {
    options = options || {};
    var busyFn =
      options.busy ||
      function () {
        return false;
      };
    var placeholder = options.placeholder || "也可以在这里打字";
    var inlineReply = options.inlineReply !== false;
    var foldable = options.foldable !== false && inlineReply;
    var page = options.page || "";
    document.body.classList.add("has-talk-dock");
    document.body.classList.remove("talk-open");
    var host = document.getElementById("talk-dock-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "talk-dock-host";
      document.body.appendChild(host);
    }
    if (container && container !== host) container.setAttribute("hidden", "");
    host.innerHTML =
      '<div class="talk-shell collapsed" data-shell>' +
      '<div class="talk-composer">' +
      '<div class="talk-head">' +
      '<span class="talk-head-mark">暖</span>' +
      "<div><strong>暖伴</strong><small>说完，我帮您办</small></div>" +
      '<button type="button" class="talk-fold" data-shut aria-label="收起说话框">' +
      DOWN_ICON +
      "<span>收起</span></button></div>" +
      '<div class="talk-turn" data-turn hidden></div>' +
      '<div class="talk-live" data-live hidden></div>' +
      '<div class="talk-bar text" data-bar>' +
      '<button type="button" class="talk-switch" data-switch aria-label="切换到语音">' +
      MIC_ICON +
      "</button>" +
      '<form class="talk-text" data-form>' +
      '<input data-input placeholder="' +
      placeholder +
      '" />' +
      '<button type="submit">发送</button></form>' +
      '<button type="button" class="talk-hold idle" data-hold>' +
      '<span class="talk-hold-dot"></span><span data-hold-label>点一下说话</span></button>' +
      '<button type="button" class="talk-fold talk-open-btn" data-open aria-label="展开说话框">' +
      UP_ICON +
      "<span>展开</span></button>" +
      "</div></div></div>";

    var shell = host.querySelector("[data-shell]");
    var bar = host.querySelector("[data-bar]");
    var switchBtn = host.querySelector("[data-switch]");
    var holdBtn = host.querySelector("[data-hold]");
    var shutBtn = host.querySelector("[data-shut]");
    var openBtn = host.querySelector("[data-open]");
    var liveEl = host.querySelector("[data-live]");
    var form = host.querySelector("[data-form]");
    var input = host.querySelector("[data-input]");
    var turnEl = host.querySelector("[data-turn]");
    var mode = "text";
    var replyBuf = "";
    var turns = [];
    var expanded = false;

    function setFold(open) {
      if (!foldable) {
        expanded = false;
        shell.className = "talk-shell plain";
        document.body.classList.remove("talk-dock-expanded");
        return;
      }
      expanded = Boolean(open);
      shell.className = "talk-shell" + (expanded ? " expanded" : " collapsed");
      document.body.classList.toggle("talk-dock-expanded", expanded);
    }

    function paintLog() {
      if (!inlineReply) return;
      turnEl.hidden = false;
      if (!turns.length) {
        turnEl.innerHTML = '<p class="talk-empty">还没有说话。打字发给我，或点左边话筒。</p>';
        return;
      }
      turnEl.innerHTML = turns
        .map(function (item) {
          return (
            '<div class="talk-line ' +
            item.role +
            '"><i>' +
            (item.role === "you" ? "您" : "暖") +
            "</i><p>" +
            esc(item.text) +
            "</p></div>"
          );
        })
        .join("");
      turnEl.scrollTop = turnEl.scrollHeight;
    }

    function lastWarm() {
      var last = turns[turns.length - 1];
      if (!last || last.role !== "warm") {
        last = { role: "warm", text: "" };
        turns.push(last);
      }
      return last;
    }

    var panel = {
      echo: function (text) {
        if (!inlineReply) return;
        turns.push({ role: "you", text: text });
        turns.push({ role: "warm", text: "暖伴在听…" });
        if (turns.length > 16) turns = turns.slice(-16);
        replyBuf = "";
        paintLog();
      },
      thinking: function () {
        if (!inlineReply) return;
        lastWarm().text = "暖伴在听…";
        paintLog();
      },
      append: function (token) {
        if (!inlineReply) return;
        replyBuf += token;
        lastWarm().text = replyBuf;
        paintLog();
      },
      reply: function (text, opts) {
        opts = opts || {};
        if (inlineReply) {
          replyBuf = text || "";
          lastWarm().text = replyBuf || "我在。";
          paintLog();
        }
        if (opts.speak !== false && text) NBSpeech.speak(text);
      },
    };

    function applyCommand(value, cmd) {
      cmd = cmd || {};
      var kind = cmd.kind || (cmd.action && cmd.action !== "chat" ? "command" : "chat");
      if (kind === "command" && cmd.action && cmd.action !== "chat") {
        var handled = onSend(value, panel, cmd);
        if (handled === false) {
          panel.reply(cmd.reply || "这一页我办不了这件事。您换个说法，或跟我闲聊。", { speak: true });
          return;
        }
        var last = turns[turns.length - 1];
        if (cmd.reply && last && last.role === "warm" && (!replyBuf || last.text === "暖伴在听…")) {
          panel.reply(cmd.reply, { speak: true });
        }
        return;
      }
      if (page) {
        streamIntoPanel(page, value, panel);
        return;
      }
      onSend(value, panel, cmd);
    }

    function dispatch(text) {
      var value = (text || "").trim();
      if (!value || busyFn()) return;
      if (foldable) setFold(true);
      panel.echo(value);
      panel.thinking();
      if (!page) {
        onSend(value, panel, null);
        return;
      }
      if (typeof NB === "undefined" || !NB.pageCommand) {
        applyCommand(value, { action: "chat" });
        return;
      }
      NB.pageCommand(page, value)
        .then(function (cmd) {
          applyCommand(value, cmd || { action: "chat" });
        })
        .catch(function () {
          applyCommand(value, { action: "chat" });
        });
    }

    var talk = createHoldTalk(dispatch, busyFn);

    function setMode(next) {
      if (next === "text") talk.abort();
      mode = next;
      bar.className = "talk-bar " + mode;
      switchBtn.setAttribute("aria-label", mode === "text" ? "切换到语音" : "切换到打字");
      switchBtn.innerHTML = mode === "text" ? MIC_ICON : KEY_ICON;
      if (mode === "text") input.focus();
    }

    talk.bindButton(holdBtn);
    switchBtn.addEventListener("click", function () {
      if (busyFn()) return;
      setMode(mode === "text" ? "voice" : "text");
    });
    talk.onChange(function (snap) {
      holdBtn.className = "talk-hold " + snap.state + (busyFn() ? " thinking" : "");
      holdBtn.disabled = busyFn();
      switchBtn.disabled = busyFn();
      var holdLabel = holdBtn.querySelector("[data-hold-label]");
      if (holdLabel) holdLabel.textContent = snap.label;
      else holdBtn.textContent = snap.label;
      var shown = snap.liveText || snap.hint || "";
      if (snap.state === "listening") shown = snap.liveText || snap.hint || "我在听，说完再点一下";
      if (snap.state === "holding") shown = shown || "松手发送 · 上滑取消";
      if (snap.state === "cancel") shown = "松开取消";
      liveEl.textContent = shown;
      liveEl.hidden = !shown;
    });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var value = input.value.trim();
      input.value = "";
      dispatch(value);
    });
    shutBtn.addEventListener("click", function () {
      setFold(false);
    });
    openBtn.addEventListener("click", function () {
      setFold(true);
      if (mode === "text") input.focus();
    });
    setMode("text");
    liveEl.hidden = true;
    if (!foldable) {
      setFold(false);
    } else {
      setFold(true);
    }
    paintLog();
    panel.send = dispatch;
    return panel;
  }

  global.NBTalk = { createHoldTalk: createHoldTalk, renderDock: renderDock };
})(window);
