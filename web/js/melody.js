(function (global) {
  var audio = null;
  var playing = false;
  var oscillators = [];

  function ctx() {
    if (!audio) audio = new AudioContext();
    return audio;
  }

  function stopMelody() {
    playing = false;
    oscillators.forEach(function (node) {
      try {
        node.stop();
      } catch (err) {}
    });
    oscillators = [];
  }

  function playMelody(notes, tempo) {
    tempo = tempo || 0.42;
    var context = ctx();
    var startPlay = function () {
      stopMelody();
      playing = true;
      var start = context.currentTime + 0.05;
      notes.forEach(function (freq, index) {
        var osc = context.createOscillator();
        var gain = context.createGain();
        osc.type = "triangle";
        osc.frequency.value = freq;
        var t = start + index * tempo;
        gain.gain.setValueAtTime(0.0001, t);
        gain.gain.exponentialRampToValueAtTime(0.09, t + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + (index + 0.92) * tempo);
        osc.connect(gain);
        gain.connect(context.destination);
        osc.start(t);
        osc.stop(start + (index + 1) * tempo);
        oscillators.push(osc);
      });
      var last = notes.length * tempo;
      setTimeout(function () {
        if (playing) playing = false;
      }, last * 1000 + 80);
    };
    if (context.state === "suspended") return context.resume().then(startPlay);
    startPlay();
    return Promise.resolve();
  }

  global.NBMelody = {
    stopMelody: stopMelody,
    playMelody: playMelody,
    isPlaying: function () {
      return playing;
    },
  };
})(window);
