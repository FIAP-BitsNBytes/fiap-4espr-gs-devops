// Tutor virtual: envia só a pergunta para /api/v1/tutor e mostra a resposta.
(function () {
  var form = document.getElementById("tutor-form");
  if (!form) return;
  var saida = document.getElementById("tutor-resposta");
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var pergunta = document.getElementById("pergunta").value.trim();
    if (!pergunta) return;
    saida.hidden = false;
    saida.textContent = "Pensando…";
    fetch("/api/v1/tutor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pergunta: pergunta })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) { saida.textContent = d.resposta || d.erro || "Sem resposta."; })
      .catch(function () {
        saida.textContent = "Sem conexão agora. Tente de novo quando a internet voltar.";
      });
  });
})();
