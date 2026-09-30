(function (global) {
  var personalAudio = null;
  var speechGeneration = 0;
  function recognitionCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function canListen() {
    return Boolean(recognitionCtor());
  }

  function audioCaptureAllowed() {
    var scopes = global.NB && NB.getConsentScopes ? NB.getConsentScopes() : {};
    return scopes.audio_storage === true;
  }

  function analyzeAudio(blob) {
    var AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return Promise.resolve({});
    var context = new AudioCtx();
    return blob.arrayBuffer().then(function (buffer) {
      return context.decodeAudioData(buffer.slice(0));
    }).then(function (audio) {
      var data = audio.getChannelData(0);
      var frameSize = Math.max(1, Math.round(audio.sampleRate * 0.02));
      var frames = [];
      var totalSquare = 0;
      var peak = 0;
      var crossings = 0;
      for (var i = 0; i < data.length; i += 1) {
        var absolute = Math.abs(data[i]);
        peak = Math.max(peak, absolute);
        totalSquare += data[i] * data[i];
        if (i > 0 && ((data[i - 1] < 0 && data[i] >= 0) || (data[i - 1] >= 0 && data[i] < 0))) crossings += 1;
      }
      var overallRms = Math.sqrt(totalSquare / Math.max(1, data.length));
      for (var start = 0; start < data.length; start += frameSize) {
        var end = Math.min(data.length, start + frameSize);
        var square = 0;
        for (var j = start; j < end; j += 1) square += data[j] * data[j];
        frames.push(Math.sqrt(square / Math.max(1, end - start)));
      }
      var threshold = Math.max(0.008, overallRms * 0.35);
      var silent = 0;
      var pauseCount = 0;
      var silentRun = 0;
      var longestSilentRun = 0;
      var speechSegments = 0;
      var speaking = false;
      frames.forEach(function (value) {
        if (value < threshold) {
          silent += 1;
          silentRun += 1;
          longestSilentRun = Math.max(longestSilentRun, silentRun);
          if (silentRun >= 5) speaking = false;
        } else {
          if (silentRun >= 15) pauseCount += 1;
          silentRun = 0;
          if (!speaking) speechSegments += 1;
          speaking = true;
        }
      });
      if (silentRun >= 15) pauseCount += 1;
      return {
        silence_ratio: Number((silent / Math.max(1, frames.length)).toFixed(4)),
        pause_count: pauseCount,
        rms: Number(overallRms.toFixed(6)),
        peak: Number(peak.toFixed(6)),
        longest_pause_ms: longestSilentRun * 20,
        speech_segments: speechSegments,
        zero_crossing_rate: Number((crossings / Math.max(1, data.length - 1)).toFixed(6)),
      };
    }).catch(function () {
      return {};
    }).finally(function () {
      if (context.close) context.close().catch(function () {});
    });
  }

  function startListening(handlers) {
    var Ctor = recognitionCtor();
    if (!Ctor) {
      if (handlers.onError) handlers.onError("这台电脑的浏览器还不支持语音，请用文字跟暖伴说");
      return function () {};
    }
    var recognition = new Ctor();
    var stopped = false;
    var keepRecording = false;
    var recordingTranscript = "";
    var recorder = null;
    var audioStream = null;
    var chunks = [];
    var recordStarted = 0;
    var recognitionStartedAt = Date.now();
    var firstSpeechAt = 0;
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = function (event) {
      if (!firstSpeechAt) firstSpeechAt = Date.now();
      var finals = "";
      var interim = "";
      for (var i = 0; i < event.results.length; i += 1) {
        var piece = event.results[i][0].transcript;
        if (event.results[i].isFinal) finals += piece;
        else interim += piece;
      }
      handlers.onText((finals + interim).trim(), Boolean(finals));
    };
    recognition.onerror = function (event) {
      if (event.error === "no-speech" || event.error === "aborted" || event.error === "network") return;
      if (handlers.onError) handlers.onError("没听清楚，请再说一次");
    };
    recognition.onend = function () {
      if (stopped) return;
      try {
        recognition.start();
      } catch (err) {}
    };
    try {
      recognition.start();
    } catch (err) {
      if (handlers.onError) handlers.onError("麦克风还没打开，请允许后再点一次");
    }
    if (audioCaptureAllowed() && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder) {
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
        if (stopped) { stream.getTracks().forEach(function (track) { track.stop(); }); return; }
        audioStream = stream;
        recorder = new MediaRecorder(stream);
        recorder.ondataavailable = function (event) { if (event.data && event.data.size) chunks.push(event.data); };
        recorder.onstop = function () {
          if (audioStream) audioStream.getTracks().forEach(function (track) { track.stop(); });
          if (keepRecording && chunks.length && handlers.onAudio) {
            var blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
            var duration = Date.now() - recordStarted;
            analyzeAudio(blob).then(function (metrics) {
              metrics.response_latency_ms = firstSpeechAt ? Math.max(0, firstSpeechAt - recognitionStartedAt) : 0;
              handlers.onAudio(blob, duration, metrics, recordingTranscript);
            });
          }
        };
        recordStarted = Date.now();
        recorder.start(500);
      }).catch(function () {});
    }
    return function (keep, transcript) {
      stopped = true;
      keepRecording = Boolean(keep);
      recordingTranscript = transcript || "";
      try {
        recognition.stop();
      } catch (err) {
        try {
          recognition.abort();
        } catch (err2) {}
      }
      if (recorder && recorder.state !== "inactive") recorder.stop();
      else if (audioStream) audioStream.getTracks().forEach(function (track) { track.stop(); });
    };
  }

  function pickVoice() {
    var voices = window.speechSynthesis.getVoices();
    return (
      voices.find(function (item) {
        return item.lang.indexOf("zh") === 0 && /Xiaoyi|Yunxi|Xiaoxiao|Huihui|Yaoyao/i.test(item.name);
      }) ||
      voices.find(function (item) {
        return item.lang.indexOf("zh") === 0;
      }) ||
      null
    );
  }

  function systemSpeak(text, rate) {
    if (!text || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    var utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-CN";
    utterance.rate = Math.min(1.1, Math.max(0.6, rate == null ? 0.82 : rate));
    utterance.pitch = 0.95;
    var voice = pickVoice();
    if (voice) utterance.voice = voice;
    window.speechSynthesis.speak(utterance);
  }

  function speak(text, rate) {
    if (!text) return;
    var scopes = global.NB && NB.getConsentScopes ? NB.getConsentScopes() : {};
    if (!scopes.voice_personalization || !global.NB || !NB.synthesizeSpeech) {
      systemSpeak(text, rate);
      return;
    }
    var generation = ++speechGeneration;
    stopSpeaking(false);
    NB.synthesizeSpeech(text).then(function (blob) {
      if (generation !== speechGeneration) return;
      var url = URL.createObjectURL(blob);
      personalAudio = new Audio(url);
      personalAudio.playbackRate = Math.min(1.1, Math.max(0.6, rate == null ? 0.82 : rate));
      personalAudio.onended = function () { URL.revokeObjectURL(url); personalAudio = null; };
      return personalAudio.play();
    }).catch(function () {
      if (generation === speechGeneration) systemSpeak(text, rate);
    });
  }

  function stopSpeaking(invalidate) {
    if (invalidate !== false) speechGeneration += 1;
    if (personalAudio) {
      personalAudio.pause();
      personalAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }

  function splitSentences(buffer) {
    var ready = [];
    var matcher = /[^。！？\n]+[。！？\n]/g;
    var match = matcher.exec(buffer);
    var last = 0;
    while (match) {
      ready.push(match[0].trim());
      last = match.index + match[0].length;
      match = matcher.exec(buffer);
    }
    return { ready: ready, rest: buffer.slice(last) };
  }

  global.NBSpeech = {
    canListen: canListen,
    startListening: startListening,
    speak: speak,
    stopSpeaking: stopSpeaking,
    splitSentences: splitSentences,
  };
})(window);
